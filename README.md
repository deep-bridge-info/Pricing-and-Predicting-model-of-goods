# Deepbridge Price Sensitivity Analyzer

Finds cost savings by comparing Alibaba prices across product attribute tiers. Given a product spec, shows how much you save by downgrading specific attributes (e.g., dropping ANC, using Bluetooth 5.0 instead of 5.3).

## How It Works

```
Search Alibaba → Extract attributes (AI) → Score matches → Analyze price tiers → Report savings
```

1. **Search** — Pulls 30-100 products from Alibaba via Apify
2. **Extract** — GPT-4o discovers and normalizes product attributes from raw specs
3. **Consolidate** — Merges duplicate attribute names, drops irrelevant ones (5-15 clean attrs)
4. **Match** — Scores products against your fixed requirements, filters out non-matches
5. **Gap fill** — Runs targeted searches for sparse tiers (3-5 additional Apify calls)
6. **Analyze** — Controlled comparison: holds other attributes constant, computes median price deltas per tier
7. **Report** — Shows savings per downgrade with confidence labels (reliable/indicative/insufficient)

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Set API keys in .env (copy from .env.example)
cp .env.example .env
# Edit .env with your Apify token and set up your local Ollama server

# Run (interactive — recommended)
python3 cli.py run "TWS earbuds" --products 1200

# This will:
#   1. Search Alibaba
#   2. Show discovered attributes
#   3. Ask you to pick fixed vs. flex attributes
#   4. Show the sensitivity report
```

## Commands

### Interactive Flow

#### `run` — Interactive all-in-one (recommended)

```bash
python3 cli.py run "TWS earbuds" --products 1200
```
Searches, discovers attributes, prompts you to pick fixed/flex, asks for quotation quantity, then runs the analysis.
- `--in <file.csv>`: Load raw products from a CSV (e.g., `apify.csv`) instead of scraping live.

### Manual Pipeline Flow

#### `scrape` — Scrape Alibaba directly
```bash
python3 cli.py scrape "TWS earbuds" --products 1200 --out apify.csv
```
Scrape Alibaba and save raw data to CSV without running analysis.

#### `discover` — Discover attributes (non-interactive)

```bash
python3 cli.py discover "TWS earbuds" --products 1200
```

Searches and extracts attributes. Caches results for `analyze`.
- `--in <file.csv>`: Load from CSV instead of scraping live.

#### `analyze` — Run analysis on cached data (non-interactive)

```bash
python3 cli.py analyze --fixed type=TWS --flex bluetooth_version=5.3 anc=true
```

Uses cached discovery data. Good for scripting or re-analyzing with different attribute selections.

#### `show` — Show cached results

```bash
python3 cli.py show
```

### Machine Learning Pipeline

#### `collect-large` — Build a large raw dataset
```bash
python3 cli.py collect-large "TWS earbuds" --products 1200 --out merged_dataset.json
```
Collects up to 1200 items by varying keywords automatically.

#### `build-model` — End-to-end Random Forest training
```bash
python3 cli.py build-model --json merged_dataset.json
```
Runs the full ETL pipeline: `extract_to_sql.py` → `export_products_csv.py` → `random_forest.py`.

#### XGBoost Workflow (Alternative to RF)
```bash
# 1. Export sparse data preserving NaNs for XGBoost
python3 export_products_csv_xgb.py

# 2. Train the XGBoost model
python3 xgboost_model.py
```

#### Prediction
```bash
# Predict prices on sensitivity.csv using Random Forest (default)
python3 predict_sensitivity.py

# Predict prices using XGBoost
python3 predict_sensitivity.py --model xgb

# Alternative CLI wrapper for Random Forest prediction
python3 cli.py predict-rf
```

## Example Output

```
PRICE SENSITIVITY REPORT
=================================================================
Category: TWS earbuds
Fixed:    {'type': 'TWS'}
Flex:     {'noise_cancellation': 'ANC', 'waterproof_standard': 'IPX5'}
Products: 45 matched / 60 total

Baseline median: $12.20 (n=6, IQR $11.50-$12.90)

Attribute            Current → Downgrade         Δ Median  Confidence
────────────────────────────────────────────────────────────────────────
noise_cancellation   ANC → None                     -4.08  reliable (n=12, QCD=0.15)
noise_cancellation   ANC → ENC                      -2.35  reliable (n=8, QCD=0.10)
waterproof_standard  IPX5 → IPX4                    -1.07  indicative (n=4, QCD=0.22)

Best single cut: noise_cancellation ANC → None (saves $4.08)
```

## Reading the Report

- **Δ Median** — Price difference between your current tier and the downgrade tier. Computed as a controlled comparison (other attributes held constant).
- **QCD** — Quartile Coefficient of Dispersion. Lower = tighter price spread = more trustworthy delta. Values < 0.3 are good.
- **Confidence levels:**
  - `reliable` — n≥5 with QCD<0.3, or n≥3 with QCD<0.15. Trust this delta.
  - `indicative` — n≥3 but higher dispersion, or uncontrolled comparison. Directionally useful.
  - `insufficient` — n<3. Not enough data.
- **[uncontrolled]** — Not enough products to hold other attributes constant. Delta may be confounded with other attribute changes.
- **\*fallback\*** on baseline — Not enough products matched all your flex specs exactly. Baseline used progressive relaxation.

## Project Structure

```
cli.py                  # CLI entry point (run, discover, analyze, show)
pipeline/
  search.py             # Apify search with rate limiting and dedup
  extractor.py          # AI attribute extraction and consolidation
  matcher.py            # AI match scoring against fixed spec
  analyzer.py           # Tier stats, gap analysis, sensitivity report
models/
  product.py            # Product dataclass
  report.py             # TierStats, AttributeDelta, SensitivityReport
apify/
  client.py             # Apify API client
  alibaba.py            # Alibaba product parser
utils/
  ai.py                 # Azure OpenAI API helper with retry
  currency.py           # Currency conversion (live rates + fallback)
  cache.py              # JSON cache for discovery and analysis
tests/                  # Unit tests (22 tests)
docs/superpowers/
  specs/                # Design spec
  plans/                # Implementation plan
```

## Configuration

Copy `.env.example` to `.env` and set:

```bash
# Required
APIFY_TOKEN=your_apify_token          # https://console.apify.com
AZURE_OPENAI_API_KEY=your_key         # Azure OpenAI API key

# Optional
EXCHANGERATE_API_KEY=your_key         # For live currency rates (free tier works)
```

## Dependencies

```
python-dotenv   # .env file loading
requests        # HTTP client for Apify + Azure OpenAI
```

No ML libraries needed. All analysis uses stdlib `statistics`.

## Statistical Methodology

- **Median** used throughout (robust to Alibaba's outlier/bait pricing)
- **Controlled comparisons** — when computing the delta for attribute X, all other flex attributes are held constant at the user's values
- **QCD (Quartile Coefficient of Dispersion)** — `(P75-P25)/(P75+P25)`, consistent with median-based analysis (unlike CV which uses mean/stdev)
- **Progressive baseline relaxation** — tries matching all flex attrs, then drops one at a time, then uses full pool
- **No ML prediction** — all prices are observed from real Alibaba listings. Absolute prices are unreliable; only low-variance deltas are trustworthy.
