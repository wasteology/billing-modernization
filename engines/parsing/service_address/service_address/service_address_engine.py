"""
Service Address Extraction Engine v1.0
Extracts service/site addresses from invoice OCR text.

Designed to work with vendor_detection_module.py as part of deterministic
invoice matching pipeline.

Usage:
    1. First detect vendor using vendor_detection_module.detect_vendor()
    2. Then extract address using extract_service_address(vendor_name, text)

DETERMINISTIC RULES:
- Each vendor has explicit extraction logic
- Returns address dict OR None (no guessing)
- Pattern must match exactly or extraction fails

Returns dict with keys: street, city, state, postal_code
This matches the location table structure (address, city, region, postal_code).

Maintained by: Wasteology
Last updated: March 2026
"""
import re
from typing import Optional, Dict, Any, List


# ============================================================
# VENDOR ADDRESS CONFIGURATIONS
# ============================================================

VENDOR_ADDRESSES: Dict[str, Dict[str, Any]] = {}


# ============================================================
# SHARED HELPERS
# ============================================================

# US state abbreviations for validation
_US_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
    'DC', 'PR', 'VI', 'GU',
}


_US_STATE_NAMES = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
    'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
    'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID',
    'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
    'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
    'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
    'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV',
    'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
    'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK',
    'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
    'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT',
    'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV',
    'wisconsin': 'WI', 'wyoming': 'WY', 'district of columbia': 'DC',
}


def _parse_city_state_zip(text: str) -> Optional[Dict[str, str]]:
    """Parse 'City, ST 12345' or 'CITY ST 12345' into components.

    Handles:
        - City, ST 12345
        - City, ST 12345-6789
        - CITY ST 12345
        - City , ST  12345  (extra spaces)
        - City, StateName 12345 (full state names)
    """
    # Standard 2-letter state code (handles "City, ST 12345" and "City, ST, 12345")
    m = re.search(
        r'([A-Za-z][A-Za-z\s\.]+?)\s*,?\s+([A-Z]{2})\s*,?\s+(\d{5}(?:-\d{4})?)',
        text,
    )
    if m and m.group(2) in _US_STATES:
        return {
            'city': m.group(1).strip().title(),
            'state': m.group(2),
            'postal_code': m.group(3),
        }

    # Full state name: "City, StateName 12345"
    m = re.search(
        r'([A-Za-z][A-Za-z\s\.]+?)\s*,\s+([A-Za-z][A-Za-z\s]+?)\s+(\d{5}(?:-\d{4})?)',
        text,
    )
    if m:
        state_name = m.group(2).strip().lower()
        if state_name in _US_STATE_NAMES:
            return {
                'city': m.group(1).strip().title(),
                'state': _US_STATE_NAMES[state_name],
                'postal_code': m.group(3),
            }

    return None


def _parse_city_state(text: str) -> Optional[Dict[str, str]]:
    """Parse 'City, ST' or 'City, StateName' WITHOUT zip code.

    Used when zip appears on a separate line.
    """
    t = text.strip().rstrip(',')

    # 2-letter state code: "City, ST"
    m = re.match(r'([A-Za-z][A-Za-z\s\.]+?)\s*,\s+([A-Z]{2})\s*$', t)
    if m and m.group(2) in _US_STATES:
        return {'city': m.group(1).strip().title(), 'state': m.group(2)}

    # Full state name: "City, StateName"
    m = re.match(r'([A-Za-z][A-Za-z\s\.]+?)\s*,\s+([A-Za-z][A-Za-z\s]+?)\s*$', t)
    if m:
        state_name = m.group(2).strip().lower()
        if state_name in _US_STATE_NAMES:
            return {'city': m.group(1).strip().title(), 'state': _US_STATE_NAMES[state_name]}

    return None


def _build_address_dict(
    street: str,
    city_state_zip: str = None,
    city: str = None,
    state: str = None,
    postal_code: str = None,
) -> Optional[Dict[str, str]]:
    """Build a normalized address dict from components.

    Can accept either a combined city_state_zip string (parsed automatically)
    or individual city/state/postal_code values.
    """
    if not street or not street.strip():
        return None

    result = {'street': street.strip()}

    if city_state_zip:
        parsed = _parse_city_state_zip(city_state_zip)
        if parsed:
            result.update(parsed)
        else:
            return None  # couldn't parse city/state/zip
    else:
        if city:
            result['city'] = city.strip().title()
        if state:
            result['state'] = state.strip().upper()
        if postal_code:
            result['postal_code'] = postal_code.strip()

    return result


def _normalize_text(text: str) -> str:
    """Normalize OCR text: convert literal \\n to newlines."""
    if not text:
        return ''
    return text.replace('\\n', '\n')


def _lines(text: str) -> list[str]:
    """Split text into lines, handling both real and literal newlines."""
    return _normalize_text(text).split('\n')


# ============================================================
# GENERIC LABEL-BASED EXTRACTOR
# ============================================================

