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

`mac_type` is computed by event-router from the MAC's U/L bit: `vendor` (factory-assigned) or `locally_administered` (randomized — e.g. Android/iOS/ChromeOS privacy MAC features). It's a secondary signal, not a presence/discovery decision on its own — see [MAC Rotation](#mac-rotation--identity-continuity) below.

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

Devices are never auto-expired — identity persists indefinitely once discovered (an earlier 14-day TTL was removed after it caused returning devices to re-alert as "new").

## MAC Rotation / Identity Continuity

Some devices (notably Android, iOS, and ChromeOS with privacy MAC features) rotate their MAC address per network. Without special handling, each rotation would look like a brand-new device to event-router.

When an event's MAC isn't found in DynamoDB but its `hostname` matches an existing device (via the `hostname-index` GSI), event-router treats it as a **rotation**, not a discovery: the existing device's identity (name, notify flag, first_seen, etc.) is migrated onto the new MAC and the old MAC's item is deleted. This only works when a hostname is present and previously known — a rotated device with no hostname match is indistinguishable from a genuinely new device and gets treated as one, with `mac_type: locally_administered` flagged as a higher-priority alert (the actual evasion pattern this guards against).

## Event Routing

```
SQS (device-events.fifo)
  → event-router Lambda
    → SNS device-discovered → notifier, metadata-enricher (new device or MAC rotation)
    → SNS notifications → notifier (new device, MAC rotation, or back-online)
```

Normal (non-transition) activity events are stored to the device_events table but not published to SNS.
