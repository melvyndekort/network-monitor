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
from handler import handler, format_notification


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
    """Test notification formatting for new device."""
    device = {
        'mac': 'AA:BB:CC:DD:EE:FF',
        'name': 'Test Device',
        'last_ip': '10.204.10.100',
        'last_vlan': 10,
        'manufacturer': 'Apple'
    }
    message = {'event_type': 'device_discovered'}
    
    title, body = format_notification(device, message)
    
    assert '🆕' in title
    assert 'AA:BB:CC:DD:EE:FF' in body
    assert '10.204.10.100' in body


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
