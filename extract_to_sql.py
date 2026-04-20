import json
import sqlite3
import os
import sys
import argparse
from typing import Dict, Any, List
from openai import OpenAI
from apify.client import ApifyClient

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(BASE_DIR, "merged_dataset.json")
SQL_FILE = os.path.join(BASE_DIR, "products_attributes.db")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3:8b")

# Initialize OpenAI client for Ollama
client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key='ollama',
)

def evaluate_attribute_similarity(new_attr: str, existing_columns: List[str]) -> str:
    """
    Uses Llama3 to evaluate if a new attribute has a similar meaning to any existing column.
    Returns the name of the matching existing column, or 'NEW_COLUMN' if no match.
    """
    if not existing_columns:
        return "NEW_COLUMN"
        
    prompt = f"""
    You are an assistant that maps product attributes.
    I have a new attribute named: '{new_attr}'.
    Here is a list of existing attribute columns in my database: {existing_columns}
    
    Does the new attribute '{new_attr}' mean exactly or almost exactly the same thing as any of the existing columns? (e.g. 'name' and 'earbud name' are similar, 'color' and 'colour' are similar).
    
    If it does, reply ONLY with the exact name of the matching existing column.
    If it does NOT match any existing column, reply ONLY with the exact string "NEW_COLUMN".
    Do not provide any explanation, markdown, or extra text.
    """
    
    try:
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": "You are a strict data mapping tool. Reply only with the requested string."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=50
        )
        result = response.choices[0].message.content.strip()
        
        # Clean up potential extra quotes or markdown
        result = result.replace("'", "").replace('"', "").replace("`", "")
        
        if result in existing_columns:
            return result
        return "NEW_COLUMN"
        
    except Exception as e:
        print(f"Error calling Ollama for '{new_attr}': {e}")
        return "NEW_COLUMN"

def clean_column_name(name: str) -> str:
    """Clean attribute name to be a valid SQLite column name."""
    clean = "".join(c if c.isalnum() else "_" for c in name)
    # Ensure it doesn't start with a number
    if clean and clean[0].isdigit():
        clean = "attr_" + clean
    return clean.lower()

