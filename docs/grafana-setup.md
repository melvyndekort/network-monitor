# Grafana Dashboard Setup

Network Monitor data lives in DynamoDB. To visualize it in Grafana Cloud, use the Infinity data source plugin to query the public API.

## Prerequisites

- Grafana Cloud account (or self-hosted Grafana)
- Infinity data source plugin installed

## Data Source Configuration

1. Install the **Infinity** plugin in Grafana
2. Add a new Infinity data source
3. Set the base URL to: `https://ys7ivwcdqf.execute-api.eu-west-1.amazonaws.com`

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

## Notes

- The API auto-refreshes data every 30 seconds from the data collector
- DynamoDB event history has a 90-day TTL
- Syslog data is also available in Grafana Cloud Loki (via Vector)
