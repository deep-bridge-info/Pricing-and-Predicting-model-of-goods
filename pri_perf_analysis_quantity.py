import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", str(Path(".mplconfig").resolve()))
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def parse_selection(selection: str, max_col: int) -> List[int]:
    parts = [p.strip() for p in selection.split(",") if p.strip()]
    if not parts:
        raise ValueError("No column numbers provided.")

    indices: List[int] = []
    for part in parts:
        idx = int(part)
        if idx < 1 or idx > max_col:
            raise ValueError(f"Column index out of range: {idx}")
        indices.append(idx - 1)
    return sorted(set(indices))


def show_columns(headers: List[str]) -> None:
    print("\nAvailable columns in products.csv:")
    for i, col in enumerate(headers, start=1):
        print(f"{i:>3}. {col}")


def quantity_match(min_q: float, max_q: float, quantity: int) -> bool:
    if quantity < min_q:
        return False
    if max_q < 0:
        return True
    return quantity <= max_q


def pick_price_for_quantity(price_rows: List[Tuple[float, float, float]], quantity: int) -> float:
    matches = [r for r in price_rows if quantity_match(r[0], r[1], quantity)]
    if not matches:
        return np.nan
    # Prefer the most specific tier (largest min_quantity).
    matches.sort(key=lambda r: (r[0], -r[1]), reverse=True)
    return float(matches[0][2])


def load_db_maps_for_quantity(db_path: Path, quantity: int) -> Tuple[Dict[str, str], Dict[str, float]]:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute("SELECT product_id, product_url FROM products")
    url_map = {str(pid): str(url or "") for pid, url in cur.fetchall()}

    cur.execute("SELECT product_id, min_quantity, max_quantity, price FROM product_prices")
    grouped: Dict[str, List[Tuple[float, float, float]]] = {}
    for pid, min_q, max_q, price in cur.fetchall():
        if pid is None or price is None:
            continue
        try:
            min_v = float(min_q if min_q is not None else 0)
            max_v = float(max_q if max_q is not None else -1)
            price_v = float(price)
        except (TypeError, ValueError):
            continue
        grouped.setdefault(str(pid), []).append((min_v, max_v, price_v))

    price_map: Dict[str, float] = {}
    for pid, ranges in grouped.items():
        picked = pick_price_for_quantity(ranges, quantity)
        if not np.isnan(picked):
            price_map[pid] = picked

    conn.close()
    return url_map, price_map


