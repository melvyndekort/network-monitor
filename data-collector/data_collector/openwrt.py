"""OpenWrt AP client - query associated wireless clients via ubus HTTP JSON-RPC."""
import json
import logging
import urllib.request

logger = logging.getLogger(__name__)


class OpenWrtClient:
    """Query associated wireless clients from OpenWrt APs via ubus HTTP."""

    def __init__(self, hosts, username="netmon", password=""):
        self.hosts = hosts
        self.username = username
        self.password = password

    def get_associated_macs(self):
        """Return set of MAC addresses associated across all APs."""
        macs = set()
        for host in self.hosts:
            try:
                macs.update(self._query_ap(host))
            except Exception:
                logger.exception("Failed to query AP %s", host)
        return macs

    def _rpc(self, host, method, params):
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(f"http://{host}/ubus", data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def _query_ap(self, host):
        """Login to AP and return set of associated MACs."""
        resp = self._rpc(host, "call", [
            "00000000000000000000000000000000", "session", "login",
            {"username": self.username, "password": self.password},
        ])
        session = resp["result"][1]["ubus_rpc_session"]

        ifaces = self._rpc(host, "list", [session, "hostapd.*"])
        macs = set()
        for iface in ifaces["result"]:
            if not iface.startswith("hostapd."):
                continue
            r = self._rpc(host, "call", [session, iface, "get_clients", {}])
            for mac in r["result"][1].get("clients", {}):
                macs.add(mac.upper())
        return macs
