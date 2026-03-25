"""Tests for event_router Lambda."""
import json
import os
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
os.environ['TOPIC_ACTIVITY'] = 'arn:aws:sns:eu-west-1:123456789012:device-activity'
os.environ['TOPIC_NOTIFICATIONS'] = 'arn:aws:sns:eu-west-1:123456789012:notifications'

from moto import mock_aws
import boto3
from handler import handler, normalize_event


@pytest.fixture
def aws_setup():
    """Set up mock AWS resources."""
    with mock_aws():
        # Create DynamoDB tables
        dynamodb = boto3.resource('dynamodb', region_name='eu-west-1')
        
        dynamodb.create_table(
            TableName='test-devices',
            KeySchema=[{'AttributeName': 'mac', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'mac', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        
        dynamodb.create_table(
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
        
        dynamodb.create_table(
            TableName='test-dedup',
            KeySchema=[{'AttributeName': 'dedup_key', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'dedup_key', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Create SNS topics
        sns = boto3.client('sns', region_name='eu-west-1')
        sns.create_topic(Name='device-discovered')
        sns.create_topic(Name='device-activity')
        sns.create_topic(Name='notifications')
        
        yield dynamodb


def test_normalize_event():
    """Test event normalization."""
    body = {
        'timestamp': '2026-03-11T12:00:00Z',
        'source': 'mikrotik_arp',
        'event_type': 'device_discovered',
        'mac': 'aa:bb:cc:dd:ee:ff',
        'ip': '10.204.10.100',
        'vlan': 10
    }
    
    result = normalize_event(body)
    
    assert result['mac'] == 'AA:BB:CC:DD:EE:FF'  # Uppercase
    assert result['event_type'] == 'device_discovered'
    assert result['ip'] == '10.204.10.100'


def test_normalize_event_invalid():
    """Test normalization with invalid event."""
    body = {'invalid': 'data'}
    result = normalize_event(body)
    assert result is None


def test_handler_new_device(aws_setup):
    """Test handler routes to TOPIC_DISCOVERED when device not in DB."""
    event = {
        'Records': [{
            'body': json.dumps({
                'timestamp': '2026-03-11T12:00:00Z',
                'source': 'data_collector',
                'event_type': 'device_activity',
                'mac': 'aa:bb:cc:dd:ee:ff',
                'ip': '10.204.10.100',
                'vlan': 10,
                'metadata': {}
            })
        }]
    }
    
    result = handler(event, None)
    
    assert result['statusCode'] == 200
    
    # Check device was created
    devices_table = aws_setup.Table('test-devices')
    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert 'Item' in response
    assert response['Item']['notify'] is False


def test_handler_existing_device(aws_setup):
    """Test handler with existing device."""
    # Create existing device
    devices_table = aws_setup.Table('test-devices')
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'name': 'Test Device',
        'current_state': 'online',
        'notify': True,
        'first_seen': 1000000,
        'last_seen': 1000000
    })
    
    event = {
        'Records': [{
            'body': json.dumps({
                'timestamp': '2026-03-11T12:00:00Z',
                'source': 'mikrotik_arp',
                'event_type': 'device_activity',
                'mac': 'aa:bb:cc:dd:ee:ff',
                'ip': '10.204.10.101',
                'vlan': 10,
                'metadata': {}
            })
        }]
    }
    
    result = handler(event, None)
    
    assert result['statusCode'] == 200
    
    # Check device was updated
    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert response['Item']['last_ip'] == '10.204.10.101'
