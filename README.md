# Weather Delay Checker (`weather-delay-checker`)

A production-grade, asynchronous Python CLI tool that ingests an `orders.json` database, queries the **OpenWeatherMap API (Free Tier)** concurrently, flags orders for delivery delays caused by adverse weather, generates personalized weather-aware customer apologies, and persists the results atomically.

---

## Table of Contents
1. [Key Features](#key-features)
2. [Architecture & Project Layout](#architecture--project-layout)
3. [The "Extreme" Weather Note](#the-extreme-weather-note)
4. [Installation & Setup](#installation--setup)
5. [Usage Guide](#usage-guide)
   - [Live API Execution](#1-live-api-execution)
   - [Simulation Mode (Offline Demo)](#2-simulation-mode-offline-demo)
   - [LLM-Enhanced Apology Mode](#3-llm-enhanced-apology-mode)
   - [Custom Concurrency and Delay Rules](#4-custom-concurrency-and-delay-rules)
6. [Resilience & Concurrency Design](#resilience--concurrency-design)
7. [Testing](#testing)

---

## Key Features

- **True Parallel Fetching**: Concurrently queries weather for all destinations using `asyncio` and `httpx.AsyncClient` orchestrated via `asyncio.gather(return_exceptions=True)`.
- **Deduplication & Bounded Concurrency**: Eliminates redundant network calls by querying each unique city at most once, with parallelism guarded by an `asyncio.Semaphore` (default: 10 concurrent requests).
- **Golden Flow Delay Logic**: Flags orders as `Delayed` when weather conditions match configured thresholds (`Rain`, `Snow`, `Thunderstorm`, `Squall`, `Tornado`, `Ash`).
- **Weather-Aware Apology**: Pure function formatting personalized apologies using the customer's first name and specific weather condition descriptions (e.g., *"Hi Alice, your order to New York is delayed due to heavy rain. We appreciate your patience!"*).
- **Resilience & Retry Policies**:
  - Non-retryable errors (e.g. `InvalidCity123` HTTP 404, HTTP 401 unauthorized) fail immediately, are logged as errors, and do **not** crash the pipeline.
  - Retryable errors (HTTP 429 rate limits, HTTP 5xx server errors, network read/connect timeouts) automatically retry with exponential backoff and jitter (up to 3 attempts).
  - Failed orders preserve their original status (`Pending`) and record a `weather_error` field.
- **Atomic File Storage**: Writes updated JSON to a temporary file in the target directory and executes an atomic POSIX replace (`os.replace`), preventing partial writes or corrupted state.
- **Simulation Mode**: Built-in `--simulate` CLI flag to override weather or simulate error responses without calling external APIs.
- **Zero-Secret Leakage**: Automatic secret masking via `logging.Filter` prevents API keys from appearing in console or `logs/run.log`.

---

## Architecture & Project Layout

```
weather-A2/
├── pyproject.toml              # Project metadata & console script definition
├── requirements.txt            # Pinned production dependencies
├── pytest.ini                  # Pytest configuration
├── .env.example                # Example environment file template
├── .gitignore                  # Git ignore rules (secrets, venv, logs)
├── orders.json                 # Order dataset (input and updated output)
├── README.md                   # Complete documentation
├── AI_LOG.md                   # AI prompt documentation & prompt records
├── logs/
│   └── run.log                 # Output log file
├── src/
│   └── weather_checker/
│       ├── __init__.py
│       ├── main.py             # CLI entrypoint, argument parsing, summary table
│       ├── config.py           # Settings management and .env validation
│       ├── models.py           # Pydantic schemas (Order, WeatherData, CityWeatherResult)
│       ├── logging_setup.py    # Structured logging with secret redaction
│       ├── weather_client.py   # Async HTTP client, retries, semaphore, deduplication
│       ├── rules.py            # Delay assessment and status assignment
│       ├── apology.py          # Weather-aware apology generation + LLM fallback
│       └── storage.py          # Atomic JSON read/write operations
└── tests/
    ├── __init__.py
    ├── test_models.py          # Tests for data models & first-name extraction
    ├── test_config.py          # Tests for environment loading & missing API key fail-fast
    ├── test_logging_setup.py   # Tests for secret redaction filter & log file writing
    ├── test_weather_client.py  # respx tests: 200 rain, 200 clear, 404, 429 retries, timeouts
    ├── test_rules.py           # Tests for delay rules and condition matching
    ├── test_apology.py         # Tests for pure apology function and LLM fallbacks
    ├── test_storage.py         # Tests for atomic file replacement
    └── test_end_to_end.py      # End-to-end integration tests on full 4-order dataset
```

---

## The "Extreme" Weather Note

> [!IMPORTANT]
> **OpenWeatherMap Condition Schema Note**:
> In earlier OpenWeatherMap API v2.5 documentation, an `Extreme` weather group (codes 900–906) existed. In modern OpenWeatherMap API v2.5/v3.0, severe weather conditions are categorized under specific groups:
> - **Group 2xx**: `Thunderstorm`
> - **Group 7xx (Atmosphere)**: `Squall` (771), `Tornado` (781), `Ash` (762)
> 
> Therefore, this tool configures `Extreme` as an alias alongside the actual standard OpenWeatherMap values:
> `DEFAULT_DELAY_CONDITIONS = {"Rain", "Snow", "Extreme", "Thunderstorm", "Squall", "Tornado", "Ash"}`
>
> Users can customize or override this set using the `--delay-conditions` flag or `WEATHER_DELAY_CONDITIONS` in `.env`.

---

## Installation & Setup

### Prerequisites
- Python 3.9+ (Python 3.14 tested)
- A free OpenWeatherMap API key from [openweathermap.org](https://openweathermap.org/api)

### 1. Clone & create virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
pip install -e .
```

### 3. Configure credentials
Copy `.env.example` to `.env` and enter your API key:
```bash
cp .env.example .env
```
Edit `.env`:
```ini
OPENWEATHER_API_KEY=your_actual_api_key_here
```

---

## Usage Guide

### 1. Live API Execution
Run against the default `orders.json` using live OpenWeatherMap queries:
```bash
weather-delay-checker orders.json
```
*(Or via python module invocation: `python -m weather_checker.main orders.json`)*

**Sample Terminal Output:**
```
                          Order Weather Delay Summary                           
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Order ID┃ Customer        ┃ City          ┃ Weather Condition   ┃ Status    ┃ Notes / Delay Details          ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1001    │ Alice Smith     │ New York      │ Rain (heavy rain)   │ Delayed   │ Severe weather in New York     │
│         │                 │               │                     │           │ Hi Alice, your order to New... │
│ 1002    │ Bob Jones       │ Mumbai        │ Clear (clear sky)   │ Pending   │ Favorable weather - on schedule│
│ 1003    │ Charlie Green   │ London        │ Snow (light snow)   │ Delayed   │ Severe weather in London       │
│         │                 │               │                     │           │ Hi Charlie, your order to...   │
│ 1004    │ InvalidCity123  │ InvalidCity123│ Error: City not f...│ Pending   │ Weather Lookup Failed: 404     │
└─────────┴─────────────────┴───────────────┴─────────────────────┴───────────┴────────────────━━━━━━━━━━━━━━━━┘
```

### 2. Simulation Mode (Offline Demo)
To demonstrate the delay path or test without consuming API quota:
```bash
weather-delay-checker orders.json --simulate "New York=Rain:heavy downpour,Mumbai=Clear:sunny,London=Snow:blizzard,InvalidCity123=404"
```

### 3. LLM-Enhanced Apology Mode
Enable optional generative apology messages with fallback to the pure template:
```bash
weather-delay-checker orders.json --llm
```

### 4. Custom Concurrency and Delay Rules
Limit concurrency to 3 simultaneous connections and trigger delays only on Snow:
```bash
weather-delay-checker orders.json --concurrency 3 --delay-conditions "Snow"
```

---

## Resilience & Concurrency Design

| Feature | Implementation | Guarantee |
|---|---|---|
| **Parallel Network Calls** | `asyncio.gather(*tasks, return_exceptions=True)` with `httpx.AsyncClient` | All calls fire concurrently; exceptions in one task cannot abort others |
| **City Deduplication** | Ordered unique set extraction | Multiple orders to the same city trigger only 1 external HTTP request |
| **Concurrency Ceiling** | `asyncio.Semaphore(max_concurrency)` | Protects against rate limits and socket exhaustion |
| **HTTP 404 (InvalidCity)**| Explicit status code branch | Logs error, populates `weather_error`, preserves order status, never crashes |
| **Transient Retries** | Exponential backoff (`2^(attempt-1) * backoff_factor + jitter`) on 429, 5xx, timeouts | Recovers from intermittent API hiccups; skips retries on 401/404 |
| **Atomic File Update** | `tempfile.NamedTemporaryFile` + `fsync` + `os.replace` | Atomic file swap guarantees no partial writes or corrupted files |
| **Credential Safety** | Custom `SecretFilter` attached to console & file handlers | Redacts API keys from log strings and query parameters |

---

## Testing

Run the comprehensive test suite with `pytest`:
```bash
pytest -v
```

All 37 test cases validate:
- 200 HTTP response with Rain triggers `Delayed` status, delay reason, and apology text.
- 200 HTTP response with Clear weather leaves order `Pending` without delay fields.
- 404 HTTP response for invalid cities logs error, marks `weather_error`, leaves status unchanged, and allows other orders to succeed.
- 429 HTTP rate-limit retries with backoff and succeeds on subsequent attempt.
- Network timeouts retry up to 3 times before recording typed failure.
- Missing API key fails fast with a clear, helpful message.
- Apology generator operates as a pure, deterministic function.
- Atomic file write avoids data loss and excludes unset fields.
- End-to-end processing of the full 4-order dataset.