def _extract_labeled_address(
    text: str,
    labels: list[str],
    skip_lines: int = 0,
    max_search_lines: int = 6,
) -> Optional[Dict[str, str]]:
    """Generic extractor for vendors that use a labeled address block.

    Looks for a label line (e.g., "Service Address"), then reads the next
    few lines to find street + city/state/zip.

    Args:
        text: Raw OCR text
        labels: List of label patterns to look for (case-insensitive)
        skip_lines: Lines to skip after label (e.g., 1 to skip a name line)
        max_search_lines: Max lines to search after label for address components
    """
    lines = _lines(text)

    for i, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean:
            continue

        # Check if this line matches any label
        matched_label = None
        for label in labels:
            if re.search(label, line_clean, re.IGNORECASE):
                matched_label = label
                break
        if not matched_label:
            continue

        # Check for inline address on the label line itself
        # e.g., "Service Address: 123 Main St, City, ST 12345"
        # e.g., "Service Address: 123 Main St • City, ST 12345"
        # e.g., "Service Addr: 192 N BECK RD" (street only)
        for label in labels:
            m = re.search(label + r'\s*[:\-]?\s*(.+)', line_clean, re.IGNORECASE)
            if m:
                remainder = m.group(1).strip()
                # Clean bullet/dot separators
                remainder = re.sub(r'\s*[•·|]\s*', ', ', remainder)
                if remainder and re.match(r'\d+\s+\S', remainder):
                    # Try full city/state/zip on the same line
                    csz = _parse_city_state_zip(remainder)
                    if csz:
                        city_upper = csz['city'].upper()
                        rem_upper = remainder.upper()
                        idx = rem_upper.find(city_upper)
                        if idx > 0:
                            street_part = remainder[:idx].strip().rstrip(',')
                            if street_part:
                                return _build_address_dict(
                                    street_part,
                                    city=csz['city'],
                                    state=csz['state'],
                                    postal_code=csz['postal_code'],
                                )
                    # Street-only inline — look ahead for city/state/zip
                    inline_street = remainder
                    for k in range(i + 1, min(i + 4, len(lines))):
                        nxt = lines[k].strip()
                        if not nxt:
                            continue
                        csz2 = _parse_city_state_zip(nxt)
                        if csz2:
                            return _build_address_dict(inline_street, city_state_zip=nxt)
                        cs2 = _parse_city_state(nxt)
                        if cs2:
                            # Look for zip on line after
                            for kk in range(k + 1, min(k + 3, len(lines))):
                                zl = lines[kk].strip()
                                zm = re.match(r'^(\d{5}(?:-\d{4})?)\s*$', zl)
                                if zm:
                                    return _build_address_dict(
                                        inline_street,
                                        city=cs2['city'], state=cs2['state'],
                                        postal_code=zm.group(1),
                                    )
                                if zl:
                                    break
                            return _build_address_dict(
                                inline_street, city=cs2['city'], state=cs2['state'],
                            )
                        # Check if next line is a standalone state name
                        state_abbr = _US_STATE_NAMES.get(nxt.lower().strip())
                        if state_abbr:
                            # Look for zip after state
                            for kk in range(k + 1, min(k + 3, len(lines))):
                                zl = lines[kk].strip()
                                zm = re.match(r'^(\d{5}(?:-\d{4})?)\s*$', zl)
                                if zm:
                                    return _build_address_dict(
                                        inline_street, state=state_abbr,
                                        postal_code=zm.group(1),
                                    )
                                if zl:
                                    break
                            return _build_address_dict(inline_street, state=state_abbr)
                        break  # non-address line, return street only
                    return _build_address_dict(inline_street)
                break

        # Found label — scan next lines for street + city/state/zip
        street = None

        search_start = i + 1 + skip_lines
        for j in range(search_start, min(search_start + max_search_lines, len(lines))):
            candidate = lines[j].strip()
            if not candidate:
                continue

            # Try to parse as city/state/zip (with zip)
            csz = _parse_city_state_zip(candidate)
            if csz and street:
                return _build_address_dict(street, city_state_zip=candidate)

            # Try city/state WITHOUT zip — check next line for standalone zip
            if street and not csz:
                cs = _parse_city_state(candidate)
                if cs:
                    # Look ahead for zip on next line
                    for k in range(j + 1, min(j + 3, len(lines))):
                        zip_line = lines[k].strip()
                        zip_m = re.match(r'^(\d{5}(?:-\d{4})?)\s*$', zip_line)
                        if zip_m:
                            return _build_address_dict(
                                street,
                                city=cs['city'],
                                state=cs['state'],
                                postal_code=zip_m.group(1),
                            )
                        if zip_line:
                            break  # non-empty, non-zip line — stop looking
                    # Return with city/state but no zip
                    return _build_address_dict(
                        street, city=cs['city'], state=cs['state'],
                    )

            # Check if line looks like a street address (starts with number or PO Box)
            if not street and re.match(r'^\d+\s+\S', candidate):
                street = candidate
                # Check if city/state/zip is on the same line
                csz_inline = _parse_city_state_zip(candidate)
                if csz_inline:
                    city_upper = csz_inline['city'].upper()
                    rem_upper = candidate.upper()
                    idx = rem_upper.find(city_upper)
                    if idx > 0:
                        street_part = candidate[:idx].strip().rstrip(',')
                        if street_part:
                            return _build_address_dict(
                                street_part,
                                city=csz_inline['city'],
                                state=csz_inline['state'],
                                postal_code=csz_inline['postal_code'],
                            )
                # Check for inline city/state without zip (zip on next line)
                cs_inline = _parse_city_state(candidate)
                if cs_inline:
                    city_upper = cs_inline['city'].upper()
                    idx = candidate.upper().find(city_upper)
                    if idx > 0:
                        street_part = candidate[:idx].strip().rstrip(',')
                        if street_part:
                            # Look ahead for zip
                            for k in range(j + 1, min(j + 3, len(lines))):
                                zip_line = lines[k].strip()
                                zip_m = re.match(r'^(\d{5}(?:-\d{4})?)\s*$', zip_line)
                                if zip_m:
                                    return _build_address_dict(
                                        street_part,
                                        city=cs_inline['city'],
                                        state=cs_inline['state'],
                                        postal_code=zip_m.group(1),
                                    )
                                if zip_line:
                                    break
                            return _build_address_dict(
                                street_part,
                                city=cs_inline['city'],
                                state=cs_inline['state'],
                            )
                continue

            # P.O. Box
            if not street and re.match(r'^P\.?O\.?\s*Box', candidate, re.I):
                street = candidate
                continue

            # If we have a street, try parsing as city/state/zip anyway
            if street:
                csz = _parse_city_state_zip(candidate)
                if csz:
                    return _build_address_dict(street, city_state_zip=candidate)

            # Standalone zip after street (no city/state line between)
            if street:
                zip_m = re.match(r'^(\d{5}(?:-\d{4})?)\s*$', candidate)
                if zip_m:
                    return _build_address_dict(street, postal_code=zip_m.group(1))

        # Exhausted search lines — return street-only if we found one
        if street:
            return _build_address_dict(street)

    return None


# ============================================================
# VENDOR-SPECIFIC EXTRACTION FUNCTIONS
# ============================================================

# --- Basin Disposal ---
def _extract_basin_disposal(text: str) -> Optional[Dict[str, str]]:
    """Basin Disposal: Name + street appear after the billing address block.

    Format (no city/state/zip for service address):
        WASTEOLOGY
        3939 SHELBYVILLE RD STE 301
        LOUISVILLE KY 40207-3103
        BIO LIFE
        7430 WRIGLEY DR

    The service address is the street line after the second name block
    (after the Wasteology billing address). No city/state/zip available,
    so we can't do structured matching. Try labeled first as fallback.
    """
    # Try labeled address (some Basin invoices might have it)
    result = _extract_labeled_address(
        text,
        labels=[r'Service\s+Address'],
        skip_lines=1,
    )
    if result:
        return result

    # Basin-specific: find street after the billing address block
    # Look for the pattern: after LOUISVILLE KY 40207, next name + street
    lines = _lines(text)
    for i, line in enumerate(lines):
        if re.search(r'LOUISVILLE\s+KY\s+4020', line, re.I):
            # Next non-empty lines should be service name + street
            found_name = False
            for j in range(i + 1, min(i + 5, len(lines))):
                candidate = lines[j].strip()
                if not candidate or candidate.upper().startswith('DATE'):
                    break
                if not found_name:
                    found_name = True  # skip the name line
                    continue
                # This should be the street
                if re.match(r'^\d+\s+\S', candidate):
                    # No city/state/zip available — return street-only
                    # with partial info from invoice header
                    return {'street': candidate}
            break

    return None

