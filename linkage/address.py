"""
Address normalization and fuzzy matching utilities.

Used by matcher.py to score invoice addresses against location table addresses.
"""

import re

# Common suffix normalizations (expand as needed)
SUFFIX_MAP = {
    "street": "st",
    "avenue": "ave",
    "boulevard": "blvd",
    "drive": "dr",
    "lane": "ln",
    "road": "rd",
    "court": "ct",
    "place": "pl",
    "circle": "cir",
    "terrace": "ter",
    "highway": "hwy",
    "parkway": "pkwy",
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
    "northeast": "ne",
    "northwest": "nw",
    "southeast": "se",
    "southwest": "sw",
    "suite": "ste",
    "apartment": "apt",
    "building": "bldg",
}

# Regex to strip unit/suite/apt suffixes (they vary between invoice and billing)
_UNIT_RE = re.compile(
    r",?\s*(?:suite|ste|apt|unit|bldg|building|#)\s*[a-z0-9\-]+\s*$",
    re.IGNORECASE,
)


def normalize_address(addr: str | None) -> str:
    """Lowercase, remove punctuation, normalize suffixes, strip unit numbers."""
    if not addr:
        return ""
    s = addr.lower().strip()
    # Remove periods and commas
    s = s.replace(".", "").replace(",", "")
    # Strip unit/suite suffixes
    s = _UNIT_RE.sub("", s)
    # Normalize suffixes
    words = s.split()
    normalized = []
    for w in words:
        normalized.append(SUFFIX_MAP.get(w, w))
    return " ".join(normalized)


def extract_street_number(addr: str) -> str | None:
    """Pull leading street number from an address string."""
    if not addr:
        return None
    m = re.match(r"(\d+)", addr.strip())
    return m.group(1) if m else None


def _first_word_after_number(addr: str) -> str | None:
    """Get the first non-number word (the street name start)."""
    if not addr:
        return None
    words = addr.strip().split()
    for w in words:
        if not w.isdigit():
            return w.lower()
    return None


def fuzzy_address_score(
    invoice_addr: str | None,
    invoice_city: str | None,
    invoice_state: str | None,
    invoice_postal: str | None,
    location_addr: str | None,
    location_city: str | None,
    location_region: str | None,
    location_postal: str | None,
) -> float:
    """Score address similarity between an invoice and a location.

    Returns 0.0–1.0 weighted:
      Street match:  0.6 (exact normalized) or 0.5 (number + first word)
      City match:    0.2
      State match:   0.1
      Zip match:     0.1
    """
    score = 0.0

    # --- Street (0.6 max) ---
    norm_inv = normalize_address(invoice_addr)
    norm_loc = normalize_address(location_addr)

    if norm_inv and norm_loc:
        if norm_inv == norm_loc:
            score += 0.6
        else:
            # Partial: street number + first word match
            inv_num = extract_street_number(norm_inv)
            loc_num = extract_street_number(norm_loc)
            inv_word = _first_word_after_number(norm_inv)
            loc_word = _first_word_after_number(norm_loc)

            if inv_num and loc_num and inv_num == loc_num and inv_word and loc_word and inv_word == loc_word:
                score += 0.5

    # --- City (0.2 max) ---
    inv_city = (invoice_city or "").lower().strip()
    loc_city = (location_city or "").lower().strip()
    if inv_city and loc_city and inv_city == loc_city:
        score += 0.2

    # --- State (0.1 max) ---
    inv_state = (invoice_state or "").lower().strip()
    loc_state = (location_region or "").lower().strip()
    if inv_state and loc_state:
        # Handle full name vs abbreviation (both stored as-is)
        if inv_state == loc_state or inv_state[:2] == loc_state[:2]:
            score += 0.1

    # --- Zip (0.1 max) ---
    inv_zip = (invoice_postal or "").strip()[:5]
    loc_zip = (location_postal or "").strip()[:5]
    if inv_zip and loc_zip and inv_zip == loc_zip:
        score += 0.1

    return round(score, 2)
