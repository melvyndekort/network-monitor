"""Tests for enrich_metadata Lambda."""
import json
import os
import pytest
from unittest.mock import patch, MagicMock

# Set env vars BEFORE importing handler
os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
os.environ['AWS_DEFAULT_REGION'] = 'eu-west-1'
os.environ['DEVICES_TABLE'] = 'test-devices'

from moto import mock_aws
import boto3
from handler import handler, lookup_manufacturer


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


@patch('handler.http')
def test_lookup_manufacturer_success(mock_http):
    """Test successful manufacturer lookup."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.data = b'Apple, Inc.'
    mock_http.request.return_value = mock_response
    
    result = lookup_manufacturer('AA:BB:CC:DD:EE:FF')
    
    assert result == 'Apple, Inc.'


@patch('handler.http')
def test_lookup_manufacturer_failure(mock_http):
    """Test failed manufacturer lookup."""
    mock_http.request.side_effect = OSError('Network error')
    
    result = lookup_manufacturer('AA:BB:CC:DD:EE:FF')
    
    assert result == 'Unknown'


@patch('handler.http')
@patch('handler.time.sleep')  # Skip sleep in tests
def test_handler_enriches_device(mock_sleep, mock_http, aws_setup):
    """Test handler enriches device metadata."""
    devices_table = aws_setup.Table('test-devices')
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'name': 'Test Device'
    })
    
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.data = b'Apple, Inc.'
    mock_http.request.return_value = mock_response
    
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
    
    # Check manufacturer was updated
    response = devices_table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert response['Item']['manufacturer'] == 'Apple, Inc.'


@patch('handler.http')
@patch('handler.time.sleep')
def test_handler_skips_existing_manufacturer(mock_sleep, mock_http, aws_setup):
    """Test handler skips devices that already have manufacturer."""
    devices_table = aws_setup.Table('test-devices')
    devices_table.put_item(Item={
        'mac': 'AA:BB:CC:DD:EE:FF',
        'manufacturer': 'Apple, Inc.'
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
    assert not mock_http.request.called  # Should not lookup
