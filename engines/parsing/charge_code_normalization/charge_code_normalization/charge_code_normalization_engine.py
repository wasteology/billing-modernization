"""Charge code normalization engine.

Maps raw charge descriptions to 155 canonical charge codes from the
Wasteology SKU vocabulary. Vendor-specific normalizers handle unique invoice
formats; generic keyword rules catch everything else.

Pipeline:
  Step 0: Reject fallbacks ("Invoice Total", "Amount Due", garbage OCR)
  Step 1: Strip numeric artifacts (amounts, qtys, WO#, TKT#)
  Step 2: Exact match against CHARGE_CODE_REF → HIGH
  Step 3: Vendor-specific regex normalizer → HIGH
  Step 4: Generic keyword regex rules → MEDIUM
  Step 5: Return None (never guess)
"""

import re
from typing import Optional, List, Tuple, Callable

from .models import NormalizedCharge


# ═══════════════════════════════════════════════════════════════════════════════
# REFERENCE DATA — 155 canonical charge codes → classification
# Source: ops_database/Skew Work draft 3.xlsx (customer_category column)
# ═══════════════════════════════════════════════════════════════════════════════

CHARGE_CODE_REF: dict[str, str] = {
    "Additional Shredding Service": "adverse",
    "Addtl Hand Pick Up Commercial": "adverse",
    "Addtl Recycling Service Pick Up": "adverse",
    "Adjustment Commercial": "one time",
    "Adjustment Industrial": "one time",
    "Bad Debt Write Down": "adverse",
    "Baler Rental": "recurring",
    "Baler Wire": "one time",
    "Biohazardous Service": "recurring",
    "Biohazardous Service by Lb": "recurring",
    "Bulk Item Pick Up By Yard": "one time",
    "Bulk Item Pick Up Commercial": "one time",
    "Bulk Item Pick Up Industrial": "one time",
    "Cardboard Rebate": "rebate",
    "Casters": "recurring",
    "Chemo Container Service": "recurring",
    "Clean Up Industrial": "adverse",
    "Commercial": "recurring",
    "Compactor Installation": "one time",
    "Compactor Monitoring": "recurring",
    "Compactor Removal": "one time",
    "Compactor Rental": "recurring",
    "Compactor/Baler Repair/Service": "one time",
    "Container Exchange": "one time",
    "Container Repair Commercial": "one time",
    "Container Repair Industrial": "one time",
    "Contaminated Disposal Charge": "adverse",
    "Contaminated Load": "adverse",
    "Contaminated Load by Yard": "adverse",
    "Contaminated Load Fee": "adverse",
    "Credit Card Processing Fee": "study",
    "Daily Rental Commercial": "one time",
    "Daily Rental Industrial": "one time",
    "Data Platform Invoice Processing": "recurring",
    "Data Platform Software": "recurring",
    "Delivery Commercial": "one time",
    "Delivery Industrial": "one time",
    "Delivery Mobile Units": "one time",
    "Delivery Portable Toilets": "one time",
    "Demurrage Industrial": "one time",
    "Deodorizer Industrial": "one time",
    "Dig Out Industrial": "one time",
    "Disposal": "demand - weight",
    "Disposal Charge": "demand - weight",
    "Disposal Charge Special Waste": "demand - weight",
    "Diversion Discount": "study",
    "Donation Credit": "recurring",
    "Empty & Return": "demand - haul",
    "Environmental Surcharge": "fuel",
    "Environmental Surcharge Commercial": "fuel",
    "Environmental Surcharge Disposal": "fuel",
    "Environmental Surcharge Industrial": "fuel",
    "Environmental Surcharge Portable Toilets": "fuel",
    "Equipment Purchase": "one time",
    "Equipment Rental": "recurring",
    "Equipment Sales": "one time",
    "EWaste Service": "one time",
    "Executive Console Shredded Paper": "recurring",
    "Extra Pick Up": "adverse",
    "Final Pick Up": "demand - haul",
    "Franchise Fee Commercial": "recurring",
    "Franchise Fee Disposal": "demand - weight",
    "Franchise Fee Industrial": "demand - haul",
    "Front Load Sensor": "recurring",
    "Front Load Sensor Installation": "one time",
    "FUEL SURCHARGE": "fuel",
    "Fuel Surcharge Commercial": "fuel",
    "Fuel Surcharge Disposal": "fuel",
    "Fuel Surcharge Industrial": "fuel",
    "Fuel Surcharge Mobile Units": "fuel",
    "Fuel Surcharge Portable Toilets": "fuel",
    "Grease Rendering Service": "recurring",
    "Grease Trap": "recurring",
    "Grease Trap Service": "recurring",
    "Hand Pick Up Commercial": "recurring",
    "Hand Pick Up industrial": "recurring",
    "Handwash Station": "one time",
    "Hopper": "unknown",
    "Inactivty Fee": "adverse",
    "Industrial": "demand",
    "Landfill - C&D": "study",
    "Landfill - Tires": "study",
    "Landfill - Trash": "study",
    "Landfill Direct - Disposal Charge": "study",
    "Lidded Container": "recurring",
    "Liner": "one time",
    "Liquidated Damages Savings Offset": "adverse",
    "Liquidated Damages Savings Offset Com": "adverse",
    "Local Surcharge Commercial": "Local Surcharges/Fees",
    "Local Surcharge Industrial": "Local Surcharges/Fees",
    "Local Surcharge/Fees Commercial": "Local Surcharges/Fees",
    "Local Surcharge/Fees Industrial": "Local Surcharges/Fees",
    "Local Surcharges/ Fees Industrial": "Local Surcharges/Fees",
    "Local Surcharges/Fees Commercial": "Local Surcharges/Fees",
    "Local Surcharges/Fees Disposal": "Local Surcharges/Fees",
    "Local Surcharges/Fees Industrial": "Local Surcharges/Fees",
    "Local Surcharges/Fees Mobile Units": "Local Surcharges/Fees",
    "Local Surcharges/Fees Portable Toilets": "Local Surcharges/Fees",
    "Lock Bar": "recurring",
    "Lock Bar Installation": "one time",
    "Metal Rebate": "rebate",
    "Miscellaneous": "study",
    "Mobile Compaction": "demand - haul",
    "Monthly Rental Commercial": "recurring",
    "Monthly Rental Industrial": "recurring",
    "Monthly Rental Mobile Units": "recurring",
    "Monthly Rental Portable Toilets": "recurring",
    "Monthly Service Commercial": "recurring",
    "Monthly Service Industrial": "recurring",
    "Monthly Service Portable Toilets": "recurring",
    "Non Hazard Container Service": "study",
    "OCC Rebate": "rebate",
    "On Call Service Commercial": "one time",
    "Onboarding Vendor cost change - Commercial": "study",
    "Onboarding Vendor cost change - Industrial": "study",
    "Over Tonnage Limit Fee": "adverse",
    "Overage": "adverse",
    "Overage by Yard": "adverse",
    "Portable Toilets": "study",
    "Proration Commercial": "one time",
    "Quarterly Solid Waste Surcharge": "Local Surcharges/Fees",
    "Receiver Container Rental": "recurring",
    "Recycling": "recycling",
    "Recycling Offset": "rebate",
    "Recycling Processing Fee": "recycling",
    "Recycling Rebate": "rebate",
    "Recycling Service Material": "recycling",
    "Recycling Service Pick Up": "recycling",
    "Recycling Service Weight": "recycling",
    "Recycling-Offset": "rebate",
    "Relocate Commercial": "one time",
    "Relocate Industrial": "one time",
    "Removal Commercial": "one time",
    "Sales Tax": "Local Surcharges/Fees",
    "Scrap Metal Service": "recycling",
    "Seasonal Service Commercial": "one time",
    "Service Attempt": "adverse",
    "Service Mobile Units": "study",
    "Sharps Disposal Service": "recurring",
    "Shredding Bag Service": "recurring",
    "Shredding Service": "recurring",
    "Supply Purchase": "study",
    "Tax Commercial": "Local Surcharges/Fees",
    "Tax Industrial": "Local Surcharges/Fees",
    "Tax Mobile Units": "Local Surcharges/Fees",
    "Tax Portable Toilets": "Local Surcharges/Fees",
    "Tipping Fee": "demand",
    "Trailer Rental": "recurring",
    "Transportation": "recurring",
    "Transportation Hourly": "recurring",
    "Trip Charge": "adverse",
    "Vacuum Service": "recurring",
    "Vacuum Service Hourly": "recurring",
    "Vendor Cost Increase - Commercial": "cost increase",
    "Vendor Cost Increase - Industrial": "cost increase",
    "Vendor Late Fees": "late fee",
    "Wasteology Franchise Management Fee": "management fee",
    "Wasteology Management Fee": "management fee",
    "Weight Adjustment": "study",
    "WG Admin Fee": "late fee",
}

