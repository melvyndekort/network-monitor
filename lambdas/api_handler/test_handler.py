"""Tests for api_handler Lambda."""
import json
import os
import pytest

# Set env vars BEFORE importing handler
os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
os.environ['AWS_DEFAULT_REGION'] = 'eu-west-1'
os.environ['DEVICES_TABLE'] = 'test-devices'

from moto import mock_aws
import boto3
from handler import handler


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
        
        yield dynamodb


def test_list_devices(aws_setup):
    """Test listing all devices."""
    devices_table = aws_setup.Table('test-devices')
    devices_table.put_item(Item={'mac': 'AA:BB:CC:DD:EE:FF', 'name': 'Device 1'})
    devices_table.put_item(Item={'mac': '11:22:33:44:55:66', 'name': 'Device 2'})
    
    event = {
        'requestContext': {
            'http': {
                'method': 'GET',
                'path': '/devices'
            }
        }
    }
    
    result = handler(event, None)
    
    assert result['statusCode'] == 200
    body = json.loads(result['body'])
    assert len(body['devices']) == 2


def test_get_device(aws_setup):
    """Test getting specific device."""
    devices_table = aws_setup.Table('test-devices')
    devices_table.put_item(Item={'mac': 'AA:BB:CC:DD:EE:FF', 'name': 'Test Device'})
    
    event = {
        'requestContext': {
            'http': {
                'method': 'GET',
                'path': '/devices/AA:BB:CC:DD:EE:FF'
            }
        }
    }
    
    result = handler(event, None)
    
    assert result['statusCode'] == 200
    body = json.loads(result['body'])
    assert body['name'] == 'Test Device'


def test_get_device_not_found(aws_setup):
    """Test getting non-existent device."""
    event = {
        'requestContext': {
            'http': {
                'method': 'GET',
                'path': '/devices/AA:BB:CC:DD:EE:FF'
            }
        }
    }
    
    result = handler(event, None)
    
    assert result['statusCode'] == 404


def test_update_device(aws_setup):
    """Test updating device."""
    devices_table = aws_setup.Table('test-devices')
    devices_table.put_item(Item={'mac': 'AA:BB:CC:DD:EE:FF', 'name': 'Old Name'})
    
    event = {
        'requestContext': {
            'http': {
                'method': 'PUT',
                'path': '/devices/AA:BB:CC:DD:EE:FF'
            }
        },
        'body': json.dumps({'name': 'New Name', 'notify': True})
    }
    
    result = handler(event, None)
    
    assert result['statusCode'] == 200
    
    # Verify update
    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert response['Item']['name'] == 'New Name'
    assert response['Item']['notify'] is True


def test_delete_device(aws_setup):
    """Test deleting device."""
    devices_table = aws_setup.Table('test-devices')
    devices_table.put_item(Item={'mac': 'AA:BB:CC:DD:EE:FF', 'name': 'Test'})
    
    event = {
        'requestContext': {
            'http': {
                'method': 'DELETE',
                'path': '/devices/AA:BB:CC:DD:EE:FF'
            }
        }
    }
    
    result = handler(event, None)
    
    assert result['statusCode'] == 200
    
    # Verify deletion
    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert 'Item' not in response
