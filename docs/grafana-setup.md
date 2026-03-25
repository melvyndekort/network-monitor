# Grafana Dashboard Setup

Network Monitor data lives in DynamoDB. To visualize it in Grafana Cloud, use the Infinity data source plugin to query the REST API. Syslog data is available in Grafana Cloud Loki via Vector.

## Prerequisites

- Grafana Cloud account (or self-hosted Grafana)
- Infinity data source plugin installed

## Data Source Configuration

1. Install the **Infinity** plugin in Grafana
2. Add a new Infinity data source
3. Set the base URL to: `https://network-monitor.mdekort.nl/api`
4. Configure authentication (CloudFront signed cookies required)

## Dashboard Ideas

### Network Overview
- Total devices (stat panel)
- Online vs offline (pie chart)
- Devices per VLAN (bar chart)
- New devices today (stat panel)

### Device Table
- URL: `/devices`
- Parser: JSON
- Root selector: `devices`
- Columns: mac, name, manufacturer, last_ip, current_state, last_vlan, last_seen, online_until

### VLAN Breakdown
- One row per VLAN using `/devices` filtered by `last_vlan`

## Syslog in Loki

All RouterOS syslog is forwarded to Grafana Cloud Loki via Vector with labels:
- `job = "vector-lmserver"`
- `source = "syslog"`

## Notes

- The data collector polls every 60 seconds, so device data refreshes at that interval
- DynamoDB event history has a 90-day TTL
- `current_state` is computed at read time from `online_until`
