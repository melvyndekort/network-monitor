# Event Types

Events flow through the system as JSON objects with a common schema.

## Common Schema

```json
{
  "timestamp": "2026-03-15T15:25:44.993445+00:00",
  "source": "data_collector",
  "event_type": "device_discovered",
  "mac": "AA:BB:CC:DD:EE:FF",
  "mac_type": "vendor",
  "ip": "10.204.10.100",
  "hostname": "my-device",
  "vlan": 10,
  "metadata": {}
}
```

`mac_type` is computed by event-router from the MAC's U/L bit: `vendor` (factory-assigned) or `locally_administered` (randomized — e.g. Android/iOS/ChromeOS privacy MAC features). A device entering the network on a `locally_administered` MAC triggers a distinct, higher-priority discovery alert — see [Identity Model](#identity-model) below.

## Sources

| Source | Description |
|--------|-------------|
| `data_collector` | Wireless AP polling + MikroTik ARP (enriched with DHCP) |
| `syslog_dhcp` | DHCP events from RouterOS syslog via Vector |
| `manual_test` | Manual test events sent directly to SQS |

## Event Types

### Discovery Events

| Type | Description | Trigger |
|------|-------------|---------|
| `device_discovered` | New MAC address seen for the first time | Event-router Lambda finds MAC not in DynamoDB |
| `device_activity` | Device present on network | Data collector sees MAC via AP wireless association or ARP table |

### DHCP Events

| Type | Description | Trigger |
|------|-------------|---------|
| `dhcp_assigned` | DHCP lease granted | RouterOS syslog via Vector |
| `dhcp_released` | DHCP lease released | RouterOS syslog via Vector |

### State Events

| Type | Description | Trigger |
|------|-------------|---------|
| *(none — state is derived)* | Online/offline is computed from `online_until` at read time | No event needed |

## Presence Model

Devices have an `online_until` timestamp that is refreshed on every activity event:

```
online_until = now + 900 (15 minutes)
```

A device is **online** if `online_until > now`, otherwise **offline**. No state machine, no state change events.

Devices are never auto-expired, and are never auto-deleted or merged with another record for any reason — see [Identity Model](#identity-model).

## Identity Model

**Identity is keyed solely on MAC address.** Every MAC address that has ever been seen gets exactly one permanent device record, created the first time it appears and never deleted automatically — the only way a record disappears is a manual `DELETE /devices/{mac}` from the UI/API. `name` and `hostname` are purely human-facing labels for telling physical devices apart; they are never used to look up, merge, or migrate a device's identity onto a different MAC.

This is a deliberate design choice, not an oversight: catching a new or randomized MAC address entering the network is the entire point of this system. Some devices (notably Android, iOS, and ChromeOS with privacy MAC features) rotate their MAC address per network — each rotation is, by design, treated as a **brand-new device**, exactly like any other previously-unseen MAC:

- `event_type: device_discovered` fires whenever a MAC isn't found in DynamoDB, with no exceptions for a hostname that happens to match an existing record.
- `mac_type: locally_administered` (the U/L bit set — i.e. a randomized MAC) on a newly-discovered device is flagged with a distinct, higher-priority "🚨 Unrecognized Device (Randomized MAC)" alert instead of the ordinary "🆕 New Device Detected" one, since this is the specific evasion pattern the system watches for.
- A hostname shared by multiple MACs (e.g. several devices from the same vendor all reporting a generic default hostname like `wlan0`) is expected and does **not** cause any merging — each MAC keeps its own separate record. Rename records individually via the UI if you want to tell them apart.

An earlier version of event-router tried to be "smart" about this: it looked up devices by hostname (`hostname-index` GSI) and, on a hostname match for an unrecognized MAC, copied the old record's name/settings onto the new MAC and **deleted the old MAC's record** (`migrate_device`). This was removed (2026-10-03) because it directly undermined the system's purpose — it silently merged and deleted device history whenever a hostname matched, which is the opposite of "alert me when a new or randomized MAC shows up." It also shipped with a missing IAM permission (`dynamodb:DeleteItem` was never granted to event-router), so in practice it only ever created duplicate, never-cleaned-up device records instead of actually merging them — a symptom that surfaced as "deleted and recreated" devices and prompted this redesign.

## Event Routing

```
SQS (device-events.fifo)
  → event-router Lambda
    → direct invoke → enrich-metadata (new device only)
    → direct invoke → send-notifications (new device or back-online)
```

Normal (non-transition) activity events are stored to the device_events table but no invoke is made.
