# AI Development Log

This document records the prompts, architectural decisions, and strategies used to design and implement the **weather-delay-checker** CLI tool, specifically focusing on **Parallel Fetching**, **Error Handling**, and **Resilience**.

---

## 1. Parallel Fetching Logic

### Objective
Fetch current weather for all cities in `orders.json` concurrently using Python's `asyncio` and `httpx.AsyncClient`, avoiding sequential loops, while preventing socket exhaustion through bounded concurrency.

### Prompts & Directives Used
```text
Prompt Directive:
"Design a concurrent weather-fetching pipeline in Python using asyncio and httpx.
Requirements:
1. Concurrency: Trigger all city weather requests in parallel using asyncio.gather.
2. Deduplication: If multiple orders target the same city (e.g. 5 orders to London),
   query OpenWeatherMap API only once for that unique city.
3. Concurrency Ceiling: Bound the maximum simultaneous network requests using an
   asyncio.Semaphore (configurable default 10).
4. Measure and log the total elapsed time of the concurrent batch to demonstrate
   and verify true parallelism in logs/run.log."
```

### Implementation Summary
- **Deduplication**: `fetch_all_cities` extracts unique city names into an ordered set before initiating network tasks.
- **Concurrency Limiter**: An `asyncio.Semaphore(max_concurrency)` wraps each HTTP request within an `async with semaphore:` block.
- **Batch Dispatch**: All task coroutines are launched simultaneously via `asyncio.gather(*tasks, return_exceptions=True)`.
- **Timing Log**: `time.perf_counter()` captures start and finish timestamps to log:
  `Completed concurrent weather fetch for N cities in X.XXXs`.

---

## 2. Error Handling & Resilience Logic

### Objective
Ensure bad or non-existent cities (such as `InvalidCity123` returning HTTP 404) do not crash the application, while transient network errors (HTTP 429 rate limits, 5xx server issues, timeouts) are retried gracefully.

### Prompts & Directives Used
```text
Prompt Directive:
"Implement production-grade resilience and error-handling for OpenWeatherMap API requests:
1. Result Typing: Per-task try/except returning a typed result (CityWeatherResult)
   encapsulating success status, weather data, HTTP status code, and error messages.
2. HTTP 404 Handling: If OpenWeatherMap returns 404 (City Not Found), log it as an ERROR
   and return a failed result. The task must NOT raise an unhandled exception or crash
   sibling tasks.
3. Retry Strategy: Implement exponential backoff with random jitter for transient errors:
   - Retry ONLY on HTTP 429, HTTP 5xx, httpx.TimeoutException, and httpx.NetworkError.
   - NEVER retry HTTP 401 (Unauthorized) or HTTP 404 (Not Found).
   - Maximum 3 attempts with formula: (backoff_factor * 2^(attempt-1)) + jitter.
4. Backstop: Use return_exceptions=True in asyncio.gather to ensure unhandled runtime
   exceptions never terminate other concurrent tasks."
```

### Implementation Summary
- **Typed Result Model (`CityWeatherResult`)**: Returned by every coroutine. Sibling orders continue regardless of individual failures.
- **Differentiated HTTP Handling**:
  - `404`: Non-retryable. Logged as `City '...' not found in OpenWeatherMap (HTTP 404)`.
  - `401`: Non-retryable. Logged as `Authentication failed (HTTP 401)`.
  - `429 / 5xx / Timeouts`: Retryable with exponential backoff and jitter.
- **Order State Preservation**: Orders targeting invalid cities maintain their original `Pending` status and store the exact reason in `order.weather_error`.

---

## 3. Weather-Aware Apology & LLM Integration

### Objective
Generate personalized apology messages using customer first name and weather description, with an optional `--llm` flag that falls back to the deterministic template on failure.

### Prompts & Directives Used
```text
Prompt Directive:
"Create a pure function generate_apology(order, weather) -> str:
1. Extract customer's first name (split on whitespace).
2. Incorporate order city and specific weather description (e.g. 'heavy rain', 'blizzard').
3. Template: 'Hi {first_name}, your order to {city} is delayed due to {description}. We appreciate your patience!'
4. Support an optional --llm mode: if LLM generation fails or is unconfigured,
   gracefully log a warning and fall back to the deterministic template."
```

---

## 4. User Prompt Log (Paste Your Prompts Here)

> [!NOTE]
> This section is reserved for the user to append any interactive prompts, review notes, or additional iterations used during the assignment.

### Prompts:
```text
<!-- Paste your additional prompts here -->

```
