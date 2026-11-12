"""Async OpenWeatherMap client with concurrency control, deduplication, and retries."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Dict, List, Optional, Set
import httpx

from weather_checker.config import Settings
from weather_checker.models import CityWeatherResult, WeatherData

logger = logging.getLogger("weather_checker.weather_client")


def parse_simulation_overrides(simulate_arg: Optional[str]) -> Dict[str, CityWeatherResult]:
    """Parse a simulation argument string formatted as 'City1=Condition,City2=Condition:description'.

    Supports both weather conditions and simulated errors:
        'Mumbai=Rain,London=Snow'
        'Mumbai=Rain:heavy rain,London=Snow:blizzard'
        'InvalidCity123=404'
    """
    if not simulate_arg:
        return {}

    overrides: Dict[str, CityWeatherResult] = {}
    pairs = [p.strip() for p in simulate_arg.split(",") if p.strip()]

    for pair in pairs:
        if "=" not in pair:
            logger.warning(f"Invalid simulation format '{pair}', expected 'City=Condition'")
            continue
        city, condition_part = pair.split("=", 1)
        city = city.strip()
        condition_part = condition_part.strip()

        if ":" in condition_part:
            main, description = condition_part.split(":", 1)
            main = main.strip()
            description = description.strip()
        else:
            main = condition_part.strip()
            description = main.lower()

        # Check for simulated 404 / error condition
        if main.lower() in ("404", "notfound", "error"):
            error_desc = description if ":" in condition_part else f"City '{city}' not found (HTTP 404)"
            overrides[city.lower()] = CityWeatherResult(
                city=city,
                success=False,
                status_code=404,
                error_message=error_desc,
            )
            logger.info(f"Configured simulation error override for '{city}': HTTP 404")
        else:
            weather_data = WeatherData(
                city=city,
                main=main,
                description=description,
                temp=20.0,
                raw={"simulated": True},
            )
            overrides[city.lower()] = CityWeatherResult(
                city=city,
                success=True,
                weather=weather_data,
                status_code=200,
            )
            logger.info(
                f"Configured simulation override for '{city}': main='{main}', description='{description}'"
            )

    return overrides


class WeatherClient:
    """Async weather client with resilience, exponential backoff, and concurrency bounds."""

    def __init__(
        self,
        settings: Settings,
        simulation_overrides: Optional[Dict[str, CityWeatherResult]] = None,
    ) -> None:
        self.settings = settings
        self.simulation_overrides: Dict[str, CityWeatherResult] = simulation_overrides or {}

    async def fetch_city_weather(
        self,
        client: httpx.AsyncClient,
        city: str,
        semaphore: asyncio.Semaphore,
    ) -> CityWeatherResult:
        """Fetch weather for a single city with retries on transient errors."""
        cleaned_city = city.strip()

        # Check simulation override first (case-insensitive)
        if cleaned_city.lower() in self.simulation_overrides:
            sim_res = self.simulation_overrides[cleaned_city.lower()]
            if sim_res.success and sim_res.weather:
                logger.info(
                    f"Using simulated weather for '{cleaned_city}': "
                    f"{sim_res.weather.main} ({sim_res.weather.description})"
                )
            else:
                logger.info(
                    f"Using simulated error for '{cleaned_city}': {sim_res.error_message}"
                )
            return sim_res

        max_attempts = max(1, self.settings.max_retries)

        async with semaphore:
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.debug(f"Fetching weather for '{cleaned_city}' (attempt {attempt}/{max_attempts})")
                    response = await client.get(
                        self.settings.api_base_url,
                        params={
                            "q": cleaned_city,
                            "appid": self.settings.api_key,
                            "units": "metric",
                        },
                    )

                    if response.status_code == 200:
                        data = response.json()
                        weather_items = data.get("weather", [])
                        if not weather_items:
                            logger.error(f"Malformed response for '{cleaned_city}': missing 'weather' array")
                            return CityWeatherResult(
                                city=cleaned_city,
                                success=False,
                                error_message="Weather data unavailable in API response",
                            )

                        first_cond = weather_items[0]
                        main_cond = first_cond.get("main", "Unknown")
                        desc_cond = first_cond.get("description", main_cond.lower())
                        temp = data.get("main", {}).get("temp")

                        weather_data = WeatherData(
                            city=cleaned_city,
                            main=main_cond,
                            description=desc_cond,
                            temp=temp,
                            raw=data,
                        )
                        logger.info(
                            f"Successfully fetched weather for '{cleaned_city}': {main_cond} ({desc_cond})"
                        )
                        return CityWeatherResult(
                            city=cleaned_city,
                            success=True,
                            weather=weather_data,
                            status_code=200,
                        )

                    # 404: City not found - NON-RETRYABLE
                    if response.status_code == 404:
                        logger.error(f"City '{cleaned_city}' not found in OpenWeatherMap (HTTP 404)")
                        return CityWeatherResult(
                            city=cleaned_city,
                            success=False,
                            status_code=404,
                            error_message=f"City '{cleaned_city}' not found (HTTP 404)",
                        )

                    # 401: Unauthorized - NON-RETRYABLE
                    if response.status_code == 401:
                        logger.error("Authentication failed: invalid or missing OpenWeatherMap API key (HTTP 401)")
                        return CityWeatherResult(
                            city=cleaned_city,
                            success=False,
                            status_code=401,
                            error_message="Unauthorized: invalid OpenWeatherMap API key (HTTP 401)",
                        )

                    # 429 (Rate Limit) or 5xx (Server Error) - RETRYABLE
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < max_attempts:
                            delay = (self.settings.backoff_factor * (2 ** (attempt - 1))) + random.uniform(0.05, 0.2)
                            logger.warning(
                                f"HTTP {response.status_code} for city '{cleaned_city}' on attempt {attempt}/{max_attempts}. "
                                f"Retrying in {delay:.2f}s..."
                            )
                            await asyncio.sleep(delay)
                            continue
                        logger.error(
                            f"HTTP {response.status_code} for city '{cleaned_city}' after {max_attempts} attempts"
                        )
                        return CityWeatherResult(
                            city=cleaned_city,
                            success=False,
                            status_code=response.status_code,
                            error_message=f"HTTP {response.status_code} after {max_attempts} attempts",
                        )

                    # Any other HTTP status code
                    logger.error(f"Unexpected HTTP {response.status_code} for city '{cleaned_city}'")
                    return CityWeatherResult(
                        city=cleaned_city,
                        success=False,
                        status_code=response.status_code,
                        error_message=f"Unexpected HTTP {response.status_code}",
                    )

                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    # Timeout / Network error - RETRYABLE
                    if attempt < max_attempts:
                        delay = (self.settings.backoff_factor * (2 ** (attempt - 1))) + random.uniform(0.05, 0.2)
                        logger.warning(
                            f"Network/timeout error for '{cleaned_city}' ({type(exc).__name__}) on attempt "
                            f"{attempt}/{max_attempts}. Retrying in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                        continue
                    logger.error(
                        f"Network/timeout error for '{cleaned_city}' after {max_attempts} attempts: {exc}"
                    )
                    return CityWeatherResult(
                        city=cleaned_city,
                        success=False,
                        error_message=f"Request timed out/failed after {max_attempts} attempts: {exc}",
                    )
                except Exception as exc:
                    logger.exception(f"Unexpected exception fetching weather for '{cleaned_city}': {exc}")
                    return CityWeatherResult(
                        city=cleaned_city,
                        success=False,
                        error_message=f"Unexpected error: {exc}",
                    )

        # Fallback if loop finishes unexpectedly
        return CityWeatherResult(
            city=cleaned_city,
            success=False,
            error_message="Exhausted attempts without a definitive response",
        )

    async def fetch_all_cities(
        self,
        cities: List[str],
    ) -> Dict[str, CityWeatherResult]:
        """Fetch weather for all unique cities concurrently with bounded parallelism.

        Deduplicates cities so each unique city is queried at most once across all orders.
        """
        # Deduplicate unique cities while preserving appearance order
        unique_cities: List[str] = []
        seen: Set[str] = set()
        for c in cities:
            cleaned = c.strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                unique_cities.append(cleaned)

        logger.info(
            f"Initiating concurrent weather fetch for {len(unique_cities)} unique cities "
            f"(concurrency limit: {self.settings.max_concurrency})"
        )

        semaphore = asyncio.Semaphore(self.settings.max_concurrency)
        timeout = httpx.Timeout(self.settings.request_timeout)

        start_time = time.perf_counter()

        async with httpx.AsyncClient(timeout=timeout) as client:
            tasks = [
                self.fetch_city_weather(client, city, semaphore)
                for city in unique_cities
            ]
            # Concurrency requirement: asyncio.gather with return_exceptions=True as backstop
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed_time = time.perf_counter() - start_time
        logger.info(
            f"Completed concurrent weather fetch for {len(unique_cities)} cities in {elapsed_time:.3f}s"
        )

        results_by_city: Dict[str, CityWeatherResult] = {}
        for city, result in zip(unique_cities, raw_results):
            if isinstance(result, Exception):
                logger.error(f"Unhandled exception returned from task for '{city}': {result}")
                results_by_city[city.lower()] = CityWeatherResult(
                    city=city,
                    success=False,
                    error_message=f"Unhandled task error: {result}",
                )
            elif isinstance(result, CityWeatherResult):
                results_by_city[city.lower()] = result
            else:
                results_by_city[city.lower()] = CityWeatherResult(
                    city=city,
                    success=False,
                    error_message=f"Invalid result type: {type(result)}",
                )

        return results_by_city
