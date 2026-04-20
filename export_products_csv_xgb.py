import argparse
import csv
import os

import sys
from typing import List
import re


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in-csv", default="products.csv")
    parser.add_argument("--price-source", default="products_cleaned.csv")
    parser.add_argument("--cleaned-out", default="products_cleaned_xgb.csv")
    args = parser.parse_args()

    if not os.path.exists(args.in_csv):
        print(f"Error: {args.in_csv} not found.")
        sys.exit(1)

    with open(args.in_csv, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)
        
    filtered_headers = list(headers)
    
    data_rows = []
    for r in rows:
        rd = {}
        for h, v in zip(headers, r):
            rd[h] = "" if v is None else str(v)
        data_rows.append(rd)

    def norm(s: str) -> str:
        return s.strip().lower().replace(" ", "_").replace("-", "_")

    def find_col(candidates: List[str]) -> str:
        for h in filtered_headers:
            if norm(h) in candidates:
                return h
        return ""

    cap_col = find_col(["battery_capacity_mah", "battery_capacity", "battery_capacity_mah_"])
    if cap_col:
        parsed = []
        for rd in data_rows:
            s = rd.get(cap_col, "")
            # For battery capacity, try to extract the main capacity value
            # Handle formats like: "400mAh", "200-500mah", "400mAh+40mAh*2", "28mAh/180mAh"
            if not s.strip():
                parsed.append(None)
                continue
                
            # Look for patterns like "XXXmAh" or "XXX-XXXmAh"
            m = re.search(r'(\d+(?:\.\d+)?)\s*-?\s*(\d+(?:\.\d+)?)?\s*mah', s.lower())
            if m:
                if m.group(2):  # Range like "200-500mah"
                    # Take the first value or average - you can choose what makes sense
                    parsed.append(float(m.group(1)))
                else:  # Single value like "400mAh"
                    parsed.append(float(m.group(1)))
            else:
                # If no mAh pattern found, try to extract any number
                nums = re.findall(r"\d+(?:\.\d+)?", s)
                if nums:
                    # Take the first/largest number
                    parsed.append(float(max(nums, key=float)))
                else:
                    parsed.append(None)
                    
        for i, v in enumerate(parsed):
            data_rows[i][cap_col] = str(v) if v is not None else "" 

    form_col = find_col(["headphone_form_factor", "headphone_form", "form_factor"])
    if form_col:
        cats = set()
        for rd in data_rows:
            s = rd.get(form_col, "").strip().lower().replace("-", " ")
            if not s:
                s = "other"
            
            parts = [p.strip() for p in re.split(r'[,/|;]', s) if p.strip()]
            if not parts:
                parts = ["other"]
                
            rd[form_col] = ", ".join(parts)
            for p in parts:
                cats.add(p)
                
        for cat in sorted(cats):
            nc = f"{norm(form_col)}_{norm(cat)}"
            filtered_headers.append(nc)
            for rd in data_rows:
                rd[nc] = "1" if cat in rd.get(form_col, "") else "0"
                
        filtered_headers.remove(form_col)
        for rd in data_rows:
            rd.pop(form_col, None)

    water_col = find_col(["waterproof_standard", "waterproof", "waterproof_rating"])
    if water_col:
        vals = []
        parsed = []
        for rd in data_rows:
            s = rd.get(water_col, "").strip().lower()
            if s in ("no", "none", "/"):
                v = 0
            else:
                m = re.search(r"(\d+)", s)
                v = int(m.group(1)) if m else None
            parsed.append(v)
            if v is not None:
                vals.append(v)
        for i, v in enumerate(parsed):
            data_rows[i][water_col] = str(v) if v is not None else "" 

    # Process battery_charging_time and charging_time separately
    battery_charge_col = find_col(["battery_charging_time"])
    if battery_charge_col:
        parsed = []
        for rd in data_rows:
            s = rd.get(battery_charge_col, "").strip().lower()
            if not s:
                parsed.append(None)
                continue
                
            # Handle different formats:
            # "30 minutes" -> 0.5
            # "1-3 hours" -> 2.0  
            # "1~3 Hours" -> 2.0
            # "2h" -> 2.0
            # "2 Hours" -> 2.0
            
            if "30 minutes" in s:
                parsed.append(0.5)
            elif "1-3 hours" in s or "1~3 hours" in s:
                parsed.append(2.0)
            elif "2-3 hours" in s or "2~3 hours" in s:
                parsed.append(2.5)
            elif "3-5 hours" in s or "3~5 hours" in s:
                parsed.append(4.0)
            else:
                # Try to extract any number
                nums = re.findall(r"\d+(?:\.\d+)?", s)
                if nums:
                    # Take the first number
                    parsed.append(float(nums[0]))
                else:
                    parsed.append(None)
                    
        for i, v in enumerate(parsed):
            data_rows[i][battery_charge_col] = str(v) if v is not None else ""

    # Also process the separate charging_time column if it exists
    charge_time_col = find_col(["charging_time"])
    if charge_time_col and charge_time_col != battery_charge_col:
        parsed = []
        for rd in data_rows:
            s = rd.get(charge_time_col, "").strip().lower()
            if not s:
                parsed.append(None)
                continue
                
            # Handle different formats for charging_time
            if "30 minutes" in s or "30 ms" in s:
                parsed.append(0.5)
            elif "1-3 hours" in s or "1~3 hours" in s or "1 hour" in s:
                parsed.append(2.0)
            elif "2-3 hours" in s or "2~3 hours" in s or "2 hours" in s or "2h" in s:
                parsed.append(2.5)
            elif "3-5 hours" in s or "3~5 hours" in s or "3 hours" in s:
                parsed.append(4.0)
            else:
                # Try to extract any number
                nums = re.findall(r"\d+(?:\.\d+)?", s)
                if nums:
                    # Take the first number
                    parsed.append(float(nums[0]))
                else:
                    parsed.append(None)
                    
        for i, v in enumerate(parsed):
            data_rows[i][charge_time_col] = str(v) if v is not None else "" 

    ind_col = find_col(["battery_indicator"])
    if ind_col:
        led_c = f"{norm(ind_col)}_LED"
        dd_c = f"{norm(ind_col)}_Digital Display"
        other_c = f"{norm(ind_col)}_Other"
        filtered_headers.extend([led_c, dd_c, other_c])
        for rd in data_rows:
            s = rd.get(ind_col, "").strip().lower() or "other"
            rd[led_c] = "1" if "led" in s else "0"
            rd[dd_c] = "1" if "digital display" in s else "0"
            rd[other_c] = "1" if "other" in s else "0"
        filtered_headers.remove(ind_col)
        for rd in data_rows:
            rd.pop(ind_col, None)

    iface_col = find_col(["charging_interface_type", "charging_interface"])
    if iface_col:
        cats = [
            ("Type-C", r"type[\s\-]?c|usb[\s\-]?c"),
            ("Magnetic Materials", r"magnetic"),
            ("Micro USB", r"micro\s*usb"),
            ("Head-mounted", r"head[\s\-]?mounted"),
            ("Wireless Charging", r"wireless"),
            ("No_Specific", r"no_specific"),
        ]
        new_cols = []
        for label, _ in cats:
            nc = f"{norm(iface_col)}_{label}"
            new_cols.append(nc)
            filtered_headers.append(nc)
        for rd in data_rows:
            s = rd.get(iface_col, "").strip().lower()
            if s in ("", "none"):
                s = "no_specific"
            for (label, pattern), nc in zip(cats, new_cols):
                rd[nc] = "1" if re.search(pattern, s) else "0"
        filtered_headers.remove(iface_col)
        for rd in data_rows:
            rd.pop(iface_col, None)

    chip_col = find_col(["chipset", "chip"])
    if chip_col:
        cats = ["JL", "Airoha", "Bluetrum", "Qualcomm", "SmartLink", "BK", "ZHONGKE", "solo Buds", "headset", "Loda", "Other"]
        new_cols = []
        for cat in cats:
            nc = f"{norm(chip_col)}_{cat}"
            new_cols.append(nc)
            filtered_headers.append(nc)
        for rd in data_rows:
            s = rd.get(chip_col, "").strip().lower() or "other"
            s = s.replace("jlzk", "jl").replace("jieli", "jl")
            t = s
            if "jl" in s:
                t = "jl"
            elif "zhongke" in s:
                t = "zhongke"
            elif "blurtrum" in s or "bluetrum" in s:
                t = "bluetrum"
            for cat, nc in zip(cats, new_cols):
                rd[nc] = "1" if cat.lower() in t else "0"
        filtered_headers.remove(chip_col)
        for rd in data_rows:
            rd.pop(chip_col, None)

    codecs_col = find_col(["codecs"])
    if codecs_col:
        cats = ["SBC", "AAC", "APT", "LHDC", "LC3", "LDAC", "Other"]
        new_cols = []
        for cat in cats:
            nc = f"{norm(codecs_col)}_{norm(cat)}"
            new_cols.append(nc)
            filtered_headers.append(nc)
        for rd in data_rows:
            s = (rd.get(codecs_col, "") or "other").strip().lower()
            if s in ("", "none"):
                s = "other"
            for cat, nc in zip(cats, new_cols):
                rd[nc] = "1" if cat.lower() in s else "0"
        filtered_headers.remove(codecs_col)
        for rd in data_rows:
            rd.pop(codecs_col, None)

    ctrl_col = find_col(["control_method", "control"])
    if ctrl_col:
        cats = ["Touch", "Voice", "Button", "App", "Other"]
        new_cols = []
        for cat in cats:
            nc = f"{norm(ctrl_col)}_{norm(cat)}"
            new_cols.append(nc)
            filtered_headers.append(nc)
        for rd in data_rows:
            s = (rd.get(ctrl_col, "") or "other").strip().lower()
            if s in ("", "none"):
                s = "other"
            for cat, nc in zip(cats, new_cols):
                rd[nc] = "1" if cat.lower() in s else "0"
        filtered_headers.remove(ctrl_col)
        for rd in data_rows:
            rd.pop(ctrl_col, None)

    mat_col = find_col(["material"])
    if mat_col:
        mats = ["abs", "plastic", "leather", "metal", "pu", "pc", "electronics", "silica gel"]
        for m in mats:
            nc = f"{norm(mat_col)}_{m}"
            filtered_headers.append(nc)
        other_nc = f"{norm(mat_col)}_Other"
        filtered_headers.append(other_nc)
        for rd in data_rows:
            s = (rd.get(mat_col, "") or "other").lower()
            anym = False
            for m in mats:
                nc = f"{norm(mat_col)}_{m}"
                has = bool(re.search(re.escape(m), s))
                rd[nc] = "1" if has else "0"
                anym = anym or has
            rd[other_nc] = "1" if not anym else "0"
        filtered_headers.remove(mat_col)
        for rd in data_rows:
            rd.pop(mat_col, None)

    for yn in ["private_mold", "volume_control"]:
        yn_col = find_col([yn])
        if yn_col:
            for rd in data_rows:
                s = (rd.get(yn_col, "") or "").strip().lower()
                rd[yn_col] = "1" if s == "yes" else "0"

    sq_col = find_col(["sound_quality"])
    if sq_col:
        # 2. Standardize Text
        for rd in data_rows:
            s = rd[sq_col].lower()
            s = re.sub(r'high fidelity \(hi-fi\)|high fidelity|hifi|hi-fi', 'Hi-Fi', s)
            s = re.sub(r'3d|stereo|surround sound', '3D', s)
            rd[sq_col] = s

        # 3. Extract Unique Categories
        unique_sq = set()
        for rd in data_rows:
            s = rd[sq_col]
            if not s.strip() or s.lower() == "other":
                continue
            parts = re.split(r'[,/|;]', s)
            for p in parts:
                p = p.strip()
                if p and p.lower() != "other":
                    if p.lower() == 'hi-fi': p = 'Hi-Fi'
                    elif p.lower() == '3d': p = '3D'
                    else: p = p.title()
                    unique_sq.add(p)

        new_cols = []
        for cat in sorted(unique_sq):
            nc = f"{norm(sq_col)}_{norm(cat)}"
            new_cols.append((cat, nc))
            filtered_headers.append(nc)

        for rd in data_rows:
            s = rd[sq_col].lower()
            if s == "other":
                for _, nc in new_cols:
                    rd[nc] = "0"
            else:
                for cat, nc in new_cols:
                    rd[nc] = "1" if cat.lower() in s else "0"

        filtered_headers.remove(sq_col)
        for rd in data_rows:
            rd.pop(sq_col, None)

    resp_col = find_col(["response_time_ms", "wireless_delay_time"])
    if resp_col:
        vals = []
        parsed = []
        for rd in data_rows:
            s = (rd.get(resp_col, "") or "").lower()
            m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:ms)?", s)
            if m:
                a = float(m.group(1))
                b = float(m.group(2))
                v = (a + b) / 2
            else:
                m2 = re.search(r"(\d+(?:\.\d+)?)", s)
                v = float(m2.group(1)) if m2 else None
            parsed.append(v)
            if v is not None:
                vals.append(v)
        for i, v in enumerate(parsed):
            data_rows[i][resp_col] = str(v) if v is not None else "" 

    gl_col = find_col(["game_atmosphere_light"])
    if gl_col:
        labels = [
            ("Single Color", r"single"),
            ("No Light", r"no\s*light"),
            ("RGB", r"rgb|multicolor"),
            ("No_Specific", r"no_specific"),
        ]
        for label, _ in labels:
            nc = f"{norm(gl_col)}_{label}"
            filtered_headers.append(nc)
        for rd in data_rows:
            s = (rd.get(gl_col, "") or "").strip().lower()
            if s in ("", "none"):
                s = "no_specific"
            for label, pattern in labels:
                nc = f"{norm(gl_col)}_{label}"
                rd[nc] = "1" if re.search(pattern, s) else "0"
        filtered_headers.remove(gl_col)
        for rd in data_rows:
            rd.pop(gl_col, None)

    brand_col = find_col(["brand_name", "brand"])
    if brand_col:
        nc_oem = f"{norm(brand_col)}_oem_odm"
        filtered_headers.append(nc_oem)
        
        brand_counts = {}
        for rd in data_rows:
            s = (rd.get(brand_col, "") or "").strip()
            rd[brand_col] = s
            if not s:
                rd[nc_oem] = ""
                continue
            s_low = s.lower()
            
            is_oem = bool(re.search(r'\b(oem/odm|oem|odm|none|no)\b', s_low))
            rd[nc_oem] = "1" if is_oem else "0"
            
            if not is_oem:
                parts = [p.strip() for p in re.split(r'[,/|;]', s) if p.strip()]
                for p in parts:
                    if p.lower() != "other":
                        brand_counts[p] = brand_counts.get(p, 0) + 1
        
        # Group rare brands (count < 5) into 'other'
        actual_brands = {b for b, count in brand_counts.items() if count >= 5}
                
        new_cols = []
        for b in sorted(actual_brands):
            nc = f"{norm(brand_col)}_{norm(b)}"
            new_cols.append((b, nc))
            filtered_headers.append(nc)
            
        nc_other = f"{norm(brand_col)}_other"
        filtered_headers.append(nc_other)
            
        for rd in data_rows:
            is_oem = rd[nc_oem] == "1"
            s_low = rd[brand_col].lower()
            
            if not is_oem:
                any_matched = False
                for b, nc in new_cols:
                    if b.lower() in s_low:
                        rd[nc] = "1"
                        any_matched = True
                    else:
                        rd[nc] = "0"
                rd[nc_other] = "1" if not any_matched else "0"
            else:
                for b, nc in new_cols:
                    rd[nc] = "0"
                rd[nc_other] = "0"
                    
        filtered_headers.remove(brand_col)
        for rd in data_rows:
            rd.pop(brand_col, None)

    for c in ["product_name", "other_features"]:
        col = find_col([c])
        if col:
            filtered_headers.remove(col)
            for rd in data_rows:
                rd.pop(col, None)

    price_headers = ["min_quantity", "max_quantity", "price"]
    final_headers = [h for h in filtered_headers if norm(h) != "product_id"]
    for ph in price_headers:
        if ph not in final_headers:
            final_headers.append(ph)

    price_rows = []
    if os.path.exists(args.price_source):
        with open(args.price_source, "r", encoding="utf-8") as pf:
            reader = csv.DictReader(pf)
            for row in reader:
                price_rows.append({
                    "min_quantity": row.get("min_quantity", ""),
                    "max_quantity": row.get("max_quantity", ""),
                    "price": row.get("price", ""),
                })

    joined_data = []
    for idx, rd in enumerate(data_rows):
        base_rd = {k: v for k, v in rd.items() if norm(k) != "product_id"}
        if idx < len(price_rows):
            new_rd = base_rd.copy()
            min_q = price_rows[idx]["min_quantity"]
            max_q = price_rows[idx]["max_quantity"]
            price = price_rows[idx]["price"]
            new_rd["min_quantity"] = "" if min_q is None else str(min_q)
            new_rd["max_quantity"] = "" if max_q is None else str(max_q)
            new_rd["price"] = "" if price is None else str(price)
            joined_data.append(new_rd)
        else:
            new_rd = base_rd.copy()
            if "min_quantity" not in new_rd:
                new_rd["min_quantity"] = ""
            if "max_quantity" not in new_rd:
                new_rd["max_quantity"] = ""
            if "price" not in new_rd:
                new_rd["price"] = ""
            joined_data.append(new_rd)

    with open(args.cleaned_out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(final_headers)
        for rd in joined_data:
            w.writerow([rd.get(h, "") for h in final_headers])

    print(args.cleaned_out)


if __name__ == "__main__":
    main()
