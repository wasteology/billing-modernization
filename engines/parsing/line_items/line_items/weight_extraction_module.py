"""
Weight Extraction Module
========================

Extracts actual tonnage from invoice line items for on-call services
(Open Top, Compactor, Roll-Off).

Business Rule: On-call services are always weighed at destination facility.
The weight appears on the invoice and should be extracted, not calculated.

Reference: 05_line_item_weight_extraction_INSTRUCTIONS.md

Usage:
    from weight_extraction_module import extract_weight

    result = extract_weight(
        vendor='Waste Management',
        description='30YD OPEN TOP - 2.45 TONS MSW',
        raw_ocr=None  # Optional: full invoice OCR text
    )
    # Returns: {'weight_tons': 2.45, 'weight_source': 'actual'}
"""

import re
from typing import Dict, Optional, Tuple, List

# =============================================================================
# GENERIC WEIGHT PATTERNS (ordered by specificity)
# =============================================================================

WEIGHT_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Net weight in POUNDS (check first to avoid partial match)
    (re.compile(r'NET\s*(?:WEIGHT|WT)[:.\s]*(\d{1,3}(?:,\d{3})*|\d+)\s*(?:LBS?|POUNDS?)', re.IGNORECASE), 'lbs'),

    # Net weight in TONS (most reliable - always use this if present)
    (re.compile(r'NET\s*(?:WEIGHT|WT|TONS?)[:.\s]*(\d+\.?\d*)\s*(?:TONS?|T)?', re.IGNORECASE), 'tons'),

    # Tonnage/Disposal charge format
    (re.compile(r'(?:TONNAGE|DISPOSAL)\s*(?:CHARGE)?[:.\s-]*(\d+\.?\d*)\s*(?:TONS?|T)', re.IGNORECASE), 'tons'),

    # "Tons:" label format
    (re.compile(r'TONS?[:.\s]+(\d+\.?\d+)', re.IGNORECASE), 'tons'),

    # Weight @ rate format (e.g., "2.45 TONS @ $50/TON")
    (re.compile(r'(\d+\.?\d+)\s*(?:TONS?|T)\s*@', re.IGNORECASE), 'tons'),

    # Decimal + TONS with or without space (e.g., "3.0900Tons" or "3.09 Tons")
    (re.compile(r'(\d+\.\d+)\s*TONS?(?:\s|$|[,.]|[A-Z])', re.IGNORECASE), 'tons'),

    # DecimalTons - no space, 4 decimal places (Republic format: "3.0900Tons")
    (re.compile(r'(\d+\.\d{2,4})Tons?\b', re.IGNORECASE), 'tons'),

    # Decimal + T (standalone, require decimal)
    (re.compile(r'(\d+\.\d+)\s*T\b(?!\w)', re.IGNORECASE), 'tons'),

    # Integer TONS (only if explicitly "TONS" spelled out)
    (re.compile(r'(\d+)\s+TONS(?:\s|$)', re.IGNORECASE), 'tons'),

    # Pounds format (will convert to tons)
    (re.compile(r'(?:NET\s*)?(?:WEIGHT)?[:.\s]*(\d{1,3}(?:,\d{3})*|\d{3,})\s*(?:LBS?|POUNDS?)(?:\s|$)', re.IGNORECASE), 'lbs'),
]

# Patterns to EXCLUDE (avoid false positives)
EXCLUDE_PATTERNS = [
    re.compile(r'(\d+)\s*YD', re.IGNORECASE),  # Container size
    re.compile(r'(\d+)\s*YARD', re.IGNORECASE),  # Container size
    re.compile(r'(\d+)\s*GAL', re.IGNORECASE),  # Gallon containers
    re.compile(r'\$\s*(\d+\.?\d*)', re.IGNORECASE),  # Dollar amounts
]


# =============================================================================
# VENDOR-SPECIFIC PATTERNS
# =============================================================================

WM_PATTERNS = {
    'tons_label': re.compile(r'TONS?[:.\s]+(\d+\.?\d+)', re.IGNORECASE),
    'net_tons': re.compile(r'NET\s*(?:TONS?|WT)[:.\s]*(\d+\.?\d*)', re.IGNORECASE),
    'disposal': re.compile(r'DISPOSAL.*?(\d+\.?\d+)\s*(?:TONS?|T)', re.IGNORECASE),
}

