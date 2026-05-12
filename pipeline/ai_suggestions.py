"""
AI suggestion dispatcher for the invoice processing pipeline.

Wraps suggestion functions from historical_build/suggestions.py and
invoice_processing/suggestions.py into a single interface.

Each function returns (candidate, confidence) — never auto-resolves.
AI suggestions are written to ip_review_queue.ai_suggestion field.

Format fingerprinting clusters documents by invoice template structure
so the HITL can bulk-resolve groups with the same format.
"""

import hashlib
import logging
import re
from typing import Optional

log = logging.getLogger(__name__)


# =============================================================================
# Format Fingerprinting — cluster documents by invoice template
# =============================================================================

def format_fingerprint(raw_text: str) -> str:
    """Create a structural fingerprint from OCR text header.

    Documents from the same invoice template produce the same fingerprint.
    Strips variable data (numbers, dates, amounts) and hashes the structural
    skeleton of the first ~10 lines.

    Returns:
        8-char hex fingerprint string
    """
    if not raw_text:
        return 'empty'

    text = raw_text.replace('\\n', '\n')
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Take first 10 non-empty lines (header/template area)
    header = lines[:10]

    # Normalize: lowercase, replace all digit sequences with D,
    # replace dollar amounts, collapse whitespace
    normalized = []
    for line in header:
        line = line.lower()
        line = re.sub(r'\$[\d,]+\.?\d*', '$D', line)
        line = re.sub(r'\d+', 'D', line)
        line = re.sub(r'\s+', ' ', line).strip()
        if line and len(line) > 2:
            normalized.append(line)

    fingerprint_text = '|'.join(normalized)
    return hashlib.md5(fingerprint_text.encode()).hexdigest()[:8]


def describe_format_group(raw_texts: list[str], step: int, vendor: str) -> str:
    """Generate a human-readable description of why a format group is failing.

    Analyzes one representative OCR text to describe:
    - What the document header looks like
    - What labels/fields are present or missing
    - What the HITL should do

    Args:
        raw_texts: List of OCR texts from the group (uses first one)
        step: Pipeline step number
        vendor: Detected vendor name

    Returns:
        Description string for the group
    """
    if not raw_texts:
        return 'Empty group'

    text = raw_texts[0].replace('\\n', '\n')
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    header_lines = lines[:8]
    text_lower = text.lower()

    # Identify header signature (first 2-3 meaningful lines)
    header_sig = []
    for line in header_lines[:3]:
        cleaned = line.strip()
        if len(cleaned) > 3 and not cleaned[0].isdigit():
            header_sig.append(cleaned[:60])
    header_desc = ' / '.join(header_sig) if header_sig else '(no readable header)'

    # Detect key labels present in the document
    label_checks = {
        'account': r'account\s*(?:#|no|number|id)',
        'customer': r'customer\s*(?:#|no|number|id)',
        'invoice': r'invoice\s*(?:#|no|number|date)',
        'statement': r'statement',
        'bill to': r'bill\s*to',
        'remit': r'remit\s*to',
        'amount due': r'(?:amount|total|balance)\s*due',
        'service address': r'service\s*(?:address|location)',
    }
    present = [name for name, pat in label_checks.items()
               if re.search(pat, text_lower)]
    missing = [name for name, pat in label_checks.items()
               if not re.search(pat, text_lower)]

    # Step-specific analysis
    if step == 2:
        desc = f'Header: "{header_desc}". '
        if vendor and vendor != '(unknown)':
            desc += f'Detected as {vendor} but vendor pattern failed. '
        else:
            desc += 'Vendor not detected. '
        desc += f'Labels found: {", ".join(present) if present else "none"}.'
    elif step == 3:
        has_acct = 'account' in present or 'customer' in present
        if has_acct:
            desc = f'Header: "{header_desc}". Account/customer label IS present — pattern needs fixing. Check OCR for the account format.'
        else:
            desc = f'Header: "{header_desc}". No account/customer label found. May be NO_ACCOUNT format or label uses non-standard text.'
    elif step == 4:
        has_inv = 'invoice' in present
        if has_inv:
            desc = f'Header: "{header_desc}". Invoice label present — pattern needs fixing.'
        else:
            desc = f'Header: "{header_desc}". No invoice # label found. Check OCR for alternative labels.'
    elif step == 5:
        desc = f'Header: "{header_desc}". Labels: {", ".join(present) if present else "none"}. Check for date format near Invoice/Statement Date label.'
    elif step == 6:
        has_amt = 'amount due' in present
        if has_amt:
            desc = f'Header: "{header_desc}". Amount/total label present — pattern needs fixing.'
        else:
            desc = f'Header: "{header_desc}". No amount due label found. Check OCR for total/balance fields.'
    else:
        desc = f'Header: "{header_desc}". Labels: {", ".join(present) if present else "none"}.'

    return desc


def get_suggestion(step: int, vendor: str, raw_text: str,
                   md5_hash: str = None) -> dict:
    """Get AI suggestion for a failed extraction.

    Returns dict with keys: ai_suggestion, suggestion_confidence, suggestion_reason
    All values may be None if no suggestion available.
    """
    result = {
        'ai_suggestion': None,
        'suggestion_confidence': None,
        'suggestion_reason': None,
    }

    try:
        if step == 2:
            result.update(_suggest_vendor(raw_text))
        elif step == 3:
            result.update(_suggest_account(vendor, raw_text, md5_hash))
        elif step == 4:
            result.update(_suggest_invoice_number(vendor, raw_text))
        elif step == 5:
            result.update(_suggest_date(vendor, raw_text))
        elif step == 6:
            result.update(_suggest_amount(vendor, raw_text))
    except Exception as e:
        log.debug("AI suggestion error for step %d: %s", step, e)

    return result


