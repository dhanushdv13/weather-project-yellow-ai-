"""Unit tests for configuration and environment settings."""

import pytest
from weather_checker.config import (
    DEFAULT_DELAY_CONDITIONS,
    ConfigError,
    Settings,
    load_settings,
)


def test_default_settings():
    settings = Settings()
    assert settings.max_concurrency == 10
    assert settings.request_timeout == 10.0
    assert "Rain" in settings.delay_conditions
    assert "Snow" in settings.delay_conditions
    assert "Thunderstorm" in settings.delay_conditions


def test_missing_api_key_raises_config_error():
    settings = Settings(api_key=None)
    with pytest.raises(ConfigError) as exc_info:
        settings.require_api_key()
    assert "OpenWeatherMap API key is missing" in str(exc_info.value)

    empty_settings = Settings(api_key="   ")
    with pytest.raises(ConfigError) as exc_info:
        empty_settings.require_api_key()
    assert "OpenWeatherMap API key is missing" in str(exc_info.value)


def test_valid_api_key():
    settings = Settings(api_key="test-api-key-12345")
    assert settings.require_api_key() == "test-api-key-12345"


def test_custom_delay_conditions_string():
    settings = Settings(delay_conditions="Rain,Snow,Fog")  # type: ignore[arg-type]
    assert settings.delay_conditions == {"Rain", "Snow", "Fog"}


def test_load_settings_with_env(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "env-key-999")
    monkeypatch.setenv("WEATHER_MAX_CONCURRENCY", "5")
    monkeypatch.setenv("WEATHER_REQUEST_TIMEOUT", "15.5")
    monkeypatch.setenv("WEATHER_DELAY_CONDITIONS", "Rain,Squall")

    settings = load_settings()
    assert settings.api_key == "env-key-999"
    assert settings.max_concurrency == 5
    assert settings.request_timeout == 15.5
    assert settings.delay_conditions == {"Rain", "Squall"}
