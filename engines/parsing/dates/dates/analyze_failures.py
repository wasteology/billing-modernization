#!/usr/bin/env python3
"""
Date Extraction Failure Analysis

Analyzes date extraction failures by vendor to prioritize pattern development.
Identifies which vendors need specific patterns based on failure count.

Usage:
    python -m parsing_engines.dates.analyze_failures <ocr_csv_path>
    python -m parsing_engines.dates.analyze_failures training_data/ocr_chunks/raw_ocr_text.csv

Output:
    - Vendor failure counts sorted by impact
    - Sample failures for top vendors
    - Overall coverage statistics
"""

import sys
import os
from pathlib import Path
from collections import defaultdict
from typing import Optional, Tuple, Dict, List
import re

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def load_csv_lazy(csv_path: str, limit: Optional[int] = None):
    """
    Load CSV lazily, yielding rows one at a time.
    Handles large files without loading into memory.
    """
    import csv

    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if limit and i >= limit:
                break
            yield row


def detect_vendor_simple(text: str) -> str:
    """
    Simple vendor detection for analysis (avoid circular imports).
    Returns vendor name or 'OTHER'.
    """
    try:
        from parsing_engines.vendor_detection.data.vendor_detection_module_v9 import detect_vendor
        return detect_vendor(text)
    except ImportError:
        # Fallback: look for common vendor names
        text_upper = text.upper() if text else ''
        if 'WASTE CONNECTIONS' in text_upper:
            return 'Waste Connections'
        elif 'REPUBLIC SERVICES' in text_upper:
            return 'Republic Services'
        elif 'WASTE MANAGEMENT' in text_upper:
            return 'Waste Management'
        elif 'GFL' in text_upper:
            return 'GFL'
        elif 'RUMPKE' in text_upper:
            return 'Rumpke'
        return 'OTHER'


def extract_date_simple(text: str) -> Optional[str]:
    """
    Simple date extraction for analysis.
    Uses generic patterns only (no vendor-specific).
    """
    from parsing_engines.dates.date_extraction_engine import _extract_generic_date, normalize_ocr_text

    if not text:
        return None

    normalized = normalize_ocr_text(text)
    return _extract_generic_date(normalized)


def has_date_in_text(text: str) -> bool:
    """
    Check if text contains any date-like pattern.
    Used to identify if extraction SHOULD have worked.
    """
    if not text:
        return False

    # Common date patterns
    patterns = [
        r'\d{1,2}/\d{1,2}/\d{2,4}',  # MM/DD/YY or MM/DD/YYYY
        r'\d{1,2}-\d{1,2}-\d{2,4}',  # MM-DD-YY or MM-DD-YYYY
        r'\d{4}-\d{2}-\d{2}',        # YYYY-MM-DD
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s*\d{4}',
    ]

    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def analyze_failures(csv_path: str, limit: Optional[int] = None, verbose: bool = False) -> Tuple[Dict, Dict]:
    """
    Analyze date extraction failures grouped by vendor.

    Args:
        csv_path: Path to OCR CSV with raw_text column
        limit: Optional limit on rows to process
        verbose: Print progress

    Returns:
        Tuple of (vendor_stats, failure_samples)
    """
    vendor_stats = defaultdict(lambda: {
        'total': 0,
        'extracted': 0,
        'has_date': 0,  # Contains date but extraction failed
    })

    failure_samples = defaultdict(list)  # vendor -> list of (md5, text_snippet)

    # Determine text column name
    text_col = None

    print(f"Analyzing: {csv_path}")
    if limit:
        print(f"Limit: {limit} rows")

    for i, row in enumerate(load_csv_lazy(csv_path, limit)):
        # Find text column on first row
        if text_col is None:
            for col in ['raw_text', 'ocr_text', 'text', 'raw_ocr_text']:
                if col in row:
                    text_col = col
                    break
            if text_col is None:
                raise ValueError(f"No text column found. Available: {list(row.keys())}")
            print(f"Using column: {text_col}")

        text = row.get(text_col, '')
        md5 = row.get('md5_hash', row.get('md5', str(i)))

        # Detect vendor
        vendor = detect_vendor_simple(text)

        # Try extraction
        date = extract_date_simple(text)

        # Update stats
        vendor_stats[vendor]['total'] += 1
        if date:
            vendor_stats[vendor]['extracted'] += 1
        else:
            # Check if text has a date (extraction should have worked)
            if has_date_in_text(text):
                vendor_stats[vendor]['has_date'] += 1

                # Save sample for analysis (max 5 per vendor)
                if len(failure_samples[vendor]) < 5:
                    # Get snippet around date
                    snippet = text[:500] if len(text) > 500 else text
                    failure_samples[vendor].append({
                        'md5': md5,
                        'snippet': snippet
                    })

        if verbose and (i + 1) % 10000 == 0:
            print(f"  Processed {i + 1} rows...")

    return dict(vendor_stats), dict(failure_samples)