# Build case-insensitive lookup
_CHARGE_CODE_LOOKUP: dict[str, tuple[str, str]] = {
    k.lower(): (k, v) for k, v in CHARGE_CODE_REF.items()
}


# ═══════════════════════════════════════════════════════════════════════════════
# REJECT PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

_FALLBACK_PATTERNS: list[re.Pattern] = [
    re.compile(r'^\s*(?:invoice\s+)?total(?:\s+(?:invoice|charges|new\s+charges))?\s*$', re.I),
    re.compile(r'^\s*total\s+(?:current\s+)?charges\s*\$?\s*$', re.I),
    re.compile(r'^\s*total\s+new\s+charges\s*$', re.I),
    re.compile(r'^\s*(?:amount|balance)\s+due\s*$', re.I),
    re.compile(r'^\s*please\s+pay\s*$', re.I),
    re.compile(r'^\s*site\s+total\s*$', re.I),
    re.compile(r'^\s*surcharges?\s+total\s*$', re.I),
    re.compile(r'^\s*current\s+(?:invoice\s+)?charges\s*$', re.I),
    re.compile(r'^\s*late\s+fees?\s*:\s*a\s+fee\s+of\b', re.I),
    re.compile(r'^\s*late\s*$', re.I),
]

# Words that indicate meaningful content (not garbage OCR)
_MEANINGFUL_WORDS = frozenset([
    'service', 'charge', 'surcharge', 'fee', 'tax', 'disposal', 'delivery',
    'rental', 'container', 'trash', 'waste', 'recycle', 'recycling', 'fuel',
    'energy', 'environ', 'location', 'hauling', 'front', 'load', 'roll',
    'compactor', 'bin', 'yard', 'pickup', 'late', 'credit', 'adjustment',
    'month', 'switch', 'lease', 'maintenance', 'processing', 'admin',
    'dump', 'organics', 'wood', 'cardboard', 'metal', 'frch', 'contamina',
])


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _strip_numeric_artifacts(desc: str) -> str:
    """Remove amounts, WO#, TKT#, percentages while preserving structural data."""
    s = desc.replace('\n', ' ').replace('\r', ' ')
    # Remove WO# and TKT# references
    s = re.sub(r'\b(?:WO|TKT)[#:]\s*\d+', '', s, flags=re.I)
    # Remove dollar amounts: $123.45 or $ 1,234.56
    s = re.sub(r'\$\s*[\d,]+\.?\d*', '', s)
    # Remove percentages: 12.00%
    s = re.sub(r'\d+\.?\d*\s*%', '', s)
    # Remove "per month"
    s = re.sub(r'\bper\s+month\b', '', s, flags=re.I)
    # Remove leading bare number (like "31 " from "31\nMARYLAND...")
    s = re.sub(r'^\d+\s+', '', s)
    # Remove decimal amounts (1.00, 295.000, -329.33) but not bare integers
    s = re.sub(r'-?[\d,]+\.\d{2,3}', '', s)
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    # Remove leading/trailing punctuation artifacts
    s = re.sub(r'^[\s;:.,\-]+|[\s;:.,\-]+$', '', s).strip()
    return s


