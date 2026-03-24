"""SQS client for sending device events."""
import hashlib
import json
import logging

import boto3

logger = logging.getLogger(__name__)

MAX_BATCH_SIZE = 10


class SQSClient:
    """Sends device events to SQS FIFO queue in batches."""

    def __init__(self, queue_url, region="eu-west-1"):
        self._client = boto3.client("sqs", region_name=region)
        self._queue_url = queue_url

    def send_events(self, events):
        """Send events to SQS in batches of 10."""
        for i in range(0, len(events), MAX_BATCH_SIZE):
            batch = events[i:i + MAX_BATCH_SIZE]
            entries = []
            for j, event in enumerate(batch):
                body = json.dumps(event)
                entries.append({
                    "Id": str(j),
                    "MessageBody": body,
                    "MessageGroupId": event["mac"],
                    "MessageDeduplicationId": hashlib.md5(body.encode()).hexdigest(),
                })
            resp = self._client.send_message_batch(
                QueueUrl=self._queue_url,
                Entries=entries,
            )
            failed = resp.get("Failed", [])
            if failed:
                logger.error("Failed to send %d messages: %s", len(failed), failed)