VENDOR_ADDRESSES['Basin Disposal'] = {
    'has_address': True,
    'label': 'After billing block',
    'examples': ['7430 WRIGLEY DR'],
    'extract': _extract_basin_disposal,
}


# --- Waste Connections ---
def _extract_waste_connections(text: str) -> Optional[Dict[str, str]]:
    """Waste Connections: 'Service Location' label → account → lines → name → street."""
    return _extract_labeled_address(
        text,
        labels=[r'Service\s+Location', r'Service\s+Address'],
        skip_lines=0,
    )

VENDOR_ADDRESSES['Waste Connections'] = {
    'has_address': True,
    'label': 'Service Location',
    'examples': ['1234 Industrial Blvd, Dallas, TX 75201'],
    'extract': _extract_waste_connections,
}


# --- Robinson Waste ---
def _extract_robinson_waste(text: str) -> Optional[Dict[str, str]]:
    """Robinson Waste: Multi-site invoices with (NNNN) blocks.

    Format:
        (0002)
        WEBER UTAH SOUTH #52
        10 WEST YOUNG STREET

    Extracts the FIRST site's street address. No city/state/zip in OCR.
    """
    # Try labeled first
    result = _extract_labeled_address(
        text,
        labels=[r'Job\s*Site\s*:', r'Service\s+Location'],
    )
    if result:
        return result

    # Robinson-specific: find first (NNNN) block → name → street
    lines = _lines(text)
    for i, line in enumerate(lines):
        if re.match(r'^\s*\(0{0,2}\d{1,4}\)\s*$', line.strip()):
            # Found a site block marker — next lines are name + street
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j].strip()
                if not candidate:
                    continue
                # Look for a street address line (starts with number)
                if re.match(r'^\d+\s+\S', candidate):
                    return {'street': candidate}
            break  # only extract first site

    return None

VENDOR_ADDRESSES['Robinson Waste'] = {
    'has_address': True,
    'label': 'Site block (NNNN)',
    'examples': ['10 WEST YOUNG STREET'],
    'extract': _extract_robinson_waste,
}


# --- AMWASTE ---
def _extract_amwaste(text: str) -> Optional[Dict[str, str]]:
    """Amwaste: Embedded format — (NNNN) NAME\\nSTREET CITY, ST ZIP
    or labeled Service Address.
    """
    # Try labeled first
    result = _extract_labeled_address(
        text,
        labels=[r'Service\s+Address', r'Service\s+Location', r'Site\s+Address'],
    )
    if result:
        return result

    # Try embedded pattern: (NNNN) or #NNNN followed by name then address
    lines = _lines(text)
    for i, line in enumerate(lines):
        if re.match(r'^\s*[\(#]\d{3,5}[\)]\s', line):
            # Next lines should be street + city/state/zip
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j].strip()
                if re.match(r'^\d+\s+\S', candidate):
                    # Found street line, look for city/state/zip
                    csz_line = lines[j + 1].strip() if j + 1 < len(lines) else ''
                    csz = _parse_city_state_zip(csz_line)
                    if csz:
                        return _build_address_dict(candidate, city_state_zip=csz_line)
                    # Maybe city/state/zip is on same line
                    csz = _parse_city_state_zip(candidate)
                    if csz:
                        street_part = re.split(
                            r'\s+[A-Z]{2}\s+\d{5}', candidate
                        )[0].rsplit(',', 1)[0].strip()
                        if street_part:
                            return _build_address_dict(
                                street_part,
                                city=csz['city'],
                                state=csz['state'],
                                postal_code=csz['postal_code'],
                            )
    return None

VENDOR_ADDRESSES['Amwaste'] = {
    'has_address': True,
    'label': 'Embedded / Service Address',
    'examples': ['(4401) Store Name, 123 Main St, City, ST 12345'],
    'extract': _extract_amwaste,
}


# --- EDCO Disposal ---
def _extract_edco_disposal(text: str) -> Optional[Dict[str, str]]:
    """EDCO Disposal: 'FOR SERVICE AT:' → name → street → city state zip.

    Format:
        FOR SERVICE AT:
        LDS CHURCH
        15100 E CORDOVA ROAD
        LA MIRADA CA 90638

    Note: city/state/zip has NO comma between city and state.
    """
    lines = _lines(text)

    for i, line in enumerate(lines):
        if re.search(r'FOR\s+SERVICE\s+AT\s*:', line, re.I):
            # Next lines: name, then street, then city (maybe separate from state zip)
            street = None
            city_candidate = None
            for j in range(i + 1, min(i + 8, len(lines))):
                candidate = lines[j].strip()
                if not candidate:
                    continue

                # Skip known non-address lines
                if re.match(r'^Account\s+Number', candidate, re.I):
                    break

                # Try to parse as city/state/zip (combined line)
                csz = _parse_city_state_zip(candidate)
                if csz and street:
                    return _build_address_dict(
                        street,
                        city=csz['city'],
                        state=csz['state'],
                        postal_code=csz['postal_code'],
                    )

                # Check for state+zip only line (e.g., "CA 90620")
                # This happens when city is on a separate line
                state_zip = re.match(r'^([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$', candidate)
                if state_zip and state_zip.group(1) in _US_STATES and street:
                    return _build_address_dict(
                        street,
                        city=city_candidate,
                        state=state_zip.group(1),
                        postal_code=state_zip.group(2),
                    )

                # Street line starts with a number
                if not street and re.match(r'^\d+\s+\S', candidate):
                    street = candidate
                    continue

                # If we have a street but no city/state/zip yet, this might be the city
                if street and not city_candidate:
                    # Could be city name (all caps, no digits)
                    if re.match(r'^[A-Z][A-Za-z\s]+$', candidate):
                        city_candidate = candidate.strip().title()
                        continue

            break  # only check first "FOR SERVICE AT"

    # Fallback to generic labels
    return _extract_labeled_address(
        text,
        labels=[r'Service\s+Address', r'Service\s+Location'],
    )

VENDOR_ADDRESSES['EDCO Disposal'] = {
    'has_address': True,
    'label': 'FOR SERVICE AT:',
    'examples': ['15100 E CORDOVA ROAD, LA MIRADA, CA 90638'],
    'extract': _extract_edco_disposal,
}


