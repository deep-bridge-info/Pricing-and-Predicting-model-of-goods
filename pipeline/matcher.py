"""AI match scoring against fixed spec."""
import json
from typing import Any, Dict, List

from models.product import Product
from utils.ai import call_ai

MIN_MATCH_THRESHOLD = 0.5
FALLBACK_THRESHOLD = 0.3
MIN_MATCHED_PRODUCTS = 15


def score_products(
    products: List[Product],
    category: str,
    fixed_attrs: Dict[str, str],
) -> List[Product]:
    """Score each product against fixed attributes using AI.

    Updates each product's match_score in place and returns the list.
    Flex attributes are NOT part of scoring.
    """
    # Prepare candidates
    candidates = [
        {
            "index": i,
            "title": p.title[:100],
            "attributes": p.attributes,
        }
        for i, p in enumerate(products)
    ]

    prompt = f"""Score how well each product matches this {category} specification.

FIXED requirements (must match):
{json.dumps(fixed_attrs, indent=2)}

Products:
{json.dumps(candidates, indent=2)}

Scoring rules:
- Score 0.0-1.0 based on how well the product matches the FIXED requirements above
- Wrong product type = 0.0
- Partial attribute match = proportional score
- Do NOT penalize for attributes not listed above — only score against the fixed requirements

Return JSON:
{{
  "scores": [
    {{"index": 0, "score": 0.85}},
    ...
  ]
}}

Return only valid JSON."""

    data = call_ai(prompt, timeout=120)
    if data and "scores" in data:
        for entry in data["scores"]:
            idx = entry.get("index", -1)
            if 0 <= idx < len(products):
                products[idx].match_score = entry.get("score", 0.0)
    else:
        # Fallback: all products get 0.5 (let the user see everything)
        print("[Matcher] AI scoring failed, defaulting all scores to 0.5")
        for p in products:
            p.match_score = 0.5

    return products


def filter_matched(products: List[Product]) -> List[Product]:
    """Filter products by match score, lowering threshold if too few pass."""
    matched = [p for p in products if (p.match_score or 0) >= MIN_MATCH_THRESHOLD]

    if len(matched) < MIN_MATCHED_PRODUCTS:
        print(f"[Matcher] Only {len(matched)} products at >={MIN_MATCH_THRESHOLD} threshold, "
              f"lowering to {FALLBACK_THRESHOLD}")
        matched = [p for p in products if (p.match_score or 0) >= FALLBACK_THRESHOLD]

    return matched
