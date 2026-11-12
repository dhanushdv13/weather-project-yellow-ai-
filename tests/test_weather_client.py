"""Tests for async weather client, retries, concurrency, and simulation overrides."""

import pytest
import respx
import httpx
from weather_checker.config import Settings
from weather_checker.weather_client import WeatherClient, parse_simulation_overrides


@pytest.fixture
def settings():
    return Settings(
        api_key="mock-api-key",
        api_base_url="https://api.openweathermap.org/data/2.5/weather",
        max_concurrency=5,
        request_timeout=2.0,
        max_retries=3,
        backoff_factor=0.01,  # Fast backoff for tests
    )


@pytest.mark.asyncio
@respx.mock
async def test_fetch_weather_200_rain(settings):
    respx.get("https://api.openweathermap.org/data/2.5/weather").respond(
        status_code=200,
        json={
            "name": "New York",
            "weather": [{"id": 501, "main": "Rain", "description": "heavy intensity rain"}],
            "main": {"temp": 14.5},
        },
    )

    client = WeatherClient(settings)
    results = await client.fetch_all_cities(["New York"])

    assert "new york" in results
    result = results["new york"]
    assert result.success is True
    assert result.weather is not None
    assert result.weather.main == "Rain"
    assert result.weather.description == "heavy intensity rain"
    assert result.weather.temp == 14.5


@pytest.mark.asyncio
@respx.mock
async def test_fetch_weather_200_clear(settings):
    respx.get("https://api.openweathermap.org/data/2.5/weather").respond(
        status_code=200,
        json={
            "name": "London",
            "weather": [{"id": 800, "main": "Clear", "description": "clear sky"}],
            "main": {"temp": 18.0},
        },
    )

    client = WeatherClient(settings)
    results = await client.fetch_all_cities(["London"])

    assert "london" in results
    result = results["london"]
    assert result.success is True
    assert result.weather is not None
    assert result.weather.main == "Clear"
    assert result.weather.description == "clear sky"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_weather_404_invalid_city(settings):
    respx.get("https://api.openweathermap.org/data/2.5/weather").respond(
        status_code=404,
        json={"cod": "404", "message": "city not found"},
    )

    client = WeatherClient(settings)
    results = await client.fetch_all_cities(["InvalidCity123"])

    assert "invalidcity123" in results
    result = results["invalidcity123"]
    assert result.success is False
    assert result.status_code == 404
    assert result.is_not_found is True
    assert "not found" in (result.error_message or "").lower()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_weather_429_retry_then_success(settings):
    route = respx.get("https://api.openweathermap.org/data/2.5/weather")
    route.side_effect = [
        httpx.Response(429, json={"message": "Too Many Requests"}),
        httpx.Response(
            200,
            json={
                "name": "Mumbai",
                "weather": [{"id": 500, "main": "Rain", "description": "light rain"}],
                "main": {"temp": 28.0},
            },
        ),
    ]

    client = WeatherClient(settings)
    results = await client.fetch_all_cities(["Mumbai"])

    assert "mumbai" in results
    result = results["mumbai"]
    assert result.success is True
    assert result.weather is not None
    assert result.weather.main == "Rain"
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_fetch_weather_timeout_retry_then_failure(settings):
    route = respx.get("https://api.openweathermap.org/data/2.5/weather")
    route.side_effect = [
        httpx.ReadTimeout("Timeout 1"),
        httpx.ReadTimeout("Timeout 2"),
        httpx.ReadTimeout("Timeout 3"),
    ]

    client = WeatherClient(settings)
    results = await client.fetch_all_cities(["Tokyo"])

    assert "tokyo" in results
    result = results["tokyo"]
    assert result.success is False
    assert "timed out" in (result.error_message or "").lower()
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_city_deduplication(settings):
    route = respx.get("https://api.openweathermap.org/data/2.5/weather").respond(
        status_code=200,
        json={
            "name": "Paris",
            "weather": [{"id": 800, "main": "Clear", "description": "clear sky"}],
        },
    )

    client = WeatherClient(settings)
    # City listed 3 times
    results = await client.fetch_all_cities(["Paris", "Paris", "paris "])

    assert "paris" in results
    assert results["paris"].success is True
    # Verify the API was only called once!
    assert route.call_count == 1


def test_simulation_overrides_parsing():
    parsed = parse_simulation_overrides("Mumbai=Rain,London=Snow:heavy blizzard,InvalidCity=404")
    assert "mumbai" in parsed
    assert parsed["mumbai"].success is True
    assert parsed["mumbai"].weather.main == "Rain"
    assert parsed["mumbai"].weather.description == "rain"

    assert "london" in parsed
    assert parsed["london"].success is True
    assert parsed["london"].weather.main == "Snow"
    assert parsed["london"].weather.description == "heavy blizzard"

    assert "invalidcity" in parsed
    assert parsed["invalidcity"].success is False
    assert parsed["invalidcity"].status_code == 404
    assert parsed["invalidcity"].is_not_found is True


@pytest.mark.asyncio
async def test_simulation_bypasses_http(settings):
    # No respx route registered; if HTTP is called it would fail
    simulated = parse_simulation_overrides("London=Snow:blizzard")
    client = WeatherClient(settings, simulation_overrides=simulated)

    results = await client.fetch_all_cities(["London"])
    assert results["london"].success is True
    assert results["london"].weather.main == "Snow"
    assert results["london"].weather.description == "blizzard"
