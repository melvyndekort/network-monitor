# SQS Queue for Event Streaming (Vector -> event_router)
#
# The former SNS-topic -> per-consumer-SQS-queue fan-out for the notifier and
# metadata-enricher Lambdas is gone: those two queues carried a combined
# ~4.6k real messages/month but ~460k SQS "empty receive" polls/month (the
# Lambda SQS poller runs continuously regardless of traffic), which is what
# pushed the account over the Free Tier SQS-requests limit. event_router now
# invokes both Lambdas directly (lambda:Invoke, InvocationType=Event) - see
# lambda.tf and iam.tf.

# Primary SQS Queue - Entry point from Vector
resource "aws_sqs_queue" "device_events" {
  name                        = "network-monitor-device-events.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  message_retention_seconds   = 1209600 # 14 days
  visibility_timeout_seconds  = 60

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.device_events_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "network-monitor-device-events"
  }
}

resource "aws_sqs_queue" "device_events_dlq" {
  name                      = "network-monitor-device-events-dlq.fifo"
  fifo_queue                = true
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Name = "network-monitor-device-events-dlq"
  }
}
