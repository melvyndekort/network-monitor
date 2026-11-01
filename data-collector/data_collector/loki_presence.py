"""Grafana Cloud Loki writer for device presence data.

Replaces the InfluxDB presence writer. Pushes one log line per active
device per poll, labeled by `job`, `mac`, and `vlan` (mirroring the
per-device label cardinality the Pi-hole writer in loki.py already uses
at this scale). Absence of log lines for a mac within a window implies
offline, same semantics the InfluxDB-based dashboard relied on.
"""

import base64
import json
import logging
import urllib.request

logger = logging.getLogger(__name__)


def create_presence_writer(url, user, password):
    """Create a function that writes device presence points to Loki."""
    push_url = f"{url.rstrip('/')}/loki/api/v1/push"
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()

    def write_presence(devices, timestamp):
        """Write one Loki log line per active device."""
        if not devices:
            return

        ts_ns = str(int(timestamp) * 1_000_000_000)
        streams = []
        for mac, info in devices.items():
            vlan = str(info["vlan"]) if info.get("vlan") else "unknown"
            line = json.dumps(
                {
                    "ip": info.get("ip"),
                    "hostname": info.get("hostname"),
                    "online": True,
                }
            )
            streams.append(
                {
                    "stream": {
                        "job": "device-presence",
                        "mac": mac,
                        "vlan": vlan,
                    },
                    "values": [[ts_ns, line]],
                }
            )

        payload = {"streams": streams}
        req = urllib.request.Request(
            push_url,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {auth}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status not in (200, 204):
                    logger.warning("Loki presence push returned status %d", resp.status)
                else:
                    logger.info("Loki: wrote %d presence points", len(streams))
        except OSError:
            logger.exception("Loki presence push failed")

    return write_presence
