"""Momentum Recycling charge extraction.

Format (hierarchical categories):
    Category:Subcategory:Item, Details
    DATE  Description  QTY  UNIT_PRICE  TOTAL
    e.g. "Recycling Collection:Food Waste:64 Gallon Cart, Food Waste, Additional Container"
    e.g. "8/26/2025 Container 5.00 $12.25 $61.25"
    e.g. "Recycling Collection:Glass:Glass Pod Recycling Cart, Additional Container"
    e.g. "8/19/2025 Container 3.00 $15.00 $45.00"
    Also: "Fuel Surcharge" with $0.00 amounts.
"""

import re
from typing import List
from ..models import ChargeItem


def extract_momentum_recycling(text: str) -> List[ChargeItem]:
    """Extract charge items from Momentum Recycling invoice OCR text."""
    items = []

    # Parse category headers and their following line items
    # Category format: "Category:SubCategory:Item, Details"
    current_category = None

    lines = text.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()

        # Check for category header (contains colons in hierarchy pattern)
        cat_match = re.match(
            r'((?:Recycling|Collection|Fuel|Container)[\w\s]*:'
            r'[\w\s]*:?[\w\s,]*)',
            line, re.IGNORECASE
        )
        if cat_match:
            current_category = cat_match.group(1).strip()
            continue

        # Check for item line: "DATE DESCRIPTION QTY $RATE $TOTAL"
        item_match = re.match(
            r'\d{1,2}/\d{1,2}/\d{4}\s+'
            r'([\w\s,]+?)\s+'
            r'(\d+\.?\d*)\s+'
            r'\$?([\d,]+\.?\d*)\s+'
            r'\$?([\d,]+\.\d{2})',
            line
        )
        if item_match:
            desc = item_match.group(1).strip()
            qty = float(item_match.group(2))
            rate = float(item_match.group(3).replace(',', ''))
            amount = float(item_match.group(4).replace(',', ''))

            # Include category context in description
            if current_category:
                full_desc = f"{current_category} - {desc}"
            else:
                full_desc = desc

            if amount > 0:
                items.append(ChargeItem(
                    charge_description=full_desc,
                    amount=amount,
                    qty=qty if qty != 1.0 else None,
                    unit_price=rate,
                    raw_text=line
                ))

    # Fuel surcharge (may be $0.00 - skip if zero)
    fuel_match = re.search(
        r'Fuel\s+Surcharge.*?\$?([\d,]+\.\d{2})',
        text, re.IGNORECASE
    )
    if fuel_match:
        amount = float(fuel_match.group(1).replace(',', ''))
        if amount > 0:
            items.append(ChargeItem(
                charge_description='Fuel Surcharge',
                amount=amount,
                raw_text=fuel_match.group(0).strip()
            ))

    return items