# --- Ace Recycling ---
def _extract_ace_recycling(text: str) -> Optional[Dict[str, str]]:
    """Ace Recycling: 'Site XXXXXX - Name - Street City State Zip' inline format
    or labeled Service Address.
    """
    # Try inline Site reference pattern
    m = re.search(
        r'Site\s+\d+\s*-\s*[^-]+\s*-\s*(\d+\s+[^,]+),\s*([A-Za-z\s]+),?\s+([A-Z]{2})\s+(\d{5})',
        text,
    )
    if m:
        return _build_address_dict(
            m.group(1).strip(),
            city=m.group(2).strip(),
            state=m.group(3),
            postal_code=m.group(4),
        )

    # Try labeled
    return _extract_labeled_address(
        text,
        labels=[r'Service\s+Address', r'Site\s+Address', r'Service\s+Location'],
    )

VENDOR_ADDRESSES['Ace Recycling'] = {
    'has_address': True,
    'label': 'Site reference / Service Address',
    'examples': ['Site 801916 - Benihana - 123 Main St, San Diego, CA 92101'],
    'extract': _extract_ace_recycling,
}


# --- Woody & Sons Disposal ---
def _extract_woody_sons(text: str) -> Optional[Dict[str, str]]:
    """Woody & Sons: Name + street + city state zip block after header.

    Format:
        LONG JOHN SILVERS
        788 MAPLE VALLEY DR
        FARMINGTON, MO 63640

    Appears after Due Date / Amount Due header lines.
    Also look for "@ STREET" inline reference.
    """
    # Try inline "@ STREET" pattern first
    m = re.search(
        r'@\s+(\d+\s+[A-Z][A-Z\s]+?(?:DR|RD|ST|AVE|BLVD|LN|CT|WAY|CIR|PL|PKWY|HWY))\b',
        text,
        re.I,
    )
    if m:
        street = m.group(1).strip()
        # Look for city/state/zip near this match
        pos = m.end()
        remaining = text[pos:pos + 200]
        csz = _parse_city_state_zip(remaining)
        if csz:
            return _build_address_dict(
                street,
                city=csz['city'],
                state=csz['state'],
                postal_code=csz['postal_code'],
            )

    # Try labeled
    result = _extract_labeled_address(
        text,
        labels=[r'Service\s+Address', r'Service\s+Location'],
    )
    if result:
        return result

    # Woody-specific: find the address block after header info
    # Look for street address followed by city, ST ZIP after the amounts
    lines = _lines(text)
    for i, line in enumerate(lines):
        if re.search(r'Amount\s+Due|Due\s+Date', line, re.I):
            # Scan next lines for a street address
            for j in range(i + 1, min(i + 8, len(lines))):
                candidate = lines[j].strip()
                if re.match(r'^\d+\s+\S', candidate):
                    # Found street, look for city/state/zip on next line
                    if j + 1 < len(lines):
                        csz = _parse_city_state_zip(lines[j + 1].strip())
                        if csz:
                            return _build_address_dict(
                                candidate,
                                city=csz['city'],
                                state=csz['state'],
                                postal_code=csz['postal_code'],
                            )
            break

    return None

VENDOR_ADDRESSES["Woody & Sons Disposal"] = {
    'has_address': True,
    'label': 'After header / @ inline',
    'examples': ['788 MAPLE VALLEY DR, FARMINGTON, MO 63640'],
    'extract': _extract_woody_sons,
}


# --- Standard Waste ---
def _extract_standard_waste(text: str) -> Optional[Dict[str, str]]:
    """Standard Waste: 'Site:ACCOUNT' label then street + city state zip.

    Format:
        Site:UPS-NJBAY
        400 PORT LINCOLN ROAD
        BAYONNE, NJ 07002
    """
    # Standard Waste specific: "Site:ACCOUNT\nSTREET\nCITY, ST ZIP"
    # Street may start with digit+letter like "16E CHIMNEY ROCK RD"
    lines = _lines(text)
    for i, line in enumerate(lines):
        if re.match(r'^\s*Site\s*:', line, re.I):
            # Next lines should be street + city/state/zip
            for j in range(i + 1, min(i + 5, len(lines))):
                candidate = lines[j].strip()
                if re.match(r'^\d+\S*\s+\S', candidate):
                    if j + 1 < len(lines):
                        csz = _parse_city_state_zip(lines[j + 1].strip())
                        if csz:
                            return _build_address_dict(
                                candidate,
                                city=csz['city'],
                                state=csz['state'],
                                postal_code=csz['postal_code'],
                            )
            break  # only check first Site:

    # Fallback to generic labels
    return _extract_labeled_address(
        text,
        labels=[r'Service\s+Address', r'Service\s+Location'],
    )

VENDOR_ADDRESSES['Standard Waste'] = {
    'has_address': True,
    'label': 'Site:',
    'examples': ['400 PORT LINCOLN ROAD, BAYONNE, NJ 07002'],
    'extract': _extract_standard_waste,
}


# --- Pueblo of Zuni ---
VENDOR_ADDRESSES['Pueblo of Zuni'] = {
    'has_address': False,
    'label': None,
    'examples': [],
    'extract': lambda text: None,
}

# --- White Mountain Apache ---
VENDOR_ADDRESSES['White Mountain Apache'] = {
    'has_address': False,  # Only location names (church names), no street addresses
    'label': None,
    'examples': [],
    'extract': lambda text: None,
}

# --- Dunham ---
VENDOR_ADDRESSES['Dunham'] = {
    'has_address': False,  # Bulk disposal invoices with PO# only, no service address
    'label': None,
    'examples': [],
    'extract': lambda text: None,
}

# --- Akat Scrap Metal ---
VENDOR_ADDRESSES['Akat Scrap Metal'] = {
    'has_address': False,  # Scrap metal pickups identified by site name only
    'label': None,
    'examples': [],
    'extract': lambda text: None,
}


# --- CR&R ---
def _extract_crr(text: str) -> Optional[Dict[str, str]]:
    """CR&R: 'Service Address' label then street + city state zip.

    Format:
        Account Number    Service Address
        93-00312437       9501 NORWALK BLVD
                          SANTA FE SPRING CA 90670

    The address appears after the 'Service Address' column header.
    """
    # Try labeled extraction first
    result = _extract_labeled_address(
        text,
        labels=[r'Service\s+Address'],
    )
    if result:
        return result

    # CR&R specific: OCR linearizes a tabular header into sequential lines:
    #   Account Number\nService Address\n...headers...\n93-00312437\n9501 NORWALK BLVD\nSANTA FE SPRING CA 90670
    # The street+city appear 8+ lines after the "Service Address" header.
    # Strategy: find account number (NN-NNNNNNNN), then next lines are street + city.
    lines = _lines(text)
    for i, line in enumerate(lines):
        if re.match(r'^\d{2}-\d{8}$', line.strip()):
            # Found account number — next lines should be street + city/state/zip
            street = None
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j].strip()
                if not candidate:
                    continue
                # Skip dates
                if re.match(r'^\d{2}/\d{2}/\d{2}', candidate):
                    break

                if not street and re.match(r'^\d+\s+\S', candidate):
                    street = candidate
                    continue

                if street:
                    csz = _parse_city_state_zip(candidate)
                    if csz:
                        return _build_address_dict(
                            street,
                            city=csz['city'],
                            state=csz['state'],
                            postal_code=csz['postal_code'],
                        )
            break

    return None

