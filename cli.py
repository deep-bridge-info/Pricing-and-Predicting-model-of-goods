#!/usr/bin/env python3
"""
Deepbridge Price Sensitivity Analyzer.

Searches Alibaba, extracts attributes, and shows how much you save
by downgrading specific product attributes.

Usage:
    # All-in-one interactive
    python3 cli.py run "TWS earbuds" --products 1200

    # Two-step (for scripting)
    python3 cli.py discover "TWS earbuds" --products 1200
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

def _discover(category, max_products, input_file=None):
    """Search + extract + consolidate. Returns (products, schema, attr_names, attr_values)."""
    from pipeline.search import search_broad
    from pipeline.extractor import (
        extract_attributes, consolidate_schema,
        apply_consolidated_schema, filter_by_coverage,
    )
    from models.product import Product
    import pandas as pd
    import json

    if input_file:
        print(f"Loading raw products from {input_file}...")
        try:
            df = pd.read_csv(input_file)
            products = []
            for _, row in df.iterrows():
                products.append(Product(
                    title=row['title'],
                    price_usd=float(row['price_usd']),
                    product_url=row['product_url'],
                    specifications=json.loads(row['specifications'])
                ))
            print(f"Loaded {len(products)} products from {input_file}.")
        except Exception as e:
            print(f"Error loading {input_file}: {e}")
            sys.exit(1)
    else:
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

def cmd_scrape(args):
    """Scrape Alibaba and save raw data to CSV."""
    from apify.alibaba import search_products
    from pipeline.search import _convert_products
    from utils.quotation import set_quotation_quantity
    import pandas as pd
    import json
    
    category = args.category

    print("Quantity of quotation (integer, default 3000):")
    q_input = input("> ").strip()
    if q_input:
        try:
            quotation_quantity = int(q_input)
        except ValueError:
            quotation_quantity = 3000
    else:
        quotation_quantity = 3000
    if quotation_quantity <= 0:
        quotation_quantity = 3000
    quotation_quantity = set_quotation_quantity(quotation_quantity)
    print(f"Using quotation quantity: {quotation_quantity}")

    print(f"Searching Alibaba for '{category}'...")
    # Get raw Apify products
    raw_products = search_products(query=category, max_results=args.products)
    
    if not raw_products:
        print("No products found.")
        sys.exit(1)
        
    # Convert using quotation quantity tier logic
    products = _convert_products(raw_products)
        
    data = []
    for p in products:
        data.append({
            "title": p.title,
            "price_usd": p.price_usd,
            "product_url": p.product_url,
            "specifications": json.dumps(p.specifications)
        })
        
    df = pd.DataFrame(data)
    out_file = args.out
    df.to_csv(out_file, index=False)
    print(f"Saved {len(products)} products with quotation-specific prices to '{out_file}'.")
    print(f"\nNext: run the rest of the pipeline using the --in flag:")
    print(f"  python3 cli.py run \"{category}\" --in {out_file}")


def cmd_run(args):
    """All-in-one: discover attributes, interactively pick fixed/flex, analyze."""
    from utils.cache import save_discovery
    from utils.quotation import set_quotation_quantity

    category = args.category

    print("Quantity of quotation (integer, default 3000):")
    q_input = input("> ").strip()
    if q_input:
        try:
            quotation_quantity = int(q_input)
        except ValueError:
            quotation_quantity = 3000
    else:
        quotation_quantity = 3000
    if quotation_quantity <= 0:
        quotation_quantity = 3000
    quotation_quantity = set_quotation_quantity(quotation_quantity)
    print(f"Using quotation quantity: {quotation_quantity}")

    products, schema, attr_names, attr_values = _discover(category, args.products, getattr(args, 'in_file', None))
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
    products, schema, attr_names, attr_values = _discover(category, args.products, getattr(args, 'in_file', None))
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


def _generate_suffixes(category):
    """Uses Ollama to generate a dynamic list of distinct sub-categories for search."""
    import os
    from openai import OpenAI
    
    OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3:8b")
    
    try:
        client = OpenAI(base_url=OLLAMA_BASE_URL, api_key='ollama')
        
        prompt = f"Select a category of {category} that adheres to the following rules:1. Minimize overlap between the types in the category.2. Include at least 3 types, but keep the total number as small as possible.3.Ensure the category is distinct and representative.Output only the set of types in the category, with no additional text."
        
        print(f"Asking AI to generate distinct sub-categories for '{category}'...")
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Output ONLY a comma-separated list of types. No introduction, no markdown, no extra words."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        result = response.choices[0].message.content.strip()
        
        # Clean and parse the comma-separated list
        result = result.replace('\n', ',').replace('"', '').replace("'", "")
        suffixes = [s.strip() for s in result.split(',') if s.strip()]
        
        if "" not in suffixes:
            suffixes.insert(0, "")
            
        print(f"AI generated suffixes: {suffixes[1:]}\n")
        return suffixes
        
    except Exception as e:
        print(f"Failed to generate suffixes via AI: {e}")
        print("Falling back to default list.\n")
        return ["waterproof", "sport", "gaming", "noise cancelling"]


def cmd_collect_large(args):
    """Collect up to 1200 items by modifying keywords to bypass Apify limits."""
    from apify.alibaba import search_raw_products
    import json
    
    base_query = args.category
    target = args.products
    out_file = args.out
    
    # Use AI to generate the rotating list of suffixes dynamically
    suffixes = ["Open-ear"]
    #suffixes = _generate_suffixes(base_query)
    
    all_items = []
    seen_ids = set()
    
    print(f"Starting large-scale collection for '{base_query}' (Target: {target} items)")
    print(f"Output will be saved to '{out_file}'\n")
    
    for suffix in suffixes:
        if len(all_items) >= target:
            break
            
        query = f"{base_query} {suffix}".strip()
        print(f"--- Querying: '{query}' ---")
        
        try:
            # We fetch up to the remaining target amount (or max pagination ~400)
            items = search_raw_products(query=query, max_results=target - len(all_items))
            
            for item in items:
                item_id = item.get("productId") or item.get("id") or item.get("productUrl")
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    all_items.append(item)
                    
            print(f"Current unique items collected: {len(all_items)} / {target}")
            
        except Exception as e:
            print(f"Error during query '{query}': {e}")
            
    print(f"\nCollection complete! Total unique items: {len(all_items)}")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"Saved raw JSON to {out_file}")
    print("Next step: Run 'python3 cli.py build-model' to train the Random Forest.")


def cmd_build_model(args):
    """Run extract_to_sql -> export_products_csv -> random_forest end-to-end."""
    import subprocess
    import sys
    
    print("=== STEP 1: Extracting raw JSON to SQLite (extract_to_sql.py) ===")
    ret = subprocess.run([sys.executable, "extract_to_sql.py", "--json", args.json])
    if ret.returncode != 0:
        print("Extraction failed.")
        sys.exit(ret.returncode)
        
    print("\n=== STEP 2: Exporting cleaned CSV (export_products_csv.py) ===")
    ret = subprocess.run([sys.executable, "export_products_csv.py"])
    if ret.returncode != 0:
        print("Export failed.")
        sys.exit(ret.returncode)
        
    print("\n=== STEP 3: Training Random Forest (random_forest.py) ===")
    ret = subprocess.run([sys.executable, "random_forest.py"])
    if ret.returncode != 0:
        print("Model training failed.")
        sys.exit(ret.returncode)
        
    print("\n=== BUILD COMPLETE ===")
    print("You can now run 'python3 cli.py predict-rf' to evaluate sensitivity reports.")


def cmd_predict_rf(args):
    """Run predict_sensitivity.py to predict prices on sensitivity.csv."""
    import subprocess
    import sys
    
    print("=== Running Sensitivity Prediction (predict_sensitivity.py) ===")
    ret = subprocess.run([sys.executable, "predict_sensitivity.py"])
    if ret.returncode != 0:
        sys.exit(ret.returncode)

def main():
    parser = argparse.ArgumentParser(
        description='Deepbridge Price Sensitivity Analyzer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive (recommended)
  python3 cli.py run "TWS earbuds" --products 1200

  # Scripted two-step
  python3 cli.py discover "TWS earbuds" --products 1200
  python3 cli.py analyze --fixed type=TWS --flex bluetooth_version=5.3 anc=true

  # Show cached results
  python3 cli.py show
        """,
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    p_scrape = subparsers.add_parser('scrape', help='Scrape Alibaba and save raw data to CSV')
    p_scrape.add_argument('category', help='Product category or Alibaba URL')
    p_scrape.add_argument('--products', type=int, default=1200, help='Max products (default: 1200)')
    p_scrape.add_argument('--out', default='apify.csv', help='Output CSV file (default: apify.csv)')

    p_run = subparsers.add_parser('run', help='Interactive: discover + pick attributes + analyze')
    p_run.add_argument('category', help='Product category (e.g., "TWS earbuds")')
    p_run.add_argument('--products', type=int, default=1200, help='Max products (default: 1200)')
    p_run.add_argument('--in', dest='in_file', help='Load raw products from CSV instead of scraping')

    p_discover = subparsers.add_parser('discover', help='Discover attributes and cache products')
    p_discover.add_argument('category', help='Product category (e.g., "TWS earbuds")')
    p_discover.add_argument('--products', type=int, default=1200, help='Max products (default: 1200)')
    p_discover.add_argument('--in', dest='in_file', help='Load raw products from CSV instead of scraping')

    p_analyze = subparsers.add_parser('analyze', help='Analyze with cached discovery data')
    p_analyze.add_argument('--fixed', nargs='*', default=[], help='Fixed attributes as key=value')
    p_analyze.add_argument('--flex', nargs='*', help='Flexible attributes as key=value (required)')

    subparsers.add_parser('show', help='Show cached analysis')

    p_collect_large = subparsers.add_parser('collect-large', help='Collect up to 1200 items by varying keywords')
    p_collect_large.add_argument('category', help='Base product category (e.g., "TWS earbuds")')
    p_collect_large.add_argument('--products', type=int, default=1200, help='Target number of products (default: 1200)')
    p_collect_large.add_argument('--out', default='merged_dataset.json', help='Output JSON file (default: merged_dataset.json)')

    p_build_model = subparsers.add_parser('build-model', help='Run extract_to_sql -> export_csv -> random_forest')
    p_build_model.add_argument('--json', default='merged_dataset.json', help='Input JSON file for extract_to_sql (default: merged_dataset.json)')

    subparsers.add_parser('predict-rf', help='Run predict_sensitivity.py on sensitivity.csv')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        'scrape': cmd_scrape,
        'run': cmd_run,
        'discover': cmd_discover,
        'analyze': cmd_analyze,
        'show': cmd_show,
        'collect-large': cmd_collect_large,
        'build-model': cmd_build_model,
        'predict-rf': cmd_predict_rf,
    }
    commands[args.command](args)


if __name__ == '__main__':
    main()
