output "sqs_queue_url" {
  description = "SQS queue URL for Vector to send events"
  value       = aws_sqs_queue.device_events.url
}

output "api_gateway_url" {
  description = "API Gateway URL for REST API"
  value       = aws_apigatewayv2_api.network_monitor.api_endpoint
}

output "dynamodb_tables" {
  description = "DynamoDB table names"
  value = {
    devices               = aws_dynamodb_table.devices.name
    device_events         = aws_dynamodb_table.device_events.name
    notification_throttle = aws_dynamodb_table.notification_throttle.name
    deduplication         = aws_dynamodb_table.deduplication.name
  }
}

output "vector_aws_access_key_id" {
  description = "AWS access key ID for Vector IAM user"
  value       = aws_iam_access_key.vector.id
  sensitive   = true
}

output "vector_aws_secret" {
  description = "AWS secret access key for Vector IAM user"
  value       = aws_iam_access_key.vector.secret
  sensitive   = true
}

output "ui_website_url" {
  description = "Network Monitor UI URL"
  value       = "https://${aws_acm_certificate.ui.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = aws_cloudfront_distribution.ui.id
}
