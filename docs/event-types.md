# Event Types

Events flow through the system as JSON objects with a common schema.

## Common Schema

```json
{
  "timestamp": "2026-03-15T15:25:44.993445+00:00",
  "source": "data_collector",
  "event_type": "device_discovered",
  "mac": "AA:BB:CC:DD:EE:FF",
  "ip": "10.204.10.100",
  "hostname": "my-device",
  "vlan": 10,
  "metadata": {}
}
```

## Sources

| Source | Description |
|--------|-------------|
| `data_collector` | ARP/DHCP polling from MikroTik |
| `syslog_dhcp` | DHCP events from RouterOS syslog via Vector |
| `manual_test` | Manual test events sent directly to SQS |

## Event Types

### Discovery Events

| Type | Description | Trigger |
|------|-------------|---------|
| `device_discovered` | New MAC address seen for the first time | Data collector sees MAC not in known set (ARP or DHCP) |
| `device_activity` | Known device still present on network | Data collector sees MAC already in known set (ARP or DHCP) |

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

## Event Routing

```
SQS (device-events.fifo)
  → event-router Lambda
    → SNS device-discovered → notifier, metadata-enricher
    → SNS device-activity
```
