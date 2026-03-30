"""Apify search with rate limiting and deduplication."""
import time
from typing import Dict, List, Optional, Set

from apify.alibaba import search_products, AlibabaProduct
from models.product import Product
from utils.currency import convert_to_usd

RATE_LIMIT_DELAY = 3  # seconds between Apify calls


def build_broad_query(category: str, fixed_attrs: Dict[str, str]) -> str:
    """Build search query from category. Fixed attrs are implicit in category."""
    return category


def search_broad(
    category: str,
    fixed_attrs: Dict[str, str],
    max_products: int = 100,
    api_token: Optional[str] = None,
) -> List[Product]:
    """Run broad Alibaba search and convert to Product objects."""
    query = build_broad_query(category, fixed_attrs)
    raw_products = search_products(
        query=query,
        max_results=max_products,
        api_token=api_token,
    )
    return _convert_products(raw_products)


def search_targeted(
    queries: List[str],
    max_per_query: int = 20,
    api_token: Optional[str] = None,
) -> List[Product]:
    """Run targeted searches sequentially with rate limiting.

    Skips failed searches and continues with remaining.
    """
    all_products = []
    for i, query in enumerate(queries):
        if i > 0:
            time.sleep(RATE_LIMIT_DELAY)
        try:
            raw = search_products(
                query=query,
                max_results=max_per_query,
                api_token=api_token,
            )
            all_products.extend(_convert_products(raw))
        except Exception as e:
            print(f"[Search] Targeted search failed for '{query}': {e}")
            continue
    return all_products


def deduplicate_products(products: List[Product]) -> List[Product]:
    """Remove duplicate products by URL, keeping first occurrence."""
    seen: Set[str] = set()
    unique = []
    for p in products:
        if p.product_url and p.product_url not in seen:
            seen.add(p.product_url)
            unique.append(p)
        elif not p.product_url:
            unique.append(p)
    return unique


def _convert_products(raw_products: List[AlibabaProduct]) -> List[Product]:
    """Convert AlibabaProduct objects to Product objects with USD prices."""
    products = []
    for raw in raw_products:
        price_usd = convert_to_usd(raw.price_min, raw.currency)
        if price_usd <= 0:
            continue
        products.append(Product(
            title=raw.title,
            price_usd=price_usd,
            product_url=raw.product_url,
            specifications=raw.specifications,
        ))
    return products
