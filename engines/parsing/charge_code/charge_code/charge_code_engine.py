"""
Charge Code Extraction Engine
Extracts structured charge line items from invoice OCR text by vendor.

Each vendor has a unique invoice format. No generic patterns.
Returns empty list (never guesses) when vendor is unconfigured.
"""

import re
from typing import List, Optional, Callable

from .models import ChargeItem


# =============================================================================
# HELPERS
# =============================================================================

def _normalize_ocr_text(text: str) -> str:
    """Convert literal \\n to actual newlines. Critical for multiline patterns."""
    if not text or str(text) == 'nan':
        return ''
    return text.replace('\\n', '\n')


def _clean_amount(amount_str: str) -> Optional[float]:
    """Convert amount string to float, handling $, commas, negatives."""
    if not amount_str:
        return None
    # Handle European-style decimal comma: "241,50" → "241.50" (exactly 2 digits after comma, no dot)
    if re.match(r'^-?\$?\d+,\d{2}$', amount_str.strip()):
        amount_str = amount_str.replace(',', '.')
    cleaned = re.sub(r'[$,\s]', '', amount_str)
    if cleaned.endswith('-') or cleaned.startswith('('):
        cleaned = '-' + cleaned.replace('-', '').replace('(', '').replace(')', '')
    try:
        val = float(cleaned)
        return val if abs(val) < 1_000_000 else None
    except ValueError:
        return None


def _clean_qty(qty_str: str) -> Optional[float]:
    """Convert quantity string to float."""
    if not qty_str:
        return None
    cleaned = re.sub(r'[,\s]', '', qty_str)
    try:
        return float(cleaned)
    except ValueError:
        return None


# =============================================================================
# WASTE MANAGEMENT
# =============================================================================

def _extract_waste_management(text: str) -> List[ChargeItem]:
    items = []

    # WIN Waste subsidiary
    if 'WIN Waste' in text or 'WIN WASTE' in text:
        win_pat = re.compile(
            r'(?P<desc>Roll-?Off\s+[\w\s&]+|MSW|Haul|Disposal|Delivery)\s*'
            r'(?:W/O\s*#?:?\s*\d+)?\s*\n?(?:MSW|TRASH|RECYC\w*)?\s*\n?'
            r'\$(?P<rate>[\d,]+\.?\d*)\s*\n?(?P<qty>[\d.]+)\s*\n?'
            r'\$(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
        for m in win_pat.finditer(text):
            items.append(ChargeItem(
                charge_description=m.group('desc').strip(),
                qty=_clean_qty(m.group('qty')),
                amount=_clean_amount(m.group('amount')),
                unit_price=_clean_amount(m.group('rate')),
                raw_text=m.group(0)))
        if items:
            return items

    # TrashBilling subsidiary
    if 'trashbilling' in text.lower():
        tb_pat = re.compile(
            r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
            r'(?P<desc>\d+\s*YD\s+[\d/]+\s*/?\s*(?:WEEK|WK|MONTH))\s+'
            r'(?:\d{1,2}/\d{1,2}\s*[-]\s*\d{1,2}/\d{1,2})\s*\n?'
            r'\$(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
        for m in tb_pat.finditer(text):
            items.append(ChargeItem(
                charge_description=m.group('desc').strip(),
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
        if items:
            return items

    # NG WM inline format: DATE [AUTH#] MATERIAL [garble] QTY DESC PRICE TAX AMOUNT
    # (all on one line — NG invoices have description BETWEEN qty and trailing numbers)
    ng_wm_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+'
        r'(?:[A-Z]{0,4}\d{5,}\s+)?'               # optional AUTH # (P0346933, SCN10333)
        r'(?:Trash|Cardboard|Recycl\w*|MSW|OCC|Organics?|'
        r'Single|Food|Green\w*|Metal|Mixed|Wood|'
        r'Construc\w*|Co-?\w*)\s+'                # material
        r'(?:[^\d\s]\S*\s+)?'                     # optional OCR garble (—-, etc.)
        r'(?P<qty>\d+\.?\d*)\s+'                  # quantity
        r'(?P<desc>.+?)\s+'                       # description (non-greedy)
        r'(?P<price>-?\d[\d,]*\.\d{2})\.?\s+'     # price (allow OCR trailing period)
        r'(?P<tax>\d[\d,]*\.\d{2})\.?\s+'         # tax
        r'(?P<amount>-?\d[\d,]*\.\d{2})\.?\s*$',  # amount
        re.IGNORECASE | re.MULTILINE)
    for m in ng_wm_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc and len(desc) > 2:
            items.append(ChargeItem(
                charge_description=desc,
                qty=_clean_qty(m.group('qty')),
                amount=_clean_amount(m.group('amount')),
                unit_price=_clean_amount(m.group('price')),
                raw_text=m.group(0)))

    # NG WM truncated lines: only PRICE TAX at end (AMOUNT missing/wrapped)
    if not items:
        ng_wm_trunc = re.compile(
            r'(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+'
            r'(?:[A-Z]{0,4}\d{5,}\s+)?'
            r'(?:Trash|Cardboard|Recycl\w*|MSW|OCC|Organics?|'
            r'Single|Food|Green\w*|Metal|Mixed|Wood|'
            r'Construc\w*|Co-?\w*)\s+'
            r'(?:[^\d\s]\S*\s+)?'
            r'(?P<qty>\d+\.?\d*)\s+'
            r'(?P<desc>.+?)\s+'
            r'(?P<price>-?\d[\d,]*\.\d{2})\.?\s+'
            r'(?P<amount>\d[\d,]*\.\d{2})\.?\s*$',
            re.IGNORECASE | re.MULTILINE)
        for m in ng_wm_trunc.finditer(text):
            desc = m.group('desc').strip()
            if desc and len(desc) > 2:
                items.append(ChargeItem(
                    charge_description=desc,
                    qty=_clean_qty(m.group('qty')),
                    amount=_clean_amount(m.group('amount')),
                    unit_price=_clean_amount(m.group('price')),
                    raw_text=m.group(0)))

    if items:
        return items

    # Standard WM: DATE MATERIAL QTY PRICE TAX AMOUNT \n DESCRIPTION
    wm_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*'
        r'(?:[\w\d]+\s+)?'
        r'(?P<material>Trash|Cardboard|Recycl\w*|MSW|OCC|Organics?|'
        r'Single\s*\n?\s*Stream\s*\n?\s*Recycl\w*|Food\s*\n?\s*Waste)\s+'
        r'(?P<qty>[\d.]+)\s+(?P<price>[\d,.]+)\s+(?P<tax>[\d,.]+)\s+'
        r'(?P<amount>-?[\d,.]+)\s*\n'
        r'(?P<desc>(?:Pickup|Container|Delivery|Haul|Disposal|Excess|Removal|'
        r'Government|Utility|Fuel|Landfill)[^\n]+)', re.IGNORECASE)
    for m in wm_pat.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group('desc').strip(),
            qty=_clean_qty(m.group('qty')),
            amount=_clean_amount(m.group('amount')),
            unit_price=_clean_amount(m.group('price')),
            raw_text=m.group(0)))

    # Tax/fee lines (qty=0.00)
    tax_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*'
        r'(?P<material>\w+(?:\s+\w+)?)\s+'
        r'0\.00\s+0\.00\s+[\d.]+\s+'
        r'(?P<amount>-?[\d,.]+)\s*\n'
        r'(?P<desc>(?:Utility\s+Tax|Pickup\s+Increase|Container\s+Service\s+Charge|'
        r'Disposal\s+Increase|Fuel\s+Surcharge)[^\n]+)', re.IGNORECASE)
    found_descs = {i.charge_description for i in items}
    for m in tax_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc not in found_descs:
            items.append(ChargeItem(
                charge_description=desc,
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))

    # Credit lines (negative amounts)
    credit_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*'
        r'(?P<material>\w+(?:\s+\w+)?)\s+'
        r'[\d.]+\s+[\d,.]+\s+[\d,.]+\s+'
        r'-(?P<amount>[\d,.]+)\s*\n'
        r'(?P<desc>[^\n]+)', re.IGNORECASE)
    for m in credit_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc not in found_descs and not desc.startswith('SCode'):
            amt = _clean_amount(m.group('amount'))
            items.append(ChargeItem(
                charge_description=desc,
                amount=-amt if amt else None,
                raw_text=m.group(0)))

    # Location charges fallback
    if not items:
        loc_pat = re.compile(
            r'(?P<location>[\w\s\-]+)\s+LOCATION\s+CHARGES\s+'
            r'(?P<amount>[\d,.]+)', re.IGNORECASE)
        for m in loc_pat.finditer(text):
            items.append(ChargeItem(
                charge_description=f"{m.group('location').strip()} Location Charges",
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))

    # Current Invoice Charges fallback
    if not items:
        tot = re.search(r'Current\s+Invoice\s+Charges\s*\n?\$?\s*([\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(
                charge_description="Current Invoice Charges",
                amount=_clean_amount(tot.group(1)),
                raw_text=tot.group(0)))

    return items


# =============================================================================
# USA WASTE (WM subsidiary - same format)
# =============================================================================

