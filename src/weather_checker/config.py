"""Configuration and environment management for weather delay checker."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Set
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


# Default weather categories that trigger delays:
# Rain, Snow, plus extreme atmospheric conditions.
# Note: "Extreme" is included for backward compatibility with older OWM schemas,
# while modern OpenWeatherMap uses "Thunderstorm", "Squall", "Tornado", "Ash".
DEFAULT_DELAY_CONDITIONS: frozenset[str] = frozenset({
    "Rain",
    "Snow",
    "Extreme",
    "Thunderstorm",
    "Squall",
    "Tornado",
    "Ash",
})


class ConfigError(Exception):
    """Raised when application configuration or credentials are missing/invalid."""


class Settings(BaseModel):
    """Application configuration settings."""

    api_key: Optional[str] = Field(
        default=None,
        description="OpenWeatherMap API key (from OPENWEATHER_API_KEY)",
    )
    api_base_url: str = Field(
        default="https://api.openweathermap.org/data/2.5/weather",
        description="OpenWeatherMap API endpoint",
    )
    max_concurrency: int = Field(
        default=10,
        ge=1,
        description="Maximum concurrent HTTP requests",
    )
    request_timeout: float = Field(
        default=10.0,
        gt=0.0,
        description="HTTP request timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retry attempts on retryable errors",
    )
    backoff_factor: float = Field(
        default=0.5,
        ge=0.0,
        description="Base backoff factor in seconds",
    )
    delay_conditions: Set[str] = Field(
        default_factory=lambda: set(DEFAULT_DELAY_CONDITIONS),
        description="Set of weather condition 'main' values that cause delays",
    )

    @field_validator("delay_conditions", mode="before")
    @classmethod
    def parse_delay_conditions(cls, v: object) -> Set[str]:
        if isinstance(v, str):
            items = [item.strip() for item in v.split(",") if item.strip()]
            return set(items)
        if isinstance(v, (set, list, tuple)):
            return {str(item).strip() for item in v if str(item).strip()}
        return set(DEFAULT_DELAY_CONDITIONS)

    def require_api_key(self) -> str:
        """Validate that the API key is present and non-empty, or raise ConfigError."""
        if not self.api_key or not self.api_key.strip():
            raise ConfigError(
                "OpenWeatherMap API key is missing. Please set OPENWEATHER_API_KEY in "
                "your .env file or environment variables. (See .env.example for details)"
            )
        return self.api_key.strip()


def load_settings(
    env_file: Optional[Path | str] = None,
    api_key: Optional[str] = None,
    max_concurrency: Optional[int] = None,
    request_timeout: Optional[float] = None,
    delay_conditions: Optional[Set[str] | str] = None,
) -> Settings:
    """Load settings from .env file, environment variables, and explicit overrides."""
    # Load .env file if it exists or if explicitly provided
    if env_file:
        load_dotenv(dotenv_path=env_file, override=False)
    else:
        load_dotenv(override=False)

    resolved_api_key = api_key or os.getenv("OPENWEATHER_API_KEY")
    resolved_concurrency = max_concurrency or int(
        os.getenv("WEATHER_MAX_CONCURRENCY", "10")
    )
    resolved_timeout = request_timeout or float(
        os.getenv("WEATHER_REQUEST_TIMEOUT", "10.0")
    )

    env_conditions = os.getenv("WEATHER_DELAY_CONDITIONS")
    resolved_conditions = delay_conditions or env_conditions or DEFAULT_DELAY_CONDITIONS

    return Settings(
        api_key=resolved_api_key,
        max_concurrency=resolved_concurrency,
        request_timeout=resolved_timeout,
        delay_conditions=resolved_conditions,
    )
