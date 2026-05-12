"""
OCR Validation — detect rotated, badly parsed, and incomplete invoices.
=========================================================================

Three issue categories:
  ROTATED   — PDF was upside-down or sideways; OCR produced mirrored/reversed gibberish
  BAD_PARSE — OCR ran but produced heavily garbled text mixed with some valid content
  INCOMPLETE — text is abnormally short or missing expected invoice fields

Each invoice gets a validation verdict:
  PASS     — no issues detected
  REVIEW   — one or more flags, needs human review
  FAIL     — high-confidence bad OCR, should be re-OCR'd or excluded

Output: output/ocr_validation.csv
"""

import re
import logging
import pandas as pd
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

INPUT_CSV = Path(__file__).parent / 'output' / 'ocr_results.csv'
OUTPUT_CSV = Path(__file__).parent / 'output' / 'ocr_validation.csv'


# ---------------------------------------------------------------------------
# Detection functions
# ---------------------------------------------------------------------------

def detect_rotated(text: str) -> dict:
    """
    Detect FULLY rotated/mirrored OCR output.

    Truly rotated PDFs produce text where ALL content is reversed/mirrored:
      - Zero parseable dollar amounts ($X.XX)
      - Zero recognized English words
      - Reversed-text markers throughout

    Multi-page docs may have one noisy page but still contain valid invoice
    data. These are NOT rotated — they're partial noise (handled by bad_parse).

    The key discriminator: truly rotated docs have ZERO dollar amounts.
    A doc with 50+ amounts and some gibberish is a noisy multi-page doc, not rotated.
    """
    words = re.findall(r'[a-zA-Z]{3,}', text)
    if not words:
        return {'rotated': False, 'rotated_score': 0, 'gibberish_ratio': 0, 'reversed_markers': 0}

    # Gibberish ratio: words with very few vowels relative to length
    gibberish = 0
    for w in words:
        lower = w.lower()
        vowels = sum(1 for c in lower if c in 'aeiou')
        if len(w) >= 4 and vowels <= len(w) * 0.2:
            gibberish += 1

    gibberish_ratio = gibberish / len(words)

    # Known reversed-text markers from WM invoices
    reversed_markers = [
        r'epops',       # "scope" reversed
        r'spzex',       # "yards" mirrored
        r'uaznjey',     # mirrored text
        r'yseaL',       # "Leasy"/"Trash" artifact
        r'Houd',        # reversed "duoH"
        r'Tesodst',     # "Disposal" reversed
        r'NOILVLINVS',  # "SANITATION" reversed
        r'SIYYVH',      # "HARRIS" reversed
    ]
    marker_hits = sum(1 for m in reversed_markers if re.search(m, text))

    # Currency amounts — the key discriminator
    # Truly rotated docs have ZERO dollar amounts
    # Match both "$280.00" and "$ 280.00" (Ace Recycling uses spaced format)
    dollar_amounts = re.findall(r'\$\s?[\d,]+\.\d{2}', text)
    # Also match bare amounts like "280.00" as backup
    bare_amounts = re.findall(r'(?<!\d)[\d,]+\.\d{2}(?!\d)', text)

    # Real word ratio (quick check)
    common = {
        'invoice', 'account', 'total', 'amount', 'date', 'service', 'payment',
        'waste', 'trash', 'recycling', 'disposal', 'charges', 'balance', 'due',
        'customer', 'number', 'address', 'location', 'description',
    }
    real_hits = sum(1 for w in words if w.lower() in common)

    score = 0

    # Only flag as rotated if NO dollar amounts (any format) — this is the hard gate
    has_any_amounts = len(dollar_amounts) > 0 or len(bare_amounts) > 3
    if not has_any_amounts:
        if gibberish_ratio > 0.10:
            score += 4
        if marker_hits >= 2:
            score += 3
        elif marker_hits >= 1:
            score += 1
        if real_hits == 0 and len(text) > 500:
            score += 2
    # else: doc has dollar amounts → not fully rotated, even if noisy

    return {
        'rotated': score >= 4,
        'rotated_score': score,
        'gibberish_ratio': round(gibberish_ratio, 4),
        'reversed_markers': marker_hits,
    }


