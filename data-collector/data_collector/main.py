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


def build_dhcp_lookup(client):
    """Build mac -> lease dict from DHCP leases."""
    return {lease["mac"].upper(): lease for lease in client.get_dhcp_leases()}


def poll(client, known_macs, sqs_client):
    """Poll ARP + DHCP, send events to SQS, return current MAC set."""
    dhcp = build_dhcp_lookup(client)
    arp = client.get_arp()

    current_macs = set()
    events = []

    for entry in arp:
        mac = entry["mac"].upper()
        ip = entry["ip"]
        current_macs.add(mac)
        hostname = dhcp.get(mac, {}).get("hostname")
        event_type = "device_discovered" if mac not in known_macs else "device_activity"
        events.append(make_event(event_type, mac, ip, hostname))

    # DHCP-only devices not seen in ARP
    for mac, lease in dhcp.items():
        if mac not in current_macs:
            current_macs.add(mac)
            event_type = "device_discovered" if mac not in known_macs else "device_activity"
            events.append(make_event(event_type, mac, lease.get("ip"), lease.get("hostname")))

    if events:
        sqs_client.send_events(events)

    return current_macs


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

    logger.info("Starting data collector (poll every %ds)", POLL_INTERVAL)
    while True:
        try:
            known_macs = poll(client, known_macs, sqs_client)
            logger.info("Poll complete: %d devices", len(known_macs))
        except (LibRouterosError, ConnectionError, OSError):
            logger.exception("Poll failed")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
