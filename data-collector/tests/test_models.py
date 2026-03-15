"""Tests for models module."""
import json
from data_collector.models import detect_vlan, make_event


def test_detect_vlan_data():
    assert detect_vlan("10.204.10.100") == 10


def test_detect_vlan_iot():
    assert detect_vlan("10.204.20.50") == 20


def test_detect_vlan_guest():
    assert detect_vlan("10.204.30.1") == 30


def test_detect_vlan_vpn():
    assert detect_vlan("10.204.40.5") == 40


def test_detect_vlan_management():
    assert detect_vlan("10.204.50.10") == 50


def test_detect_vlan_unknown():
    assert detect_vlan("192.168.1.1") is None


def test_detect_vlan_none():
    assert detect_vlan(None) is None


def test_make_event_discovered():
    result = json.loads(make_event("device_discovered", "aa:bb:cc:dd:ee:ff", "10.204.10.100", "test-host"))
    assert result["source"] == "data_collector"
    assert result["event_type"] == "device_discovered"
    assert result["mac"] == "AA:BB:CC:DD:EE:FF"
    assert result["ip"] == "10.204.10.100"
    assert result["hostname"] == "test-host"
    assert result["vlan"] == 10
    assert result["metadata"] == {}
    assert "timestamp" in result


def test_make_event_activity():
    result = json.loads(make_event("device_activity", "11:22:33:44:55:66", "10.204.20.50"))
    assert result["event_type"] == "device_activity"
    assert result["mac"] == "11:22:33:44:55:66"
    assert result["vlan"] == 20
    assert result["hostname"] is None


def test_make_event_no_ip():
    result = json.loads(make_event("device_discovered", "aa:bb:cc:dd:ee:ff"))
    assert result["ip"] is None
    assert result["vlan"] is None


def test_make_event_with_metadata():
    result = json.loads(make_event("device_discovered", "aa:bb:cc:dd:ee:ff", metadata={"key": "value"}))
    assert result["metadata"] == {"key": "value"}
