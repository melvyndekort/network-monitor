"""Tests for Pi-hole client."""

import json
from unittest.mock import patch, MagicMock

from data_collector.pihole import PiholeClient, classify
from tests.helpers import mock_urlopen as build_responses

LOGIN_OK = {"session": {"valid": True, "sid": "test-sid"}}


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
    """poll_host logs in, then returns only events for tracked devices, correctly classified."""
    mock_urlopen.side_effect = build_responses(
        [
            LOGIN_OK,
            {
                "devices": [
                    {
                        "hwaddr": "74:4C:A1:55:F9:55",
                        "ips": [{"ip": "10.204.10.108"}],
                    }
                ]
            },
            {
                "queries": [
                    {
                        "time": 1000,
                        "domain": "roncalli.magister.net",
                        "type": "A",
                        "status": "FORWARDED",
                        "client": {"ip": "10.204.10.108"},
                    },
                    {
                        "time": 1001,
                        "domain": "youtube.com",
                        "type": "A",
                        "status": "GRAVITY",
                        "client": {"ip": "10.204.10.108"},
                    },
                    {
                        "time": 1002,
                        "domain": "other-device.example.com",
                        "type": "A",
                        "status": "FORWARDED",
                        "client": {"ip": "10.204.10.200"},
                    },
                ],
            },
        ]
    )

    client = PiholeClient(
        ["pihole-1"], {"74:4C:A1:55:F9:55": "chromebook"}, {"pihole-1": "pw"}
    )
    client._last_seen["pihole-1"] = 0  # pylint: disable=protected-access
    events = client.poll_host("pihole-1")

    assert len(events) == 2
    assert events[0]["domain"] == "roncalli.magister.net"
    assert events[0]["result"] == "allowed"
    assert events[0]["device"] == "chromebook"
    assert events[1]["domain"] == "youtube.com"
    assert events[1]["result"] == "blocked"
    assert client._last_seen["pihole-1"] == 1002  # pylint: disable=protected-access


@patch("data_collector.pihole.urllib.request.urlopen")
def test_poll_host_skips_queries_at_or_before_last_seen(mock_urlopen):
    """Regression test: queries at/before the last-seen boundary are not re-emitted.

    Pi-hole's "cursor" field is not an actual pagination token (verified live:
    resubmitting it returns the exact same rows), so the "from" timestamp
    filter is inclusive and can return the boundary record again.
    """
    mock_urlopen.side_effect = build_responses(
        [
            LOGIN_OK,
            {"devices": [{"hwaddr": "AA:BB:CC:DD:EE:FF", "ips": [{"ip": "10.0.0.1"}]}]},
            {
                "queries": [
                    {
                        "time": 1000,
                        "domain": "already-seen.com",
                        "type": "A",
                        "status": "FORWARDED",
                        "client": {"ip": "10.0.0.1"},
                    },
                    {
                        "time": 1001,
                        "domain": "new.com",
                        "type": "A",
                        "status": "FORWARDED",
                        "client": {"ip": "10.0.0.1"},
                    },
                ],
            },
        ]
    )

    client = PiholeClient(
        ["pihole-1"], {"AA:BB:CC:DD:EE:FF": "chromebook"}, {"pihole-1": "pw"}
    )
    client._last_seen["pihole-1"] = 1000  # pylint: disable=protected-access
    events = client.poll_host("pihole-1")

    assert len(events) == 1
    assert events[0]["domain"] == "new.com"


@patch("data_collector.pihole.urllib.request.urlopen")
def test_poll_host_no_new_queries_does_not_regress_last_seen(mock_urlopen):
    """If nothing new came back, last_seen stays put rather than resetting."""
    mock_urlopen.side_effect = build_responses(
        [
            LOGIN_OK,
            {"devices": [{"hwaddr": "AA:BB:CC:DD:EE:FF", "ips": [{"ip": "10.0.0.1"}]}]},
            {"queries": []},
        ]
    )

    client = PiholeClient(
        ["pihole-1"], {"AA:BB:CC:DD:EE:FF": "chromebook"}, {"pihole-1": "pw"}
    )
    client._last_seen["pihole-1"] = 1000  # pylint: disable=protected-access
    events = client.poll_host("pihole-1")

    assert not events
    assert client._last_seen["pihole-1"] == 1000  # pylint: disable=protected-access


@patch("data_collector.pihole.urllib.request.urlopen")
def test_poll_host_no_tracked_devices_returns_empty(mock_urlopen):
    """poll_host returns nothing when no tracked device IPs are known."""
    mock_urlopen.side_effect = build_responses([LOGIN_OK, {"devices": []}])

    client = PiholeClient(
        ["pihole-1"], {"AA:BB:CC:DD:EE:FF": "chromebook"}, {"pihole-1": "pw"}
    )
    events = client.poll_host("pihole-1")

    assert not events


