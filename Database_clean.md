Do not change anything in products_attributes.db 
create a new python file to do following data cleaning
all the matching bellow using substring matching (case-insensitive)
each cell may have value more than 1 category, splited by comma,

## Step-by-Step Implementation Logic

### 0. Data Extraction
- Connect to `products_attributes.db`.
- Read the `products` table into a pandas DataFrame (`df`).
- (Optional) Save an initial copy as `products_raw.csv`.

### 1. Initial Column Removal
- Remove the following specific columns: `product_id`, `subject`, `image_url`, `product_url`, `supplier_profile_url`, `supplier_home_url`, `place of origin`.
- Remove any columns where the percentage of missing (`NaN`, `None`, empty string) values exceeds 70%.

### 2. Clean `battery_capacity_mah` Column
- For each cell, extract all integer numbers using regex.
- If integers are found, calculate their average and replace the cell with that average (as a float or int).
- If the cell contains no integers (only text), set the cell to `np.nan`.
- Fill all remaining `NaN` values in the column with the column's **median** value.

### 3. Clean `headphone_form_factor` Column
a. **Fill Missing Values:** Replace all blank/`NaN` cells with `"other"`.
b. **Standardize Text:**
    - Convert text to lowercase.
    - Remove hyphens (e.g., `"in-ear"` -> `"in ear"`).
c. **One-Hot Encoding:**
    - Identify unique categories (e.g., `"in ear"`, `"over ear"`, `"on ear"`, `"other"`).
    - Create new binary columns for each category (e.g., `headphone_form_factor_in_ear`).
    - For each original cell, if it contains the category string, the corresponding new column gets `1`.
    - Identify categories in the defined list using partial matching (case-insensitive).
    - The original `headphone_form_factor` column is **dropped**.


### 4. Clean `waterproof_standard` Column
a. **Extract Integers:** For any cell containing an integer, extract the first integer found and replace the whole cell with it (as a numeric type).
b. **Calculate Mean:** Compute the mean of all extracted integers.
c. **Handle Specific Text:** If the cell text is `"No"`, `"None"`, or `"/"`, replace with `0`.
d. **Fill Remaining:** Fill all other cells (those that had no integer and are not from step c, or were blank) with the mean calculated in step b.

### 5. Clean `battery_charging_time` Column
a. **Process Ranges:** For cells matching pattern `"X-Y hours"` or `"X-Y"`, calculate average `(X+Y)/2`.
b. **Handle "30 minutes":** Replace exact string `"30 minutes"` with `0.5`.
c. **Fill Remaining:**
    - Collect all numeric results from steps a & b.
    - Compute their average.
    - Replace all other cells (blanks, text like `"fast charge"`) with this average.

### 6. Clean `battery_indicator` Column
a. **Fill Missing:** Replace all blank/`NaN` cells with `"Other"`.
b. **One-Hot Encoding:**
    - Create three new columns: `battery_indicator_LED`, `battery_indicator_Digital Display`, `battery_indicator_Other`.
    - For each original cell, perform case-insensitive search:
        - Contains `"led"` -> `LED` = 1
        - Contains `"digital display"` -> `Digital Display` = 1
        - Contains `"other"` -> `Other` = 1
    - A cell can set multiple columns to 1.
    - Identify categories in the defined list using partial matching (case-insensitive).
- Drop the original `battery_indicator` column.

### 7. Clean `charging_interface_type` Column
a. **Fill Missing:** Replace blank/`NaN` and cells with text `"None"` with `"No_Specific"`.
b. **One-Hot Encoding:**
    - Create six new columns: `charging_interface_type_Type-C`, `charging_interface_type_Magnetic Materials`, `charging_interface_type_Micro USB`, `charging_interface_type_Head-mounted`, `charging_interface_type_Wireless Charging`, `charging_interface_type_No_Specific`.
    - Case-insensitive substring matching. A cell can belong to multiple categories.
    - Identify categories in the defined list using partial matching (case-insensitive).
- Drop the original `charging_interface_type` column.

### 8. Clean `chipset` Column
1. **Fill Missing:** Replace blank/`NaN` with `"other"`.
2. **Standardize Categories:** Map known variants to a standard name (case-insensitive):
    - `"jl"`, `"jieli"`, `"jlzk"` -> `"JL"`
    - `"zhongke"` -> `"ZHONGKE"`
    - `"blurtrum"` -> `"Bluetrum"` (Assuming this is a typo for Bluetrum)
3. **Define Category List:** `["JL", "Airoha", "Bluetrum", "Qualcomm", "SmartLink", "BK", "ZHONGKE", "solo Buds", "headset", "Loda", "Other"]`
4. **One-Hot Encoding:** Create a new binary column for each category in the list. Substring matching. Multi-label allowed.
    - Identify categories in the defined list using partial matching (case-insensitive).