VENDOR_ADDRESSES['CR&R'] = {
    'has_address': True,
    'label': 'Service Address',
    'examples': ['9501 NORWALK BLVD, SANTA FE SPRING, CA 90670'],
    'extract': _extract_crr,
}


# --- Derby City Environmental ---
def _extract_derby_city(text: str) -> Optional[Dict[str, str]]:
    """Derby City: Inline 'Site: NAME, STREET CITY, ST ZIP'.

    Format:
        Site: Sewing and Vacuum Authority, 10494 Westport Road Louisville, KY 40241
    """
    # Match: Site: NAME, STREET, CITY, ST ZIP  or  Site: NAME, STREET CITY, ST ZIP
    m = re.search(
        r'Site\s*:\s*[^,]+,\s*(.+?),?\s+([A-Z]{2})\s+(\d{5})',
        text,
    )
    if m and m.group(2) in _US_STATES:
        # Split street from city: everything before last comma or last capitalized word group
        full_addr = m.group(1).strip()
        # Try splitting on last comma
        if ',' in full_addr:
            parts = full_addr.rsplit(',', 1)
            street = parts[0].strip()
            city = parts[1].strip()
        else:
            # No comma — split street from city by finding the last word group
            # that looks like a city name (e.g., "10494 Westport Road Louisville")
            # Greedy: city is the LAST capitalized word(s) before state
            addr_m = re.match(r'^(.+\S)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)$', full_addr)
            if addr_m:
                street = addr_m.group(1).strip()
                city = addr_m.group(2).strip()
            else:
                street = full_addr
                city = None
        return _build_address_dict(
            street,
            city=city,
            state=m.group(2),
            postal_code=m.group(3),
        )
        return _build_address_dict(
            m.group(1).strip(),
            city=m.group(2).strip(),
            state=m.group(3),
            postal_code=m.group(4),
        )

    # Fallback
    return _extract_labeled_address(
        text,
        labels=[r'Service\s+Address', r'Site\s+Address'],
    )

VENDOR_ADDRESSES['Derby City Environmental'] = {
    'has_address': True,
    'label': 'Site: inline',
    'examples': ['10494 Westport Road, Louisville, KY 40241'],
    'extract': _extract_derby_city,
}


# --- Clarke Waste Solutions ---
def _extract_clarke_waste(text: str) -> Optional[Dict[str, str]]:
    """Clarke Waste: address block after equipment listing.

    Format:
        UPS
        6707 North Basin Avenue
        Portland, OR 97217
    """
    result = _extract_labeled_address(
        text, labels=[r'Service\s+Address', r'Service\s+Location'],
    )
    if result:
        return result

    # Clarke-specific: service address appears just BEFORE "Subtotal"/"Job Total"
    # Pattern: UPS\n6707 North Basin Avenue\nPortland, OR 97217\nSubtotal
    lines = _lines(text)
    # Find Subtotal line, then scan backwards for street + city/state/zip
    subtotal_idx = None
    for i, line in enumerate(lines):
        if re.search(r'\b(?:Subtotal|Job\s+Total)\b', line, re.I):
            subtotal_idx = i
            break

    if subtotal_idx:
        # Scan backwards from Subtotal for city/state/zip + street
        for i in range(subtotal_idx - 1, max(subtotal_idx - 6, 0), -1):
            candidate = lines[i].strip()
            csz = _parse_city_state_zip(candidate)
            if csz and i > 0:
                # Previous line should be the street
                street_line = lines[i - 1].strip()
                if re.match(r'^\d+\s+\S', street_line):
                    return _build_address_dict(street_line, city_state_zip=candidate)
    return None

VENDOR_ADDRESSES['Clarke Waste Solutions'] = {
    'has_address': True,
    'label': 'After equipment block',
    'examples': ['6707 North Basin Avenue, Portland, OR 97217'],
    'extract': _extract_clarke_waste,
}


# --- Anytime Disposal Services ---
def _extract_anytime_disposal(text: str) -> Optional[Dict[str, str]]:
    """Anytime Disposal: address on description lines.

    Format (repeated for each service line):
        Undeliverable - 30 Yard CAD
        55 Glenlake Parkway Northeast Atlanta, GA 30328
        Jan 07, 2026
    """
    result = _extract_labeled_address(
        text, labels=[r'Service\s+Address', r'Service\s+Location'],
    )
    if result:
        return result

    # Suffix/directional pattern for splitting street from city
    _SUFFIXES = (
        r'(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|'
        r'Ln|Lane|Ct|Court|Way|Pl|Place|Pkwy|Parkway|Hwy|Highway|'
        r'Trl|Trail|Cir|Circle|NE|NW|SE|SW|'
        r'Northeast|Northwest|Southeast|Southwest|'
        r'North|South|East|West)'
    )

    lines = _lines(text)
    for line in lines:
        line_s = line.strip()
        if not line_s or not re.match(r'^\d', line_s):
            continue
        # Skip Wasteology billing
        if 'shelbyville' in line_s.lower():
            continue
        # Match: NUMBER ... , ST ZIP
        m = re.match(
            r'^(\d+\s+.+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s*$',
            line_s,
        )
        if not m or m.group(2) not in _US_STATES:
            continue
        before_state = m.group(1).strip()
        state = m.group(2)
        zip_code = m.group(3)
        # Split street from city using last street suffix/directional
        street_m = re.match(
            r'^(\d+\s+.+\b' + _SUFFIXES + r')\b\.?,?\s+(.+)',
            before_state,
            re.IGNORECASE,
        )
        if street_m:
            street = street_m.group(1).strip()
            city = street_m.group(2).strip()
            if not re.match(r'^\d', city):  # city shouldn't start with digit
                return _build_address_dict(
                    street, city=city, state=state, postal_code=zip_code,
                )
        # Fallback: try _parse_city_state_zip which handles comma-separated cities
        csz = _parse_city_state_zip(before_state + ', ' + state + ' ' + zip_code)
        if csz:
            city_upper = csz['city'].upper()
            idx = before_state.upper().rfind(city_upper)
            if idx > 0:
                street = before_state[:idx].strip().rstrip(',')
                if street:
                    return _build_address_dict(
                        street, city=csz['city'],
                        state=csz['state'], postal_code=csz['postal_code'],
                    )
    return None

