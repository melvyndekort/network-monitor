"""Tests for main module."""
import os
import sys
import pytest
from unittest.mock import MagicMock
from data_collector import main


def test_build_dhcp_lookup(monkeypatch):
    class MockClient:
        def get_dhcp_leases(self):
            return [
                {"mac": "aa:bb:cc:dd:ee:ff", "ip": "10.204.10.100", "hostname": "host1"},
                {"mac": "11:22:33:44:55:66", "ip": "10.204.10.101", "hostname": "host2"},
            ]

    result = main.build_dhcp_lookup(MockClient())
    assert "AA:BB:CC:DD:EE:FF" in result
    assert "11:22:33:44:55:66" in result
    assert result["AA:BB:CC:DD:EE:FF"]["hostname"] == "host1"


def test_poll_new_device():
    class MockClient:
        def get_arp(self):
            return [{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}]

        def get_dhcp_leases(self):
            return [{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "myhost"}]

    sqs = MagicMock()
    result = main.poll(MockClient(), set(), sqs)
    assert "AA:BB:CC:DD:EE:FF" in result

    sqs.send_events.assert_called_once()
    events = sqs.send_events.call_args[0][0]
    assert len(events) == 1
    assert events[0]["event_type"] == "device_discovered"
    assert events[0]["mac"] == "AA:BB:CC:DD:EE:FF"
    assert events[0]["hostname"] == "myhost"
    assert events[0]["vlan"] == 10


def test_poll_existing_device():
    class MockClient:
        def get_arp(self):
            return [{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}]

        def get_dhcp_leases(self):
            return []

    sqs = MagicMock()
    result = main.poll(MockClient(), {"AA:BB:CC:DD:EE:FF"}, sqs)
    assert "AA:BB:CC:DD:EE:FF" in result

    events = sqs.send_events.call_args[0][0]
    assert events[0]["event_type"] == "device_activity"


def test_poll_multiple_devices():
    class MockClient:
        def get_arp(self):
            return [
                {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"},
                {"mac": "11:22:33:44:55:66", "ip": "10.204.20.50", "interface": "bridge"},
            ]

        def get_dhcp_leases(self):
            return []

    sqs = MagicMock()
    result = main.poll(MockClient(), set(), sqs)
    assert len(result) == 2

    events = sqs.send_events.call_args[0][0]
    assert len(events) == 2
    assert all(e["event_type"] == "device_discovered" for e in events)


def test_poll_no_hostname_without_dhcp():
    class MockClient:
        def get_arp(self):
            return [{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}]

        def get_dhcp_leases(self):
            return []

    sqs = MagicMock()
    main.poll(MockClient(), set(), sqs)
    events = sqs.send_events.call_args[0][0]
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
