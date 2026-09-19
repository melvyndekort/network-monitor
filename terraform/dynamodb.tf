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
    name = "hostname"
    type = "S"
  }

  # GSI for MAC-rotation identity continuity: given a hostname on a newly
  # seen MAC, look up whether a device with the same hostname already
  # exists under a different (previously assigned, now-rotated) MAC.
  # Sparse by nature - only devices with a hostname attribute are indexed.
  global_secondary_index {
    name = "hostname-index"
    key_schema {
      attribute_name = "hostname"
      key_type       = "HASH"
    }
    projection_type = "ALL"
  }

  # No TTL: device identity persists once discovered. Table is tiny
  # (dozens of items) so storage cost is immaterial - the alternative
  # (auto-expiring and re-alerting a returning device as "unrecognized")
  # is a confirmed false-positive source.

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
