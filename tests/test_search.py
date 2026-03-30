from pipeline.search import build_broad_query, deduplicate_products
from models.product import Product


def test_build_broad_query_simple():
    q = build_broad_query("TWS earbuds", {"type": "TWS"})
    assert "TWS earbuds" in q


def test_build_broad_query_with_fixed():
    q = build_broad_query("earbuds", {"type": "TWS", "brand": "Sony"})
    # Fixed attrs should be included as keywords
    assert "earbuds" in q


def test_deduplicate_products():
    products = [
        Product(title="A", price_usd=10.0, product_url="https://ali.com/1", specifications={}),
        Product(title="B", price_usd=12.0, product_url="https://ali.com/2", specifications={}),
        Product(title="A dup", price_usd=11.0, product_url="https://ali.com/1", specifications={}),
    ]
    deduped = deduplicate_products(products)
    assert len(deduped) == 2
    urls = [p.product_url for p in deduped]
    assert "https://ali.com/1" in urls
    assert "https://ali.com/2" in urls


def test_deduplicate_empty():
    assert deduplicate_products([]) == []
