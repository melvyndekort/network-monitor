"""Notification sender Lambda - Send alerts via Apprise."""
import json
import logging
import os
import time
import urllib3
import boto3

logger = logging.getLogger(__name__)

# DynamoDB setup (initialized once per container)
dynamodb = boto3.resource('dynamodb')
devices_table = dynamodb.Table(os.environ.get('DEVICES_TABLE', ''))
throttle_table = dynamodb.Table(os.environ.get('THROTTLE_TABLE', ''))

# HTTP client
http = urllib3.PoolManager()
APPRISE_URL = os.environ.get('APPRISE_URL', '')

# CF Access credentials (fetched once per container)
ssm = boto3.client('ssm')
CF_ACCESS_CLIENT_ID = ssm.get_parameter(
    Name='/network-monitor/cf-access-client-id',
    WithDecryption=True
)['Parameter']['Value']
CF_ACCESS_CLIENT_SECRET = ssm.get_parameter(
    Name='/network-monitor/cf-access-client-secret',
    WithDecryption=True
)['Parameter']['Value']


def handler(event, _context):
    """Send notifications for device events."""
    for record in event['Records']:
        body = json.loads(record['body'])
        message = json.loads(body['Message'])

        mac = message['mac']
        device = get_device(mac)

        if not device:
            continue

        # Discovery alerts bypass the per-device notify flag - a device that
        # was never seen before can't have opted in yet. Every other
        # transition (back-online, MAC-rotation) respects it.
        is_discovery = message.get('new_state') == 'discovered'
        if not is_discovery and not device.get('notify'):
            continue

        reason = message.get('new_state', message.get('event_type'))
        throttle_key = f"{mac}#{reason}"

        if check_throttle(throttle_key):
            continue

        title, body_text = format_notification(device, message)
        if send_apprise(title, body_text):
            set_throttle(throttle_key, 3600)

    return {'statusCode': 200}


def get_device(mac):
    """Get device from DynamoDB."""
    response = devices_table.get_item(Key={'mac': mac})
    return response.get('Item')


def check_throttle(key):
    """Check if notification is throttled."""
    response = throttle_table.get_item(Key={'throttle_key': key})
    return 'Item' in response


def set_throttle(key, duration):
    """Set notification throttle."""
    ttl = int(time.time()) + duration
    throttle_table.put_item(Item={
        'throttle_key': key,
        'last_sent': int(time.time()),
        'ttl': ttl
    })


def format_notification(device, message):
    """Format notification title and body."""
    name = device.get('name') or device['mac']
    new_state = message.get('new_state')

    if new_state == 'online':
        return ('✅ Device Online', f"{name} is back online")

    if new_state == 'rotated':
        previous_mac = message.get('previous_mac', 'unknown')
        return (
            'ℹ️ Device Re-identified',
            f"{name} reconnected with a new MAC ({device['mac']}, was {previous_mac})"
        )

    if new_state == 'discovered':
        # A locally-administered (randomized) MAC with no matching known
        # hostname is the actual evasion pattern this system exists to
        # catch - flag it distinctly from an ordinary new vendor-MAC device.
        if message.get('mac_type') == 'locally_administered':
            title = '🚨 Unrecognized Device (Randomized MAC)'
        else:
            title = '🆕 New Device Detected'
        return (
            title,
            f"MAC: {device['mac']}\n"
            f"IP: {device.get('last_ip', 'Unknown')}\n"
            f"VLAN: {device.get('last_vlan', 'Unknown')}\n"
            f"Manufacturer: {device.get('manufacturer', 'Unknown')}"
        )

    return ('📴 Device Offline', f"{name} went offline")


def send_apprise(title, body):
    """Send notification via Apprise. Returns True on a successful request."""
    try:
        http.request(
            'POST',
            f"{APPRISE_URL}/notify/apprise",
            body=json.dumps({
                'title': title, 'body': body, 'tag': 'homelab'
            }),
            headers={
                'Content-Type': 'application/json',
                'CF-Access-Client-Id': CF_ACCESS_CLIENT_ID,
                'CF-Access-Client-Secret': CF_ACCESS_CLIENT_SECRET,
            }
        )
        return True
    except (urllib3.exceptions.HTTPError, OSError):
        logger.exception("Failed to send notification")
        return False
