#!/usr/bin/env python3
"""
Combine all JSON files in current directory into merged_dataset.json without duplicates.
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any

def get_json_files() -> List[str]:
    """Get all JSON files in current directory."""
    return [f for f in os.listdir('.') if f.endswith('.json') and f != 'merged_dataset.json']

def read_json_file(file_path: str) -> List[Dict[str, Any]]:
    """Read and parse a JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            else:
                return [data]
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"Warning: Could not parse {file_path}: {e}")
        return []

def get_unique_id(item: Dict[str, Any]) -> str:
    """Generate a unique identifier for an item to detect duplicates."""
    # Try various possible ID fields
    for field in ['productId', 'id', 'productUrl', 'url', 'title']:
        if field in item and item[field]:
            return f"{field}:{item[field]}"
    
    # Fallback: use hash of the entire item
    return f"hash:{hash(json.dumps(item, sort_keys=True))}"

def merge_json_files() -> None:
    """Merge all JSON files into merged_dataset.json without duplicates."""
    json_files = get_json_files()
    
    if not json_files:
        print("No JSON files found in current directory.")
        return
    
    print(f"Found {len(json_files)} JSON files: {json_files}")
    
    all_items = []
    seen_ids = set()
    
    for json_file in json_files:
        print(f"Processing {json_file}...")
        items = read_json_file(json_file)
        
        if not items:
            print(f"  No valid data in {json_file}")
            continue
            
        print(f"  Found {len(items)} items")
        
        for item in items:
            item_id = get_unique_id(item)
            
            if item_id not in seen_ids:
                seen_ids.add(item_id)
                all_items.append(item)
    
    print(f"\nTotal unique items: {len(all_items)}")
    
    # Write merged dataset
    with open('merged_dataset.json', 'w', encoding='utf-8') as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    
    print(f"Merged dataset saved to merged_dataset.json")
    
    # Show summary
    print(f"\nSummary:")
    print(f"- Input files: {len(json_files)}")
    print(f"- Total items processed: {sum(len(read_json_file(f)) for f in json_files)}")
    print(f"- Unique items: {len(all_items)}")
    print(f"- Duplicates removed: {sum(len(read_json_file(f)) for f in json_files) - len(all_items)}")

if __name__ == "__main__":
    merge_json_files()