5. Drop the original `chipset` column.

### 9. Clean `codecs`column 
1. **Fill Missing:** Replace blank/`NaN` or text `"None"` with `"Other"`.
2. **Define Category List:** in codecs:`["SBC", "AAC","APT","LHDC","LC3","LDAC","Other"]`
3. **One-Hot Encoding:** Create a new binary column for each unique category. Substring matching. Multi-label allowed.
    - Identify categories in the defined list using partial matching (case-insensitive).
4. Drop the original `codecs` column.

### 10. Clean `control_method` column
1. **Fill Missing:** Replace blank/`NaN` or text `"None"` with `"Other"`.
2. **Define Category List:** in control_method:`["Touch","Voice","Button","App","Other".]`
3. **One-Hot Encoding:** Create a new binary column for each unique category. Substring matching. Multi-label allowed.
    - Identify categories in the defined list using partial matching (case-insensitive).
4. Drop the original `control_method` column.

### 11. Clean `material` Column
1. **Fill Missing:** Replace blank/`NaN` with `"Other"`.
2. **Define Category List:** `["Abs", "Plastic", "Leather", "Metal", "PU", "PC", "Electronics", "Silica Gel"]` (Note: Corrected "Sillica Gel" to "Silica Gel").
3. **One-Hot Encoding:** Create a new binary column for each material. Substring matching. For cells not matching any listed material, ensure they are represented in the `material_Other` column. Multi-label allowed.
    - Identify categories in the defined list using partial matching (case-insensitive).
4. Drop the original `material` column.

### 12. Clean `private_mold` and `volume_control` Columns
- For each column, map values:
    - `"yes"`, `"Yes"`, `"YES"` -> `1`
    - `"no"`, `"No"`, `"NO"`, blank, `NaN` -> `0`

### 13. Clean `sound_quality` Column
1. **Fill Missing:** Replace blank/`NaN` with `"Other"`.
2. **Standardize Text** (case-insensitive):
    - `"hi-fi"`, `"high fidelity"`, `"high fidelity (hi-fi)"`, `"hifi"`  -> `"Hi-Fi"`
    - `"3d"`, `"stereo"`, `"surround sound"` -> `"3D"`
3. **Extract Unique Categories:** Dynamically identify all unique categories (e.g., `"Hi-Fi"`, `"3D"`, `"Bass"`). **Do not** create a column for the placeholder `"Other"`.
4. **One-Hot Encoding:** Create a new binary column for each unique category (excluding `"Other"`). Substring matching. Multi-label allowed.
    - A cell filled as `"Other"` will have `0` in all new sound quality columns.
    - Identify categories in the defined list using partial matching (case-insensitive).
5. Drop the original `Sound_quality` column.

### 14. Clean `wireless_delay_time` Column
a. **Process Ranges:** For cells like `"40-50 ms"`, calculate average `(40+50)/2 = 45`.
b. **Single Digit:** For cells with a single number, extract that number.
c. **Fill Remaining:** Compute the average of all results from steps a & b. Replace all other cells (blanks, text) with this average.

### 15. Clean `game_atmosphere_light` Column
a. **Fill Missing:** Replace blank/`NaN` and cells with text `"None"` with `"No_Specific"`.
b. **Standardize:** Map `"rgb"` and `"multicolor"` to `"RGB"`.
c. **One-Hot Encoding:** Create four new columns: `game_atmosphere_light_Single Color`, `game_atmosphere_light_No Light`, `game_atmosphere_light_RGB`, `game_atmosphere_light_No_Specific`. Case-insensitive substring matching. Multi-label allowed.
    - Identify categories in the defined list using partial matching (case-insensitive).
d. Drop the original `game_atmosphere_light` column.

### 16. Clean brand_name Column
1. Fill Missing: Replace blank/NaN values with "other".
2. OEM/ODM Flag Column:
   • Create a new binary column named brand_name_OEM_ODM.
   • For each cell, check(substring matching) if it contains (case-insensitive) any of: "oem/odm", "oem", "odm", "none", or "no".
   • If yes: set brand_name_OEM_ODM to 1.
   • If no: set brand_name_OEM_ODM to 0.
3. Extract Actual Brand Names:
   • From the cleaned column, identify all unique values that do not contain the OEM/ODM patterns from step 2.
4. One-Hot Encoding for Actual Brands:
   • For each unique actual brand name found in step 3, create a new binary column named brand_name_<Brand>.
   • Use substring matching (case-insensitive) to assign 1 to matching cells.
   • Cells that are OEM/ODM (step 2 flag = 1) do not get encoded as separate brands.
5. Drop Original: Remove the original brand_name column.

### 17. Final Column Removal
- Remove the `product_name` and `other_features` columns.

### 18. Save Output
- Save the fully cleaned and transformed DataFrame to a new CSV file (e.g., `products_cleaned.csv`).