@patch("data_collector.pihole.urllib.request.urlopen")
def test_poll_combines_multiple_hosts(mock_urlopen):
    """poll() logs into and combines events across all configured Pi-hole hosts."""
    mock_urlopen.side_effect = build_responses(
        [
            LOGIN_OK,
            {"devices": [{"hwaddr": "AA:BB:CC:DD:EE:FF", "ips": [{"ip": "10.0.0.1"}]}]},
            {
                "queries": [
                    {
                        "time": 1000,
                        "domain": "a.com",
                        "type": "A",
                        "status": "FORWARDED",
                        "client": {"ip": "10.0.0.1"},
                    }
                ],
            },
            LOGIN_OK,
            {"devices": [{"hwaddr": "AA:BB:CC:DD:EE:FF", "ips": [{"ip": "10.0.0.1"}]}]},
            {
                "queries": [
                    {
                        "time": 2000,
                        "domain": "b.com",
                        "type": "A",
                        "status": "GRAVITY",
                        "client": {"ip": "10.0.0.1"},
                    }
                ],
            },
        ]
    )

    client = PiholeClient(
        ["pihole-1", "pihole-2"],
        {"AA:BB:CC:DD:EE:FF": "chromebook"},
        {"pihole-1": "pw1", "pihole-2": "pw2"},
    )
    client._last_seen = {"pihole-1": 0, "pihole-2": 0}  # pylint: disable=protected-access
    events = client.poll()

    assert len(events) == 2
    assert {e["domain"] for e in events} == {"a.com", "b.com"}


@patch("data_collector.pihole.urllib.request.urlopen")
def test_poll_host_unreachable_does_not_raise(mock_urlopen):
    """A failed Pi-hole login returns an empty list rather than raising."""
    mock_urlopen.side_effect = OSError("unreachable")

    client = PiholeClient(
        ["pihole-1"], {"AA:BB:CC:DD:EE:FF": "chromebook"}, {"pihole-1": "pw"}
    )
    events = client.poll_host("pihole-1")

    assert not events


@patch("data_collector.pihole.urllib.request.urlopen")
def test_poll_one_host_failing_does_not_break_others(mock_urlopen):
    """poll() continues to the next host if one fails to log in."""
    call_count = 0

    def side_effect(*args, **kwargs):
        del args, kwargs
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError("pihole-1 unreachable")
        responses = [
            LOGIN_OK,
            {"devices": [{"hwaddr": "AA:BB:CC:DD:EE:FF", "ips": [{"ip": "10.0.0.1"}]}]},
            {
                "queries": [
                    {
                        "time": 1000,
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

    client = PiholeClient(
        ["pihole-1", "pihole-2"],
        {"AA:BB:CC:DD:EE:FF": "chromebook"},
        {"pihole-1": "pw1", "pihole-2": "pw2"},
    )
    client._last_seen = {"pihole-1": 0, "pihole-2": 0}  # pylint: disable=protected-access
    events = client.poll()

    assert len(events) == 1
    assert events[0]["domain"] == "a.com"


@patch("data_collector.pihole.urllib.request.urlopen")
def test_poll_host_login_rejected_returns_empty(mock_urlopen):
    """A login response with no sid (bad password) results in no events, no crash."""
    mock_urlopen.side_effect = build_responses([{"session": {"valid": False}}])

    client = PiholeClient(
        ["pihole-1"], {"AA:BB:CC:DD:EE:FF": "chromebook"}, {"pihole-1": "wrong"}
    )
    events = client.poll_host("pihole-1")

    assert not events


@patch("data_collector.pihole.urllib.request.urlopen")
def test_poll_host_reauths_on_expired_session(mock_urlopen):
    """A 401 on an authenticated request triggers a fresh login and retry."""
    call_count = 0

    def side_effect(req, **kwargs):
        del kwargs
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # initial login
            resp = MagicMock()
            resp.read.return_value = json.dumps(LOGIN_OK).encode()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp
        if call_count == 2:
            # first devices call: session expired
            import urllib.error  # pylint: disable=import-outside-toplevel

            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
        if call_count == 3:
            # re-login
            resp = MagicMock()
            resp.read.return_value = json.dumps(LOGIN_OK).encode()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp
        # retried devices call succeeds
        resp = MagicMock()
        resp.read.return_value = json.dumps({"devices": []}).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    mock_urlopen.side_effect = side_effect

    client = PiholeClient(
        ["pihole-1"], {"AA:BB:CC:DD:EE:FF": "chromebook"}, {"pihole-1": "pw"}
    )
    ip_map = client._device_ips("pihole-1")  # pylint: disable=protected-access

    assert not ip_map
    assert call_count == 4