REPUBLIC_PATTERNS = {
    # Republic often uses "3.0900Tons" format without space
    'decimal_tons_nospace': re.compile(r'(\d+\.\d{2,4})Tons?\b', re.IGNORECASE),
    'net_weight': re.compile(r'NET\s*WEIGHT[:.\s]*(\d+\.?\d*)\s*TONS?', re.IGNORECASE),
    'tons_at_rate': re.compile(r'(\d+\.?\d+)\s*(?:TONS?|T)\s*@', re.IGNORECASE),
    'tonnage': re.compile(r'TONNAGE[:.\s]*(\d+\.?\d+)', re.IGNORECASE),
}

WASTE_CONNECTIONS_PATTERNS = {
    'tons_field': re.compile(r'TONS[:.\s]+(\d+\.?\d+)', re.IGNORECASE),
    'tons_rate': re.compile(r'(\d+\.?\d+)\s*(?:TONS?)\s*(?:@|RATE)', re.IGNORECASE),
    'inline': re.compile(r'(?:HAUL|PULL).*?(\d+\.?\d+)\s*(?:TONS?|T)', re.IGNORECASE),
}

ATHENS_PATTERNS = {
    'tonnage': re.compile(r'TONNAGE[:.\s]*(\d+\.?\d+)', re.IGNORECASE),
    'tons_label': re.compile(r'TONS[:.\s]+(\d+\.?\d+)', re.IGNORECASE),
    'net': re.compile(r'NET[:.\s]*(\d+\.?\d+)\s*(?:TONS?)?', re.IGNORECASE),
}

RUMPKE_PATTERNS = {
    'tons_rate': re.compile(r'(\d+\.?\d+)\s*TONS?\s*@', re.IGNORECASE),
    'tons_label': re.compile(r'TONS[:.\s]+(\d+\.?\d+)', re.IGNORECASE),
    'inline': re.compile(r'(?:RO|ROLL\s*OFF).*?(\d+\.?\d+)\s*(?:TONS?|T)', re.IGNORECASE),
}

COCKEYS_PATTERNS = {
    'tonnage': re.compile(r'TONNAGE[:.\s]*(\d+\.?\d+)', re.IGNORECASE),
    'tons': re.compile(r'(\d+\.?\d+)\s*TONS?', re.IGNORECASE),
}

GFL_PATTERNS = {
    'tons_label': re.compile(r'TONS[:.\s]+(\d+\.?\d+)', re.IGNORECASE),
    'net': re.compile(r'NET[:.\s]*(\d+\.?\d+)', re.IGNORECASE),
    'tons_at': re.compile(r'(\d+\.?\d+)\s*(?:TONS?|T)\s*@', re.IGNORECASE),
}

CASELLA_PATTERNS = {
    'tons': re.compile(r'(\d+\.?\d+)\s*TONS?', re.IGNORECASE),
    'tonnage': re.compile(r'TONNAGE[:.\s]*(\d+\.?\d+)', re.IGNORECASE),
}


# =============================================================================
# EXTRACTION FUNCTIONS
# =============================================================================

def normalize_weight(value: float, unit: str) -> float:
    """
    Normalize weight to tons.

    Args:
        value: Numeric weight value
        unit: 'tons' or 'lbs'

    Returns:
        Weight in tons (rounded to 3 decimal places)
    """
    if unit == 'lbs':
        return round(value / 2000.0, 3)
    return round(value, 3)


def validate_weight(weight: float) -> bool:
    """
    Validate extracted weight is reasonable.

    Typical ranges for on-call services:
    - Open Top 20YD: 1-8 tons
    - Open Top 30YD: 2-12 tons
    - Open Top 40YD: 3-15 tons
    - Compactor: 2-20 tons

    Args:
        weight: Extracted weight in tons

    Returns:
        True if weight is within reasonable range
    """
    if weight <= 0:
        return False
    if weight > 50:  # Unreasonably high for single haul
        return False
    if weight < 0.05:  # Unreasonably low (100 lbs)
        return False
    return True


