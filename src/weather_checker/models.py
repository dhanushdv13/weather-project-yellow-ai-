"""Data models for weather delay checker."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class OrderStatus(str, Enum):
    """Possible order statuses."""

    PENDING = "Pending"
    DELAYED = "Delayed"
    PROCESSING = "Processing"
    SHIPPED = "Shipped"
    DELIVERED = "Delivered"


class Order(BaseModel):
    """Representation of an e-commerce order."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    order_id: str = Field(..., description="Unique order identifier")
    customer: str = Field(..., description="Customer full name")
    city: str = Field(..., description="Destination city name")
    status: str = Field(default=OrderStatus.PENDING.value, description="Order status")
    delay_reason: Optional[str] = Field(
        default=None, description="Explanation for delivery delay if applicable"
    )
    apology_message: Optional[str] = Field(
        default=None, description="Personalized apology message if delayed"
    )
    weather_error: Optional[str] = Field(
        default=None, description="Error encountered during weather lookup if any"
    )

    @property
    def first_name(self) -> str:
        """Extract first name from customer name, falling back to full string."""
        parts = self.customer.strip().split()
        return parts[0] if parts else self.customer


class WeatherCondition(BaseModel):
    """OpenWeatherMap weather item schema."""

    id: Optional[int] = None
    main: str = Field(..., description="Weather condition category (e.g. Rain, Snow)")
    description: str = Field(..., description="Detailed description (e.g. heavy rain)")
    icon: Optional[str] = None


class WeatherData(BaseModel):
    """Normalized weather information for a city."""

    city: str = Field(..., description="City name queried")
    main: str = Field(..., description="Primary weather condition (e.g. Rain, Clear)")
    description: str = Field(
        ..., description="Human-readable weather description (e.g. heavy rain)"
    )
    temp: Optional[float] = Field(default=None, description="Temperature if available")
    raw: Optional[dict[str, Any]] = Field(
        default=None, description="Raw API response data"
    )


class CityWeatherResult(BaseModel):
    """Typed result of a weather lookup task for resilience and error handling."""

    city: str = Field(..., description="City name queried")
    success: bool = Field(..., description="True if weather fetch succeeded")
    weather: Optional[WeatherData] = Field(
        default=None, description="Fetched weather data if successful"
    )
    error_message: Optional[str] = Field(
        default=None, description="Descriptive error message on failure"
    )
    status_code: Optional[int] = Field(
        default=None, description="HTTP status code if an HTTP error occurred"
    )

    @property
    def is_not_found(self) -> bool:
        """Convenience property to check for HTTP 404 (city not found)."""
        return self.status_code == 404
