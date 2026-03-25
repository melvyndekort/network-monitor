"""Tests for main module."""
import pytest
from unittest.mock import MagicMock
from data_collector import main


class MockClient:
    def __init__(self, arp=None, dhcp=None):
        self._arp = arp or []
        self._dhcp = dhcp or []

    def get_arp(self):
        return self._arp

    def get_dhcp_leases(self):
        return self._dhcp


def test_build_dhcp_lookup():
    client = MockClient(dhcp=[
        {"mac": "aa:bb:cc:dd:ee:ff", "ip": "10.204.10.100", "hostname": "host1"},
        {"mac": "11:22:33:44:55:66", "ip": "10.204.10.101", "hostname": "host2"},
    ])
    result = main.build_dhcp_lookup(client)
    assert "AA:BB:CC:DD:EE:FF" in result
    assert "11:22:33:44:55:66" in result
    assert result["AA:BB:CC:DD:EE:FF"]["hostname"] == "host1"


def test_collect_devices():
    client = MockClient(
        arp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}],
        dhcp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "myhost"}],
    )
    devices = main.collect_devices(client)
    assert "AA:BB:CC:DD:EE:FF" in devices
    assert devices["AA:BB:CC:DD:EE:FF"]["hostname"] == "myhost"


def test_collect_devices_dhcp_only():
    client = MockClient(
        arp=[],
        dhcp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "myhost"}],
    )
    devices = main.collect_devices(client)
    assert "AA:BB:CC:DD:EE:FF" in devices


def test_poll_sends_all_devices():
    client = MockClient(
        arp=[
            {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"},
            {"mac": "11:22:33:44:55:66", "ip": "10.204.20.50", "interface": "bridge"},
        ],
        dhcp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "myhost"}],
    )
    sqs = MagicMock()
    sent = main.poll(client, sqs)
    assert sent == 2
    events = sqs.call_args[0][0]
    assert len(events) == 2
    assert all(e["event_type"] == "device_activity" for e in events)


def test_poll_empty_network():
    client = MockClient()
    sqs = MagicMock()
    sent = main.poll(client, sqs)
    assert sent == 0
    sqs.assert_not_called()


def test_poll_includes_hostname_from_dhcp():
    client = MockClient(
        arp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}],
        dhcp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "myhost"}],
    )
    sqs = MagicMock()
    main.poll(client, sqs)
    events = sqs.call_args[0][0]
    assert events[0]["hostname"] == "myhost"


def test_poll_no_hostname_without_dhcp():
    client = MockClient(
        arp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}],
        dhcp=[],
    )
    sqs = MagicMock()
    main.poll(client, sqs)
    events = sqs.call_args[0][0]
    assert events[0]["hostname"] is None


def test_main_exits_without_password(monkeypatch):
    monkeypatch.delenv("MIKROTIK_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main.main()
    assert exc_info.value.code == 1


def test_main_exits_without_queue_url(monkeypatch):
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    monkeypatch.delenv("SQS_QUEUE_URL", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main.main()
    assert exc_info.value.code == 1
