"""Tests for InfluxDB writer module."""

from unittest.mock import patch, MagicMock
from data_collector.influxdb import create_influxdb_writer


@patch("data_collector.influxdb.urllib3.PoolManager")
def test_write_presence_sends_line_protocol(mock_pool_cls):
    """Test that write_presence sends correct line protocol."""
    mock_http = MagicMock()
    mock_http.request.return_value = MagicMock(status=204)
    mock_pool_cls.return_value = mock_http

    writer = create_influxdb_writer("http://influxdb:8086", "token", "org", "bucket")
    devices = {
        "AA:BB:CC:DD:EE:FF": {"ip": "10.204.10.100", "hostname": "host1", "vlan": 10},
    }
    writer(devices, 1000000)

    mock_http.request.assert_called_once()
    args = mock_http.request.call_args
    body = (
        args[1]["body"].decode()
        if isinstance(args[1]["body"], bytes)
        else args[1]["body"]
    )
    assert "device_presence,mac=AA:BB:CC:DD:EE:FF,vlan=10" in body
    assert "online=1i" in body
    assert 'ip="10.204.10.100"' in body
    assert 'hostname="host1"' in body
    assert "1000000" in body


@patch("data_collector.influxdb.urllib3.PoolManager")
def test_write_presence_skips_empty(mock_pool_cls):
    """Test that write_presence does nothing for empty devices."""
    mock_http = MagicMock()
    mock_pool_cls.return_value = mock_http

    writer = create_influxdb_writer("http://influxdb:8086", "token", "org", "bucket")
    writer({}, 1000000)

    mock_http.request.assert_not_called()


@patch("data_collector.influxdb.urllib3.PoolManager")
def test_write_presence_handles_missing_fields(mock_pool_cls):
    """Test that write_presence handles devices without optional fields."""
    mock_http = MagicMock()
    mock_http.request.return_value = MagicMock(status=204)
    mock_pool_cls.return_value = mock_http

    writer = create_influxdb_writer("http://influxdb:8086", "token", "org", "bucket")
    devices = {"AA:BB:CC:DD:EE:FF": {"ip": None, "hostname": None, "vlan": None}}
    writer(devices, 1000000)

    body = mock_http.request.call_args[1]["body"].decode()
    assert "device_presence,mac=AA:BB:CC:DD:EE:FF online=1i 1000000" == body


@patch("data_collector.influxdb.urllib3.PoolManager")
def test_write_presence_logs_error_on_failure(mock_pool_cls):
    """Test that write_presence logs errors on non-204 response."""
    mock_http = MagicMock()
    mock_http.request.return_value = MagicMock(status=401, data=b"unauthorized")
    mock_pool_cls.return_value = mock_http

    writer = create_influxdb_writer("http://influxdb:8086", "token", "org", "bucket")
    # Should not raise
    writer(
        {"AA:BB:CC:DD:EE:FF": {"ip": "10.0.0.1", "hostname": None, "vlan": None}},
        1000000,
    )
