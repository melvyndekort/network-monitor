"""Tests for event_router Lambda."""
import json
import os
import time
import uuid
from unittest.mock import MagicMock

import pytest

# Set env vars BEFORE importing handler
os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
os.environ['AWS_SECURITY_TOKEN'] = 'testing'
os.environ['AWS_SESSION_TOKEN'] = 'testing'
os.environ['AWS_DEFAULT_REGION'] = 'eu-west-1'
os.environ['DEVICES_TABLE'] = 'test-devices'
os.environ['EVENTS_TABLE'] = 'test-events'
os.environ['DEDUP_TABLE'] = 'test-dedup'
os.environ['TOPIC_DISCOVERED'] = 'arn:aws:sns:eu-west-1:123456789012:device-discovered'
os.environ['TOPIC_NOTIFICATIONS'] = 'arn:aws:sns:eu-west-1:123456789012:notifications'

from moto import mock_aws  # pylint: disable=wrong-import-position
import boto3  # pylint: disable=wrong-import-position
from handler import (  # pylint: disable=wrong-import-position
    handler, normalize_event, compute_mac_type, OFFLINE_GRACE, ONLINE_TTL,
)


@pytest.fixture(name='dynamodb')
def fixture_dynamodb():
    """Set up mock AWS resources."""
    with mock_aws():
        ddb = boto3.resource('dynamodb', region_name='eu-west-1')

        ddb.create_table(
            TableName='test-devices',
            KeySchema=[{'AttributeName': 'mac', 'KeyType': 'HASH'}],
            AttributeDefinitions=[
                {'AttributeName': 'mac', 'AttributeType': 'S'},
                {'AttributeName': 'hostname', 'AttributeType': 'S'},
            ],
            GlobalSecondaryIndexes=[{
                'IndexName': 'hostname-index',
                'KeySchema': [{'AttributeName': 'hostname', 'KeyType': 'HASH'}],
                'Projection': {'ProjectionType': 'ALL'},
            }],
            BillingMode='PAY_PER_REQUEST'
        )

        ddb.create_table(
            TableName='test-events',
            KeySchema=[
                {'AttributeName': 'mac', 'KeyType': 'HASH'},
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'mac', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'N'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )

        ddb.create_table(
            TableName='test-dedup',
            KeySchema=[{'AttributeName': 'dedup_key', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'dedup_key', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )

        sns = boto3.client('sns', region_name='eu-west-1')
        sns.create_topic(Name='device-discovered')
        sns.create_topic(Name='notifications')

        yield ddb


def _make_sqs_event(*events):
    """Build SQS event with one or more raw events, each in its own record."""
    return {
        'Records': [
            {'messageId': str(uuid.uuid4()), 'body': json.dumps(evt)}
            for evt in events
        ]
    }


def _make_batched_sqs_event(*events):
    """Build a single SQS record carrying multiple bundled events."""
    return {
        'Records': [
            {'messageId': str(uuid.uuid4()), 'body': json.dumps({'events': list(events)})}
        ]
    }


def _make_raw_event(mac='aa:bb:cc:dd:ee:ff', ip='10.204.10.100', hostname=None):
    """Build a raw device event."""
    return {
        'timestamp': '2026-03-11T12:00:00Z',
        'source': 'data_collector',
        'event_type': 'device_activity',
        'mac': mac,
        'ip': ip,
        'hostname': hostname,
        'vlan': 10,
        'metadata': {}
    }


def _subscribe_notifications_queue():
    """Create SQS queue subscribed to notifications topic, return queue URL."""
    sqs = boto3.client('sqs', region_name='eu-west-1')
    queue = sqs.create_queue(QueueName='test-notif')
    queue_url = queue['QueueUrl']
    queue_arn = sqs.get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=['QueueArn']
    )['Attributes']['QueueArn']
    sns = boto3.client('sns', region_name='eu-west-1')
    topics = sns.list_topics()['Topics']
    notif_arn = [t['TopicArn'] for t in topics if 'notifications' in t['TopicArn']][0]
    sns.subscribe(TopicArn=notif_arn, Protocol='sqs', Endpoint=queue_arn)
    return queue_url


def _get_notification_messages(queue_url):
    """Read messages from the notifications SQS queue."""
    sqs = boto3.client('sqs', region_name='eu-west-1')
    return sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10).get('Messages', [])


def test_normalize_event():
    """Test event normalization."""
    body = _make_raw_event()
    result = normalize_event(body)
    assert result['mac'] == 'AA:BB:CC:DD:EE:FF'
    assert result['event_type'] == 'device_activity'
    assert result['ip'] == '10.204.10.100'
    # 0xAA = 0b10101010 - the U/L bit (0x02) is set on this conventional test MAC
    assert result['mac_type'] == 'locally_administered'


def test_normalize_event_invalid():
    """Test normalization with invalid event."""
    assert normalize_event({'invalid': 'data'}) is None


@pytest.mark.parametrize('mac,expected', [
    ('00:11:22:33:44:55', 'vendor'),        # 0x00 = 00000000, bit 0x02 unset
    ('02:00:00:00:00:01', 'locally_administered'),
    ('2A:FB:8C:D1:4B:A0', 'locally_administered'),  # real randomized MAC seen in prod
    ('98:5F:41:66:CB:4B', 'vendor'),  # real vendor (Intel) MAC seen in prod
])
def test_compute_mac_type(mac, expected):
    """Test U/L-bit classification against known real-world MAC examples."""
    assert compute_mac_type(mac) == expected


def test_handler_new_device(dynamodb):
    """Test handler creates device and publishes to TOPIC_DISCOVERED."""
    result = handler(_make_sqs_event(_make_raw_event()), None)
    assert result['statusCode'] == 200
    assert result['batchItemFailures'] == []

    devices_table = dynamodb.Table('test-devices')
    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert 'Item' in response
    assert response['Item']['notify'] is False
    assert response['Item']['mac_type'] == 'locally_administered'
    assert 'ttl' not in response['Item']
    assert 'hostname' not in response['Item']


def test_handler_new_device_with_hostname_sets_gsi_key(dynamodb):
    """Test a new device with a hostname is written with the hostname attribute set."""
    handler(_make_sqs_event(_make_raw_event(hostname='some-device')), None)

    devices_table = dynamodb.Table('test-devices')
    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert response['Item']['hostname'] == 'some-device'


def test_handler_existing_device_updates_fields(dynamodb):
    """Test handler updates last_ip, online_until, and last_ap for existing device."""
    devices_table = dynamodb.Table('test-devices')
    now = int(time.time())
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'name': 'Test Device',
        'notify': True,
        'first_seen': now,
        'last_seen': now,
        'online_until': now + ONLINE_TTL,
    })

    event = _make_raw_event(ip='10.204.10.101')
    event['metadata'] = {'ap': '10.204.50.13'}
    result = handler(_make_sqs_event(event), None)
    assert result['statusCode'] == 200

    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert response['Item']['last_ip'] == '10.204.10.101'
    assert response['Item']['last_ap'] == '10.204.50.13'


