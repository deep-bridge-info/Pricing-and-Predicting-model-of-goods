"""
Alibaba-specific Apify actor wrappers.

Uses shareze001's scrape-alibaba-products-by-keywords actor which returns
full product details including specifications in a single search call.
"""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .client import ApifyClient


ACTOR_SEARCH = "shareze001~scrape-alibaba-products-by-keywords"


@dataclass
class AlibabaProduct:
    """Parsed Alibaba product from search results."""
    title: str
    price_min: float
    price_max: Optional[float]
    currency: str
    moq: int
    moq_unit: str
    price_tiers: List[Dict[str, Any]]
    product_url: str
    image_url: Optional[str]
    supplier_name: Optional[str]
    supplier_url: Optional[str]
    supplier_years: Optional[int]
    supplier_verified: bool
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def specifications(self) -> Dict[str, str]:
        """Extract specifications from raw_data (shareze001 format)."""
        specs = {}
        # Combine all property sources
        for prop_key in ['productBasicProperties', 'productKeyIndustryProperties', 'productOtherProperties']:
            props = self.raw_data.get(prop_key, [])
            if props:
                for prop in props:
                    name = prop.get('attrName', '').strip()
                    value = prop.get('attrValue', '').strip()
                    if name and value and name not in specs:
                        specs[name] = value
        return specs



def _parse_price(price_str: str) -> tuple[float, Optional[float], str]:
    """Parse price string like '$1.50 - $3.00' or '₱47.44'."""
    import re

    currencies = {
        '$': 'USD',
        '₱': 'PHP',
        '€': 'EUR',
        '£': 'GBP',
        '¥': 'CNY',
    }

    currency = 'USD'
    for symbol, curr in currencies.items():
        if symbol in str(price_str):
            currency = curr
            break

    # Extract numbers, filtering out empty strings
    numbers = re.findall(r'[\d,]+\.?\d*', str(price_str))
    parsed_numbers = []
    for n in numbers:
        n = n.strip().replace(',', '')
        if n and n != '.':
            try:
                parsed_numbers.append(float(n))
            except ValueError:
                continue

    if len(parsed_numbers) >= 2:
        return parsed_numbers[0], parsed_numbers[1], currency
    elif len(parsed_numbers) == 1:
        return parsed_numbers[0], None, currency
    else:
        return 0.0, None, currency


def _parse_moq(moq_str: str) -> tuple[int, str]:
    """Parse MOQ string like '10 pieces' or 'Min. order: 100 sets'."""
    import re

    numbers = re.findall(r'[\d,]+', str(moq_str))
    quantity = int(numbers[0].replace(',', '')) if numbers else 1

    unit = "pieces"
    unit_patterns = ['pieces', 'piece', 'pcs', 'sets', 'set', 'units', 'unit', 'pairs', 'pair']
    moq_lower = str(moq_str).lower()
    for pattern in unit_patterns:
        if pattern in moq_lower:
            unit = pattern
            break

    return quantity, unit


