"""Shared test helpers."""

import json
from unittest.mock import MagicMock


def mock_urlopen(responses):
    """Create a mock urlopen side_effect that returns JSON responses in order."""
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
