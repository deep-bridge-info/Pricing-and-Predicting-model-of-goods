#!/usr/bin/env python3
"""
Deepbridge Price Sensitivity Analyzer.

Searches Alibaba, extracts attributes, and shows how much you save
by downgrading specific product attributes.

Usage:
    # All-in-one interactive
    python3 cli.py run "TWS earbuds" --products 30

    # Two-step (for scripting)
    python3 cli.py discover "TWS earbuds" --products 30
    python3 cli.py analyze --fixed type=TWS --flex bluetooth_version=5.3 anc=true

    python3 cli.py show
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / '.env')
except ImportError:
    pass


def _parse_kv_pairs(pairs: list) -> dict:
    """Parse key=value pairs from CLI args."""
    result = {}
    if pairs:
        for kv in pairs:
            if '=' in kv:
                k, v = kv.split('=', 1)
                result[k.strip()] = v.strip()
    return result


# ─── Shared logic ──────────────────────────────────────────────────

def _discover(category, max_products):
    """Search + extract + consolidate. Returns (products, schema, attr_names, attr_values)."""
    from pipeline.search import search_broad
    from pipeline.extractor import (
        extract_attributes, consolidate_schema,
        apply_consolidated_schema, filter_by_coverage,
    )

    print(f"Searching Alibaba for '{category}'...")
    products = search_broad(category, {}, max_products=max_products)

    if len(products) < 10:
        print(f"Error: Only found {len(products)} products. Need at least 10.")
        sys.exit(1)

    prices = [p.price_usd for p in products]
    print(f"Found {len(products)} products (${min(prices):.2f} - ${max(prices):.2f})")

    print("Extracting attributes...")
    raw_attrs = extract_attributes(products, category)
    for i, attrs in enumerate(raw_attrs):
        if i < len(products):
            products[i].attributes = attrs

    print("Consolidating schema...")
    schema = consolidate_schema(raw_attrs, category)
    if schema:
        consolidated_attrs = apply_consolidated_schema(raw_attrs, schema)
        good_attrs = filter_by_coverage(consolidated_attrs, threshold=0.3)
        for i, attrs in enumerate(consolidated_attrs):
            if i < len(products):
                products[i].attributes = {k: v for k, v in attrs.items() if k in good_attrs}
        attr_names = sorted(good_attrs)
    else:
        print("  (AI consolidation failed, using raw attribute names)")
        good_attrs = filter_by_coverage(raw_attrs, threshold=0.3)
        for i, attrs in enumerate(raw_attrs):
            if i < len(products):
                products[i].attributes = {k: v for k, v in attrs.items() if k in good_attrs}
        attr_names = sorted(good_attrs)

    # Build value info per attribute
    attr_values = {}
    for attr in attr_names:
        values = Counter()
        for p in products:
            val = p.attributes.get(attr)
            if val is not None:
                values[str(val)] += 1
        coverage = sum(values.values()) / len(products) * 100
        attr_values[attr] = {
            "coverage": coverage,
            "top_values": [v for v, _ in values.most_common(5)],
        }

    return products, schema, attr_names, attr_values


def _display_attributes(attr_names, attr_values):
    """Print discovered attributes with numbering."""
    print(f"\n{'='*60}")
    print(f"DISCOVERED ATTRIBUTES ({len(attr_names)})")
    print(f"{'='*60}")
    for idx, attr in enumerate(attr_names, 1):
        info = attr_values[attr]
        vals = ", ".join(info["top_values"])
        print(f"  [{idx:2d}] {attr:<30s} {info['coverage']:3.0f}%  {vals}")
    print()


def _run_analysis(products, category, schema, attr_names, fixed, flex):
    """Run match + gap analysis + targeted search + report."""
    from pipeline.search import search_targeted, deduplicate_products
    from pipeline.extractor import extract_attributes, apply_consolidated_schema
    from pipeline.matcher import score_products, filter_matched
    from pipeline.analyzer import (
        find_gaps, build_targeted_queries,
        compute_sensitivity, format_report,
    )
    from utils.cache import save_analysis

    attr_names_set = set(attr_names)

    # Validate flex attrs
    missing = [k for k in flex if k not in attr_names_set]
    if missing:
        print(f"Warning: flex attributes not found in schema: {missing}")
        print(f"Available: {attr_names}")
        print()

    # Match scoring
    print("Scoring products against fixed spec...")
    products = score_products(products, category, fixed)
    matched = filter_matched(products)
    print(f"{len(matched)} products matched")

    # Gap analysis
    print("Analyzing gaps...")
    gaps = find_gaps(matched, flex)
    if gaps:
        print(f"Found {len(gaps)} sparse tiers")
        for g in gaps[:5]:
            print(f"  {g['attr']}={g['value']}: n={g['n']}")

        queries = build_targeted_queries(gaps, category, fixed, max_queries=min(5, len(gaps)))
        if queries:
            print(f"\nRunning {len(queries)} targeted searches...")
            targeted = search_targeted(queries)
            if targeted:
                targeted_attrs = extract_attributes(targeted, category)
                for i, attrs in enumerate(targeted_attrs):
                    if i < len(targeted):
                        targeted[i].attributes = attrs
                if schema:
                    consolidated = apply_consolidated_schema(targeted_attrs, schema)
                    for i, attrs in enumerate(consolidated):
                        if i < len(targeted):
                            targeted[i].attributes = {k: v for k, v in attrs.items() if k in attr_names_set}

                targeted = score_products(targeted, category, fixed)
                new_matched = filter_matched(targeted)
                all_matched = deduplicate_products(matched + new_matched)
                print(f"Added {len(all_matched) - len(matched)} new products (total: {len(all_matched)})")
                matched = all_matched
    else:
        print("No gaps to fill")

    # Report
    print("\nComputing sensitivity report...")
    report = compute_sensitivity(matched, category, fixed, flex)
    print(format_report(report))

    # Cache
    products_data = [
        {"title": p.title, "price_usd": p.price_usd, "attributes": p.attributes,
         "match_score": p.match_score, "product_url": p.product_url}
        for p in matched
    ]
    report_data = {
        "category": report.category,
        "baseline_median": report.baseline.median,
        "baseline_n": report.baseline.n,
        "deltas": [
            {"attr": d.attr_name, "from": d.current_value, "to": d.downgrade_value,
             "delta": d.delta, "confidence": d.confidence}
            for d in report.deltas
        ],
    }
    save_analysis(category, products_data, schema, flex, report_data)


# ─── Commands ──────────────────────────────────────────────────────

def cmd_run(args):
    """All-in-one: discover attributes, interactively pick fixed/flex, analyze."""
    from utils.cache import save_discovery

    category = args.category
    products, schema, attr_names, attr_values = _discover(category, args.products)
    _display_attributes(attr_names, attr_values)

    # Cache discovery in case user wants to re-analyze later
    products_data = [
        {"title": p.title, "price_usd": p.price_usd, "attributes": p.attributes,
         "product_url": p.product_url}
        for p in products
    ]
    save_discovery(category, products_data, schema if schema else {}, attr_names)

    # Interactive: pick fixed attributes
    print("Enter FIXED attribute numbers (non-negotiable), comma-separated, or press Enter to skip:")
    fixed_input = input("> ").strip()
    fixed = {}
    if fixed_input:
        for num_str in fixed_input.split(","):
            try:
                idx = int(num_str.strip()) - 1
                if 0 <= idx < len(attr_names):
                    attr = attr_names[idx]
                    vals = attr_values[attr]["top_values"]
                    print(f"  {attr} values: {', '.join(vals)}")
                    val = input(f"  Value for {attr}: ").strip()
                    if val:
                        fixed[attr] = val
            except ValueError:
                continue

    # Interactive: pick flex attributes
    print("\nEnter FLEX attribute numbers (explore downgrades), comma-separated:")
    flex_input = input("> ").strip()
    flex = {}
    if not flex_input:
        print("Error: must select at least one flex attribute.")
        sys.exit(1)

    for num_str in flex_input.split(","):
        try:
            idx = int(num_str.strip()) - 1
            if 0 <= idx < len(attr_names):
                attr = attr_names[idx]
                vals = attr_values[attr]["top_values"]
                print(f"  {attr} values: {', '.join(vals)}")
                val = input(f"  Your current value for {attr}: ").strip()
                if val:
                    flex[attr] = val
        except ValueError:
            continue

    if not flex:
        print("Error: no flex attributes selected.")
        sys.exit(1)

    print(f"\nFixed: {fixed}")
    print(f"Flex:  {flex}")
    print()

    _run_analysis(products, category, schema, attr_names, fixed, flex)


def cmd_discover(args):
    """Search Alibaba and discover available attributes (non-interactive)."""
    from utils.cache import save_discovery

    category = args.category
    products, schema, attr_names, attr_values = _discover(category, args.products)
    _display_attributes(attr_names, attr_values)

    products_data = [
        {"title": p.title, "price_usd": p.price_usd, "attributes": p.attributes,
         "product_url": p.product_url}
        for p in products
    ]
    save_discovery(category, products_data, schema if schema else {}, attr_names)

    print(f"Cached {len(products)} products with {len(attr_names)} attributes.")
    print(f"\nNext: run analyze with chosen attributes:")
    print(f'  python3 cli.py analyze --fixed <attr>=<val> --flex <attr>=<val> ...')


def cmd_analyze(args):
    """Run sensitivity analysis using cached discovery data (non-interactive)."""
    from utils.cache import load_discovery
    from models.product import Product

    fixed = _parse_kv_pairs(args.fixed)
    flex = _parse_kv_pairs(args.flex)

    if not flex:
        print("Error: --flex is required.")
        print("Example: --flex bluetooth_version=5.3 anc=true")
        sys.exit(1)

    cached = load_discovery()
    if not cached:
        print("No discovery data. Run 'discover' or 'run' first.")
        sys.exit(1)

    category = cached["category"]
    schema = cached.get("schema", {})
    attr_names = cached.get("attr_names", [])

    products = [
        Product(
            title=p["title"],
            price_usd=p["price_usd"],
            product_url=p.get("product_url", ""),
            attributes=p.get("attributes", {}),
        )
        for p in cached["products"]
    ]

    print(f"Category: {category} ({len(products)} products from cache)")
    print(f"Fixed:    {fixed}")
    print(f"Flex:     {flex}")
    print()

    _run_analysis(products, category, schema, attr_names, fixed, flex)


def cmd_show(args):
    """Show cached analysis summary."""
    from utils.cache import load_analysis

    cached = load_analysis()
    if not cached:
        print("No cached analysis. Run 'run' or 'analyze' first.")
        sys.exit(1)

    print(f"Category:   {cached.get('category', '?')}")
    print(f"Products:   {len(cached.get('products', []))}")
    ts = cached.get('timestamp', 0)
    if ts:
        age = time.time() - ts
        if age < 3600:
            print(f"Cached:     {int(age / 60)} minutes ago")
        else:
            print(f"Cached:     {int(age / 3600)} hours ago")

    report = cached.get("report", {})
    if report:
        print(f"\nBaseline:   ${report.get('baseline_median', 0):.2f} (n={report.get('baseline_n', 0)})")
        print(f"\nDeltas:")
        for d in report.get("deltas", []):
            print(f"  {d['attr']}: {d['from']} -> {d['to']}  ${d['delta']:+.2f}  ({d['confidence']})")


def main():
    parser = argparse.ArgumentParser(
        description='Deepbridge Price Sensitivity Analyzer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive (recommended)
  python3 cli.py run "TWS earbuds" --products 30

  # Scripted two-step
  python3 cli.py discover "TWS earbuds" --products 30
  python3 cli.py analyze --fixed type=TWS --flex bluetooth_version=5.3 anc=true

  # Show cached results
  python3 cli.py show
        """,
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    p_run = subparsers.add_parser('run', help='Interactive: discover + pick attributes + analyze')
    p_run.add_argument('category', help='Product category (e.g., "TWS earbuds")')
    p_run.add_argument('--products', type=int, default=200, help='Max products (default: 200)')

    p_discover = subparsers.add_parser('discover', help='Discover attributes and cache products')
    p_discover.add_argument('category', help='Product category (e.g., "TWS earbuds")')
    p_discover.add_argument('--products', type=int, default=200, help='Max products (default: 200)')

    p_analyze = subparsers.add_parser('analyze', help='Analyze with cached discovery data')
    p_analyze.add_argument('--fixed', nargs='*', default=[], help='Fixed attributes as key=value')
    p_analyze.add_argument('--flex', nargs='*', help='Flexible attributes as key=value (required)')

    subparsers.add_parser('show', help='Show cached analysis')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        'run': cmd_run,
        'discover': cmd_discover,
        'analyze': cmd_analyze,
        'show': cmd_show,
    }
    commands[args.command](args)


if __name__ == '__main__':
    main()
