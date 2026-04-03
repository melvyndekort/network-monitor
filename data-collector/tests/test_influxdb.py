"""Tests for InfluxDB writer module."""

from unittest.mock import patch, MagicMock

from data_collector.influxdb import create_influxdb_writer


@patch("data_collector.influxdb.InfluxDBClient")
def test_write_presence_sends_points(mock_client_cls):
    """Test that write_presence sends correct points."""
    mock_write_api = MagicMock()
    mock_client_cls.return_value.write_api.return_value = mock_write_api

    writer = create_influxdb_writer("http://influxdb:8086", "token", "org", "bucket")
    devices = {
        "AA:BB:CC:DD:EE:FF": {"ip": "10.204.10.100", "hostname": "host1", "vlan": 10},
    }
    writer(devices, 1000000)

    mock_write_api.write.assert_called_once()
    call_kwargs = mock_write_api.write.call_args
    assert call_kwargs[1]["bucket"] == "bucket"
    points = call_kwargs[1]["record"]
    assert len(points) == 1


@patch("data_collector.influxdb.InfluxDBClient")
def test_write_presence_skips_empty(mock_client_cls):
    """Test that write_presence does nothing for empty devices."""
    mock_write_api = MagicMock()
    mock_client_cls.return_value.write_api.return_value = mock_write_api

    writer = create_influxdb_writer("http://influxdb:8086", "token", "org", "bucket")
    writer({}, 1000000)

    mock_write_api.write.assert_not_called()


@patch("data_collector.influxdb.InfluxDBClient")
def test_write_presence_handles_missing_fields(mock_client_cls):
    """Test that write_presence handles devices without optional fields."""
    mock_write_api = MagicMock()
    mock_client_cls.return_value.write_api.return_value = mock_write_api

    writer = create_influxdb_writer("http://influxdb:8086", "token", "org", "bucket")
    devices = {"AA:BB:CC:DD:EE:FF": {"ip": None, "hostname": None, "vlan": None}}
    writer(devices, 1000000)

    mock_write_api.write.assert_called_once()
    points = mock_write_api.write.call_args[1]["record"]
    assert len(points) == 1


@patch("data_collector.influxdb.InfluxDBClient")
def test_write_presence_handles_write_error(mock_client_cls):
    """Test that write_presence logs errors without raising."""
    mock_write_api = MagicMock()
    mock_write_api.write.side_effect = OSError("connection refused")
    mock_client_cls.return_value.write_api.return_value = mock_write_api

    writer = create_influxdb_writer("http://influxdb:8086", "token", "org", "bucket")
    # Should not raise
    writer(
        {"AA:BB:CC:DD:EE:FF": {"ip": "10.0.0.1", "hostname": None, "vlan": None}},
        1000000,
    )