def _parse_search_result(item: Dict[str, Any]) -> AlibabaProduct:
    """Parse a single search result item from Apify (shareze001 actor format)."""
    import re

    # Title is in 'subject' field
    title = item.get("subject") or item.get("title") or ""

    # Price can be a dict or string - shareze001 uses complex nested structure
    price_data = item.get("price", {})
    price_min = 0.0
    price_max = None
    currency = "USD"

    if isinstance(price_data, dict):
        tier_prices = []
        # Try productRangePrices first (has USD prices)
        range_prices = price_data.get("productRangePrices", {})
        if range_prices:
            price_min = range_prices.get("dollarPriceRangeLow") or 0.0
            price_max = range_prices.get("dollarPriceRangeHigh")

        # Try productLadderPrices (tier pricing with USD)
        ladder_prices = price_data.get("productLadderPrices", [])
        if ladder_prices:
            for p in ladder_prices:
                tier_prices.append({
                    "min": p.get("min"),
                    "max": p.get("max"),
                    "price": p.get("dollarPrice", p.get("price")),
                })
            if not price_min:
                dollar_prices = [p.get("price") for p in tier_prices if p.get("price") is not None]
                if dollar_prices:
                    price_min = min(dollar_prices)
                    price_max = max(dollar_prices) if len(dollar_prices) > 1 else None

        # Fallback to simple format
        if not price_min:
            price_min = price_data.get("min") or price_data.get("minPrice") or 0.0
            price_max = price_data.get("max") or price_data.get("maxPrice")
            currency = price_data.get("currency", "USD")
    else:
        price_min, price_max, currency = _parse_price(str(price_data))
        tier_prices = []

    # MOQ can be a dict or string
    moq_data = item.get("moq", {})
    if isinstance(moq_data, dict):
        moq = moq_data.get("minOrderQuantity") or moq_data.get("quantity") or 1
        moq_unit = moq_data.get("unit") or "pieces"
        if isinstance(moq, str):
            moq, moq_unit = _parse_moq(moq)
    else:
        moq, moq_unit = _parse_moq(str(moq_data))

    # URL
    product_url = item.get("url") or item.get("productUrl") or ""

    # Image - from mediaItems array
    image_url = None
    media_items = item.get("mediaItems", [])
    if media_items and isinstance(media_items, list):
        for media in media_items:
            if media.get("type") == "image":
                img_urls = media.get("imageUrl", {})
                image_url = img_urls.get("normal") or img_urls.get("small") or img_urls.get("big")
                if image_url:
                    break

    # Supplier info
    supplier_info = item.get("supplierInfo", {})
    supplier_name = supplier_info.get("companyName") or supplier_info.get("name")
    supplier_url = supplier_info.get("companyUrl") or supplier_info.get("url")

    supplier_years = None
    years_str = supplier_info.get("yearsAsSeller") or supplier_info.get("years")
    if years_str:
        years_match = re.search(r'(\d+)', str(years_str))
        if years_match:
            supplier_years = int(years_match.group(1))

    supplier_verified = bool(
        supplier_info.get("verified") or
        supplier_info.get("goldSupplier") or
        supplier_info.get("tradeAssurance")
    )

    return AlibabaProduct(
        title=title,
        price_min=float(price_min) if price_min else 0.0,
        price_max=float(price_max) if price_max else None,
        currency=currency,
        moq=int(moq) if moq else 1,
        moq_unit=moq_unit,
        price_tiers=tier_prices,
        product_url=product_url,
        image_url=image_url,
        supplier_name=supplier_name,
        supplier_url=supplier_url,
        supplier_years=supplier_years,
        supplier_verified=supplier_verified,
        raw_data=item,
    )


def _build_search_run_input(query: str, max_results: int) -> Dict[str, Any]:
    """
    Build actor input for Alibaba keyword search.

    Keeping this in one place prevents drift between wrappers and ensures
    `max_results` is always propagated to the actor payload.
    """
    from urllib.parse import quote

    if query.startswith("http://") or query.startswith("https://"):
        search_url = query
    else:
        search_url = f"https://www.alibaba.com/trade/search?SearchText={quote(query)}"

    return {
        "search_url": search_url,
        "size": max_results,
        "skip_page_parameter": True,
    }


def search_products(
    query: str,
    max_results: int = 1200,
    api_token: Optional[str] = None,
    timeout_secs: int = 86400,  # 24 hours max
) -> List[AlibabaProduct]:
    """
    Search Alibaba products by keyword or direct URL.

    Args:
        query: Search query (e.g., "TWS earbuds") or a full Alibaba search URL
        max_results: Maximum number of results to return
        api_token: Apify API token (or set APIFY_TOKEN env var)
        timeout_secs: Maximum time to wait for results

    Returns:
        List of AlibabaProduct objects
    """
    # Delegate fetching to search_raw_products so there is a single source of truth
    # for actor input configuration.
    items = search_raw_products(query, max_results, api_token, timeout_secs)
    products = [_parse_search_result(item) for item in items]
    print(f"[Apify] Parsed {len(products)} products")

    return products

def search_raw_products(
    query: str,
    max_results: int = 1200,
    api_token: Optional[str] = None,
    timeout_secs: int = 86400,  # 24 hours max
) -> List[Dict[str, Any]]:
    """
    Search Alibaba products and return raw JSON dicts.
    """
    client = ApifyClient(api_token=api_token)
    run_input = _build_search_run_input(query, max_results)
    search_url = run_input["search_url"]

    print(f"[Apify] Searching Alibaba for: {query}")
    print(f"[Apify] URL: {search_url}")
    items = client.run_actor_sync(
        actor_id=ACTOR_SEARCH,
        run_input=run_input,
        timeout_secs=timeout_secs,
    )
    
    # Enforce the max_results limit purely in Python after fetching
    items = items[:max_results]
    
    print(f"[Apify] Found {len(items)} raw products")
    return items