def test_existing_device_activity_without_hostname_does_not_clear_it(dynamodb):
    """A ping with no hostname (e.g. WiFi-only, no ARP/DHCP match) must not
    blank out a device's already-known hostname."""
    devices_table = dynamodb.Table('test-devices')
    now = int(time.time())
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'hostname': 'known-hostname',
        'notify': True,
        'online_until': now + ONLINE_TTL,
    })

    handler(_make_sqs_event(_make_raw_event(hostname=None)), None)

    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert response['Item']['hostname'] == 'known-hostname'


def test_mac_rotation_links_identity_instead_of_new_discovery(dynamodb):
    """A new MAC with a hostname matching an existing device is a rotation, not a new discovery."""
    old_mac = '11:22:33:00:00:01'
    new_mac = '11:22:33:00:00:02'
    devices_table = dynamodb.Table('test-devices')
    now = int(time.time())
    devices_table.put_item(Item={
        'mac': old_mac,
        'hostname': 'Galaxy-A17-5G',
        'name': 'Daan phone',
        'notify': True,
        'first_seen': now - 1000,
        'last_seen': now - 1000,
        'online_until': now - OFFLINE_GRACE - 60,
    })

    queue_url = _subscribe_notifications_queue()
    result = handler(
        _make_sqs_event(_make_raw_event(mac=new_mac, hostname='Galaxy-A17-5G')),
        None,
    )
    assert result['statusCode'] == 200

    # Old identity migrated to the new MAC, old MAC item removed.
    old_response = devices_table.get_item(Key={'mac': old_mac})
    assert 'Item' not in old_response

    new_response = devices_table.get_item(Key={'mac': new_mac})
    assert new_response['Item']['name'] == 'Daan phone'
    assert new_response['Item']['notify'] is True

    # Notification fires (as a rotation notice), but never on TOPIC_DISCOVERED.
    messages = _get_notification_messages(queue_url)
    assert len(messages) == 1
    message = json.loads(json.loads(messages[0]['Body'])['Message'])
    assert message['new_state'] == 'rotated'
    assert message['previous_mac'] == old_mac


