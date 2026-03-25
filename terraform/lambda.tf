# Lambda Functions

# Event Router Lambda
resource "aws_lambda_function" "event_router" {
  filename      = "event_router.zip"
  function_name = "network-monitor-event-router"
  role          = aws_iam_role.event_router.arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      DEVICES_TABLE    = aws_dynamodb_table.devices.name
      EVENTS_TABLE     = aws_dynamodb_table.device_events.name
      DEDUP_TABLE      = aws_dynamodb_table.deduplication.name
      TOPIC_DISCOVERED   = aws_sns_topic.device_discovered.arn
      TOPIC_ACTIVITY     = aws_sns_topic.device_activity.arn
      TOPIC_NOTIFICATIONS = aws_sns_topic.notifications.arn
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_lambda_event_source_mapping" "event_router" {
  event_source_arn = aws_sqs_queue.device_events.arn
  function_name    = aws_lambda_function.event_router.arn
  batch_size       = 10
}

# Send Notifications Lambda
resource "aws_lambda_function" "send_notifications" {
  filename      = "send_notifications.zip"
  function_name = "network-monitor-send-notifications"
  role          = aws_iam_role.send_notifications.arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      DEVICES_TABLE  = aws_dynamodb_table.devices.name
      THROTTLE_TABLE = aws_dynamodb_table.notification_throttle.name
      APPRISE_URL    = var.apprise_url
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_lambda_event_source_mapping" "send_notifications" {
  event_source_arn = aws_sqs_queue.notifier.arn
  function_name    = aws_lambda_function.send_notifications.arn
  batch_size       = 5
}

# Enrich Metadata Lambda
resource "aws_lambda_function" "enrich_metadata" {
  filename      = "enrich_metadata.zip"
  function_name = "network-monitor-enrich-metadata"
  role          = aws_iam_role.enrich_metadata.arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      DEVICES_TABLE = aws_dynamodb_table.devices.name
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_lambda_event_source_mapping" "enrich_metadata" {
  event_source_arn = aws_sqs_queue.metadata_enricher.arn
  function_name    = aws_lambda_function.enrich_metadata.arn
  batch_size       = 2
}

# API Handler Lambda
resource "aws_lambda_function" "api_handler" {
  filename      = "api_handler.zip"
  function_name = "network-monitor-api-handler"
  role          = aws_iam_role.api_handler.arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 512

  environment {
    variables = {
      DEVICES_TABLE = aws_dynamodb_table.devices.name
      EVENTS_TABLE  = aws_dynamodb_table.device_events.name
    }
  }
}

resource "aws_lambda_function_url" "api_handler" {
  function_name      = aws_lambda_function.api_handler.function_name
  authorization_type = "AWS_IAM"
}

resource "aws_lambda_permission" "cloudfront_oac" {
  statement_id  = "AllowCloudFrontOAC"
  action        = "lambda:InvokeFunctionUrl"
  function_name = aws_lambda_function.api_handler.function_name
  principal     = "cloudfront.amazonaws.com"
  source_arn    = aws_cloudfront_distribution.ui.arn
}

resource "aws_lambda_permission" "cloudfront_oac_invoke" {
  statement_id  = "AllowCloudFrontOACInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_handler.function_name
  principal     = "cloudfront.amazonaws.com"
  source_arn    = aws_cloudfront_distribution.ui.arn
}