def print_report(vendor_stats: Dict, failure_samples: Dict, top_n: int = 20):
    """Print analysis report."""
    # Calculate totals
    total_invoices = sum(v['total'] for v in vendor_stats.values())
    total_extracted = sum(v['extracted'] for v in vendor_stats.values())
    total_has_date = sum(v['has_date'] for v in vendor_stats.values())

    print("\n" + "=" * 70)
    print("DATE EXTRACTION FAILURE ANALYSIS")
    print("=" * 70)

    print(f"\nOverall Statistics:")
    print(f"  Total invoices:     {total_invoices:,}")
    print(f"  Dates extracted:    {total_extracted:,} ({100*total_extracted/total_invoices:.1f}%)")
    print(f"  Failed (has date):  {total_has_date:,} ({100*total_has_date/total_invoices:.1f}%)")
    print(f"  Failed (no date):   {total_invoices - total_extracted - total_has_date:,}")

    # Sort by failures with date present (highest impact)
    sorted_vendors = sorted(
        vendor_stats.items(),
        key=lambda x: x[1]['has_date'],
        reverse=True
    )

    print(f"\n{'Vendor':<40} {'Total':>8} {'Extracted':>10} {'Failed*':>10} {'Rate':>8}")
    print("-" * 80)

    for vendor, stats in sorted_vendors[:top_n]:
        rate = 100 * stats['extracted'] / stats['total'] if stats['total'] > 0 else 0
        print(f"{vendor:<40} {stats['total']:>8,} {stats['extracted']:>10,} {stats['has_date']:>10,} {rate:>7.1f}%")

    print("\n* Failed = extraction failed but text contains date-like pattern")

    # Print sample failures for top vendors
    print("\n" + "=" * 70)
    print("SAMPLE FAILURES (Top 5 vendors by impact)")
    print("=" * 70)

    for vendor, stats in sorted_vendors[:5]:
        if vendor in failure_samples and failure_samples[vendor]:
            print(f"\n--- {vendor} ({stats['has_date']} failures) ---")
            for sample in failure_samples[vendor][:2]:
                print(f"\nMD5: {sample['md5']}")
                # Show first few lines
                lines = sample['snippet'].replace('\\n', '\n').split('\n')[:10]
                for line in lines:
                    print(f"  {line[:80]}")
                print("  ...")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m parsing_engines.dates.analyze_failures <ocr_csv_path> [--limit N]")
        print("\nExample:")
        print("  python -m parsing_engines.dates.analyze_failures training_data/ocr_chunks/raw_ocr_text.csv")
        print("  python -m parsing_engines.dates.analyze_failures data.csv --limit 10000")
        sys.exit(1)

    csv_path = sys.argv[1]

    # Parse optional limit
    limit = None
    if '--limit' in sys.argv:
        idx = sys.argv.index('--limit')
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])

    verbose = '--verbose' in sys.argv or '-v' in sys.argv

    if not os.path.exists(csv_path):
        print(f"Error: File not found: {csv_path}")
        sys.exit(1)

    vendor_stats, failure_samples = analyze_failures(csv_path, limit=limit, verbose=verbose)
    print_report(vendor_stats, failure_samples)


if __name__ == "__main__":
    main()
