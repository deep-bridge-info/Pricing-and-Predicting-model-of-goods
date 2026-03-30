"""AI-powered attribute extraction and consolidation."""
import json
from typing import Any, Dict, List, Optional, Set

from models.product import Product
from utils.ai import call_ai


def extract_attributes(products: List[Product], category: str) -> List[Dict[str, Any]]:
    """Extract attributes from products using AI. Batches at 10 products.

    Returns list of attribute dicts (one per product, same order).
    """
    all_attrs: List[Dict[str, Any]] = [{}] * len(products)

    batch_size = 10
    total_batches = (len(products) + batch_size - 1) // batch_size
    for batch_num, start in enumerate(range(0, len(products), batch_size), 1):
        batch = products[start:start + batch_size]
        print(f"  [Batch {batch_num}/{total_batches}] Extracting {len(batch)} products...")
        batch_attrs = _extract_batch(batch, category)
        for i, attrs in enumerate(batch_attrs):
            all_attrs[start + i] = attrs

    return all_attrs


def _extract_batch(products: List[Product], category: str) -> List[Dict[str, Any]]:
    """Extract attributes from a single batch of products."""
    # Send only specs (no titles) to keep prompt small
    product_specs = []
    for i, p in enumerate(products):
        # Trim spec values to keep tokens down
        trimmed_specs = {k: str(v)[:80] for k, v in p.specifications.items()}
        product_specs.append({"i": i, "s": trimmed_specs})

    prompt = f"""Extract price-relevant attributes from these {category} product specs.

{json.dumps(product_specs)}

Rules:
- Use snake_case names (e.g. bluetooth_version, noise_cancellation, battery_life_hours)
- Normalize: booleans→true/false, numbers→plain numbers, remove units from values
- Only include attributes that affect price

Return JSON:
{{"products":[{{"i":0,"a":{{"attr":"val"}}}},...]}}"""

    data = call_ai(prompt, timeout=180)
    if not data:
        print("    [Extractor] AI failed, using fallback for this batch")
        return _fallback_extract(products)

    # Map AI response back to product order
    result = [{}] * len(products)
    for p in data.get("products", []):
        idx = p.get("i", p.get("index", -1))
        if 0 <= idx < len(products):
            result[idx] = p.get("a", p.get("attributes", {}))

    return result


def _fallback_extract(products: List[Product]) -> List[Dict[str, Any]]:
    """Simple fallback: normalize spec keys to snake_case."""
    result = []
    for p in products:
        attrs = {}
        for key, value in p.specifications.items():
            norm_key = key.lower().replace(" ", "_").replace("-", "_").rstrip(":")
            attrs[norm_key] = value
        result.append(attrs)
    return result


def consolidate_schema(
    all_attrs: List[Dict[str, Any]], category: str
) -> Optional[Dict[str, Dict[str, Any]]]:
    """Use AI to merge duplicate attribute names and drop junk.

    Returns mapping: {canonical_name: display_name} or None on failure.
    """
    # Collect all unique attribute names with sample values
    attr_samples: Dict[str, List[str]] = {}
    for attrs in all_attrs:
        for key, val in attrs.items():
            if key not in attr_samples:
                attr_samples[key] = []
            if len(attr_samples[key]) < 3:
                attr_samples[key].append(str(val))

    if not attr_samples:
        return None

    prompt = f"""I have these attribute names extracted from {category} products on Alibaba.
Many are duplicates with different naming. Some are irrelevant to price.

Attributes and sample values:
{json.dumps(attr_samples, indent=2)}

Task:
1. Merge duplicate attributes into canonical snake_case names
2. Drop attributes that don't affect product PRICE (e.g., place_of_origin, logo, oem_odm, model_number, brand_name)
3. Keep only the most price-relevant attributes (typically 5-15)

Return JSON:
{{
  "schema": {{
    "canonical_name": {{"display_name": "Human Name", "source_keys": ["original_key1", "original_key2"]}},
    ...
  }}
}}

Return only valid JSON."""

    data = call_ai(prompt, timeout=60)
    if not data or "schema" not in data:
        return None
    
    schema_data = data["schema"]
    # Sometimes AI returns a list instead of a dict when it misinterprets the schema request
    if isinstance(schema_data, list):
        # Convert list format to the expected dict format if possible
        converted_schema = {}
        for item in schema_data:
            if isinstance(item, dict) and "canonical_name" in item:
                canonical = item["canonical_name"]
                converted_schema[canonical] = {
                    "display_name": item.get("display_name", canonical),
                    "source_keys": item.get("source_keys", [canonical])
                }
            elif isinstance(item, dict) and len(item) == 1:
                # Handle case where it might be [{"attr_name": {"display_name": ...}}]
                key = list(item.keys())[0]
                converted_schema[key] = item[key]
        return converted_schema if converted_schema else None

    return schema_data


def apply_consolidated_schema(
    all_attrs: List[Dict[str, Any]], schema: Dict
) -> List[Dict[str, Any]]:
    """Remap product attributes using the consolidated schema.

    For each product, maps original attribute keys to canonical names.
    """
    result = []
    for attrs in all_attrs:
        mapped = {}
        for canonical, info in schema.items():
            source_keys = info.get("source_keys", [canonical])
            for sk in source_keys:
                if sk in attrs:
                    mapped[canonical] = attrs[sk]
                    break
        result.append(mapped)
    return result


def filter_by_coverage(
    all_attrs: List[Dict[str, Any]], threshold: float = 0.3
) -> Set[str]:
    """Return attribute names that appear in >= threshold fraction of products."""
    if not all_attrs:
        return set()

    total = len(all_attrs)
    counts: Dict[str, int] = {}
    for attrs in all_attrs:
        for key in attrs:
            counts[key] = counts.get(key, 0) + 1

    return {key for key, count in counts.items() if count / total >= threshold}
