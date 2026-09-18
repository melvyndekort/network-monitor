"""Pi-hole client - poll DNS query events for tracked devices, classify allowed/blocked."""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

BLOCKED_STATUSES = {
    "GRAVITY",
    "GRAVITY_CNAME",
    "DENYLIST",
    "DENYLIST_CNAME",
    "REGEX",
    "REGEX_CNAME",
    "SPECIAL_DOMAIN",
    "EXTERNAL_BLOCKED_IP",
    "EXTERNAL_BLOCKED_NULL",
    "EXTERNAL_BLOCKED_NXRA",
}
ALLOWED_STATUSES = {"FORWARDED", "CACHE", "CACHE_STALE"}


def _login(host, password):
    """Authenticate against a Pi-hole instance, return a session ID or None."""
    url = f"http://{host}/api/auth"
    body = json.dumps({"password": password}).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
    except (OSError, ValueError):
        logger.exception("Pi-hole login failed: %s", host)
        return None
    return data.get("session", {}).get("sid")


def _get(host, path, sid):
    """GET a Pi-hole API endpoint with a session ID. Return (status, json)."""
    url = f"http://{host}/api/{path}"
    req = urllib.request.Request(url, headers={"sid": sid})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except (OSError, ValueError):
        logger.exception("Pi-hole request failed: %s", url)
        return None, None


def classify(status):
    """Classify a Pi-hole query status as 'allowed', 'blocked', or None (skip)."""
    if status in BLOCKED_STATUSES:
        return "blocked"
    if status in ALLOWED_STATUSES:
        return "allowed"
    return None


class PiholeClient:
    """Poll Pi-hole instances for DNS query events belonging to tracked devices."""

    def __init__(self, hosts, devices, passwords):
        """hosts: list of Pi-hole hostnames/IPs to poll.
        devices: dict of {mac: label}, e.g. {"AA:BB:...": "chromebook"}.
        passwords: dict of {host: api_password} for authenticating each instance.
        """
        self.hosts = hosts
        self.devices = {mac.upper(): label for mac, label in devices.items()}
        self.passwords = passwords
        self._cursors = {}
        self._sids = {}

    def _authenticated_get(self, host, path):
        """GET an endpoint, logging in (or re-logging in on an expired session) as needed."""
        sid = self._sids.get(host)
        if not sid:
            sid = _login(host, self.passwords.get(host, ""))
            if not sid:
                return None
            self._sids[host] = sid

        status, data = _get(host, path, sid)
        if status == 401:
            sid = _login(host, self.passwords.get(host, ""))
            if not sid:
                self._sids.pop(host, None)
                return None
            self._sids[host] = sid
            status, data = _get(host, path, sid)

        return data

    def _device_ips(self, host):
        """Return {ip: device_label} for tracked devices' current known IPs."""
        data = self._authenticated_get(host, "network/devices?max_devices=200")
        if not data:
            return {}
        ip_map = {}
        for dev in data.get("devices", []):
            label = self.devices.get(dev.get("hwaddr", "").upper())
            if not label:
                continue
            for entry in dev.get("ips", []):
                ip = entry.get("ip")
                if ip:
                    ip_map[ip] = label
        return ip_map

    def poll_host(self, host):
        """Poll one Pi-hole instance for new queries, return classified events."""
        ip_map = self._device_ips(host)
        if not ip_map:
            return []

        endpoint = "queries?length=500"
        cursor = self._cursors.get(host)
        if cursor:
            endpoint += f"&cursor={cursor}"
        data = self._authenticated_get(host, endpoint)
        if not data:
            return []

        new_cursor = data.get("cursor")
        if new_cursor:
            self._cursors[host] = new_cursor

        events = []
        for query in data.get("queries", []):
            client_ip = query.get("client", {}).get("ip")
            device = ip_map.get(client_ip)
            if not device:
                continue
            result = classify(query.get("status"))
            if not result:
                continue
            events.append(
                {
                    "device": device,
                    "result": result,
                    "domain": query.get("domain"),
                    "query_type": query.get("type"),
                    "client_ip": client_ip,
                    "pihole_instance": host,
                }
            )
        return events

    def poll(self):
        """Poll all configured Pi-hole hosts, return combined classified events."""
        events = []
        for host in self.hosts:
            try:
                events.extend(self.poll_host(host))
            except (OSError, ValueError):
                logger.exception("Pi-hole poll failed for %s", host)
        return events