def is_fallback(desc: str) -> bool:
    """Return True if description is a known non-useful summary label."""
    cleaned = desc.replace('\n', ' ').strip()
    for pat in _FALLBACK_PATTERNS:
        if pat.match(cleaned):
            return True
    return False


def _is_garbage_ocr(desc: str) -> bool:
    """Return True if description is entirely garbled OCR with no meaningful content."""
    lower = desc.lower()
    for word in _MEANINGFUL_WORDS:
        if word in lower:
            return False
    # No meaningful words found — check if there's any real alphabetic content
    alpha = re.sub(r'[^a-zA-Z]', '', desc)
    return len(alpha) < 4


# ═══════════════════════════════════════════════════════════════════════════════
# VENDOR NORMALIZERS
# Each returns (charge_code, classification) or None to fall through.
# ═══════════════════════════════════════════════════════════════════════════════

def _normalize_waste_management(desc: str) -> Optional[Tuple[str, str]]:
    """WM invoices: NG DETAIL format + legacy Location Charges/FRCH."""
    d = desc.upper()

    # ── NG DETAIL inline format ──
    # "Pickup [Size] [Material] DMP|TOT [Frequency]"
    if re.match(r'PICKUP\s+\d+', d):
        if re.search(r'RECYCL|SINGLE\s*STREAM|CO-?MINGLE|OCC|CARDBOARD', d):
            return ('Recycling Service Pick Up', 'recycling')
        if re.search(r'ORGANIC|FOOD\s*WASTE|GREEN\s*WASTE', d):
            return ('Monthly Service Commercial', 'recurring')
        return ('Monthly Service Commercial', 'recurring')

    # "Haul [Size] [Material] OT" (roll-off haul)
    if re.match(r'HAUL\s+\d+', d):
        return ('Empty & Return', 'demand - haul')

    # "Disposal [Size] [Material] OT"
    if re.match(r'DISPOSAL\s+\d+', d):
        if re.search(r'RECYCL|OCC|CARDBOARD|SINGLE\s*STREAM', d):
            return ('Disposal Charge', 'demand - weight')
        return ('Disposal', 'demand - weight')

    # "Container Service Charge [Size] [Material]"
    if re.match(r'CONTAINER\s+SERVICE\s+CHARGE', d):
        if re.search(r'RECYCL|SINGLE\s*STREAM|OCC', d):
            return ('Monthly Rental Industrial', 'recurring')
        return ('Monthly Rental Industrial', 'recurring')

    # "Container Usage Charge [Size] [Material]"
    if re.match(r'CONTAINER\s+USAGE\s+CHARGE', d):
        return ('Equipment Rental', 'recurring')

    # "Landfill Fee|Landfill [Size] [Material]"
    if re.match(r'LANDFILL', d):
        return ('Landfill - Trash', 'study')

    # "Government Franchise Reg Fee" / "GOVT FRAN REG FEE"
    if re.search(r'GOVERNMENT\s*FRANCHISE|GOVT\s*FRAN', d):
        return ('Franchise Fee Commercial', 'recurring')

    # "Delivery [Size] [Material] OT"
    if re.match(r'DELIVERY\s+\d+', d):
        return ('Delivery Industrial', 'one time')

    # "Removal [Size] [Material]"
    if re.match(r'REMOVAL\s+\d+', d):
        return ('Removal Commercial', 'one time')

    # "Dry Run [Size] [Material]"
    if re.match(r'DRY\s*RUN', d):
        return ('Empty & Return', 'demand - haul')

    # "Energy Surcharge"
    if re.search(r'ENERGY\s*SURCHARGE', d):
        return ('Fuel Surcharge Commercial', 'fuel')

    # "Fuel Surcharge"
    if re.search(r'FUEL\s*SURCHARGE', d):
        return ('Fuel Surcharge Commercial', 'fuel')

    # City/Municipal surcharges: "Melbourne City Of Surcharge", "City Fee", "Zero Waste San Diego"
    if re.search(r'CITY\s+(?:OF\s+)?SURCHARGE|CITY\s+FEE|ZERO\s+WASTE|MAN\s+BCH|RECOV(?:ERY)?\s+COST', d):
        return ('Local Surcharges/Fees Commercial', 'Local Surcharges/Fees')

    # "Recyclable Material Offset" (recycling credit)
    if re.search(r'RECYCL\w*\s*MATERIAL\s*OFFSET', d):
        return ('Recycling', 'recycling')

    # "Inactivity Charge Per Diem"
    if re.search(r'INACTIV', d):
        return ('Demurrage Industrial', 'one time')

    # "Contamination Incident#"
    if re.search(r'CONTAMIN', d):
        return ('Contaminated Load Fee', 'adverse')

    # "Casters"
    if re.match(r'CASTERS?\b', d):
        return ('Casters', 'recurring')

    # "Lock" / "Lock Service"
    if re.match(r'LOCK\b', d):
        return ('Lock Bar', 'recurring')

    # "Administrative Charge"
    if re.search(r'ADMIN\w*\s*CHARGE', d):
        return ('WG Admin Fee', 'late fee')

    # "Excess Yards" / "Excess" charges (overage)
    if re.match(r'EXCESS', d):
        return ('Overage', 'adverse')

    # "Push Out/Pull Out" / "Push Out" / "Pull Out"
    if re.search(r'PUSH\s*OUT|PULL\s*OUT', d):
        return ('Trip Charge', 'adverse')

    # "Minimum tonnage charge"
    if re.search(r'MINIMUM\s*TONNAGE', d):
        return ('Disposal Charge', 'demand - weight')

    # ── Legacy patterns ──
    # FRONTLOAD service line: "FRONTLOAD 8 YD- SOLID WASTE SERVICE 6"
    if re.search(r'FRONTLOAD.*(?:SOLID\s*WASTE|TRASH|REFUSE)\s*SERVICE', d):
        return ('Monthly Service Commercial', 'recurring')

    # Location Charges (covers garbled OCR + clean location names)
    if 'LOCATION CHARGES' in d:
        return ('Monthly Service Commercial', 'recurring')

    # FRCH prefix (WM front-load charge)
    if d.startswith('FRCH'):
        return ('Monthly Service Commercial', 'recurring')

    return None