def is_false_positive(text: str, match_start: int, match_end: int) -> bool:
    """
    Check if a weight match is likely a false positive.

    Args:
        text: Full text being searched
        match_start: Start position of match
        match_end: End position of match

    Returns:
        True if likely false positive
    """
    # Get context around match
    context_start = max(0, match_start - 10)
    context_end = min(len(text), match_end + 10)
    context = text[context_start:context_end].upper()

    # Check for container size indicators
    if 'YD' in context or 'YARD' in context:
        # Could be container size, not weight
        # But allow if "TONS" is explicit
        if 'TON' not in context:
            return True

    # Check for dollar amounts
    if '$' in context:
        return True

    return False


def extract_with_patterns(
    text: str,
    patterns: Dict[str, re.Pattern]
) -> Optional[float]:
    """
    Try multiple patterns to extract weight.

    Args:
        text: Text to search
        patterns: Dictionary of named patterns

    Returns:
        Extracted weight in tons, or None
    """
    for name, pattern in patterns.items():
        match = pattern.search(text)
        if match:
            try:
                weight_str = match.group(1).replace(',', '')
                weight = float(weight_str)

                # Check if this is a lbs pattern
                unit = 'lbs' if 'lbs' in name.lower() or 'pounds' in name.lower() else 'tons'
                weight = normalize_weight(weight, unit)

                if validate_weight(weight):
                    return weight
            except (ValueError, IndexError):
                continue

    return None


def extract_weight_generic(
    description: str,
    raw_ocr: Optional[str] = None
) -> Dict[str, Optional[float]]:
    """
    Generic weight extraction using common patterns.

    Args:
        description: Line item/charge description
        raw_ocr: Full OCR text of invoice (optional)

    Returns:
        {'weight_tons': float or None, 'weight_source': str}
    """
    result = {'weight_tons': None, 'weight_source': 'needs_weight'}

    # Search in description first, then raw_ocr
    search_texts = [description] if description else []
    if raw_ocr:
        search_texts.append(raw_ocr)

    for text in search_texts:
        if not text:
            continue

        for pattern, unit in WEIGHT_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    weight_str = match.group(1).replace(',', '')
                    weight = float(weight_str)
                    weight = normalize_weight(weight, unit)

                    # Validate and check for false positives
                    if validate_weight(weight):
                        if not is_false_positive(text, match.start(), match.end()):
                            result['weight_tons'] = weight
                            result['weight_source'] = 'actual'
                            return result
                except (ValueError, IndexError):
                    continue

    return result


def extract_weight_wm(
    description: str,
    raw_ocr: Optional[str] = None
) -> Dict[str, Optional[float]]:
    """Extract weight from Waste Management invoices."""
    result = {'weight_tons': None, 'weight_source': 'needs_weight'}

    # Try description first
    weight = extract_with_patterns(description or '', WM_PATTERNS)
    if weight:
        result['weight_tons'] = weight
        result['weight_source'] = 'actual'
        return result

    # Try raw OCR
    if raw_ocr:
        weight = extract_with_patterns(raw_ocr, WM_PATTERNS)
        if weight:
            result['weight_tons'] = weight
            result['weight_source'] = 'actual'
            return result

    # Fall back to generic
    return extract_weight_generic(description, raw_ocr)


def extract_weight_republic(
    description: str,
    raw_ocr: Optional[str] = None
) -> Dict[str, Optional[float]]:
    """Extract weight from Republic Services invoices."""
    result = {'weight_tons': None, 'weight_source': 'needs_weight'}

    weight = extract_with_patterns(description or '', REPUBLIC_PATTERNS)
    if weight:
        result['weight_tons'] = weight
        result['weight_source'] = 'actual'
        return result

    if raw_ocr:
        weight = extract_with_patterns(raw_ocr, REPUBLIC_PATTERNS)
        if weight:
            result['weight_tons'] = weight
            result['weight_source'] = 'actual'
            return result

    return extract_weight_generic(description, raw_ocr)


