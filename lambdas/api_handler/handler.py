"""API handler Lambda - REST API for device management."""
import json
import os
from decimal import Decimal
import boto3


class DecimalEncoder(json.JSONEncoder):
    """Handle DynamoDB Decimal types."""
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == int(o) else float(o)
        return super().default(o)

# DynamoDB setup (initialized once per container)
dynamodb = boto3.resource('dynamodb')
devices_table = dynamodb.Table(os.environ.get('DEVICES_TABLE', ''))


def handler(event, context):
    """Handle API Gateway requests."""
    method = event['requestContext']['http']['method']
    path = event['requestContext']['http']['path']

    # Strip /api prefix (CloudFront proxies /api/* to API Gateway)
    if path.startswith('/api'):
        path = path[4:] or '/'
    
    if path == '/devices' and method == 'GET':
        return list_devices()
    elif path.startswith('/devices/') and method == 'GET':
        mac = path.split('/')[-1]
        return get_device(mac)
    elif path.startswith('/devices/') and method == 'PUT':
        mac = path.split('/')[-1]
        body = json.loads(event.get('body', '{}'))
        return update_device(mac, body)
    elif path.startswith('/devices/') and method == 'DELETE':
        mac = path.split('/')[-1]
        return delete_device(mac)
    
    return {'statusCode': 404, 'body': json.dumps({'error': 'Not found'}, cls=DecimalEncoder)}


def list_devices():
    """List all devices."""
    response = devices_table.scan()
    return {
        'statusCode': 200,
        'body': json.dumps({'devices': response['Items']}, cls=DecimalEncoder)
    }


def get_device(mac):
    """Get device by MAC."""
    response = devices_table.get_item(Key={'mac': mac})
    device = response.get('Item')
    
    if not device:
        return {'statusCode': 404, 'body': json.dumps({'error': 'Device not found'}, cls=DecimalEncoder)}
    
    return {'statusCode': 200, 'body': json.dumps(device, cls=DecimalEncoder)}


def update_device(mac, updates):
    """Update device."""
    response = devices_table.get_item(Key={'mac': mac})
    if 'Item' not in response:
        return {'statusCode': 404, 'body': json.dumps({'error': 'Device not found'}, cls=DecimalEncoder)}
    
    allowed = {'name', 'notify', 'device_type'}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    
    if filtered:
        update_expr = 'SET ' + ', '.join(f'#{k} = :{k}' for k in filtered.keys())
        expr_names = {f'#{k}': k for k in filtered.keys()}
        expr_values = {f':{k}': v for k, v in filtered.items()}
        
        devices_table.update_item(
            Key={'mac': mac},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values
        )
    
    return {'statusCode': 200, 'body': json.dumps({'status': 'updated'}, cls=DecimalEncoder)}


def delete_device(mac):
    """Delete device."""
    devices_table.delete_item(Key={'mac': mac})
    return {'statusCode': 200, 'body': json.dumps({'status': 'deleted'}, cls=DecimalEncoder)}