def _normalize_republic(desc: str) -> Optional[Tuple[str, str]]:
    """Republic: 'N Waste/Recycle Container SIZE - SCHEDULE' structured format."""

    # Container/Compactor service line
    m = re.match(
        r'\d+\s+(waste|recycle)\s+(container|compactor)\s+(\d+)\s*-\s*(.*)',
        desc, re.I
    )
    if m:
        material = m.group(1).lower()
        equip = m.group(2).lower()
        size = int(m.group(3))
        schedule = m.group(4).strip().lower()

        if material == 'recycle':
            if size >= 20 or equip == 'compactor':
                return ('Recycling', 'recycling')
            return ('Recycling Service Pick Up', 'recycling')

        # Waste
        if size >= 20 or equip == 'compactor':
            return ('Monthly Service Industrial', 'recurring')
        return ('Monthly Service Commercial', 'recurring')

    # Front Load: "1 Front Load 4 Yd - 1 Lift Per Week"
    if re.match(r'\d+\s+front\s+load\s+\d+\s*yd', desc, re.I):
        return ('Monthly Service Commercial', 'recurring')

    # Pickup Service
    if re.match(r'\s*pickup\s+service\s*$', desc, re.I):
        return ('Monthly Service Commercial', 'recurring')

    # Rental (standalone)
    if re.match(r'\s*rental\s*$', desc, re.I):
        return ('Monthly Rental Industrial', 'recurring')

    # Late Fee
    if re.match(r'\s*late\s+fee\s*$', desc, re.I):
        return ('Vendor Late Fees', 'late fee')

    # Taxes — most specific first
    if re.search(r'solid\s+waste\s+management\s+tax', desc, re.I):
        return ('Tax Commercial', 'Local Surcharges/Fees')
    if re.search(r'solid\s+waste\s+management\s+fee', desc, re.I):
        return ('Local Surcharges/Fees Commercial', 'Local Surcharges/Fees')
    if re.search(r'(?:county|state|city|mta)\s+sales\s+tax', desc, re.I):
        return ('Sales Tax', 'Local Surcharges/Fees')

    return None


def _normalize_athens(desc: str) -> Optional[Tuple[str, str]]:
    """Athens: 'NNyd-MATERIAL R/O-DUMP', 'NNyd MATERIAL BIN # P/U: N'."""
    d = desc.upper()

    # Roll-off dump: "40YD-TRASH R/O-DUMP 1.00"
    if re.search(r'\d+YD.*R/O.*DUMP', d):
        return ('Empty & Return', 'demand - haul')

    # Disposal fee with ticket: "DISPOSAL FEE-PROC TRAS TKT#..."
    if re.search(r'DISPOSAL\s+FEE', d):
        return ('Disposal', 'demand - weight')

    # Bin service: "2YD ORGANICS BIN # P/U: 3"
    if re.search(r'\d+YD.*(?:RECY|RECYCL)', d):
        return ('Recycling Service Pick Up', 'recycling')
    if re.search(r'\d+YD.*BIN', d):
        return ('Monthly Service Commercial', 'recurring')

    # Late fee
    if 'LATE FEE' in d:
        return ('Vendor Late Fees', 'late fee')

    return None


