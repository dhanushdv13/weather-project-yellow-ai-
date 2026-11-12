"""End-to-end integration tests for the weather delay checker pipeline."""

import json
import pytest
import respx
from weather_checker.main import run_pipeline


FOUR_ORDERS_SAMPLE = [
    {
        "order_id": "1001",
        "customer": "Alice Smith",
        "city": "New York",
        "status": "Pending",
    },
    {
        "order_id": "1002",
        "customer": "Bob Jones",
        "city": "Mumbai",
        "status": "Pending",
    },
    {
        "order_id": "1003",
        "customer": "Charlie Green",
        "city": "London",
        "status": "Pending",
    },
    {
        "order_id": "1004",
        "customer": "InvalidCity123",
        "city": "InvalidCity123",
        "status": "Pending",
    },
]


@pytest.mark.asyncio
@respx.mock
async def test_end_to_end_full_pipeline(tmp_path, monkeypatch):
    """Test full pipeline processing all 4 orders concurrently with mocked HTTP responses."""
    monkeypatch.setenv("OPENWEATHER_API_KEY", "dummy-api-key-12345")

    # Mock OpenWeatherMap responses for the 4 cities
    respx.get("https://api.openweathermap.org/data/2.5/weather", params={"q": "New York"}).respond(
        status_code=200,
        json={
            "name": "New York",
            "weather": [{"id": 501, "main": "Rain", "description": "heavy rain"}],
            "main": {"temp": 12.0},
        },
    )
    respx.get("https://api.openweathermap.org/data/2.5/weather", params={"q": "Mumbai"}).respond(
        status_code=200,
        json={
            "name": "Mumbai",
            "weather": [{"id": 800, "main": "Clear", "description": "clear sky"}],
            "main": {"temp": 30.5},
        },
    )
    respx.get("https://api.openweathermap.org/data/2.5/weather", params={"q": "London"}).respond(
        status_code=200,
        json={
            "name": "London",
            "weather": [{"id": 600, "main": "Snow", "description": "light snow"}],
            "main": {"temp": 0.5},
        },
    )
    respx.get("https://api.openweathermap.org/data/2.5/weather", params={"q": "InvalidCity123"}).respond(
        status_code=404,
        json={"cod": "404", "message": "city not found"},
    )

    input_file = tmp_path / "orders.json"
    output_file = tmp_path / "orders_updated.json"
    input_file.write_text(json.dumps(FOUR_ORDERS_SAMPLE), encoding="utf-8")

    exit_code = await run_pipeline(
        file_path=str(input_file),
        output_path=str(output_file),
    )

    assert exit_code == 0
    assert output_file.exists()

    updated = json.loads(output_file.read_text(encoding="utf-8"))
    assert len(updated) == 4

    # 1001: New York (Rain -> Delayed)
    order_1001 = updated[0]
    assert order_1001["order_id"] == "1001"
    assert order_1001["status"] == "Delayed"
    assert "Rain" in order_1001["delay_reason"]
    assert "Hi Alice" in order_1001["apology_message"]
    assert "heavy rain" in order_1001["apology_message"]
    assert "weather_error" not in order_1001

    # 1002: Mumbai (Clear -> Pending unchanged)
    order_1002 = updated[1]
    assert order_1002["order_id"] == "1002"
    assert order_1002["status"] == "Pending"
    assert "delay_reason" not in order_1002
    assert "apology_message" not in order_1002
    assert "weather_error" not in order_1002

    # 1003: London (Snow -> Delayed)
    order_1003 = updated[2]
    assert order_1003["order_id"] == "1003"
    assert order_1003["status"] == "Delayed"
    assert "Snow" in order_1003["delay_reason"]
    assert "Hi Charlie" in order_1003["apology_message"]
    assert "light snow" in order_1003["apology_message"]
    assert "weather_error" not in order_1003

    # 1004: InvalidCity123 (404 -> Pending unchanged, weather_error populated, no crash!)
    order_1004 = updated[3]
    assert order_1004["order_id"] == "1004"
    assert order_1004["status"] == "Pending"
    assert "delay_reason" not in order_1004
    assert "apology_message" not in order_1004
    assert "weather_error" in order_1004
    assert "404" in order_1004["weather_error"]


@pytest.mark.asyncio
async def test_end_to_end_simulation_mode(tmp_path, monkeypatch):
    """Test full pipeline with --simulate override, demonstrating delay without calling real API."""
    empty_env = tmp_path / ".env.empty"
    empty_env.write_text("", encoding="utf-8")
    monkeypatch.setenv("OPENWEATHER_API_KEY", "")

    input_file = tmp_path / "orders.json"
    input_file.write_text(
        json.dumps(
            [
                {"order_id": "1", "customer": "Alice Smith", "city": "Mumbai", "status": "Pending"},
                {"order_id": "2", "customer": "Bob Jones", "city": "London", "status": "Pending"},
            ]
        ),
        encoding="utf-8",
    )

    exit_code = await run_pipeline(
        file_path=str(input_file),
        simulate_arg="Mumbai=Rain,London=Snow:blizzard",
        env_file=empty_env,
    )

    assert exit_code == 0
    updated = json.loads(input_file.read_text(encoding="utf-8"))

    # Both simulated cities should be marked as Delayed
    assert updated[0]["status"] == "Delayed"
    assert "Hi Alice" in updated[0]["apology_message"]
    assert "rain" in updated[0]["apology_message"]

    assert updated[1]["status"] == "Delayed"
    assert "Hi Bob" in updated[1]["apology_message"]
    assert "blizzard" in updated[1]["apology_message"]


@pytest.mark.asyncio
async def test_end_to_end_missing_api_key_fails_fast(tmp_path, monkeypatch):
    """Test pipeline exits with code 1 when API key is missing and cities are not simulated."""
    empty_env = tmp_path / ".env.empty"
    empty_env.write_text("", encoding="utf-8")
    monkeypatch.setenv("OPENWEATHER_API_KEY", "")

    input_file = tmp_path / "orders.json"
    input_file.write_text(json.dumps(FOUR_ORDERS_SAMPLE), encoding="utf-8")

    exit_code = await run_pipeline(
        file_path=str(input_file),
        env_file=empty_env,
    )
    assert exit_code == 1

