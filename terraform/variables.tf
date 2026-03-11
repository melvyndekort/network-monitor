variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "eu-west-1"
}

variable "account_id" {
  description = "AWS Account ID for network-monitor"
  type        = string
}

variable "apprise_url" {
  description = "URL for Apprise notification service (via Cloudflare Tunnel)"
  type        = string
  sensitive   = true
}

variable "mikrotik_host" {
  description = "MikroTik router hostname/IP (for documentation only, actual access is on-premise)"
  type        = string
  default     = "10.204.10.1"
}
