"""Tests for api_handler Lambda."""
import json
import os

# Set env vars BEFORE importing handler
os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
os.environ['AWS_DEFAULT_REGION'] = 'eu-west-1'
os.environ['DEVICES_TABLE'] = 'test-devices'

# pylint: disable=wrong-import-position
from moto import mock_aws  # noqa: E402
import boto3  # noqa: E402
from handler import handler  # noqa: E402
# pylint: enable=wrong-import-position


@mock_aws
def _create_table():
    """Create mock DynamoDB table."""
    dynamodb = boto3.resource('dynamodb', region_name='eu-west-1')
    dynamodb.create_table(
        TableName='test-devices',
        KeySchema=[{'AttributeName': 'mac', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'mac', 'AttributeType': 'S'}],
        BillingMode='PAY_PER_REQUEST'
    )
    return dynamodb


def _make_event(method, path, body=None):
    """Build a Lambda function URL event."""
    event = {'requestContext': {'http': {'method': method, 'path': path}}}
    if body is not None:
        event['body'] = json.dumps(body)
    return event


@mock_aws
def test_list_devices():
    """Test listing all devices."""
    dynamodb = _create_table()
    table = dynamodb.Table('test-devices')
    table.put_item(Item={'mac': 'AA:BB:CC:DD:EE:FF', 'name': 'Device 1'})
    table.put_item(Item={'mac': '11:22:33:44:55:66', 'name': 'Device 2'})

    result = handler(_make_event('GET', '/devices'), None)

    assert result['statusCode'] == 200
    body = json.loads(result['body'])
    assert len(body['devices']) == 2


@mock_aws
def test_get_device():
    """Test getting specific device."""
    dynamodb = _create_table()
    table = dynamodb.Table('test-devices')
    table.put_item(Item={'mac': 'AA:BB:CC:DD:EE:FF', 'name': 'Test Device'})

    result = handler(_make_event('GET', '/devices/AA:BB:CC:DD:EE:FF'), None)

    assert result['statusCode'] == 200
    body = json.loads(result['body'])
    assert body['name'] == 'Test Device'


@mock_aws
def test_get_device_not_found():
    """Test getting non-existent device."""
    _create_table()

    result = handler(_make_event('GET', '/devices/AA:BB:CC:DD:EE:FF'), None)

    assert result['statusCode'] == 404


@mock_aws
def test_update_device():
    """Test updating device."""
    dynamodb = _create_table()
    table = dynamodb.Table('test-devices')
    table.put_item(Item={'mac': 'AA:BB:CC:DD:EE:FF', 'name': 'Old Name'})

    result = handler(
        _make_event('PUT', '/devices/AA:BB:CC:DD:EE:FF', {'name': 'New Name', 'notify': True}),
        None
    )

    assert result['statusCode'] == 200
    response = table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert response['Item']['name'] == 'New Name'
    assert response['Item']['notify'] is True


@mock_aws
def test_delete_device():
    """Test deleting device."""
    dynamodb = _create_table()
    table = dynamodb.Table('test-devices')
    table.put_item(Item={'mac': 'AA:BB:CC:DD:EE:FF', 'name': 'Test'})

    result = handler(_make_event('DELETE', '/devices/AA:BB:CC:DD:EE:FF'), None)

    assert result['statusCode'] == 200
    response = table.get_item(Key={'mac': 'AA:BB:CC:DD:EE:FF'})
    assert 'Item' not in response
