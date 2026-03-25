"""Data collector - polls MikroTik and sends events to SQS."""
import logging
import os
import sys
import time

from librouteros.exceptions import LibRouterosError

from data_collector.mikrotik import MikroTikClient
from data_collector.models import make_event
from data_collector.sqs import create_sqs_client

FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT, stream=sys.stderr)
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))


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


def poll(client, send_events):
    """Poll devices and send all events to SQS."""
    devices = collect_devices(client)
    events = [
        make_event("device_activity", mac, d["ip"], d["hostname"])
        for mac, d in devices.items()
    ]
    if events:
        send_events(events)
    return len(events)


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
    send_events = create_sqs_client(queue_url, region=os.environ.get("AWS_REGION", "eu-west-1"))

    logger.info("Starting data collector (poll every %ds)", POLL_INTERVAL)
    while True:
        try:
            sent = poll(client, send_events)
            logger.info("Poll complete: %d events sent", sent)
        except (LibRouterosError, ConnectionError, OSError):
            logger.exception("Poll failed")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
