"""Grafana Cloud Loki writer for Pi-hole DNS query events."""

import base64
import json
import logging
import time
import urllib.request

logger = logging.getLogger(__name__)


def create_loki_writer(url, user, password):
    """Create a function that pushes classified Pi-hole events to Grafana Cloud Loki."""
    push_url = f"{url.rstrip('/')}/loki/api/v1/push"
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()

    def write_events(events):
        """Push a batch of classified Pi-hole events to Loki as labeled streams."""
        if not events:
            return

        streams = {}
        now_ns = str(int(time.time() * 1e9))
        for event in events:
            key = (event["device"], event["result"])
            line = json.dumps(
                {
                    "domain": event.get("domain"),
                    "query_type": event.get("query_type"),
                    "client_ip": event.get("client_ip"),
                    "pihole_instance": event.get("pihole_instance"),
                }
            )
            streams.setdefault(key, []).append([now_ns, line])

        payload = {
            "streams": [
                {
                    "stream": {
                        "job": "pihole-daan",
                        "device": device,
                        "result": result,
                    },
                    "values": values,
                }
                for (device, result), values in streams.items()
            ]
        }
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
                    logger.warning("Loki push returned status %d", resp.status)
        except OSError:
            logger.exception("Loki push failed")

    return write_events
