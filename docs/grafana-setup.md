# Grafana Dashboard Setup

Network Monitor observability data is available in Grafana Cloud Loki. RouterOS syslog (including DHCP events) is forwarded by Vector.

## Prerequisites

- Grafana Cloud account
- Access to the `grafanacloud-mdekort-logs` Loki datasource
- Access to the homelab InfluxDB datasource (via Cloudflare Tunnel + service token)

## Deployed Dashboards

### DHCP Activity (Loki-based)

**UID**: `network-monitor-dhcp`
**Folder**: Network Monitor
**Data source**: Loki (`grafanacloud-logs`)

Visualizes DHCP lease activity from RouterOS syslog. All data flows through Vector to Grafana Cloud Loki with labels `job="vector-lmserver"`, `source="syslog"`.

**Panels**:
- DHCP Events (24h) — total event count (stat)
- Assignments (24h) — assigned events only (stat)
- Deassignments (24h) — deassigned events only (stat)
- Unique MACs (24h) — distinct devices seen (stat)
- DHCP Event Rate — assigned vs deassigned over time (timeseries)
- Events by DHCP Pool — stacked timeseries by `appname` (dhcp-data, dhcp-iot, etc.)
- Top Devices by DHCP Churn — top 10 MACs by event count (bar gauge)
- DHCP Event Log — raw log panel with full details (logs)

**Template variable**: `pool` — multi-select filter by DHCP pool (`appname` label)

**Dashboard JSON**: `examples/grafana-dashboards/dhcp-activity.json`

### Device Presence Timeline (InfluxDB-based)

**UID**: `network-monitor-presence`
**Folder**: Network Monitor
**Data source**: InfluxDB (`cfhzfqe4ywnb4e` — homelab InfluxDB 2.x via Cloudflare Tunnel)

Visualizes device online/offline presence over time. The data-collector writes one `device_presence` point per active device every 60s to the `network-monitor` InfluxDB bucket. Absence of data points implies offline.

**Panels**:
- Online Devices — current count (stat)
- Devices per VLAN (now) — breakdown by VLAN (piechart)
- Total Online Devices Over Time — device count over time (timeseries)
- Device Presence Timeline — per-device online/offline state (state-timeline)
- Currently Online Devices — MAC, VLAN, IP, hostname, last seen (table)

**Template variables**: `vlan`, `mac` — multi-select filters

**Dashboard reference**: `examples/grafana-dashboards/device-presence-timeline.json`

**Architecture**:
```
data-collector (every 60s) → InfluxDB (homelab, network-monitor bucket)
Grafana Cloud → CF Tunnel (influxdb.mdekort.nl) → InfluxDB → Dashboard
```

## Syslog in Loki

All RouterOS syslog is forwarded to Grafana Cloud Loki via Vector with labels:
- `job = "vector-lmserver"`
- `source = "syslog"`

DHCP events have `appname` values like `dhcp-data` (VLAN 10), `dhcp-iot` (VLAN 20), etc.

## Notes

- The data collector polls every 60 seconds, so device data refreshes at that interval
- DynamoDB event history has a 90-day TTL
- `current_state` (online/offline) is computed at read time from `online_until` — it is not stored in DynamoDB
- DHCP events are not presence signals — they indicate lease activity, not device connectivity
