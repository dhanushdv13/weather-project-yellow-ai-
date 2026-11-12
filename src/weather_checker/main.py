"""CLI entry point for weather-delay-checker."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.table import Table

from weather_checker.config import ConfigError, load_settings
from weather_checker.logging_setup import setup_logging
from weather_checker.models import Order, OrderStatus
from weather_checker.rules import evaluate_order
from weather_checker.storage import StorageError, load_orders, save_orders_atomic
from weather_checker.weather_client import WeatherClient, parse_simulation_overrides


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="weather-delay-checker",
        description="Checks order delivery cities for weather delays and updates orders with apologies.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="orders.json",
        help="Path to orders.json file (default: orders.json)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Destination path for updated orders JSON (defaults to overwriting input file atomically)",
    )
    parser.add_argument(
        "--simulate",
        type=str,
        default=None,
        help="Simulate weather for cities without calling API (e.g. 'Mumbai=Rain,London=Snow')",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Enable LLM-enhanced apology generation (falls back to template on failure)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Maximum concurrent network requests (default: 10)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Network request timeout in seconds (default: 10.0)",
    )
    parser.add_argument(
        "--delay-conditions",
        type=str,
        default=None,
        help="Comma-separated weather conditions that trigger delays (e.g. 'Rain,Snow,Thunderstorm')",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Console logging verbosity (default: INFO)",
    )
    return parser


def display_summary_table(
    orders: List[Order],
    results_by_city: dict,
    console: Optional[Console] = None,
) -> None:
    """Render a terminal summary table of processed orders."""
    console = console or Console()
    table = Table(title="Order Weather Delay Summary", show_header=True, header_style="bold cyan")

    table.add_column("Order ID", style="bold", width=10)
    table.add_column("Customer", width=18)
    table.add_column("City", width=16)
    table.add_column("Weather Condition", width=22)
    table.add_column("Status", width=12)
    table.add_column("Notes / Delay Details", min_width=30)

    for order in orders:
        city_res = results_by_city.get(order.city.strip().lower())

        if city_res and city_res.success and city_res.weather:
            weather_str = f"{city_res.weather.main} ({city_res.weather.description})"
        elif city_res and not city_res.success:
            weather_str = f"[red]Error: {city_res.error_message}[/red]"
        else:
            weather_str = "Unknown"

        if order.status == OrderStatus.DELAYED.value:
            status_str = f"[bold red]{order.status}[/bold red]"
            notes_str = f"[yellow]{order.delay_reason}[/yellow]\n[italic]{order.apology_message}[/italic]"
        elif order.weather_error:
            status_str = f"[yellow]{order.status}[/yellow]"
            notes_str = f"[red]Weather Lookup Failed: {order.weather_error}[/red]"
        else:
            status_str = f"[green]{order.status}[/green]"
            notes_str = "[dim green]Favorable weather - on schedule[/dim green]"

        table.add_row(
            order.order_id,
            order.customer,
            order.city,
            weather_str,
            status_str,
            notes_str,
        )

    console.print()
    console.print(table)
    console.print()


async def run_pipeline(
    file_path: str,
    output_path: Optional[str] = None,
    simulate_arg: Optional[str] = None,
    use_llm: bool = False,
    concurrency: Optional[int] = None,
    timeout: Optional[float] = None,
    delay_conditions_arg: Optional[str] = None,
    log_level_str: str = "INFO",
) -> int:
    """Main async execution pipeline."""
    # 1. Load settings & configure logging
    level = getattr(logging, log_level_str.upper(), logging.INFO)
    settings = load_settings(
        max_concurrency=concurrency,
        request_timeout=timeout,
        delay_conditions=delay_conditions_arg,
    )
    logger = setup_logging(
        log_file="logs/run.log",
        level=level,
        secrets_to_mask=[settings.api_key] if settings.api_key else None,
    )

    logger.info("Starting weather-delay-checker...")

    # 2. Parse simulation overrides if any
    simulation_overrides = parse_simulation_overrides(simulate_arg)

    # 3. Read orders from input JSON
    try:
        orders = load_orders(file_path)
    except StorageError as err:
        logger.error(f"Cannot load orders: {err}")
        print(f"Error: {err}", file=sys.stderr)
        return 1

    if not orders:
        logger.warning(f"No orders found in {file_path}. Nothing to process.")
        return 0

    # 4. Check if API key is required
    # If all cities in the orders are covered by --simulate, we do not strictly require the API key.
    # Otherwise, validate and fail fast if missing.
    unsimulated_cities = [
        o.city.strip() for o in orders if o.city.strip().lower() not in simulation_overrides
    ]
    if unsimulated_cities:
        try:
            settings.require_api_key()
        except ConfigError as err:
            logger.error(str(err))
            print(f"\n[CONFIGURATION ERROR] {err}\n", file=sys.stderr)
            return 1

    # 5. Fetch weather for all cities concurrently
    client = WeatherClient(settings=settings, simulation_overrides=simulation_overrides)
    cities_to_fetch = [order.city for order in orders]
    results_by_city = await client.fetch_all_cities(cities_to_fetch)

    # 6. Apply business rules to evaluate orders
    updated_orders: List[Order] = []
    for order in orders:
        city_key = order.city.strip().lower()
        city_res = results_by_city.get(city_key)
        evaluated = evaluate_order(
            order=order,
            weather_result=city_res,
            delay_conditions=settings.delay_conditions,
            use_llm_apology=use_llm,
        )
        updated_orders.append(evaluated)

    # 7. Atomically save updated orders to output JSON
    dest_path = output_path or file_path
    try:
        save_orders_atomic(updated_orders, dest_path)
    except StorageError as err:
        logger.error(f"Failed to persist updated orders: {err}")
        print(f"Storage Error: {err}", file=sys.stderr)
        return 1

    # 8. Render terminal summary table
    display_summary_table(updated_orders, results_by_city)

    logger.info("weather-delay-checker finished successfully.")
    return 0


def main() -> None:
    """CLI synchronous entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()

    exit_code = asyncio.run(
        run_pipeline(
            file_path=args.file,
            output_path=args.output,
            simulate_arg=args.simulate,
            use_llm=args.llm,
            concurrency=args.concurrency,
            timeout=args.timeout,
            delay_conditions_arg=args.delay_conditions,
            log_level_str=args.log_level,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
