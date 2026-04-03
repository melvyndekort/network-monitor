"""Event router Lambda - Normalize and route events."""
import json
import os
import time
from datetime import datetime, timezone
import boto3

# DynamoDB setup (initialized once per container)
dynamodb = boto3.resource('dynamodb')
devices_table = dynamodb.Table(os.environ.get('DEVICES_TABLE', ''))
events_table = dynamodb.Table(os.environ.get('EVENTS_TABLE', ''))
dedup_table = dynamodb.Table(os.environ.get('DEDUP_TABLE', ''))

# SNS setup
sns = boto3.client('sns')
TOPIC_DISCOVERED = os.environ.get('TOPIC_DISCOVERED', '')
TOPIC_NOTIFICATIONS = os.environ.get('TOPIC_NOTIFICATIONS', '')
ONLINE_TTL = 900  # 15 minutes
DEVICE_TTL = 14 * 24 * 60 * 60  # 14 days


def handler(event, _context):
    """Process events from SQS and route to appropriate SNS topics."""
    all_events = []
    for record in event['Records']:
        body = json.loads(record['body'])
        raw_events = body.get('events', [body])
        for raw in raw_events:
            normalized = normalize_event(raw)
            if normalized:
                all_events.append(normalized)

    # Deduplicate
    now_window = int(time.time() // 30)
    dedup_keys = {}
    unique_events = []
    for evt in all_events:
        key = f"{evt['mac']}#{evt['event_type']}#{now_window}"
        if key not in dedup_keys and not check_dedup(key):
            dedup_keys[key] = True
            unique_events.append(evt)

    if not unique_events:
        return {'statusCode': 200}

    # Batch write dedup keys
    batch_write_dedup(list(dedup_keys.keys()))

    # Batch write events
    batch_write_events(unique_events)

    # Route each event (device lookups + SNS publishes)
    now = int(time.time())
    for normalized in unique_events:
        _route_event(normalized, now)

    return {'statusCode': 200}


def _route_event(normalized, now):
    """Route a single event to appropriate SNS topics."""
    device = get_device(normalized['mac'])
    if device:
        was_offline = device.get('online_until', 0) < now
        update_device_last_seen(normalized['mac'], normalized)
        if was_offline:
            normalized['new_state'] = 'online'
            sns.publish(
                TopicArn=TOPIC_NOTIFICATIONS,
                Message=json.dumps(normalized)
            )
    else:
        create_device(normalized)
        sns.publish(
            TopicArn=TOPIC_DISCOVERED,
            Message=json.dumps(normalized)
        )
        sns.publish(
            TopicArn=TOPIC_NOTIFICATIONS,
            Message=json.dumps(normalized)
        )


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
        'notify': False,
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
        UpdateExpression=(
            'SET last_seen = :ls, last_ip = :ip, last_vlan = :vlan,'
            ' online_until = :ou, #t = :ttl'
        ),
        ExpressionAttributeNames={'#t': 'ttl'},
        ExpressionAttributeValues={
            ':ls': now,
            ':ip': event.get('ip'),
            ':vlan': event.get('vlan'),
            ':ou': now + ONLINE_TTL,
            ':ttl': now + DEVICE_TTL
        }
    )


def batch_write_events(events):
    """Batch write events to DynamoDB."""
    ttl = int(time.time()) + (90 * 24 * 60 * 60)
    with events_table.batch_writer() as batch:
        for event in events:
            ts = event['timestamp'].replace('Z', '+00:00')
            batch.put_item(Item={
                'mac': event['mac'],
                'timestamp': int(
                    datetime.fromisoformat(ts)
                    .replace(tzinfo=timezone.utc).timestamp() * 1000
                ),
                'event_type': event['event_type'],
                'ip': event.get('ip'),
                'vlan': event.get('vlan'),
                'metadata': event.get('metadata', {}),
                'ttl': ttl
            })


def batch_write_dedup(keys):
    """Batch write dedup keys to DynamoDB."""
    ttl = int(time.time()) + 300
    with dedup_table.batch_writer() as batch:
        for key in keys:
            batch.put_item(Item={'dedup_key': key, 'ttl': ttl})


def check_dedup(key):
    """Check if event is duplicate."""
    response = dedup_table.get_item(Key={'dedup_key': key})
    return 'Item' in response
