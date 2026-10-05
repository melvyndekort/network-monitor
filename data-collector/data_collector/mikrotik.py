"""MikroTik RouterOS API client."""

import logging
from librouteros import connect
from librouteros.exceptions import LibRouterosError

logger = logging.getLogger(__name__)

# Interface name prefixes that sit on the WAN side of the router (ISP-facing
# VLANs/links such as IPTV or the PPPoE WAN session), not on a home VLAN.
# ARP learned on these carries the ISP's own private addressing (e.g. IPTV
# headend equipment on 10.180.176.0/24) and must never be reported as a
# device on the home network.
WAN_INTERFACE_PREFIXES = ("wan", "pppoe", "ether1")


def _is_wan_interface(interface):
    """True if `interface` is a WAN-side interface, not a home LAN/VLAN."""
    if not interface:
        return False
    return interface.startswith(WAN_INTERFACE_PREFIXES)


class MikroTikClient:
    """Wrapper around librouteros for querying ARP and DHCP data."""

    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password
        self._api = None

    def _connect(self):
        try:
            self._api = connect(
                host=self.host, username=self.username, password=self.password
            )
        except LibRouterosError:
            logger.exception("Failed to connect to %s", self.host)
            self._api = None

    def _query(self, *path):
        if self._api is None:
            self._connect()
        if self._api is None:
            return []
        try:
            return list(self._api.path(*path))
        except (LibRouterosError, ConnectionError):
            logger.warning("Connection lost, reconnecting")
            self._api = None
            self._connect()
            if self._api is None:
                return []
            try:
                return list(self._api.path(*path))
            except LibRouterosError:
                logger.exception("Query failed after reconnect")
                return []

    def get_arp(self):
        """Return ARP table entries as list of dicts with mac, ip, interface.

        Only includes entries with active statuses (reachable, delay, permanent).
        Excludes stale and failed entries, and excludes entries learned on a
        WAN-side interface (e.g. the ISP's IPTV VLAN) - those carry the ISP's
        own private addressing, not a device on the home network.
        """
        active_statuses = {"reachable", "delay", "permanent"}
        entries = []
        for row in self._query("ip", "arp"):
            mac = row.get("mac-address")
            if not mac or mac == "00:00:00:00:00:00":
                continue
            if row.get("status") not in active_statuses:
                continue
            if _is_wan_interface(row.get("interface")):
                logger.debug(
                    "Skipping WAN-side ARP entry %s on %s", mac, row.get("interface")
                )
                continue
            entries.append(
                {
                    "mac": mac,
                    "ip": row.get("address"),
                    "interface": row.get("interface"),
                }
            )
        return entries

    def get_dhcp_leases(self):
        """Return active DHCP leases as list of dicts with mac, ip, hostname."""
        entries = []
        for row in self._query("ip", "dhcp-server", "lease"):
            if row.get("status") != "bound":
                continue
            mac = row.get("mac-address")
            if not mac:
                continue
            entries.append(
                {
                    "mac": mac,
                    "ip": row.get("address"),
                    "hostname": row.get("host-name"),
                }
            )
        return entries
