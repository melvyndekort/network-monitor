"""Data collector - polls MikroTik and outputs JSON events to stdout."""
import logging
import os
import sys
import time

from data_collector.mikrotik import MikroTikClient
from data_collector.models import make_event

FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT, stream=sys.stderr)
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))


def build_dhcp_lookup(client):
    """Build mac -> lease dict from DHCP leases."""
    return {lease["mac"].upper(): lease for lease in client.get_dhcp_leases()}


def poll(client, known_macs):
    """Poll ARP + DHCP, emit events to stdout, return current MAC set."""
    dhcp = build_dhcp_lookup(client)
    arp = client.get_arp()

    current_macs = set()
    for entry in arp:
        mac = entry["mac"].upper()
        ip = entry["ip"]
        current_macs.add(mac)

        hostname = dhcp.get(mac, {}).get("hostname")

        if mac not in known_macs:
            print(make_event("device_discovered", mac, ip, hostname), flush=True)
        else:
            print(make_event("device_activity", mac, ip, hostname), flush=True)

    # Emit events for DHCP-only devices not seen in ARP
    for mac, lease in dhcp.items():
        if mac not in current_macs:
            current_macs.add(mac)
            event_type = "device_discovered" if mac not in known_macs else "device_activity"
            print(make_event(event_type, mac, lease.get("ip"), lease.get("hostname")), flush=True)

    return current_macs


def main():
    """Main entry point."""
    host = os.environ.get("MIKROTIK_HOST", "10.204.50.1")
    user = os.environ.get("MIKROTIK_USER", "api-user")
    password = os.environ.get("MIKROTIK_PASSWORD", "")

    if not password:
        logger.error("MIKROTIK_PASSWORD is required")
        sys.exit(1)

    client = MikroTikClient(host, user, password)
    known_macs = set()

    logger.info("Starting data collector (poll every %ds)", POLL_INTERVAL)
    while True:
        try:
            known_macs = poll(client, known_macs)
            logger.info("Poll complete: %d devices", len(known_macs))
        except Exception:
            logger.exception("Poll failed")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
