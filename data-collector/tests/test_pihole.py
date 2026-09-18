"""Tests for Pi-hole client."""

import json
from unittest.mock import patch, MagicMock

from data_collector.pihole import PiholeClient, classify
from tests.helpers import mock_urlopen as build_responses


def test_classify_blocked():
    """Blocked statuses classify as 'blocked'."""
    assert classify("GRAVITY") == "blocked"
    assert classify("DENYLIST_CNAME") == "blocked"
    assert classify("REGEX") == "blocked"


def test_classify_allowed():
    """Allowed statuses classify as 'allowed'."""
    assert classify("FORWARDED") == "allowed"
    assert classify("CACHE") == "allowed"


def test_classify_unknown_skipped():
    """Unrecognized/in-progress statuses classify as None (skip)."""
    assert classify("IN_PROGRESS") is None
    assert classify("RETRIED") is None


@patch("data_collector.pihole.urllib.request.urlopen")
def test_poll_host_classifies_and_filters(mock_urlopen):
    """poll_host returns only events for tracked devices, correctly classified."""
    mock_urlopen.side_effect = build_responses(
        [
            {
                "devices": [
                    {
                        "hwaddr": "74:4C:A1:55:F9:55",
                        "ips": [{"ip": "10.204.10.108"}],
                    }
                ]
            },
            {
                "cursor": 42,
                "queries": [
                    {
                        "domain": "roncalli.magister.net",
                        "type": "A",
                        "status": "FORWARDED",
                        "client": {"ip": "10.204.10.108"},
                    },
                    {
                        "domain": "youtube.com",
                        "type": "A",
                        "status": "GRAVITY",
                        "client": {"ip": "10.204.10.108"},
                    },
                    {
                        "domain": "other-device.example.com",
                        "type": "A",
                        "status": "FORWARDED",
                        "client": {"ip": "10.204.10.200"},
                    },
                ],
            },
        ]
    )

    client = PiholeClient(["pihole-1"], {"74:4C:A1:55:F9:55": "chromebook"})
    events = client.poll_host("pihole-1")

    assert len(events) == 2
    assert events[0]["domain"] == "roncalli.magister.net"
    assert events[0]["result"] == "allowed"
    assert events[0]["device"] == "chromebook"
    assert events[1]["domain"] == "youtube.com"
    assert events[1]["result"] == "blocked"
    assert client._cursors["pihole-1"] == 42  # pylint: disable=protected-access


@patch("data_collector.pihole.urllib.request.urlopen")
def test_poll_host_no_tracked_devices_returns_empty(mock_urlopen):
    """poll_host returns nothing when no tracked device IPs are known."""
    mock_urlopen.side_effect = build_responses([{"devices": []}])

    client = PiholeClient(["pihole-1"], {"AA:BB:CC:DD:EE:FF": "chromebook"})
    events = client.poll_host("pihole-1")

    assert not events


@patch("data_collector.pihole.urllib.request.urlopen")
def test_poll_combines_multiple_hosts(mock_urlopen):
    """poll() combines events across all configured Pi-hole hosts."""
    mock_urlopen.side_effect = build_responses(
        [
            {"devices": [{"hwaddr": "AA:BB:CC:DD:EE:FF", "ips": [{"ip": "10.0.0.1"}]}]},
            {
                "cursor": 1,
                "queries": [
                    {
                        "domain": "a.com",
                        "type": "A",
                        "status": "FORWARDED",
                        "client": {"ip": "10.0.0.1"},
                    }
                ],
            },
            {"devices": [{"hwaddr": "AA:BB:CC:DD:EE:FF", "ips": [{"ip": "10.0.0.1"}]}]},
            {
                "cursor": 2,
                "queries": [
                    {
                        "domain": "b.com",
                        "type": "A",
                        "status": "GRAVITY",
                        "client": {"ip": "10.0.0.1"},
                    }
                ],
            },
        ]
    )

    client = PiholeClient(["pihole-1", "pihole-2"], {"AA:BB:CC:DD:EE:FF": "chromebook"})
    events = client.poll()

    assert len(events) == 2
    assert {e["domain"] for e in events} == {"a.com", "b.com"}


@patch("data_collector.pihole.urllib.request.urlopen")
def test_poll_host_unreachable_does_not_raise(mock_urlopen):
    """A failed Pi-hole request returns an empty list rather than raising."""
    mock_urlopen.side_effect = OSError("unreachable")

    client = PiholeClient(["pihole-1"], {"AA:BB:CC:DD:EE:FF": "chromebook"})
    events = client.poll_host("pihole-1")

    assert not events


@patch("data_collector.pihole.urllib.request.urlopen")
def test_poll_one_host_failing_does_not_break_others(mock_urlopen):
    """poll() continues to the next host if one fails."""
    call_count = 0

    def side_effect(*args, **kwargs):
        del args, kwargs
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            raise OSError("pihole-1 unreachable")
        responses = [
            {"devices": [{"hwaddr": "AA:BB:CC:DD:EE:FF", "ips": [{"ip": "10.0.0.1"}]}]},
            {
                "cursor": 1,
                "queries": [
                    {
                        "domain": "a.com",
                        "type": "A",
                        "status": "FORWARDED",
                        "client": {"ip": "10.0.0.1"},
                    }
                ],
            },
        ]
        resp = MagicMock()
        resp.read.return_value = json.dumps(responses[call_count - 2]).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    mock_urlopen.side_effect = side_effect

    client = PiholeClient(["pihole-1", "pihole-2"], {"AA:BB:CC:DD:EE:FF": "chromebook"})
    events = client.poll()

    assert len(events) == 1
    assert events[0]["domain"] == "a.com"
