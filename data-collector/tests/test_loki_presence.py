"""Tests for the Loki device-presence writer."""

import json
from unittest.mock import patch, MagicMock

from data_collector.loki_presence import create_presence_writer


def _mock_response(status=204):
    resp = MagicMock()
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@patch("data_collector.loki_presence.urllib.request.urlopen")
def test_write_presence_sends_points(mock_urlopen):
    """write_presence posts one stream per device with the right labels/body."""
    mock_urlopen.return_value = _mock_response()

    writer = create_presence_writer("https://logs.example.com", "user", "pass")
    writer(
        {"AA:BB:CC:DD:EE:FF": {"ip": "10.204.10.100", "hostname": "host1", "vlan": 10}},
        1000000,
    )

    mock_urlopen.assert_called_once()
    request = mock_urlopen.call_args[0][0]
    assert request.full_url == "https://logs.example.com/loki/api/v1/push"
    assert request.get_header("Authorization").startswith("Basic ")

    payload = json.loads(request.data)
    assert len(payload["streams"]) == 1
    stream = payload["streams"][0]
    assert stream["stream"] == {
        "job": "device-presence",
        "mac": "AA:BB:CC:DD:EE:FF",
        "vlan": "10",
    }
    line = json.loads(stream["values"][0][1])
    assert line["ip"] == "10.204.10.100"
    assert line["hostname"] == "host1"
    assert line["online"] is True


@patch("data_collector.loki_presence.urllib.request.urlopen")
def test_write_presence_skips_empty(mock_urlopen):
    """write_presence does nothing for an empty devices dict."""
    writer = create_presence_writer("https://logs.example.com", "user", "pass")
    writer({}, 1000000)

    mock_urlopen.assert_not_called()


@patch("data_collector.loki_presence.urllib.request.urlopen")
def test_write_presence_handles_missing_fields(mock_urlopen):
    """write_presence handles devices without optional fields, defaulting vlan."""
    mock_urlopen.return_value = _mock_response()

    writer = create_presence_writer("https://logs.example.com", "user", "pass")
    writer({"AA:BB:CC:DD:EE:FF": {"ip": None, "hostname": None, "vlan": None}}, 1000000)

    payload = json.loads(mock_urlopen.call_args[0][0].data)
    stream = payload["streams"][0]
    assert stream["stream"]["vlan"] == "unknown"
    line = json.loads(stream["values"][0][1])
    assert line["ip"] is None
    assert line["hostname"] is None


@patch("data_collector.loki_presence.urllib.request.urlopen")
def test_write_presence_multiple_devices_separate_streams(mock_urlopen):
    """Each device gets its own stream (labeled by mac)."""
    mock_urlopen.return_value = _mock_response()

    writer = create_presence_writer("https://logs.example.com", "user", "pass")
    writer(
        {
            "AA:AA:AA:AA:AA:AA": {"ip": "10.0.0.1", "hostname": "a", "vlan": 10},
            "BB:BB:BB:BB:BB:BB": {"ip": "10.0.0.2", "hostname": "b", "vlan": 20},
        },
        1000000,
    )

    payload = json.loads(mock_urlopen.call_args[0][0].data)
    assert len(payload["streams"]) == 2
    macs = {s["stream"]["mac"] for s in payload["streams"]}
    assert macs == {"AA:AA:AA:AA:AA:AA", "BB:BB:BB:BB:BB:BB"}


@patch("data_collector.loki_presence.urllib.request.urlopen")
def test_write_presence_handles_push_error(mock_urlopen):
    """write_presence logs and does not raise on a Loki push failure."""
    mock_urlopen.side_effect = OSError("connection refused")

    writer = create_presence_writer("https://logs.example.com", "user", "pass")
    # Should not raise
    writer(
        {"AA:BB:CC:DD:EE:FF": {"ip": "10.0.0.1", "hostname": None, "vlan": None}},
        1000000,
    )
