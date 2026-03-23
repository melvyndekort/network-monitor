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
- Vector acts as security boundary
- Least privilege IAM roles

### 3. Event Sourcing

- All state changes are events
- Events are immutable
- State can be rebuilt from events
- 90-day event retention

### 4. Fail-Safe

- Vector buffers events if AWS is down
- Dead letter queues for failed processing
- Automatic retries with exponential backoff
- Local backup of all events

## Component Architecture

### On-Premise Components

#### Data Collector Container

**Purpose**: Gather network data from MikroTik router

**Technology**: Python 3.12, librouteros

**Responsibilities**:
- Poll MikroTik ARP table every 30 seconds
- Poll DHCP leases
- Poll wireless registrations
- Output structured JSON events to stdout

**Why Container?**:
- Isolated environment
- Easy deployment
- Consistent runtime
- Can be restarted without affecting other services

**Event Output Format**:
```json
{
  "timestamp": "2026-03-11T12:59:55.526Z",
  "source": "mikrotik_arp",
  "event_type": "device_discovered",
  "mac": "00:11:22:33:44:55",
  "ip": "10.204.10.100",
  "hostname": "johns-iphone",
  "vlan": 10,
  "metadata": {
    "interface": "vlan10",
    "complete": true,
    "dynamic": true
  }
}
```

#### Vector (Event Gateway)

**Purpose**: Aggregate, normalize, and forward events to AWS

**Technology**: Vector 0.36+

**Responsibilities**:
- Receive syslog from RouterOS (DHCP events)
- Receive JSON events from data collector (exec source)
- Parse and normalize different event formats
- Deduplicate events (30-second window)
- Buffer events if AWS is unavailable
- Forward to AWS SQS

**Why Vector?**:
- Battle-tested event pipeline
- Built-in buffering and retry logic
- Powerful transformation capabilities
- Low resource usage
- Acts as security boundary

**Configuration Highlights**:
```toml
[sources.data_collector]
type = "exec"
command = ["docker", "exec", "data-collector", "python", "-u", "/app/collector/main.py"]
mode = "streaming"

[transforms.deduplicate]
type = "dedupe"
fields.match = ["mac", "event_type"]
cache.num_events = 10000

[sinks.aws_sqs]
type = "aws_sqs"
queue_url = "https://sqs.eu-west-1.amazonaws.com/account/device-events.fifo"
message_group_id = "{{ mac }}"
```

#### Apprise Container

**Purpose**: Multi-channel notification delivery

**Technology**: Apprise

**Responsibilities**:
- Receive notification requests from Lambda
- Deliver to configured channels (ntfy, email, etc.)
- Handle retries and failures

