"""Data collector - polls MikroTik and OpenWrt APs, sends events to SQS."""

import json
import logging
import os
import sys
import time

from librouteros.exceptions import LibRouterosError

from data_collector.influxdb import create_influxdb_writer
from data_collector.loki import create_loki_writer
from data_collector.mikrotik import MikroTikClient
from data_collector.models import make_event, detect_vlan
from data_collector.openwrt import OpenWrtClient
from data_collector.pihole import PiholeClient
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

    wired_only = arp_macs - set(wireless_macs)
    active_macs = set(wireless_macs) | arp_macs
    logger.info(
        "Discovered %d wireless, %d wired-only, %d total active",
        len(wireless_macs),
        len(wired_only),
        len(active_macs),
    )

    devices = {}
    for mac in active_macs:
        info = enrichment.get(mac, {})
        wifi = wireless_macs.get(mac)
        devices[mac] = {
            "ip": info.get("ip"),
            "hostname": info.get("hostname"),
            "wifi": wifi,
        }
    return devices


def poll(mikrotik, openwrt, send_events, write_presence=None):
    """Poll devices and send all events to SQS."""
    devices = collect_devices(mikrotik, openwrt)
    events = [
        make_event(
            "device_activity",
            mac,
            d["ip"],
            d["hostname"],
            metadata=d.get("wifi") if d.get("wifi") else None,
        )
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


def poll_pihole(pihole_client, write_pihole):
    """Poll Pi-hole for tracked devices and push classified events to Loki."""
    events = pihole_client.poll()
    if events:
        write_pihole(events)
    return len(events)


def build_influxdb_writer():
    """Build a presence writer from env vars, or None if InfluxDB is unconfigured."""
    influxdb_url = os.environ.get("INFLUXDB_URL")
    influxdb_token = os.environ.get("INFLUXDB_TOKEN")
    if not influxdb_url or not influxdb_token:
        return None

    write_presence = create_influxdb_writer(
        influxdb_url,
        influxdb_token,
        os.environ.get("INFLUXDB_ORG", "mdekort"),
        os.environ.get("INFLUXDB_BUCKET", "network-monitor"),
    )
    logger.info("InfluxDB writer enabled: %s", influxdb_url)
    return write_presence


def build_pihole_client():
    """Build (pihole_client, write_pihole) from env vars, or (None, None) if unconfigured."""
    pihole_hosts = [h for h in os.environ.get("PIHOLE_HOSTS", "").split(",") if h]
    loki_password = os.environ.get("LOKI_PASSWORD")
    if not pihole_hosts or not loki_password:
        return None, None

    try:
        tracked_devices = json.loads(os.environ.get("PIHOLE_TRACKED_DEVICES", "{}"))
        pihole_passwords = json.loads(os.environ.get("PIHOLE_API_PASSWORDS", "{}"))
    except ValueError:
        logger.exception(
            "Invalid PIHOLE_TRACKED_DEVICES/PIHOLE_API_PASSWORDS, disabling Pi-hole polling"
        )
        return None, None
    if not tracked_devices or not pihole_passwords:
        return None, None

    pihole_client = PiholeClient(pihole_hosts, tracked_devices, pihole_passwords)
    write_pihole = create_loki_writer(
        os.environ.get("LOKI_URL", "https://logs-prod-eu-west-0.grafana.net"),
        os.environ.get("LOKI_USER", "876553"),
        loki_password,
    )
    logger.info(
        "Pi-hole polling enabled: %d hosts, %d tracked devices",
        len(pihole_hosts),
        len(tracked_devices),
    )
    return pihole_client, write_pihole


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

    write_presence = build_influxdb_writer()
    pihole_client, write_pihole = build_pihole_client()

    logger.info(
        "Starting data collector (poll every %ds, %d APs)", POLL_INTERVAL, len(ap_hosts)
    )
    while True:
        try:
            sent = poll(mikrotik, openwrt, send_events, write_presence)
            logger.info("Poll complete: %d events sent", sent)
        except (LibRouterosError, ConnectionError, OSError):
            logger.exception("Poll failed")

        if pihole_client and write_pihole:
            pihole_sent = poll_pihole(pihole_client, write_pihole)
            logger.info("Pi-hole poll complete: %d events sent", pihole_sent)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