def test_update_last_seen_removes_hostname_when_neither_side_has_one(monkeypatch):
    """A device with no known hostname, pinged by an event with no hostname,
    must issue a REMOVE for hostname. Real-world reason: a device written by
    the old create_device (pre-dating the hostname-index GSI) can have an
    explicit NULL-type hostname attribute, and DynamoDB rejects ANY write to
    such an item - not just ones touching hostname - once a GSI exists on
    that attribute. REMOVE is a no-op when the attribute was already absent,
    so this is always safe, not just for the legacy-data case."""
    import handler as handler_module  # pylint: disable=import-outside-toplevel

    mock_table = MagicMock()
    monkeypatch.setattr(handler_module, 'devices_table', mock_table)

    handler_module.update_device_last_seen(
        'AA:BB:CC:DD:EE:FF', _make_raw_event(hostname=None), {'hostname': None}
    )

    call_kwargs = mock_table.update_item.call_args.kwargs
    assert 'REMOVE hostname' in call_kwargs['UpdateExpression']


def test_update_last_seen_keeps_existing_hostname_untouched(monkeypatch):
    """A device with an already-known real hostname, pinged by an event with
    no hostname, must neither SET nor REMOVE hostname."""
    import handler as handler_module  # pylint: disable=import-outside-toplevel

    mock_table = MagicMock()
    monkeypatch.setattr(handler_module, 'devices_table', mock_table)

    handler_module.update_device_last_seen(
        'AA:BB:CC:DD:EE:FF', _make_raw_event(hostname=None), {'hostname': 'known-host'}
    )

    call_kwargs = mock_table.update_item.call_args.kwargs
    assert 'hostname' not in call_kwargs['UpdateExpression']


def test_no_notification_when_device_still_online(dynamodb):
    """Test no notification when device online_until is in the future."""
    devices_table = dynamodb.Table('test-devices')
    now = int(time.time())
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'name': 'Test Device',
        'notify': True,
        'online_until': now + 600,
    })

    queue_url = _subscribe_notifications_queue()
    handler(_make_sqs_event(_make_raw_event()), None)
    assert len(_get_notification_messages(queue_url)) == 0


def test_no_notification_within_offline_grace(dynamodb):
    """Test no notification when device offline less than OFFLINE_GRACE."""
    devices_table = dynamodb.Table('test-devices')
    now = int(time.time())
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'name': 'Test Device',
        'notify': True,
        'online_until': now - 300,
    })

    queue_url = _subscribe_notifications_queue()
    handler(_make_sqs_event(_make_raw_event()), None)
    assert len(_get_notification_messages(queue_url)) == 0


