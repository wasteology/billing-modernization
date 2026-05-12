"""C&M Topsoil charge extraction.

Format (summary only):
    SITE  QTY  U/M  DESCRIPTION  PRICE  AMOUNT
    e.g. "40 CY BIN RENTAL (WOOD WASTE) ONLY"
    Very simple - often just a description with no structured table.
"""

import re
from typing import List
from ..models import ChargeItem


def extract_cm_topsoil(text: str) -> List[ChargeItem]:
    """Extract charge items from C&M Topsoil invoice OCR text."""
    items = []

    # Look for description lines near "DESCRIPTION PRICE AMOUNT" header
    # e.g. "40 CY BIN RENTAL (WOOD WASTE) ONLY"
    item_pattern = re.compile(
        r'(\d+\s*(?:CY|YD|YARD|TON)\s+[\w\s\-/&()]+?)\s*$',
        re.MULTILINE | re.IGNORECASE
    )

    for m in item_pattern.finditer(text):
        desc = m.group(1).strip()
        if len(desc) > 5:
            items.append(ChargeItem(
                charge_description=desc,
                raw_text=m.group(0).strip()
            ))

    # Try to find amount from invoice total if no structured line items
    if not items:
        # Look for any service description
        desc_match = re.search(
            r'((?:BIN|CONTAINER|DUMPSTER|ROLL\s*OFF|RENTAL|HAULING|'
            r'DISPOSAL|DELIVERY|TOPSOIL|WOOD|DEBRIS|CONCRETE|DIRT)'
            r'[\w\s\-/&()]*)',
            text, re.IGNORECASE
        )
        total_match = re.search(
            r'(?:AMOUNT|TOTAL|PRICE)\s*\n?\s*\$?([\d,]+\.\d{2})',
            text, re.IGNORECASE
        )

        if desc_match:
            amount = float(total_match.group(1).replace(',', '')) if total_match else None
            items.append(ChargeItem(
                charge_description=desc_match.group(1).strip(),
                amount=amount,
                raw_text=desc_match.group(0).strip()
            ))

    return items
