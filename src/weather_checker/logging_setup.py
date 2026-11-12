"""Logging configuration for weather delay checker."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional


class SecretFilter(logging.Filter):
    """Logging filter that scrubs sensitive API keys and tokens from log records."""

    def __init__(self, secrets: Optional[list[str]] = None) -> None:
        super().__init__()
        self.secrets = [s.strip() for s in (secrets or []) if s and len(s.strip()) > 3]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            # Redact known explicit secret values
            for secret in self.secrets:
                record.msg = record.msg.replace(secret, "***REDACTED***")
            # Redact common URL parameter patterns like appid=XYZ or api_key=XYZ
            record.msg = re.sub(
                r"(appid|api_key|token)=([a-zA-Z0-9_-]+)",
                r"\1=***REDACTED***",
                record.msg,
                flags=re.IGNORECASE,
            )
        return True


def setup_logging(
    log_file: Optional[Path | str] = "logs/run.log",
    level: int = logging.INFO,
    secrets_to_mask: Optional[list[str]] = None,
) -> logging.Logger:
    """Configure console and file logging.

    Args:
        log_file: Path to the log file (e.g., 'logs/run.log'). Set to None to disable file logging.
        level: Logging level (e.g., logging.INFO, logging.DEBUG).
        secrets_to_mask: List of secret strings to scrub from log output.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("weather_checker")
    logger.setLevel(level)

    # Avoid duplicate handlers if setup is called multiple times
    if logger.handlers:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    secret_filter = SecretFilter(secrets=secrets_to_mask)

    # 1. Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(secret_filter)
    logger.addHandler(console_handler)

    # 2. File Handler (if log_file specified)
    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(file_path, mode="a", encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(secret_filter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger
