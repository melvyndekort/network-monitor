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
- Send `device_activity` events to SQS FIFO queue only for devices that are new, changed (IP/hostname/AP), or due for a periodic heartbeat — not one event per device per poll
- Optionally poll Pi-hole for tracked devices' DNS query activity, pushed to Grafana Cloud Loki (see below)
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

**Key Design Decision**: The data collector is a pure sensor — it does not track state or decide whether a device is "new". The event-router Lambda handles new-device detection by checking DynamoDB.

**Change Detection**: Each poll computes a per-device signature (`ip`, `hostname`, AP) and keeps in-memory state across polls. An event is only sent when the signature changes, is new, or hasn't been sent in `HEARTBEAT_INTERVAL` (default 15 minutes) — the heartbeat exists purely to refresh `online_until` downstream for devices with nothing else to report. A device dropped from the active set is removed from state, so a later reappearance is treated as a fresh change rather than "unchanged". This replaced sending one event per device on every 60s poll, which was driving 2.6-7M DynamoDB write-request-units/month (~40x this doc's own prior estimate).

**Presence Signal Priority**:
1. **Wireless**: AP association via ubus `hostapd.*.get_clients` — most reliable, drops immediately on disconnect
2. **Wired**: MikroTik ARP table (non-stale entries) — for devices connected via Ethernet
3. **DHCP**: Used only for IP/hostname enrichment — leases persist after disconnect, not reliable for presence

**SQS Deduplication**: Each poll sends at most one batched SQS message (all changed devices in one body). The FIFO `MessageDeduplicationId` is a hash of the batch content with `timestamp` excluded, so a retry of the same event set is actually deduplicated by content — a raw per-event timestamp in the hash would make every send unique and defeat FIFO content-based dedup.

#### Pi-hole Client (Optional)

**Purpose**: Poll Pi-hole's REST API for tracked devices' DNS query activity, classify allowed/blocked, push to Grafana Cloud Loki

**Technology**: Python, Pi-hole v6 API (`/api/auth`, `/api/queries`, `/api/network/devices`)

**Responsibilities**:
- Authenticate per-host via `/api/auth` (session-based; Pi-hole v6 requires a session for all endpoints), re-logging in automatically on an expired/401 session
- Cross-reference `network/devices` for each tracked device's current IPv4/IPv6 addresses (Pi-hole's `client=` query filter doesn't reliably scope by device, and IPv6 privacy addresses rotate)
- Track a per-host last-seen query timestamp and use it as the `from` filter boundary — Pi-hole's `cursor` field on `/api/queries` is not a pagination token; resubmitting it returns identical rows, so a timestamp boundary is the only real advance mechanism
- Classify each query allowed/blocked from Pi-hole's `status` field, push to Loki via `loki.py`

**Why bypass SQS/DynamoDB?**: The device-presence pipeline's schema is device-presence-shaped (one row per device, updated in place), not per-query-DNS-event-shaped. Pushing straight to Loki avoids forcing DNS query volume through a pipeline built for a different access pattern.

**Enabled only when** `PIHOLE_HOSTS`, `PIHOLE_TRACKED_DEVICES`, `PIHOLE_API_PASSWORDS` (JSON, keyed by host), and `LOKI_PASSWORD` are all set — same optional pattern as the InfluxDB writer below.

#### InfluxDB Writer (Optional)

**Purpose**: Write one `device_presence` point per active device per poll to a homelab InfluxDB bucket, for the Device Presence Timeline Grafana dashboard (see [Grafana Setup](grafana-setup.md))

**Enabled only when** `INFLUXDB_URL` and `INFLUXDB_TOKEN` are set.

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
- Validate and normalize event schema, classifying each MAC's `mac_type` (`vendor` vs. `locally_administered`, from the U/L bit — a secondary priority signal, not "new = suspicious" on its own, since legitimate devices rotate randomized MACs too)
- Deduplicate events (30-second window via deduplication table)
- Check DynamoDB to determine if device is new, existing, or a MAC rotation of a known device — looked up by hostname via the `hostname-index` GSI, so an Android/iOS/ChromeOS privacy MAC rotation migrates the existing device's identity onto the new MAC instead of alerting as a brand-new device
- Create new devices, migrate identity on a detected rotation, or update `last_seen`/`online_until`/`mac_type` for existing ones
- Detect "back online" transitions (was offline for longer than a 30-minute grace period, now active)
- Write to DynamoDB (device_events table)
- Route to SNS topics:
  - New device → `device-discovered` + `notifications`
  - MAC rotation → `notifications`
  - Back online → `notifications`

**Configuration**:
- Memory: 256 MB
- Timeout: 30 seconds

#### Lambda: send-notifications

**Purpose**: Send notifications via Apprise

