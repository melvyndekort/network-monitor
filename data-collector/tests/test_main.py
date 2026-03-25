"""Tests for main module."""
import pytest
from unittest.mock import MagicMock
from data_collector import main


class MockMikroTik:
    def __init__(self, arp=None, dhcp=None):
        self._arp = arp or []
        self._dhcp = dhcp or []

    def get_arp(self):
        return self._arp

    def get_dhcp_leases(self):
        return self._dhcp


class MockOpenWrt:
    def __init__(self, macs=None):
        self._macs = macs or set()

    def get_associated_macs(self):
        return self._macs


def test_build_enrichment_lookup():
    client = MockMikroTik(
        arp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}],
        dhcp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "host1"}],
    )
    result = main.build_enrichment_lookup(client)
    assert "AA:BB:CC:DD:EE:FF" in result
    assert result["AA:BB:CC:DD:EE:FF"]["hostname"] == "host1"


def test_build_enrichment_lookup_dhcp_only():
    client = MockMikroTik(
        arp=[],
        dhcp=[{"mac": "aa:bb:cc:dd:ee:ff", "ip": "10.204.10.100", "hostname": "host1"}],
    )
    result = main.build_enrichment_lookup(client)
    assert "AA:BB:CC:DD:EE:FF" in result
    assert result["AA:BB:CC:DD:EE:FF"]["ip"] == "10.204.10.100"


def test_collect_devices_wireless_present():
    mikrotik = MockMikroTik(
        arp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}],
        dhcp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "myhost"}],
    )
    openwrt = MockOpenWrt(macs={"AA:BB:CC:DD:EE:FF"})
    devices = main.collect_devices(mikrotik, openwrt)
    assert "AA:BB:CC:DD:EE:FF" in devices
    assert devices["AA:BB:CC:DD:EE:FF"]["hostname"] == "myhost"


def test_collect_devices_wireless_only_no_arp():
    """Wireless device with no ARP/DHCP entry still shows up."""
    mikrotik = MockMikroTik()
    openwrt = MockOpenWrt(macs={"AA:BB:CC:DD:EE:FF"})
    devices = main.collect_devices(mikrotik, openwrt)
    assert "AA:BB:CC:DD:EE:FF" in devices
    assert devices["AA:BB:CC:DD:EE:FF"]["ip"] is None


def test_collect_devices_wired_device_included():
    """Wired device in ARP but not wireless is still included."""
    mikrotik = MockMikroTik(
        arp=[{"mac": "11:22:33:44:55:66", "ip": "10.204.10.10", "interface": "bridge"}],
        dhcp=[],
    )
    openwrt = MockOpenWrt(macs=set())
    devices = main.collect_devices(mikrotik, openwrt)
    assert "11:22:33:44:55:66" in devices


def test_collect_devices_dhcp_only_not_included():
    """DHCP-only device (not wireless, not in ARP) is NOT included."""
    mikrotik = MockMikroTik(
        arp=[],
        dhcp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "myhost"}],
    )
    openwrt = MockOpenWrt(macs=set())
    devices = main.collect_devices(mikrotik, openwrt)
    assert "AA:BB:CC:DD:EE:FF" not in devices


def test_poll_sends_events():
    mikrotik = MockMikroTik(
        arp=[{"mac": "11:22:33:44:55:66", "ip": "10.204.10.10", "interface": "bridge"}],
        dhcp=[],
    )
    openwrt = MockOpenWrt(macs={"AA:BB:CC:DD:EE:FF"})
    sqs = MagicMock()
    sent = main.poll(mikrotik, openwrt, sqs)
    assert sent == 2
    events = sqs.call_args[0][0]
    assert all(e["event_type"] == "device_activity" for e in events)


def test_poll_empty_network():
    mikrotik = MockMikroTik()
    openwrt = MockOpenWrt()
    sqs = MagicMock()
    sent = main.poll(mikrotik, openwrt, sqs)
    assert sent == 0
    sqs.assert_not_called()


def test_poll_enriches_wireless_with_dhcp_hostname():
    mikrotik = MockMikroTik(
        arp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "interface": "bridge"}],
        dhcp=[{"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.204.10.100", "hostname": "myhost"}],
    )
    openwrt = MockOpenWrt(macs={"AA:BB:CC:DD:EE:FF"})
    sqs = MagicMock()
    main.poll(mikrotik, openwrt, sqs)
    events = sqs.call_args[0][0]
    assert events[0]["hostname"] == "myhost"


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


def test_main_exits_without_ap_hosts(monkeypatch):
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.example.com/queue")
    monkeypatch.delenv("AP_HOSTS", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main.main()
    assert exc_info.value.code == 1


def test_main_exits_without_ap_password(monkeypatch):
    monkeypatch.setenv("MIKROTIK_PASSWORD", "secret")
    monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.example.com/queue")
    monkeypatch.setenv("AP_HOSTS", "10.204.50.11")
    monkeypatch.delenv("AP_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main.main()
    assert exc_info.value.code == 1