VENDOR_ADDRESSES['Anytime Disposal Services'] = {
    'has_address': True,
    'label': 'Description line address',
    'examples': ['55 Glenlake Parkway Northeast Atlanta, GA 30328'],
    'extract': _extract_anytime_disposal,
}


# --- City of Mesa ---
def _extract_city_of_mesa(text: str) -> Optional[Dict[str, str]]:
    """City of Mesa: utility bill with service address after customer name.

    Format:
        WASTEOLOGY GROUP TRANSPORTATION, LLC
        7337 E GREENWAY ST
        Previous Payments & Balance...
    """
    lines = _lines(text)
    for i, line in enumerate(lines):
        if re.search(r'WASTEOLOGY\s+GROUP', line, re.I):
            # Next non-empty line should be the service street address
            for j in range(i + 1, min(i + 3, len(lines))):
                candidate = lines[j].strip()
                if not candidate:
                    continue
                if re.match(r'^\d+\s+\S', candidate):
                    # Skip Wasteology billing
                    if 'shelbyville' in candidate.lower():
                        break
                    return _build_address_dict(
                        candidate, city='Mesa', state='AZ',
                    )
                break
    return None

VENDOR_ADDRESSES['City of Mesa'] = {
    'has_address': True,
    'label': 'After customer name (utility bill)',
    'examples': ['7337 E GREENWAY ST, Mesa, AZ'],
    'extract': _extract_city_of_mesa,
}


# --- Tacoma Public Utilities ---
def _extract_tacoma_utilities(text: str) -> Optional[Dict[str, str]]:
    """Tacoma Public Utilities: service address in Description column.

    Format (OCR linearizes columns into separate lines):
        Description
        Quantity
        UM
        Net Price
        Net Amount
        5101 E 12th St
        EA
    """
    lines = _lines(text)
    # Find "Description" header, then scan for the first street address
    for i, line in enumerate(lines):
        if re.match(r'^\s*Description\s*$', line.strip(), re.I):
            # Scan next ~10 lines for first address-looking line
            for j in range(i + 1, min(i + 12, len(lines))):
                candidate = lines[j].strip()
                if not candidate:
                    continue
                if re.match(r'^\d+\s+[A-Za-z]', candidate):
                    # Skip Wasteology billing and utility office
                    cl = candidate.lower()
                    if 'shelbyville' in cl or 'market st' in cl:
                        continue
                    return _build_address_dict(
                        candidate, city='Tacoma', state='WA',
                    )
    return None

VENDOR_ADDRESSES['Tacoma Public Utilities'] = {
    'has_address': True,
    'label': 'Description column (utility bill)',
    'examples': ['5101 E 12th St, Tacoma, WA'],
    'extract': _extract_tacoma_utilities,
}


def _extract_walker_lake(text: str) -> Optional[Dict[str, str]]:
    """Walker Lake Disposal: 'Service Address' label, multiline format.

    Format:
        Service Address\\n355 Vista Boulevard Sparks,\\nNV, 89434
        Service Address\\n45 Vista Boulevard Sparks, NV,\\n89434

    Street + city on first line, state/zip may wrap to next line.
    """
    lines = _lines(text)
    for i, line in enumerate(lines):
        if re.search(r'Service\s+Address', line, re.I):
            # Next line should be the address
            if i + 1 >= len(lines):
                return None
            addr_line = lines[i + 1].strip()
            if not addr_line or not re.match(r'^\d', addr_line):
                continue

            # Gather up to 2 more continuation lines for state/zip
            combined = addr_line
            for j in range(i + 2, min(i + 4, len(lines))):
                nxt = lines[j].strip()
                if not nxt or re.search(r'Service\s+Period|Deliver|Picked|Item', nxt, re.I):
                    break
                combined += ' ' + nxt

            # Parse: "355 Vista Boulevard Sparks, NV, 89434"
            m = re.search(r'(\d{5}(?:-\d{4})?)\s*$', combined)
            zip_code = m.group(1) if m else ''

            # Find state
            state_m = re.search(r',?\s*([A-Z]{2})\s*,?\s*\d{5}', combined)
            if not state_m:
                state_m = re.search(r',\s*([A-Z]{2})\s*,', combined)
            state = state_m.group(1) if state_m and state_m.group(1) in _US_STATES else ''

            # Split street from city at the street suffix
            _SUFFIXES = (
                r'(?:Blvd|Boulevard|St|Street|Ave|Avenue|Dr|Drive|Rd|Road|'
                r'Ln|Lane|Ct|Court|Way|Pl|Place|Pkwy|Cir|Hwy|Trl)'
            )
            street_m = re.match(
                r'^(\d+\s+.+?\b' + _SUFFIXES + r')\b\.?,?\s*(.*)',
                addr_line, re.IGNORECASE,
            )
            if street_m:
                street = street_m.group(1).strip().rstrip(',')
                remainder = street_m.group(2).strip().rstrip(',')
                # remainder might be "Sparks" or "Sparks, NV,"
                city_m = re.match(r'^([A-Za-z][A-Za-z\s]+?)(?:,|\s+[A-Z]{2})', remainder)
                city = city_m.group(1).strip() if city_m else remainder.split(',')[0].strip()
                # Don't use city if it's a state abbreviation
                if city.upper() in _US_STATES:
                    city = ''
                return _build_address_dict(street, city=city, state=state, postal_code=zip_code)

            return _build_address_dict(addr_line.rstrip(','), state=state, postal_code=zip_code)
    return None


VENDOR_ADDRESSES['Walker Lake Disposal'] = {
    'has_address': True,
    'label': 'Service Address',
    'examples': ['355 Vista Boulevard, Sparks, NV, 89434'],
    'extract': _extract_walker_lake,
}


# ============================================================
# GENERIC FALLBACK (tries common labels for unconfigured vendors)
# ============================================================

_GENERIC_LABELS = [
    r'Service\s+Addr(?:ess)?\s*:?',
    r'Service\s+Location\s*:?',
    r'Site\s+Address\s*:?',
    r'Job\s*Site\s*:',
    r'Location\s+Address\s*:?',
    r'Property\s+Address\s*:?',
    r'Ship\s+(?:To|Address)\s*:?',
    r'Deliver(?:y)?\s+To\s*:?',
    r'Svc\s+Address\s*:?',
    r'FOR\s+SERVICE\s+AT\s*:?',
    r'Generator\s+Of\s+Waste\s*:?',
]

_SECONDARY_LABELS = [
    r'Loc\s*:',
    r'Location\s*:',
    r'^\s*Address\s*:',
]


