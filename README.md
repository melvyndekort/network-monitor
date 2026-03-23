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
│  │  • Polls MikroTik ARP table (every 30s)                    │ │
│  │  • Polls DHCP leases                                        │ │
│  │  • Polls wireless registrations                            │ │
│  │  • Outputs JSON events to stdout                           │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Vector (Event Gateway)                                      │ │
│  │  • Receives syslog from RouterOS                           │ │
│  │  • Receives events from data collector                     │ │
│  │  • Normalizes and deduplicates events                      │ │
│  │  • Sends to AWS SQS                                        │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Apprise Container (notifications)                              │
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
│  • event-router: Normalize & route events                       │
│  • send-notifications: Apprise integration                      │
│  • enrich-metadata: Manufacturer lookup                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  AWS - DATA & API                                                │
│  • DynamoDB: Device state + event history                       │
│  • API Gateway + Lambda: REST API                               │
│  • S3: Static UI (HTMX)                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  VISUALIZATION                                                   │
│  • Grafana Cloud: Dashboards and analytics                      │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. MikroTik Router → Data Collector → Vector → AWS SQS
2. SQS → Lambda (event-router) → SNS Topics
3. SNS → Multiple SQS Queues (fan-out pattern)
4. Each Lambda processor consumes from its queue
5. Lambdas write to DynamoDB
6. API Gateway exposes REST API
7. Grafana Cloud queries DynamoDB for dashboards
```

## 🎯 Features

### Device Discovery
- **ARP Table Monitoring**: Polls MikroTik ARP table every 30 seconds
- **DHCP Lease Discovery**: Detects devices with active DHCP leases, even if they disconnect between ARP polls
- **DHCP Event Tracking**: Captures DHCP assignments/releases via syslog
- **Wireless Monitoring**: Tracks WiFi client associations/disassociations
- **Multi-VLAN Support**: Monitors devices across all VLANs (Data, IoT, Guest, Management, VPN)
- **Static IP Detection**: Discovers devices with static IPs through ARP polling

### Presence Tracking
- **TTL-Based**: Each device has an `online_until` timestamp refreshed on every activity event
- **Read-Time Evaluation**: Online/offline status computed when queried — no state machine needed
- **Real-time Updates**: WebSocket support for live device status
- **Historical Data**: 90-day event retention in DynamoDB

### Notifications
- **Apprise Integration**: Supports 80+ notification services
- **Configurable Rules**: Per-device notification settings
- **Throttling**: Prevents notification spam (1 hour cooldown)
- **Event Types**: New device, device offline, device online, anomalies

### Metadata Enrichment
- **Manufacturer Lookup**: Automatic MAC address vendor identification
- **Hostname Resolution**: Reverse DNS lookups
- **Device Classification**: Automatic device type detection
- **VLAN Tracking**: Records which VLAN each device uses

### API & UI
- **REST API**: Full CRUD operations for devices
- **WebSocket**: Real-time device updates
- **HTMX UI**: Lightweight web interface for device management
- **Grafana Dashboards**: Time-series analytics and visualizations

## 📊 Data Model

### DynamoDB Tables

#### `devices` Table
```
Primary Key: mac (String)

Attributes:
- mac: "00:11:22:33:44:55"
- name: "John's iPhone"
- manufacturer: "Apple, Inc."
- hostname: "johns-iphone"
- device_type: "phone"
- last_ip: "10.204.10.100"
- last_vlan: 10
- current_state: "online" | "offline" (computed from online_until at read time)
- notify: true
- first_seen: 1710155697 (unix timestamp)
- last_seen: 1710155697
- online_until: 1710156597 (last_seen + 900s)
- metadata: { ... }

GSI: vlan-index (last_vlan, last_seen)
```

#### `device_events` Table
```
Primary Key: mac (String), timestamp (Number)

Attributes:
- mac: "00:11:22:33:44:55"
- timestamp: 1710155697000
- event_type: "arp_discovered" | "dhcp_assigned" | "state_changed"
- ip: "10.204.10.100"
- vlan: 10
- metadata: { ... }
- ttl: 1717931697 (90 days, auto-delete)
```

#### `notification_throttle` Table
```
Primary Key: throttle_key (String)
Format: "{mac}#{event_type}"

Attributes:
- throttle_key: "00:11:22:33:44:55#new_device"
- last_sent: 1710155697
- ttl: 1710159297 (1 hour)
```

#### `deduplication` Table
```
Primary Key: dedup_key (String)
Format: "{mac}#{event_type}#{rounded_timestamp}"

