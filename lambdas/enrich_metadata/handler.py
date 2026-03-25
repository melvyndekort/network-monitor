"""Metadata enricher Lambda - Lookup manufacturer."""
import json
import logging
import os
import time
import boto3
import urllib3

logger = logging.getLogger(__name__)

# DynamoDB setup (initialized once per container)
dynamodb = boto3.resource('dynamodb')
devices_table = dynamodb.Table(os.environ.get('DEVICES_TABLE', ''))

# HTTP client
http = urllib3.PoolManager()


def handler(event, _context):
    """Enrich device metadata."""
    for record in event['Records']:
        body = json.loads(record['body'])
        message = json.loads(body['Message'])

        mac = message['mac']
        device = get_device(mac)

        if not device or device.get('manufacturer'):
            continue

        time.sleep(1)  # Rate limit

        manufacturer = lookup_manufacturer(mac)
        if manufacturer:
            update_manufacturer(mac, manufacturer)

    return {'statusCode': 200}


def get_device(mac):
    """Get device from DynamoDB."""
    response = devices_table.get_item(Key={'mac': mac})
    return response.get('Item')


def update_manufacturer(mac, manufacturer):
    """Update device manufacturer."""
    devices_table.update_item(
        Key={'mac': mac},
        UpdateExpression='SET manufacturer = :m',
        ExpressionAttributeValues={':m': manufacturer}
    )


def lookup_manufacturer(mac):
    """Lookup manufacturer via MAC address."""
    try:
        response = http.request(
            'GET', f"https://api.macvendors.com/{mac}"
        )
        if response.status == 200:
            return response.data.decode('utf-8')
    except (urllib3.exceptions.HTTPError, OSError):
        logger.exception("Manufacturer lookup failed")
    return 'Unknown'
