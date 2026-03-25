# Deployment Guide

## Prerequisites

- **AWS Account**: With appropriate permissions
- **Terraform**: v1.0+
- **Docker**: For building data collector container
- **MikroTik Router**: With API access enabled
- **OpenWrt APs**: With ubus HTTP JSON-RPC enabled (rpcd + uhttpd-mod-ubus)
- **Vector**: Running on compute-1
- **Apprise**: Running on compute-1 (exposed via Cloudflare Tunnel)

## Infrastructure Setup

```bash
# 1. Clone repository
git clone https://github.com/melvyndekort/network-monitor.git
cd network-monitor

# 2. Deploy AWS infrastructure
cd terraform
terraform init
terraform plan
terraform apply

# 3. Lambda functions are deployed via CI/CD (GitHub Actions)
# Push to main branch triggers deployment per Lambda

# 4. Deploy static UI to S3
./scripts/deploy_ui.sh
```

## On-Premise Setup

```bash
# 1. Build and deploy data collector container
cd data-collector
docker build -t network-monitor-collector .

# 2. Configure Vector
cp examples/vector.toml /etc/vector/vector.toml
# Edit with your AWS credentials and SQS queue URL

# 3. Start services
docker run -d \
  -e MIKROTIK_HOST=10.204.50.1 \
  -e MIKROTIK_USER=api-user \
  -e MIKROTIK_PASSWORD=<password> \
  -e AP_HOSTS=10.204.50.11,10.204.50.12,10.204.50.13,10.204.50.14 \
  -e AP_USER=netmon \
  -e AP_PASSWORD=<ap-password> \
  -e SQS_QUEUE_URL=<queue-url> \
  -e AWS_REGION=eu-west-1 \
  -e AWS_ACCESS_KEY_ID=<key> \
  -e AWS_SECRET_ACCESS_KEY=<secret> \
  network-monitor-collector
```

## Configuration

### Environment Variables

#### Data Collector
```bash
MIKROTIK_HOST=10.204.50.1       # Router IP
MIKROTIK_USER=api-user           # RouterOS API user
MIKROTIK_PASSWORD=<password>     # RouterOS API password
AP_HOSTS=10.204.50.11,10.204.50.12,10.204.50.13,10.204.50.14  # OpenWrt AP IPs
AP_USER=netmon                   # rpcd username on APs
AP_PASSWORD=<ap-password>        # rpcd password on APs
POLL_INTERVAL=60                 # Seconds between polls
SQS_QUEUE_URL=<queue-url>       # FIFO queue URL
AWS_REGION=eu-west-1
AWS_ACCESS_KEY_ID=<key>
AWS_SECRET_ACCESS_KEY=<secret>
```

#### Vector
```bash
SQS_QUEUE_URL=<queue-url>       # Same FIFO queue
AWS_REGION=eu-west-1
AWS_ACCESS_KEY_ID=<key>
AWS_SECRET_ACCESS_KEY=<secret>
LOKI_PASSWORD=<password>         # Grafana Cloud Loki
```

#### Lambda Functions (set via Terraform)
```bash
# event-router
DEVICES_TABLE=network-monitor-devices
EVENTS_TABLE=network-monitor-device-events
DEDUP_TABLE=network-monitor-deduplication
TOPIC_DISCOVERED=arn:aws:sns:...device-discovered
TOPIC_ACTIVITY=arn:aws:sns:...device-activity
TOPIC_NOTIFICATIONS=arn:aws:sns:...notifications

# send-notifications
DEVICES_TABLE=network-monitor-devices
THROTTLE_TABLE=network-monitor-notification-throttle
APPRISE_URL=https://apprise.mdekort.nl

# enrich-metadata
DEVICES_TABLE=network-monitor-devices

# api-handler
DEVICES_TABLE=network-monitor-devices
EVENTS_TABLE=network-monitor-device-events
```

## Testing

```bash
# Run all tests
make test

# Run Lambda unit tests only
make test-lambdas

# Run data collector tests only
make test-collector
```

## Troubleshooting

### Data Collector Not Sending Events
```bash
# Check container logs
docker logs data-collector

# Verify MikroTik connectivity
docker exec data-collector ping 10.204.50.1
```

### Vector Not Forwarding DHCP Events to SQS
```bash
# Check Vector logs
docker logs vector

# Verify AWS credentials
docker exec vector aws sqs list-queues
```

### Lambda Function Errors
```bash
# View CloudWatch logs
aws logs tail /aws/lambda/network-monitor-event-router --follow
```
