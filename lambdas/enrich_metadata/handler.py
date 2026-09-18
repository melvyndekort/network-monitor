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

# Vendor lookup can never succeed for a randomized MAC - skip it entirely
# rather than retrying forever (previously: 3 chained external HTTP calls,
# every single day, indefinitely, for every locally-administered MAC).
RANDOMIZED_MAC_MANUFACTURER = 'Randomized MAC (no vendor)'


def handler(event, _context):
    """Enrich device metadata via SQS or scheduled retry."""
    if 'Records' in event:
        handle_sqs(event)
    else:
        handle_scheduled()
    return {'statusCode': 200}


def handle_sqs(event):
    """Process new device discovery events from SQS."""
    for record in event['Records']:
        body = json.loads(record['body'])
        message = json.loads(body['Message'])

        mac = message['mac']
        device = get_device(mac)

        if not device or device.get('manufacturer'):
            continue

        manufacturer = _resolve_manufacturer(mac, device.get('mac_type'))
        if manufacturer:
            update_manufacturer(mac, manufacturer)


def handle_scheduled():
    """Retry manufacturer lookup for unknown devices."""
    response = devices_table.scan(
        FilterExpression=(
            'attribute_not_exists(manufacturer)'
            ' OR manufacturer = :unk OR manufacturer = :none'
        ),
        ExpressionAttributeValues={':unk': 'Unknown', ':none': None}
    )
    for device in response.get('Items', []):
        manufacturer = _resolve_manufacturer(device['mac'], device.get('mac_type'))
        if manufacturer and manufacturer != 'Unknown':
            update_manufacturer(device['mac'], manufacturer)


def _resolve_manufacturer(mac, mac_type):
    """Resolve manufacturer, skipping the external lookup chain entirely
    for locally-administered (randomized) MACs - it can never succeed."""
    if mac_type == 'locally_administered':
        return RANDOMIZED_MAC_MANUFACTURER
    time.sleep(1)  # Rate limit
    return lookup_manufacturer(mac)


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
    """Lookup manufacturer via multiple APIs with fallback."""
    for lookup_fn in (_lookup_macvendors, _lookup_maclookup, _lookup_macvendors_co):
        result = lookup_fn(mac)
        if result:
            return result
    return 'Unknown'


def _lookup_macvendors(mac):
    """Lookup via macvendors.com (plain text response)."""
    try:
        response = http.request(
            'GET', f"https://api.macvendors.com/{mac}"
        )
        if response.status == 200:
            return response.data.decode('utf-8').strip()
    except (urllib3.exceptions.HTTPError, OSError):
        logger.exception("macvendors.com lookup failed")
    return None


def _lookup_maclookup(mac):
    """Lookup via maclookup.app (JSON response)."""
    try:
        response = http.request(
            'GET',
            f"https://api.maclookup.app/v2/macs/{mac}/company/name"
        )
        if response.status == 200:
            company = response.data.decode('utf-8').strip()
            if company not in ('*NO COMPANY*', '*PRIVATE*'):
                return company
    except (urllib3.exceptions.HTTPError, OSError):
        logger.exception("maclookup.app lookup failed")
    return None


def _lookup_macvendors_co(mac):
    """Lookup via macvendors.co (JSON response)."""
    try:
        response = http.request(
            'GET', f"https://macvendors.co/api/{mac}/json"
        )
        if response.status == 200:
            data = json.loads(response.data.decode('utf-8'))
            company = data.get('result', {}).get('company', '')
            if company:
                return company.strip()
    except (urllib3.exceptions.HTTPError, OSError, json.JSONDecodeError):
        logger.exception("macvendors.co lookup failed")
    return None