def _normalize_cockeys(desc: str) -> Optional[Tuple[str, str]]:
    """Cockey's: 'Weekly 04YD FRONT LOAD SERVICE', 'FUEL SURCHARGE'."""
    d = desc.upper()

    # Recycle service: "Every 2 Weeks 04YD RECYCLE SERVICE"
    if re.search(r'RECYCLE\s+SERVICE', d):
        return ('Recycling Service Pick Up', 'recycling')

    # Front load service: "Weekly 04YD FRONT LOAD SERVICE"
    if re.search(r'FRONT\s+LOAD\s+SERVICE', d):
        return ('Monthly Service Commercial', 'recurring')

    # Environmental regulatory fee
    if re.search(r'ENVIRONMENTAL\s+REGULATORY\s+FEE', d):
        return ('Environmental Surcharge Commercial', 'fuel')

    # Fuel surcharge
    if re.search(r'FUEL\s+SURCHARGE', d):
        return ('Fuel Surcharge Commercial', 'fuel')

    # Sales tax
    if re.search(r'SALES\s+TAX|STATE\s+.*TAX', d):
        return ('Sales Tax', 'Local Surcharges/Fees')

    return None


def _normalize_burgmeiers(desc: str) -> Optional[Tuple[str, str]]:
    """Burgmeier's: 'NNYD OPEN TOP SWITCH', 'NNYD DISPOSAL N.NN', 'LEASE FEE'."""
    d = desc.upper()

    # Switch (haul) operations: "20YD OPEN TOP SWITCH", "30YD COMP SWITCH"
    if re.search(r'\d+YD\s+(?:OPEN\s+TOP|COMP)\s+SWITCH', d):
        return ('Empty & Return', 'demand - haul')

    # Disposal by tonnage: "20YD DISPOSAL 2.97 69.010"
    if re.search(r'\d+YD\s+DISPOSAL', d):
        return ('Disposal', 'demand - weight')

    # Lease fee: "LEASE FEE"
    if 'LEASE FEE' in d:
        return ('Monthly Rental Industrial', 'recurring')

    return None


def _normalize_vanderlind(desc: str) -> Optional[Tuple[str, str]]:
    """Vanderlind: 'NNYD DISPOSAL - MATERIAL TKT# NNNN'."""
    d = desc.upper()

    if re.search(r'\d+YD\s+DISPOSAL', d):
        return ('Disposal', 'demand - weight')

    return None


def _normalize_universal_waste(desc: str) -> Optional[Tuple[str, str]]:
    """Universal Waste: 'TRASH SERVICE', 'CONTAINER SERVICE', 'PROCESSING FEE'."""
    d = desc.upper()

    # Delivery: "8YD FL TRASH DELIVERY"
    if re.search(r'DELIVERY', d):
        return ('Delivery Commercial', 'one time')

    # Trash/waste/yard waste service
    if re.search(r'(?:TRASH|WASTE|YARD\s+WASTE)\s+SERVICE', d):
        return ('Monthly Service Commercial', 'recurring')

    # Container service (rental)
    if re.search(r'CONTAINER\s+SERVICE', d):
        return ('Monthly Rental Commercial', 'recurring')

    # Processing fee
    if re.search(r'PROCESSING\s+FEE', d):
        return ('Recycling Processing Fee', 'recycling')

    return None


def _normalize_sbc_waste(desc: str) -> Optional[Tuple[str, str]]:
    """SBC Waste: 'N Yard Front Load Trash/Recycle Service QTY $ PRICE per month'."""
    d = desc.upper()

    # Recycle service
    if re.search(r'FRONT\s+LOAD\s+RECYCLE\s+SERVICE', d):
        return ('Recycling Service Pick Up', 'recycling')

    # Trash service
    if re.search(r'FRONT\s+LOAD\s+TRASH\s+SERVICE', d):
        return ('Monthly Service Commercial', 'recurring')

    # Generic "Yard Front Load" (any material)
    if re.search(r'YARD\s+FRONT\s+LOAD', d):
        return ('Monthly Service Commercial', 'recurring')

    return None


def _normalize_mdi(desc: str) -> Optional[Tuple[str, str]]:
    """MDI (Mark Dunning Industries): waste-to-energy disposal tickets."""
    d = desc.upper()

    # Energy disposal: "ENERGY RZ-268137 7.33 TN"
    if re.search(r'ENERGY\s+(?:RZ|LA)[\s\-]', d):
        return ('Disposal', 'demand - weight')
    if re.search(r'ENERGY\s+\d', d):
        return ('Disposal', 'demand - weight')

    return None


def _normalize_kmg(desc: str) -> Optional[Tuple[str, str]]:
    """KMG: 'DELIVERY CHARGE - BIN/ROLL OFF - WO:N', 'DISPOSAL CHARGE'."""
    d = desc.upper()

    # Delivery charges
    if re.search(r'DELIVERY\s+CHARGE.*ROLL\s*OFF', d):
        return ('Delivery Industrial', 'one time')
    if re.search(r'DELIVERY\s+CHARGE.*BIN', d):
        return ('Delivery Commercial', 'one time')
    if re.search(r'DELIVERY\s+CHARGE', d):
        return ('Delivery Commercial', 'one time')

    # Disposal charge
    if re.search(r'DISPOSAL\s+CHARGE', d):
        return ('Disposal Charge', 'demand - weight')

    return None


def _normalize_edco(desc: str) -> Optional[Tuple[str, str]]:
    """EDCO: 'LOCATION Location Charges'."""
    d = desc.upper()

    if 'LOCATION CHARGES' in d:
        return ('Monthly Service Commercial', 'recurring')

    return None