**Exposure**: Cloudflare Tunnel (https://apprise.internal.mdekort.nl)

### AWS Components

#### SQS Queue: device-events.fifo

**Purpose**: Single entry point for all events from Vector

**Configuration**:
- FIFO queue (ordered processing)
- Message retention: 14 days
- Visibility timeout: 60 seconds
- Dead letter queue: device-events-dlq

**Why FIFO?**:
- Ensures events for same device are processed in order
- Prevents race conditions in state updates
- Message deduplication

#### Lambda: event-router

**Purpose**: Normalize events and route to appropriate processors

**Trigger**: SQS (device-events.fifo)

**Responsibilities**:
- Validate event schema
- Normalize event format
- Write to DynamoDB (device_events table)
- Route to SNS topics based on event type
- Handle deduplication

**Routing Logic**:
```python
if event_type in ['device_discovered']:
    publish_to_sns('device-discovered', event)
elif event_type in ['device_activity', 'dhcp_assigned']:
    publish_to_sns('device-activity', event)
elif event_type in ['state_changed']:
    publish_to_sns('device-state-changed', event)
```

**Configuration**:
- Memory: 256 MB
- Timeout: 30 seconds
- Concurrency: 10
- Batch size: 10 events

#### Lambda: send-notifications

**Purpose**: Send notifications via Apprise

**Trigger**: SQS (notifier-queue)

**Responsibilities**:
- Check if device has notifications enabled
- Check throttle table (prevent spam)
- Format notification message
- HTTP POST to Apprise
- Update throttle table

**Throttling Logic**:
- New device: Max 1 notification per hour
- Device offline: Max 1 notification per 4 hours
- Device online: Max 1 notification per hour

**Configuration**:
- Memory: 256 MB
- Timeout: 30 seconds
- Concurrency: 5

#### Lambda: enrich-metadata

**Purpose**: Enrich device data with manufacturer, hostname, etc.

**Trigger**: SQS (metadata-enricher-queue)

**Responsibilities**:
- Lookup manufacturer via MAC address
- Reverse DNS for hostname
- Device fingerprinting (OS detection)
- Update DynamoDB (devices table)

**Rate Limiting**:
- Max 1 manufacturer lookup per second (external API limits)
- Uses DynamoDB to track last lookup time

**Configuration**:
- Memory: 256 MB
- Timeout: 30 seconds
- Concurrency: 2 (rate limiting)

#### Lambda: api-handler

**Purpose**: REST API for device management

**Trigger**: API Gateway

**Endpoints**:
- `GET /devices`: List all devices
- `GET /devices/{mac}`: Get device details
- `PUT /devices/{mac}`: Update device
- `DELETE /devices/{mac}`: Delete device
- `GET /devices/{mac}/history`: Get event history
- `GET /stats`: Network statistics

**Configuration**:
- Memory: 512 MB
- Timeout: 30 seconds
- Concurrency: 10

#### DynamoDB Tables

See [README.md](README.md#data-model) for detailed table schemas.

**Design Decisions**:
- **On-demand pricing**: Unpredictable traffic patterns
- **TTL enabled**: Automatic cleanup of old events
- **GSI for queries**: Fast lookups by state and VLAN
- **Single-table design**: Considered but rejected (multiple tables clearer)

#### API Gateway

**Type**: REST API

**Configuration**:
- Regional endpoint
- API key authentication
- CORS enabled
- CloudWatch logging enabled

**Why REST over HTTP API?**:
- More features (API keys, usage plans)
- Better for public APIs
- Marginal cost difference for homelab scale

#### S3 + CloudFront (Optional)

**Purpose**: Host static UI

**Configuration**:
- S3 bucket: network-monitor-ui
- CloudFront distribution (optional, for HTTPS)
- Static website hosting

## Data Flow

### Device Discovery Flow

```
1. MikroTik ARP table contains new MAC
2. Data Collector polls ARP table
3. Data Collector outputs JSON event to stdout
4. Vector receives event via exec source
5. Vector normalizes and deduplicates
6. Vector sends to SQS (device-events.fifo)
7. Lambda (event-router) processes event
8. Lambda writes to DynamoDB (device_events)
9. Lambda publishes to SNS (device-discovered)
10. SNS fans out to multiple SQS queues
11. Lambda (send-notifications) sends notification
12. Lambda (enrich-metadata) looks up manufacturer
```

### State Change Flow

```
1. Device goes offline (no activity for 15 minutes)
2. online_until timestamp expires
3. Next API/UI read computes current_state = offline
4. No Lambda invocation needed — status is derived at read time
```

### API Query Flow

```
1. User requests GET /devices?state=online
2. API Gateway authenticates request
3. Lambda (api-handler) invoked
4. Lambda queries DynamoDB (devices table)
5. Lambda returns JSON response
6. API Gateway returns to user
```

## Event Streaming

### Why Event Streaming?

- **Decoupling**: Producers and consumers are independent
- **Scalability**: Add new consumers without changing producers
- **Reliability**: Events are persisted, can be replayed
- **Observability**: All state changes are visible
- **Flexibility**: Easy to add new features

### Event Schema

All events follow this schema:

```json
{
  "timestamp": "ISO 8601 timestamp",
  "source": "mikrotik_arp | routeros_dhcp | wireless",
  "event_type": "device_discovered | device_activity | dhcp_assigned | ...",
  "mac": "MAC address (uppercase, colon-separated)",
  "ip": "IP address (optional)",
  "hostname": "Hostname (optional)",
  "vlan": "VLAN ID (optional)",
  "metadata": {
    "source-specific fields": "..."
  }
}
```

### Event Types

| Event Type | Source | Description |
|------------|--------|-------------|
| `device_discovered` | mikrotik_arp | New MAC address seen |
| `device_activity` | mikrotik_arp | Existing device still present |
| `dhcp_assigned` | routeros_dhcp | DHCP lease granted |
| `dhcp_released` | routeros_dhcp | DHCP lease released |
| `wireless_connected` | wireless | Client associated to AP |
| `wireless_disconnected` | wireless | Client disassociated |
| `state_changed` | *(removed)* | State is derived from `online_until` at read time |

### Fan-Out Pattern

```
SNS Topic: device-events
  ↓
  ├─→ SQS: event-processor-queue → Lambda: event-router
  ├─→ SQS: notifier-queue → Lambda: send-notifications
  └─→ SQS: metadata-enricher-queue → Lambda: enrich-metadata
```

**Benefits**:
- Each Lambda processes events independently
- Failures in one Lambda don't affect others
- Easy to add new processors
- Built-in retry and DLQ

## State Management

### Device State

Stored in DynamoDB `devices` table.

**Presence Model**:

Each device has an `online_until` timestamp, refreshed on every activity event:
```
online_until = now + 900 (15 minutes)
```

A device is **online** if `online_until > now`, otherwise **offline**. Status is computed at read time by the API handler — no state machine, no state change events, no dedicated Lambda.

**State Definitions**:
- `online`: `online_until` is in the future
- `offline`: `online_until` has passed

### Event History

Stored in DynamoDB `device_events` table.

**Retention**: 90 days (TTL)

**Purpose**:
- Audit trail
- Debugging
- Historical analysis
- Grafana dashboards

### Presence History

Stored in DynamoDB `device_presence` table (optional).

**Purpose**:
- Time-series data for Grafana
- Uptime calculations
- Pattern analysis

**Alternative**: Export to CloudWatch Metrics

## Scalability

### Current Scale

- **Devices**: ~50-100
- **Events**: ~500K/month
- **API Requests**: ~10K/month

### Scaling Limits

| Component | Current | Max (without changes) |
|-----------|---------|----------------------|
| Data Collector | 1 instance | 10 instances |
| Vector | 1 instance | 5 instances |
| SQS | 500K msgs/month | 1M msgs/month (free tier) |
| Lambda | 500K invocations/month | 1M invocations/month (free tier) |
| DynamoDB | On-demand | Unlimited |
| API Gateway | 10K requests/month | 1M requests/month (free tier) |

### Scaling Strategies

**Horizontal Scaling**:
- Add more data collector instances
- Increase Lambda concurrency
- Add more SQS queues (sharding)

**Vertical Scaling**:
- Increase Lambda memory (faster execution)
- Use provisioned DynamoDB capacity

**Cost Optimization**:
- Use Lambda ARM64 (20% cheaper)
- Enable DynamoDB auto-scaling
- Use S3 Intelligent-Tiering for UI

## Security

### Threat Model

**Threats**:
- Unauthorized access to AWS resources
- Exposure of MikroTik credentials
- Man-in-the-middle attacks
- Data exfiltration
- Denial of service

**Mitigations**:
- IAM roles with least privilege
- Secrets Manager for credentials
- TLS for all communication
- API Gateway authentication
- Rate limiting
- CloudWatch alarms

### Security Layers

**Layer 1: Network**
- MikroTik credentials never leave on-premise
- Vector acts as security boundary
- Cloudflare Tunnel for Apprise (no port forwarding)

**Layer 2: Authentication**
- API Gateway API keys
- IAM roles for Lambda
- SQS queue policies

**Layer 3: Authorization**
- Lambda execution roles (least privilege)
- DynamoDB table policies
- S3 bucket policies

**Layer 4: Encryption**
- TLS 1.3 for all communication
- DynamoDB encryption at rest
- SQS encryption at rest
- S3 encryption at rest

**Layer 5: Monitoring**
- CloudWatch alarms for anomalies
- CloudTrail for audit logs
- VPC Flow Logs (if using VPC)

### IAM Roles

**event-router-role**:
- Read from SQS (device-events.fifo)
- Write to DynamoDB (device_events)
- Publish to SNS (device-discovered, device-activity)
- Write to CloudWatch Logs

**track-presence-role**: *(removed — presence is derived from `online_until` at read time)*

**send-notifications-role**:
- Read from SQS (notifier-queue)
- Read/Write DynamoDB (devices, notification_throttle)
- HTTP POST to Apprise (via VPC or public internet)
- Write to CloudWatch Logs

**enrich-metadata-role**:
- Read from SQS (metadata-enricher-queue)
- Read/Write DynamoDB (devices)
- HTTP GET to external APIs (manufacturer lookup)
- Write to CloudWatch Logs

**api-handler-role**:
- Read/Write DynamoDB (devices, device_events)
- Write to CloudWatch Logs

## Monitoring & Observability

### CloudWatch Metrics

**Lambda Metrics**:
- Invocations
- Errors
- Duration
- Throttles
- Concurrent executions

**SQS Metrics**:
- Messages sent
- Messages received
- Messages deleted
- Age of oldest message
- Approximate number of messages visible

**DynamoDB Metrics**:
- Consumed read/write capacity
- Throttled requests
- User errors
- System errors

**API Gateway Metrics**:
- Request count
- Latency
- 4xx errors
- 5xx errors

### CloudWatch Alarms

**Critical Alarms**:
- Lambda error rate > 5%
- SQS age of oldest message > 5 minutes
- DynamoDB throttled requests > 0
- API Gateway 5xx errors > 10

**Warning Alarms**:
- Lambda duration > 20 seconds
- SQS messages visible > 1000
- DynamoDB consumed capacity > 80%
- API Gateway latency > 1 second

### CloudWatch Logs

**Log Groups**:
- `/aws/lambda/event-router`
- `/aws/lambda/send-notifications`
- `/aws/lambda/enrich-metadata`
- `/aws/lambda/api-handler`
- `/aws/apigateway/network-monitor`

**Log Retention**: 30 days

### Grafana Dashboards

**Network Overview**:
- Total devices
- Online/offline devices
- Devices by VLAN
- New devices today
- Event rate

**Device Details**:
- Presence history (24h, 7d, 30d)
- Event timeline
- Connection history

**System Health**:
- Lambda invocations
- Lambda errors
- SQS queue depth
- API latency

### Tracing

**AWS X-Ray** (optional):
- End-to-end request tracing
- Service map
- Performance bottlenecks

## Future Enhancements

### Short-term (1-3 months)
- WebSocket support for real-time updates
- Device grouping
- Custom notification rules
- Bandwidth monitoring

### Medium-term (3-6 months)
- Anomaly detection (ML-based)
- Network topology visualization
- Device fingerprinting (OS detection)
- Historical analytics

### Long-term (6-12 months)
- Multi-site support
- Integration with other monitoring systems
- Mobile app
- Advanced alerting (PagerDuty, Opsgenie)

## References

- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)
- [Vector Documentation](https://vector.dev/docs/)
- [MikroTik RouterOS API](https://help.mikrotik.com/docs/display/ROS/API)
- [Apprise Documentation](https://github.com/caronc/apprise)

---

**Last Updated**: 2026-03-11