def test_notification_sent_after_offline_grace(dynamodb):
    """Test notification sent when device offline longer than OFFLINE_GRACE."""
    devices_table = dynamodb.Table('test-devices')
    now = int(time.time())
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'name': 'Test Device',
        'notify': True,
        'online_until': now - OFFLINE_GRACE - 60,
    })

    queue_url = _subscribe_notifications_queue()
    handler(_make_sqs_event(_make_raw_event()), None)

    messages = _get_notification_messages(queue_url)
    assert len(messages) == 1
    body = json.loads(messages[0]['Body'])
    message = json.loads(body['Message'])
    assert message['new_state'] == 'online'


@pytest.mark.usefixtures('dynamodb')
def test_new_device_discovery_sets_new_state():
    """New-device discovery messages carry new_state=discovered (previously unset)."""
    queue_url = _subscribe_notifications_queue()
    handler(_make_sqs_event(_make_raw_event()), None)

    messages = _get_notification_messages(queue_url)
    assert len(messages) == 1
    message = json.loads(json.loads(messages[0]['Body'])['Message'])
    assert message['new_state'] == 'discovered'


def test_batched_events_format(dynamodb):
    """Test handler processes {"events": [...]} batch format."""
    event1 = _make_raw_event(mac='aa:bb:cc:00:00:01', ip='10.204.10.1')
    event2 = _make_raw_event(mac='aa:bb:cc:00:00:02', ip='10.204.10.2')

    result = handler(_make_batched_sqs_event(event1, event2), None)
    assert result['statusCode'] == 200

    devices_table = dynamodb.Table('test-devices')
    assert 'Item' in devices_table.get_item(Key={'mac': 'AA:BB:CC:00:00:01'})
    assert 'Item' in devices_table.get_item(Key={'mac': 'AA:BB:CC:00:00:02'})


def test_dedup_skips_duplicate_in_same_batch(dynamodb):
    """Test that duplicate events in same batch are deduplicated."""
    event = _make_raw_event()

    result = handler(_make_batched_sqs_event(event, event), None)
    assert result['statusCode'] == 200

    events_table = dynamodb.Table('test-events')
    response = events_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('mac').eq('AA:BB:CC:DD:EE:FF')
    )
    assert response['Count'] == 1


@pytest.mark.usefixtures('dynamodb')
def test_handler_empty_events():
    """Test handler with no valid events returns early."""
    result = handler({
        'Records': [{'messageId': str(uuid.uuid4()), 'body': json.dumps({'invalid': 'data'})}]
    }, None)
    assert result['statusCode'] == 200


def test_one_bad_record_does_not_fail_other_records_in_batch(dynamodb, monkeypatch):
    """A failure routing one record's event must not affect other records' processing,
    and the failing record's messageId is reported for partial-batch retry."""
    import handler as handler_module  # pylint: disable=import-outside-toplevel

    original_route = handler_module._route_event  # pylint: disable=protected-access

    def flaky_route(normalized, now):
        if normalized['mac'] == 'BA:D0:00:00:00:01':
            raise handler_module.ClientError(
                {'Error': {'Code': 'ValidationException', 'Message': 'boom'}},
                'PutItem',
            )
        return original_route(normalized, now)

    monkeypatch.setattr(handler_module, '_route_event', flaky_route)

    good_event = _make_raw_event(mac='aa:bb:cc:00:00:03')
    bad_event = _make_raw_event(mac='ba:d0:00:00:00:01')
    sqs_event = _make_sqs_event(good_event, bad_event)
    bad_message_id = sqs_event['Records'][1]['messageId']

    result = handler_module.handler(sqs_event, None)

    assert result['batchItemFailures'] == [{'itemIdentifier': bad_message_id}]

    devices_table = dynamodb.Table('test-devices')
    assert 'Item' in devices_table.get_item(Key={'mac': 'AA:BB:CC:00:00:03'})
    assert 'Item' not in devices_table.get_item(Key={'mac': 'BA:D0:00:00:00:01'})
