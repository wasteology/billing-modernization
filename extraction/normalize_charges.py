"""
Normalize all_charges.csv equipment, material, and charge_code fields
to the canonical vocabulary in Normalization Targets/normalization_targets.json.

Adds three new columns:
  equipment_name  — matched equipment_name from normalization_targets
  material_name   — canonical material_name from normalization_targets
  service_desc    — canonical service_description from normalization_targets

Outputs: output/all_charges_normalized.csv
"""

import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
TARGETS_FILE = HERE / "Normalization Targets" / "normalization_targets.json"
INPUT_CSV = HERE / "output" / "all_charges.csv"
OUTPUT_CSV = HERE / "output" / "all_charges_normalized.csv"

# ── Equipment type → container_type ──────────────────────────────────────────

EQUIP_TYPE_MAP = {
    "FRONT_LOAD": ["Front Load"],
    "CART":       ["Tote"],
    "OPEN_TOP":   ["Open Top"],
    "ROLL_OFF":   ["Open Top"],          # roll-offs are open tops in the target schema
    "COMPACTOR":  ["Self-Cont Comp", "Compactor"],   # try Self-Cont Comp first (has real volumes)
    "OTHER":      [],
    "":           [],
}

# ── Material raw value → canonical material_name ─────────────────────────────

MATERIAL_MAP = {
    "MSW": "Trash",
    "TRASH": "Trash",
    "Trash": "Trash",
    "RECYCLING": "Mixed Recycling",
    "Recycling": "Mixed Recycling",
    "OCC": "Cardboard",
    "Cardboard": "Cardboard",
    "C&D": "C&D",
    "ORGANICS": "Organics",
    "Organics": "Organics",
    "Organic": "Organics",
    "GREASE": "Frying Oil",
    "Grease": "Frying Oil",
    "Green Waste": "Yard Waste",
    "YARD_WASTE": "Yard Waste",
    "Yard Waste": "Yard Waste",
    "Mattress": "Mattress",
    "Scrap Metal": "Scrap Metal",
    "SCRAP_METAL": "Scrap Metal",
    "Single Stream": "Single Stream",
    "SINGLE_STREAM": "Single Stream",
    "WOOD": "Wood",
    "Wood": "Wood",
}

# ── Charge code → service_desc ────────────────────────────────────────────────
# Note: Monthly Rental Commerical is intentionally misspelled in the target.

CHARGE_CODE_MAP = {
    "Compactor Installation Dry Run": "Compactor Installation",
    "Contaminated Load": "Contaminated Load",
    "Delivery Commercial": "Delivery Commercial",
    "Delivery Industrial": "Delivery Industrial",
    "Disposal": "Disposal Charge",
    "Disposal Charge": "Disposal Charge",
    "Empty & Return": "Empty & Return",
    "Environmental Surcharge": "Environmental Surcharge",
    "Extra Pick Up": "Extra Pick Up",
    "FUEL SURCHARGE": "Fuel Surcharge Commercial",
    "Final Pick Up": "Final Pick Up",
    "Franchise Fee Commercial": "Franchise Fee Commercial",
    "Inactivty Fee": "Inactivity Fee",          # typo fix
    "Local Surcharge Commercial": "Local Surcharges/Fees Commercial",
    "Lock Bar": "Lock Bar",
    "Metal Rebate": "Recycling Rebate Scrap Metal",
    "Miscellaneous": "Miscellaneous",
    "Monthly Rental Commercial": "Monthly Rental Commerical",  # target has typo
    "Monthly Rental Industrial": "Monthly Rental Industrial",
    "Monthly Service Commercial": "Monthly Service Commercial",
    "Monthly Service Industrial": "Monthly Service Industrial",
    "Overage": "Overage",
    "Recycling Offset": "Recycling Service Material",
    "Recycling Rebate": "Recycling Rebate",
    "Relocate Commercial": "Relocate Commercial",
    "Relocate Industrial": "Relocate Industrial",
    "Sales Tax": "Tax Commercial",
    "Tax Commercial": "Tax Commercial",
    "Trip Charge": "Trip Charge",
    "Vendor Late Fees": "Vendor Late Fees",
}


# ── Normalization overrides ───────────────────────────────────────────────────
# Applied before equipment lookup. Fixes misclassified equipment types and
# OCR size errors at the normalization layer (not in vendor patterns).
#
# Each rule: (equipment_type, equipment_size) → {field: corrected_value, ...}

NORMALIZATION_OVERRIDES = {
    # Meridian/SBC/WM: 30-40 YD "front loads" are actually open tops (haul/disposal)
    ("FRONT_LOAD", "30 YD"): {"equipment_type": "OPEN_TOP"},
    ("FRONT_LOAD", "40 YD"): {"equipment_type": "OPEN_TOP"},
    # Ace Recycling: 15 Yard Screen Top = open top
    ("FRONT_LOAD", "15 YD"): {"equipment_type": "OPEN_TOP"},
    # Robinson: OCR misread 30 → 34
    ("OPEN_TOP",   "34 YD"): {"equipment_size": "30 YD"},
    # Athens: 0 YD roll-off is OCR artifact — no valid size
    ("ROLL_OFF",   "0 YD"):  {"equipment_size": ""},
    # Casella: 4 YD "roll-off" is actually a front load
    ("ROLL_OFF",   "4 YD"):  {"equipment_type": "FRONT_LOAD"},
}


# ── Size parsing ──────────────────────────────────────────────────────────────

