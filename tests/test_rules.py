"""Unit tests for business delay rules."""

from weather_checker.models import CityWeatherResult, Order, WeatherData
from weather_checker.rules import evaluate_order, is_delay_condition


def test_is_delay_condition():
    assert is_delay_condition(WeatherData(city="NYC", main="Rain", description="light rain")) is True
    assert is_delay_condition(WeatherData(city="NYC", main="Snow", description="snow")) is True
    assert is_delay_condition(WeatherData(city="NYC", main="Thunderstorm", description="storm")) is True
    assert is_delay_condition(WeatherData(city="NYC", main="Tornado", description="tornado")) is True
    assert is_delay_condition(WeatherData(city="NYC", main="Squall", description="squall")) is True
    assert is_delay_condition(WeatherData(city="NYC", main="Ash", description="volcanic ash")) is True
    assert is_delay_condition(WeatherData(city="NYC", main="Clear", description="clear sky")) is False
    assert is_delay_condition(WeatherData(city="NYC", main="Clouds", description="few clouds")) is False


def test_custom_delay_conditions():
    custom = {"Fog", "Haze"}
    assert is_delay_condition(WeatherData(city="NYC", main="Fog", description="dense fog"), custom) is True
    assert is_delay_condition(WeatherData(city="NYC", main="Rain", description="rain"), custom) is False


def test_evaluate_order_delays_on_rain():
    order = Order(
        order_id="1001",
        customer="Alice Smith",
        city="New York",
        status="Pending",
    )
    weather_result = CityWeatherResult(
        city="New York",
        success=True,
        weather=WeatherData(city="New York", main="Rain", description="heavy rain"),
    )

    evaluated = evaluate_order(order, weather_result)
    assert evaluated.status == "Delayed"
    assert evaluated.delay_reason is not None
    assert "Rain" in evaluated.delay_reason
    assert evaluated.apology_message is not None
    assert "Hi Alice" in evaluated.apology_message
    assert evaluated.weather_error is None


def test_evaluate_order_unchanged_on_clear_weather():
    order = Order(
        order_id="1003",
        customer="Charlie Green",
        city="London",
        status="Pending",
    )
    weather_result = CityWeatherResult(
        city="London",
        success=True,
        weather=WeatherData(city="London", main="Clear", description="sunny"),
    )

    evaluated = evaluate_order(order, weather_result)
    assert evaluated.status == "Pending"
    assert evaluated.delay_reason is None
    assert evaluated.apology_message is None
    assert evaluated.weather_error is None


def test_evaluate_order_on_404_error():
    order = Order(
        order_id="1004",
        customer="InvalidCity123",
        city="InvalidCity123",
        status="Pending",
    )
    weather_result = CityWeatherResult(
        city="InvalidCity123",
        success=False,
        status_code=404,
        error_message="City 'InvalidCity123' not found (HTTP 404)",
    )

    evaluated = evaluate_order(order, weather_result)
    assert evaluated.status == "Pending"
    assert evaluated.delay_reason is None
    assert evaluated.apology_message is None
    assert evaluated.weather_error == "City 'InvalidCity123' not found (HTTP 404)"
