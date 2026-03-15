"""Tests for mikrotik module."""
import pytest
from librouteros.exceptions import LibRouterosError
from data_collector import mikrotik


def test_get_arp_filters_empty_mac(monkeypatch):
    client = mikrotik.MikroTikClient("host", "user", "pass")

    def mock_query(*path):
        return [
            {"mac-address": "AA:BB:CC:DD:EE:FF", "address": "10.204.10.100", "interface": "bridge"},
            {"mac-address": "00:00:00:00:00:00", "address": "10.204.10.1", "interface": "bridge"},
            {"address": "10.204.10.2", "interface": "bridge"},
        ]

    monkeypatch.setattr(client, "_query", mock_query)
    result = client.get_arp()
    assert len(result) == 1
    assert result[0]["mac"] == "AA:BB:CC:DD:EE:FF"
    assert result[0]["ip"] == "10.204.10.100"
    assert result[0]["interface"] == "bridge"


def test_get_arp_empty(monkeypatch):
    client = mikrotik.MikroTikClient("host", "user", "pass")
    monkeypatch.setattr(client, "_query", lambda *p: [])
    assert client.get_arp() == []


def test_get_dhcp_leases_filters_unbound(monkeypatch):
    client = mikrotik.MikroTikClient("host", "user", "pass")

    def mock_query(*path):
        return [
            {"mac-address": "AA:BB:CC:DD:EE:FF", "address": "10.204.10.100", "host-name": "myhost", "status": "bound"},
            {"mac-address": "11:22:33:44:55:66", "address": "10.204.10.101", "host-name": "other", "status": "waiting"},
            {"mac-address": None, "address": "10.204.10.102", "status": "bound"},
        ]

    monkeypatch.setattr(client, "_query", mock_query)
    result = client.get_dhcp_leases()
    assert len(result) == 1
    assert result[0]["mac"] == "AA:BB:CC:DD:EE:FF"
    assert result[0]["hostname"] == "myhost"


def test_get_dhcp_leases_empty(monkeypatch):
    client = mikrotik.MikroTikClient("host", "user", "pass")
    monkeypatch.setattr(client, "_query", lambda *p: [])
    assert client.get_dhcp_leases() == []


def test_query_connects_on_first_call(monkeypatch):
    client = mikrotik.MikroTikClient("host", "user", "pass")
    connected = []

    class MockApi:
        def path(self, *args):
            return [{"result": "ok"}]

    def mock_connect(host, username, password):
        connected.append(True)
        return MockApi()

    monkeypatch.setattr(mikrotik, "connect", mock_connect)
    result = client._query("ip", "arp")
    assert len(connected) == 1
    assert result == [{"result": "ok"}]


def test_query_reconnects_on_failure(monkeypatch):
    client = mikrotik.MikroTikClient("host", "user", "pass")
    call_count = []

    class FailOnceApi:
        def __init__(self, fail):
            self.fail = fail

        def path(self, *args):
            if self.fail:
                raise LibRouterosError("connection lost")
            return [{"result": "ok"}]

    def mock_connect(host, username, password):
        call_count.append(True)
        return FailOnceApi(fail=len(call_count) == 1)

    monkeypatch.setattr(mikrotik, "connect", mock_connect)
    result = client._query("ip", "arp")
    assert len(call_count) == 2
    assert result == [{"result": "ok"}]


def test_query_returns_empty_on_connect_failure(monkeypatch):
    client = mikrotik.MikroTikClient("host", "user", "pass")

    def mock_connect(host, username, password):
        raise LibRouterosError("refused")

    monkeypatch.setattr(mikrotik, "connect", mock_connect)
    result = client._query("ip", "arp")
    assert result == []