def _extract_usa_waste(text: str) -> List[ChargeItem]:
    # USA Waste uses WM's DETAILS OF SERVICE format:
    # "Lock 09/01/25 1.00 10.00"
    # "8 Yard Dumpster Service 09/01/25 1.00 303.73"
    # "2 - 6 Yard Dumpster Recycle 1 Time Per Week 09/01/25 2.00 333.60"
    items = []

    detail_pat = re.compile(
        r'(?P<desc>(?:\d+\s*-\s*)?(?:\d+\s*(?:Yard|Gallon|YD|GAL)\s+)?'
        r'(?:Dumpster|Toter|Cart|Lock|Container|Compactor)[\w\s\-]*?'
        r'(?:Service|Per\s+Unit|Per\s+Week|Recycl\w*|Organics?|Trash)?)\s+'
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?P<qty>[\d.]+)\s+'
        r'(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in detail_pat.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group('desc').strip(),
            qty=_clean_qty(m.group('qty')),
            amount=_clean_amount(m.group('amount')),
            raw_text=m.group(0)))

    # Surcharge/fee lines (no date, no qty): "Energy Surcharge 265.83"
    fee_pat = re.compile(
        r'(?P<desc>(?:Recyclable\s+Material\s+Offset|Energy\s+Surcharge|Administrative\s+Charge|'
        r'FRANCHISE\s+FEE[\w\-]*|Fuel\s+Surcharge|Environmental\s+Fee|Regulatory\s+Charge|'
        r'Overage\s+Service[\w\s]*|Recycling\s+contamination[\w\s]*|Clean[\w\s]*Fee)[\w\s\-#]*?)\s+'
        r'(?P<amount>-?\(?\d[\d,]*\.?\d*\)?)\s*$',
        re.MULTILINE | re.IGNORECASE)
    found = {i.charge_description.upper() for i in items}
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(
                charge_description=desc,
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    # Try standard WM patterns if USA Waste detail format didn't work
    if not items:
        items = _extract_waste_management(text)

    return items


# =============================================================================
# REPUBLIC SERVICES
# =============================================================================

def _extract_republic(text: str) -> List[ChargeItem]:
    items = []

    # Container service lines: "N Container(s) SIZE TYPE, N Lift(s) Per Week"
    container_pat = re.compile(
        r'(?P<desc>\d+\s+Container\(?s?\)?\s+[\d.]+\s*(?:Yard|YD|Gallon)[\w\s,]+?'
        r'(?:Per\s+(?:Week|Month|Pickup)))\s*\n'
        r'(?P<svc>[^\n]+?(?:Service|Charge|Fee|Surcharge))\s+'
        r'(?:\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s+)?'
        r'\$?(?P<rate>[\d,]+\.?\d*)\s+'
        r'\$?(?P<amount>-?[\d,]+\.?\d*)', re.IGNORECASE)
    for m in container_pat.finditer(text):
        items.append(ChargeItem(
            charge_description=f"{m.group('desc').strip()} - {m.group('svc').strip()}",
            amount=_clean_amount(m.group('amount')),
            unit_price=_clean_amount(m.group('rate')),
            raw_text=m.group(0)))

    found = {i.charge_description.upper() for i in items}

    # Service/charge lines with date range
    svc_pat = re.compile(
        r'(?P<desc>(?:Delivery|Removal|Extra|Admin|Container|Fuel|Enviro|Disposal|'
        r'Recycl\w*|Franchise|Regulatory|Lock|Lid|Over[\w]*|Contamination)[\w\s\-/]+?)\s+'
        r'(?:\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s+)?'
        r'\$?(?P<rate>[\d,]+\.?\d*)\s+'
        r'\$?(?P<amount>-?[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found and len(desc) > 5:
            items.append(ChargeItem(
                charge_description=desc,
                amount=_clean_amount(m.group('amount')),
                unit_price=_clean_amount(m.group('rate')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    # Simple fee lines
    fee_pat = re.compile(
        r'(?P<desc>(?:Fuel|Energy|Environmental|Franchise|Admin|Regulatory|Recovery|'
        r'Sustainability|Late)\s*(?:Surcharge|Fee|Charge|Recovery))\s+'
        r'\$?(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(
                charge_description=desc,
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    # Fallback
    if not items:
        tot = re.search(r'(?:Total\s+Amount\s+Due|Invoice\s+Charges)\s*\$?(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(
                charge_description="Invoice Charges",
                amount=_clean_amount(tot.group('amt')),
                raw_text=tot.group(0)))

    return items


# =============================================================================
# COCKEY'S ENTERPRISES
# =============================================================================

def _extract_cockeys(text: str) -> List[ChargeItem]:
    items = []

    # Skip LEED Waste Analysis and Tonnage reports (not invoices)
    if re.search(r'LEED\s+Waste\s+Analysis|TONNAGE\s+REPORT|YTD\s+TONNAGE', text, re.IGNORECASE):
        return []

    # Pattern 1: RO/FL inline charges (single date)
    # "11/05/25 RO - Disposal Charge - per Ton 3581429 2.00 94.00 188.00"
    # "11/07/25 RO - Disposal Charge - 3588116 3568595-A 1.63 100.00 163.00"
    ro_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?P<desc>(?:RO|FL)\s*-\s*[A-Za-z][\w\s\-]+?)\s+'
        r'(?:\d{5,}[\w\-]*\s+)+'
        r'(?P<qty>[\d,.]+)\s+'
        r'(?P<rate>[\d,]+\.\d{2})\s+'
        r'(?P<amount>[\d,]+\.\d{2})',
        re.IGNORECASE)
    for m in ro_pat.finditer(text):
        desc = m.group('desc').strip().rstrip('-').strip()
        if any(w in desc.upper() for w in ['TAX', 'TOTAL', 'BALANCE', 'PAYMENT']):
            continue
        items.append(ChargeItem(
            charge_description=desc,
            qty=_clean_qty(m.group('qty')),
            amount=_clean_amount(m.group('amount')),
            unit_price=_clean_amount(m.group('rate')),
            raw_text=m.group(0)))

    # Pattern 2: Date-range charges with 3 numbers (qty rate amount)
    # "11/01/25 - 11/30/25 FL-Comm-Trash-02yd 1.00 443.00 443.00"
    # "11/01/25 - 11/30/25 ClosedBox.RO 1.00 300.00 300.00"
    range_pat = re.compile(
        r'\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s+'
        r'(?P<desc>[A-Za-z][\w\-.]+(?:\s+[\w\-.]+)*?)\s+'
        r'(?P<qty>[\d.]+)\s+(?P<rate>[\d,]+\.\d{2})\s+(?P<amount>[\d,]+\.\d{2})',
        re.IGNORECASE)
    found = {i.charge_description.upper() for i in items}
    for m in range_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found and not any(w in desc.upper() for w in ['TAX', 'TOTAL', 'BALANCE', 'SITE']):
            items.append(ChargeItem(
                charge_description=desc,
                qty=_clean_qty(m.group('qty')),
                amount=_clean_amount(m.group('amount')),
                unit_price=_clean_amount(m.group('rate')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    # Pattern 2b: Date-range charges with 2 numbers (qty amount, no unit_price column)
    # "08/01/25 - 08/31/25 FL-Comm-Recycling-02yd 1.00 88.00"
    if not items:
        range2_pat = re.compile(
            r'\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s+'
            r'(?P<desc>[A-Za-z][\w\-.]+(?:\s+[\w\-.]+)*?)\s+'
            r'(?P<qty>[\d.]+)\s+(?P<amount>[\d,]+\.\d{2})\s*$',
            re.IGNORECASE | re.MULTILINE)
        for m in range2_pat.finditer(text):
            desc = m.group('desc').strip()
            if not any(w in desc.upper() for w in ['TAX', 'TOTAL', 'BALANCE', 'SITE']):
                qty = _clean_qty(m.group('qty'))
                items.append(ChargeItem(
                    charge_description=desc,
                    qty=qty if qty and qty != 1.0 else None,
                    amount=_clean_amount(m.group('amount')),
                    raw_text=m.group(0)))

    # Pattern 3: Old column format with ref code (letters)
    # "12/31/2024 | T SINGLE STREAM RECYCLING 1.00 105.00 105.00"
    # "4/30/2025 WwW MONTHLY TRASH SERVICE 2.00 195.00 390.00"
    if not items:
        old_pat = re.compile(
            r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+\|?\s*'
            r'(?:[A-Za-z]{1,4})\s+'
            r'(?P<desc>(?!PAYMENT|ACH)[A-Z][\w\s\-/&]+?)\s+'
            r'(?P<qty>\d+\.?\d*)\s+'
            r'(?P<rate>[\d,]+\.?\d*)\s+'
            r'(?P<amount>[\d,]+\.?\d*)',
            re.IGNORECASE)
        for m in old_pat.finditer(text):
            desc = m.group('desc').strip()
            if any(w in desc.upper() for w in ['PAYMENT', 'ACH', 'TOTAL', 'BALANCE']):
                continue
            qty = _clean_qty(m.group('qty'))
            items.append(ChargeItem(
                charge_description=desc,
                qty=qty if qty and qty != 1.0 else None,
                amount=_clean_amount(m.group('amount')),
                unit_price=_clean_amount(m.group('rate')),
                raw_text=m.group(0)))

    # Pattern 4: Statement format (CHARGES THIS INVOICE section)
    # "6/24/2025 1146596 COMPACTOR HAUL RATE 1.00 205.00 205.00" (with digit ref)
    # "8/19/2025 1156859-30 DELIVERY CHARGE 1.00 125.00 125.00" (ref with hyphen)
    # "3/31/2025 SINGLE STREAM RECYCLING 2.00 262.50 525.00" (no ref)
    # "7/31/2025 | COMPACTORS MO EQUIP SVC/ROLL-OFF 2.00 1,100.00 2,200.00" (pipe)
    if not items and re.search(r'CHARGES\s+THIS\s+INVOICE', text, re.IGNORECASE):
        stmt_pat = re.compile(
            r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+\|?\s*'
            r'(?:\d{5,}[\w-]*\s+)?'
            r'(?P<desc>(?!PAYMENT|CUSTOMER|PO#|\d+%)[A-Z][\w\s\-/&]+?)\s+'
            r'(?P<qty>[\d.]+)\s+'
            r'(?P<rate>[\d,]+\.\d{2})\s+'
            r'(?P<amount>[\d,]+\.\d{2})',
            re.IGNORECASE)
        for m in stmt_pat.finditer(text):
            desc = m.group('desc').strip()
            if any(w in desc.upper() for w in ['PAYMENT', 'ACH', 'TOTAL', 'BALANCE', 'CUSTOMER PO']):
                continue
            qty = _clean_qty(m.group('qty'))
            items.append(ChargeItem(
                charge_description=desc,
                qty=qty if qty and qty != 1.0 else None,
                amount=_clean_amount(m.group('amount')),
                unit_price=_clean_amount(m.group('rate')),
                raw_text=m.group(0)))

    # Fuel surcharge
    fuel = re.search(r'Fuel\s+Surcharge\s+(?P<amount>[\d,]+\.?\d*)', text, re.IGNORECASE)
    if fuel:
        amt = _clean_amount(fuel.group('amount'))
        if amt and amt > 0:
            items.append(ChargeItem(charge_description='Fuel Surcharge', amount=amt, raw_text=fuel.group(0)))

    # Last resort: INVOICE TOTAL
    if not items:
        tot = re.search(r'INVOICE\s+TOTAL\s*\$?\s*(?P<amount>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(
                charge_description="Invoice Total",
                amount=_clean_amount(tot.group('amount')),
                raw_text=tot.group(0)))

    return items


# =============================================================================
# ROBINSON WASTE
# =============================================================================

def _extract_robinson(text: str) -> List[ChargeItem]:
    items = []
    found = set()

    # Service lines: "02 - Dec Dump & Return W.O# 326533 1.00 $125.00 $125.00"
    # Also: "02 Dec Roll Off Service - Haul Charge $280.00 1.00 $280.00"
    # Pipe-delimited variant: "01 - Aug | Container Service Fee 1.00 $271.76 $271.76"
    svc_pat = re.compile(
        r'(?P<date>\d{1,2}\s*-?\s*\w{3})\s*\|?\s+'
        r'(?P<desc>[A-Z][\w\s\-&/]+?)\s+'
        r'(?:W\.?O\.?\s*#?\s*\d+\s+)?'
        r'(?:INO?\d+\s+)?'
        r'(?P<qty>[\d.]+)\s+'
        r'\$(?P<rate>[\d,]+\.?\d*)\s+'
        r'\$(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip()
        if any(w in desc.upper() for w in ['PAYMENT', 'BALANCE', 'TOTAL']):
            continue
        key = f"{m.group('date').strip()}_{desc}"
        if key not in found:
            items.append(ChargeItem(
                charge_description=desc,
                qty=_clean_qty(m.group('qty')),
                amount=_clean_amount(m.group('amount')),
                unit_price=_clean_amount(m.group('rate')),
                raw_text=m.group(0)))
            found.add(key)

    # Disposal lines: "02 - Dec MSW - Disposal 01-4305911 $30.87"
    disp_pat = re.compile(
        r'(?P<date>\d{1,2}\s*-?\s*\w{3})\s*\|?\s+'
        r'(?P<desc>[\w\s]+?-?\s*Disposal[\w\s]*?)\s+'
        r'[\w\-#]+\s+'
        r'\$(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in disp_pat.finditer(text):
        desc = m.group('desc').strip()
        key = f"{m.group('date').strip()}_{desc}"
        if key not in found:
            items.append(ChargeItem(
                charge_description=desc,
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
            found.add(key)

    # Surcharges / fees
    fee_pat = re.compile(
        r'(?:(?:\d{1,2}\s*-?\s*\w{3})\s*\|?\s+)?'
        r'(?P<desc>(?:Environmental|Fuel|Energy|Admin|Regulatory|Finance|'
        r'Container\s*Service)\s*'
        r'(?:Surcharge|Fee|Charge|Recovery))\s+'
        r'\$(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    fee_found = {i.charge_description.upper() for i in items}
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in fee_found:
            items.append(ChargeItem(
                charge_description=desc,
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
            fee_found.add(desc.upper())

    return items


# =============================================================================
# BURGMEIER'S HAULING
# =============================================================================

def _extract_burgmeiers(text: str) -> List[ChargeItem]:
    items = []

    # Portal format sub-items: "30 YD Switch 241.50 1 241.50"
    sub_pat = re.compile(
        r'(?P<desc>(?:\d+\s*YD\s+)?(?:Switch|Dump\s*&?\s*Return|Haul|Delivery|Removal|'
        r'Final\s*Pull|Pull|Swap|Live\s*Load|Disposal\s+by\s+Ton|usageDays))\s+'
        r'(?P<rate>[\d,]+\.?\d*)\s+'
        r'(?P<qty>[\d.]+)\s+'
        r'(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in sub_pat.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group('desc').strip(),
            qty=_clean_qty(m.group('qty')),
            amount=_clean_amount(m.group('amount')),
            unit_price=_clean_amount(m.group('rate')),
            raw_text=m.group(0)))

    # Legacy format: "date |invoice# qty desc date_range amount"
    # "11/30/25 |5BX03377 1 MSW8Y 2xWw TRASH REMOVAL(C) 11/01/25-11/30/25 391.00"
    # "08/31/25 |58x03445 1 TOTER RENTAL RENTAL 08/01/25-08/31/25 46.00"
    if not items:
        legacy_pat = re.compile(
            r'\d{1,2}/\d{1,2}/\d{2,4}\s*\|?\s*'
            r'\w+\s+'
            r'(?P<qty>\d+)\s+'
            r'(?P<desc>.+?)\s+'
            r'\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*'
            r'\d[\d\s]*/[\d\s]*\d/\d{2,4}\s+'
            r'(?P<amount>[\d\s,.]+\.\s*\d{2})',
            re.IGNORECASE)
        for m in legacy_pat.finditer(text):
            desc = m.group('desc').strip()
            if any(w in desc.upper() for w in ['PAYMENT', 'ACH', 'TOTAL', 'BALANCE']):
                continue
            amount_str = re.sub(r'\s+', '', m.group('amount'))
            qty = _clean_qty(m.group('qty'))
            items.append(ChargeItem(
                charge_description=desc,
                qty=qty if qty and qty != 1.0 else None,
                amount=_clean_amount(amount_str),
                raw_text=m.group(0)))

    # Surcharges
    surcharge = re.findall(r'Surcharges\s+([\d,]+\.?\d*)', text, re.IGNORECASE)
    for s in surcharge:
        amt = _clean_amount(s)
        if amt and amt > 0:
            items.append(ChargeItem(
                charge_description="Surcharges",
                amount=amt,
                raw_text=f"Surcharges {s}"))

    return items


# =============================================================================
# UNIVERSAL WASTE
# =============================================================================

def _extract_universal_waste(text: str) -> List[ChargeItem]:
    items = []

    # Format: "03/01/25 - 03/31/25 2 3YD FL Rec. 378.49 378.49"
    # Columns: Date QTY Desc Charges Credits Fees Extended
    # Amount is the last number (extended), charge is second-to-last
    svc_pat = re.compile(
        r'(?P<start>\d{1,2}/\d{1,2}/\d{2,4})\s*-?\s*(?:\d{1,2}/\d{1,2}/\d{2,4})?\s+'
        r'(?P<qty>\d+)\s+'
        r'(?P<desc>(?:\d+\s*)?(?:YD|GAL|G)\s+(?:FL|Organics)[\w\s.]*?)\s+'
        r'(?P<amount>[\d,]+\.\d{2})\s+[\d,]+\.\d{2}', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group('desc').strip(),
            qty=_clean_qty(m.group('qty')),
            amount=_clean_amount(m.group('amount')),
            raw_text=m.group(0)))

    found = {i.charge_description.upper() for i in items}

    # Credits/adjustments: "02/01/25 1 Price Increase -55.71 -55.71"
    credit_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?P<qty>\d+)\s+'
        r'(?P<desc>Price\s+Increase[\w\s]*?)\s+'
        r'(?P<amount>-?[\d,]+\.\d{2})\s+-?[\d,]+\.\d{2}', re.IGNORECASE)
    for m in credit_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(
                charge_description=desc,
                qty=_clean_qty(m.group('qty')),
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    # Fees: "03/01/25 - 03/31/25 1 Lock 25.00 25.00"
    fee_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s*-?\s*(?:\d{1,2}/\d{1,2}/\d{2,4})?\s+'
        r'(?P<qty>\d+)\s+'
        r'(?P<desc>Lock|Lid|Admin|Environmental|Extra[\w\s]*?)\s+'
        r'(?P<amount>[\d,]+\.\d{2})\s+[\d,]+\.\d{2}', re.IGNORECASE)
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(
                charge_description=desc,
                qty=_clean_qty(m.group('qty')),
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    if not items:
        tot = re.search(r'(?:Total\s+New\s+Charges|Current\s+Charges)\s*:?\s*\$?(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(
                charge_description="Current Charges",
                amount=_clean_amount(tot.group('amt')),
                raw_text=tot.group(0)))

    return items


# =============================================================================
# RUMPKE
# =============================================================================

def _extract_rumpke(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?:\d{1,2}/\d{1,2}/\d{2,4}\s+)?'
        r'(?P<desc>(?:\d+\s*)?(?:YD|GAL|CART)[\w\s/\-]+(?:MSW|TRASH|CRDBD|COM\s*MIX|RECYCLE?|OCC))'
        r'(?:\s*#\s*P/U:\s*(?P<pu>\d+))?\s+'
        r'(?P<qty>[\d.]+)\s+'
        r'(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group('desc').strip(),
            qty=_clean_qty(m.group('qty')),
            amount=_clean_amount(m.group('amount')),
            raw_text=m.group(0)))

    found = {i.charge_description.upper() for i in items}

    fuel_pat = re.compile(
        r'(?P<desc>FUEL\s+SURCHARGE\s*(?:FL|RL|RO|RECY)?)\s+'
        r'(?P<qty>[\d.]+)\s+'
        r'(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in fuel_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(
                charge_description=desc,
                qty=_clean_qty(m.group('qty')),
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    if not items:
        tot = re.search(r'Invoice\s+Total:\s*(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(
                charge_description="Invoice Total",
                amount=_clean_amount(tot.group('amt')),
                raw_text=tot.group(0)))

    return items


# =============================================================================
# CASELLA
# =============================================================================

def _extract_casella(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?P<desc>(?:CHARGE\s+PRORATION|(?:\d+\s*)?(?:YD|GAL)\s+FL[\w\s#:]+))\s+'
        r'(?P<qty>[\d.]+)\s+'
        r'(?P<amount>-?[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        amt = _clean_amount(m.group('amount'))
        if amt and amt != 0:
            items.append(ChargeItem(
                charge_description=m.group('desc').strip(),
                qty=_clean_qty(m.group('qty')),
                amount=amt,
                raw_text=m.group(0)))

    found = {i.charge_description.upper() for i in items}

    fee_pat = re.compile(
        r'(?P<desc>(?:Resource\s+Solutions|Fuel|Energy|Environmental|Sustainability)[\w\s&]+(?:Fee|Charge|Surcharge)):\s*'
        r'(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            amt = _clean_amount(m.group('amount'))
            if amt and amt > 0:
                items.append(ChargeItem(
                    charge_description=desc, amount=amt, raw_text=m.group(0)))
                found.add(desc.upper())

    return items


# =============================================================================
# MERIDIAN WASTE
# =============================================================================

def _extract_meridian(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?P<desc>(?:O?\d+\s*)?(?:YD|GL|GAL)\s+(?:F/L|R/O|ROL|RO|RL|PERM)[\w\s/\-#:]+)\s+'
        r'(?P<qty>[\d.]+)\s+'
        r'(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group('desc').strip(),
            qty=_clean_qty(m.group('qty')),
            amount=_clean_amount(m.group('amount')),
            raw_text=m.group(0)))

    found = {i.charge_description.upper() for i in items}

    fee_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?P<desc>(?:BROKER\s+)?(?:FUEL|FRANCHISE|COUNTY|CITY|ENVIRO\w*|REGULATORY|RECOVERY)[\w\s]*'
        r'(?:FL|RL|RO|FEE|CHARGE|SURCHARGE)?)\s+'
        r'(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found and len(desc) > 3:
            items.append(ChargeItem(
                charge_description=desc, amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))
            found.add(desc.upper())

    return items


# =============================================================================
# MARK DUNNING / MDI
# =============================================================================

def _extract_mdi(text: str) -> List[ChargeItem]:
    items = []

    # MDI/Mark Dunning format (same billing system as Burgmeier's):
    # "10/01/25 5A159772 1 8Y BIN 1XW 10/01/25-10/31/25 110.00"
    # "10/01/25 5A159772 1 FUEL SURCHARGE 10/01/25 16.50"
    # "09/22/25] 59X24618 1 30Y ROLLOFF HAULING FEE 09/22/25 250.00"
    # "09/30/25] 59x24618 1. MONTH CONT RENT RENTAL 09/01/25-09/30/25 30.00"
    # "09/30/25] 59x24618 1 FUELSURCHARGE  FUELSURCHARGE 09/30/25 37.50"
    svc_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})[|\]]?\s*'
        r'[\w]+\s+'
        r'(?P<qty>\d+)\.?\s+'
        r'(?P<desc>[\w\s\-/]+?)\s+'
        r'(?:\d{1,2}/\d{1,2}/\d{2,4}\s*(?:-\s*\d[\d\s]*/[\d\s]+/\d{2,4}\s+)?)?'
        r'(?:\d+\s+)?'
        r'(?P<amount>\d[\d,]*\.?\d*)\s*$',
        re.MULTILINE | re.IGNORECASE)
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip()
        if any(w in desc.upper() for w in ['PAYMENT', 'RCVD', 'THANK', 'PRIOR', 'CURRENT']):
            continue
        # Clean duplicate words (e.g., "FUELSURCHARGE  FUELSURCHARGE")
        words = desc.split()
        if len(words) >= 2 and words[-1].upper() == words[-2].upper():
            desc = ' '.join(words[:-1])
        qty = _clean_qty(m.group('qty'))
        items.append(ChargeItem(
            charge_description=desc,
            qty=qty if qty and qty != 1.0 else None,
            amount=_clean_amount(m.group('amount')),
            raw_text=m.group(0)))

    # Standalone fee lines: "LANDFILL FEE 195.00"
    fee_pat = re.compile(
        r'^(?P<desc>LANDFILL\s+FEE|TRIP\s+CHARGE|FUEL\s*SURCHARGE)\s+(?P<amount>[\d,]+\.?\d*)\s*$',
        re.MULTILINE | re.IGNORECASE)
    found = {i.charge_description.upper() for i in items}
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(
                charge_description=desc,
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    return items


# =============================================================================
# JAMAICA ASH
# =============================================================================

def _extract_jamaica_ash(text: str) -> List[ChargeItem]:
    items = []

    # Format: "07/14/25 | 57X00727 1 30YCOMPACTOR HAULING FEE 00760684 275.00"
    # The 00XXXXXX is a ref number, actual amount follows with decimal
    haul_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s*\|?\s*'
        r'(?:\w+\s+)?'
        r'(?P<qty>\d+)\s+'
        r'(?P<desc>(?:\d+Y\s*)?(?:COMPACTOR|CONTAINER|ROLL\s*OFF|DUMPSTER)\s+'
        r'(?:HAULING|HAUL)\s*(?:FEE|CHARGE)?[\w\s]*?)\s+'
        r'(?:\d{7,}\s+)?'
        r'(?P<amount>[\d,]+\.\d{2})\s*$', re.IGNORECASE | re.MULTILINE)
    for m in haul_pat.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group('desc').strip(),
            qty=_clean_qty(m.group('qty')),
            amount=_clean_amount(m.group('amount')),
            raw_text=m.group(0)))

    disp_pat = re.compile(
        r'(?P<desc>LANDFILL\s+FEE)\s+'
        r'(?P<qty>[\d.]+)\s*tons?\s+'
        r'(?P<rate>[\d,]+\.\d{2})/ton\s+'
        r'(?P<amount>[\d,]+\.\d{2})', re.IGNORECASE)
    for m in disp_pat.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group('desc').strip(),
            qty=_clean_qty(m.group('qty')),
            amount=_clean_amount(m.group('amount')),
            unit_price=_clean_amount(m.group('rate')),
            raw_text=m.group(0)))

    rental_pat = re.compile(
        r'(?P<desc>(?:COMPACTOR|CONTAINER|DUMPSTER)\s+RENTAL[\w\s]*?)\s+'
        r'(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in rental_pat.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group('desc').strip(),
            amount=_clean_amount(m.group('amount')),
            raw_text=m.group(0)))

    return items


# =============================================================================
# WASTE CONNECTIONS
# =============================================================================

def _extract_waste_connections(text: str) -> List[ChargeItem]:
    items = []
    found = set()

    # Format 1 (parenthetical): "4/30/2025 RENTAL FEES (1.0000 @ $162.08) $162.08"
    paren_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?P<desc>[A-Z][\w\s\-/&#]+?)\s+'
        r'\((?P<qty>[\d.]+)\s*@\s*\$(?P<rate>[\d,]+\.?\d*)\)\s+'
        r'\$\s*(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in paren_pat.finditer(text):
        desc = m.group('desc').strip()
        if any(w in desc.upper() for w in ['PAYMENT', 'THANK YOU', 'TOTAL']):
            continue
        qty = _clean_qty(m.group('qty'))
        items.append(ChargeItem(
            charge_description=desc,
            qty=qty if qty and qty != 1.0 else None,
            amount=_clean_amount(m.group('amount')),
            unit_price=_clean_amount(m.group('rate')),
            raw_text=m.group(0)))
        found.add(desc.upper())

    # Format 2 (Each @): "09/30/24 Disposal 0.45 @ $62.00 $ 27.90"
    # Also: "10/31/24 Rental Fees 3 Each @ $111.00 $ 333.00"
    # Also: "09/30/24 Environmental Compliance 1Each@ $11.85 $11.85"
    each_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\.?\s+'
        r'(?P<desc>[A-Z][\w\s\-/&]+?)\s+'
        r'(?P<qty>[\d.]+)\s*(?:Each\s*)?@\s*\$(?P<rate>[\d,]+\.?\d*)\s+'
        r'\$\s*(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in each_pat.finditer(text):
        desc = m.group('desc').strip()
        if any(w in desc.upper() for w in ['PAYMENT', 'THANK YOU', 'TOTAL']):
            continue
        if desc.upper() not in found:
            qty = _clean_qty(m.group('qty'))
            items.append(ChargeItem(
                charge_description=desc,
                qty=qty if qty and qty != 1.0 else None,
                amount=_clean_amount(m.group('amount')),
                unit_price=_clean_amount(m.group('rate')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    # Surcharges/fees without (qty@rate): "FUEL & MATERIAL SURCHARGE $404.94"
    fee_pat = re.compile(
        r'(?P<desc>(?:FUEL|ENVIRONMENTAL|ENERGY|ADMIN|REGULATORY|MATERIAL|COMPLIANCE)[\w\s&]+?'
        r'(?:SURCHARGE|FEE|CHARGE))\s+\$(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(
                charge_description=desc,
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    # Date-prefixed simple charges without parenthetical: "4/28/2025 FINANCE CHARGE ... $9.49"
    simple_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?P<desc>(?:FINANCE|LATE|RENTAL|ADMIN|DELIVERY|PICKUP|CONTAINER|'
        r'COMPACTOR|HAUL|ROLL\s*OFF)[\w\s\-/&]+?)\s+'
        r'\$(?P<amount>[\d,]+\.?\d*)\s*$',
        re.MULTILINE | re.IGNORECASE)
    for m in simple_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(
                charge_description=desc,
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    # Broad format: "date |? code? desc qty sizeYD? code? $ amount"
    # "10/31/24 BASIC CONTAINER CHARGE 1.00 36.00YD C $ 491.47"
    # "10/31/24 BASIC SERVICE CHARGE 1.00 8.00YD $ 187.54"
    # "10/18/24 RO DUMP & RETURN 1.00 20,00YD SHANE SCHROEDER $ 225.00"
    broad_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s*\|?\s*'
        r'(?:[\d.,]+\s*(?:YD|M)\s+)?'
        r'(?:\d+\s+[\d.,]+\s*YD\s+)?'
        r'(?P<desc>[A-Z][\w\s&\-/]+?)\s+'
        r'(?:W\.?O\.?\s*#?\s*\d+\s+[\w\s]*?\s+)?'
        r'(?P<qty>[\d.]+)\s+'
        r'(?:[\d.,]+\s*(?:YD|TN)\s*)?'
        r'(?:\w{1,3}\s+)?'
        r'\$\s*(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in broad_pat.finditer(text):
        desc = m.group('desc').strip()
        if any(w in desc.upper() for w in ['PAYMENT', 'THANK', 'TOTAL', 'PREVIOUS', 'BALANCE', 'CREDIT']):
            continue
        if desc.upper() not in found and len(desc) > 3:
            qty = _clean_qty(m.group('qty'))
            items.append(ChargeItem(
                charge_description=desc,
                qty=qty if qty and qty != 1.0 else None,
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    # Disposal/material lines: "10/18/24 DRY COMMERCIAL WASTE 2.59TN PP 509695 $116.55"
    disp_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s*\|?\s*'
        r'(?:\w+\s+)?'
        r'(?P<desc>(?:ICI|DRY|CONSTRUCTION|COMMERCIAL|C&D|MSW|RECYCL)[\w\s]+?)\s+'
        r'(?:[\w\-]+\s+)?'
        r'(?P<qty>[\d.]+)\s*TN\s+'
        r'(?:\w+\s+)?'
        r'\$\s*(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in disp_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            qty = _clean_qty(m.group('qty'))
            items.append(ChargeItem(
                charge_description=desc,
                qty=qty,
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    return items


# =============================================================================
# KMG HAULING
# =============================================================================

def _extract_kmg(text: str) -> List[ChargeItem]:
    items = []

    # Format: "6/1/2025 - 6/30/2025 2x/Week 8 YD FRONT LOAD SINGLE STREAM 1.00 $379.00 $379.00"
    # Also: "6/1/2025 - 6/30/2025 1x/Week 4 YD FRONT LOAD SOLID WASTE 1.00 $195.00 $195.00"
    svc_pat = re.compile(
        r'\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s+'
        r'(?P<desc>[\dxX]+/?\s*(?:Week|Month|Bi[\w]*)[\w\s]+?'
        r'(?:FRONT\s+LOAD|ROLL\s+OFF|REAR\s+LOAD|COMPACTOR|CART|CONTAINER)[\w\s]*?)\s+'
        r'(?P<qty>[\d.]+)\s+\$(?P<rate>[\d,]+\.?\d*)\s+\$(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in svc_pat.finditer(text):
        qty = _clean_qty(m.group('qty'))
        items.append(ChargeItem(
            charge_description=m.group('desc').strip(),
            qty=qty if qty and qty != 1.0 else None,
            amount=_clean_amount(m.group('amount')),
            unit_price=_clean_amount(m.group('rate')),
            raw_text=m.group(0)))

    # Broader date-range pattern if specific one doesn't match
    if not items:
        broad_pat = re.compile(
            r'\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s+'
            r'(?P<desc>[A-Z][\w\s/\-]+?)\s+'
            r'(?P<qty>[\d.]+)\s+\$(?P<rate>[\d,]+\.?\d*)\s+\$(?P<amount>[\d,]+\.?\d*)',
            re.IGNORECASE)
        for m in broad_pat.finditer(text):
            desc = m.group('desc').strip()
            if any(w in desc.upper() for w in ['TOTAL', 'BALANCE', 'PAYMENT']):
                continue
            if len(desc) > 5:
                qty = _clean_qty(m.group('qty'))
                items.append(ChargeItem(
                    charge_description=desc,
                    qty=qty if qty and qty != 1.0 else None,
                    amount=_clean_amount(m.group('amount')),
                    unit_price=_clean_amount(m.group('rate')),
                    raw_text=m.group(0)))

    # Single-date event: "1/22/2025 DELIVERY CHARGE - ROLL OFF - WO: 0000330319 1.00 $200.00 $200.00"
    if not items:
        event_pat = re.compile(
            r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
            r'(?P<desc>[A-Z][\w\s\-]+?)\s+'
            r'(?:-\s*WO\s*:\s*\d+\s+)?'
            r'(?P<qty>[\d.]+)\s+\$(?P<rate>[\d,]+\.?\d*)\s+\$(?P<amount>[\d,]+\.?\d*)',
            re.IGNORECASE)
        for m in event_pat.finditer(text):
            desc = m.group('desc').strip().rstrip('-').strip()
            if any(w in desc.upper() for w in ['TOTAL', 'BALANCE', 'PAYMENT']):
                continue
            if len(desc) > 5:
                qty = _clean_qty(m.group('qty'))
                items.append(ChargeItem(
                    charge_description=desc,
                    qty=qty if qty and qty != 1.0 else None,
                    amount=_clean_amount(m.group('amount')),
                    unit_price=_clean_amount(m.group('rate')),
                    raw_text=m.group(0)))

    # Fee lines: "ECONOMIC ADJUSTMENT CHARGE $56.86 $56.86" or just "FUEL SURCHARGE $25.00"
    fee_pat = re.compile(
        r'(?P<desc>(?:ECONOMIC|FUEL|ENVIRONMENTAL|ADMIN|REGULATORY|RECOVERY)\s*'
        r'(?:ADJUSTMENT|SURCHARGE|FEE|CHARGE)[\w\s]*?)\s+'
        r'\$(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    found = {i.charge_description.upper() for i in items}
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(charge_description=desc, amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))
            found.add(desc.upper())

    return items


# =============================================================================
# WB WASTE SOLUTIONS
# =============================================================================

def _extract_wb_waste(text: str) -> List[ChargeItem]:
    items = []

    # Date-range format: "11/01/2024 - 11/30/2024 Weekly 04YD FRONT LOAD SERVICE 1.00 $200.26"
    svc_pat = re.compile(
        r'\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s+'
        r'(?P<desc>(?:Weekly|Monthly|Bi[\s-]*Weekly|EOW|Every[\w\s]+)?\s*'
        r'(?:\d+\s*YD\s+)?'
        r'(?:FRONT\s*LOAD|ROLL\s*OFF|REAR\s*LOAD|CONTAINER|CART|COMPACTOR|RECYCLE|TOTER)[\w\s]*?'
        r'(?:SERVICE|PICKUP|REMOVAL)?)\s+'
        r'(?P<qty>[\d.]+)\s+\$?(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in svc_pat.finditer(text):
        qty = _clean_qty(m.group('qty'))
        items.append(ChargeItem(
            charge_description=m.group('desc').strip(),
            qty=qty if qty and qty != 1.0 else None,
            amount=_clean_amount(m.group('amount')),
            raw_text=m.group(0)))

    # Fee/surcharge lines: "FUEL SURCHARGE $20.31"
    fee_pat = re.compile(
        r'(?P<desc>(?:FUEL|ENVIRONMENTAL|ADMIN|REGULATORY|RECOVERY|ENERGY)\s*'
        r'(?:SURCHARGE|FEE|CHARGE))\s+\$?(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    found = {i.charge_description.upper() for i in items}
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(charge_description=desc, amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))
            found.add(desc.upper())

    return items


# =============================================================================
# WASTE PRO
# =============================================================================

def _extract_waste_pro(text: str) -> List[ChargeItem]:
    items = []

    # Format: "10/01/2025 - 10/31/2025  FRONTLOAD8YD- SOLID WASTE SERVICE 6.00 1,590.00"
    # Also:   "09/01/2025-  Frontload 8 Yd- Solid Waste Service 6 $1,590.00"  (single date, $ prefix)
    svc_pat = re.compile(
        r'\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*(?:\d{1,2}/\d{1,2}/\d{2,4}\s+)?'
        r'(?P<desc>(?:FRONTLOAD|FRONT\s*LOAD|ROLL\s*OFF|REAR\s*LOAD|COMPACTOR|TOTER|CART|CONTAINER)\s*'
        r'[\w\s\-/&]+?(?:SERVICE|PICKUP|REMOVAL|HAUL|DISPOSAL|RENTAL)?)\s+'
        r'(?P<qty>[\d.]+)\s+\$?(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip().rstrip('-').strip()
        if 'TOTAL' not in desc.upper():
            qty = _clean_qty(m.group('qty'))
            items.append(ChargeItem(
                charge_description=desc,
                qty=qty if qty and qty != 1.0 else None,
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))

    # Fee lines
    fee_pat = re.compile(
        r'(?P<desc>(?:FUEL|ENVIRONMENTAL|ENERGY|ADMIN|REGULATORY|FRANCHISE)\s*'
        r'(?:SURCHARGE|FEE|CHARGE|RECOVERY))\s+\$?(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    found = {i.charge_description.upper() for i in items}
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(charge_description=desc, amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))
            found.add(desc.upper())

    return items


# =============================================================================
# LOCAL WASTE SOLUTION
# =============================================================================

def _extract_local_waste(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?P<desc>(?:O?\d+\s*YD)[\w\s#:/\-]+)\s+(?P<qty>[\d.]+)\s+(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip()
        if 'LATE' not in desc.upper() and 'PAYMENT' not in desc.upper():
            items.append(ChargeItem(charge_description=desc, qty=_clean_qty(m.group('qty')),
                                    amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))

    late_pat = re.compile(r'(?P<desc>LATE\s+FEE[\w\s]*)\s+(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in late_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))

    return items


# =============================================================================
# TATE SERVICES
# =============================================================================

def _extract_tate(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?P<desc>(?:SWAP|HAUL|DELIVERY|REMOVAL|PULL|DUMP|DISPOSAL|RENTAL)[\w\s\-/]+?'
        r'(?:ROLL\s*OFF|FRONT\s*LOAD|COMPACTOR|CONTAINER)?[\w\s\-]*?)'
        r'(?:\s*-\s*WO:\s*\d+)?\s+(?P<qty>[\d.]+)\s+\$(?P<rate>[\d,]+\.?\d*)\s+\$(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), qty=_clean_qty(m.group('qty')),
                                amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    if not items:
        tot = re.search(r'Total\s+New\s+Charges:?\s*\$?(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(charge_description="Total New Charges", amount=_clean_amount(tot.group('amt')), raw_text=tot.group(0)))

    return items


# =============================================================================
# VEIT DISPOSAL
# =============================================================================

def _extract_veit(text: str) -> List[ChargeItem]:
    items = []

    # Service code lines: "R1 30.00) Truck Time $250.00 1.00 $250.00"
    # Also: "31 - Dec | Ri 30.00} Container Rental 1.00 $1,020.00 $1,020.00"
    # Also: "31 - Dec |R1 6.00 | Monthly Service MSW Commercial 1.00 $655.00 $655.00"
    # Handles OCR: Ri=R1, | used as } or ), date prefix optional
    svc_pat = re.compile(
        r'(?:\d{1,2}\s*-\s*\w{3}\s*\|?\s*)?'
        r'(?:(?:R[\w]|FS|CD|DR|DL|SW|MH)\s+[\d.]+[)}\]|]\s*\|?\s*)?'
        r'(?P<desc>(?:Truck\s+Time|Disposal|Haul|Delivery|Removal|Pull|Swap|'
        r'Monthly\s+Service|Container\s+Rental|Fuel\s*Surcharge|Environmental|'
        r'Const\s+Debris|Recycle|MSW|Compactor|Container|Roll\s*Off|Front\s*Load)[\w\s\-]*?)\s+'
        r'(?P<qty>[\d.]+)\s+\$(?P<rate>[\d,]+\.?\d*)\s+\$(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in svc_pat.finditer(text):
        qty = _clean_qty(m.group('qty'))
        items.append(ChargeItem(
            charge_description=m.group('desc').strip(),
            qty=qty if qty and qty != 1.0 else None,
            amount=_clean_amount(m.group('amount')),
            unit_price=_clean_amount(m.group('rate')),
            raw_text=m.group(0)))

    # Standalone fee lines
    fee_pat = re.compile(
        r'(?P<desc>(?:Fuel|Environmental|Energy|Regulatory)\s*(?:Surcharge|Fee))\s+'
        r'\$(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    found = {i.charge_description.upper() for i in items}
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(charge_description=desc, amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))
            found.add(desc.upper())

    return items


# =============================================================================
# ATHENS SERVICES
# =============================================================================

def _extract_athens(text: str) -> List[ChargeItem]:
    items = []

    # Skip diversion reports
    if 'WASTE DIVERSION REPORT' in text.upper() or 'DIVERSION REPORT' in text.upper():
        return []

    # Roll-off lines: "04/02/2025 40YD-TRASH R/O-DUMP 1.00 $275.83"
    # Also: "04/02/2025 DISPOSAL FEE-PROC TRAS TKT# 1366042 7.05 $583.39"
    svc_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?P<desc>[\w\-/]+(?:[\s\-]+[\w\-/]+)*?)\s+'
        r'(?:TKT#?\s*\d+\s+)?'
        r'(?P<qty>[\d.]+)\s+\$(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip()
        if any(w in desc.upper() for w in ['PAYMENT', 'TOTAL', 'BALANCE', 'INVOICE', 'PREVIOUS', 'PMT']):
            continue
        if len(desc) < 3:
            continue
        qty = _clean_qty(m.group('qty'))
        items.append(ChargeItem(
            charge_description=desc,
            qty=qty if qty and qty != 1.0 else None,
            amount=_clean_amount(m.group('amount')),
            raw_text=m.group(0)))

    # Front-load lines: "2YD ORGANICS BIN # P/U: 3 2.00 $690.19"
    # Also: "3YD-ORGANICS BIN #P/U: 3"
    fl_pat = re.compile(
        r'(?P<desc>\d+YD[\w\s\-]+BIN[\w\s#:/]*?)\s+'
        r'(?P<qty>[\d.]+)\s+\$(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    found = {i.charge_description.upper() for i in items}
    for m in fl_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            qty = _clean_qty(m.group('qty'))
            items.append(ChargeItem(
                charge_description=desc,
                qty=qty if qty and qty != 1.0 else None,
                amount=_clean_amount(m.group('amount')),
                raw_text=m.group(0)))
            found.add(desc.upper())

    # Fee lines
    fee_pat = re.compile(
        r'(?P<desc>(?:Fuel|Environmental|Energy|Regulatory|Recovery|Franchise)\s*'
        r'(?:Surcharge|Fee|Charge|Recovery))\s+\$?(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(charge_description=desc, amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))
            found.add(desc.upper())

    return items


# =============================================================================
# WASTE DISPOSAL (AZ)
# =============================================================================

def _extract_waste_disposal(text: str) -> List[ChargeItem]:
    items = []

    # Format: "Swap Roll Off-30 Yard Open Top-Swap(08/07/2025)-WO0#59813 1.00 $185.00 $185.00"
    # Also: "Over Tonnage Roll Off-30 Yard Open Top-Over Tonnage(08/07/2025)-WO#57365 0.74 $45.00 $33.30"
    svc_pat = re.compile(
        r'(?P<desc>(?:Swap|Haul|Delivery|Removal|Pull|Dump|Over\s*Tonnage|Disposal|'
        r'Rental|Container|Processing|Environmental|Fuel|Admin)[\w\s\-/&,]+?)'
        r'(?:\(\d{1,2}/\d{1,2}/\d{2,4}\))?'
        r'(?:\s*-?\s*W[O0]\d?\s*#?\s*\d+)?\s+'
        r'(?P<qty>[\d.]+)\s+\$(?P<rate>[\d,]+\.?\d*)\s+\$(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip().rstrip('-').strip()
        if any(w in desc.upper() for w in ['SUBTOTAL', 'TOTAL', 'BALANCE']):
            continue
        qty = _clean_qty(m.group('qty'))
        items.append(ChargeItem(
            charge_description=desc,
            qty=qty if qty and qty != 1.0 else None,
            amount=_clean_amount(m.group('amount')),
            unit_price=_clean_amount(m.group('rate')),
            raw_text=m.group(0)))

    # Fee lines without $ prefix: "Environmental Fee 1.00 $3.50 $3.50"
    fee_pat = re.compile(
        r'(?P<desc>(?:Environmental|Fuel|Energy|Regulatory|Admin)\s*(?:Fee|Surcharge|Charge))\s+'
        r'[\d.]+\s+\$[\d,]+\.?\d*\s+\$(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    found = {i.charge_description.upper() for i in items}
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(charge_description=desc, amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))
            found.add(desc.upper())

    return items


# =============================================================================
# ASPEN WASTE
# =============================================================================

def _extract_aspen(text: str) -> List[ChargeItem]:
    items = []

    fee_pat = re.compile(
        r'(?P<desc>(?:Fuel|Enviro\w*|County|Solid\s+Waste)\s*(?:Surcharge|Fee|Tax|Charge))\s+\$?(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in fee_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))

    if not items:
        tot = re.search(r'(?:Invoice\s+Total|Amount\s+Due):?\s*\$?(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(charge_description="Invoice Total", amount=_clean_amount(tot.group('amt')), raw_text=tot.group(0)))

    return items


# =============================================================================
# SBC WASTE
# =============================================================================

def _extract_sbc_waste(text: str) -> List[ChargeItem]:
    items = []
    found = set()

    # Skip tonnage reports (not invoices)
    if re.search(r'YTD\s+TONNAGE\s+REPORT|TONNAGE\s+REPORT', text, re.IGNORECASE):
        return []

    # Format: "02/28/25 TRASH SERVICE 1.00 221.450 $221.45"
    # Also: "02/28/25 CONTAINER SERVICE 1.00 $11.85"
    # Also: "02/28/25 PROCESSING FEE 1.00 $7.06"
    svc_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?P<desc>(?:TRASH|CONTAINER|PROCESSING|RECYCLING|ROLL\s*OFF|FRONT\s*LOAD|COMPACTOR|'
        r'DUMPSTER|DELIVERY|HAUL|DISPOSAL|PICKUP|YARD\s*WASTE|ORGANIC|FOOD\s*WASTE|'
        r'LEASE|SWITCH|\d+YD\s)[\w\s\-.]+?)\s+'
        r'(?P<qty>[\d.]+)\s+[\d.]*\s*\$(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip()
        if any(w in desc.upper() for w in ['PAYMENT', 'PMT', 'TOTAL']):
            continue
        qty = _clean_qty(m.group('qty'))
        items.append(ChargeItem(
            charge_description=desc,
            qty=qty if qty and qty != 1.0 else None,
            amount=_clean_amount(m.group('amount')),
            raw_text=m.group(0)))
        found.add(desc.upper())

    # Fee lines without date: "BUS. COMPLIANCE $28.79"
    fee_pat = re.compile(
        r'(?P<desc>(?:BUS\.?\s*COMPLIANCE|FUEL|ENVIRONMENTAL|ENERGY|ADMIN|REGULATORY|FRANCHISE)\s*'
        r'(?:SURCHARGE|FEE|CHARGE)?)\s+\$(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in fee_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(charge_description=desc, amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))
            found.add(desc.upper())

    return items


# =============================================================================
# EDCO DISPOSAL
# =============================================================================

def _extract_edco(text: str) -> List[ChargeItem]:
    items = []

    # EDCO format: "$20 X30 DAYS RENT 600.00" or "$20 x31 DAYS oo. i oe 690 00"
    # Date prefix is garbled, amounts may have OCR artifacts
    rent_pat = re.compile(
        r'\$(?P<rate>\d+)\s*[xX×]\s*(?P<qty>\d+)\s*DAYS[\w\s.,]*?\s+(?P<amount>[\d\s,]+\.[\s\d]+)',
        re.IGNORECASE)
    for m in rent_pat.finditer(text):
        qty = _clean_qty(m.group('qty'))
        rate = _clean_amount(m.group('rate'))
        # Clean OCR-garbled amount (e.g., "690 00" -> "690.00", "620.00" -> "620.00")
        amount_str = re.sub(r'\s+', '', m.group('amount'))
        amt = _clean_amount(amount_str)
        items.append(ChargeItem(
            charge_description="Daily Rental",
            qty=qty,
            amount=amt,
            unit_price=rate,
            raw_text=m.group(0)))

    # Current charges line as additional data
    curr = re.search(r'CURRENT\s+CHARGES:\s*(?P<amount>[\d,]+\.?\d*)', text, re.IGNORECASE)
    if curr and not items:
        items.append(ChargeItem(
            charge_description="Current Charges",
            amount=_clean_amount(curr.group('amount')),
            raw_text=curr.group(0)))

    return items


# =============================================================================
# CITY OF OXNARD
# =============================================================================

def _extract_city_of_oxnard(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<desc>(?:CR|CM|FL|RL|RO)\s+\d+\s*(?:YD|GAL)\s+[\w\s]+?(?:X\d+)?)\s+'
        r'(?:\d{1,2}/\d{1,2}/\d{2,4}\s+to\s+\d{1,2}/\d{1,2}/\d{2,4}\s+)?'
        r'(?P<rate>[\d,]+\.?\d*)\s+(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(),
                                amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    if not items:
        tot = re.search(r'Total\s+Current\s+Charges\s*\$?\s*(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(charge_description="Total Current Charges", amount=_clean_amount(tot.group('amt')), raw_text=tot.group(0)))

    return items


# =============================================================================
# MODERN DISPOSAL (+ MODERN DISPOSAL SERVICES)
# =============================================================================

def _extract_modern_disposal(text: str) -> List[ChargeItem]:
    items = []

    # Sub-items: "3.79 - DC Trash - $58.00"
    if 'WO#' in text or 'W.O.' in text or 'Work Order' in text:
        sub_pat = re.compile(
            r'(?P<qty>[\d.]+)\s*-\s*(?P<desc>[\w\s\-/&]+?)\s*-\s*\$(?P<rate>[\d,]+\.?\d{2})', re.IGNORECASE)
        for m in sub_pat.finditer(text):
            qty = _clean_qty(m.group('qty'))
            desc = m.group('desc').strip()
            rate = _clean_amount(m.group('rate'))
            if any(w in desc.upper() for w in ['DISPOSAL', 'TRASH', 'DEBRIS', 'MSW', 'RECYCL']):
                amount = round(qty * rate, 2) if qty and rate else rate
            else:
                amount = rate
            items.append(ChargeItem(charge_description=desc, qty=qty, amount=amount, unit_price=rate, raw_text=m.group(0)))

    # Service line: "08/01/25 - 08/31/25 1 - Description - $378.35 PO# 105111 $378.35"
    svc_pat = re.compile(
        r'\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s+'
        r'(?P<qty>\d+)\s*-\s*(?P<desc>[\w\s\-/&,]+?)\s*-?\s*'
        r'\$?(?P<rate>[\d,]+\.?\d*)\s+(?:PO#?\s*\d+\s+)?'
        r'\$?(?P<amount>[\d,]+\.?\d{2})', re.IGNORECASE)
    found = {i.charge_description.upper() for i in items}
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip().rstrip('-').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(charge_description=desc, qty=_clean_qty(m.group('qty')),
                                    amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))
            found.add(desc.upper())

    # Percentage surcharges
    pct_pat = re.compile(
        r'(?P<desc>(?:ENVIRONMENTAL|FUEL|ENERGY|ADMIN|REGULATORY)\s*'
        r'(?:REGULATORY\s*)?(?:FEE|SURCHARGE|CHARGE))\s+(?P<pct>[\d.]+)%\s+\$?(?P<amount>[\d,]+\.?\d{2})', re.IGNORECASE)
    for m in pct_pat.finditer(text):
        items.append(ChargeItem(charge_description=f"{m.group('desc').strip()} {m.group('pct')}%",
                                amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))

    return items


# =============================================================================
# ACE RECYCLING
# =============================================================================

def _extract_ace_recycling(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s+'
        r'(?P<desc>[\w\s\-/&]+?)\s+(?P<qty>[\d.]+)\s+\$?\s*(?P<rate>[\d,]+\.?\d*)\s+'
        r'(?:per\s+month\s+)?(?P<amount>-?[\d,]+\.?\d{2})', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip()
        if not any(w in desc.upper() for w in ['TAX', 'TOTAL', 'BALANCE', 'PAYMENT', 'ACH']):
            items.append(ChargeItem(charge_description=desc, qty=_clean_qty(m.group('qty')),
                                    amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    return items


# =============================================================================
# WASTE MASTERS
# =============================================================================

def _extract_waste_masters(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'\d{1,2}\s*-\s*\w{3}\s*\|?\s*(?P<desc>Monthly\s+Svc:?\s*[\w\s\-/&]+?)\s+'
        r'\$(?P<rate>[\d,]+\.?\d*)\s+(?P<qty>[\d.]+)\s+\$(?P<amount>[\d,]+\.?\d{2})', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), qty=_clean_qty(m.group('qty')),
                                amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    fee_pat = re.compile(
        r'(?P<desc>(?:FUEL|ENVIRONMENTAL|ENERGY|ADMIN|REGULATORY)\s*(?:SURCHARGE|FEE|CHARGE)[\w\s]*?)\s+\$(?P<amount>[\d,]+\.?\d{2})', re.IGNORECASE)
    for m in fee_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))

    return items


# =============================================================================
# VANDERLIND / CONTAINER RENTALS
# =============================================================================

def _extract_vanderlind(text: str) -> List[ChargeItem]:
    items = []

    # Format: "5/9 Compactor Pull In: Apr 23 1 300.00 300.00"
    # Also: "5/9 FS - FuelSurcharge In: Apr 23 1 15.95 15.95"
    # Also: "5/9 TippingFee Weight: 2.92 2.92 55.00 160.60"
    # Also: "5/9 CompDlyRental 16 12.16 194.56"
    # Also: "5/9 40ydCanPull In: Apr 25 1 200.00 200.00"
    # Also: "5/18 Daily Rental SC-0095 since Apr 18, 1 65.00 65.00"
    # Format: "5/9 Compactor Pull In: Apr 23 1 300.00 300.00" (qty rate amount)
    # Also: "3/27. Daily Rental SC-0019 since Feb 25, 2025 1 65.00" (qty amount only)
    # Also: "2/6 40ydCanPull In: Jan 22 - SWAP - Customer Name 200.00 200.00" (no qty)
    svc_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2})\.?\s+'
        r'(?P<desc>(?:Compactor\s*Pull|CompDlyRental|TippingFee|FS|EPA|DEQ|'
        r'Fuel\s*Surcharge|Environmental|Daily\s*Rental|Container|Haul|Delivery|Removal|'
        r'Disposal|Roll\s*Off|Dumpster|\d+yd\w+Pull|30ydCanPull|40ydCanPull)[\w\s\-:.,]*?)\s+'
        r'(?P<qty>[\d.]+)\s+(?P<rate>[\d,]+\.\d{2})\s+(?P<amount>[\d,]+\.\d{2})\s*$',
        re.IGNORECASE | re.MULTILINE)
    for m in svc_pat.finditer(text):
        desc = re.sub(r',?\s*\d{4}$', '', m.group('desc').strip()).strip()
        # Normalize abbreviated descriptions
        desc_clean = desc
        for abbrev, full in [('CompDlyRental', 'Compactor Daily Rental'),
                             ('FS - FuelSurcharge', 'Fuel Surcharge'),
                             ('EPA - DEQ Environmental Fee', 'Environmental Fee')]:
            if abbrev.lower() in desc.lower():
                desc_clean = full
                break
        qty = _clean_qty(m.group('qty'))
        items.append(ChargeItem(
            charge_description=desc_clean,
            qty=qty if qty and qty != 1.0 else None,
            amount=_clean_amount(m.group('amount')),
            unit_price=_clean_amount(m.group('rate')),
            raw_text=m.group(0)))

    # Fallback: 2-number pattern (no qty) or single-amount daily rental
    found = {i.raw_text for i in items}
    two_num = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2})\.?\s+'
        r'(?P<desc>(?:Compactor\s*Pull|CompDlyRental|TippingFee|FS|EPA|DEQ|'
        r'Fuel\s*Surcharge|Environmental|Daily\s*Rental|Container|Haul|Delivery|Removal|'
        r'Disposal|Roll\s*Off|Dumpster|\d+yd\w+Pull|30ydCanPull|40ydCanPull)[\w\s\-:.,]*?)\s+'
        r'(?P<amount>[\d,]+\.\d{2})\s*$',
        re.IGNORECASE | re.MULTILINE)
    for m in two_num.finditer(text):
        if m.group(0) in found:
            continue
        desc = re.sub(r',?\s*\d{4}$', '', m.group('desc').strip()).strip()
        desc_clean = desc
        for abbrev, full in [('CompDlyRental', 'Compactor Daily Rental'),
                             ('FS - FuelSurcharge', 'Fuel Surcharge'),
                             ('EPA - DEQ Environmental Fee', 'Environmental Fee')]:
            if abbrev.lower() in desc.lower():
                desc_clean = full
                break
        items.append(ChargeItem(
            charge_description=desc_clean,
            amount=_clean_amount(m.group('amount')),
            raw_text=m.group(0)))

    return items


# =============================================================================
# PARISH DISPOSAL
# =============================================================================

def _extract_parish(text: str) -> List[ChargeItem]:
    items = []

    # Format: "6 8 yd dumpster 8yd service 2x wk 265.00 1,590.00"
    # Also: "1 delivered 30-149 10/01/2024 02/24/2025 350.00 350.00"
    # Also: "2 MSW tonnage fees 60.00 120.00"
    # Also: "1 Inactivity 60 days- fee 150.00 150.00"

    # Look for lines after "Charges" header: QTY DESCRIPTION RATE AMOUNT
    charges_section = text
    charges_idx = text.find('Charges')
    if charges_idx >= 0:
        charges_section = text[charges_idx:]

    # Primary: QTY DESCRIPTION [dates/item#] RATE AMOUNT
    # Use MULTILINE anchor to prevent qty from crossing line boundaries
    svc_pat = re.compile(
        r'^(?P<qty>\d+)\s+'
        r'(?P<desc>(?:\d+\s*(?:yd|yard|gal)\s*)?(?:dumpster\s+)?'
        r'[\w\s\-/]+?(?:service|dumpster|container|pickup|haul|disposal|rental|'
        r'wk|week|month|delivered|tonnage|fee|inactivity)[\w\s\-]*?)\s+'
        r'(?P<rate>[\d,]+\.\d{2})\s+(?P<amount>[\d,]+\.\d{2})',
        re.IGNORECASE | re.MULTILINE)
    for m in svc_pat.finditer(charges_section):
        desc = m.group('desc').strip()
        if any(w in desc.upper() for w in ['BALANCE', 'TOTAL', 'PAYMENT', 'INVOICE', 'DATE']):
            continue
        # Remove embedded dates and item numbers from description
        desc_clean = re.sub(r'\d{1,2}/\d{1,2}/\d{2,4}', '', desc).strip()
        desc_clean = re.sub(r'\b\d{2}-\d{3}\b', '', desc_clean).strip()
        desc_clean = re.sub(r'\s+', ' ', desc_clean)
        if len(desc_clean) > 3:
            qty = _clean_qty(m.group('qty'))
            items.append(ChargeItem(
                charge_description=desc_clean,
                qty=qty if qty and qty != 1.0 else None,
                amount=_clean_amount(m.group('amount')),
                unit_price=_clean_amount(m.group('rate')),
                raw_text=m.group(0)))

    # Fallback: QTY DESCRIPTION AMOUNT (no unit rate column)
    if not items:
        simple_pat = re.compile(
            r'^(?P<qty>\d+)\s+(?P<desc>[\w\s\-]+?(?:service|wk|week|month|dumpster|pickup|haul|disposal|rental|fee)[\w\s]*?)\s+'
            r'(?P<amount>[\d,]+\.\d{2})',
            re.IGNORECASE | re.MULTILINE)
        for m in simple_pat.finditer(charges_section):
            desc = m.group('desc').strip()
            if any(w in desc.upper() for w in ['BALANCE', 'TOTAL', 'PAYMENT', 'INVOICE', 'DATE']):
                continue
            if len(desc) > 3:
                qty = _clean_qty(m.group('qty'))
                items.append(ChargeItem(
                    charge_description=desc,
                    qty=qty if qty and qty != 1.0 else None,
                    amount=_clean_amount(m.group('amount')),
                    raw_text=m.group(0)))

    return items


# =============================================================================
# UNIQUE SANITATION
# =============================================================================

def _extract_unique_sanitation(text: str) -> List[ChargeItem]:
    items = []

    # Format: "04/17/25 1.00 | 8 YD CONTAINER CARDBOARD 48.00 48.00"
    svc_pat = re.compile(
        r'\d{1,2}/\d{1,2}/\d{2,4}\s+'
        r'(?P<qty>[\d.]+)\s*\|?\s*'
        r'(?P<desc>(?:\d+\s*(?:YD|YARD|GAL)\s+)?(?:CONTAINER|DUMPSTER|SERVICE|CART)[\w\s\-]+?)\s+'
        r'(?P<rate>[\d,]+\.\d{2})\s+(?P<amount>[\d,]+\.\d{2})\s*$', re.IGNORECASE | re.MULTILINE)
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip()
        if len(desc) > 5 and 'TOTAL' not in desc.upper():
            items.append(ChargeItem(charge_description=desc, qty=_clean_qty(m.group('qty')),
                                    amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    if not items:
        tot = re.search(r'(?:Total|Amount\s+Due)\s*:?\s*\$?(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(charge_description="Total", amount=_clean_amount(tot.group('amt')), raw_text=tot.group(0)))

    return items


# =============================================================================
# CHECK SAMMY
# =============================================================================

def _extract_check_sammy(text: str) -> List[ChargeItem]:
    items = []

    # Standard format: "desc qty $rate $tax $total"
    # "30 Yard Open Top - Initial Haul - C&D 1.00 $1,110.00 $0.00 $1,110.00"
    broad_pat = re.compile(
        r'(?P<desc>(?:\d+\s*Yard|Commercial|Residential)[\w\s\-/&#]+?)\s+'
        r'(?P<qty>[\d.]+)\s+\$(?P<rate>[\d,]+\.?\d*)\s+\$[\d,]+\.?\d*\s+\$(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in broad_pat.finditer(text):
        desc = m.group('desc').strip()
        if any(w in desc.upper() for w in ['TOTAL', 'SUB', 'PAID']):
            continue
        items.append(ChargeItem(charge_description=desc, qty=_clean_qty(m.group('qty')),
                                amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    svc_pat = re.compile(
        r'(?P<desc>(?:Commercial|Residential)\s+(?:Junk\s+Removal|Bulk\s+Pickup|Mattress|E-?Waste|Recycling)[\w\s\-#]*?)\s+'
        r'(?P<qty>\d+)\s+\$(?P<rate>[\d,]+\.?\d*)\s+\$(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    found = {i.charge_description.upper() for i in items}
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip()
        if desc.upper() not in found:
            items.append(ChargeItem(charge_description=desc, qty=_clean_qty(m.group('qty')),
                                    amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    trip_pat = re.compile(
        r'(?P<desc>(?:Late\s+Cancellation\s+)?Trip\s+Fee[\w\s]*)\s+'
        r'(?P<qty>\d+)\s+\$(?P<rate>[\d,]+\.?\d*)\s+\$(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in trip_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), qty=_clean_qty(m.group('qty')),
                                amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    if not items:
        tot = re.search(r'Total\s*\$(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(charge_description="Total", amount=_clean_amount(tot.group('amt')), raw_text=tot.group(0)))

    return items


# =============================================================================
# THE ARC
# =============================================================================

def _extract_the_arc(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<qty>\d+)\s+(?P<desc>Administrative[\w\s]+|Waste[\w\s]+|Recycling[\w\s]+)\s+'
        r'\$(?P<rate>[\d,]+\.?\d*)\s+\$(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), qty=_clean_qty(m.group('qty')),
                                amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    # Stacked column format - description on one line, amounts on another
    # "Administrative Services (March)\n...\nAmount\n\n$999.00"
    if not items:
        desc_match = re.search(r'(?P<desc>Administrative\s+Services[\w\s()]*|Waste\s+[\w\s]+|Recycling\s+[\w\s]+)', text, re.IGNORECASE)
        amt_match = re.search(r'(?:TOTAL|Amount)\s*\n+\s*\$(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if desc_match and amt_match:
            items.append(ChargeItem(
                charge_description=desc_match.group('desc').strip(),
                amount=_clean_amount(amt_match.group('amt')),
                raw_text=f"{desc_match.group(0)} {amt_match.group(0)}"))

    if not items:
        tot = re.search(r'(?:Total|TOTAL|Amount)\s*\n+\s*\$(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(charge_description="Total", amount=_clean_amount(tot.group('amt')), raw_text=tot.group(0)))

    return items


# =============================================================================
# NATIONAL WASTE SERVICES
# =============================================================================

def _extract_national_waste(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+(?P<desc>Monthly[\w\s]+(?:Service|Recycling)[\w\s]*?)\s+'
        r'(?P<qty>\d+)\s+(?P<rate>[\d,]+\.?\d*)\s+(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), qty=_clean_qty(m.group('qty')),
                                amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    return items


# =============================================================================
# 1-800-GOT-JUNK
# =============================================================================

def _extract_got_junk(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<desc>(?:Dry\s+Run|Minimum\s+Load|Quarter\s+Load|Half\s+Load|'
        r'Three\s+Quarter|Full\s+Load|Junk\s+Removal|Item\s+Removal)[\w\s\-]*?)\s+'
        r'(?P<qty>\d+)\s+\$(?P<rate>[\d,]+\.?\d*)\s+\$(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), qty=_clean_qty(m.group('qty')),
                                amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    if not items:
        tot = re.search(r'(?:Sub\s*Total|Total)\s*:?\s*\$(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(charge_description="Total", amount=_clean_amount(tot.group('amt')), raw_text=tot.group(0)))

    return items


# =============================================================================
# EASCO BROKERAGE
# =============================================================================

def _extract_easco(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+(?P<ref>\d+)\s+'
        r'(?P<desc>[\w\s.]+?)\s+(?P<qty>[\d,]+)\s+(?P<rate>[\d.]+)\s+(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), qty=_clean_qty(m.group('qty')),
                                amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    if not items:
        tot = re.search(r'TOTAL\s+[\d,]+\s+([\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(charge_description="Total", amount=_clean_amount(tot.group(1)), raw_text=tot.group(0)))

    return items


# =============================================================================
# RP WASTE / CONTRACTORS CHOICE
# =============================================================================

def _extract_rp_waste(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<desc>[\w\s\-/&,]+?(?:container|dumpster|haul|disposal|swap|delivery|rental|pull|tonnage|service|fee|surcharge|charge)[\w\s]*?)\s+'
        r'(?P<qty>\d+)\s+\$?(?P<rate>[\d,]+\.?\d*)\s+(?:[\d.]+%\s+)?\$?(?P<amount>[\d,]+\.?\d{2})', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip()
        if not any(w in desc.upper() for w in ['SUBTOTAL', 'TOTAL', 'BALANCE']):
            items.append(ChargeItem(charge_description=desc, qty=_clean_qty(m.group('qty')),
                                    amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    return items


# =============================================================================
# 121 DISPOSAL
# =============================================================================

def _extract_121_disposal(text: str) -> List[ChargeItem]:
    items = []
    found = set()

    # New format: "11/12/2025 108145506, Dump and Return Roll Off Per Job 1.00 284.00 284.00"
    # Also: "11/12/2025 JOB145506, Processing/Disposal, C&D Tons 0.21 48.00 10.08"
    new_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
        r'(?:\w+,\s*)?'
        r'(?P<desc>(?:Dump|Haul|Delivery|Removal|Pull|Swap|Processing|Disposal|Rental|'
        r'Environmental|Container|Roll\s*Off|Service)[\w\s/,\-&]+?)\s+'
        r'(?P<qty>[\d.]+)\s+(?P<rate>[\d,]+\.?\d*)\s+(?P<amount>[\d,]+\.?\d*)',
        re.IGNORECASE)
    for m in new_pat.finditer(text):
        desc = m.group('desc').strip().rstrip(',').strip()
        if any(w in desc.upper() for w in ['SUBTOTAL', 'TOTAL', 'BALANCE']):
            continue
        key = f"{m.group('date')}_{desc}"
        if key not in found:
            qty = _clean_qty(m.group('qty'))
            items.append(ChargeItem(
                charge_description=desc,
                qty=qty if qty and qty != 1.0 else None,
                amount=_clean_amount(m.group('amount')),
                unit_price=_clean_amount(m.group('rate')),
                raw_text=m.group(0)))
            found.add(key)

    # Old format: "Rental 40 YD Closed Top PerMonth- -PO#NA MSW 45.00"
    if not items:
        old_pat = re.compile(
            r'(?P<desc>(?:Rental|Haul|Disposal|Delivery|Removal|Pull|Swap|Service|Container|Processing)[\w\s\-/&,#.()]+?)\s+'
            r'(?P<amount>\d[\d,]+\.?\d{2})\s*$',
            re.MULTILINE | re.IGNORECASE)
        for m in old_pat.finditer(text):
            desc = m.group('desc').strip()
            if not any(w in desc.upper() for w in ['SUBTOTAL', 'TOTAL', 'BALANCE', 'PREVIOUS', 'CURRENT']):
                items.append(ChargeItem(
                    charge_description=desc,
                    amount=_clean_amount(m.group('amount')),
                    raw_text=m.group(0)))

    return items


# =============================================================================
# MASTER PAC SERVICES
# =============================================================================

def _extract_master_pac(text: str) -> List[ChargeItem]:
    items = []

    parts_pat = re.compile(
        r'(?P<desc>(?:Parts|Hinges|Welding|Cable|Motor|Hydraulic|Cylinder)[\w\s]*?)=?\s*\$(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in parts_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), amount=_clean_amount(m.group('amount')), raw_text=m.group(0)))

    labor_pat = re.compile(
        r'(?P<desc>Travel|Labor):\s*(?:(?P<qty>[\d.]+)\s*(?:hours?\s*@\s*)?\$?(?P<rate>[\d,]+\.?\d*)\s*=?\s*)?\$?(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in labor_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), qty=_clean_qty(m.group('qty')),
                                amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    if not items:
        tot = re.search(r'Amount\s+Due\s*\(?USD\)?\s*:?\s*\$(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(charge_description="Amount Due", amount=_clean_amount(tot.group('amt')), raw_text=tot.group(0)))

    return items


# =============================================================================
# PSI WASTE EQUIPMENT
# =============================================================================

def _extract_psi_waste(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<desc>(?:Travel|Service|Labor|Parts|Repair|Inspection|Maintenance|'
        r'PM\s+Compactor|Diagnostic)[\w\s\-\[\]().]+?)\s+'
        r'(?P<qty>\d+)\s+(?P<rate>[\d,]+\.?\d*)\s+(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip()
        if len(desc) > 3:
            items.append(ChargeItem(charge_description=desc, qty=_clean_qty(m.group('qty')),
                                    amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    return items


# =============================================================================
# ATLANTIC WASTE / MID-ATLANTIC
# =============================================================================

def _extract_atlantic_waste(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<desc>(?:PM\s+Compactor|Inspection|Labor|Travel|Parts|Fuel|'
        r'Hauling|Disposal|Service|Repair|Maintenance)[\w\s\-]+?)\s+'
        r'(?P<qty>[\d.]+)\s+\$?(?P<rate>[\d,]+\.?\d*)\s+\$?(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        desc = m.group('desc').strip()
        if len(desc) > 3 and 'TOTAL' not in desc.upper():
            items.append(ChargeItem(charge_description=desc, qty=_clean_qty(m.group('qty')),
                                    amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    if not items:
        tot = re.search(r'(?:Invoice\s+Total|TOTAL)\s*:?\s*\$?(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(charge_description="Invoice Total", amount=_clean_amount(tot.group('amt')), raw_text=tot.group(0)))

    return items


# =============================================================================
# C&M TOPSOIL
# =============================================================================

def _extract_cm_topsoil(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<qty>\d+)\s+(?:CY|YD|EA)\s+(?P<desc>(?:BIN\s+RENTAL|DISPOSAL|HAULING|DELIVERY)[\w\s()]+?)\s+'
        r'(?P<rate>[\d,]+\.?\d*)\s+(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), qty=_clean_qty(m.group('qty')),
                                amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    if not items:
        desc_pat = re.compile(r'(?P<desc>(?:\d+\s*(?:CY|YD)\s+)?(?:BIN|CONTAINER)\s+RENTAL[\w\s()]*)', re.IGNORECASE)
        for m in desc_pat.finditer(text):
            items.append(ChargeItem(charge_description=m.group('desc').strip(), raw_text=m.group(0)))

    return items


# =============================================================================
# MOMENTUM RECYCLING
# =============================================================================

def _extract_momentum_recycling(text: str) -> List[ChargeItem]:
    items = []

    svc_pat = re.compile(
        r'(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+'
        r'(?P<desc>(?:Fuel\s+Surcharge|Container|1st\s+Container|Additional\s+Container|'
        r'Glass\s+Pod[\w\s]*|Food\s+Waste[\w\s]*|Recycling[\w\s]*)[^\n]*?)\s+'
        r'(?P<qty>[\d.]+)\s+\$(?P<rate>[\d,]+\.?\d*)\s+\$(?P<amount>[\d,]+\.?\d*)', re.IGNORECASE)
    for m in svc_pat.finditer(text):
        items.append(ChargeItem(charge_description=m.group('desc').strip(), qty=_clean_qty(m.group('qty')),
                                amount=_clean_amount(m.group('amount')), unit_price=_clean_amount(m.group('rate')), raw_text=m.group(0)))

    if not items:
        tot = re.search(r'Total:\s*\$(?P<amt>[\d,]+\.?\d*)', text, re.IGNORECASE)
        if tot:
            items.append(ChargeItem(charge_description="Total", amount=_clean_amount(tot.group('amt')), raw_text=tot.group(0)))

    return items


# =============================================================================
# DISPATCHER
# =============================================================================

VENDOR_EXTRACTORS: dict[str, Callable[[str], List[ChargeItem]]] = {
    'waste management': _extract_waste_management,
    'usa waste': _extract_usa_waste,
    "cockey's": _extract_cockeys,
    'cockey': _extract_cockeys,
    'robinson waste': _extract_robinson,
    'robinson': _extract_robinson,
    'athens services': _extract_athens,
    'athens': _extract_athens,
    'burgmeier': _extract_burgmeiers,
    'veit': _extract_veit,
    'waste disposal': _extract_waste_disposal,
    'aspen waste': _extract_aspen,
    'republic services': _extract_republic,
    'republic': _extract_republic,
    'universal waste': _extract_universal_waste,
    'rumpke': _extract_rumpke,
    'casella': _extract_casella,
    'meridian waste': _extract_meridian,
    'meridian': _extract_meridian,
    'mark dunning': _extract_mdi,
    'mdi': _extract_mdi,
    'jamaica ash': _extract_jamaica_ash,
    'kmg hauling': _extract_kmg,
    'kmg': _extract_kmg,
    'wb waste': _extract_wb_waste,
    'waste pro': _extract_waste_pro,
    'local waste solution': _extract_local_waste,
    'local waste': _extract_local_waste,
    'tate services': _extract_tate,
    'tate': _extract_tate,
    'sbc waste': _extract_sbc_waste,
    'edco': _extract_edco,
    'city of oxnard': _extract_city_of_oxnard,
    'oxnard': _extract_city_of_oxnard,
    'parish disposal': _extract_parish,
    'parish': _extract_parish,
    'unique sanitation': _extract_unique_sanitation,
    'check sammy': _extract_check_sammy,
    'checksammy': _extract_check_sammy,
    'the arc': _extract_the_arc,
    'national waste': _extract_national_waste,
    'got-junk': _extract_got_junk,
    'got junk': _extract_got_junk,
    '1-800-got': _extract_got_junk,
    'easco': _extract_easco,
    'container rentals': _extract_vanderlind,
    'vanderlind': _extract_vanderlind,
    'modern disposal services': _extract_modern_disposal,
    'modern disposal': _extract_modern_disposal,
    'ace recycling': _extract_ace_recycling,
    'waste masters': _extract_waste_masters,
    'rp waste': _extract_rp_waste,
    'contractors choice': _extract_rp_waste,
    '121 disposal': _extract_121_disposal,
    'waste connections': _extract_waste_connections,
    'master pac': _extract_master_pac,
    'masterpac': _extract_master_pac,
    'psi waste': _extract_psi_waste,
    'atlantic waste': _extract_atlantic_waste,
    'mid-atlantic': _extract_atlantic_waste,
    'c&m topsoil': _extract_cm_topsoil,
    'c & m topsoil': _extract_cm_topsoil,
    'topsoil': _extract_cm_topsoil,
    'momentum recycling': _extract_momentum_recycling,
}


def _find_extractor(vendor: str) -> Optional[Callable[[str], List[ChargeItem]]]:
    """Find extractor for vendor using substring matching."""
    vendor_lower = vendor.lower().strip()
    for key in sorted(VENDOR_EXTRACTORS.keys(), key=len, reverse=True):
        if key in vendor_lower:
            return VENDOR_EXTRACTORS[key]
    return None


def extract_charges(vendor: str, ocr_text: str) -> List[ChargeItem]:
    """Extract charge line items from raw OCR text for the given vendor."""
    if not ocr_text or not vendor:
        return []
    text = _normalize_ocr_text(ocr_text)
    extractor = _find_extractor(vendor)
    if extractor:
        return extractor(text)
    return []


def get_vendor_count() -> int:
    """Return number of unique vendor extractors configured."""
    return len(set(VENDOR_EXTRACTORS.values()))


def get_configured_vendors() -> List[str]:
    """Return list of vendor match keys."""
    return sorted(VENDOR_EXTRACTORS.keys())
