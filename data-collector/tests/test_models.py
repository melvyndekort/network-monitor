"""Tests for models module."""

from data_collector.models import detect_vlan, make_event


def test_detect_vlan_data():
    """Test VLAN 10 detection for data subnet."""
    assert detect_vlan("10.204.10.100") == 10


def test_detect_vlan_iot():
    """Test VLAN 20 detection for IoT subnet."""
    assert detect_vlan("10.204.20.50") == 20


def test_detect_vlan_guest():
    """Test VLAN 30 detection for guest subnet."""
    assert detect_vlan("10.204.30.1") == 30


def test_detect_vlan_vpn():
    """Test VLAN 40 detection for VPN subnet."""
    assert detect_vlan("10.204.40.5") == 40


def test_detect_vlan_management():
    """Test VLAN 50 detection for management subnet."""
    assert detect_vlan("10.204.50.10") == 50


def test_detect_vlan_unknown():
    """Test unknown subnet returns None."""
    assert detect_vlan("192.168.1.1") is None


def test_detect_vlan_none():
    """Test None IP returns None."""
    assert detect_vlan(None) is None


def test_make_event_discovered():
    """Test device_discovered event creation."""
    result = make_event(
        "device_discovered", "aa:bb:cc:dd:ee:ff", "10.204.10.100", "test-host"
    )
    assert result["source"] == "data_collector"
    assert result["event_type"] == "device_discovered"
    assert result["mac"] == "AA:BB:CC:DD:EE:FF"
    assert result["ip"] == "10.204.10.100"
    assert result["hostname"] == "test-host"
    assert result["vlan"] == 10
    assert result["metadata"] == {}
    assert "timestamp" in result


def test_make_event_activity():
    """Test device_activity event creation."""
    result = make_event("device_activity", "11:22:33:44:55:66", "10.204.20.50")
    assert result["event_type"] == "device_activity"
    assert result["mac"] == "11:22:33:44:55:66"
    assert result["vlan"] == 20
    assert result["hostname"] is None


def test_make_event_no_ip():
    """Test event creation without IP."""
    result = make_event("device_discovered", "aa:bb:cc:dd:ee:ff")
    assert result["ip"] is None
    assert result["vlan"] is None


def test_make_event_with_metadata():
    """Test event creation with metadata."""
    result = make_event(
        "device_discovered", "aa:bb:cc:dd:ee:ff", metadata={"key": "value"}
    )
    assert result["metadata"] == {"key": "value"}