def _extract_site_block(text: str) -> Optional[Dict[str, str]]:
    """Extract address from site blocks: (NNNN)\\nName\\nAddress, City ST ZIP.

    Common in multi-site vendors like Suburban Waste, Tri-State.
    Pattern: (0001)\\nSite Name\\n123 Street, City ST
    """
    lines = _lines(text)
    for i, line in enumerate(lines):
        # Match (NNNN) site number marker
        if not re.match(r'^\s*\(?0{0,2}\d{1,5}\)?\s*$', line.strip()):
            continue
        # Skip the site name line(s), look for a street address in next 1-4 lines
        for j in range(i + 1, min(i + 5, len(lines))):
            candidate = lines[j].strip()
            if not candidate:
                continue
            if re.match(r'^\d+\s+\S', candidate):
                # Found street — check for inline city/state/zip
                csz = _parse_city_state_zip(candidate)
                if csz:
                    city_upper = csz['city'].upper()
                    idx = candidate.upper().find(city_upper)
                    if idx > 0:
                        street_part = candidate[:idx].strip().rstrip(',')
                        if street_part:
                            return _build_address_dict(
                                street_part, city=csz['city'],
                                state=csz['state'], postal_code=csz['postal_code'],
                            )
                # Check next line for city/state/zip
                for k in range(j + 1, min(j + 3, len(lines))):
                    nxt = lines[k].strip()
                    if not nxt:
                        continue
                    csz2 = _parse_city_state_zip(nxt)
                    if csz2:
                        return _build_address_dict(candidate, city_state_zip=nxt)
                    cs2 = _parse_city_state(nxt)
                    if cs2:
                        return _build_address_dict(
                            candidate, city=cs2['city'], state=cs2['state'],
                        )
                    break
                return _build_address_dict(candidate)
    return None


def _extract_inline_patterns(text: str) -> Optional[Dict[str, str]]:
    """Extract address from inline patterns in description/service lines.

    Handles:
      - "Service:... @ 174 N WILLARD"
      - "Site 12345 - Name - 4650 Forge Rd Colorado Springs, CO 80907"
      - "JLL The Church | 3625 Quail Drive, Woodward, OK, 73801"
      - '"2440 Hunters Way Charlottesville, VA"' (quoted)
      - "at 500 Callahan Dr. in Knoxville, TN"
      - "Location: 520 S Jefferson Ave, St Louis, MO 63103" (inline, not on own line)
      - "(1) Name\\n3769 Commerce Center Blvd\\nCity, ST ZIP" (numbered item blocks)
    """
    lines = _lines(text)
    full = '\n'.join(lines)

    # Pattern: "@ ADDRESS" (after service description)
    m = re.search(r'@\s+(\d+\s+[A-Za-z].{3,})', full)
    if m:
        remainder = m.group(1).strip()
        csz = _parse_city_state_zip(remainder)
        if csz:
            city_upper = csz['city'].upper()
            idx = remainder.upper().find(city_upper)
            if idx > 0:
                street = remainder[:idx].strip().rstrip(',')
                if street:
                    return _build_address_dict(
                        street, city=csz['city'],
                        state=csz['state'], postal_code=csz['postal_code'],
                    )
        # Street-only after @
        return _build_address_dict(remainder)

    # Pattern: "Site NNNNN - Name - Address City, ST ZIP"
    m = re.search(
        r'Site\s+\S+\s*-\s*[^-]+\s*-\s*(\d+\s+[A-Za-z].+)',
        full,
    )
    if m:
        remainder = m.group(1).strip()
        csz = _parse_city_state_zip(remainder)
        if csz:
            city_upper = csz['city'].upper()
            idx = remainder.upper().find(city_upper)
            if idx > 0:
                street = remainder[:idx].strip().rstrip(',')
                if street:
                    return _build_address_dict(
                        street, city=csz['city'],
                        state=csz['state'], postal_code=csz['postal_code'],
                    )

    # Pattern: "| ADDRESS, City, ST, ZIP" (pipe separator before address)
    m = re.search(
        r'\|\s*(\d+\s+[A-Za-z][^|]+?(?:[A-Z]{2})\s*,?\s*\d{5})',
        full,
    )
    if m:
        remainder = m.group(1).strip()
        csz = _parse_city_state_zip(remainder)
        if csz:
            city_upper = csz['city'].upper()
            idx = remainder.upper().find(city_upper)
            if idx > 0:
                street = remainder[:idx].strip().rstrip(',')
                if street:
                    return _build_address_dict(
                        street, city=csz['city'],
                        state=csz['state'], postal_code=csz['postal_code'],
                    )

    # Pattern: quoted address "123 Street City, ST" or "123 Street City, ST ZIP"
    m = re.search(r'"(\d+\s+[A-Za-z][^"]{3,})"', full)
    if m:
        remainder = m.group(1).strip()
        csz = _parse_city_state_zip(remainder)
        if csz:
            city_upper = csz['city'].upper()
            idx = remainder.upper().find(city_upper)
            if idx > 0:
                street = remainder[:idx].strip().rstrip(',')
                if street:
                    return _build_address_dict(
                        street, city=csz['city'],
                        state=csz['state'], postal_code=csz['postal_code'],
                    )
        # Search for "City, ST" within the string (street starts with digit)
        m2 = re.search(
            r'([A-Za-z][A-Za-z\s]+?)\s*,\s*([A-Z]{2})(?:\s*,?\s*(\d{5}))?\s*$',
            remainder,
        )
        if m2 and m2.group(2) in _US_STATES:
            idx = remainder.find(m2.group(1))
            if idx > 0:
                street = remainder[:idx].strip().rstrip(',')
                if street:
                    return _build_address_dict(
                        street, city=m2.group(1).strip().title(),
                        state=m2.group(2),
                        postal_code=m2.group(3) if m2.group(3) else None,
                    )

    # Pattern: "at ADDRESS in City, ST" in description
    m = re.search(
        r'\bat\s+(\d+\s+[A-Za-z].+?)\s+in\s+([A-Za-z][A-Za-z\s]+,\s*[A-Z]{2})\b',
        full,
    )
    if m:
        street = m.group(1).strip().rstrip('.')
        csz_text = m.group(2).strip()
        cs = _parse_city_state(csz_text)
        if cs:
            return _build_address_dict(street, city=cs['city'], state=cs['state'])

    # Pattern: "Location: ADDRESS, City, ST ZIP" (inline on one line)
    m = re.search(
        r'Location\s*:\s*(\d+\s+[A-Za-z].+)',
        full,
    )
    if m:
        remainder = m.group(1).strip()
        csz = _parse_city_state_zip(remainder)
        if csz:
            city_upper = csz['city'].upper()
            idx = remainder.upper().find(city_upper)
            if idx > 0:
                street = remainder[:idx].strip().rstrip(',')
                if street:
                    return _build_address_dict(
                        street, city=csz['city'],
                        state=csz['state'], postal_code=csz['postal_code'],
                    )

    # Pattern: numbered item "(N) Name\nStreet\nCity, ST ZIP" (D&S, Conigliaro)
    for i, line in enumerate(lines):
        m_item = re.match(r'^\s*\(\d+\)\s+\S', line.strip())
        if not m_item:
            continue
        for j in range(i + 1, min(i + 4, len(lines))):
            candidate = lines[j].strip()
            if candidate and re.match(r'^\d+\s+\S', candidate):
                # Check next line for city/state/zip
                for k in range(j + 1, min(j + 3, len(lines))):
                    nxt = lines[k].strip()
                    if not nxt:
                        continue
                    csz2 = _parse_city_state_zip(nxt)
                    if csz2:
                        return _build_address_dict(candidate, city_state_zip=nxt)
                    break
                break

    # Pattern: "Loc: ADDRESS" on single line (abbreviated)
    m = re.search(r'\bLoc\s*:\s*(\d+\s+\S.+)', full)
    if m:
        addr_text = m.group(1).strip()
        csz = _parse_city_state_zip(addr_text)
        if csz:
            city_upper = csz['city'].upper()
            idx = addr_text.upper().find(city_upper)
            if idx > 0:
                street = addr_text[:idx].strip().rstrip(',')
                if street:
                    return _build_address_dict(
                        street, city=csz['city'],
                        state=csz['state'], postal_code=csz['postal_code'],
                    )
        # Street only
        return _build_address_dict(addr_text)

    return None