def main() -> None:
    parser = argparse.ArgumentParser(description="CSV filter + quantity-aware price-performance analysis")
    parser.add_argument("--input", default="products.csv", help="Input CSV file")
    parser.add_argument("--db", default="products_attributes.db", help="SQLite DB path")
    parser.add_argument(
        "--select",
        default="",
        help="Comma-separated 1-based column numbers (e.g. 1,3). If omitted, prompts interactively.",
    )
    parser.add_argument(
        "--quantity",
        type=int,
        default=None,
        help="Quotation quantity (default prompts, fallback=3000)",
    )
    parser.add_argument("--pri-perf-out", default="Pri-Perf.csv", help="Filtered output CSV")
    parser.add_argument("--clean-out", default="Pri-Perf_clean.csv", help="Cleaned output CSV")
    parser.add_argument(
        "--analysis-out",
        default="Pri-Perf_analysis.csv",
        help="Analysis output with Actual Price and Perfomance",
    )
    parser.add_argument(
        "--plot-out",
        default="Pri-Perf_saddle_plot.png",
        help="Scatter + fitted line plot output",
    )
    args = parser.parse_args()

    input_csv = Path(args.input)
    db_path = Path(args.db)
    pri_perf_out = Path(args.pri_perf_out)
    clean_out = Path(args.clean_out)
    analysis_out = Path(args.analysis_out)
    plot_out = Path(args.plot_out)
    price_source_out = Path("Pri-Perf_price_source.csv")

    if not input_csv.exists():
        print(f"Error: input file not found: {input_csv}")
        sys.exit(1)
    if not db_path.exists():
        print(f"Error: database file not found: {db_path}")
        sys.exit(1)

    df = pd.read_csv(input_csv, dtype=str).fillna("")
    headers = list(df.columns)
    if "product_id" not in df.columns:
        print("Error: input CSV must contain 'product_id'.")
        sys.exit(1)

    show_columns(headers)
    selection = args.select.strip()
    if not selection:
        selection = input("\nEnter column numbers separated by comma (e.g. 1,3): ").strip()
    try:
        selected_idx = parse_selection(selection, len(headers))
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    selected_cols = [headers[i] for i in selected_idx]
    print(f"\nSelected columns: {selected_cols}")

    if args.quantity is None:
        q_raw = input("Enter quantity (default 3000): ").strip()
        if not q_raw:
            quantity = 3000
        else:
            try:
                quantity = int(q_raw)
            except ValueError:
                print("Invalid quantity, using default 3000.")
                quantity = 3000
    else:
        quantity = int(args.quantity)
    if quantity <= 0:
        quantity = 3000
    print(f"Using quantity: {quantity}")

    # Step 3: filter rows where selected columns are not null/empty.
    not_null_mask = pd.Series(True, index=df.index)
    for col in selected_cols:
        not_null_mask &= df[col].astype(str).str.strip().ne("")
    filtered = df.loc[not_null_mask].copy()
    if filtered.empty:
        print("No rows remain after non-null filtering for selected columns.")
        sys.exit(1)

    # Add URL and quantity-matched price from DB.
    url_map, price_map = load_db_maps_for_quantity(db_path, quantity)
    filtered.loc[:, "Url"] = filtered["product_id"].map(url_map).fillna("")
    filtered.loc[:, "price"] = filtered["product_id"].map(price_map)

    # Keep rows with valid URL and valid selected-tier price.
    filtered = filtered[filtered["Url"].astype(str).str.strip().ne("")].copy()
    filtered = filtered[filtered["price"].notna()].copy()
    if filtered.empty:
        print("No rows left after URL/price join. Check products_attributes.db content.")
        sys.exit(1)

    # Keep selected columns + price + Url only.
    pri_perf_df = filtered[selected_cols + ["price", "Url"]].copy()
    pri_perf_df.to_csv(pri_perf_out, index=False)
    print(f"Saved filtered CSV: {pri_perf_out} ({len(pri_perf_df)} rows)")

    # Step 4: run same cleaning criteria via export_products_csv_xgb.py.
    price_source_df = pd.DataFrame(
        {
            "min_quantity": "",
            "max_quantity": "",
            "price": filtered["price"].astype(float).round(6),
        }
    )
    price_source_df.to_csv(price_source_out, index=False)

    export_cmd = [
        sys.executable,
        "export_products_csv_xgb.py",
        "--in-csv",
        str(pri_perf_out),
        "--price-source",
        str(price_source_out),
        "--cleaned-out",
        str(clean_out),
    ]
    subprocess.run(export_cmd, check=True)
    print(f"Saved cleaned CSV: {clean_out}")

    # Step 5: predicted price (Perfomance) = mean price for identical selected-column values.
    analysis_df = filtered[selected_cols + ["price", "Url"]].copy()
    analysis_df.rename(columns={"price": "Actual Price"}, inplace=True)
    analysis_df.loc[:, "Perfomance"] = (
        analysis_df.groupby(selected_cols, dropna=False)["Actual Price"].transform("mean").round(6)
    )
    analysis_df.to_csv(analysis_out, index=False)
    print(f"Saved analysis CSV: {analysis_out}")

    # Step 6: saddle points graph with fitted line.
    x = analysis_df["Perfomance"].astype(float).values
    y = analysis_df["Actual Price"].astype(float).values

    plt.figure(figsize=(10, 6))
    plt.scatter(x, y, alpha=0.55, s=20, label="Products")

    if len(analysis_df) >= 3 and len(np.unique(x)) >= 3:
        coeffs = np.polyfit(x, y, 2)
        x_fit = np.linspace(float(np.min(x)), float(np.max(x)), 300)
        y_fit = np.polyval(coeffs, x_fit)
        plt.plot(x_fit, y_fit, color="red", linewidth=2, label="Fitted line (deg=2)")
    elif len(analysis_df) >= 2 and len(np.unique(x)) >= 2:
        coeffs = np.polyfit(x, y, 1)
        x_fit = np.linspace(float(np.min(x)), float(np.max(x)), 300)
        y_fit = np.polyval(coeffs, x_fit)
        plt.plot(x_fit, y_fit, color="red", linewidth=2, label="Fitted line (deg=1)")

    plt.xlabel("Perfomance")
    plt.ylabel("Actual Price")
    plt.title("Price-Performance Saddle Points Graph")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(plot_out, dpi=200)
    print(f"Saved plot: {plot_out}")


if __name__ == "__main__":
    main()
