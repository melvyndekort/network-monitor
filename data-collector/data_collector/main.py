"""Data collector - polls MikroTik and OpenWrt APs, sends events to SQS."""

import logging
import os
import sys
import time

from librouteros.exceptions import LibRouterosError

from data_collector.influxdb import create_influxdb_writer
from data_collector.mikrotik import MikroTikClient
from data_collector.models import make_event, detect_vlan
from data_collector.openwrt import OpenWrtClient
from data_collector.sqs import create_sqs_client

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT, stream=sys.stderr)
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))


def build_enrichment_lookup(client):
    """Build mac -> {ip, hostname} from ARP + DHCP for enrichment."""
    return build_enrichment_lookup_from(client.get_arp(), client.get_dhcp_leases())


def build_enrichment_lookup_from(arp_entries, dhcp_leases):
    """Build mac -> {ip, hostname} from pre-fetched ARP + DHCP data."""
    dhcp = {lease["mac"].upper(): lease for lease in dhcp_leases}
    lookup = {}
    for entry in arp_entries:
        mac = entry["mac"].upper()
        lookup[mac] = {"ip": entry["ip"], "hostname": dhcp.get(mac, {}).get("hostname")}
    for mac, lease in dhcp.items():
        if mac not in lookup:
            lookup[mac] = {"ip": lease.get("ip"), "hostname": lease.get("hostname")}
    return lookup


def collect_devices(mikrotik, openwrt):
    """Collect active devices using AP associations as presence, ARP+DHCP for enrichment.

    A device is considered present only if it is associated to an AP
    or has a non-stale ARP entry (wired devices). DHCP leases are
    used solely for IP/hostname enrichment.
    """
    wireless_macs = openwrt.get_associated_macs()
    arp_entries = mikrotik.get_arp()
    arp_macs = {e["mac"].upper() for e in arp_entries}
    dhcp_leases = mikrotik.get_dhcp_leases()
    logger.info(
        "MikroTik: %d ARP entries, %d DHCP leases", len(arp_entries), len(dhcp_leases)
    )

    enrichment = build_enrichment_lookup_from(arp_entries, dhcp_leases)

    wired_only = arp_macs - wireless_macs
    active_macs = wireless_macs | arp_macs
    logger.info(
        "Discovered %d wireless, %d wired-only, %d total active",
        len(wireless_macs),
        len(wired_only),
        len(active_macs),
    )

    devices = {}
    for mac in active_macs:
        info = enrichment.get(mac, {})
        devices[mac] = {"ip": info.get("ip"), "hostname": info.get("hostname")}
    return devices


def poll(mikrotik, openwrt, send_events, write_presence=None):
    """Poll devices and send all events to SQS."""
    devices = collect_devices(mikrotik, openwrt)
    events = [
        make_event("device_activity", mac, d["ip"], d["hostname"])
        for mac, d in devices.items()
    ]
    if events:
        send_events(events)
    if write_presence and devices:
        enriched = {
            mac: {
                "ip": d["ip"],
                "hostname": d["hostname"],
                "vlan": detect_vlan(d["ip"]),
            }
            for mac, d in devices.items()
        }
        write_presence(enriched, int(time.time()))
    return len(events)


def main():
    """Main entry point."""
    host = os.environ.get("MIKROTIK_HOST", "10.204.50.1")
    user = os.environ.get("MIKROTIK_USER", "api-user")
    password = os.environ.get("MIKROTIK_PASSWORD", "")
    queue_url = os.environ.get("SQS_QUEUE_URL", "")
    ap_hosts = os.environ.get("AP_HOSTS", "").split(",")
    ap_user = os.environ.get("AP_USER", "netmon")
    ap_password = os.environ.get("AP_PASSWORD", "")

    if not password:
        logger.error("MIKROTIK_PASSWORD is required")
        sys.exit(1)
    if not queue_url:
        logger.error("SQS_QUEUE_URL is required")
        sys.exit(1)
    if not ap_hosts or not ap_hosts[0]:
        logger.error("AP_HOSTS is required")
        sys.exit(1)
    if not ap_password:
        logger.error("AP_PASSWORD is required")
        sys.exit(1)

    mikrotik = MikroTikClient(host, user, password)
    openwrt = OpenWrtClient(ap_hosts, ap_user, ap_password)
    send_events = create_sqs_client(
        queue_url, region=os.environ.get("AWS_REGION", "eu-west-1")
    )

    write_presence = None
    influxdb_url = os.environ.get("INFLUXDB_URL")
    influxdb_token = os.environ.get("INFLUXDB_TOKEN")
    if influxdb_url and influxdb_token:
        write_presence = create_influxdb_writer(
            influxdb_url,
            influxdb_token,
            os.environ.get("INFLUXDB_ORG", "mdekort"),
            os.environ.get("INFLUXDB_BUCKET", "network-monitor"),
        )
        logger.info("InfluxDB writer enabled: %s", influxdb_url)

    logger.info(
        "Starting data collector (poll every %ds, %d APs)", POLL_INTERVAL, len(ap_hosts)
    )
    while True:
        try:
            sent = poll(mikrotik, openwrt, send_events, write_presence)
            logger.info("Poll complete: %d events sent", sent)
        except (LibRouterosError, ConnectionError, OSError):
            logger.exception("Poll failed")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