def detect_bad_parse(text: str) -> dict:
    """
    Detect badly parsed OCR — partial garbling mixed with valid content.

    Two sub-categories:
      1. Multi-page docs with one or more noisy/rotated pages mixed with valid content
         (gibberish_ratio 0.05-0.20 BUT has dollar amounts — partially usable)
      2. Overall garbled text with low real-word ratio

    Signals:
      - Elevated gibberish ratio (>0.04) — partial noise from rotated pages
      - High noise-line ratio (lines with <30% alpha characters)
      - Low real-word ratio despite having enough text
      - OCR artifacts: repeated special chars, broken words
    """
    words = re.findall(r'[a-zA-Z]{3,}', text)
    total_words = len(words) if words else 1

    # Common invoice English words
    common = {
        'the', 'and', 'for', 'this', 'with', 'from', 'your', 'that', 'are', 'not',
        'you', 'all', 'can', 'our', 'has', 'how', 'any', 'use', 'due', 'new',
        'date', 'invoice', 'account', 'total', 'amount', 'service', 'payment',
        'balance', 'charges', 'number', 'address', 'bill', 'page', 'period',
        'customer', 'waste', 'trash', 'recycling', 'pickup', 'yard', 'container',
        'disposal', 'monthly', 'weekly', 'previous', 'current', 'received',
        'credit', 'return', 'please', 'check', 'paid', 'make', 'call',
        'location', 'description', 'quantity', 'price', 'rate', 'unit',
        'hauling', 'collection', 'delivery', 'rental', 'fuel', 'tax',
        'company', 'name', 'street', 'city', 'state', 'code',
    }
    real_words = sum(1 for w in words if w.lower() in common)
    real_word_ratio = real_words / total_words

    # Gibberish ratio (same calc as rotated, needed for partial-noise detection)
    gibberish = 0
    for w in words:
        lower = w.lower()
        vowels = sum(1 for c in lower if c in 'aeiou')
        if len(w) >= 4 and vowels <= len(w) * 0.2:
            gibberish += 1
    gibberish_ratio = gibberish / total_words

    # Noise lines: lines where alpha chars are < 30% of content
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    total_lines = len(lines) if lines else 1
    noise_lines = 0
    for line in lines:
        alpha = sum(1 for c in line if c.isalpha())
        if len(line) > 0 and alpha / len(line) < 0.30:
            noise_lines += 1
    noise_ratio = noise_lines / total_lines

    # Broken-word artifacts: excessive single/double char "words"
    short_fragments = sum(1 for w in re.findall(r'\S+', text) if len(w) <= 2)
    all_tokens = len(re.findall(r'\S+', text)) or 1
    fragment_ratio = short_fragments / all_tokens

    # Repeated special character noise
    special_noise = len(re.findall(r'[°€£¥§±×÷]{2,}|[^\x00-\x7F]{3,}', text))

    score = 0

    # Partial noise: elevated gibberish from multi-page docs with rotated pages
    # These docs have valid content but also significant garbage mixed in
    if gibberish_ratio > 0.10:
        score += 2  # heavy noise (but doc has amounts, so not ROTATED)
    elif gibberish_ratio > 0.05:
        score += 1  # moderate noise

    if real_word_ratio < 0.15:
        score += 2
    elif real_word_ratio < 0.25:
        score += 1
    if noise_ratio > 0.25:
        score += 2
    elif noise_ratio > 0.15:
        score += 1
    if special_noise > 5:
        score += 1
    if fragment_ratio > 0.40:
        score += 1

    return {
        'bad_parse': score >= 3,
        'bad_parse_score': score,
        'real_word_ratio': round(real_word_ratio, 4),
        'noise_ratio': round(noise_ratio, 4),
        'fragment_ratio': round(fragment_ratio, 4),
        'special_noise_count': special_noise,
        'bp_gibberish_ratio': round(gibberish_ratio, 4),
    }


def detect_incomplete(text: str) -> dict:
    """
    Detect incomplete OCR — truncated documents or missing key fields.

    Signals:
      - Very short text (bottom 5% of corpus is ~770 chars, but some vendors
        legitimately produce short invoices like Burgmeier's at ~680)
      - Missing ALL of: currency amounts, dates, account/invoice numbers
      - Missing expected invoice structure keywords
    """
    total_chars = len(text)

    # Currency amounts (both "$X.XX", "$ X.XX", and bare "X.XX" patterns)
    dollar_amounts = re.findall(r'\$\s?[\d,]+\.\d{2}', text)
    bare_amounts = re.findall(r'(?<!\d)[\d,]+\.\d{2}(?!\d)', text)

    # Dates — multiple formats
    slash_dates = re.findall(r'\d{1,2}/\d{1,2}/\d{2,4}', text)
    spelled_dates = re.findall(
        r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
        text, re.IGNORECASE
    )
    short_dates = re.findall(
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{2,4}',
        text, re.IGNORECASE
    )
    all_dates = slash_dates + spelled_dates + short_dates

    # Key invoice field labels
    upper = text.upper()
    has_invoice_num = bool(re.search(r'INVOICE\s*(#|NO|NUMBER)', upper))
    has_account = bool(re.search(r'ACCOUNT\s*(#|NO|NUMBER)', upper))
    has_customer = bool(re.search(r'CUSTOMER\s*(#|NO|NUMBER|ID|NAME)', upper))
    has_amount_due = bool(re.search(r'AMOUNT\s*DUE|TOTAL\s*DUE|BALANCE\s*DUE|INVOICE\s*TOTAL', upper))
    has_any_id = has_invoice_num or has_account or has_customer

    field_count = sum([has_invoice_num, has_account, has_customer, has_amount_due])

    score = 0
    # Very short with no amounts = likely truncated
    if total_chars < 400:
        score += 3
    elif total_chars < 600 and len(bare_amounts) < 3:
        score += 2

    # No amounts at all
    if len(bare_amounts) == 0:
        score += 2

    # No dates and no amounts = not an invoice
    if len(all_dates) == 0 and len(bare_amounts) == 0:
        score += 2

    # No identifiable invoice field labels
    if field_count == 0:
        score += 1

    return {
        'incomplete': score >= 3,
        'incomplete_score': score,
        'text_length': total_chars,
        'dollar_amounts': len(dollar_amounts),
        'total_amounts': len(bare_amounts),
        'date_count': len(all_dates),
        'field_count': field_count,
        'has_invoice_num': has_invoice_num,
        'has_account': has_account,
        'has_amount_due': has_amount_due,
    }


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------

