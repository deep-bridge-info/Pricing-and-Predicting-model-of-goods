from pipeline.matcher import filter_matched
from models.product import Product


def _make_product(score):
    p = Product(title="X", price_usd=10.0, product_url=f"u{score}", specifications={})
    p.match_score = score
    return p


def test_filter_matched_above_threshold():
    # Need 15+ above threshold to avoid fallback
    products = [_make_product(0.6 + i * 0.01) for i in range(16)] + [_make_product(0.3)]
    matched = filter_matched(products)
    assert len(matched) == 16  # all 0.6+ pass, the 0.3 does not


def test_filter_matched_fallback_threshold():
    """When < 15 products pass 0.5, lower to 0.3."""
    products = [_make_product(0.6)] + [_make_product(0.35) for _ in range(20)]
    matched = filter_matched(products)
    # Only 1 passes 0.5, so falls back to 0.3 — all 21 pass
    assert len(matched) == 21


def test_filter_matched_none_score():
    products = [_make_product(None), _make_product(0.7)]
    matched = filter_matched(products)
    assert len(matched) == 1  # only 0.7 passes
