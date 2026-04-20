#!/bin/bash
set -e
echo "Starting collection of 1200 products..."
python3 cli.py collect-large "TWS earbuds" --products 1200 --out merged_dataset.json

echo "Extracting collected data to SQLite database..."
python3 extract_to_sql.py --json merged_dataset.json

echo "Done! 1200 products have been extracted to products_attributes.db."