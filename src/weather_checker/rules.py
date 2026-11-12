"""Weather delay business rules."""

from __future__ import annotations

import logging
from typing import Optional, Set

from weather_checker.apology import generate_apology
from weather_checker.config import DEFAULT_DELAY_CONDITIONS
from weather_checker.models import (
    CityWeatherResult,
    Order,
    OrderStatus,
    WeatherData,
)

logger = logging.getLogger("weather_checker.rules")


def is_delay_condition(
    weather: WeatherData,
    delay_conditions: Set[str] = DEFAULT_DELAY_CONDITIONS,
) -> bool:
    """Check whether a weather condition matches configured delay triggers.

    Comparison is case-insensitive.
    """
    normalized_conditions = {cond.lower() for cond in delay_conditions}
    return weather.main.strip().lower() in normalized_conditions


def evaluate_order(
    order: Order,
    weather_result: Optional[CityWeatherResult],
    delay_conditions: Set[str] = DEFAULT_DELAY_CONDITIONS,
    use_llm_apology: bool = False,
) -> Order:
    """Evaluate an order against weather results, updating status, delay reason, or error.

    Rules:
    - If weather lookup failed or city not found:
        - Keep original status (e.g. "Pending")
        - Populate `order.weather_error`
        - Leave `delay_reason` and `apology_message` as None
    - If weather lookup succeeded:
        - If condition matches delay set:
            - Set status to "Delayed"
            - Populate `delay_reason` and `apology_message`
            - Clear `weather_error`
        - If condition does NOT match delay set:
            - Keep original status
            - Clear `delay_reason`, `apology_message`, and `weather_error`
    """
    # 1. Weather lookup failed / unavailable
    if weather_result is None or not weather_result.success or not weather_result.weather:
        error_msg = (
            weather_result.error_message
            if weather_result and weather_result.error_message
            else "Weather information could not be retrieved"
        )
        logger.warning(
            f"Order {order.order_id} ({order.city}): Weather lookup failed. "
            f"Preserving status='{order.status}', setting weather_error='{error_msg}'."
        )
        order.weather_error = error_msg
        order.delay_reason = None
        order.apology_message = None
        return order

    weather = weather_result.weather

    # 2. Weather is a delay condition
    if is_delay_condition(weather, delay_conditions):
        order.status = OrderStatus.DELAYED.value
        order.delay_reason = (
            f"Severe weather in {order.city}: {weather.main} ({weather.description})"
        )
        order.apology_message = generate_apology(
            order=order,
            weather=weather,
            use_llm=use_llm_apology,
        )
        order.weather_error = None
        logger.info(
            f"Order {order.order_id} ({order.city}): Status updated to 'Delayed'. "
            f"Reason: {weather.main} ({weather.description})"
        )
        return order

    # 3. Weather is clear / benign
    logger.info(
        f"Order {order.order_id} ({order.city}): Favorable weather ({weather.main}). "
        f"Status unchanged ('{order.status}')."
    )
    order.delay_reason = None
    order.apology_message = None
    order.weather_error = None
    return order
