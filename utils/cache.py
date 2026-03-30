"""JSON cache for discovery and analysis results."""
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

CACHE_DIR = Path(__file__).parent.parent / 'cache'
DISCOVER_FILE = CACHE_DIR / 'last_discover.json'
ANALYSIS_FILE = CACHE_DIR / 'last_analysis.json'


def save_discovery(category: str, products: list, schema: dict, attr_names: list):
    """Save discover results to cache."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_data = {
        "category": category,
        "products": products,
        "schema": schema,
        "attr_names": attr_names,
        "timestamp": time.time(),
    }
    with open(DISCOVER_FILE, 'w') as f:
        json.dump(cache_data, f, indent=2)


def load_discovery() -> Optional[Dict[str, Any]]:
    """Load cached discovery. Returns None if no cache exists."""
    if not DISCOVER_FILE.exists():
        return None
    with open(DISCOVER_FILE) as f:
        return json.load(f)


def save_analysis(category: str, products: list, schema: list, flex_attrs: dict, report_data: dict):
    """Save analysis results to cache."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_data = {
        "category": category,
        "products": products,
        "schema": schema,
        "flex_attrs": flex_attrs,
        "report": report_data,
        "timestamp": time.time(),
    }
    with open(ANALYSIS_FILE, 'w') as f:
        json.dump(cache_data, f, indent=2)


def load_analysis() -> Optional[Dict[str, Any]]:
    """Load cached analysis. Returns None if no cache exists."""
    if not ANALYSIS_FILE.exists():
        return None
    with open(ANALYSIS_FILE) as f:
        return json.load(f)
