# Network Monitor

**Serverless network device monitoring system with event streaming architecture**

Comprehensive network monitoring solution that tracks all devices across VLANs, detects presence changes, and sends notifications. Built with AWS Lambda, DynamoDB, and Vector for event streaming.

## 🏗️ Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  ON-PREMISE (compute-1)                                          │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Data Collector Container                                    │ │
│  │  • Polls OpenWrt APs for wireless clients (ubus HTTP)      │ │
│  │  • Polls MikroTik ARP table for wired devices              │ │
│  │  • Polls DHCP leases for IP/hostname enrichment            │ │
│  │  • Sends events directly to AWS SQS (every 60s)            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Vector (Syslog Gateway)                                     │ │
│  │  • Receives syslog from RouterOS                           │ │
│  │  • Filters and transforms DHCP events                      │ │
│  │  • Sends DHCP events to AWS SQS                            │ │
│  │  • Forwards all syslog to Grafana Loki                     │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Apprise Container (notifications via Cloudflare Tunnel)        │
│                                                                  │
│  OpenWrt APs (lm-ap-1..4, queried via ubus HTTP JSON-RPC)      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  AWS - EVENT BUS                                                 │
│  SQS Queue: device-events.fifo                                  │
│    ↓                                                             │
│  Lambda: event-router → SNS Topics → SQS Queues (fan-out)      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  AWS - EVENT PROCESSORS (Lambda)                                │
│  • event-router: Normalize, route, update device state          │
│  • send-notifications: Apprise integration                      │
│  • enrich-metadata: Manufacturer lookup                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  AWS - DATA & UI                                                 │
│  • DynamoDB: Device state + event history                       │
│  • CloudFront + Lambda function URL: REST API                   │
│  • S3 + CloudFront: Static UI (Bootstrap 5)                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  VISUALIZATION                                                   │
│  • Grafana Cloud: Loki (syslog) + Infinity plugin (API)         │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1a. OpenWrt APs → Data Collector → AWS SQS (wireless client associations)
1b. MikroTik Router → Data Collector → AWS SQS (ARP for wired + DHCP for enrichment)
1c. MikroTik Router → Vector → AWS SQS (DHCP syslog events)
2.  SQS → Lambda (event-router) → SNS Topics
3.  SNS → Multiple SQS Queues (fan-out pattern)
4.  Each Lambda processor consumes from its queue
5.  Lambdas write to DynamoDB
6.  CloudFront proxies /api/* to Lambda function URL
7.  Grafana Cloud queries API via Infinity plugin
```

## 🎯 Features

### Device Discovery
- **Wireless Client Monitoring**: Polls 4 OpenWrt APs via ubus HTTP JSON-RPC for associated clients (primary presence signal)
- **ARP Table Monitoring**: Polls MikroTik ARP table every 60 seconds for wired devices (skips stale entries)
- **DHCP Lease Enrichment**: Uses DHCP leases for IP/hostname enrichment only (not as a presence signal)
- **DHCP Event Tracking**: Captures DHCP assignments/releases via RouterOS syslog (through Vector)
- **Multi-VLAN Support**: Monitors devices across all VLANs (10, 20, 30, 40, 50)
- **New Device Detection**: Event-router Lambda checks DynamoDB to determine if a device is new or existing

### Presence Tracking
- **TTL-Based**: Each device has an `online_until` timestamp (`last_seen + 900s`) refreshed on every activity event
- **Read-Time Evaluation**: Online/offline status computed when queried — no state machine needed
- **Device Auto-Expiry**: Devices automatically deleted after 14 days of inactivity via DynamoDB TTL
- **Historical Data**: 90-day event retention in DynamoDB

### Notifications
- **Apprise Integration**: Supports 80+ notification services (via Cloudflare Tunnel with Zero Trust service token auth)
- **Per-Device Toggle**: `notify` flag per device
- **Throttling**: Prevents notification spam (1 hour cooldown)
- **Event Types**: New device detected, device back online

### Metadata Enrichment
- **Manufacturer Lookup**: Automatic MAC address vendor identification via macvendors.com API
- **VLAN Detection**: Automatic VLAN ID detection from IP address prefix

### API & UI
- **REST API**: CRUD operations for devices (via CloudFront + Lambda function URL with OAC/SigV4)
- **Bootstrap 5 UI**: Dark theme dashboard with inline name editing at `https://network-monitor.mdekort.nl`
- **Signed Cookie Auth**: Cognito login → CloudFront signed cookies (shared with other mdekort.nl sites)

## 📊 Data Model

### DynamoDB Tables

#### `network-monitor-devices` Table
```
Primary Key: mac (String)

Attributes:
- mac: "00:11:22:33:44:55"
- name: "John's iPhone"
- manufacturer: "Apple, Inc."
- hostname: "johns-iphone"
- device_type: null (manually set via API)
- last_ip: "10.204.10.100"
- last_vlan: 10
- notify: false
- first_seen: 1710155697 (unix timestamp)
- last_seen: 1710155697
- online_until: 1710156597 (last_seen + 900s)
- ttl: 1711365297 (last_seen + 14 days, auto-delete)
- metadata: {}

current_state is NOT stored — computed at read time:
  online if online_until > now(), else offline

GSI: vlan-index (last_vlan, last_seen)
```

#### `network-monitor-device-events` Table
```
Primary Key: mac (String), timestamp (Number)

Attributes:
- mac: "00:11:22:33:44:55"
- timestamp: 1710155697000 (milliseconds)
- event_type: "device_activity" | "device_discovered" | "dhcp_assigned" | "dhcp_released"
- ip: "10.204.10.100"
- vlan: 10
- metadata: {}
- ttl: 1717931697 (90 days, auto-delete)
```

#### `network-monitor-notification-throttle` Table
```
Primary Key: throttle_key (String)
Format: "{mac}#{event_type}"

Attributes:
- throttle_key: "00:11:22:33:44:55#device_discovered"
- last_sent: 1710155697
- ttl: 1710159297 (1 hour)
```

#### `network-monitor-deduplication` Table
```
Primary Key: dedup_key (String)
Format: "{mac}#{event_type}#{30s_bucket}"

Attributes:
- dedup_key: "00:11:22:33:44:55#device_activity#57005190"
- ttl: 1710156000 (5 minutes)
```

## 🚀 Deployment

### Prerequisites

- **AWS Account**: With appropriate permissions
- **Terraform**: v1.0+
- **Docker**: For building data collector container
- **MikroTik Router**: With API access enabled
- **OpenWrt APs**: With ubus HTTP JSON-RPC enabled (rpcd + uhttpd-mod-ubus)
- **Vector**: Running on compute-1
- **Apprise**: Running on compute-1 (exposed via Cloudflare Tunnel)

### Infrastructure Setup

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

### On-Premise Setup

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

## 📁 Repository Structure

```
network-monitor/
├── README.md
├── ARCHITECTURE.md
├── TODO.md
├── Makefile                           # Root test runner
├── terraform/
│   ├── main.tf
│   ├── providers.tf                   # AWS + Cloudflare providers
│   ├── remote-state.tf                # Cross-account state refs
│   ├── variables.tf
│   ├── outputs.tf
│   ├── dynamodb.tf                    # DynamoDB tables
│   ├── lambda.tf                      # Lambda functions + function URLs
│   ├── cloudfront.tf                  # CloudFront distribution (UI + API)
│   ├── sns_sqs.tf                     # SNS topics + SQS queues
│   ├── iam.tf                         # IAM roles and policies
│   ├── vector_iam.tf                  # IAM user for Vector
│   ├── s3.tf                          # S3 bucket for UI
│   ├── acm.tf                         # ACM certificate
│   ├── dns.tf                         # Cloudflare DNS record
│   └── ssm.tf                         # SSM parameters (CF Access creds)
├── lambdas/
│   ├── event_router/
│   │   ├── handler.py
│   │   ├── test_handler.py
│   │   └── pyproject.toml
│   ├── send_notifications/
│   │   ├── handler.py
│   │   ├── test_handler.py
│   │   └── pyproject.toml
│   ├── enrich_metadata/
│   │   ├── handler.py
│   │   ├── test_handler.py
│   │   └── pyproject.toml
│   └── api_handler/
│       ├── handler.py
│       ├── test_handler.py
│       └── pyproject.toml
├── data-collector/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── Makefile
│   ├── data_collector/
│   │   ├── __init__.py
│   │   ├── main.py                    # Poll loop + event emission
│   │   ├── mikrotik.py                # RouterOS API client
│   │   ├── openwrt.py                 # OpenWrt ubus HTTP client
│   │   ├── models.py                  # Event schema + VLAN detection
│   │   └── sqs.py                     # SQS batch sender
│   └── tests/
│       ├── test_main.py
│       ├── test_mikrotik.py
│       ├── test_openwrt.py
│       └── test_models.py
├── ui/
│   ├── index.html                     # Bootstrap 5 dark theme dashboard
│   ├── callback.html                  # Cognito auth callback
│   ├── error-pages/
│   │   └── 403.html                   # Login redirect page
│   ├── assets/
│   │   └── js/                        # callback.js
│   ├── favicon.ico
│   └── favicon.png
├── examples/
│   ├── vector.toml                    # Vector config for syslog + SQS
│   └── grafana-dashboards/
│       └── network-overview.json
├── scripts/
│   └── deploy_ui.sh                   # S3 sync for UI deployment
├── docs/
│   ├── api.md
│   ├── event-types.md
│   └── grafana-setup.md
├── .github/
│   └── workflows/
│       ├── terraform.yml              # Terraform plan/apply
│       ├── deploy-lambda.yml          # Reusable Lambda deploy workflow
│       ├── event-router.yml           # Event router trigger
│       ├── send-notifications.yml     # Send notifications trigger
│       ├── enrich-metadata.yml        # Enrich metadata trigger
│       ├── api-handler.yml            # API handler trigger
│       ├── data-collector.yml         # Data collector CI
│       └── deploy-ui.yml             # UI deployment
├── .gitignore
├── LICENSE
└── SECURITY.md
```

## 🔧 Configuration

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

## 📡 API Reference

Base URL: `https://network-monitor.mdekort.nl/api`

Authentication: CloudFront signed cookies (Cognito login required)

### Endpoints

```http
GET    /api/devices                    # List all devices
GET    /api/devices/{mac}              # Get device details
PUT    /api/devices/{mac}              # Update device (name, notify, device_type)
DELETE /api/devices/{mac}              # Delete device
```

### Example

```bash
# List all devices (requires signed cookies)
curl https://network-monitor.mdekort.nl/api/devices

# Update device name
curl -X PUT https://network-monitor.mdekort.nl/api/devices/00:11:22:33:44:55 \
  -H "Content-Type: application/json" \
  -d '{"name": "Living Room Speaker", "notify": true}'
```

## 💰 Cost Estimate

### AWS Free Tier (First 12 Months)
- Lambda: 1M requests free, 400K GB-seconds free
- SNS: 1M publishes free
- SQS: 1M requests free
- DynamoDB: 25 GB storage, 25 WCU, 25 RCU free (forever)

### Expected Monthly Usage (Homelab)
- Lambda invocations: ~50K/month
- SNS/SQS messages: ~50K/month
- DynamoDB storage: <1 GB

### Estimated Cost After Free Tier
- **$3-5/month** for typical homelab usage
- **$0/month** within free tier limits

## 🔒 Security

- **IAM Roles**: Least privilege access for each Lambda function
- **CloudFront Signed Cookies**: Cognito-authenticated access to UI and API
- **Cloudflare Tunnel**: Secure access to on-premise Apprise (Zero Trust service token)
- **SSM Parameter Store**: CF Access credentials stored as SecureString
- **DynamoDB Encryption**: At-rest encryption enabled
- **SQS Encryption**: Server-side encryption enabled
- **MikroTik Credentials**: Stay on-premise (data collector container only)

## 🧪 Testing

```bash
# Run all tests
make test

# Run Lambda unit tests only
make test-lambdas

# Run data collector tests only
make test-collector
```

## 📝 Event Types

### Discovery Events
- `device_discovered`: New MAC address seen (determined by event-router checking DynamoDB)
- `device_activity`: Existing device still present (wireless association or ARP)

### DHCP Events (via Vector syslog)
- `dhcp_assigned`: DHCP lease granted
- `dhcp_released`: DHCP lease released

### Presence Model
- Online/offline is computed from `online_until` at read time — no state change events
- `online_until = last_seen + 900` (15 minutes)

See [docs/event-types.md](docs/event-types.md) for detailed event schemas.

## 🛠️ Troubleshooting

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

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- **Vector**: Syslog pipeline and DHCP event streaming
- **MikroTik RouterOS**: Network infrastructure
- **AWS Lambda**: Serverless compute
- **Apprise**: Multi-channel notifications
- **Grafana Cloud**: Loki for syslog, Infinity plugin for API dashboards

---

**Status**: Active Development

**Version**: 1.0.0

**Last Updated**: 2026-03-25
