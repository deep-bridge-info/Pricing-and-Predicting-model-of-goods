import argparse
import csv
import os
import sqlite3
import sys
from typing import List
import re


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="products_attributes.db")
    parser.add_argument("--out", default="products.csv")
    parser.add_argument("--blank-threshold", type=float, default=0.7)
    parser.add_argument("--cleaned-out", default="products_cleaned.csv")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"Error: {args.db} not found.")
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
    row = cur.fetchone()
    if not row:
        conn.close()
        print("Error: 'products' table not found.")
        sys.exit(1)

    cur.execute("SELECT * FROM products")
    headers: List[str] = [d[0] for d in cur.description]
    rows = cur.fetchall()

    drop_exact = {
        "subject",
        "image_url",
        "product_url",
        "supplier_profile_url",
        "supplier_home_url",
        "place of origin",
        "place_of_origin",
    }
    """
    drop_exact = {
        "product_id",
        "subject",
        "image_url",
        "product_url",
        "supplier_profile_url",
        "supplier_home_url",
        "place of origin",
        "place_of_origin",
    }"""
    
    def norm(s: str) -> str:
        return s.strip().lower().replace(" ", "_").replace("-", "_")

    keep_indices = []
    n_rows = len(rows)
    for idx, h in enumerate(headers):
        h_norm = norm(h)
        if h_norm in drop_exact:
            continue
        if n_rows > 0:
            blanks = 0
            for r in rows:
                v = r[idx]
                if v is None or str(v).strip() == "":
                    blanks += 1
            if blanks / n_rows > args.blank_threshold:
                continue
        keep_indices.append(idx)

    filtered_headers = [headers[i] for i in keep_indices]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(filtered_headers)
        for r in rows:
            w.writerow(["" if r[i] is None else r[i] for i in keep_indices])

    data_rows = []
    for r in rows:
        rd = {}
        for i, h in zip(keep_indices, filtered_headers):
            v = r[i]
            rd[h] = "" if v is None else str(v)
        data_rows.append(rd)

    def find_col(candidates: List[str]) -> str:
        for h in filtered_headers:
            if norm(h) in candidates:
                return h
        return ""

    cap_col = find_col(["battery_capacity_mah", "battery_capacity", "battery_capacity_mah_"])
    if cap_col:
        vals = []
        parsed = []
        for rd in data_rows:
            s = rd.get(cap_col, "")
            ints = re.findall(r"\d+", s)
            if ints:
                ns = [int(x) for x in ints]
                avg = sum(ns) / len(ns)
                parsed.append(avg)
                vals.append(avg)
            else:
                parsed.append(None)
        med = 0
        if vals:
            sv = sorted(vals)
            m = len(sv) // 2
            med = sv[m] if len(sv) % 2 == 1 else (sv[m - 1] + sv[m]) / 2
        for i, v in enumerate(parsed):
            data_rows[i][cap_col] = str(v if v is not None else med)

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
        mean_v = sum(vals) / len(vals) if vals else 0
        for i, v in enumerate(parsed):
            data_rows[i][water_col] = str(v if v is not None else mean_v)

    charge_col = find_col(["battery_charging_time", "charging_time"])
    if charge_col:
        vals = []
        parsed = []
        for rd in data_rows:
            s = rd.get(charge_col, "").strip().lower()
            if s == "30 minutes":
                v = 0.5
            else:
                m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)(?:\s*hours)?", s)
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
        avg_v = sum(vals) / len(vals) if vals else 0
        for i, v in enumerate(parsed):
            data_rows[i][charge_col] = str(v if v is not None else avg_v)

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
        # 1. Fill Missing
        for rd in data_rows:
            if not rd.get(sq_col, "").strip():
                rd[sq_col] = "Other"
                
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
            if s.lower() == "other":
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
        avg_v = sum(vals) / len(vals) if vals else 0
        for i, v in enumerate(parsed):
            data_rows[i][resp_col] = str(v if v is not None else avg_v)

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
        
        actual_brands = set()
        for rd in data_rows:
            s = (rd.get(brand_col, "") or "").strip()
            if not s:
                s = "other"
            rd[brand_col] = s
            s_low = s.lower()
            
            is_oem = bool(re.search(r'\b(oem/odm|oem|odm|none|no)\b', s_low))
            rd[nc_oem] = "1" if is_oem else "0"
            
            if not is_oem:
                parts = [p.strip() for p in re.split(r'[,/|;]', s) if p.strip()]
                for p in parts:
                    if p.lower() != "other":
                        actual_brands.add(p)
                
        new_cols = []
        for b in sorted(actual_brands):
            nc = f"{norm(brand_col)}_{norm(b)}"
            new_cols.append((b, nc))
            filtered_headers.append(nc)
            
        for rd in data_rows:
            is_oem = rd[nc_oem] == "1"
            s_low = rd[brand_col].lower()
            for b, nc in new_cols:
                if is_oem:
                    rd[nc] = "0"
                else:
                    rd[nc] = "1" if b.lower() in s_low else "0"
                    
        filtered_headers.remove(brand_col)
        for rd in data_rows:
            rd.pop(brand_col, None)

    for c in ["product_name", "other_features"]:
        col = find_col([c])
        if col:
            filtered_headers.remove(col)
            for rd in data_rows:
                rd.pop(col, None)

    # Fetch prices from DB to join with products
    cur.execute("SELECT product_id, min_quantity, max_quantity, price, currency FROM product_prices")
    price_rows = cur.fetchall()
    
    prices_by_pid = {}
    for pr in price_rows:
        pid = pr[0]
        if pid not in prices_by_pid:
            prices_by_pid[pid] = []
        prices_by_pid[pid].append({
            "min_quantity": pr[1],
            "max_quantity": pr[2],
            "price": pr[3],
            "currency": pr[4]
        })

    # Join price data and flatten products_cleaned
    joined_data = []
    # Add new price columns to headers
    price_headers = ["min_quantity", "max_quantity", "price", "currency"]
    final_headers = [h for h in filtered_headers if norm(h) != "product_id"] + price_headers

    for rd in data_rows:
        pid = rd.get("product_id", "")
        base_rd = {k: v for k, v in rd.items() if norm(k) != "product_id"}
        
        # If product has price tiers, create a row for each tier
        if pid in prices_by_pid:
            for tier in prices_by_pid[pid]:
                new_rd = base_rd.copy()
                
                min_q = tier["min_quantity"]
                if min_q is None or str(min_q).strip() == "":
                    new_rd["min_quantity"] = "1"
                else:
                    new_rd["min_quantity"] = str(min_q)
                    
                max_q = tier["max_quantity"]
                if max_q is None or str(max_q).strip() == "" or str(max_q) == "-1":
                    new_rd["max_quantity"] = "9999999999"
                else:
                    new_rd["max_quantity"] = str(max_q)
                    
                new_rd["price"] = tier["price"]
                new_rd["currency"] = tier["currency"]
                joined_data.append(new_rd)
        else:
            # If no price data, just append the base row with default quantities
            new_rd = base_rd.copy()
            for ph in price_headers:
                new_rd[ph] = ""
            new_rd["min_quantity"] = "1"
            new_rd["max_quantity"] = "9999999999"
            joined_data.append(new_rd)

    with open(args.cleaned_out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(final_headers)
        for rd in joined_data:
            w.writerow([rd.get(h, "") for h in final_headers])

    conn.close()
    print(args.out)
    print(args.cleaned_out)


if __name__ == "__main__":
    main()