def _normalize_waste_connections(desc: str) -> Optional[Tuple[str, str]]:
    """Waste Connections: 'Disposal N', 'Rental Fees', 'Fuel & Material Surcharge'."""
    d = desc.upper()

    if re.search(r'^DISPOSAL\b', d):
        return ('Disposal', 'demand - weight')

    if re.search(r'RENTAL\s+FEE', d):
        return ('Monthly Rental Industrial', 'recurring')

    if re.search(r'FUEL\s*&\s*MATERIAL\s+SURCHARGE', d):
        return ('Fuel Surcharge Industrial', 'fuel')

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# GENERIC KEYWORD RULES — ordered most-specific to least-specific
# (regex_pattern, charge_code, classification)
# ═══════════════════════════════════════════════════════════════════════════════

_GENERIC_RULES: list[tuple[re.Pattern, str, str]] = [
    # ── Fuel / Environmental surcharges ──────────────────────────────────
    (re.compile(r'fuel\s*&\s*material\s+surcharge', re.I),
     'Fuel Surcharge Commercial', 'fuel'),
    (re.compile(r'fuel\s+surcharge', re.I),
     'Fuel Surcharge Commercial', 'fuel'),
    (re.compile(r'energy\s*&?\s*environmental\s*fee', re.I),
     'Environmental Surcharge Commercial', 'fuel'),
    (re.compile(r'resource\s+solutions\s+energy', re.I),
     'Environmental Surcharge Commercial', 'fuel'),
    (re.compile(r'environmental\s+(?:regulatory\s+)?(?:fee|surcharge)', re.I),
     'Environmental Surcharge Commercial', 'fuel'),
    (re.compile(r'^environmental\s+fee', re.I),
     'Environmental Surcharge Commercial', 'fuel'),

    # ── Taxes ────────────────────────────────────────────────────────────
    (re.compile(r'solid\s+waste\s+management\s+tax', re.I),
     'Tax Commercial', 'Local Surcharges/Fees'),
    (re.compile(r'solid\s+waste\s+management\s+fee', re.I),
     'Local Surcharges/Fees Commercial', 'Local Surcharges/Fees'),
    (re.compile(r'quarterly\s+solid\s+waste\s+surcharge', re.I),
     'Quarterly Solid Waste Surcharge', 'Local Surcharges/Fees'),
    (re.compile(r'(?:state|county|city|mta)\s+sales\s+tax', re.I),
     'Sales Tax', 'Local Surcharges/Fees'),
    (re.compile(r'sales\s+tax', re.I),
     'Sales Tax', 'Local Surcharges/Fees'),
    (re.compile(r'franchise\s+fee', re.I),
     'Franchise Fee Commercial', 'recurring'),

    # ── Late fees ────────────────────────────────────────────────────────
    (re.compile(r'late\s+fee', re.I),
     'Vendor Late Fees', 'late fee'),

    # ── Contamination ────────────────────────────────────────────────────
    (re.compile(r'contaminat', re.I),
     'Contaminated Load', 'adverse'),

    # ── Extra / Trip / Overage ───────────────────────────────────────────
    (re.compile(r'extra\s+pick\s*up', re.I),
     'Extra Pick Up', 'adverse'),
    (re.compile(r'trip\s+charge', re.I),
     'Trip Charge', 'adverse'),
    (re.compile(r'overage', re.I),
     'Overage', 'adverse'),

    # ── Delivery ─────────────────────────────────────────────────────────
    (re.compile(r'delivery\s+charge.*roll\s*off', re.I),
     'Delivery Industrial', 'one time'),
    (re.compile(r'delivery\s+charge.*bin', re.I),
     'Delivery Commercial', 'one time'),
    (re.compile(r'delivery', re.I),
     'Delivery Commercial', 'one time'),

    # ── Disposal ─────────────────────────────────────────────────────────
    (re.compile(r'disposal\s+charge\s+special\s+waste', re.I),
     'Disposal Charge Special Waste', 'demand - weight'),
    (re.compile(r'disposal\s+(?:charge|fee)', re.I),
     'Disposal Charge', 'demand - weight'),
    (re.compile(r'\bdisposal\b', re.I),
     'Disposal', 'demand - weight'),
    (re.compile(r'tipping\s+fee', re.I),
     'Tipping Fee', 'demand'),

    # ── Haul / Switch ────────────────────────────────────────────────────
    (re.compile(r'empty\s*&?\s*return', re.I),
     'Empty & Return', 'demand - haul'),
    (re.compile(r'\bswitch\b', re.I),
     'Empty & Return', 'demand - haul'),
    (re.compile(r'final\s+pick\s*up', re.I),
     'Final Pick Up', 'demand - haul'),

    # ── Rental ───────────────────────────────────────────────────────────
    (re.compile(r'container\s+(?:service|rental)', re.I),
     'Monthly Rental Commercial', 'recurring'),
    (re.compile(r'rolloff\s+maintenance', re.I),
     'Monthly Rental Industrial', 'recurring'),
    (re.compile(r'lease\s+fee', re.I),
     'Monthly Rental Industrial', 'recurring'),
    (re.compile(r'rental\s+fee', re.I),
     'Monthly Rental Industrial', 'recurring'),
    (re.compile(r'\brental\b', re.I),
     'Monthly Rental Industrial', 'recurring'),

    # ── Processing ───────────────────────────────────────────────────────
    (re.compile(r'processing\s+fee', re.I),
     'Recycling Processing Fee', 'recycling'),

    # ── Recycling service ────────────────────────────────────────────────
    (re.compile(r'recycl(?:e|ing)\s+(?:service|pick\s*up)', re.I),
     'Recycling Service Pick Up', 'recycling'),
    (re.compile(r'recycle\s+(?:container|compactor)', re.I),
     'Recycling Service Pick Up', 'recycling'),
    (re.compile(r'\brecycl', re.I),
     'Recycling', 'recycling'),

    # ── Service lines ────────────────────────────────────────────────────
    (re.compile(r'front\s*load\s+(?:service|trash|recycle)', re.I),
     'Monthly Service Commercial', 'recurring'),
    (re.compile(r'(?:trash|waste|solid\s+waste|refuse)\s+service', re.I),
     'Monthly Service Commercial', 'recurring'),
    (re.compile(r'yard\s+waste\s+service', re.I),
     'Monthly Service Commercial', 'recurring'),
    (re.compile(r'organics?\s+(?:bin|service)', re.I),
     'Monthly Service Commercial', 'recurring'),
    (re.compile(r'pickup\s+service', re.I),
     'Monthly Service Commercial', 'recurring'),
    (re.compile(r'on\s+call\s+service', re.I),
     'On Call Service Commercial', 'one time'),
    (re.compile(r'compactor\s+(?:service|rental)', re.I),
     'Compactor Rental', 'recurring'),

    # ── Container exchange / repair ──────────────────────────────────────
    (re.compile(r'container\s+exchange', re.I),
     'Container Exchange', 'one time'),
    (re.compile(r'container\s+repair', re.I),
     'Container Repair Commercial', 'one time'),

    # ── Energy (waste-to-energy) — after environmental surcharge rules ───
    (re.compile(r'\benergy\b', re.I),
     'Disposal', 'demand - weight'),

    # ── Location Charges (WM / EDCO pattern) ────────────────────────────
    (re.compile(r'location\s+charges', re.I),
     'Monthly Service Commercial', 'recurring'),

    # ── Dump & Return / haul patterns ──────────────────────────────────
    (re.compile(r'dump\s*&?\s*return', re.I),
     'Empty & Return', 'demand - haul'),
    (re.compile(r'\bhaul\s*rate\b', re.I),
     'Empty & Return', 'demand - haul'),
    (re.compile(r'compactor\s+haul\s*rate', re.I),
     'Empty & Return', 'demand - haul'),
    (re.compile(r'\bhaul\b.*\byard', re.I),
     'Empty & Return', 'demand - haul'),
    (re.compile(r'\bdry\s+run\b', re.I),
     'Empty & Return', 'demand - haul'),

    # ── Recovery / compliance / economic fees ──────────────────────────
    (re.compile(r'\brecovery\s*fee\b', re.I),
     'Environmental Surcharge Commercial', 'fuel'),
    (re.compile(r'\benvironmental\s+compliance\b', re.I),
     'Environmental Surcharge Commercial', 'fuel'),
    (re.compile(r'\beconomic\s+adjustment\s+charge\b', re.I),
     'Environmental Surcharge Commercial', 'fuel'),

    # ── Permit / permanent / rental fees ───────────────────────────────
    (re.compile(r'\d+\s*YD\s+ROL\s+PERM\s+FEE', re.I),
     'Monthly Rental Industrial', 'recurring'),
    (re.compile(r'PERM(?:ANENT)?\s+FEE', re.I),
     'Monthly Rental Industrial', 'recurring'),

    # ── Front load / service by size & frequency ───────────────────────
    (re.compile(r'FL[- ]Comm[- ](?:Trash|Recycle)', re.I),
     'Monthly Service Commercial', 'recurring'),
    (re.compile(r'\d+\s*(?:YD|YARD)\s+FL\s', re.I),
     'Monthly Service Commercial', 'recurring'),
    (re.compile(r'\d+\s*(?:YD|YARD)\s*(?:FL|FRONT)', re.I),
     'Monthly Service Commercial', 'recurring'),
    (re.compile(r'(?:MSW|TRASH)\s+\d+Y\s+\d+[xX]W\s+TRASH\s+REMOVAL', re.I),
     'Monthly Service Commercial', 'recurring'),
    (re.compile(r'Monthly\s+Svc:\s+\d+-?\d+\s*yd', re.I),
     'Monthly Service Commercial', 'recurring'),
    (re.compile(r'Scheduled\s+Service', re.I),
     'Monthly Service Commercial', 'recurring'),
    (re.compile(r'\d+x/Week.*FRONT\s+LOAD', re.I),
     'Monthly Service Commercial', 'recurring'),

    # ── Gallon / toter services ────────────────────────────────────────
    (re.compile(r'\d+\s*G(?:AL|ALLON)?\s+(?:Organic|Food|Trash|Recycl|MSW)', re.I),
     'Monthly Service Commercial', 'recurring'),
    (re.compile(r'\d+\s*Gallon\s+Toter', re.I),
     'Monthly Service Commercial', 'recurring'),

    # ── Lock service ───────────────────────────────────────────────────
    (re.compile(r'\block\b(?:\s+(?:per\s+unit|service|bar))?\s*$', re.I),
     'Lock Bar', 'recurring'),

    # ── Finance / late ─────────────────────────────────────────────────
    (re.compile(r'\bfinance\s+charge\b', re.I),
     'Vendor Late Fees', 'late fee'),

    # ── Fuel fee (generic) ─────────────────────────────────────────────
    (re.compile(r'\bfuel\s+fee\b', re.I),
     'Fuel Surcharge Commercial', 'fuel'),

    # ── Usage days (per-diem rental) ───────────────────────────────────
    (re.compile(r'\busage\s*days?\b', re.I),
     'Daily Rental Industrial', 'one time'),

    # ── Administrative / miscellaneous ───────────────────────────────────
    (re.compile(r'\badmin(?:istrative)?\b', re.I),
     'Miscellaneous', 'study'),

    # ── Generic surcharge catch-all ──────────────────────────────────────
    (re.compile(r'\bsurcharge\b', re.I),
     'Environmental Surcharge Commercial', 'fuel'),
]


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCH REGISTRY — vendor substring → normalizer function
# ═══════════════════════════════════════════════════════════════════════════════

