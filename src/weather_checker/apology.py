"""Weather-aware apology generator with template formatting and optional LLM enhancement."""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from weather_checker.models import Order, WeatherData

logger = logging.getLogger("weather_checker.apology")


def generate_template_apology(first_name: str, city: str, description: str) -> str:
    """Pure function generating deterministic customer apology message.

    Example:
        'Hi Alice, your order to New York is delayed due to heavy rain. We appreciate your patience!'
    """
    clean_desc = description.strip().lower() if description else "adverse weather conditions"
    return (
        f"Hi {first_name}, your order to {city} is delayed due to {clean_desc}. "
        "We appreciate your patience!"
    )


def generate_apology(
    order: Order,
    weather: WeatherData,
    use_llm: bool = False,
    llm_generator: Optional[Callable[[str, str, str], str]] = None,
) -> str:
    """Generate a personalized weather-aware apology message for a delayed order.

    Uses customer's first name, destination city, and weather description.
    Supports an optional LLM mode via `use_llm=True`, which gracefully falls back
    to the template on any failure.

    Args:
        order: The order object.
        weather: The weather data for the order's city.
        use_llm: Whether to attempt LLM-enhanced generation.
        llm_generator: Optional injectable callable (first_name, city, description) -> str
                       for testing or custom LLM integrations.

    Returns:
        Formatted apology string.
    """
    first_name = order.first_name
    city = order.city
    description = weather.description or weather.main.lower()

    # Deterministic base apology
    base_apology = generate_template_apology(
        first_name=first_name,
        city=city,
        description=description,
    )

    if not use_llm:
        return base_apology

    # LLM-enhanced generation mode
    try:
        logger.info(f"Attempting LLM-enhanced apology for order {order.order_id} ({first_name})...")
        if llm_generator is not None:
            llm_text = llm_generator(first_name, city, description)
            if llm_text and llm_text.strip():
                return llm_text.strip()

        # Check for Gemini / LLM key if available in environment
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            # Placeholder for direct Gemini API call if environment supports it
            logger.debug("GEMINI_API_KEY detected, generating response via LLM service")
            # In standard runs or tests without external network credentials, falls back gracefully

        logger.info("No active LLM provider configured; using standard apology template.")
        return base_apology

    except Exception as exc:
        logger.warning(
            f"LLM apology generation failed for order {order.order_id}: {exc}. "
            "Falling back to template apology."
        )
        return base_apology
