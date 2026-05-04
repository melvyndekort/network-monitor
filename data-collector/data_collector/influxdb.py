"""InfluxDB client for writing device presence data."""

import logging

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException

logger = logging.getLogger(__name__)


def create_influxdb_writer(url, token, org, bucket):
    """Create a function that writes device presence points to InfluxDB."""
    client = InfluxDBClient(url=url, token=token, org=org)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    def write_presence(devices, timestamp):
        """Write one point per active device."""
        if not devices:
            return

        points = []
        for mac, info in devices.items():
            point = (
                Point("device_presence")
                .tag("mac", mac)
                .field("online", 1)
                .time(timestamp, WritePrecision.S)
            )
            if info.get("vlan"):
                point = point.tag("vlan", str(info["vlan"]))
            if info.get("ip"):
                point = point.field("ip", info["ip"])
            if info.get("hostname"):
                point = point.field("hostname", info["hostname"])
            points.append(point)

        try:
            write_api.write(bucket=bucket, record=points)
            logger.info("InfluxDB: wrote %d presence points", len(points))
        except (ApiException, OSError):
            logger.exception("InfluxDB write error")

    return write_presence
