"""InfluxDB client for writing device presence data."""

import logging

import urllib3

logger = logging.getLogger(__name__)


def create_influxdb_writer(url, token, org, bucket):
    """Create a function that writes device presence points to InfluxDB."""
    http = urllib3.PoolManager()
    write_url = f"{url}/api/v2/write?org={org}&bucket={bucket}&precision=s"
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "text/plain",
    }

    def write_presence(devices, timestamp):
        """Write one point per active device in line protocol format."""
        lines = []
        for mac, info in devices.items():
            tags = f"mac={mac}"
            if info.get("vlan"):
                tags += f",vlan={info['vlan']}"
            fields = "online=1i"
            if info.get("ip"):
                fields += f',ip="{info["ip"]}"'
            if info.get("hostname"):
                fields += f',hostname="{info["hostname"]}"'
            lines.append(f"device_presence,{tags} {fields} {timestamp}")

        if not lines:
            return

        body = "\n".join(lines)
        try:
            resp = http.request("POST", write_url, body=body.encode(), headers=headers)
            if resp.status != 204:
                logger.error(
                    "InfluxDB write failed: %s %s", resp.status, resp.data.decode()
                )
            else:
                logger.info("InfluxDB: wrote %d presence points", len(lines))
        except urllib3.exceptions.HTTPError:
            logger.exception("InfluxDB write error")

    return write_presence