**Trigger**: SQS (notifier-queue), batch size 5

**Responsibilities**:
- New device discovery notifications always sent (bypass per-device flag)
- Check if device has `notify` flag enabled (for state change notifications)
- Check throttle table (1 hour cooldown per mac + reason, where reason is the specific transition — `discovered`/`rotated`/`online` — not the raw event type, so a discovery and a back-online for the same device don't share a throttle key)
- Format notification message
- HTTP POST to Apprise via Cloudflare Tunnel (with CF Access service token)
- Update throttle table only after a successful Apprise delivery — a failed send no longer silently swallows the next retry's chance to alert

**Configuration**:
- Memory: 256 MB
- Timeout: 30 seconds

#### Lambda: enrich-metadata

**Purpose**: Enrich device data with manufacturer info

**Trigger**: SQS (metadata-enricher-queue), batch size 2; EventBridge (daily retry)

**Responsibilities**:
- Lookup manufacturer via fallback chain: macvendors.com → maclookup.app → macvendors.co
- Skip if manufacturer already set
- Skip the lookup chain entirely for `locally_administered` (randomized) MACs — a vendor lookup can never succeed for one, so there's no point retrying it against 3 APIs every day forever
- Rate limited (1 second delay between lookups)
- Update DynamoDB devices table
- Daily scheduled retry for devices with unknown/missing manufacturer

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

See [Event Types](event-types.md) for event schemas and the presence model.

**Design Decisions**:
- **On-demand pricing**: Unpredictable traffic patterns
- **TTL enabled**: Automatic cleanup — 90 days for events, 5 minutes for dedup, 1 hour for throttle. The devices table has **no TTL**: identity persists once discovered. An earlier 14-day auto-expiry was removed after being confirmed as a false-positive source — a returning device would re-alert as "new" instead of "back online". The table is tiny (dozens of items), so unbounded storage cost is immaterial.
- **GSI for identity continuity**: `hostname-index` (hash key `hostname`) — sparse, since only devices with a hostname are indexed. Used to detect MAC rotation: when a MAC is unrecognized but its hostname matches an existing device, that device's identity (name, notify flag, first_seen, etc.) is migrated onto the new MAC instead of creating a duplicate "new device". A prior `vlan-index` GSI was removed — it rejected `NULL` on `last_vlan` for WiFi-only events, throwing `ValidationException` on every write for those devices and silently dropping them (confirmed via CloudWatch: 50-79 errors/hour, 15,495 messages stuck in the DLQ). Any GSI on an attribute that can legitimately be absent needs the same care: DynamoDB rejects a write with a `NULL`-typed value on a GSI key attribute, and — as re-discovered live in production right after this GSI's rollout — also rejects a write to an item that already has an explicit `NULL`-typed value stored for that attribute, even if the write never touches it. `update_device_last_seen` now `REMOVE`s a stray legacy `NULL` hostname instead of leaving it in place, self-healing affected devices on their next event.
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
1. Data Collector polls APs + ARP, sees known device (signature unchanged since last send and heartbeat not due → no event sent this poll)
2. On change or heartbeat, Data Collector sends device_activity event to SQS
3. Lambda (event-router) processes event
4. Event-router checks DynamoDB — device found
5. Event-router updates last_seen, last_ip, last_vlan, online_until, mac_type
6. If device was offline for longer than the 30-minute grace period:
   → publishes to notifications topic (back online)
7. Otherwise, no SNS publish — the event is still recorded in the device_events table
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
```

Note: only these two SNS topics exist. A previously-planned `device-activity` topic (for a Loki-based presence timeline) was never built — the Device Presence Timeline dashboard instead reads from InfluxDB, written directly by the data collector on each poll (see Pi-hole/InfluxDB sections above and [Grafana Setup](grafana-setup.md)).

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
- Updated on every activity event (last_seen, last_ip, last_vlan, online_until, mac_type)
- Persists indefinitely — no TTL, identity is never auto-expired
- On a MAC rotation (matched by hostname via `hostname-index`), the existing device's identity is migrated onto the new MAC and the old MAC's item is deleted, rather than creating a duplicate

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
- Publish to SNS (device-discovered, notifications)

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

- **Loki**: All RouterOS syslog via Vector (labels: `job=vector-lmserver`, `source=syslog`); tracked devices' Pi-hole DNS activity via the data collector's Pi-hole client (optional, see above)
- **DHCP Activity dashboard**: Deployed, queries Loki for DHCP assign/deassign events over time

## References

- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)
- [Vector Documentation](https://vector.dev/docs/)
- [MikroTik RouterOS API](https://help.mikrotik.com/docs/display/ROS/API)
- [Apprise Documentation](https://github.com/caronc/apprise)

---

**Last Updated**: 2026-09-18
