"""Presence tracker Lambda - Manage device online/offline state."""
import json
import os
import time
import boto3

# DynamoDB setup
dynamodb = boto3.resource('dynamodb')
devices_table = dynamodb.Table(os.environ['DEVICES_TABLE'])

# SNS setup
sns = boto3.client('sns')
TOPIC_STATE_CHANGED = os.environ['TOPIC_STATE_CHANGED']

OFFLINE_THRESHOLD = 900  # 15 minutes


def handler(event, context):
    """Track device presence and state transitions."""
    for record in event['Records']:
        body = json.loads(record['body'])
        message = json.loads(body['Message'])
        
        mac = message['mac']
        device = get_device(mac)
        
        if not device:
            continue
        
        old_state = device.get('current_state', 'unknown')
        new_state = determine_state(device)
        
        if old_state != new_state:
            update_state(mac, new_state)
            publish_state_change(mac, old_state, new_state)
    
    return {'statusCode': 200}


def get_device(mac):
    """Get device from DynamoDB."""
    response = devices_table.get_item(Key={'mac': mac})
    return response.get('Item')


def determine_state(device):
    """Determine device state based on last_seen."""
    last_seen = device.get('last_seen', 0)
    now = int(time.time())
    return 'online' if now - last_seen < OFFLINE_THRESHOLD else 'offline'


def update_state(mac, state):
    """Update device state."""
    now = int(time.time())
    update_expr = 'SET current_state = :state'
    expr_values = {':state': state}
    
    if state == 'online':
        update_expr += ', last_online = :time'
        expr_values[':time'] = now
    elif state == 'offline':
        update_expr += ', last_offline = :time'
        expr_values[':time'] = now
    
    devices_table.update_item(
        Key={'mac': mac},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values
    )


def publish_state_change(mac, old_state, new_state):
    """Publish state change to SNS."""
    sns.publish(
        TopicArn=TOPIC_STATE_CHANGED,
        Message=json.dumps({
            'mac': mac,
            'old_state': old_state,
            'new_state': new_state,
            'timestamp': int(time.time())
        })
    )
