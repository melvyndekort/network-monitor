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
      "mac_type": "vendor",
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

Removes a device from tracking. This is the **only** way a device record is ever deleted — the system never deletes or merges a record automatically.

## Notes

- `current_state` is computed at read time from `online_until` — it is not stored in DynamoDB
- `mac_type` is `vendor` or `locally_administered` (randomized MAC), computed from the MAC's U/L bit
- Identity is keyed solely on MAC address. Devices persist indefinitely — no auto-expiry, no automatic deletion or merging. A MAC rotation (e.g. Android/iOS privacy MACs) always creates a brand-new device record, by design — see [Identity Model](event-types.md#identity-model)
- The API is served via CloudFront → Lambda function URL (OAC with SigV4)
