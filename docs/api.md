# API Reference

Base URL: `https://ys7ivwcdqf.execute-api.eu-west-1.amazonaws.com`

## Authentication

- `GET` routes are public (no auth required)
- `PUT` and `DELETE` routes require AWS IAM (SigV4) authentication

## Endpoints

### List Devices

```
GET /devices
```

Returns all tracked devices.

**Response:**
```json
{
  "devices": [
    {
      "mac": "AA:BB:CC:DD:EE:FF",
      "name": null,
      "manufacturer": "Google, Inc.",
      "hostname": "Google-Home-Mini",
      "device_type": null,
      "last_ip": "10.204.10.193",
      "last_vlan": 10,
      "current_state": "online",
      "notify": true,
      "first_seen": 1773588353,
      "last_seen": 1773588377,
      "last_online": 1773588355
    }
  ]
}
```

### Get Device

```
GET /devices/{mac}
```

Returns a single device by MAC address.

### Update Device

```
PUT /devices/{mac}
```

**Requires IAM auth.** Updates allowed fields: `name`, `notify`, `device_type`.

```json
{
  "name": "Living Room Speaker",
  "notify": false
}
```

### Delete Device

```
DELETE /devices/{mac}
```

**Requires IAM auth.** Removes a device from tracking.

### Get Device History

```
GET /devices/{mac}/history
```

Returns event history for a device.

### Get Stats

```
GET /stats
```

Returns network-wide statistics.

### Get VLAN Stats

```
GET /stats/vlan/{vlan_id}
```

Returns statistics for a specific VLAN.
