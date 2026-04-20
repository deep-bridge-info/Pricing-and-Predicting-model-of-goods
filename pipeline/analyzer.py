"""Gap analysis, tier statistics, and sensitivity report generation."""
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from models.product import Product
from models.report import AttributeDelta, SensitivityReport, TierStats

MIN_TIER_SIZE = 5


def compute_tier_stats(products: List[Product], attr_name: str) -> Dict[str, TierStats]:
    """Group products by attribute value and compute stats per tier."""
    tiers: Dict[str, List[float]] = defaultdict(list)
    for p in products:
        val = p.attributes.get(attr_name)
        if val is not None:
            tiers[str(val)].append(p.price_usd)

    result = {}
    for value, prices in tiers.items():
        if not prices:
            continue
        prices.sort()
        n = len(prices)
        median = statistics.median(prices)
        p25 = _percentile(prices, 25)
        p75 = _percentile(prices, 75)
        # QCD: robust dispersion metric consistent with median
        qcd = (p75 - p25) / (p75 + p25) if (p75 + p25) > 0 else 0.0

        result[value] = TierStats(
            value=value, n=n, median=round(median, 2),
            p25=round(p25, 2), p75=round(p75, 2), qcd=round(qcd, 3),
        )

    return result


def find_gaps(
    products: List[Product], flex_attrs: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Find attribute tiers that need more data.

    Returns list of {attr, value, n, price_spread} sorted by priority.
    """
    gaps = []
    for attr_name, user_value in flex_attrs.items():
        tiers = compute_tier_stats(products, attr_name)

        # Calculate price spread across tiers with data
        tier_medians = [t.median for t in tiers.values() if t.n >= 2]
        price_spread = max(tier_medians) - min(tier_medians) if len(tier_medians) >= 2 else 0

        for value, stats in tiers.items():
            if stats.n < MIN_TIER_SIZE and value != user_value:
                gaps.append({
                    "attr": attr_name,
                    "value": value,
                    "n": stats.n,
                    "price_spread": price_spread,
                })

    # Sort: highest price spread first, then lowest n
    gaps.sort(key=lambda g: (-g["price_spread"], g["n"]))
    return gaps


def build_targeted_queries(
    gaps: List[Dict[str, Any]],
    category: str,
    fixed_attrs: Dict[str, str],
    max_queries: int = 5,
) -> List[str]:
    """Build targeted search queries for the most impactful gaps."""
    queries = []

    for gap in gaps[:max_queries]:
        attr = gap["attr"]
        value = gap["value"]

        # Skip pure numbers and booleans as search terms
        if _is_numeric(value) or value.lower() in ("true", "false", "none"):
            term = attr.replace("_", " ")
        else:
            term = value.replace("_", " ")

        query = f"{category} {term}"
        if query not in queries:
            queries.append(query)

    return queries[:max_queries]


def _compute_baseline(products: List[Product], flex_attrs: Dict[str, str]) -> Tuple[TierStats, bool]:
    """Compute baseline with progressive relaxation.

    Tries matching all flex attrs, then drops one at a time, then uses all products.
    Returns (baseline_stats, is_fallback).
    """
    attr_items = list(flex_attrs.items())

    # Try all flex attrs first
    prices = _match_prices(products, dict(attr_items))
    if len(prices) >= 3:
        return _make_tier_stats("baseline", prices), False

    # Progressive relaxation: drop one attr at a time, keep the most restrictive match
    for drop_idx in range(len(attr_items)):
        subset = {k: v for i, (k, v) in enumerate(attr_items) if i != drop_idx}
        if subset:
            prices = _match_prices(products, subset)
            if len(prices) >= 3:
                return _make_tier_stats("baseline (partial match)", prices), True

    # Last resort: all products
    prices = sorted(p.price_usd for p in products)
    return _make_tier_stats("baseline (all products)", prices), True


def _match_prices(products: List[Product], attrs: Dict[str, str]) -> List[float]:
    """Get prices of products matching all given attribute values."""
    prices = []
    for p in products:
        if all(
            str(p.attributes.get(k, "")).lower() == str(v).lower()
            for k, v in attrs.items()
        ):
            prices.append(p.price_usd)
    prices.sort()
    return prices


def _make_tier_stats(label: str, sorted_prices: List[float]) -> TierStats:
    """Build TierStats from sorted price list."""
    n = len(sorted_prices)
    median = statistics.median(sorted_prices)
    p25 = _percentile(sorted_prices, 25)
    p75 = _percentile(sorted_prices, 75)
    qcd = (p75 - p25) / (p75 + p25) if (p75 + p25) > 0 else 0.0
    return TierStats(
        value=label, n=n, median=round(median, 2),
        p25=round(p25, 2), p75=round(p75, 2), qcd=round(qcd, 3),
    )


def compute_sensitivity(
    products: List[Product],
    category: str,
    fixed_attrs: Dict[str, str],
    flex_attrs: Dict[str, str],
) -> SensitivityReport:
    """Compute full sensitivity report with controlled comparisons."""
    # Baseline with progressive relaxation
    baseline, baseline_is_fallback = _compute_baseline(products, flex_attrs)

    # Compute controlled deltas: for each flex attribute, hold all OTHER
    # flex attributes constant at the user's values, then compare tiers.
    deltas = []
    for attr_name, user_value in flex_attrs.items():
        # Filter to products matching all OTHER flex attrs
        other_flex = {k: v for k, v in flex_attrs.items() if k != attr_name}
        controlled = [
            p for p in products
            if all(
                str(p.attributes.get(k, "")).lower() == str(v).lower()
                for k, v in other_flex.items()
            )
        ]

        is_controlled = len(controlled) >= 3
        if not is_controlled:
            controlled = products

        tiers = compute_tier_stats(controlled, attr_name)
        user_tier = tiers.get(str(user_value))

        if not user_tier:
            continue

        for tier_value, tier_stats in tiers.items():
            if tier_value == str(user_value):
                continue
            if tier_stats.median < user_tier.median:  # Only show downgrades (cheaper)
                deltas.append(AttributeDelta(
                    attr_name=attr_name,
                    current_value=str(user_value),
                    downgrade_value=tier_value,
                    current_tier=user_tier,
                    downgrade_tier=tier_stats,
                    controlled=is_controlled,
                ))

    # Sort by savings (largest first)
    deltas.sort(key=lambda d: d.delta)

    # Combo estimates (top 2 deltas from different attributes)
    combo_estimates = _compute_combo_estimates(products, deltas, baseline)

    return SensitivityReport(
        category=category,
        fixed_attrs=fixed_attrs,
        flex_attrs=flex_attrs,
        baseline=baseline,
        deltas=deltas,
        total_products=len(products),
        matched_products=len(products),
        baseline_is_fallback=baseline_is_fallback,
        combo_estimates=combo_estimates if combo_estimates else None,
    )


def _compute_combo_estimates(
    products: List[Product],
    deltas: List[AttributeDelta],
    baseline: TierStats,
) -> List[Dict[str, Any]]:
    """Compute combo estimates for top 2 deltas from different attributes."""
    if len(deltas) < 2:
        return []

    d1, d2 = deltas[0], deltas[1]
    if d1.attr_name == d2.attr_name:
        return []

    combo_products = [
        p for p in products
        if str(p.attributes.get(d1.attr_name, "")).lower() == d1.downgrade_value.lower()
        and str(p.attributes.get(d2.attr_name, "")).lower() == d2.downgrade_value.lower()
    ]

    if len(combo_products) >= 3:
        combo_median = statistics.median([p.price_usd for p in combo_products])
        return [{
            "attrs": {d1.attr_name: d1.downgrade_value, d2.attr_name: d2.downgrade_value},
            "median": round(combo_median, 2),
            "n": len(combo_products),
            "source": "observed",
        }]

    additive = round(baseline.median + d1.delta + d2.delta, 2)
    return [{
        "attrs": {d1.attr_name: d1.downgrade_value, d2.attr_name: d2.downgrade_value},
        "median": max(0.01, additive),
        "n": 0,
        "source": "estimated — actual savings may differ",
    }]


def format_report(report: SensitivityReport) -> str:
    """Format the sensitivity report for terminal output."""
    import pandas as pd
    
    # Generate sensitivity.csv
    # We want to create rows based on the original flex input (the baseline) 
    # and then create additional rows for each downgrade option.
    csv_data = []
    
    # 1. Add the Baseline Row
    baseline_row = {"type": report.category}
    # Add all flex attributes with their current values
    for attr, val in report.flex_attrs.items():
        baseline_row[attr] = val
    baseline_row["price"] = round(report.baseline.median, 2)
    csv_data.append(baseline_row)
    
    # 2. Add Downgrade Rows
    if report.deltas:
        for d in report.deltas:
            downgrade_row = {"type": report.category}
            # Copy the flex attributes
            for attr, val in report.flex_attrs.items():
                downgrade_row[attr] = val
            
            # Replace the specific attribute being downgraded
            downgrade_row[d.attr_name] = d.downgrade_value
            downgrade_row["price"] = round(d.downgrade_tier.median, 2)
            
            csv_data.append(downgrade_row)
            
    # Save to CSV
    if csv_data:
        df = pd.DataFrame(csv_data)
        df.to_csv("sensitivity.csv", index=False)
        print("Generated 'sensitivity.csv' based on report data.")

    lines = []
    lines.append(f"\n{'='*65}")
    lines.append("PRICE SENSITIVITY REPORT")
    lines.append(f"{'='*65}")
    lines.append(f"Category: {report.category}")
    lines.append(f"Fixed:    {report.fixed_attrs}")
    lines.append(f"Flex:     {report.flex_attrs}")
    lines.append(f"Products: {report.matched_products} matched / {report.total_products} total")
    lines.append("")

    b = report.baseline
    baseline_note = " *fallback*" if report.baseline_is_fallback else ""
    lines.append(f"Baseline median: ${b.median:.2f} (n={b.n}, IQR ${b.p25:.2f}-${b.p75:.2f}){baseline_note}")
    if report.baseline_is_fallback:
        lines.append("  * Not enough products matched all flex specs exactly. Baseline is approximate.")
    lines.append("")

    if report.deltas:
        lines.append(f"{'Attribute':<20} {'Current → Downgrade':<25} {'Δ Median':>10}  {'Confidence'}")
        lines.append("\u2500" * 80)
        for d in report.deltas:
            t = d.downgrade_tier
            arrow = f"{d.current_value} \u2192 {d.downgrade_value}"
            ctrl_flag = "" if d.controlled else " [uncontrolled]"
            
            # Use the report baseline if it's a fallback situation where the current tier is misaligned
            current_median = report.baseline.median if report.baseline_is_fallback else d.current_tier.median
            actual_delta = d.downgrade_tier.median - current_median
            
            lines.append(
                f"{d.attr_name:<20} {arrow:<25} {actual_delta:>+10.2f}  "
                f"{d.confidence} (n={t.n}, QCD={t.qcd:.2f}){ctrl_flag}"
            )
        lines.append("")

        # Best single cut (only if baseline is not a fallback)
        best = report.deltas[0]
        best_current_median = report.baseline.median if report.baseline_is_fallback else best.current_tier.median
        best_actual_delta = best.downgrade_tier.median - best_current_median
        
        if not report.baseline_is_fallback:
            best_price = round(best_current_median + best_actual_delta, 2)
            lines.append(f"Best single cut: {best.attr_name} {best.current_value} \u2192 {best.downgrade_value} "
                          f"\u2192 ${best_price:.2f} (saves ${abs(best_actual_delta):.2f})")
        else:
            lines.append(f"Best single cut: {best.attr_name} {best.current_value} \u2192 {best.downgrade_value} "
                          f"(saves ${abs(best_actual_delta):.2f})")

        # Combo estimate
        if report.combo_estimates:
            combo = report.combo_estimates[0]
            attrs_str = " + ".join(f"{k}={v}" for k, v in combo["attrs"].items())
            prefix = "~" if combo["source"] != "observed" else ""
            lines.append(f"Best combo:      {attrs_str} \u2192 {prefix}${combo['median']:.2f} "
                          f"({combo['source']})")
    else:
        lines.append("No cheaper downgrade tiers found in the data.")

    lines.append("")
    return "\n".join(lines)


def _percentile(sorted_data: List[float], p: int) -> float:
    """Compute percentile from sorted data."""
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


def _is_numeric(val: str) -> bool:
    try:
        float(str(val).replace(",", ""))
        return True
    except (ValueError, TypeError):
        return False
