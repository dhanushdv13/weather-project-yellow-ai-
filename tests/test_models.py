"""Unit tests for data models."""

from weather_checker.models import (
    CityWeatherResult,
    Order,
    OrderStatus,
    WeatherData,
)


def test_order_creation_and_first_name():
    order = Order(
        order_id="1001",
        customer="Alice Smith",
        city="New York",
        status="Pending",
    )
    assert order.order_id == "1001"
    assert order.first_name == "Alice"
    assert order.status == OrderStatus.PENDING.value
    assert order.delay_reason is None
    assert order.apology_message is None
    assert order.weather_error is None


def test_order_first_name_single_word():
    order = Order(
        order_id="1004",
        customer="InvalidCity123",
        city="InvalidCity123",
        status="Pending",
    )
    assert order.first_name == "InvalidCity123"


def test_city_weather_result_success():
    weather = WeatherData(
        city="London",
        main="Rain",
        description="light rain",
    )
    result = CityWeatherResult(city="London", success=True, weather=weather)
    assert result.success is True
    assert result.weather is not None
    assert result.weather.main == "Rain"
    assert result.is_not_found is False


def test_city_weather_result_404():
    result = CityWeatherResult(
        city="InvalidCity123",
        success=False,
        error_message="City not found",
        status_code=404,
    )
    assert result.success is False
    assert result.is_not_found is True
