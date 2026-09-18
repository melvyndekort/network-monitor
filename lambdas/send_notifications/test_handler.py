"""Tests for send_notifications Lambda."""
import json
import os
import pytest
from unittest.mock import patch, MagicMock

# Set env vars BEFORE importing handler
os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
os.environ['AWS_DEFAULT_REGION'] = 'eu-west-1'
os.environ['DEVICES_TABLE'] = 'test-devices'
os.environ['THROTTLE_TABLE'] = 'test-throttle'
os.environ['APPRISE_URL'] = 'http://apprise.test'

from moto import mock_aws
import boto3

# Start moto mock, create SSM parameters, import handler, then stop
# (handler fetches SSM at module level)
_mock = mock_aws()
_mock.start()

ssm = boto3.client('ssm', region_name='eu-west-1')
ssm.put_parameter(Name='/network-monitor/cf-access-client-id', Value='test-id', Type='SecureString')
ssm.put_parameter(Name='/network-monitor/cf-access-client-secret', Value='test-secret', Type='SecureString')

from handler import handler, format_notification

_mock.stop()


@pytest.fixture
def aws_setup():
    """Set up mock AWS resources."""
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='eu-west-1')
        
        dynamodb.create_table(
            TableName='test-devices',
            KeySchema=[{'AttributeName': 'mac', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'mac', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        
        dynamodb.create_table(
            TableName='test-throttle',
            KeySchema=[{'AttributeName': 'throttle_key', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'throttle_key', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        
        yield dynamodb


def test_format_notification_new_device():
    """Test notification formatting for a new vendor-MAC device."""
    device = {
        'mac': 'AA:BB:CC:DD:EE:FF',
        'name': 'Test Device',
        'last_ip': '10.204.10.100',
        'last_vlan': 10,
        'manufacturer': 'Apple'
    }
    message = {'event_type': 'device_activity', 'new_state': 'discovered', 'mac_type': 'vendor'}

    title, body = format_notification(device, message)

    assert '🆕' in title
    assert 'AA:BB:CC:DD:EE:FF' in body
    assert '10.204.10.100' in body


def test_format_notification_new_device_randomized_mac_is_high_priority():
    """A new device with a locally-administered MAC gets a distinct, urgent title."""
    device = {'mac': 'AA:BB:CC:DD:EE:FF', 'manufacturer': 'Unknown'}
    message = {
        'event_type': 'device_activity',
        'new_state': 'discovered',
        'mac_type': 'locally_administered',
    }

    title, _ = format_notification(device, message)

    assert '🚨' in title


def test_format_notification_rotated_device():
    """Test notification formatting for a MAC-rotation identity link."""
    device = {'mac': 'NEW:MA:C0:00:00:02', 'name': 'Daan phone'}
    message = {'new_state': 'rotated', 'previous_mac': 'OLD:MA:C0:00:00:01'}

    title, body = format_notification(device, message)

    assert 'Re-identified' in title
    assert 'OLD:MA:C0:00:00:01' in body


def test_format_notification_offline():
    """Test notification formatting for offline device."""
    device = {'mac': 'AA:BB:CC:DD:EE:FF', 'name': 'Test Device'}
    message = {'new_state': 'offline'}
    
    title, body = format_notification(device, message)
    
    assert '📴' in title
    assert 'Test Device' in body


@patch('handler.http')
def test_handler_sends_notification(mock_http, aws_setup):
    """Test handler sends notification."""
    devices_table = aws_setup.Table('test-devices')
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'name': 'Test Device',
        'notify': True
    })
    
    event = {
        'Records': [{
            'body': json.dumps({
                'Message': json.dumps({
                    'mac': 'AA:BB:CC:DD:EE:FF',
                    'new_state': 'offline'
                })
            })
        }]
    }
    
    result = handler(event, None)
    
    assert result['statusCode'] == 200
    assert mock_http.request.called


@patch('handler.http')
def test_handler_respects_throttle(mock_http, aws_setup):
    """Test handler respects throttle."""
    devices_table = aws_setup.Table('test-devices')
    throttle_table = aws_setup.Table('test-throttle')
    
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'notify': True
    })
    
    # Set throttle
    throttle_table.put_item(Item={
        'throttle_key': 'AA:BB:CC:DD:EE:FF#offline',
        'ttl': 9999999999
    })
    
    event = {
        'Records': [{
            'body': json.dumps({
                'Message': json.dumps({
                    'mac': 'AA:BB:CC:DD:EE:FF',
                    'new_state': 'offline'
                })
            })
        }]
    }
    
    result = handler(event, None)

    assert result['statusCode'] == 200
    assert not mock_http.request.called  # Should not send


def _make_event(mac, new_state, mac_type=None, previous_mac=None):
    """Build an SNS-wrapped SQS event for the handler."""
    message = {'mac': mac, 'new_state': new_state}
    if mac_type:
        message['mac_type'] = mac_type
    if previous_mac:
        message['previous_mac'] = previous_mac
    return {
        'Records': [{
            'body': json.dumps({'Message': json.dumps(message)})
        }]
    }


@patch('handler.http')
def test_discovery_notification_bypasses_notify_flag(mock_http, aws_setup):
    """A newly-discovered device (notify defaults to False) must still alert."""
    devices_table = aws_setup.Table('test-devices')
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'notify': False,
    })

    handler(_make_event('AA:BB:CC:DD:EE:FF', 'discovered', mac_type='vendor'), None)

    assert mock_http.request.called


@patch('handler.http')
def test_back_online_notification_respects_notify_flag(mock_http, aws_setup):
    """A known device with notify=False must not alert on back-online."""
    devices_table = aws_setup.Table('test-devices')
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'notify': False,
    })

    handler(_make_event('AA:BB:CC:DD:EE:FF', 'online'), None)

    assert not mock_http.request.called


@patch('handler.http')
def test_discovery_and_online_throttle_keys_do_not_collide(mock_http, aws_setup):
    """Discovery and a later back-online alert for the same MAC must not share
    a throttle bucket (previously both mapped to the same event_type key)."""
    devices_table = aws_setup.Table('test-devices')
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'notify': True,
    })

    handler(_make_event('AA:BB:CC:DD:EE:FF', 'discovered', mac_type='vendor'), None)
    handler(_make_event('AA:BB:CC:DD:EE:FF', 'online'), None)

    assert mock_http.request.call_count == 2


@patch('handler.http')
def test_throttle_not_set_when_delivery_fails(mock_http, aws_setup):
    """A failed Apprise delivery must not mark the alert as throttled -
    otherwise a transient failure silently suppresses the real alert."""
    devices_table = aws_setup.Table('test-devices')
    throttle_table = aws_setup.Table('test-throttle')
    devices_table.put_item(Item={'mac': 'AA:BB:CC:DD:EE:FF', 'notify': True})
    mock_http.request.side_effect = OSError('connection refused')

    handler(_make_event('AA:BB:CC:DD:EE:FF', 'online'), None)

    response = throttle_table.get_item(Key={'throttle_key': 'AA:BB:CC:DD:EE:FF#online'})
    assert 'Item' not in response