Attributes:
- dedup_key: "00:11:22:33:44:55#arp_discovered#1710155700"
- ttl: 1710156000 (5 minutes)
```

## 🚀 Deployment

### Prerequisites

- **AWS Account**: With appropriate permissions
- **Terraform**: v1.0+
- **Docker**: For building Lambda containers
- **MikroTik Router**: With API access
- **Vector**: Running on compute-1
- **Apprise**: Running on compute-1 (exposed via Cloudflare Tunnel)

### Infrastructure Setup

```bash
# 1. Clone repository
git clone https://github.com/melvyndekort/network-monitor.git
cd network-monitor

# 2. Configure Terraform backend
cd terraform
terraform init

# 3. Set variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# 4. Deploy AWS infrastructure
terraform plan
terraform apply

# 5. Build and deploy Lambda functions
cd ../lambdas
./scripts/deploy_lambdas.sh

# 6. Deploy static UI to S3
cd ../ui
aws s3 sync . s3://network-monitor-ui-bucket/
```

### On-Premise Setup

```bash
# 1. Deploy data collector container
cd data-collector
docker build -t network-monitor-collector .

# 2. Configure Vector
cp examples/vector.toml /etc/vector/vector.toml
# Edit with your AWS credentials and SQS queue URL

# 3. Start services
docker-compose up -d
```

## 📁 Repository Structure

```
network-monitor/
├── README.md                          # This file
├── ARCHITECTURE.md                    # Detailed architecture documentation
├── terraform/                         # AWS infrastructure
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── dynamodb.tf                    # DynamoDB tables
│   ├── lambda.tf                      # Lambda functions
│   ├── api_gateway.tf                 # API Gateway
│   ├── sns_sqs.tf                     # SNS topics + SQS queues
│   ├── iam.tf                         # IAM roles and policies
│   └── s3.tf                          # S3 bucket for UI
├── lambdas/                           # Lambda function code
│   ├── shared/                        # Shared libraries
│   │   ├── dynamodb.py
│   │   ├── sns.py
│   │   └── models.py
│   ├── event_router/
│   │   ├── handler.py
│   │   └── requirements.txt
│   ├── send_notifications/
│   │   ├── handler.py
│   │   └── requirements.txt
│   ├── enrich_metadata/
│   │   ├── handler.py
│   │   └── requirements.txt
│   └── api_handler/
│       ├── handler.py
│       └── requirements.txt
├── data-collector/                    # On-premise data collector
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── collector/
│   │   ├── main.py
│   │   ├── mikrotik.py
│   │   └── models.py
│   └── config.yaml
├── ui/                                # Static web UI
│   ├── index.html
│   ├── devices.html
│   └── styles.css
├── examples/                          # Example configurations
│   ├── vector.toml
│   ├── docker-compose.yml
│   └── grafana-dashboards/
├── scripts/                           # Deployment scripts
│   ├── deploy_lambdas.sh
│   └── package_lambdas.sh
├── docs/                              # Additional documentation
│   ├── api.md                         # API documentation
│   ├── event-types.md                 # Event type reference
│   └── grafana-setup.md               # Grafana dashboard setup
├── .github/
│   └── workflows/
│       ├── terraform.yml              # Terraform CI/CD
│       └── lambda-deploy.yml          # Lambda deployment
├── .gitignore
├── LICENSE
└── SECURITY.md
```

## 🔧 Configuration

### Environment Variables

#### Data Collector
```bash
MIKROTIK_HOST=10.204.10.1
MIKROTIK_USER=api-user
MIKROTIK_PASSWORD=secret
POLL_INTERVAL=30  # seconds
```

#### Vector
```bash
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION=eu-west-1
SQS_QUEUE_URL=https://sqs.eu-west-1.amazonaws.com/account/device-events.fifo
```

#### Lambda Functions
```bash
DYNAMODB_DEVICES_TABLE=devices
DYNAMODB_EVENTS_TABLE=device_events
APPRISE_URL=https://apprise.internal.mdekort.nl
SNS_TOPIC_ARN=arn:aws:sns:eu-west-1:account:device-events
```

## 📡 API Reference

### Devices

```http
GET    /api/devices                    # List all devices
GET    /api/devices/{mac}              # Get device details
PUT    /api/devices/{mac}              # Update device
DELETE /api/devices/{mac}              # Delete device
GET    /api/devices/{mac}/history      # Get device event history
POST   /api/devices/{mac}/ping         # Trigger presence check
```

### Stats

```http
GET    /api/stats                      # Network-wide statistics
GET    /api/stats/vlan/{vlan_id}       # VLAN-specific stats
```

### WebSocket

```
WS     /api/ws/devices                 # Live device updates
```

### Example Request

```bash
# Get all online devices
curl https://api.network-monitor.example.com/api/devices?state=online