def _extract_address_block(text: str) -> Optional[Dict[str, str]]:
    """Last resort: scan for street + city/state/zip on consecutive lines.

    Skips first 10 lines (header/vendor info) and known billing addresses.
    """
    lines = _lines(text)
    for i in range(10, len(lines) - 1):
        candidate = lines[i].strip()
        if not candidate or not re.match(r'^\d+\s+\S', candidate):
            continue
        # Skip known billing addresses
        cl = candidate.lower()
        if any(w in cl for w in ('shelbyville', 'st matthews', 'st. matthews')):
            continue
        # Check next lines for city/state/zip
        for j in range(i + 1, min(i + 3, len(lines))):
            nxt = lines[j].strip()
            if not nxt:
                continue
            csz = _parse_city_state_zip(nxt)
            if csz:
                return _build_address_dict(candidate, city_state_zip=nxt)
            break
    return None


def _extract_generic(text: str) -> Optional[Dict[str, str]]:
    """Generic fallback: try common address labels, then secondary labels,
    then site block patterns, then inline patterns, then address block scan."""
    result = _extract_labeled_address(text, labels=_GENERIC_LABELS)
    if result:
        return result

    result = _extract_labeled_address(text, labels=_SECONDARY_LABELS, skip_lines=0)
    if result:
        return result

    result = _extract_site_block(text)
    if result:
        return result

    result = _extract_inline_patterns(text)
    if result:
        return result

    return _extract_address_block(text)


# ============================================================
# HIGH-VOLUME VENDORS (common label patterns)
# ============================================================

# Republic Services
def _extract_republic_services(text: str) -> Optional[Dict[str, str]]:
    """Republic Services: 'Service Location' or 'Service Address'."""
    return _extract_labeled_address(
        text,
        labels=[r'Service\s+Location', r'Service\s+Address', r'Site\s+Location'],
    )

VENDOR_ADDRESSES['Republic Services'] = {
    'has_address': True,
    'label': 'Service Location',
    'examples': [],
    'extract': _extract_republic_services,
}


# Waste Management
def _extract_waste_management(text: str) -> Optional[Dict[str, str]]:
    """Waste Management: 'Service Address' or 'Service Location'."""
    return _extract_labeled_address(
        text,
        labels=[r'Service\s+Address', r'Service\s+Location', r'Site\s+Address'],
    )

VENDOR_ADDRESSES['Waste Management'] = {
    'has_address': True,
    'label': 'Service Address',
    'examples': [],
    'extract': _extract_waste_management,
}


# GFL Environmental
def _extract_gfl(text: str) -> Optional[Dict[str, str]]:
    """GFL Environmental: 'Service Address' label."""
    return _extract_labeled_address(
        text,
        labels=[r'Service\s+Address', r'Service\s+Location'],
    )

VENDOR_ADDRESSES['GFL Environmental'] = {
    'has_address': True,
    'label': 'Service Address',
    'examples': [],
    'extract': _extract_gfl,
}


# Casella Waste Systems
VENDOR_ADDRESSES['Casella Waste Systems'] = {
    'has_address': True,
    'label': 'Service Address',
    'examples': [],
    'extract': lambda text: _extract_labeled_address(
        text, labels=[r'Service\s+Address', r'Service\s+Location']),
}


# Athens Services
VENDOR_ADDRESSES['Athens Services'] = {
    'has_address': True,
    'label': 'Service Address',
    'examples': [],
    'extract': lambda text: _extract_labeled_address(
        text, labels=[r'Service\s+Address', r'Service\s+Location', r'Site\s*:']),
}


# Waste Pro
VENDOR_ADDRESSES['Waste Pro'] = {
    'has_address': True,
    'label': 'Service Address',
    'examples': [],
    'extract': lambda text: _extract_labeled_address(
        text, labels=[r'Service\s+Address', r'Service\s+Location']),
}


# ============================================================
# PUBLIC API
# ============================================================

def extract_service_address(vendor_name: str, text: str) -> Optional[Dict[str, str]]:
    """
    Extract service address from invoice text for a given vendor.

    DETERMINISTIC: Returns exact match or None. No guessing.

    Args:
        vendor_name: The detected vendor name (from vendor_detection_module)
        text: The raw OCR text from the invoice

    Returns:
        dict with keys: street, city, state, postal_code
        Or None if not found/not applicable
    """
    if vendor_name in VENDOR_ADDRESSES:
        config = VENDOR_ADDRESSES[vendor_name]
        if not config['has_address']:
            return None
        result = config['extract'](text)
        if result:
            return result

    # Try generic fallback for any vendor
    return _extract_generic(text)


def get_configured_vendors() -> List[str]:
    """Return list of all vendors with address extraction configured."""
    return list(VENDOR_ADDRESSES.keys())


def get_vendor_stats() -> Dict[str, int]:
    """Return summary statistics of configured vendors."""
    total = len(VENDOR_ADDRESSES)
    with_addresses = sum(1 for v in VENDOR_ADDRESSES.values() if v['has_address'])
    return {
        'total_configured': total,
        'with_addresses': with_addresses,
        'no_address': total - with_addresses,
    }
