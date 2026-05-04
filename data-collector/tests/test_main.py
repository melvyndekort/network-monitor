"""Tests for main module."""

from unittest.mock import MagicMock

import pytest

from data_collector import main


class MockMikroTik:
    """Mock MikroTik client for testing."""

    def __init__(self, arp=None, dhcp=None):
        self._arp = arp or []
        self._dhcp = dhcp or []

    def get_arp(self):
        """Return mock ARP entries."""
        return self._arp

    def get_dhcp_leases(self):
        """Return mock DHCP leases."""
        return self._dhcp


def _mock_openwrt(macs=None):
    """Create a mock OpenWrt client returning {MAC: client_info} dict."""
    mock = MagicMock()
    mock.get_associated_macs.return_value = macs if macs is not None else {}
    return mock


def test_build_enrichment_lookup():
    """Test enrichment lookup from ARP + DHCP."""
    client = MockMikroTik(
        arp=[
            {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}
        ],
        dhcp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "host1"}],
    )
    result = main.build_enrichment_lookup(client)
    assert "AA:BB:CC:DD:EE:FF" in result
    assert result["AA:BB:CC:DD:EE:FF"]["hostname"] == "host1"


def test_build_enrichment_lookup_dhcp_only():
    """Test enrichment lookup with DHCP-only entries."""
    client = MockMikroTik(
        arp=[],
        dhcp=[{"mac": "aa:bb:cc:dd:ee:ff", "ip": "10.204.10.100", "hostname": "host1"}],
    )
    result = main.build_enrichment_lookup(client)
    assert "AA:BB:CC:DD:EE:FF" in result
    assert result["AA:BB:CC:DD:EE:FF"]["ip"] == "10.204.10.100"


def test_collect_devices_wireless_present():
    """Test wireless device is collected."""
    mikrotik = MockMikroTik(
        arp=[
            {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}
        ],
        dhcp=[
            {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "myhost"}
        ],
    )
    openwrt = _mock_openwrt(macs={"AA:BB:CC:DD:EE:FF": {"ap": "10.0.0.1", "band": "5GHz", "signal": -50, "connected_time": 60}})
    devices = main.collect_devices(mikrotik, openwrt)
    assert "AA:BB:CC:DD:EE:FF" in devices
    assert devices["AA:BB:CC:DD:EE:FF"]["hostname"] == "myhost"
    assert devices["AA:BB:CC:DD:EE:FF"]["wifi"]["ap"] == "10.0.0.1"
    assert devices["AA:BB:CC:DD:EE:FF"]["wifi"]["band"] == "5GHz"


def test_collect_devices_wireless_only_no_arp():
    """Wireless device with no ARP/DHCP entry still shows up."""
    mikrotik = MockMikroTik()
    openwrt = _mock_openwrt(macs={"AA:BB:CC:DD:EE:FF": {"ap": "10.0.0.1", "band": "5GHz", "signal": -50, "connected_time": 60}})
    devices = main.collect_devices(mikrotik, openwrt)
    assert "AA:BB:CC:DD:EE:FF" in devices
    assert devices["AA:BB:CC:DD:EE:FF"]["ip"] is None
    assert devices["AA:BB:CC:DD:EE:FF"]["wifi"]["ap"] == "10.0.0.1"


def test_collect_devices_wired_device_included():
    """Wired device in ARP but not wireless is still included."""
    mikrotik = MockMikroTik(
        arp=[{"mac": "11:22:33:44:55:66", "ip": "10.204.10.10", "interface": "bridge"}],
        dhcp=[],
    )
    openwrt = _mock_openwrt(macs={})
    devices = main.collect_devices(mikrotik, openwrt)
    assert "11:22:33:44:55:66" in devices
    assert devices["11:22:33:44:55:66"]["wifi"] is None


def test_collect_devices_dhcp_only_not_included():
    """DHCP-only device (not wireless, not in ARP) is NOT included."""
    mikrotik = MockMikroTik(
        arp=[],
        dhcp=[
            {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "myhost"}
        ],
    )
    openwrt = _mock_openwrt(macs={})
    devices = main.collect_devices(mikrotik, openwrt)
    assert "AA:BB:CC:DD:EE:FF" not in devices


