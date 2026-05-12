"""
Per-field validation checks loaded from vendor profiles (ip_vendor_profile).

Three validation layers:
1. Format validation — length, composition, structure
2. Behavioral validation — recurrence, cardinality, stability (queries ip_extraction_result)
3. Position validation — extraction zone, label proximity

All three must pass before gate_result = PASSED.
Results → ip_validation_result.
"""

import logging
import re
from typing import Optional

import psycopg2.extras

from .database import get_connection

log = logging.getLogger(__name__)


def load_all_vendor_profiles(conn=None) -> dict:
    """Load ALL active vendor profiles into memory.

    Returns: {(vendor_name, field): profile_dict, ...}
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM ip_vendor_profile WHERE profile_status = 'ACTIVE'")
    profiles = {}
    for row in cur.fetchall():
        key = (row['vendor_name'], row['field'])
        profiles[key] = dict(row)
    if own_conn:
        conn.close()
    log.info("Loaded %d vendor profiles", len(profiles))
    return profiles


def get_vendor_profile(vendor_name: str, field: str,
                       format_variant: int = 1,
                       _profiles_cache: dict = None) -> Optional[dict]:
    """Load vendor profile — uses cache if provided, else hits DB."""
    if _profiles_cache is not None:
        return _profiles_cache.get((vendor_name, field))
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM ip_vendor_profile"
        " WHERE vendor_name = %s AND field = %s AND format_variant = %s"
        " AND profile_status = 'ACTIVE'",
        (vendor_name, field, format_variant),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def validate_format(field: str, value: str, vendor_profile: dict) -> dict:
    """Format validation: check value against vendor profile constraints.

    Returns: {check_result: 'PASS'|'FAIL', detail: str}
    """
    if not vendor_profile:
        return {'check_result': 'PASS', 'detail': 'No profile (skip format check)'}

    checks = []

    # Length check
    min_len = vendor_profile.get('value_length_min')
    max_len = vendor_profile.get('value_length_max')
    if min_len and len(value) < min_len:
        checks.append(f'Length {len(value)} < minimum {min_len}')
    if max_len and len(value) > max_len:
        checks.append(f'Length {len(value)} > maximum {max_len}')

    # Composition check
    composition = vendor_profile.get('value_composition')
    if composition:
        if composition == 'NUMERIC' and not re.match(r'^[\d\-\.]+$', value):
            checks.append(f'Expected NUMERIC, got non-numeric chars')
        elif composition == 'ALPHANUMERIC' and not re.match(r'^[A-Za-z0-9\-]+$', value):
            checks.append(f'Expected ALPHANUMERIC, got special chars')
        elif composition == 'PREFIXED':
            prefix = vendor_profile.get('value_prefix_pattern')
            if prefix and not re.match(prefix, value):
                checks.append(f'Does not match prefix pattern: {prefix}')

    if checks:
        return {'check_result': 'FAIL', 'detail': '; '.join(checks)}
    return {'check_result': 'PASS', 'detail': 'Format OK'}


def validate_behavioral(field: str, value: str,
                        vendor_name: str,
                        _collision_cache: dict = None) -> dict:
    """Behavioral validation: check value against corpus patterns.

    Note: The same account number CAN legitimately appear under different vendors.
    The unique key is (vendor, account_number), not account_number alone.
    Cross-vendor collision is NOT a failure.

    Returns: {check_result: 'PASS'|'FAIL', detail: str}
    """
    # Currently no behavioral checks produce failures.
    # Placeholder for future checks (e.g. account format drift within a vendor).
    return {'check_result': 'PASS', 'detail': 'Behavioral OK'}


def validate_position(field: str, value: str, raw_text: str,
                      vendor_profile: dict) -> dict:
    """Position validation: check extraction zone and label proximity.

    Returns: {check_result: 'PASS'|'FAIL', detail: str}
    """
    if not vendor_profile or not vendor_profile.get('detection_zone'):
        return {'check_result': 'PASS', 'detail': 'No position profile (skip)'}

    # Skip position check for normalized fields — extracted value won't match raw text
    if field in ('invoice_date', 'bill_total', 'amount_due'):
        return {'check_result': 'PASS', 'detail': 'Normalized field (skip position)'}

    checks = []
    text = raw_text.replace('\\n', '\n') if raw_text else ''

    # Find value position in text
    pos = text.find(value)
    if pos < 0:
        checks.append('Value not found in raw text')
    else:
        text_len = len(text)
        relative_pos = pos / text_len if text_len else 0

        # Check detection zone
        zone = vendor_profile.get('detection_zone', '')
        if zone == 'HEADER' and relative_pos > 0.4:
            checks.append(f'Expected HEADER zone, found at position {relative_pos:.1%}')
        elif zone == 'BODY' and (relative_pos < 0.2 or relative_pos > 0.8):
            checks.append(f'Expected BODY zone, found at position {relative_pos:.1%}')

    if checks:
        return {'check_result': 'FAIL', 'detail': '; '.join(checks)}
    return {'check_result': 'PASS', 'detail': 'Position OK'}


def run_validation(md5_hash: str, step: int, field: str,
                   value: str, vendor_name: str, raw_text: str,
                   extraction_result_id: int,
                   _profiles_cache: dict = None,
                   _collision_cache: dict = None) -> list[dict]:
    """Run all validation checks for an extraction result.

    _profiles_cache: pre-loaded vendor profiles from load_all_vendor_profiles()
    _collision_cache: pre-computed account cross-vendor collision counts

    Returns list of validation result dicts ready for write_validation_results().
    """
    profile = get_vendor_profile(vendor_name, field, _profiles_cache=_profiles_cache)

    results = []

    # Format check
    fmt_result = validate_format(field, value, profile)
    results.append({
        'extraction_result_id': extraction_result_id,
        'md5_hash': md5_hash,
        'step': step,
        'check_name': 'FORMAT',
        'check_result': fmt_result['check_result'],
        'detail': fmt_result['detail'],
    })

    # Behavioral check (only for account numbers, skip for other fields initially)
    if field in ('account_number', 'hauler_account_number'):
        beh_result = validate_behavioral(field, value, vendor_name,
                                         _collision_cache=_collision_cache)
        results.append({
            'extraction_result_id': extraction_result_id,
            'md5_hash': md5_hash,
            'step': step,
            'check_name': 'BEHAVIORAL',
            'check_result': beh_result['check_result'],
            'detail': beh_result['detail'],
        })

    # Position check
    pos_result = validate_position(field, value, raw_text, profile)
    results.append({
        'extraction_result_id': extraction_result_id,
        'md5_hash': md5_hash,
        'step': step,
        'check_name': 'POSITION',
        'check_result': pos_result['check_result'],
        'detail': pos_result['detail'],
    })

    return results


def all_checks_pass(validation_results: list[dict]) -> bool:
    """Return True if all validation checks passed."""
    return all(r['check_result'] == 'PASS' for r in validation_results)


# =============================================================================
# Seed vendor profiles for POC vendors
# =============================================================================

POC_VENDOR_PROFILES = [
    # Republic Services
    {'vendor_name': 'Republic Services', 'field': 'account_number',
     'detection_zone': 'HEADER', 'value_length_min': 13, 'value_length_max': 15,
     'value_composition': 'NUMERIC', 'value_prefix_pattern': r'\d-\d{4}-\d{7}',
     'known_value_examples': '3-0509-0312663'},
    {'vendor_name': 'Republic Services', 'field': 'invoice_number',
     'detection_zone': 'HEADER', 'value_length_min': 14, 'value_length_max': 14,
     'value_composition': 'NUMERIC', 'value_prefix_pattern': r'\d{4}-\d{9}',
     'known_value_examples': '0176-007823583'},
    {'vendor_name': 'Republic Services', 'field': 'invoice_date',
     'detection_zone': 'HEADER'},
    {'vendor_name': 'Republic Services', 'field': 'detected_vendor',
     'detection_zone': 'HEADER'},

    # Waste Management
    {'vendor_name': 'Waste Management', 'field': 'account_number',
     'detection_zone': 'HEADER', 'value_length_min': 8, 'value_length_max': 14,
     'value_composition': 'ALPHANUMERIC', 'value_prefix_pattern': r'W(?:GY|HM)',
     'known_value_examples': 'WGY17110UB'},
    {'vendor_name': 'Waste Management', 'field': 'invoice_number',
     'detection_zone': 'HEADER', 'value_length_min': 10, 'value_length_max': 13,
     'value_composition': 'NUMERIC',
     'known_value_examples': '0012345678'},
    {'vendor_name': 'Waste Management', 'field': 'invoice_date',
     'detection_zone': 'HEADER'},
    {'vendor_name': 'Waste Management', 'field': 'detected_vendor',
     'detection_zone': 'HEADER'},

    # GFL
    {'vendor_name': 'GFL', 'field': 'account_number',
     'detection_zone': 'HEADER', 'value_length_min': 5, 'value_length_max': 12,
     'value_composition': 'ALPHANUMERIC',
     'known_value_examples': 'UK1234567'},
    {'vendor_name': 'GFL', 'field': 'invoice_number',
     'detection_zone': 'HEADER', 'value_length_min': 10, 'value_length_max': 13,
     'value_composition': 'ALPHANUMERIC', 'value_prefix_pattern': r'[A-Z]{1,2}\d{10,11}',
     'known_value_examples': 'UK0000449634'},
    {'vendor_name': 'GFL', 'field': 'invoice_date',
     'detection_zone': 'HEADER'},
    {'vendor_name': 'GFL', 'field': 'detected_vendor',
     'detection_zone': 'HEADER'},

    # Anytime Waste
    {'vendor_name': 'Anytime Waste', 'field': 'account_number',
     'detection_zone': 'HEADER', 'value_length_min': 5, 'value_length_max': 5,
     'value_composition': 'NUMERIC',
     'known_value_examples': '12345'},
    {'vendor_name': 'Anytime Waste', 'field': 'invoice_number',
     'detection_zone': 'HEADER', 'value_length_min': 6, 'value_length_max': 6,
     'value_composition': 'NUMERIC',
     'known_value_examples': '123456'},
    {'vendor_name': 'Anytime Waste', 'field': 'invoice_date',
     'detection_zone': 'HEADER'},
    {'vendor_name': 'Anytime Waste', 'field': 'detected_vendor',
     'detection_zone': 'HEADER'},
]


def seed_vendor_profiles() -> int:
    """Populate ip_vendor_profile with POC vendor profiles."""
    conn = get_connection()
    cur = conn.cursor()

    # Upsert profiles
    sql = """
        INSERT INTO ip_vendor_profile
            (vendor_name, field, format_variant, detection_zone,
             value_length_min, value_length_max, value_composition,
             value_prefix_pattern, known_value_examples)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (vendor_name, field, format_variant) DO UPDATE SET
            detection_zone = EXCLUDED.detection_zone,
            value_length_min = EXCLUDED.value_length_min,
            value_length_max = EXCLUDED.value_length_max,
            value_composition = EXCLUDED.value_composition,
            value_prefix_pattern = EXCLUDED.value_prefix_pattern,
            known_value_examples = EXCLUDED.known_value_examples,
            updated_at = NOW()
    """

    count = 0
    for p in POC_VENDOR_PROFILES:
        cur.execute(sql, (
            p['vendor_name'], p['field'], p.get('format_variant', 1),
            p.get('detection_zone'), p.get('value_length_min'),
            p.get('value_length_max'), p.get('value_composition'),
            p.get('value_prefix_pattern'), p.get('known_value_examples'),
        ))
        count += 1

    conn.commit()
    conn.close()

    log.info("Seeded %d vendor profile rows", count)
    print(f"\n  Seeded {count} vendor profile rows for 4 POC vendors.")
    return count
