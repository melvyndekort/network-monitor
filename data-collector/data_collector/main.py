"""Data collector - polls MikroTik and sends events to SQS."""
import logging
import os
import sys
import time

from librouteros.exceptions import LibRouterosError

from data_collector.mikrotik import MikroTikClient
from data_collector.models import make_event
from data_collector.sqs import SQSClient

FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT, stream=sys.stderr)
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))
HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "300"))


def build_dhcp_lookup(client):
    """Build mac -> lease dict from DHCP leases."""
    return {lease["mac"].upper(): lease for lease in client.get_dhcp_leases()}


def collect_devices(client):
    """Poll ARP + DHCP, return dict of mac -> {ip, hostname}."""
    dhcp = build_dhcp_lookup(client)
    arp = client.get_arp()

    devices = {}
    for entry in arp:
        mac = entry["mac"].upper()
        devices[mac] = {
            "ip": entry["ip"],
            "hostname": dhcp.get(mac, {}).get("hostname"),
        }

    for mac, lease in dhcp.items():
        if mac not in devices:
            devices[mac] = {
                "ip": lease.get("ip"),
                "hostname": lease.get("hostname"),
            }

    return devices


def poll(devices, known_macs, sqs_client, heartbeat):
    """Send discovery events for new MACs. On heartbeat, send activity for all."""
    events = []

    new_macs = set(devices) - known_macs
    for mac in new_macs:
        d = devices[mac]
        events.append(make_event("device_discovered", mac, d["ip"], d["hostname"]))

    if heartbeat:
        for mac in set(devices) - new_macs:
            d = devices[mac]
            events.append(make_event("device_activity", mac, d["ip"], d["hostname"]))

    if events:
        sqs_client.send_events(events)

    return set(devices), len(events)


def main():
    """Main entry point."""
    host = os.environ.get("MIKROTIK_HOST", "10.204.50.1")
    user = os.environ.get("MIKROTIK_USER", "api-user")
    password = os.environ.get("MIKROTIK_PASSWORD", "")
    queue_url = os.environ.get("SQS_QUEUE_URL", "")

    if not password:
        logger.error("MIKROTIK_PASSWORD is required")
        sys.exit(1)
    if not queue_url:
        logger.error("SQS_QUEUE_URL is required")
        sys.exit(1)

    client = MikroTikClient(host, user, password)
    sqs_client = SQSClient(queue_url, region=os.environ.get("AWS_REGION", "eu-west-1"))
    known_macs = set()
    last_heartbeat = 0

    logger.info("Starting data collector (poll every %ds, heartbeat every %ds)", POLL_INTERVAL, HEARTBEAT_INTERVAL)
    while True:
        try:
            now = time.monotonic()
            heartbeat = (now - last_heartbeat) >= HEARTBEAT_INTERVAL
            devices = collect_devices(client)
            known_macs, sent = poll(devices, known_macs, sqs_client, heartbeat)
            if heartbeat:
                last_heartbeat = now
            logger.info("Poll complete: %d devices, %d events sent%s", len(known_macs), sent, " (heartbeat)" if heartbeat else "")
        except (LibRouterosError, ConnectionError, OSError):
            logger.exception("Poll failed")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
