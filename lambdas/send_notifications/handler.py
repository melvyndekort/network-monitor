"""Notification sender Lambda - Send alerts via Apprise."""
import json
import os
import time
import urllib3
import boto3

# DynamoDB setup
dynamodb = boto3.resource('dynamodb')
devices_table = dynamodb.Table(os.environ['DEVICES_TABLE'])
throttle_table = dynamodb.Table(os.environ['THROTTLE_TABLE'])

# HTTP client
http = urllib3.PoolManager()
APPRISE_URL = os.environ['APPRISE_URL']


def handler(event, context):
    """Send notifications for device events."""
    for record in event['Records']:
        body = json.loads(record['body'])
        message = json.loads(body['Message'])
        
        mac = message['mac']
        device = get_device(mac)
        
        if not device or not device.get('notify'):
            continue
        
        event_type = message.get('event_type') or message.get('new_state')
        throttle_key = f"{mac}#{event_type}"
        
        if check_throttle(throttle_key):
            continue
        
        title, body_text = format_notification(device, message)
        send_apprise(title, body_text)
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
    
    if 'new_state' in message:
        if message['new_state'] == 'offline':
            return ('📴 Device Offline', f"{name} went offline")
        else:
            return ('✅ Device Online', f"{name} is back online")
    else:
        return (
            '🆕 New Device Detected',
            f"MAC: {device['mac']}\n"
            f"IP: {device.get('last_ip', 'Unknown')}\n"
            f"VLAN: {device.get('last_vlan', 'Unknown')}\n"
            f"Manufacturer: {device.get('manufacturer', 'Unknown')}"
        )


def send_apprise(title, body):
    """Send notification via Apprise."""
    try:
        http.request(
            'POST',
            f"{APPRISE_URL}/notify",
            body=json.dumps({'title': title, 'body': body}),
            headers={'Content-Type': 'application/json'}
        )
    except Exception as e:
        print(f"Failed to send notification: {e}")
