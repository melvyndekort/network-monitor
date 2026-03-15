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
| `device_discovered` | New MAC address seen for the first time | Data collector sees MAC not in known set |
| `device_activity` | Known device still present on network | Data collector sees MAC already in known set |

### DHCP Events

| Type | Description | Trigger |
|------|-------------|---------|
| `dhcp_assigned` | DHCP lease granted | RouterOS syslog via Vector |
| `dhcp_released` | DHCP lease released | RouterOS syslog via Vector |

### State Events

| Type | Description | Trigger |
|------|-------------|---------|
| `state_changed` | Device state transition | track-presence Lambda detects change |

## State Machine

```
unknown → online (first activity seen)
online → offline (no activity for 15 minutes)
offline → online (activity seen again)
```

## Event Routing

```
SQS (device-events.fifo)
  → event-router Lambda
    → SNS device-discovered → presence-tracker, notifier, metadata-enricher
    → SNS device-activity → presence-tracker
    → SNS device-state-changed → notifier
```
