# Deepbridge Workflow Guide

This document explains the end-to-end workflow of the current project for a new user, including the runtime flow, technical implementation details, and output artifacts.

## 1) What This Project Does

The project supports two related workflows:

1. **Sensitivity analysis workflow (core product):**
   - Search Alibaba products
   - Extract price-relevant attributes with AI
   - Match products to your fixed requirements
   - Estimate savings by downgrading flexible attributes

2. **ML/data workflow (supporting tooling):**
   - Build large datasets from Alibaba raw JSON
   - Convert to SQL/CSV training data
   - Train RF/XGBoost models
   - Predict prices for generated sensitivity scenarios

---

## 2) High-Level Architecture

- `cli.py` is the main command entry point.
- `pipeline/` contains the sensitivity-analysis stages:
  - `search.py`: Alibaba search + conversion + dedup
  - `extractor.py`: AI attribute extraction and schema consolidation
  - `matcher.py`: AI-based fixed-spec match scoring
  - `analyzer.py`: tier stats, deltas, confidence, report formatting
- `models/` defines data models:
  - `product.py`: product object used across pipeline
  - `report.py`: `TierStats`, `AttributeDelta`, `SensitivityReport`
- `apify/` wraps Alibaba scraping via Apify.
- `utils/` provides AI calls, cache, currency conversion, and quotation quantity settings.

---

## 3) Core Sensitivity Workflow (Recommended for New Users)

### Command

```bash
python3 cli.py run "TWS earbuds" --products 1200
```

### Runtime flow in detail

1. **Quotation quantity input**
   - CLI asks for quantity (default `3000`).
   - Saved via `utils/quotation.py` and used when selecting tier prices from Alibaba price ladders.

2. **Broad search**
   - `pipeline.search.search_broad()` calls `apify.alibaba.search_products()`.
   - Raw Alibaba products are converted by `_convert_products()`:
     - selects the best price tier matching quotation quantity
     - converts to USD (`utils/currency.py`)
     - maps to `Product` objects

3. **Attribute extraction**
   - `pipeline.extractor.extract_attributes()` processes products in batches of 10.
   - AI prompt requests price-relevant normalized attributes in `snake_case`.
   - On AI failure, fallback normalizes raw spec keys.

4. **Schema consolidation**
   - `consolidate_schema()` asks AI to merge duplicate attribute names and drop non-price-relevant keys.
   - `apply_consolidated_schema()` remaps original keys to canonical keys.
   - `filter_by_coverage(threshold=0.3)` keeps only attributes present in >=30% of products.

5. **Interactive fixed/flex selection**
   - User selects:
     - **Fixed** attributes (must match)
     - **Flex** attributes (candidate downgrade dimensions)

6. **AI matching**
   - `pipeline.matcher.score_products()` scores each product (0.0-1.0) against fixed attrs only.
   - `filter_matched()` keeps scores >=0.5; if too few, fallback threshold is 0.3.

7. **Gap analysis + targeted search**
   - `pipeline.analyzer.find_gaps()` finds sparse tiers (`n < 5`) among flex attrs.
   - `build_targeted_queries()` generates targeted search terms.
   - `search_targeted()` fetches additional products and deduplicates by URL.

8. **Sensitivity report computation**
   - `compute_sensitivity()`:
     - builds baseline tier (with fallback relaxation if needed)
     - computes controlled deltas for each flex attr (hold others constant)
   - Confidence comes from `TierStats.confidence` using sample size + QCD.
   - `format_report()` prints report and generates `sensitivity.csv`.

9. **Caching**
   - Discovery and analysis outputs are cached via `utils/cache.py`.
   - You can inspect summary with `python3 cli.py show`.

---

## 4) Key Statistical Logic

- Primary metric is **median** (robust against outlier/bait prices).
- Dispersion metric is **QCD** = `(p75 - p25) / (p75 + p25)`.
- Delta = `downgrade_median - current_median` (usually negative for savings).
- Confidence levels:
  - reliable: enough support + low spread
  - indicative: moderate support/spread
  - insufficient: very low sample support