def extract_weight_waste_connections(
    description: str,
    raw_ocr: Optional[str] = None
) -> Dict[str, Optional[float]]:
    """Extract weight from Waste Connections invoices."""
    result = {'weight_tons': None, 'weight_source': 'needs_weight'}

    weight = extract_with_patterns(description or '', WASTE_CONNECTIONS_PATTERNS)
    if weight:
        result['weight_tons'] = weight
        result['weight_source'] = 'actual'
        return result

    if raw_ocr:
        weight = extract_with_patterns(raw_ocr, WASTE_CONNECTIONS_PATTERNS)
        if weight:
            result['weight_tons'] = weight
            result['weight_source'] = 'actual'
            return result

    return extract_weight_generic(description, raw_ocr)


def extract_weight_athens(
    description: str,
    raw_ocr: Optional[str] = None
) -> Dict[str, Optional[float]]:
    """Extract weight from Athens Services invoices."""
    result = {'weight_tons': None, 'weight_source': 'needs_weight'}

    weight = extract_with_patterns(description or '', ATHENS_PATTERNS)
    if weight:
        result['weight_tons'] = weight
        result['weight_source'] = 'actual'
        return result

    if raw_ocr:
        weight = extract_with_patterns(raw_ocr, ATHENS_PATTERNS)
        if weight:
            result['weight_tons'] = weight
            result['weight_source'] = 'actual'
            return result

    return extract_weight_generic(description, raw_ocr)


def extract_weight_rumpke(
    description: str,
    raw_ocr: Optional[str] = None
) -> Dict[str, Optional[float]]:
    """Extract weight from Rumpke invoices."""
    result = {'weight_tons': None, 'weight_source': 'needs_weight'}

    weight = extract_with_patterns(description or '', RUMPKE_PATTERNS)
    if weight:
        result['weight_tons'] = weight
        result['weight_source'] = 'actual'
        return result

    if raw_ocr:
        weight = extract_with_patterns(raw_ocr, RUMPKE_PATTERNS)
        if weight:
            result['weight_tons'] = weight
            result['weight_source'] = 'actual'
            return result

    return extract_weight_generic(description, raw_ocr)


def extract_weight_cockeys(
    description: str,
    raw_ocr: Optional[str] = None
) -> Dict[str, Optional[float]]:
    """Extract weight from Cockey's Enterprises invoices."""
    result = {'weight_tons': None, 'weight_source': 'needs_weight'}

    weight = extract_with_patterns(description or '', COCKEYS_PATTERNS)
    if weight:
        result['weight_tons'] = weight
        result['weight_source'] = 'actual'
        return result

    if raw_ocr:
        weight = extract_with_patterns(raw_ocr, COCKEYS_PATTERNS)
        if weight:
            result['weight_tons'] = weight
            result['weight_source'] = 'actual'
            return result

    return extract_weight_generic(description, raw_ocr)


def extract_weight_gfl(
    description: str,
    raw_ocr: Optional[str] = None
) -> Dict[str, Optional[float]]:
    """Extract weight from GFL invoices."""
    result = {'weight_tons': None, 'weight_source': 'needs_weight'}

    weight = extract_with_patterns(description or '', GFL_PATTERNS)
    if weight:
        result['weight_tons'] = weight
        result['weight_source'] = 'actual'
        return result

    if raw_ocr:
        weight = extract_with_patterns(raw_ocr, GFL_PATTERNS)
        if weight:
            result['weight_tons'] = weight
            result['weight_source'] = 'actual'
            return result

    return extract_weight_generic(description, raw_ocr)


def extract_weight_casella(
    description: str,
    raw_ocr: Optional[str] = None
) -> Dict[str, Optional[float]]:
    """Extract weight from Casella invoices."""
    result = {'weight_tons': None, 'weight_source': 'needs_weight'}

    weight = extract_with_patterns(description or '', CASELLA_PATTERNS)
    if weight:
        result['weight_tons'] = weight
        result['weight_source'] = 'actual'
        return result

    if raw_ocr:
        weight = extract_with_patterns(raw_ocr, CASELLA_PATTERNS)
        if weight:
            result['weight_tons'] = weight
            result['weight_source'] = 'actual'
            return result

    return extract_weight_generic(description, raw_ocr)


# =============================================================================
# MAIN DISPATCHER
# =============================================================================

