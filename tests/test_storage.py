"""Unit tests for atomic order storage."""

import json
import pytest
from weather_checker.models import Order
from weather_checker.storage import StorageError, load_orders, save_orders_atomic


def test_load_orders_success(tmp_path):
    file_path = tmp_path / "orders.json"
    data = [
        {"order_id": "1", "customer": "Alice", "city": "NYC", "status": "Pending"},
        {"order_id": "2", "customer": "Bob", "city": "London", "status": "Pending"},
    ]
    file_path.write_text(json.dumps(data), encoding="utf-8")

    orders = load_orders(file_path)
    assert len(orders) == 2
    assert orders[0].customer == "Alice"
    assert orders[1].city == "London"


def test_load_orders_missing_file(tmp_path):
    with pytest.raises(StorageError) as exc_info:
        load_orders(tmp_path / "nonexistent.json")
    assert "not found" in str(exc_info.value).lower()


def test_load_orders_invalid_json(tmp_path):
    file_path = tmp_path / "bad.json"
    file_path.write_text("not json content", encoding="utf-8")
    with pytest.raises(StorageError) as exc_info:
        load_orders(file_path)
    assert "failed to parse json" in str(exc_info.value).lower()


def test_save_orders_atomic(tmp_path):
    file_path = tmp_path / "output_orders.json"
    orders = [
        Order(
            order_id="1001",
            customer="Alice Smith",
            city="New York",
            status="Delayed",
            delay_reason="Severe weather: Rain",
            apology_message="Hi Alice, sorry!",
        ),
        Order(
            order_id="1002",
            customer="Bob Jones",
            city="London",
            status="Pending",
        ),
    ]

    save_orders_atomic(orders, file_path)

    assert file_path.exists()
    content = json.loads(file_path.read_text(encoding="utf-8"))
    assert len(content) == 2
    assert content[0]["status"] == "Delayed"
    assert content[0]["delay_reason"] == "Severe weather: Rain"
    assert content[0]["apology_message"] == "Hi Alice, sorry!"
    assert "delay_reason" not in content[1]  # Excluded None
    assert "apology_message" not in content[1]
