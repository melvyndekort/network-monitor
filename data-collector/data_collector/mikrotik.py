"""MikroTik RouterOS API client."""
import logging
from librouteros import connect
from librouteros.exceptions import LibRouterosError

logger = logging.getLogger(__name__)


class MikroTikClient:
    """Wrapper around librouteros for querying ARP and DHCP data."""

    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password
        self._api = None

    def _connect(self):
        try:
            self._api = connect(host=self.host, username=self.username, password=self.password)
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
        Excludes stale and failed entries.
        """
        active_statuses = {"reachable", "delay", "permanent"}
        entries = []
        for row in self._query("ip", "arp"):
            mac = row.get("mac-address")
            if not mac or mac == "00:00:00:00:00:00":
                continue
            if row.get("status") not in active_statuses:
                continue
            entries.append({
                "mac": mac,
                "ip": row.get("address"),
                "interface": row.get("interface"),
            })
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
            entries.append({
                "mac": mac,
                "ip": row.get("address"),
                "hostname": row.get("host-name"),
            })
        return entries
