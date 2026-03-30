"""
Currency conversion utilities.
"""
import os
import threading
import time
import warnings

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# Hardcoded fallback rates: 1 USD = X foreign (same convention as live API)
_FALLBACK_RATES = {
    "USD": 1.0,
    "PHP": 55.56,       # 1 USD = ~55.56 PHP
    "EUR": 0.926,       # 1 USD = ~0.926 EUR
    "GBP": 0.787,       # 1 USD = ~0.787 GBP
    "CNY": 7.143,       # 1 USD = ~7.143 CNY
    "JPY": 149.25,      # 1 USD = ~149.25 JPY
    "KRW": 1333.33,     # 1 USD = ~1333.33 KRW
    "INR": 83.33,       # 1 USD = ~83.33 INR
}

_cache_lock = threading.Lock()
_live_cache: dict = {}
_CACHE_TTL = 3600       # 1 hour
_NEGATIVE_CACHE_TTL = 60  # retry after 60s on failure


def _fetch_live_rates() -> dict | None:
    """Try to fetch live USD rates from exchangerate-api (free tier).

    Requires the `requests` package and optionally an EXCHANGERATE_API_KEY
    env var for higher limits. Returns None on any failure.
    """
    if not _HAS_REQUESTS:
        return None

    api_key = os.environ.get("EXCHANGERATE_API_KEY")
    if api_key:
        url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/USD"
    else:
        url = "https://open.er-api.com/v6/latest/USD"

    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result") == "success":
            return data.get("conversion_rates") or data.get("rates")
    except Exception:
        pass
    return None


def _get_rates() -> dict:
    """Return exchange rates, preferring live data with staleness warning fallback."""
    now = time.time()

    with _cache_lock:
        cached_rates = _live_cache.get("rates")
        fetched_at = _live_cache.get("fetched_at", 0)
        failed_at = _live_cache.get("failed_at", 0)

    # Return cached live rates if fresh
    if cached_rates and now - fetched_at < _CACHE_TTL:
        return cached_rates

    # Skip fetch if we failed recently (negative cache)
    if not cached_rates and failed_at and now - failed_at < _NEGATIVE_CACHE_TTL:
        return _FALLBACK_RATES

    # Try fetching live rates
    live = _fetch_live_rates()
    if live:
        with _cache_lock:
            _live_cache["rates"] = live
            _live_cache["fetched_at"] = now
            _live_cache.pop("failed_at", None)
        return live

    # Record failure to avoid retry storms
    with _cache_lock:
        _live_cache["failed_at"] = now

    warnings.warn(
        "Using hardcoded exchange rates (March 2026). Set EXCHANGERATE_API_KEY "
        "or install `requests` for live rates.",
        stacklevel=3,
    )
    return _FALLBACK_RATES


def convert_to_usd(amount: float, from_currency: str) -> float:
    """
    Convert an amount to USD.

    Args:
        amount: The amount to convert
        from_currency: Source currency code (e.g., "PHP", "EUR")

    Returns:
        Amount in USD
    """
    currency = from_currency.upper()
    if currency == "USD":
        return round(amount, 2)

    rates = _get_rates()

    # All rates use "1 USD = X foreign" convention, so: USD = amount / rate
    rate = rates.get(currency)
    if rate and rate != 0:
        return round(amount / rate, 2)

    # Unknown currency — return as-is rather than silently assuming 1:1
    warnings.warn(f"Unknown currency '{from_currency}', returning amount as-is", stacklevel=2)
    return round(amount, 2)


def get_currency_symbol(currency: str) -> str:
    """Get the symbol for a currency code."""
    symbols = {
        "USD": "$",
        "PHP": "₱",
        "EUR": "€",
        "GBP": "£",
        "CNY": "¥",
        "JPY": "¥",
    }
    return symbols.get(currency.upper(), f"{currency} ")
