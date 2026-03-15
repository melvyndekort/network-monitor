"""Tests for main module."""
import json
import os
import sys
import pytest
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


def test_poll_new_device(monkeypatch, capsys):
    class MockClient:
        def get_arp(self):
            return [{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}]

        def get_dhcp_leases(self):
            return [{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "myhost"}]

    result = main.poll(MockClient(), set())
    assert "AA:BB:CC:DD:EE:FF" in result

    output = json.loads(capsys.readouterr().out.strip())
    assert output["event_type"] == "device_discovered"
    assert output["mac"] == "AA:BB:CC:DD:EE:FF"
    assert output["hostname"] == "myhost"
    assert output["vlan"] == 10


def test_poll_existing_device(monkeypatch, capsys):
    class MockClient:
        def get_arp(self):
            return [{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}]

        def get_dhcp_leases(self):
            return []

    result = main.poll(MockClient(), {"AA:BB:CC:DD:EE:FF"})
    assert "AA:BB:CC:DD:EE:FF" in result

    output = json.loads(capsys.readouterr().out.strip())
    assert output["event_type"] == "device_activity"


def test_poll_multiple_devices(monkeypatch, capsys):
    class MockClient:
        def get_arp(self):
            return [
                {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"},
                {"mac": "11:22:33:44:55:66", "ip": "10.204.20.50", "interface": "bridge"},
            ]

        def get_dhcp_leases(self):
            return []

    result = main.poll(MockClient(), set())
    assert len(result) == 2

    lines = capsys.readouterr().out.strip().split("\n")
    assert len(lines) == 2
    events = [json.loads(line) for line in lines]
    assert all(e["event_type"] == "device_discovered" for e in events)


def test_poll_no_hostname_without_dhcp(monkeypatch, capsys):
    class MockClient:
        def get_arp(self):
            return [{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}]

        def get_dhcp_leases(self):
            return []

    main.poll(MockClient(), set())
    output = json.loads(capsys.readouterr().out.strip())
    assert output["hostname"] is None


def test_main_exits_without_password(monkeypatch):
    monkeypatch.delenv("MIKROTIK_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main.main()
    assert exc_info.value.code == 1
