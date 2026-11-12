"""Unit tests for apology message generation."""

from weather_checker.apology import generate_apology, generate_template_apology
from weather_checker.models import Order, WeatherData


def test_template_apology_format():
    msg = generate_template_apology("Alice", "New York", "heavy rain")
    assert msg == "Hi Alice, your order to New York is delayed due to heavy rain. We appreciate your patience!"


def test_generate_apology_pure_function():
    order = Order(
        order_id="1001",
        customer="Alice Smith",
        city="New York",
        status="Pending",
    )
    weather = WeatherData(
        city="New York",
        main="Rain",
        description="heavy rain",
    )
    msg = generate_apology(order, weather)
    assert msg == "Hi Alice, your order to New York is delayed due to heavy rain. We appreciate your patience!"


def test_generate_apology_snow():
    order = Order(
        order_id="1003",
        customer="Charlie Green",
        city="London",
        status="Pending",
    )
    weather = WeatherData(
        city="London",
        main="Snow",
        description="blizzard conditions",
    )
    msg = generate_apology(order, weather)
    assert msg == "Hi Charlie, your order to London is delayed due to blizzard conditions. We appreciate your patience!"


def test_generate_apology_llm_success_override():
    order = Order(
        order_id="1002",
        customer="Bob Jones",
        city="Mumbai",
        status="Pending",
    )
    weather = WeatherData(
        city="Mumbai",
        main="Rain",
        description="monsoon downpour",
    )

    def mock_llm(name: str, city: str, desc: str) -> str:
        return f"Greetings {name}! Unfortunately, extreme {desc} in {city} has slowed down our couriers."

    msg = generate_apology(order, weather, use_llm=True, llm_generator=mock_llm)
    assert "Greetings Bob!" in msg
    assert "monsoon downpour in Mumbai" in msg


def test_generate_apology_llm_failure_falls_back_to_template():
    order = Order(
        order_id="1002",
        customer="Bob Jones",
        city="Mumbai",
        status="Pending",
    )
    weather = WeatherData(
        city="Mumbai",
        main="Rain",
        description="thunderstorm",
    )

    def failing_llm(name: str, city: str, desc: str) -> str:
        raise RuntimeError("API quota exceeded")

    msg = generate_apology(order, weather, use_llm=True, llm_generator=failing_llm)
    assert msg == "Hi Bob, your order to Mumbai is delayed due to thunderstorm. We appreciate your patience!"
