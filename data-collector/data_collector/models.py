"""Event models matching the event-router Lambda schema."""

from datetime import datetime, timezone

VLAN_MAP = {
    "10.204.10.": 10,
    "10.204.20.": 20,
    "10.204.30.": 30,
    "10.204.40.": 40,
    "10.204.50.": 50,
}


def detect_vlan(ip):
    """Detect VLAN ID from IP address prefix."""
    if not ip:
        return None
    for prefix, vlan in VLAN_MAP.items():
        if ip.startswith(prefix):
            return vlan
    return None


def make_event(event_type, mac, ip=None, hostname=None, *, metadata=None):
    """Create event dict matching event-router normalize_event() schema."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "data_collector",
        "event_type": event_type,
        "mac": mac.upper(),
        "ip": ip,
        "hostname": hostname,
        "vlan": detect_vlan(ip),
        "metadata": metadata or {},
    }
