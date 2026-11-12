"""Unit tests for logging setup and secret redaction."""

import logging
from weather_checker.logging_setup import SecretFilter, setup_logging


def test_secret_filter_masks_known_secret():
    secret = "secret_api_key_12345"
    f = SecretFilter(secrets=[secret])
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=f"Requesting weather with key {secret} now",
        args=(),
        exc_info=None,
    )
    f.filter(record)
    assert secret not in record.msg
    assert "***REDACTED***" in record.msg


def test_secret_filter_masks_url_param():
    f = SecretFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="GET https://api.openweathermap.org/data/2.5/weather?q=London&appid=abcdef123456",
        args=(),
        exc_info=None,
    )
    f.filter(record)
    assert "abcdef123456" not in record.msg
    assert "appid=***REDACTED***" in record.msg


def test_setup_logging_writes_to_file(tmp_path):
    log_file = tmp_path / "test_run.log"
    logger = setup_logging(log_file=log_file, level=logging.DEBUG)
    logger.info("Test log line written")

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "Test log line written" in content
