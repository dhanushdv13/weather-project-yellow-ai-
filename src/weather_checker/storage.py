"""Storage module for atomic reading and writing of order data."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import tempfile
from typing import List

from weather_checker.models import Order

logger = logging.getLogger("weather_checker.storage")


class StorageError(Exception):
    """Raised when reading or writing order data fails."""


def load_orders(file_path: Path | str) -> List[Order]:
    """Read orders from a JSON file and validate with Pydantic.

    Args:
        file_path: Path to the orders JSON file.

    Returns:
        List of validated Order instances.

    Raises:
        StorageError: If file not found, unreadable, or invalid JSON format.
    """
    path = Path(file_path)
    if not path.is_file():
        raise StorageError(f"Orders file not found at: {path.resolve()}")

    try:
        content = path.read_text(encoding="utf-8")
        raw_data = json.loads(content)
        if not isinstance(raw_data, list):
            raise StorageError(
                f"Expected JSON array in {path.name}, but found {type(raw_data).__name__}"
            )
        orders = [Order.model_validate(item) for item in raw_data]
        logger.info(f"Loaded {len(orders)} orders from {path.resolve()}")
        return orders
    except json.JSONDecodeError as exc:
        raise StorageError(f"Failed to parse JSON in {path}: {exc}") from exc
    except Exception as exc:
        raise StorageError(f"Error loading orders from {path}: {exc}") from exc


def save_orders_atomic(
    orders: List[Order],
    file_path: Path | str,
    indent: int = 2,
) -> None:
    """Atomically write orders to a JSON file using a temp file and replace.

    Guarantees that readers never observe partially written files or corruption.

    Args:
        orders: List of Order instances to persist.
        file_path: Destination path for orders.json.
        indent: JSON indentation for readability.

    Raises:
        StorageError: If writing or renaming fails.
    """
    dest_path = Path(file_path).resolve()
    target_dir = dest_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # Convert orders to dict, omitting None fields to keep clean schema
    serialized = [order.model_dump(exclude_none=True) for order in orders]
    json_bytes = (json.dumps(serialized, indent=indent) + "\n").encode("utf-8")

    # Create temporary file in the same directory to guarantee atomic rename
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target_dir,
            prefix=f".{dest_path.name}.tmp_",
            delete=False,
        ) as f:
            temp_file = Path(f.name)
            f.write(json_bytes)
            f.flush()
            os.fsync(f.fileno())

        # Atomic replacement
        os.replace(temp_file, dest_path)
        logger.info(f"Atomically saved {len(orders)} orders to {dest_path}")
    except Exception as exc:
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass
        logger.exception(f"Failed to atomically write orders to {dest_path}: {exc}")
        raise StorageError(f"Failed to write orders to {dest_path}: {exc}") from exc
