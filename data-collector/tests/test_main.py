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


def test_poll_new_device_sends_discovered():
    devices = {"AA:BB:CC:DD:EE:FF": {"ip": "10.204.10.100", "hostname": "myhost"}}
    sqs = MagicMock()
    macs, sent = main.poll(devices, set(), sqs, heartbeat=False)
    assert "AA:BB:CC:DD:EE:FF" in macs
    events = sqs.send_events.call_args[0][0]
    assert len(events) == 1
    assert events[0]["event_type"] == "device_discovered"
    assert events[0]["mac"] == "AA:BB:CC:DD:EE:FF"
    assert events[0]["hostname"] == "myhost"
    assert events[0]["vlan"] == 10


def test_poll_known_device_no_heartbeat_sends_nothing():
    devices = {"AA:BB:CC:DD:EE:FF": {"ip": "10.204.10.100", "hostname": "myhost"}}
    sqs = MagicMock()
    macs, sent = main.poll(devices, {"AA:BB:CC:DD:EE:FF"}, sqs, heartbeat=False)
    assert "AA:BB:CC:DD:EE:FF" in macs
    assert sent == 0
    sqs.send_events.assert_not_called()


def test_poll_known_device_heartbeat_sends_activity():
    devices = {"AA:BB:CC:DD:EE:FF": {"ip": "10.204.10.100", "hostname": "myhost"}}
    sqs = MagicMock()
    macs, sent = main.poll(devices, {"AA:BB:CC:DD:EE:FF"}, sqs, heartbeat=True)
    events = sqs.send_events.call_args[0][0]
    assert len(events) == 1
    assert events[0]["event_type"] == "device_activity"


def test_poll_mix_new_and_known_on_heartbeat():
    devices = {
        "AA:BB:CC:DD:EE:FF": {"ip": "10.204.10.100", "hostname": None},
        "11:22:33:44:55:66": {"ip": "10.204.20.50", "hostname": None},
    }
    sqs = MagicMock()
    macs, sent = main.poll(devices, {"AA:BB:CC:DD:EE:FF"}, sqs, heartbeat=True)
    assert len(macs) == 2
    events = sqs.send_events.call_args[0][0]
    types = {e["mac"]: e["event_type"] for e in events}
    assert types["11:22:33:44:55:66"] == "device_discovered"
    assert types["AA:BB:CC:DD:EE:FF"] == "device_activity"


def test_poll_new_device_on_heartbeat_sends_discovered_not_activity():
    devices = {"AA:BB:CC:DD:EE:FF": {"ip": "10.204.10.100", "hostname": None}}
    sqs = MagicMock()
    macs, sent = main.poll(devices, set(), sqs, heartbeat=True)
    events = sqs.send_events.call_args[0][0]
    assert len(events) == 1
    assert events[0]["event_type"] == "device_discovered"


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
