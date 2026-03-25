"""Event router Lambda - Normalize and route events."""
import json
import os
import time
from datetime import datetime
import boto3

# DynamoDB setup (initialized once per container)
dynamodb = boto3.resource('dynamodb')
devices_table = dynamodb.Table(os.environ.get('DEVICES_TABLE', ''))
events_table = dynamodb.Table(os.environ.get('EVENTS_TABLE', ''))
dedup_table = dynamodb.Table(os.environ.get('DEDUP_TABLE', ''))

# SNS setup
sns = boto3.client('sns')
TOPIC_DISCOVERED = os.environ.get('TOPIC_DISCOVERED', '')
TOPIC_ACTIVITY = os.environ.get('TOPIC_ACTIVITY', '')
ONLINE_TTL = 900  # 15 minutes
DEVICE_TTL = 14 * 24 * 60 * 60  # 14 days


def handler(event, context):
    """Process events from SQS and route to appropriate SNS topics."""
    for record in event['Records']:
        body = json.loads(record['body'])

        # Support batch messages ({"events": [...]}) and single events
        raw_events = body.get('events', [body])

        for raw in raw_events:
            normalized = normalize_event(raw)
            if not normalized:
                continue
            
            # Deduplication
            dedup_key = f"{normalized['mac']}#{normalized['event_type']}#{int(time.time() // 30)}"
            if check_dedup(dedup_key):
                continue
            set_dedup(dedup_key)
            
            # Store event
            put_event(normalized)
            
            # Update device
            device = get_device(normalized['mac'])
            if device:
                update_device_last_seen(normalized['mac'], normalized)
                topic = TOPIC_ACTIVITY
            else:
                create_device(normalized)
                topic = TOPIC_DISCOVERED
            
            # Route to SNS
            sns.publish(TopicArn=topic, Message=json.dumps(normalized))
    
    return {'statusCode': 200}


def normalize_event(body):
    """Normalize event from Vector."""
    try:
        return {
            'timestamp': body['timestamp'],
            'source': body['source'],
            'event_type': body['event_type'],
            'mac': body['mac'].upper(),
            'ip': body.get('ip'),
            'hostname': body.get('hostname'),
            'vlan': body.get('vlan'),
            'metadata': body.get('metadata', {})
        }
    except (KeyError, ValueError):
        return None


def get_device(mac):
    """Get device from DynamoDB."""
    response = devices_table.get_item(Key={'mac': mac})
    return response.get('Item')


def create_device(event):
    """Create new device."""
    now = int(time.time())
    devices_table.put_item(Item={
        'mac': event['mac'],
        'name': event.get('hostname'),
        'manufacturer': None,
        'hostname': event.get('hostname'),
        'device_type': None,
        'last_ip': event.get('ip'),
        'last_vlan': event.get('vlan'),
        'notify': True,
        'first_seen': now,
        'last_seen': now,
        'online_until': now + ONLINE_TTL,
        'ttl': now + DEVICE_TTL,
        'metadata': {}
    })


def update_device_last_seen(mac, event):
    """Update device last_seen and online_until."""
    now = int(time.time())
    devices_table.update_item(
        Key={'mac': mac},
        UpdateExpression='SET last_seen = :ls, last_ip = :ip, last_vlan = :vlan, online_until = :ou, #t = :ttl',
        ExpressionAttributeNames={'#t': 'ttl'},
        ExpressionAttributeValues={
            ':ls': now,
            ':ip': event.get('ip'),
            ':vlan': event.get('vlan'),
            ':ou': now + ONLINE_TTL,
            ':ttl': now + DEVICE_TTL
        }
    )


def put_event(event):
    """Store event in DynamoDB."""
    ttl = int(time.time()) + (90 * 24 * 60 * 60)
    events_table.put_item(Item={
        'mac': event['mac'],
        'timestamp': int(datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00')).timestamp() * 1000),
        'event_type': event['event_type'],
        'ip': event.get('ip'),
        'vlan': event.get('vlan'),
        'metadata': event.get('metadata', {}),
        'ttl': ttl
    })


def check_dedup(key):
    """Check if event is duplicate."""
    response = dedup_table.get_item(Key={'dedup_key': key})
    return 'Item' in response


def set_dedup(key):
    """Mark event as processed."""
    ttl = int(time.time()) + 300
    dedup_table.put_item(Item={'dedup_key': key, 'ttl': ttl})
