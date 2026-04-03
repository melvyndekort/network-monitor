"""Tests for mikrotik module."""

from unittest.mock import MagicMock
from librouteros.exceptions import LibRouterosError
from data_collector import mikrotik


def _mock_api(path_result):
    """Create a mock RouterOS API that returns path_result for any path() call."""
    api = MagicMock()
    api.path.return_value = path_result
    return api


ARP_ROW = {
    "mac-address": "AA:BB:CC:DD:EE:FF",
    "address": "10.204.10.100",
    "interface": "bridge",
    "status": "reachable",
}


def test_get_arp_filters_empty_mac(monkeypatch):
    """Test ARP entries with empty/missing/stale/failed MACs are filtered."""
    client = mikrotik.MikroTikClient("host", "user", "pass")

    def mock_query(*args):
        """Return mock ARP data regardless of path."""
        del args
        return [
            ARP_ROW,
            {
                "mac-address": "00:00:00:00:00:00",
                "address": "10.204.10.1",
                "interface": "bridge",
                "status": "reachable",
            },
            {"address": "10.204.10.2", "interface": "bridge", "status": "reachable"},
            {
                "mac-address": "11:22:33:44:55:66",
                "address": "10.204.10.3",
                "interface": "bridge",
                "status": "stale",
            },
            {
                "mac-address": "22:33:44:55:66:77",
                "address": "10.204.10.4",
                "interface": "bridge",
                "status": "failed",
            },
        ]

    monkeypatch.setattr(client, "_query", mock_query)
    result = client.get_arp()
    assert len(result) == 1
    assert result[0]["mac"] == "AA:BB:CC:DD:EE:FF"


def test_get_arp_empty(monkeypatch):
    """Test empty ARP table returns empty list."""
    client = mikrotik.MikroTikClient("host", "user", "pass")

    def mock_query(*args):
        """Return empty list."""
        del args
        return []

    monkeypatch.setattr(client, "_query", mock_query)
    assert not client.get_arp()


def test_get_dhcp_leases_filters_unbound(monkeypatch):
    """Test DHCP leases filters out non-bound and MAC-less entries."""
    client = mikrotik.MikroTikClient("host", "user", "pass")

    def mock_query(*args):
        """Return mock DHCP data regardless of path."""
        del args
        return [
            {
                "mac-address": "AA:BB:CC:DD:EE:FF",
                "address": "10.204.10.100",
                "host-name": "myhost",
                "status": "bound",
            },
            {
                "mac-address": "11:22:33:44:55:66",
                "address": "10.204.10.101",
                "host-name": "other",
                "status": "waiting",
            },
            {"mac-address": None, "address": "10.204.10.102", "status": "bound"},
        ]

    monkeypatch.setattr(client, "_query", mock_query)
    result = client.get_dhcp_leases()
    assert len(result) == 1
    assert result[0]["mac"] == "AA:BB:CC:DD:EE:FF"
    assert result[0]["hostname"] == "myhost"


def test_get_dhcp_leases_empty(monkeypatch):
    """Test empty DHCP leases returns empty list."""
    client = mikrotik.MikroTikClient("host", "user", "pass")

    def mock_query(*args):
        """Return empty list."""
        del args
        return []

    monkeypatch.setattr(client, "_query", mock_query)
    assert not client.get_dhcp_leases()


def test_query_connects_on_first_call(monkeypatch):
    """Test get_arp connects to router on first call."""
    client = mikrotik.MikroTikClient("host", "user", "pass")
    connected = []

    def mock_connect(**kwargs):
        """Track connection attempts."""
        del kwargs
        connected.append(True)
        return _mock_api([ARP_ROW])

    monkeypatch.setattr(mikrotik, "connect", mock_connect)
    result = client.get_arp()
    assert len(connected) == 1
    assert len(result) == 1


def test_query_reconnects_on_failure(monkeypatch):
    """Test get_arp reconnects when connection is lost."""
    client = mikrotik.MikroTikClient("host", "user", "pass")
    call_count = []

    def mock_connect(**kwargs):
        """Track connection attempts, fail first time."""
        del kwargs
        call_count.append(True)
        api = MagicMock()
        if len(call_count) == 1:
            api.path.side_effect = LibRouterosError("connection lost")
        else:
            api.path.return_value = [ARP_ROW]
        return api

    monkeypatch.setattr(mikrotik, "connect", mock_connect)
    result = client.get_arp()
    assert len(call_count) == 2
    assert len(result) == 1


def test_query_returns_empty_on_connect_failure(monkeypatch):
    """Test get_arp returns empty list when connection fails."""
    client = mikrotik.MikroTikClient("host", "user", "pass")

    def mock_connect(**kwargs):
        """Always fail to connect."""
        del kwargs
        raise LibRouterosError("refused")

    monkeypatch.setattr(mikrotik, "connect", mock_connect)
    result = client.get_arp()
    assert not result
