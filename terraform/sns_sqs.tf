# SNS Topics and SQS Queues for Event Streaming

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

# SNS Topics for event routing
resource "aws_sns_topic" "device_discovered" {
  name = "network-monitor-device-discovered"

  tags = {
    Name = "network-monitor-device-discovered"
  }
}

resource "aws_sns_topic" "device_activity" {
  name = "network-monitor-device-activity"

  tags = {
    Name = "network-monitor-device-activity"
  }
}

resource "aws_sns_topic" "device_state_changed" {
  name = "network-monitor-device-state-changed"

  tags = {
    Name = "network-monitor-device-state-changed"
  }
}

# SQS Queues for Lambda processors (fan-out from SNS)
resource "aws_sqs_queue" "presence_tracker" {
  name                       = "network-monitor-presence-tracker"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 345600 # 4 days

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.presence_tracker_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "network-monitor-presence-tracker"
  }
}

resource "aws_sqs_queue" "presence_tracker_dlq" {
  name                      = "network-monitor-presence-tracker-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Name = "network-monitor-presence-tracker-dlq"
  }
}

resource "aws_sqs_queue" "notifier" {
  name                       = "network-monitor-notifier"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 345600 # 4 days

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notifier_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "network-monitor-notifier"
  }
}

resource "aws_sqs_queue" "notifier_dlq" {
  name                      = "network-monitor-notifier-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Name = "network-monitor-notifier-dlq"
  }
}

resource "aws_sqs_queue" "metadata_enricher" {
  name                       = "network-monitor-metadata-enricher"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 345600 # 4 days

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.metadata_enricher_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "network-monitor-metadata-enricher"
  }
}

resource "aws_sqs_queue" "metadata_enricher_dlq" {
  name                      = "network-monitor-metadata-enricher-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Name = "network-monitor-metadata-enricher-dlq"
  }
}

# SNS to SQS subscriptions
resource "aws_sns_topic_subscription" "device_activity_to_presence" {
  topic_arn = aws_sns_topic.device_activity.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.presence_tracker.arn
}

resource "aws_sns_topic_subscription" "device_discovered_to_presence" {
  topic_arn = aws_sns_topic.device_discovered.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.presence_tracker.arn
}

resource "aws_sns_topic_subscription" "device_discovered_to_notifier" {
  topic_arn = aws_sns_topic.device_discovered.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.notifier.arn
}

resource "aws_sns_topic_subscription" "device_state_changed_to_notifier" {
  topic_arn = aws_sns_topic.device_state_changed.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.notifier.arn
}

resource "aws_sns_topic_subscription" "device_discovered_to_enricher" {
  topic_arn = aws_sns_topic.device_discovered.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.metadata_enricher.arn
}

# SQS Queue Policies to allow SNS to send messages
resource "aws_sqs_queue_policy" "presence_tracker" {
  queue_url = aws_sqs_queue.presence_tracker.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "sns.amazonaws.com"
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.presence_tracker.arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = [
            aws_sns_topic.device_activity.arn,
            aws_sns_topic.device_discovered.arn
          ]
        }
      }
    }]
  })
}

resource "aws_sqs_queue_policy" "notifier" {
  queue_url = aws_sqs_queue.notifier.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "sns.amazonaws.com"
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.notifier.arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = [
            aws_sns_topic.device_discovered.arn,
            aws_sns_topic.device_state_changed.arn
          ]
        }
      }
    }]
  })
}

resource "aws_sqs_queue_policy" "metadata_enricher" {
  queue_url = aws_sqs_queue.metadata_enricher.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "sns.amazonaws.com"
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.metadata_enricher.arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_sns_topic.device_discovered.arn
        }
      }
    }]
  })
}