_VendorNormalizer = Callable[[str], Optional[Tuple[str, str]]]

VENDOR_NORMALIZERS: dict[str, _VendorNormalizer] = {
    'waste management': _normalize_waste_management,
    'republic services': _normalize_republic,
    'republic': _normalize_republic,
    'athens services': _normalize_athens,
    'athens': _normalize_athens,
    "cockey's": _normalize_cockeys,
    'cockey': _normalize_cockeys,
    "burgmeier": _normalize_burgmeiers,
    'vanderlind': _normalize_vanderlind,
    'universal waste': _normalize_universal_waste,
    'sbc waste': _normalize_sbc_waste,
    'mark dunning': _normalize_mdi,
    'mdi': _normalize_mdi,
    'kmg hauling': _normalize_kmg,
    'kmg': _normalize_kmg,
    'edco': _normalize_edco,
    'waste connections': _normalize_waste_connections,
}

# Sorted longest-first for correct substring matching
_VENDOR_KEYS_SORTED = sorted(VENDOR_NORMALIZERS.keys(), key=len, reverse=True)


def _find_normalizer(vendor: str) -> Optional[_VendorNormalizer]:
    """Find normalizer for vendor using longest-match-first substring matching."""
    if not vendor:
        return None
    vendor_lower = vendor.lower().strip()
    for key in _VENDOR_KEYS_SORTED:
        if key in vendor_lower:
            return VENDOR_NORMALIZERS[key]
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def normalize_charge(vendor: str, description: str) -> Optional[NormalizedCharge]:
    """Normalize a single charge description to a canonical charge code.

    Args:
        vendor: Normalized vendor name (e.g., "Republic Services")
        description: Single charge description (not semicolon-delimited)

    Returns:
        NormalizedCharge or None if rejected/unmatched
    """
    if not description or str(description) == 'nan':
        return None

    desc = description.strip()
    if not desc or len(desc) < 2:
        return None

    # Step 0: Reject known fallbacks
    if is_fallback(desc):
        return None

    # Step 1: Clean for matching
    cleaned = _strip_numeric_artifacts(desc)
    if not cleaned or len(cleaned) < 2:
        return None

    # Step 0b: Garbage OCR check (after cleaning)
    if _is_garbage_ocr(cleaned):
        return None

    # Step 2: Exact match against CHARGE_CODE_REF (case-insensitive)
    lookup = cleaned.lower()
    if lookup in _CHARGE_CODE_LOOKUP:
        ref_code, ref_class = _CHARGE_CODE_LOOKUP[lookup]
        return NormalizedCharge(
            charge_code=ref_code,
            classification=ref_class,
            raw_description=description,
            confidence='HIGH',
            match_type='exact',
        )

    # Step 3: Vendor-specific normalizer
    normalizer = _find_normalizer(vendor or '')
    if normalizer:
        result = normalizer(cleaned)
        if result:
            return NormalizedCharge(
                charge_code=result[0],
                classification=result[1],
                raw_description=description,
                confidence='HIGH',
                match_type='vendor_specific',
            )

    # Step 4: Generic keyword rules
    for pattern, charge_code, classification in _GENERIC_RULES:
        if pattern.search(cleaned):
            return NormalizedCharge(
                charge_code=charge_code,
                classification=classification,
                raw_description=description,
                confidence='MEDIUM',
                match_type='generic',
            )

    # Step 5: Return None (never guess)
    return None


def normalize_charges(vendor: str, descriptions: str) -> List[NormalizedCharge]:
    """Normalize semicolon-delimited charge descriptions.

    Args:
        vendor: Normalized vendor name
        descriptions: Semicolon-delimited charge descriptions from dimensional_table

    Returns:
        List of NormalizedCharge (empty list if all rejected/unmatched)
    """
    if not descriptions or str(descriptions) == 'nan':
        return []

    results = []
    for item in descriptions.split(';'):
        item = item.strip()
        if not item or len(item) < 3:
            continue
        result = normalize_charge(vendor, item)
        if result:
            results.append(result)
    return results


def get_configured_vendors() -> List[str]:
    """Return sorted list of vendor match keys in the dispatch registry."""
    return sorted(VENDOR_NORMALIZERS.keys())


def get_vendor_count() -> int:
    """Return number of unique vendor normalizer functions."""
    return len(set(VENDOR_NORMALIZERS.values()))