- If controlled comparison has too few samples, analysis falls back to uncontrolled comparison and lowers confidence.

---

## 5) Main CLI Commands and When to Use

- `python3 cli.py run ...`
  - Best for first-time users and interactive exploration.

- `python3 cli.py scrape ...`
  - Only scrape and store raw converted results into CSV.

- `python3 cli.py discover ...`
  - Run search + extraction + schema discovery, cache results.

- `python3 cli.py analyze --fixed ... --flex ...`
  - Re-run analysis on cached discovery without scraping again.

- `python3 cli.py show`
  - Show cached analysis summary.

- `python3 cli.py collect-large ...`
  - Build larger raw JSON dataset for ML workflows.

- `python3 cli.py build-model --json ...`
  - Run RF model pipeline end-to-end (`extract_to_sql.py` -> `export_products_csv.py` -> `random_forest.py`).

- `python3 cli.py predict-rf`
  - Run model prediction on `sensitivity.csv` with RF artifacts.

---

## 6) ML / Dataset Workflow

### A) Data build path

1. Raw JSON collection:
   - `cli.py collect-large ...` -> `merged_dataset.json`
2. SQL extraction:
   - `extract_to_sql.py` -> `products_attributes.db`
3. CSV export:
   - RF path: `export_products_csv.py` -> `products_cleaned.csv`
   - XGB path: `export_products_csv_xgb.py` -> `products_cleaned_xgb.csv`

### B) Training path

- RF:
  - `random_forest.py`
  - outputs: `best_rf_model.pkl`, `rf_features.pkl`, `rf_medians.pkl`

- XGB:
  - `xgboost_model.py`
  - outputs: `best_xgb_model.pkl`, `xgb_features.pkl`, `xgb_medians.pkl`

### C) Prediction path

- `predict_sensitivity.py` reads `sensitivity.csv`, aligns features to saved model feature sets, and writes `result.csv`.
- Default model is RF; use `--model xgb` for XGBoost.

---

## 7) Quantity and Price Tier Behavior

Quotation quantity is important because Alibaba listings often have tiered pricing.

- In search conversion (`pipeline/search.py`), tier price is selected by:
  - quantity between `[min, max]`, with `max=-1` treated as open-ended
  - fallback to nearest boundary tier if no exact range match
- This selected tier price becomes `price_usd` used in downstream analysis.

---

## 8) Common Artifacts Produced

- Sensitivity workflow:
  - `sensitivity.csv` (scenarios + baseline/downgrade reference prices)
  - terminal report output
  - cache files (discovery/analysis)

- ML workflow:
  - `products_attributes.db`
  - `products_cleaned.csv` / `products_cleaned_xgb.csv`
  - model `.pkl` artifacts
  - feature importance outputs
  - `result.csv` predictions

- Price-performance helper scripts in repo:
  - `pri_perf_analysis.py`
  - `pri_perf_analysis_quantity.py`
  - outputs include `Pri-Perf.csv`, `Pri-Perf_clean.csv`, analysis CSV, and `Pri-Perf_saddle_plot.png`

---

## 9) Environment and Dependencies

Minimum expected setup:

1. Python environment + `pip install -r requirements.txt`
2. `.env` configured from `.env.example`
3. Credentials/services:
   - Apify token for Alibaba scraping
   - Azure OpenAI key for AI extraction/matching
   - Optional exchange-rate API key

---

## 10) Quick Start for a New User

1. Configure `.env`.
2. Run:
   ```bash
   python3 cli.py run "TWS earbuds" --products 1200
   ```
3. Select fixed/flex attributes when prompted.
4. Review generated report and `sensitivity.csv`.
5. (Optional) Train ML model and run prediction:
   ```bash
   python3 export_products_csv_xgb.py
   python3 xgboost_model.py
   python3 predict_sensitivity.py --model xgb
   ```

This gives you both the statistical sensitivity analysis and the model-based estimated pricing path.