# Update device name
curl -X PUT https://api.network-monitor.example.com/api/devices/00:11:22:33:44:55 \
  -H "Content-Type: application/json" \
  -d '{"name": "Johns iPhone", "notify": true}'
```

## 📈 Grafana Dashboards

### Network Overview Dashboard
- Total devices by VLAN
- Online vs offline devices
- New devices today
- Device presence timeline

### Device Details Dashboard
- Individual device presence history
- Event timeline
- Connection history (IPs, VLANs)
- Signal strength (for wireless devices)

### VLAN Activity Dashboard
- Devices per VLAN
- Activity heatmap
- Top active devices

See [docs/grafana-setup.md](docs/grafana-setup.md) for dashboard JSON and setup instructions.

## 💰 Cost Estimate

### AWS Free Tier (First 12 Months)
- Lambda: 1M requests free, 400K GB-seconds free
- API Gateway: 1M requests free
- SNS: 1M publishes free
- SQS: 1M requests free
- DynamoDB: 25 GB storage, 25 WCU, 25 RCU free (forever)

### Expected Monthly Usage (Homelab)
- Lambda invocations: ~500K/month
- API Gateway requests: ~10K/month
- SNS/SQS messages: ~500K/month
- DynamoDB storage: <1 GB

### Estimated Cost After Free Tier
- **$3-5/month** for typical homelab usage
- **$0/month** within free tier limits

## 🔒 Security

- **IAM Roles**: Least privilege access for Lambda functions
- **VPC**: Optional VPC deployment for Lambda functions
- **Secrets Manager**: Stores MikroTik credentials
- **API Gateway**: API key authentication
- **Cloudflare Tunnel**: Secure access to on-premise Apprise
- **DynamoDB Encryption**: At-rest encryption enabled
- **SQS Encryption**: Server-side encryption enabled

## 🧪 Testing

```bash
# Run all tests
make test

# Run Lambda unit tests only
make test-lambdas

# Run data collector tests only
make test-collector

# Test data collector locally
cd data-collector
docker build -t collector-test .
docker run --rm -e MIKROTIK_HOST=10.204.10.1 collector-test
```

## 📝 Event Types

### Discovery Events
- `device_discovered`: New MAC address seen
- `device_activity`: Existing device still present

### DHCP Events
- `dhcp_assigned`: DHCP lease granted
- `dhcp_released`: DHCP lease released

### Wireless Events
- `wireless_connected`: Client associated to AP
- `wireless_disconnected`: Client disassociated

### State Events
- `state_changed`: *(removed — online/offline is derived from `online_until` at read time)*

See [docs/event-types.md](docs/event-types.md) for detailed event schemas.

## 🛠️ Troubleshooting

### Data Collector Not Sending Events
```bash
# Check container logs
docker logs data-collector

# Verify MikroTik connectivity
docker exec data-collector ping 10.204.10.1

# Test MikroTik API
docker exec data-collector python -c "from librouteros import connect; api = connect(host='10.204.10.1', username='user', password='pass'); print(list(api.path('/ip/arp')))"
```

### Vector Not Forwarding to SQS
```bash
# Check Vector logs
docker logs vector

# Verify AWS credentials
docker exec vector aws sqs list-queues

# Test SQS connectivity
docker exec vector aws sqs send-message --queue-url <url> --message-body "test"
```

### Lambda Function Errors
```bash
# View CloudWatch logs
aws logs tail /aws/lambda/event-router --follow

# Check Lambda metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=event-router \
  --start-time 2026-03-11T00:00:00Z \
  --end-time 2026-03-11T23:59:59Z \
  --period 3600 \
  --statistics Sum
```

## 🤝 Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- **Vector**: Data pipeline and event streaming
- **MikroTik RouterOS**: Network infrastructure
- **AWS Lambda**: Serverless compute
- **Apprise**: Multi-channel notifications
- **Grafana**: Visualization and dashboards

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/melvyndekort/network-monitor/issues)
- **Discussions**: [GitHub Discussions](https://github.com/melvyndekort/network-monitor/discussions)
- **Documentation**: [docs/](docs/)

---

**Status**: Active Development

**Version**: 1.0.0

**Last Updated**: 2026-03-11
