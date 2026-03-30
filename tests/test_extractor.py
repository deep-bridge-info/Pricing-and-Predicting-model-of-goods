from pipeline.extractor import consolidate_schema, filter_by_coverage


def test_filter_by_coverage():
    """Drop attributes below 30% coverage."""
    products_attrs = [
        {"bluetooth": "5.3", "anc": "true"},
        {"bluetooth": "5.0", "anc": "false"},
        {"bluetooth": "5.3"},
        {"bluetooth": "5.4"},
        {},
    ]
    # bluetooth: 4/5 = 80%, anc: 2/5 = 40%
    filtered = filter_by_coverage(products_attrs, threshold=0.3)
    assert "bluetooth" in filtered
    assert "anc" in filtered

    # At 50% threshold, anc should be dropped
    filtered_strict = filter_by_coverage(products_attrs, threshold=0.5)
    assert "bluetooth" in filtered_strict
    assert "anc" not in filtered_strict


def test_filter_by_coverage_empty():
    assert filter_by_coverage([], threshold=0.3) == set()
