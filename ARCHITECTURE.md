# Network Monitor Architecture

Detailed technical architecture documentation for the Network Monitor system.

## Table of Contents

- [Overview](#overview)
- [Design Principles](#design-principles)
- [Component Architecture](#component-architecture)
- [Data Flow](#data-flow)
- [Event Streaming](#event-streaming)
- [State Management](#state-management)
- [Scalability](#scalability)
- [Security](#security)
- [Monitoring & Observability](#monitoring--observability)

## Overview

Network Monitor is a serverless, event-driven system for comprehensive network device monitoring. It uses a hybrid architecture with on-premise data collection and cloud-based processing.

### Key Characteristics

- **Event-Driven**: All state changes flow through event streams
- **Serverless**: Zero infrastructure management (AWS Lambda)
- **Hybrid**: On-premise collection, cloud processing
- **Real-time**: Sub-second event processing
- **Cost-Effective**: ~$3-5/month for typical homelab

## Design Principles

### 1. KISS (Keep It Simple, Stupid)

- Single responsibility per Lambda function
- Minimal dependencies
- Clear data flow
- No over-engineering

### 2. Security First

- No AWS access to on-premise network
- MikroTik credentials stay on-premise
- Cloudflare Tunnel for Apprise (no port forwarding)
- Least privilege IAM roles

### 3. Event Sourcing

- All state changes are events
- Events are immutable
- State can be rebuilt from events
- 90-day event retention

### 4. Fail-Safe

- Dead letter queues for failed processing
- Automatic retries
- Data collector reconnects on connection loss

## Component Architecture

### On-Premise Components

#### Data Collector Container

**Purpose**: Gather network data from MikroTik router and OpenWrt APs, send events to AWS SQS

**Technology**: Python 3.12, librouteros, boto3

**Responsibilities**:
- Poll 4 OpenWrt APs via ubus HTTP JSON-RPC for associated wireless clients (primary presence signal)
- Poll MikroTik ARP table every 60 seconds for wired devices (skips stale entries)
- Poll DHCP leases for IP/hostname enrichment only (not used as presence signal)
- Send `device_activity` events directly to SQS FIFO queue
- Automatic reconnection on MikroTik API failures
- Graceful handling of individual AP failures (other APs still polled)

**Why Container?**:
- Isolated environment
- Easy deployment
- Consistent runtime
- Can be restarted without affecting other services

**Event Output Format**:
```json
{
  "timestamp": "2026-03-11T12:59:55.526Z",
  "source": "data_collector",
  "event_type": "device_activity",
  "mac": "00:11:22:33:44:55",
  "ip": "10.204.10.100",
  "hostname": "johns-iphone",
  "vlan": 10,
  "metadata": {}
}
```

**Key Design Decision**: The data collector is a pure sensor — it sends `device_activity` for every device on every poll. It does not track state or decide whether a device is "new". The event-router Lambda handles new-device detection by checking DynamoDB.

**Presence Signal Priority**:
1. **Wireless**: AP association via ubus `hostapd.*.get_clients` — most reliable, drops immediately on disconnect
2. **Wired**: MikroTik ARP table (non-stale entries) — for devices connected via Ethernet
3. **DHCP**: Used only for IP/hostname enrichment — leases persist after disconnect, not reliable for presence

#### Vector (Syslog Gateway)

**Purpose**: Receive RouterOS syslog, extract DHCP events, forward to SQS and Loki

**Technology**: Vector 0.36+

**Responsibilities**:
- Receive syslog from RouterOS via UDP port 514
- Filter DHCP-related syslog messages
- Transform DHCP events to the common event schema
- Send DHCP events to AWS SQS FIFO queue
- Forward all syslog to Grafana Cloud Loki

**Why Vector?**:
- Battle-tested event pipeline
- Powerful transformation capabilities (VRL)
- Low resource usage
- Dual output: SQS for events, Loki for logs

**Configuration Highlights**:
```toml
[sources.syslog]
type = "syslog"
address = "0.0.0.0:514"
mode = "udp"

[transforms.dhcp_filter]
type = "filter"
inputs = ["fix_timestamp"]
condition = 'contains!(.appname, "dhcp")'

[sinks.aws_sqs]
type = "aws_sqs"
inputs = ["dhcp_to_event"]
queue_url = "${SQS_QUEUE_URL}"
message_group_id = "{{ mac }}"
```

#### Apprise Container

**Purpose**: Multi-channel notification delivery

**Technology**: Apprise

**Responsibilities**:
- Receive notification requests from Lambda
- Deliver to configured channels via `homelab` tag
- Handle retries and failures

**Exposure**: Cloudflare Tunnel (`https://apprise.mdekort.nl`) with Zero Trust service token auth

#### OpenWrt Access Points

**Purpose**: Provide authoritative wireless client association data

**Technology**: OpenWrt 24.10, rpcd + uhttpd-mod-ubus

**APs**: lm-ap-1 (10.204.50.11), lm-ap-2 (10.204.50.12), lm-ap-3 (10.204.50.13), lm-ap-4 (10.204.50.14)

**Access Method**: ubus HTTP JSON-RPC (`POST http://<ap>/ubus`)
- Login with `netmon` rpcd user → session token
- List `hostapd.*` interfaces
- Call `get_clients` on each interface → associated MAC addresses

**ACL**: Read-only access to `hostapd.*.get_clients` via `/usr/share/rpcd/acl.d/network-monitor.json`

**Why ubus HTTP over SSH/SNMP?**:
- Already running on all APs (uhttpd + rpcd)
- No extra packages needed
- Lightweight HTTP POST, no connection overhead
- Structured JSON responses
- SNMP on OpenWrt lacks native wireless station MIB support

### AWS Components

#### SQS Queue: device-events.fifo

**Purpose**: Single entry point for all events (from data collector and Vector)

**Configuration**:
- FIFO queue (ordered processing per device via MessageGroupId = MAC)
- Message retention: 14 days
- Visibility timeout: 60 seconds
- Dead letter queue with maxReceiveCount: 3

**Why FIFO?**:
- Ensures events for same device are processed in order
- Prevents race conditions in state updates
- Content-based deduplication

#### Lambda: event-router

**Purpose**: Normalize events, update device state, route to processors

**Trigger**: SQS (device-events.fifo), batch size 10

**Responsibilities**:
- Validate and normalize event schema
- Deduplicate events (30-second window via deduplication table)
- Check DynamoDB to determine if device is new or existing
- Create new devices or update `last_seen`/`online_until` for existing ones
- Detect "back online" transitions (was offline, now active)
- Write to DynamoDB (device_events table)
- Route to SNS topics:
  - New device → `device-discovered` + `notifications`
  - Back online → `notifications` + `device-activity`
  - Normal activity → `device-activity`

**Configuration**:
- Memory: 256 MB
- Timeout: 30 seconds

#### Lambda: send-notifications

**Purpose**: Send notifications via Apprise

**Trigger**: SQS (notifier-queue), batch size 5

**Responsibilities**:
- Check if device has `notify` flag enabled
- Check throttle table (1 hour cooldown per mac+event_type)
- Format notification message
- HTTP POST to Apprise via Cloudflare Tunnel (with CF Access service token)
- Update throttle table

**Configuration**:
- Memory: 256 MB
- Timeout: 30 seconds

#### Lambda: enrich-metadata

**Purpose**: Enrich device data with manufacturer info

**Trigger**: SQS (metadata-enricher-queue), batch size 2

**Responsibilities**:
- Lookup manufacturer via macvendors.com API
- Skip if manufacturer already set
- Rate limited (1 second delay between lookups)
- Update DynamoDB devices table

**Configuration**:
- Memory: 256 MB
- Timeout: 30 seconds

#### Lambda: api-handler

**Purpose**: REST API for device management

**Trigger**: Lambda function URL (via CloudFront OAC with SigV4)

**Endpoints**:
- `GET /devices`: List all devices (with computed online/offline status)
- `GET /devices/{mac}`: Get device details
- `PUT /devices/{mac}`: Update device (name, notify, device_type)
- `DELETE /devices/{mac}`: Delete device

**Configuration**:
- Memory: 512 MB
- Timeout: 30 seconds

#### DynamoDB Tables

See [README.md](README.md#-data-model) for detailed table schemas.

**Design Decisions**:
- **On-demand pricing**: Unpredictable traffic patterns
- **TTL enabled**: Automatic cleanup — 14 days for devices, 90 days for events, 5 minutes for dedup, 1 hour for throttle
- **GSI for queries**: vlan-index for fast lookups by VLAN
- **Point-in-time recovery**: Enabled on devices and events tables

#### CloudFront Distribution

**Purpose**: Serve UI and proxy API requests

**Configuration**:
- S3 origin for static UI (via OAI)
- Lambda function URL origin for `/api/*` (via OAC with SigV4)
- Signed cookie authentication via Cognito (trusted key groups)
- Public paths: `/error-pages/*`, `/callback.html`, `/assets/*` (for auth flow)
- Custom error response: 403 → login redirect page

## Data Flow

### Device Discovery Flow

```
1. Data Collector polls all 4 OpenWrt APs for associated wireless clients
2. Data Collector polls MikroTik ARP table for wired devices
3. Data Collector merges wireless + ARP MACs, enriches with DHCP data
4. Data Collector sends device_activity events to SQS
5. Lambda (event-router) processes event
6. Event-router checks DynamoDB — device not found
7. Event-router creates device, writes event
8. Event-router publishes to SNS (device-discovered + notifications)
9. Lambda (send-notifications) sends notification
10. Lambda (enrich-metadata) looks up manufacturer
```

### Existing Device Activity Flow

```
1. Data Collector polls APs + ARP, sees known device
2. Data Collector sends device_activity event to SQS
3. Lambda (event-router) processes event
4. Event-router checks DynamoDB — device found
5. Event-router updates last_seen, online_until, ttl
6. If device was offline (online_until had passed):
   → publishes to notifications topic (back online)
7. Event-router publishes to device-activity topic
```

### State Change Flow

```
1. Device goes offline (no activity for 15 minutes)
2. online_until timestamp expires
3. Next API/UI read computes current_state = offline
4. No Lambda invocation needed — status is derived at read time
```

### DHCP Syslog Flow

```
1. MikroTik sends DHCP syslog to Vector (UDP 514)
2. Vector filters for DHCP messages
3. Vector transforms to event schema (dhcp_assigned/dhcp_released)
4. Vector sends to SQS FIFO queue
5. Event-router processes like any other event
```

## Event Streaming

### Event Schema

All events follow this schema:

```json
{
  "timestamp": "ISO 8601 timestamp",
  "source": "data_collector | syslog_dhcp",
  "event_type": "device_activity | device_discovered | dhcp_assigned | dhcp_released",
  "mac": "MAC address (uppercase, colon-separated)",
  "ip": "IP address (optional)",
  "hostname": "Hostname (optional)",
  "vlan": "VLAN ID (optional, detected from IP prefix)",
  "metadata": {}
}
```

### Event Types

| Event Type | Source | Description |
|------------|--------|-------------|
| `device_activity` | data_collector | Device seen via AP wireless association or ARP table |
| `device_discovered` | event-router | New MAC address (set by event-router, not data collector) |
| `dhcp_assigned` | syslog_dhcp | DHCP lease granted (via Vector) |
| `dhcp_released` | syslog_dhcp | DHCP lease released (via Vector) |

### Fan-Out Pattern

```
SQS (device-events.fifo)
  → event-router Lambda
    → SNS device-discovered → metadata-enricher SQS → enrich-metadata Lambda
    → SNS notifications → notifier SQS → send-notifications Lambda
    → SNS device-activity (available for future consumers)
```

## State Management

### Device State

Stored in DynamoDB `network-monitor-devices` table.

**Presence Model**:

Each device has an `online_until` timestamp, refreshed on every activity event:
```
online_until = now + 900 (15 minutes)
```

A device is **online** if `online_until > now`, otherwise **offline**. Status is computed at read time by the API handler — no state machine, no state change events.

**Device Lifecycle**:
- Created when first seen (by event-router)
- Updated on every activity event (last_seen, online_until, ttl)
- Auto-deleted after 14 days of inactivity (DynamoDB TTL)
- Re-discovered as new device when it returns

### Event History

Stored in DynamoDB `network-monitor-device-events` table.

**Retention**: 90 days (TTL)

## Scalability

### Current Scale

- **Devices**: ~50-100
- **Events**: ~50K/month
- **API Requests**: ~10K/month

### Scaling Limits

| Component | Current | Max (without changes) |
|-----------|---------|----------------------|
| Data Collector | 1 instance | 1 instance (single router) |
| SQS | 50K msgs/month | 1M msgs/month (free tier) |
| Lambda | 50K invocations/month | 1M invocations/month (free tier) |
| DynamoDB | On-demand | Unlimited |

## Security

### Security Layers

**Layer 1: Network**
- MikroTik credentials never leave on-premise
- Cloudflare Tunnel for Apprise (no port forwarding)
- Zero Trust service token for Apprise access

**Layer 2: Authentication**
- CloudFront signed cookies (Cognito login)
- IAM roles for Lambda
- SQS queue policies
- Lambda function URL with OAC (SigV4)

**Layer 3: Authorization**
- Lambda execution roles (least privilege per function)
- DynamoDB table-level permissions
- S3 bucket policy (OAI only)

**Layer 4: Encryption**
- TLS for all communication
- DynamoDB encryption at rest
- SQS encryption at rest
- SSM SecureString for CF Access credentials

### IAM Roles

**event-router-role**:
- Read from SQS (device-events.fifo)
- Read/Write DynamoDB (devices, device_events, deduplication)
- Publish to SNS (device-discovered, device-activity, notifications)

**send-notifications-role**:
- Read from SQS (notifier-queue)
- Read/Write DynamoDB (devices, notification_throttle)
- Read SSM parameters (CF Access credentials)

**enrich-metadata-role**:
- Read from SQS (metadata-enricher-queue)
- Read/Write DynamoDB (devices)

**api-handler-role**:
- Read/Write/Delete/Scan DynamoDB (devices, device_events)

## Monitoring & Observability

### CloudWatch Logs

**Log Groups**:
- `/aws/lambda/network-monitor-event-router`
- `/aws/lambda/network-monitor-send-notifications`
- `/aws/lambda/network-monitor-enrich-metadata`
- `/aws/lambda/network-monitor-api-handler`

### Grafana Cloud

- **Loki**: All RouterOS syslog via Vector
- **Infinity plugin**: Queries REST API for device dashboards

## References

- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)
- [Vector Documentation](https://vector.dev/docs/)
- [MikroTik RouterOS API](https://help.mikrotik.com/docs/display/ROS/API)
- [Apprise Documentation](https://github.com/caronc/apprise)

---

**Last Updated**: 2026-03-25
