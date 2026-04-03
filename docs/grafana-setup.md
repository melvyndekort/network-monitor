# Grafana Dashboard Setup

Network Monitor observability data is available in Grafana Cloud Loki. RouterOS syslog (including DHCP events) is forwarded by Vector.

## Prerequisites

- Grafana Cloud account
- Access to the `grafanacloud-mdekort-logs` Loki datasource

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
