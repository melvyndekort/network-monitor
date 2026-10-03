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

  # No TTL: device identity persists once discovered, and is never
  # auto-deleted - only an explicit DELETE /devices/{mac} API call removes
  # a record. Identity is keyed solely on MAC address; hostname/name are
  # human-facing labels only and are never used to look up, merge, or
  # migrate identity between MAC addresses (a prior hostname-index GSI and
  # MAC-rotation feature did this and was removed: it silently deleted
  # device records whenever a MAC appeared to "rotate" by hostname match,
  # which is the opposite of what this system is for - every MAC, including
  # a device's own previous randomized MACs, must be visible and alertable
  # as a distinct entry). Table is tiny (dozens of items) so storage cost
  # is immaterial.

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