def main():
    parser = argparse.ArgumentParser(description="Extract product attributes and price tiers to SQLite")
    parser.add_argument("--dataset", dest="dataset_id", help="Apify dataset ID to fetch items from (e.g., 6dI6ddbYZKJ5zcVkB)")
    parser.add_argument("--token", dest="api_token", help="Apify API token (overrides APIFY_TOKEN env var)")
    parser.add_argument("--limit", type=int, default=1000, help="Limit items fetched from Apify dataset")
    parser.add_argument("--json", dest="json_path", default=JSON_FILE, help="Path to local JSON file (fallback if no --dataset)")
    args = parser.parse_args()

    data: List[Dict[str, Any]] = []
    if args.dataset_id:
        print(f"Loading dataset items from Apify dataset '{args.dataset_id}'...")
        try:
            client = ApifyClient(api_token=args.api_token)
            data = client.get_dataset_items(args.dataset_id, limit=args.limit)
        except Exception as e:
            print(f"Error fetching dataset from Apify: {e}")
            sys.exit(1)
    else:
        json_path = args.json_path
        if not os.path.exists(json_path):
            print(f"Error: {json_path} not found.")
            sys.exit(1)
        print(f"Loading {json_path}...")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

    # Dictionary to hold the final processed data for each product
    # List of dictionaries: [{col1: val1, col2: val2}, ...]
    processed_products = []
    
    # List to hold the price tiers for each product
    # Format: [{"product_id": "...", "min_quantity": 10, "max_quantity": 99, "price": 5.5}, ...]
    processed_prices = []
    
    # Keep track of existing columns to pass to the LLM
    # Use clean column names as keys, original names as values for display if needed
    existing_columns = {} 

    # Connect to SQLite
    if os.path.exists(SQL_FILE):
        os.remove(SQL_FILE) # Start fresh
    
    conn = sqlite3.connect(SQL_FILE)
    cursor = conn.cursor()

    print(f"Processing {len(data)} products...")
    
    for i, product in enumerate(data):
        print(f"Processing product {i+1}/{len(data)}...")
        
        product_attrs = {}
        
        # Always extract product ID and subject as base columns
        product_id = str(product.get('productId', ''))
        product_attrs['product_id'] = product_id
        product_attrs['subject'] = product.get('subject', '')
        # Product and supplier URLs
        product_attrs['product_url'] = product.get('url') or product.get('productUrl') or ''
        supplier_info = product.get('supplierInfo', {}) or {}
        product_attrs['supplier_profile_url'] = (
            supplier_info.get('profileUrl')
            or supplier_info.get('companyUrl')
            or supplier_info.get('url')
            or ''
        )
        product_attrs['supplier_home_url'] = (
            supplier_info.get('homeUrl')
            or supplier_info.get('homeurl')
            or ''
        )
        
        # Extract main image URL
        image_url = ""
        media_items = product.get('mediaItems', [])
        for item in media_items:
            if item.get('type') == 'image' and 'imageUrl' in item:
                image_url = item['imageUrl'].get('big', item['imageUrl'].get('normal', ''))
                if image_url:
                    break
        product_attrs['image_url'] = image_url
        
        existing_columns['product_id'] = 'product_id'
        existing_columns['subject'] = 'subject'
        existing_columns['image_url'] = 'image_url'
        existing_columns['product_url'] = 'product_url'
        existing_columns['supplier_profile_url'] = 'supplier_profile_url'
        existing_columns['supplier_home_url'] = 'supplier_home_url'

        # Extract price ladder tiers
        price_info = product.get('price', {})
        if price_info:
            ladder_prices = price_info.get('productLadderPrices', [])
            if ladder_prices:
                for tier in ladder_prices:
                    processed_prices.append({
                        "product_id": product_id,
                        "min_quantity": tier.get('min'),
                        "max_quantity": tier.get('max'),
                        "price": tier.get('dollarPrice', tier.get('price')),
                        "currency": "USD"
                    })
            else:
                range_prices = price_info.get('productRangePrices', {})
                if range_prices:
                    # Get both low and high prices
                    price_low = range_prices.get('dollarPriceRangeLow', range_prices.get('priceRangeLow'))
                    price_high = range_prices.get('dollarPriceRangeHigh', range_prices.get('priceRangeHigh'))
                    
                    # Calculate average price
                    avg_price = None
                    if price_low is not None and price_high is not None:
                        avg_price = (price_low + price_high) / 2.0
                    elif price_low is not None:
                        avg_price = price_low
                    elif price_high is not None:
                        avg_price = price_high
                    

                    processed_prices.append({
                        "product_id": product_id,
                        "min_quantity": None,
                        "max_quantity": None,
                        "price": avg_price, 
                        "currency": "USD"
                    })

        # Extract attributes from productProperties and productOtherProperties
        raw_attrs = {}
        
        for prop in product.get('productProperties', []):
            if 'attrName' in prop and 'attrValue' in prop:
                raw_attrs[prop['attrName']] = prop['attrValue']
                
        for prop in product.get('productOtherProperties', []):
            if 'attrName' in prop and 'attrValue' in prop:
                raw_attrs[prop['attrName']] = prop['attrValue']

        # Process each extracted attribute
        for attr_name, attr_value in raw_attrs.items():
            if not attr_name or not attr_value:
                continue
                
            clean_name = clean_column_name(attr_name)
            
            # If we already have this exact column, use it
            if clean_name in existing_columns:
                product_attrs[clean_name] = str(attr_value)
                continue
                
            # If not, use LLM to check if it matches an existing column
            print(f"  Checking new attribute: '{attr_name}'...")
            matched_col = evaluate_attribute_similarity(clean_name, list(existing_columns.keys()))
            
            if matched_col != "NEW_COLUMN" and matched_col in existing_columns and matched_col not in product_attrs:
                print(f"    -> Mapped to existing column: '{matched_col}'")
                product_attrs[matched_col] = str(attr_value)
            else:
                print(f"    -> Created new column: '{clean_name}'")
                existing_columns[clean_name] = clean_name
                product_attrs[clean_name] = str(attr_value)
                
        processed_products.append(product_attrs)

    # Now create the table with all discovered columns
    print("\nCreating database schema...")
    columns_def = ", ".join([f"{col} TEXT" for col in existing_columns.keys()])
    create_table_sql = f"CREATE TABLE products ({columns_def});"
    cursor.execute(create_table_sql)
    
    # Create the prices table
    create_prices_sql = """
    CREATE TABLE product_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id TEXT,
        min_quantity INTEGER,
        max_quantity INTEGER,
        price REAL,
        currency TEXT,
        FOREIGN KEY(product_id) REFERENCES products(product_id)
    );
    """
    cursor.execute(create_prices_sql)
    
    # Insert data
    print("Inserting data into database...")
    for prod in processed_products:
        cols = list(prod.keys())
        vals = list(prod.values())
        
        placeholders = ", ".join(["?"] * len(cols))
        cols_str = ", ".join(cols)
        
        insert_sql = f"INSERT INTO products ({cols_str}) VALUES ({placeholders})"
        cursor.execute(insert_sql, vals)
        
    # Insert price data
    print("Inserting price tiers into database...")
    for price_tier in processed_prices:
        cursor.execute("""
            INSERT INTO product_prices (product_id, min_quantity, max_quantity, price, currency)
            VALUES (?, ?, ?, ?, ?)
        """, (
            price_tier['product_id'], 
            price_tier['min_quantity'], 
            price_tier['max_quantity'], 
            price_tier['price'],
            price_tier['currency']
        ))
        
    conn.commit()
    conn.close()
    
    print(f"\nSuccessfully extracted attributes and saved to {SQL_FILE}")
    print(f"Total columns created in products table: {len(existing_columns)}")
    print(f"Total price tiers extracted: {len(processed_prices)}")

if __name__ == "__main__":
    main()
