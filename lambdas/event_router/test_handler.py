"""Tests for event_router Lambda."""
import json
import os
import time

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
    handler, normalize_event, OFFLINE_GRACE, ONLINE_TTL,
)


@pytest.fixture(name='dynamodb')
def fixture_dynamodb():
    """Set up mock AWS resources."""
    with mock_aws():
        ddb = boto3.resource('dynamodb', region_name='eu-west-1')

        ddb.create_table(
            TableName='test-devices',
            KeySchema=[{'AttributeName': 'mac', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'mac', 'AttributeType': 'S'}],
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
    """Build SQS event with one or more raw events."""
    if len(events) == 1:
        return {'Records': [{'body': json.dumps(events[0])}]}
    return {'Records': [{'body': json.dumps({'events': list(events)})}]}


def _make_raw_event(mac='aa:bb:cc:dd:ee:ff', ip='10.204.10.100'):
    """Build a raw device event."""
    return {
        'timestamp': '2026-03-11T12:00:00Z',
        'source': 'data_collector',
        'event_type': 'device_activity',
        'mac': mac,
        'ip': ip,
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
    return sqs.receive_message(QueueUrl=queue_url).get('Messages', [])


def test_normalize_event():
    """Test event normalization."""
    body = _make_raw_event()
    result = normalize_event(body)
    assert result['mac'] == 'AA:BB:CC:DD:EE:FF'
    assert result['event_type'] == 'device_activity'
    assert result['ip'] == '10.204.10.100'


def test_normalize_event_invalid():
    """Test normalization with invalid event."""
    assert normalize_event({'invalid': 'data'}) is None


def test_handler_new_device(dynamodb):
    """Test handler creates device and publishes to TOPIC_DISCOVERED."""
    result = handler(_make_sqs_event(_make_raw_event()), None)
    assert result['statusCode'] == 200

    devices_table = dynamodb.Table('test-devices')
    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert 'Item' in response
    assert response['Item']['notify'] is False


def test_handler_existing_device_updates_fields(dynamodb):
    """Test handler updates last_ip and online_until for existing device."""
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

    result = handler(_make_sqs_event(_make_raw_event(ip='10.204.10.101')), None)
    assert result['statusCode'] == 200

    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert response['Item']['last_ip'] == '10.204.10.101'


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


def test_batched_events_format(dynamodb):
    """Test handler processes {"events": [...]} batch format."""
    event1 = _make_raw_event(mac='aa:bb:cc:00:00:01', ip='10.204.10.1')
    event2 = _make_raw_event(mac='aa:bb:cc:00:00:02', ip='10.204.10.2')

    result = handler(_make_sqs_event(event1, event2), None)
    assert result['statusCode'] == 200

    devices_table = dynamodb.Table('test-devices')
    assert 'Item' in devices_table.get_item(Key={'mac': 'AA:BB:CC:00:00:01'})
    assert 'Item' in devices_table.get_item(Key={'mac': 'AA:BB:CC:00:00:02'})


def test_dedup_skips_duplicate_in_same_batch(dynamodb):
    """Test that duplicate events in same batch are deduplicated."""
    event = _make_raw_event()

    result = handler({
        'Records': [
            {'body': json.dumps(event)},
            {'body': json.dumps(event)},
        ]
    }, None)
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
        'Records': [{'body': json.dumps({'invalid': 'data'})}]
    }, None)
    assert result['statusCode'] == 200