def extract_weight(
    vendor: str,
    description: str,
    raw_ocr: Optional[str] = None
) -> Dict[str, Optional[float]]:
    """
    Extract weight from invoice for on-call services.

    Routes to vendor-specific extraction function based on vendor name,
    then falls back to generic extraction if needed.

    Args:
        vendor: Vendor name for routing to vendor-specific patterns
        description: Line item/charge description
        raw_ocr: Full OCR text of invoice (optional, for context search)

    Returns:
        {
            'weight_tons': float or None,
            'weight_source': 'actual' | 'needs_weight'
        }

    Examples:
        >>> extract_weight('Waste Management', '30YD OPEN TOP - 2.45 TONS MSW')
        {'weight_tons': 2.45, 'weight_source': 'actual'}

        >>> extract_weight('Republic', 'Open Top Haul', 'Net Weight: 3.2 Tons')
        {'weight_tons': 3.2, 'weight_source': 'actual'}

        >>> extract_weight('Unknown', 'Container Rental')
        {'weight_tons': None, 'weight_source': 'needs_weight'}
    """
    if not vendor:
        return extract_weight_generic(description, raw_ocr)

    vendor_lower = vendor.lower().strip()

    # Route to vendor-specific extraction
    if 'waste management' in vendor_lower or vendor_lower.startswith('wm ') or vendor_lower == 'wm':
        return extract_weight_wm(description, raw_ocr)

    elif 'republic' in vendor_lower:
        return extract_weight_republic(description, raw_ocr)

    elif 'waste connections' in vendor_lower:
        return extract_weight_waste_connections(description, raw_ocr)

    elif 'athens' in vendor_lower:
        return extract_weight_athens(description, raw_ocr)

    elif 'rumpke' in vendor_lower:
        return extract_weight_rumpke(description, raw_ocr)

    elif 'cockey' in vendor_lower:
        return extract_weight_cockeys(description, raw_ocr)

    elif 'gfl' in vendor_lower:
        return extract_weight_gfl(description, raw_ocr)

    elif 'casella' in vendor_lower:
        return extract_weight_casella(description, raw_ocr)

    # Fall back to generic extraction
    return extract_weight_generic(description, raw_ocr)


# =============================================================================
# TESTING
# =============================================================================

if __name__ == '__main__':
    # Test cases
    test_cases = [
        # (vendor, description, raw_ocr, expected_weight)
        ('Waste Management', '30YD OPEN TOP - 2.45 TONS MSW', None, 2.45),
        ('Waste Management', 'DISPOSAL CHARGE', 'Tons: 3.200\nRate: $50/Ton', 3.2),
        ('Republic Services', 'Open Top Haul', 'Net Weight: 4.89 Tons', 4.89),
        ('Waste Connections', 'TONS: 2.45 @ $52/TON', None, 2.45),
        ('Athens Services', 'Roll Off Service', 'Tonnage: 5.12', 5.12),
        ('Rumpke', '30YD RO/HAUL - 2.45 TONS @ $48/TON', None, 2.45),
        ('Unknown Vendor', '30YD OPEN TOP - 3.5 TONS', None, 3.5),
        ('Unknown Vendor', 'Container Rental', None, None),
        # Pounds conversion
        ('Generic', 'Disposal', 'Net Weight: 4,900 LBS', 2.45),
        # Edge cases
        ('Test', '30YD container', None, None),  # Should NOT extract 30 as weight
        ('Test', '$50.00 charge', None, None),  # Should NOT extract dollar amount
    ]

    print("Weight Extraction Module - Test Results")
    print("=" * 60)

    passed = 0
    failed = 0

    for vendor, desc, ocr, expected in test_cases:
        result = extract_weight(vendor, desc, ocr)
        actual = result['weight_tons']

        if actual == expected or (expected and actual and abs(actual - expected) < 0.01):
            status = "PASS"
            passed += 1
        else:
            status = "FAIL"
            failed += 1

        print(f"\n{status}: {vendor}")
        print(f"  Description: {desc[:50]}...")
        if ocr:
            print(f"  OCR: {ocr[:50]}...")
        print(f"  Expected: {expected}, Got: {actual}")
        print(f"  Source: {result['weight_source']}")

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
