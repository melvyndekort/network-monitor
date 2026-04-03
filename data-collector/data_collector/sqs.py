"""SQS client for sending device events."""
import hashlib
import json
import logging

import boto3

logger = logging.getLogger(__name__)


def create_sqs_client(queue_url, region="eu-west-1"):
    """Create an SQS send function bound to a specific queue."""
    client = boto3.client("sqs", region_name=region)

    def send_events(events):
        """Send all events as a single batched SQS message."""
        if not events:
            return
        body = json.dumps({"events": events})
        dedup_id = hashlib.md5(body.encode()).hexdigest()
        client.send_message(
            QueueUrl=queue_url,
            MessageBody=body,
            MessageGroupId="data-collector",
            MessageDeduplicationId=dedup_id,
        )

    return send_events
