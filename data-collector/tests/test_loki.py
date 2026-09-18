"""Tests for Grafana Cloud Loki writer."""

import json
from unittest.mock import patch, MagicMock

from data_collector.loki import create_loki_writer


def _mock_response(status=204):
    resp = MagicMock()
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@patch("data_collector.loki.urllib.request.urlopen")
def test_write_events_pushes_to_loki(mock_urlopen):
    """write_events posts a correctly-shaped payload to the Loki push endpoint."""
    mock_urlopen.return_value = _mock_response()

    writer = create_loki_writer("https://logs.example.com", "user", "pass")
    writer(
        [
            {
                "device": "chromebook",
                "result": "blocked",
                "domain": "youtube.com",
                "query_type": "A",
                "client_ip": "10.204.10.108",
                "pihole_instance": "pihole-1",
            }
        ]
    )

    mock_urlopen.assert_called_once()
    request = mock_urlopen.call_args[0][0]
    assert request.full_url == "https://logs.example.com/loki/api/v1/push"
    assert request.get_header("Authorization").startswith("Basic ")

    payload = json.loads(request.data)
    assert len(payload["streams"]) == 1
    stream = payload["streams"][0]
    assert stream["stream"] == {
        "job": "pihole-daan",
        "device": "chromebook",
        "result": "blocked",
    }
    line = json.loads(stream["values"][0][1])
    assert line["domain"] == "youtube.com"


@patch("data_collector.loki.urllib.request.urlopen")
def test_write_events_skips_empty(mock_urlopen):
    """write_events does nothing for an empty event list."""
    writer = create_loki_writer("https://logs.example.com", "user", "pass")
    writer([])

    mock_urlopen.assert_not_called()


@patch("data_collector.loki.urllib.request.urlopen")
def test_write_events_groups_by_device_and_result(mock_urlopen):
    """Events with the same (device, result) share one stream."""
    mock_urlopen.return_value = _mock_response()

    writer = create_loki_writer("https://logs.example.com", "user", "pass")
    writer(
        [
            {
                "device": "chromebook",
                "result": "blocked",
                "domain": "a.com",
                "query_type": "A",
                "client_ip": "10.204.10.108",
                "pihole_instance": "pihole-1",
            },
            {
                "device": "chromebook",
                "result": "blocked",
                "domain": "b.com",
                "query_type": "A",
                "client_ip": "10.204.10.108",
                "pihole_instance": "pihole-1",
            },
            {
                "device": "phone",
                "result": "allowed",
                "domain": "c.com",
                "query_type": "A",
                "client_ip": "10.204.10.127",
                "pihole_instance": "pihole-1",
            },
        ]
    )

    payload = json.loads(mock_urlopen.call_args[0][0].data)
    assert len(payload["streams"]) == 2
    blocked_stream = next(
        s for s in payload["streams"] if s["stream"]["result"] == "blocked"
    )
    assert len(blocked_stream["values"]) == 2


@patch("data_collector.loki.urllib.request.urlopen")
def test_write_events_handles_push_error(mock_urlopen):
    """write_events logs and does not raise on a Loki push failure."""
    mock_urlopen.side_effect = OSError("connection refused")

    writer = create_loki_writer("https://logs.example.com", "user", "pass")
    # Should not raise
    writer(
        [
            {
                "device": "chromebook",
                "result": "blocked",
                "domain": "a.com",
                "query_type": "A",
                "client_ip": "10.204.10.108",
                "pihole_instance": "pihole-1",
            }
        ]
    )
