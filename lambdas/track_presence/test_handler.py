"""Tests for track_presence Lambda."""
import json
import os
import time
import pytest

# Set env vars BEFORE importing handler
os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
os.environ['AWS_DEFAULT_REGION'] = 'eu-west-1'
os.environ['DEVICES_TABLE'] = 'test-devices'
os.environ['TOPIC_STATE_CHANGED'] = 'arn:aws:sns:eu-west-1:123456789012:state-changed'

from moto import mock_aws
import boto3
from handler import handler, determine_state


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
        
        sns = boto3.client('sns', region_name='eu-west-1')
        sns.create_topic(Name='state-changed')
        
        yield dynamodb


def test_determine_state_online():
    """Test state determination for online device."""
    device = {'last_seen': int(time.time()) - 60}  # 1 minute ago
    assert determine_state(device) == 'online'


def test_determine_state_offline():
    """Test state determination for offline device."""
    device = {'last_seen': int(time.time()) - 1000}  # 16+ minutes ago
    assert determine_state(device) == 'offline'


def test_handler_state_change_to_online(aws_setup):
    """Test state change from offline to online."""
    devices_table = aws_setup.Table('test-devices')
    
    # Create device that's offline
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'current_state': 'offline',
        'last_seen': int(time.time()) - 60,  # Recently seen
        'notify': True
    })
    
    event = {
        'Records': [{
            'body': json.dumps({
                'Message': json.dumps({
                    'mac': 'AA:BB:CC:DD:EE:FF'
                })
            })
        }]
    }
    
    result = handler(event, None)
    
    assert result['statusCode'] == 200
    
    # Check state changed to online
    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert response['Item']['current_state'] == 'online'
    assert 'last_online' in response['Item']


def test_handler_state_change_to_offline(aws_setup):
    """Test state change from online to offline."""
    devices_table = aws_setup.Table('test-devices')
    
    # Create device that's online but hasn't been seen
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'current_state': 'online',
        'last_seen': int(time.time()) - 1000,  # 16+ minutes ago
        'notify': True
    })
    
    event = {
        'Records': [{
            'body': json.dumps({
                'Message': json.dumps({
                    'mac': 'AA:BB:CC:DD:EE:FF'
                })
            })
        }]
    }
    
    result = handler(event, None)
    
    assert result['statusCode'] == 200
    
    # Check state changed to offline
    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert response['Item']['current_state'] == 'offline'
    assert 'last_offline' in response['Item']


def test_handler_no_state_change(aws_setup):
    """Test when state doesn't change."""
    devices_table = aws_setup.Table('test-devices')
    
    # Create device that's online and recently seen
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'current_state': 'online',
        'last_seen': int(time.time()) - 60,
        'notify': True
    })
    
    event = {
        'Records': [{
            'body': json.dumps({
                'Message': json.dumps({
                    'mac': 'AA:BB:CC:DD:EE:FF'
                })
            })
        }]
    }
    
    result = handler(event, None)
    
    assert result['statusCode'] == 200
    
    # State should still be online
    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert response['Item']['current_state'] == 'online'