def validate_ocr(df: pd.DataFrame) -> pd.DataFrame:
    """Run all three validators on every row. Return validation results."""
    results = []

    for _, row in df.iterrows():
        text = str(row['raw_ocr_text'])

        rot = detect_rotated(text)
        bad = detect_bad_parse(text)
        inc = detect_incomplete(text)

        # Determine verdict
        flags = []
        if rot['rotated']:
            flags.append('ROTATED')
        if bad['bad_parse']:
            flags.append('BAD_PARSE')
        if inc['incomplete']:
            flags.append('INCOMPLETE')

        # Score-based verdict
        total_score = rot['rotated_score'] + bad['bad_parse_score'] + inc['incomplete_score']
        if rot['rotated']:
            verdict = 'FAIL'
        elif total_score >= 5:
            verdict = 'FAIL'
        elif total_score >= 3:
            verdict = 'REVIEW'
        elif flags:
            verdict = 'REVIEW'
        else:
            verdict = 'PASS'

        results.append({
            'pdf_filename': row['pdf_filename'],
            'pdf_path': row.get('pdf_path', ''),
            'month_folder': row.get('month_folder', ''),
            'site_code': row.get('site_code', ''),
            'vendor_name': row.get('vendor_name', ''),
            'document_type': row.get('document_type', ''),
            'ocr_quality_score': row.get('ocr_quality_score', ''),
            'verdict': verdict,
            'flags': '|'.join(flags) if flags else '',
            'total_score': total_score,
            # Rotated
            'rotated_score': rot['rotated_score'],
            'gibberish_ratio': rot['gibberish_ratio'],
            'reversed_markers': rot['reversed_markers'],
            # Bad parse
            'bad_parse_score': bad['bad_parse_score'],
            'real_word_ratio': bad['real_word_ratio'],
            'noise_ratio': bad['noise_ratio'],
            'fragment_ratio': bad['fragment_ratio'],
            'special_noise': bad['special_noise_count'],
            # Incomplete
            'incomplete_score': inc['incomplete_score'],
            'text_length': inc['text_length'],
            'dollar_amounts': inc['dollar_amounts'],
            'total_amounts': inc['total_amounts'],
            'date_count': inc['date_count'],
            'field_count': inc['field_count'],
        })

    return pd.DataFrame(results)


def main():
    logger.info(f"Loading OCR results from {INPUT_CSV}")
    df = pd.read_csv(INPUT_CSV)
    logger.info(f"  {len(df)} invoices loaded")

    logger.info("Running validation...")
    vdf = validate_ocr(df)

    # Save
    vdf.to_csv(OUTPUT_CSV, index=False)
    logger.info(f"Saved to {OUTPUT_CSV}")

    # Summary
    print("\n" + "=" * 60)
    print("  OCR VALIDATION SUMMARY")
    print("=" * 60)

    vc = vdf['verdict'].value_counts()
    for v in ['PASS', 'REVIEW', 'FAIL']:
        cnt = vc.get(v, 0)
        pct = cnt / len(vdf) * 100
        print(f"  {v:<8s}  {cnt:>5d}  ({pct:5.1f}%)")
    print(f"  {'TOTAL':<8s}  {len(vdf):>5d}")

    # Flag breakdown
    flagged = vdf[vdf['flags'] != '']
    if len(flagged) > 0:
        print(f"\n  Flag breakdown:")
        all_flags = []
        for f in flagged['flags']:
            all_flags.extend(f.split('|'))
        for flag, cnt in pd.Series(all_flags).value_counts().items():
            print(f"    {flag:<15s}  {cnt:>4d}")

    # Show all FAIL
    fails = vdf[vdf['verdict'] == 'FAIL']
    if len(fails) > 0:
        print(f"\n  FAIL details ({len(fails)}):")
        for _, r in fails.iterrows():
            print(f"    {r['pdf_filename']}")
            print(f"      flags={r['flags']}  score={r['total_score']}  "
                  f"gib={r['gibberish_ratio']}  rwr={r['real_word_ratio']}  "
                  f"len={r['text_length']}  amt={r['total_amounts']}  dt={r['date_count']}")

    # Show REVIEW
    reviews = vdf[vdf['verdict'] == 'REVIEW']
    if len(reviews) > 0:
        print(f"\n  REVIEW details ({len(reviews)}):")
        for _, r in reviews.iterrows():
            print(f"    {r['pdf_filename']}")
            print(f"      flags={r['flags']}  score={r['total_score']}  "
                  f"gib={r['gibberish_ratio']}  rwr={r['real_word_ratio']}  "
                  f"len={r['text_length']}  amt={r['total_amounts']}  dt={r['date_count']}")

    print()


if __name__ == '__main__':
    main()
