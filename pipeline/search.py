"""Apify search with rate limiting and deduplication."""
import time
from typing import Dict, List, Optional, Set

from apify.alibaba import search_products, AlibabaProduct
from models.product import Product
from utils.currency import convert_to_usd
from utils.quotation import get_quotation_quantity

RATE_LIMIT_DELAY = 3  # seconds between Apify calls


def build_broad_query(category: str, fixed_attrs: Dict[str, str]) -> str:
    """Build search query from category. Fixed attrs are implicit in category."""
    return category


def search_broad(
    category: str,
    fixed_attrs: Dict[str, str],
    max_products: int = 1200,
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
    max_per_query: int = 1200,
    api_token: Optional[str] = None,
) -> List[Product]:
    """Run targeted searches sequentially with rate limiting.

    Skips failed searches and continues with remaining.
    """
    import os
    import csv
    
    csv_path = "products.csv"
    if os.path.exists(csv_path):
        print(f"[Search] Using local {csv_path} for temporary testing")
        all_products = []
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = list(csv.DictReader(f))
            
            for query in queries:
                print(f"[Search] Local search for: {query}")
                found = 0
                
                # Try to extract the specific term from the query. 
                search_terms = query.lower().split()
                
                for row in reader:
                    if found >= max_per_query:
                        break
                        
                    row_str = str(list(row.values())).lower()
                    
                    # Simple heuristic: if the last word of the query is in the row, it's a match
                    if search_terms[-1] in row_str:
                        pid = row.get("product_id", "0")
                        try:
                            # Use product_id for deterministic mock price
                            price = 5.0 + (int(pid) % 1500) / 100.0
                        except ValueError:
                            price = 10.0
                        
                        title = row.get("product_name") or f"Local Product {pid}"
                        p = Product(
                            title=title,
                            price_usd=price,
                            product_url=f"http://example.com/{pid}",
                            specifications=dict(row)
                        )
                        all_products.append(p)
                        found += 1
                        
                print(f"[Search] Found {found} products locally for '{query}'")
            return all_products
        except Exception as e:
            print(f"[Search] Failed to use local CSV: {e}")
            pass
            
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
    def _to_int(value):
        try:
            return int(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return None

    def _to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _pick_tier_price(raw: AlibabaProduct, quotation_qty: int) -> Optional[float]:
        tiers = raw.price_tiers or []
        if not tiers:
            return None

        normalized = []
        for t in tiers:
            min_q = _to_int(t.get("min"))
            max_q = _to_int(t.get("max"))
            p = _to_float(t.get("price"))
            if p is None:
                continue
            normalized.append((min_q, max_q, p))
        if not normalized:
            return None

        for min_q, max_q, p in normalized:
            min_ok = True if min_q is None else quotation_qty >= min_q
            max_ok = True if max_q is None or max_q == -1 else quotation_qty <= max_q
            if min_ok and max_ok:
                return p

        sorted_by_min = sorted(
            normalized,
            key=lambda x: x[0] if x[0] is not None else float("inf")
        )
        below_all = sorted_by_min[0][0] is not None and quotation_qty < sorted_by_min[0][0]
        if below_all:
            return sorted_by_min[0][2]
        return sorted_by_min[-1][2]

    products = []
    quotation_qty = get_quotation_quantity()
    for raw in raw_products:
        selected_price = _pick_tier_price(raw, quotation_qty)
        if selected_price is None:
            selected_price = raw.price_min
        price_usd = convert_to_usd(selected_price, raw.currency)
        if price_usd <= 0:
            continue
        products.append(Product(
            title=raw.title,
            price_usd=price_usd,
            product_url=raw.product_url,
            specifications=raw.specifications,
        ))
    return products
