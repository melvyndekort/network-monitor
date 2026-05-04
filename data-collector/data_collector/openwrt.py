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
        """Return dict of {MAC: client_info} for all associated clients."""
        macs = {}
        for host in self.hosts:
            try:
                ap_clients = self.query_ap(host)
                logger.info("AP %s: %d clients", host, len(ap_clients))
                macs.update(ap_clients)
            except (OSError, ValueError, KeyError):
                logger.exception("Failed to query AP %s", host)
        return macs

    def query_ap(self, host):
        """Login to a single AP and return dict of {MAC: client_info}."""
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
        clients = {}
        for iface in ifaces["result"]:
            if not iface.startswith("hostapd."):
                continue
            r = _rpc(host, "call", [session, iface, "get_clients", {}])
            band = _detect_band(iface)
            for mac, info in r["result"][1].get("clients", {}).items():
                clients[mac.upper()] = {
                    "ap": host,
                    "band": band,
                    "signal": info.get("signal"),
                    "connected_time": info.get("connected_time"),
                }
        return clients


def _detect_band(iface):
    """Detect WiFi band from interface name (wl0=2.4GHz, wl1=5GHz)."""
    if "wl1" in iface:
        return "5GHz"
    if "wl0" in iface:
        return "2.4GHz"
    return None
