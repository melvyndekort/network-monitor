# Network Monitor

**Serverless network device monitoring system with event streaming architecture**

Comprehensive network monitoring solution that tracks all devices across VLANs, detects presence changes, and sends notifications. Built with AWS Lambda, DynamoDB, and Vector for event streaming.

## Architecture

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
│  AWS                                                             │
│  SQS → Lambda (event-router) → SNS → SQS (fan-out)             │
│  Lambdas: event-router, send-notifications, enrich-metadata     │
│  DynamoDB: device state + event history                         │
│  CloudFront + S3: UI | CloudFront + Lambda URL: API             │
└─────────────────────────────────────────────────────────────────┘
```

See [docs/architecture.md](docs/architecture.md) for detailed component documentation.

## Features

- **Wireless Client Monitoring**: Polls 4 OpenWrt APs via ubus HTTP JSON-RPC (primary presence signal)
- **Wired Device Monitoring**: Polls MikroTik ARP table for Ethernet-connected devices
- **DHCP Enrichment**: IP/hostname lookup from DHCP leases (not used as presence signal)
- **DHCP Event Tracking**: Captures DHCP assignments/releases via RouterOS syslog (through Vector)
- **Presence Tracking**: TTL-based `online_until` timestamp, computed at read time — no state machine
- **Device Auto-Expiry**: Devices deleted after 14 days of inactivity via DynamoDB TTL
- **Notifications**: Apprise integration with per-device toggle and 1-hour throttling
- **Manufacturer Lookup**: Automatic MAC vendor identification via macvendors.com API
- **REST API**: CRUD operations via CloudFront + Lambda function URL (OAC/SigV4)
- **Bootstrap 5 UI**: Dark theme dashboard with inline editing at `https://network-monitor.mdekort.nl`
- **Signed Cookie Auth**: Cognito login → CloudFront signed cookies

## Data Flow

```
1a. OpenWrt APs → Data Collector → AWS SQS (wireless client associations)
1b. MikroTik Router → Data Collector → AWS SQS (ARP for wired + DHCP for enrichment)
1c. MikroTik Router → Vector → AWS SQS (DHCP syslog events)
2.  SQS → Lambda (event-router) → SNS Topics
3.  SNS → SQS Queues (fan-out) → Lambda processors
4.  Lambdas write to DynamoDB
5.  CloudFront proxies /api/* to Lambda function URL
```

## Repository Structure

```
network-monitor/
├── terraform/                         # AWS infrastructure (DynamoDB, Lambda, SNS/SQS, CloudFront, IAM)
├── lambdas/                           # Lambda functions (event_router, send_notifications, enrich_metadata, api_handler)
├── data-collector/                    # On-premise data collector (MikroTik + OpenWrt polling)
├── ui/                                # Static web UI (Bootstrap 5, Cognito auth)
├── examples/                          # Vector config, Grafana dashboards
├── docs/                              # Documentation
├── scripts/                           # Deployment scripts
└── .github/workflows/                 # CI/CD
```

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | Component details, data flows, design decisions |
| [Deployment](docs/deployment.md) | Setup, configuration, environment variables, troubleshooting |
| [API Reference](docs/api.md) | REST API endpoints and examples |
| [Event Types](docs/event-types.md) | Event schemas, sources, presence model |
| [Grafana Setup](docs/grafana-setup.md) | Dashboard configuration with Infinity plugin |
| [Changelog](docs/changelog.md) | Project history and task tracking |

## Cost Estimate

- **$0/month** within AWS free tier limits
- **$3-5/month** after free tier for typical homelab usage (~50K Lambda invocations, <1 GB DynamoDB)

## Security

- IAM least privilege per Lambda function
- CloudFront signed cookies (Cognito auth)
- Cloudflare Tunnel for on-premise Apprise (Zero Trust service token)
- SSM SecureString for CF Access credentials
- DynamoDB + SQS encryption at rest
- MikroTik/AP credentials stay on-premise

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Status**: Active Development · **Version**: 1.0.0 · **Last Updated**: 2026-03-25
