"""OpenWrt AP client - query associated wireless clients via ubus HTTP JSON-RPC."""

import json
import logging
import urllib.request

logger = logging.getLogger(__name__)


def _rpc(host, method, params):
    """Make a ubus JSON-RPC call."""
    data = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode()
    req = urllib.request.Request(
        f"http://{host}/ubus", data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


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
                ap_macs = self.query_ap(host)
                logger.info("AP %s: %d clients", host, len(ap_macs))
                macs.update(ap_macs)
            except (OSError, ValueError, KeyError):
                logger.exception("Failed to query AP %s", host)
        return macs

    def query_ap(self, host):
        """Login to a single AP and return set of associated MACs."""
        resp = _rpc(
            host,
            "call",
            [
                "00000000000000000000000000000000",
                "session",
                "login",
                {"username": self.username, "password": self.password},
            ],
        )
        session = resp["result"][1]["ubus_rpc_session"]

        ifaces = _rpc(host, "list", [session, "hostapd.*"])
        macs = set()
        for iface in ifaces["result"]:
            if not iface.startswith("hostapd."):
                continue
            r = _rpc(host, "call", [session, iface, "get_clients", {}])
            for mac in r["result"][1].get("clients", {}):
                macs.add(mac.upper())
        return macs
