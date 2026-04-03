"""Tests for OpenWrt ubus client."""

import json
from unittest.mock import patch, MagicMock
from data_collector.openwrt import OpenWrtClient


def _mock_urlopen(responses):
    """Create a mock urlopen that returns responses in order."""
    call_count = 0

    def side_effect(*args, **kwargs):
        del args, kwargs
        nonlocal call_count
        resp = MagicMock()
        resp.read.return_value = json.dumps(responses[call_count]).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        call_count += 1
        return resp

    return side_effect


@patch("data_collector.openwrt.urllib.request.urlopen")
def test_get_associated_macs(mock_urlopen):
    """Test getting associated MACs from a single AP."""
    mock_urlopen.side_effect = _mock_urlopen(
        [
            {"jsonrpc": "2.0", "id": 1, "result": [0, {"ubus_rpc_session": "abc123"}]},
            {"jsonrpc": "2.0", "id": 1, "result": {"hostapd.wl0": {"get_clients": {}}}},
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"clients": {"aa:bb:cc:dd:ee:ff": {}}}],
            },
        ]
    )

    client = OpenWrtClient(["10.0.0.1"], "user", "pass")
    macs = client.get_associated_macs()
    assert macs == {"AA:BB:CC:DD:EE:FF"}


@patch("data_collector.openwrt.urllib.request.urlopen")
def test_get_associated_macs_multiple_interfaces(mock_urlopen):
    """Test getting associated MACs from multiple interfaces."""
    mock_urlopen.side_effect = _mock_urlopen(
        [
            {"jsonrpc": "2.0", "id": 1, "result": [0, {"ubus_rpc_session": "abc"}]},
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"hostapd.wl0": {}, "hostapd.wl1": {}},
            },
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"clients": {"aa:bb:cc:dd:ee:ff": {}}}],
            },
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"clients": {"11:22:33:44:55:66": {}}}],
            },
        ]
    )

    client = OpenWrtClient(["10.0.0.1"], "user", "pass")
    macs = client.get_associated_macs()
    assert macs == {"AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"}


@patch("data_collector.openwrt.urllib.request.urlopen")
def test_failed_ap_does_not_break_others(mock_urlopen):
    """Test that a failed AP doesn't prevent collecting from others."""
    call_count = 0

    def side_effect(req, **kwargs):
        del kwargs
        nonlocal call_count
        call_count += 1
        url = req.full_url
        if "10.0.0.1" in url:
            raise ConnectionError("AP unreachable")
        responses = [
            {"jsonrpc": "2.0", "id": 1, "result": [0, {"ubus_rpc_session": "abc"}]},
            {"jsonrpc": "2.0", "id": 1, "result": {"hostapd.wl0": {}}},
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": [0, {"clients": {"aa:bb:cc:dd:ee:ff": {}}}],
            },
        ]
        idx = call_count - 2
        resp = MagicMock()
        resp.read.return_value = json.dumps(responses[idx]).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    mock_urlopen.side_effect = side_effect

    client = OpenWrtClient(["10.0.0.1", "10.0.0.2"], "user", "pass")
    macs = client.get_associated_macs()
    assert macs == {"AA:BB:CC:DD:EE:FF"}


@patch("data_collector.openwrt.urllib.request.urlopen")
def test_empty_ap(mock_urlopen):
    """Test AP with no clients returns empty set."""
    mock_urlopen.side_effect = _mock_urlopen(
        [
            {"jsonrpc": "2.0", "id": 1, "result": [0, {"ubus_rpc_session": "abc"}]},
            {"jsonrpc": "2.0", "id": 1, "result": {"hostapd.wl0": {}}},
            {"jsonrpc": "2.0", "id": 1, "result": [0, {"clients": {}}]},
        ]
    )

    client = OpenWrtClient(["10.0.0.1"], "user", "pass")
    macs = client.get_associated_macs()
    assert macs == set()
