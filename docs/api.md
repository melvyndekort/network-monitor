# API Reference

Base URL: `https://network-monitor.mdekort.nl/api`

## Authentication

All routes require CloudFront signed cookies (Cognito login at `auth.mdekort.nl`).

## Endpoints

### List Devices

```
GET /api/devices
```

Returns all tracked devices with computed online/offline status.

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
      "online_until": 1773589277,
      "ttl": 1774798177,
      "metadata": {}
    }
  ]
}
```

### Get Device

```
GET /api/devices/{mac}
```

Returns a single device by MAC address with computed online/offline status.

### Update Device

```
PUT /api/devices/{mac}
```

Updates allowed fields: `name`, `notify`, `device_type`.

```json
{
  "name": "Living Room Speaker",
  "notify": false
}
```

### Delete Device

```
DELETE /api/devices/{mac}
```

Removes a device from tracking.

## Notes

- `current_state` is computed at read time from `online_until` — it is not stored in DynamoDB
- Devices auto-expire after 14 days of inactivity via DynamoDB TTL
- The API is served via CloudFront → Lambda function URL (OAC with SigV4)
