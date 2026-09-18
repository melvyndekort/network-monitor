"""Tests for the SQS client."""

from unittest.mock import MagicMock, patch

from data_collector.sqs import create_sqs_client


def _events(timestamp="2026-01-01T00:00:00Z"):
    return [
        {
            "timestamp": timestamp,
            "source": "data_collector",
            "event_type": "device_activity",
            "mac": "AA:BB:CC:DD:EE:FF",
            "ip": "10.204.10.1",
            "hostname": None,
            "vlan": 10,
            "metadata": {},
        }
    ]


@patch("data_collector.sqs.boto3.client")
def test_send_events_calls_sqs(mock_boto_client):
    """Test send_events sends a single batched message."""
    client = MagicMock()
    mock_boto_client.return_value = client

    send_events = create_sqs_client("https://sqs.example.com/queue")
    send_events(_events())

    client.send_message.assert_called_once()
    kwargs = client.send_message.call_args.kwargs
    assert kwargs["QueueUrl"] == "https://sqs.example.com/queue"
    assert kwargs["MessageGroupId"] == "data-collector"


@patch("data_collector.sqs.boto3.client")
def test_send_events_skips_empty(mock_boto_client):
    """Test send_events does nothing for an empty event list."""
    client = MagicMock()
    mock_boto_client.return_value = client

    send_events = create_sqs_client("https://sqs.example.com/queue")
    send_events([])

    client.send_message.assert_not_called()


@patch("data_collector.sqs.boto3.client")
def test_dedup_id_ignores_timestamp(mock_boto_client):
    """Same event content at two different timestamps must dedup identically,
    so FIFO content-based dedup is a real safety net (previously a fresh
    per-event timestamp made every poll's dedup ID unique, defeating it)."""
    client = MagicMock()
    mock_boto_client.return_value = client

    send_events = create_sqs_client("https://sqs.example.com/queue")
    send_events(_events(timestamp="2026-01-01T00:00:00Z"))
    send_events(_events(timestamp="2026-01-01T00:01:00Z"))

    first_id = client.send_message.call_args_list[0].kwargs["MessageDeduplicationId"]
    second_id = client.send_message.call_args_list[1].kwargs["MessageDeduplicationId"]
    assert first_id == second_id


@patch("data_collector.sqs.boto3.client")
def test_dedup_id_differs_on_real_change(mock_boto_client):
    """A genuinely different event set must get a different dedup ID."""
    client = MagicMock()
    mock_boto_client.return_value = client

    send_events = create_sqs_client("https://sqs.example.com/queue")
    send_events(_events())
    other = _events()
    other[0]["ip"] = "10.204.10.2"
    send_events(other)

    first_id = client.send_message.call_args_list[0].kwargs["MessageDeduplicationId"]
    second_id = client.send_message.call_args_list[1].kwargs["MessageDeduplicationId"]
    assert first_id != second_id
