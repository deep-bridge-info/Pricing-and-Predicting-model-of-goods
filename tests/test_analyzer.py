from pipeline.analyzer import compute_tier_stats, compute_sensitivity
from models.product import Product
from models.report import TierStats


def test_compute_tier_stats():
    products = [
        Product(title="A", price_usd=10.0, product_url="u1", attributes={"bt": "5.3"}),
        Product(title="B", price_usd=12.0, product_url="u2", attributes={"bt": "5.3"}),
        Product(title="C", price_usd=14.0, product_url="u3", attributes={"bt": "5.3"}),
        Product(title="D", price_usd=16.0, product_url="u4", attributes={"bt": "5.3"}),
        Product(title="E", price_usd=18.0, product_url="u5", attributes={"bt": "5.3"}),
        Product(title="F", price_usd=8.0, product_url="u6", attributes={"bt": "5.0"}),
        Product(title="G", price_usd=9.0, product_url="u7", attributes={"bt": "5.0"}),
        Product(title="H", price_usd=10.0, product_url="u8", attributes={"bt": "5.0"}),
    ]
    tiers = compute_tier_stats(products, "bt")
    assert "5.3" in tiers
    assert "5.0" in tiers
    assert tiers["5.3"].n == 5
    assert tiers["5.0"].n == 3
    assert tiers["5.3"].median == 14.0  # middle of [10,12,14,16,18]
    assert tiers["5.0"].median == 9.0   # middle of [8,9,10]


def test_compute_tier_stats_empty():
    tiers = compute_tier_stats([], "bt")
    assert tiers == {}


def test_compute_sensitivity():
    products = [
        Product(title="A", price_usd=10.0, product_url="u1", attributes={"bt": "5.3", "anc": "true"}),
        Product(title="B", price_usd=12.0, product_url="u2", attributes={"bt": "5.3", "anc": "true"}),
        Product(title="C", price_usd=14.0, product_url="u3", attributes={"bt": "5.3", "anc": "true"}),
        Product(title="D", price_usd=16.0, product_url="u4", attributes={"bt": "5.3", "anc": "true"}),
        Product(title="E", price_usd=18.0, product_url="u5", attributes={"bt": "5.3", "anc": "true"}),
        Product(title="F", price_usd=6.0, product_url="u6", attributes={"bt": "5.3", "anc": "false"}),
        Product(title="G", price_usd=7.0, product_url="u7", attributes={"bt": "5.3", "anc": "false"}),
        Product(title="H", price_usd=8.0, product_url="u8", attributes={"bt": "5.3", "anc": "false"}),
        Product(title="I", price_usd=9.0, product_url="u9", attributes={"bt": "5.3", "anc": "false"}),
        Product(title="J", price_usd=10.0, product_url="u10", attributes={"bt": "5.3", "anc": "false"}),
    ]
    flex = {"anc": "true"}
    report = compute_sensitivity(products, "earbuds", {"type": "TWS"}, flex)
    assert report.baseline.median == 14.0
    assert len(report.deltas) >= 1
    anc_delta = report.deltas[0]
    assert anc_delta.delta < 0  # downgrade saves money
