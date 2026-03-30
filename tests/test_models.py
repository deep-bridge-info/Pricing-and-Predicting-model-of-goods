from models.product import Product
from models.report import TierStats, AttributeDelta, SensitivityReport


def test_product_creation():
    p = Product(
        title="TWS Earbuds BT5.3",
        price_usd=12.50,
        product_url="https://alibaba.com/product/123",
        specifications={"BT Wireless": "Bluetooth v5.3", "noise cancelling": "ANC"},
    )
    assert p.title == "TWS Earbuds BT5.3"
    assert p.price_usd == 12.50
    assert p.match_score is None
    assert p.attributes == {}


def test_product_with_attributes():
    p = Product(
        title="TWS Earbuds",
        price_usd=8.00,
        product_url="https://alibaba.com/product/456",
        specifications={},
        attributes={"bluetooth_version": "5.0", "anc": "false"},
        match_score=0.8,
    )
    assert p.attributes["bluetooth_version"] == "5.0"
    assert p.match_score == 0.8


def test_tier_stats_confidence_reliable():
    # n>=5, QCD<0.3
    ts = TierStats(value="5.3", n=6, median=12.40, p25=10.50, p75=14.20, qcd=0.15)
    assert ts.confidence == "reliable"


def test_tier_stats_confidence_reliable_small_n_low_qcd():
    # n>=3, QCD<0.15 → also reliable
    ts = TierStats(value="5.0", n=4, median=11.00, p25=10.50, p75=11.50, qcd=0.05)
    assert ts.confidence == "reliable"


def test_tier_stats_confidence_indicative():
    # n>=3 but QCD >= 0.15 and n < 5
    ts = TierStats(value="5.0", n=4, median=11.00, p25=9.00, p75=13.00, qcd=0.20)
    assert ts.confidence == "indicative"


def test_tier_stats_confidence_insufficient():
    ts = TierStats(value="4.2", n=2, median=8.00, p25=7.00, p75=9.00, qcd=0.12)
    assert ts.confidence == "insufficient"


def test_tier_stats_confidence_high_dispersion():
    # n=10 but high QCD → indicative
    ts = TierStats(value="5.3", n=10, median=12.00, p25=5.00, p75=20.00, qcd=0.60)
    assert ts.confidence == "indicative"


def test_attribute_delta_controlled():
    d = AttributeDelta(
        attr_name="bluetooth_version",
        current_value="5.3",
        downgrade_value="5.0",
        current_tier=TierStats(value="5.3", n=8, median=12.40, p25=10.50, p75=14.20, qcd=0.15),
        downgrade_tier=TierStats(value="5.0", n=5, median=11.20, p25=9.00, p75=13.00, qcd=0.18),
        controlled=True,
    )
    assert d.delta == -1.2
    assert d.confidence == "reliable"


def test_attribute_delta_uncontrolled_downgrades_confidence():
    d = AttributeDelta(
        attr_name="anc",
        current_value="true",
        downgrade_value="false",
        current_tier=TierStats(value="true", n=8, median=12.40, p25=10.50, p75=14.20, qcd=0.15),
        downgrade_tier=TierStats(value="false", n=10, median=8.00, p25=6.00, p75=10.00, qcd=0.25),
        controlled=False,
    )
    # Both tiers would be "reliable" individually, but uncontrolled → downgraded to "indicative"
    assert d.confidence == "indicative"


def test_sensitivity_report():
    baseline = TierStats(value="baseline", n=8, median=12.40, p25=10.50, p75=14.20, qcd=0.15)
    report = SensitivityReport(
        category="TWS earbuds",
        fixed_attrs={"type": "TWS"},
        flex_attrs={"bluetooth_version": "5.3"},
        baseline=baseline,
        deltas=[],
        total_products=100,
        matched_products=45,
    )
    assert report.category == "TWS earbuds"
    assert report.baseline.median == 12.40
    assert report.baseline_is_fallback is False