def parse_size(size_str: str, equip_type: str):
    """Return (volume: float, uom: str) or (None, None) if unparseable."""
    s = size_str.strip()
    if not s:
        return None, None

    su = s.upper()

    # Determine unit
    if re.search(r'GAL', su):
        uom = "Gallon"
    elif re.search(r'YD|YARD', su):
        uom = "Cubicyard"
    elif equip_type == "CART":
        # Carts without explicit unit are gallons (32, 35, 64, 90, 95, 96 gal)
        uom = "Gallon"
    else:
        uom = "Cubicyard"

    # Extract first numeric token
    nums = re.findall(r'\d+\.?\d*', s)
    if not nums:
        return None, None

    return float(nums[0]), uom


# ── Equipment lookup ──────────────────────────────────────────────────────────

def build_equip_index(equipment_list):
    """
    Returns:
      vol_idx:  (container_type, volume_float, uom) → equipment_name  (volume-based)
      name_idx: (container_type, volume_float) → equipment_name        (name-parsed volume, for vol=0 entries)
    """
    vol_idx = {}
    name_idx = {}

    for e in equipment_list:
        ctype = e["container_type"]
        vol = float(e["container_volume"])
        uom = e["container_uom"]
        name = e["equipment_name"]

        # Volume-based index
        key = (ctype, vol, uom)
        if key not in vol_idx:
            vol_idx[key] = name
        elif "w/" not in name and "w/" in vol_idx[key]:
            vol_idx[key] = name

        # Name-parsed index for vol=0 entries (e.g. "40 Yard Compactor" → 40 yd)
        if vol == 0:
            m = re.match(r'^(\d+\.?\d*)\s*(Yard|Gallon|YD|GAL)', name, re.IGNORECASE)
            if m:
                parsed_vol = float(m.group(1))
                parsed_uom = "Cubicyard" if m.group(2).upper() in ("YARD", "YD") else "Gallon"
                nkey = (ctype, parsed_vol, parsed_uom)
                if nkey not in name_idx:
                    name_idx[nkey] = name

    return vol_idx, name_idx


def lookup_equipment(equip_type: str, equip_size: str, vol_idx: dict, name_idx: dict) -> str:
    container_types = EQUIP_TYPE_MAP.get(equip_type, [])
    if not container_types:
        return ""

    vol, uom = parse_size(equip_size, equip_type)

    for ctype in container_types:
        if vol is None:
            # No size — return generic entry, or the container type name as fallback
            generic_key = (ctype, 0.0, "N/A")
            if generic_key in vol_idx:
                return vol_idx[generic_key]
            # Fallback: use the container_type name itself (e.g. "Open Top")
            return ctype

        # 1. Exact volume match in vol_idx
        key = (ctype, vol, uom)
        if key in vol_idx:
            return vol_idx[key]

        # 2. Cubicyard uom-agnostic fallback in vol_idx
        if uom == "Cubicyard":
            for k, name in vol_idx.items():
                if k[0] == ctype and k[1] == vol:
                    return name

        # 3. Name-parsed index (handles vol=0 entries like "40 Yard Compactor")
        nkey = (ctype, vol, uom)
        if nkey in name_idx:
            return name_idx[nkey]

    return f"UNMAPPED:{equip_type}:{equip_size}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    with open(TARGETS_FILE) as f:
        targets = json.load(f)

    vol_idx, name_idx = build_equip_index(targets["equipment"])

    # Validate material map against target list
    target_material_names = {m["material_name"] for m in targets["materials"]}
    for raw, canonical in MATERIAL_MAP.items():
        if canonical not in target_material_names:
            print(f"[WARN] material '{canonical}' not found in targets", file=sys.stderr)

    # Validate service_desc map against target list
    target_service_descs = {s["service_desc_new"] for s in targets["service_descriptions"]}
    for raw, canonical in CHARGE_CODE_MAP.items():
        if canonical not in target_service_descs:
            print(f"[WARN] service_desc '{canonical}' not found in targets", file=sys.stderr)

    unmapped_equip = set()
    unmapped_material = set()
    unmapped_charge = set()
    total = 0

    with open(INPUT_CSV, newline="", encoding="utf-8") as fin, \
         open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fout:

        reader = csv.DictReader(fin)
        fieldnames = reader.fieldnames + ["equipment_name", "material_name", "service_desc"]
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            total += 1
            et = row["equipment_type"]
            es = row["equipment_size"]

            # Apply normalization overrides before lookup
            override = NORMALIZATION_OVERRIDES.get((et, es))
            if override:
                if "equipment_type" in override:
                    et = override["equipment_type"]
                    row["equipment_type"] = et
                if "equipment_size" in override:
                    es = override["equipment_size"]
                    row["equipment_size"] = es

            mat = row["material"]
            cc = row["charge_code"]

            # Equipment
            en = lookup_equipment(et, es, vol_idx, name_idx)
            if en.startswith("UNMAPPED:"):
                unmapped_equip.add((et, es))
            row["equipment_name"] = en

            # Material
            mn = MATERIAL_MAP.get(mat, "")
            if mat and not mn:
                unmapped_material.add(mat)
            row["material_name"] = mn

            # Charge code
            sd = CHARGE_CODE_MAP.get(cc, "")
            if cc and not sd:
                unmapped_charge.add(cc)
            row["service_desc"] = sd

            writer.writerow(row)

    print(f"Wrote {total} rows → {OUTPUT_CSV}")

    if unmapped_equip:
        print(f"\nUnmapped equipment ({len(unmapped_equip)}):")
        for et, es in sorted(unmapped_equip):
            print(f"  type={et!r} size={es!r}")

    if unmapped_material:
        print(f"\nUnmapped materials ({len(unmapped_material)}):")
        for m in sorted(unmapped_material):
            print(f"  {m!r}")

    if unmapped_charge:
        print(f"\nUnmapped charge codes ({len(unmapped_charge)}):")
        for c in sorted(unmapped_charge):
            print(f"  {c!r}")


if __name__ == "__main__":
    main()