def test_poll_sends_events():
    """Test poll sends events to SQS."""
    mikrotik = MockMikroTik(
        arp=[{"mac": "11:22:33:44:55:66", "ip": "10.204.10.10", "interface": "bridge"}],
        dhcp=[],
    )
    openwrt = _mock_openwrt(macs={"AA:BB:CC:DD:EE:FF": {"ap": "10.0.0.1", "band": "5GHz", "signal": -50, "connected_time": 60}})
    sqs = MagicMock()
    sent = main.poll(mikrotik, openwrt, sqs)
    assert sent == 2
    events = sqs.call_args[0][0]
    assert all(e["event_type"] == "device_activity" for e in events)
    wireless_event = [e for e in events if e["mac"] == "AA:BB:CC:DD:EE:FF"][0]
    assert wireless_event["metadata"]["ap"] == "10.0.0.1"
    assert wireless_event["metadata"]["band"] == "5GHz"
    assert wireless_event["metadata"]["signal"] == -50
    assert wireless_event["metadata"]["connected_time"] == 60


def test_poll_empty_network():
    """Test poll with no devices sends nothing."""
    mikrotik = MockMikroTik()
    openwrt = _mock_openwrt(macs={})
    sqs = MagicMock()
    sent = main.poll(mikrotik, openwrt, sqs)
    assert sent == 0
    sqs.assert_not_called()


def test_poll_writes_to_influxdb():
    """Test poll writes presence data to InfluxDB when writer provided."""
    mikrotik = MockMikroTik(
        arp=[
            {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}
        ],
        dhcp=[],
    )
    openwrt = _mock_openwrt(macs={"AA:BB:CC:DD:EE:FF": {"ap": "10.0.0.1", "band": "5GHz", "signal": -50, "connected_time": 60}})
    sqs = MagicMock()
    influx = MagicMock()
    main.poll(mikrotik, openwrt, sqs, write_presence=influx)
    influx.assert_called_once()
    devices = influx.call_args[0][0]
    assert "AA:BB:CC:DD:EE:FF" in devices
    assert devices["AA:BB:CC:DD:EE:FF"]["vlan"] == 10


def test_poll_no_influxdb_write_when_none():
    """Test poll works without InfluxDB writer."""
    mikrotik = MockMikroTik(
        arp=[
            {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}
        ],
        dhcp=[],
    )
    openwrt = _mock_openwrt(macs={"AA:BB:CC:DD:EE:FF": {"ap": "10.0.0.1", "band": "5GHz", "signal": -50, "connected_time": 60}})
    sqs = MagicMock()
    main.poll(mikrotik, openwrt, sqs)


def test_poll_enriches_wireless_with_dhcp_hostname():
    """Test poll enriches wireless devices with DHCP hostname."""
    mikrotik = MockMikroTik(
        arp=[
            {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}
        ],
        dhcp=[
            {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "myhost"}
        ],
    )
    openwrt = _mock_openwrt(macs={"AA:BB:CC:DD:EE:FF": {"ap": "10.0.0.1", "band": "5GHz", "signal": -50, "connected_time": 60}})
    sqs = MagicMock()
    main.poll(mikrotik, openwrt, sqs)
    events = sqs.call_args[0][0]
    assert events[0]["hostname"] == "myhost"


def test_main_exits_without_password(monkeypatch):
    """Test main exits when MIKROTIK_PASSWORD is missing."""
    monkeypatch.delenv("MIKROTIK_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main.main()
    assert exc_info.value.code == 1


def test_main_exits_without_queue_url(monkeypatch):
    """Test main exits when SQS_QUEUE_URL is missing."""
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    monkeypatch.delenv("SQS_QUEUE_URL", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main.main()
    assert exc_info.value.code == 1


def test_main_exits_without_ap_hosts(monkeypatch):
    """Test main exits when AP_HOSTS is missing."""
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.example.com/queue")
    monkeypatch.delenv("AP_HOSTS", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main.main()
    assert exc_info.value.code == 1


def test_main_exits_without_ap_password(monkeypatch):
    """Test main exits when AP_PASSWORD is missing."""
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.example.com/queue")
    monkeypatch.setenv("AP_HOSTS", "10.204.50.11")
    monkeypatch.delenv("AP_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main.main()
    assert exc_info.value.code == 1
