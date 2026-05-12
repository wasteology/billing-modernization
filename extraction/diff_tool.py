"""
Diff tool — automated regression checker for vendor extract migration.

Compares baseline (Python script output) vs executor (JSON pattern output)
row by row, column by column. Any difference in critical fields = regression.
"""

import csv
import sys
from collections import defaultdict


# Fields where differences are regressions (hard failures)
CRITICAL_FIELDS = {
    'charge_total', 'equipment_type', 'material', 'charge_code',
    'equipment_size', 'invoice_number', 'account_number', 'bill_total',
    'invoice_total', 'valid',
}

# Fields to compare but only warn (soft differences)
WARN_FIELDS = {
    'description', 'service_date', 'schedule', 'weight', 'weight_unit',
    'charge_sum', 'diff', 'wo_number', 'reference', 'qty', 'unit_rate',
}


def load_csv(path):
    """Load CSV into list of dicts."""
    with open(path, 'r', newline='') as f:
        return list(csv.DictReader(f))


def normalize_value(val):
    """Normalize a value for comparison."""
    if val is None:
        return ''
    s = str(val).strip()
    if s.lower() in ('none', 'nan', ''):
        return ''
    # Normalize floats
    try:
        fv = float(s)
        if fv == int(fv):
            return str(int(fv))
        return f"{fv:.2f}"
    except (ValueError, OverflowError):
        pass
    # Normalize booleans
    if s.lower() == 'true':
        return 'True'
    if s.lower() == 'false':
        return 'False'
    return s


def diff_rows(baseline, executor, key_fields=None):
    """Compare two lists of row dicts.

    Args:
        baseline: list of dicts (Python script output)
        executor: list of dicts (executor output)
        key_fields: fields to use as row key for matching (default: pdf_filename + charge_total + description)

    Returns:
        dict with:
          total_rows: int
          matched: int
          regressions: list of {row, field, baseline, executor}
          warnings: list of {row, field, baseline, executor}
          missing_in_executor: int
          extra_in_executor: int
    """
    if key_fields is None:
        key_fields = ['pdf_filename', 'charge_total', 'description']

    def make_key(row):
        parts = []
        for f in key_fields:
            parts.append(normalize_value(row.get(f, '')))
        return tuple(parts)

    # Build lookup by key
    base_by_key = defaultdict(list)
    for i, row in enumerate(baseline):
        base_by_key[make_key(row)].append((i, row))

    exec_by_key = defaultdict(list)
    for i, row in enumerate(executor):
        exec_by_key[make_key(row)].append((i, row))

    regressions = []
    warnings = []
    matched = 0
    missing = 0
    extra = 0

    # Match baseline rows to executor rows
    used_exec = set()
    for key, base_rows in base_by_key.items():
        exec_rows = exec_by_key.get(key, [])
        for bi, (base_idx, base_row) in enumerate(base_rows):
            if bi < len(exec_rows):
                exec_idx, exec_row = exec_rows[bi]
                used_exec.add((key, bi))
                matched += 1
                # Compare fields
                all_fields = set(base_row.keys()) | set(exec_row.keys())
                for field in all_fields:
                    bv = normalize_value(base_row.get(field, ''))
                    ev = normalize_value(exec_row.get(field, ''))
                    if bv != ev:
                        entry = {
                            'row': base_idx,
                            'key': key,
                            'field': field,
                            'baseline': bv,
                            'executor': ev,
                        }
                        if field in CRITICAL_FIELDS:
                            regressions.append(entry)
                        elif field in WARN_FIELDS:
                            warnings.append(entry)
            else:
                missing += 1

    # Count extra executor rows
    for key, exec_rows in exec_by_key.items():
        base_count = len(base_by_key.get(key, []))
        extra += max(0, len(exec_rows) - base_count)

    return {
        'total_baseline': len(baseline),
        'total_executor': len(executor),
        'matched': matched,
        'regressions': regressions,
        'warnings': warnings,
        'missing_in_executor': missing,
        'extra_in_executor': extra,
    }


def print_report(result):
    """Print human-readable diff report."""
    print("=" * 70)
    print("REGRESSION CHECK REPORT")
    print("=" * 70)
    print(f"  Baseline rows:       {result['total_baseline']}")
    print(f"  Executor rows:       {result['total_executor']}")
    print(f"  Matched:             {result['matched']}")
    print(f"  Missing in executor: {result['missing_in_executor']}")
    print(f"  Extra in executor:   {result['extra_in_executor']}")
    print()

    regs = result['regressions']
    warns = result['warnings']

    if regs:
        print(f"REGRESSIONS: {len(regs)}")
        print("-" * 70)
        # Group by field
        by_field = defaultdict(list)
        for r in regs:
            by_field[r['field']].append(r)
        for field, entries in sorted(by_field.items()):
            print(f"  {field}: {len(entries)} differences")
            for e in entries[:5]:
                print(f"    row {e['row']}: '{e['baseline']}' → '{e['executor']}'")
            if len(entries) > 5:
                print(f"    ... and {len(entries) - 5} more")
        print()
    else:
        print("REGRESSIONS: 0 (PASS)")
        print()

    if warns:
        print(f"WARNINGS: {len(warns)}")
        print("-" * 70)
        by_field = defaultdict(list)
        for w in warns:
            by_field[w['field']].append(w)
        for field, entries in sorted(by_field.items()):
            print(f"  {field}: {len(entries)} differences")
            for e in entries[:3]:
                print(f"    row {e['row']}: '{e['baseline']}' → '{e['executor']}'")
            if len(entries) > 3:
                print(f"    ... and {len(entries) - 3} more")
        print()
    else:
        print("WARNINGS: 0")
        print()

    if not regs and result['missing_in_executor'] == 0 and result['extra_in_executor'] == 0:
        print("RESULT: PASS — output matches baseline")
    elif not regs:
        print("RESULT: SOFT PASS — no critical regressions but row count differs")
    else:
        print("RESULT: FAIL — critical regressions found")

    return len(regs) == 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Regression diff tool')
    parser.add_argument('baseline', help='Path to baseline CSV (Python script output)')
    parser.add_argument('executor', help='Path to executor CSV (JSON pattern output)')
    parser.add_argument('--key', nargs='+', default=None, help='Key fields for row matching')
    args = parser.parse_args()

    baseline = load_csv(args.baseline)
    executor = load_csv(args.executor)
    result = diff_rows(baseline, executor, key_fields=args.key)
    passed = print_report(result)
    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