def _suggest_vendor(raw_text: str) -> dict:
    """Vendor suggestion using both suggestion modules."""
    source_descriptions = {
        'header_scan': 'Found in first 10 lines with industry keyword (waste, disposal, etc.). Check if this is the hauler name — Accept if correct, Set Value if wrong.',
        'entity_pattern': 'Business entity (LLC/Inc/Corp) found in header. Verify this is the hauler, not a customer or third party.',
        'keyword_proximity': 'Name found near "Invoice"/"Bill To" label. Lower confidence — verify against the OCR text.',
    }

    # Try historical_build suggestions first (more refined junk filtering)
    try:
        from .suggestions_legacy import suggest_vendor as hb_suggest
        candidate, source = hb_suggest(raw_text)
        if candidate:
            return {
                'ai_suggestion': candidate,
                'suggestion_confidence': 'HIGH' if source == 'header_scan' else 'MEDIUM' if source == 'entity_pattern' else 'LOW',
                'suggestion_reason': source_descriptions.get(source, source),
            }
    except ImportError:
        pass

    # Fallback: invoice_processing suggestions
    try:
        from .suggestions import suggest_vendor as ip_suggest
        candidate, source = ip_suggest(raw_text)
        if candidate:
            return {
                'ai_suggestion': candidate,
                'suggestion_confidence': 'HIGH' if source == 'header_scan' else 'MEDIUM' if source == 'entity_pattern' else 'LOW',
                'suggestion_reason': source_descriptions.get(source, source),
            }
    except ImportError:
        pass

    return {'suggestion_reason': 'No vendor name detected. Check OCR text for the hauler name in the header, then use Set Value.'}


def _suggest_account(vendor: str, raw_text: str,
                     md5_hash: str = None) -> dict:
    """Account number suggestion."""
    # Try invoice_processing suggestions (has spatial bounding-box support)
    try:
        from .suggestions import suggest_account as ip_suggest
        candidate = ip_suggest(vendor, raw_text, md5_hash=md5_hash)
        if candidate:
            return {
                'ai_suggestion': candidate,
                'suggestion_confidence': 'MEDIUM',
                'suggestion_reason': f'Found "{candidate}" near Account/Customer # label. Verify format matches {vendor} account pattern — Accept if correct, Set Value if wrong.',
            }
    except ImportError:
        pass

    # Fallback: historical_build suggestions
    try:
        from .suggestions_legacy import suggest_account as hb_suggest
        candidate = hb_suggest(vendor, raw_text)
        if candidate:
            return {
                'ai_suggestion': candidate,
                'suggestion_confidence': 'LOW',
                'suggestion_reason': f'Found "{candidate}" near account keyword. Low confidence — check OCR text to verify this is the account number, not an invoice or reference number.',
            }
    except ImportError:
        pass

    return {'suggestion_reason': f'No account number found for {vendor}. Check OCR text for an account/customer # field. If this vendor has no account numbers, use No Account.'}


def _suggest_invoice_number(vendor: str, raw_text: str) -> dict:
    """Invoice number suggestion."""
    try:
        from .suggestions_legacy import suggest_invoice_number
        candidate = suggest_invoice_number(vendor, raw_text)
        if candidate:
            return {
                'ai_suggestion': candidate,
                'suggestion_confidence': 'MEDIUM',
                'suggestion_reason': f'Found "{candidate}" near Invoice #/No label. Accept if correct. If wrong, check OCR text for the actual invoice number and use Set Value.',
            }
    except ImportError:
        pass

    return {'suggestion_reason': f'No invoice number found for {vendor}. Look for "Invoice #", "Invoice No", or "Bill #" in the OCR text, then use Set Value.'}


def _suggest_date(vendor: str, raw_text: str) -> dict:
    """Invoice date suggestion."""
    try:
        from .suggestions_legacy import suggest_date
        candidate = suggest_date(vendor, raw_text)
        if candidate:
            return {
                'ai_suggestion': candidate,
                'suggestion_confidence': 'MEDIUM',
                'suggestion_reason': f'Found date "{candidate}" near Invoice/Bill Date label. Accept if this is the invoice date (not due date or service period).',
            }
    except ImportError:
        pass

    return {'suggestion_reason': f'No invoice date found for {vendor}. Look for "Invoice Date" or "Statement Date" in OCR text (not "Due Date"). Use Set Value with format MM/DD/YYYY.'}


def _suggest_amount(vendor: str, raw_text: str) -> dict:
    """Bill total suggestion."""
    try:
        from .suggestions_legacy import suggest_amount
        candidate = suggest_amount(vendor, raw_text)
        if candidate:
            return {
                'ai_suggestion': candidate,
                'suggestion_confidence': 'MEDIUM',
                'suggestion_reason': f'Found ${candidate} near Total/Amount Due label. Accept if this is the final amount owed (not a subtotal or previous balance).',
            }
    except ImportError:
        pass

    return {'suggestion_reason': f'No amount found for {vendor}. Look for "Total Due", "Amount Due", or "Balance Due" in OCR text, then use Set Value.'}
