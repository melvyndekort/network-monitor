# DynamoDB Tables for Network Monitor

# Devices Table - Current device state
resource "aws_dynamodb_table" "devices" {
  name         = "network-monitor-devices"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "mac"

  attribute {
    name = "mac"
    type = "S"
  }

  attribute {
    name = "last_seen"
    type = "N"
  }

  attribute {
    name = "last_vlan"
    type = "N"
  }

  # GSI for querying by VLAN
  global_secondary_index {
    name            = "vlan-index"
    hash_key        = "last_vlan"
    range_key       = "last_seen"
    projection_type = "ALL"
  }

  ttl {
    enabled        = false
    attribute_name = ""
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "network-monitor-devices"
  }
}

# Device Events Table - Event history with TTL
resource "aws_dynamodb_table" "device_events" {
  name         = "network-monitor-device-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "mac"
  range_key    = "timestamp"

  attribute {
    name = "mac"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }

  ttl {
    enabled        = true
    attribute_name = "ttl"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "network-monitor-device-events"
  }
}

# Notification Throttle Table - Prevent notification spam
resource "aws_dynamodb_table" "notification_throttle" {
  name         = "network-monitor-notification-throttle"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "throttle_key"

  attribute {
    name = "throttle_key"
    type = "S"
  }

  ttl {
    enabled        = true
    attribute_name = "ttl"
  }

  point_in_time_recovery {
    enabled = false
  }

  tags = {
    Name = "network-monitor-notification-throttle"
  }
}

# Deduplication Table - Prevent duplicate event processing
resource "aws_dynamodb_table" "deduplication" {
  name         = "network-monitor-deduplication"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "dedup_key"

  attribute {
    name = "dedup_key"
    type = "S"
  }

  ttl {
    enabled        = true
    attribute_name = "ttl"
  }

  point_in_time_recovery {
    enabled = false
  }

  tags = {
    Name = "network-monitor-deduplication"
  }
}
