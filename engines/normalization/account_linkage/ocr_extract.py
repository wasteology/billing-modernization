#!/usr/bin/env python3
"""
OCR Extraction Pipeline

Extracts vendor, account number, and invoice number from raw OCR text.
Uses parsing_engines modules for extraction.

Pipeline Steps:
1. vendor   - Detect vendor from OCR text
2. account  - Extract account number using vendor-specific patterns
3. invoice  - Extract invoice number using vendor-specific patterns

Output: ocr_step3_invoices.csv with columns:
- md5_hash: Unique document identifier
- detected_vendor: Detected vendor name
- raw_text: Original OCR text
- account_number: Extracted account (may be null)
- invoice_number: Extracted invoice (may be null)
"""

import pandas as pd
import sys
import time
from pathlib import Path
from typing import Optional

# Add parsing_engines to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent))

try:
    from parsing_engines.vendor_detection.data.vendor_detection_module_v9 import detect_vendor
    from parsing_engines.account_number.account_extraction_engine import extract_account
    from parsing_engines.invoice_number.invoice_extraction_engine import extract_invoice_number as extract_invoice
except ImportError as e:
    print(f"Error importing parsing_engines: {e}")
    print("Make sure parsing_engines is available in the project root")
    sys.exit(1)


def run_extraction(
    ocr_path: str,
    output_dir: str,
    step: str = 'all'
) -> None:
    """
    Run OCR extraction pipeline.

    Args:
        ocr_path: Path to raw OCR CSV (must have md5_hash, raw_text columns)
        output_dir: Directory to save output files
        step: Which step to run ('vendor', 'account', 'invoice', 'all')
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if step in ('vendor', 'all'):
        print("Step 1: Vendor Detection")
        print("=" * 50)
        _run_vendor_detection(ocr_path, output_dir)

    if step in ('account', 'all'):
        print("\nStep 2: Account Extraction")
        print("=" * 50)
        _run_account_extraction(output_dir)

    if step in ('invoice', 'all'):
        print("\nStep 3: Invoice Extraction")
        print("=" * 50)
        _run_invoice_extraction(output_dir)


def _run_vendor_detection(ocr_path: str, output_dir: Path) -> None:
    """Detect vendors from raw OCR text."""
    print(f"Loading OCR from {ocr_path}...")
    df = pd.read_csv(ocr_path, dtype=str)
    print(f"  {len(df):,} records")

    results = []
    detected = 0
    start = time.time()

    for i, row in df.iterrows():
        if i % 25000 == 0 and i > 0:
            elapsed = time.time() - start
            print(f"  {i:,}/{len(df):,} ({elapsed:.0f}s)")

        md5 = str(row.get('md5_hash', ''))
        text = str(row.get('raw_text', ''))

        vendor = detect_vendor(text)
        if vendor and vendor != 'OTHER':
            detected += 1

        results.append({
            'md5_hash': md5,
            'detected_vendor': vendor or '',
            'raw_text': text
        })

    output = output_dir / 'ocr_step1_vendors.csv'
    pd.DataFrame(results).to_csv(output, index=False)

    print(f"\nDetected vendors: {detected:,} ({detected/len(df)*100:.1f}%)")
    print(f"Saved to {output}")


def _run_account_extraction(output_dir: Path) -> None:
    """Extract account numbers from vendor-detected OCR."""
    input_file = output_dir / 'ocr_step1_vendors.csv'
    if not input_file.exists():
        print(f"Error: {input_file} not found. Run vendor step first.")
        return

    print(f"Loading {input_file}...")
    df = pd.read_csv(input_file, dtype=str)
    print(f"  {len(df):,} records")

    extracted = 0
    start = time.time()

    for i, row in df.iterrows():
        if i % 25000 == 0 and i > 0:
            elapsed = time.time() - start
            print(f"  {i:,}/{len(df):,} ({elapsed:.0f}s)")

        vendor = str(row.get('detected_vendor', ''))
        text = str(row.get('raw_text', ''))

        account = None
        if vendor and vendor != 'OTHER':
            account = extract_account(vendor, text)

        if account:
            extracted += 1
            df.at[i, 'account_number'] = account
        else:
            df.at[i, 'account_number'] = ''

    output = output_dir / 'ocr_step2_accounts.csv'
    df.to_csv(output, index=False)

    print(f"\nExtracted accounts: {extracted:,} ({extracted/len(df)*100:.1f}%)")
    print(f"Saved to {output}")


def _run_invoice_extraction(output_dir: Path) -> None:
    """Extract invoice numbers from account-extracted OCR."""
    input_file = output_dir / 'ocr_step2_accounts.csv'
    if not input_file.exists():
        print(f"Error: {input_file} not found. Run account step first.")
        return

    print(f"Loading {input_file}...")
    df = pd.read_csv(input_file, dtype=str)
    print(f"  {len(df):,} records")

    extracted = 0
    start = time.time()

    for i, row in df.iterrows():
        if i % 25000 == 0 and i > 0:
            elapsed = time.time() - start
            print(f"  {i:,}/{len(df):,} ({elapsed:.0f}s)")

        vendor = str(row.get('detected_vendor', ''))
        text = str(row.get('raw_text', ''))

        invoice = None
        if vendor and vendor != 'OTHER':
            invoice = extract_invoice(vendor, text)

        if invoice:
            extracted += 1
            df.at[i, 'invoice_number'] = invoice
        else:
            df.at[i, 'invoice_number'] = ''

    output = output_dir / 'ocr_step3_invoices.csv'
    df.to_csv(output, index=False)

    print(f"\nExtracted invoices: {extracted:,} ({extracted/len(df)*100:.1f}%)")
    print(f"Saved to {output}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='OCR Extraction Pipeline')
    parser.add_argument('step', choices=['vendor', 'account', 'invoice', 'all'],
                        help='Which extraction step to run')
    parser.add_argument('--ocr', help='Path to raw OCR CSV (required for vendor step)')
    parser.add_argument('--output-dir', default='./data/output',
                        help='Output directory for results')

    args = parser.parse_args()

    if args.step in ('vendor', 'all') and not args.ocr:
        parser.error("--ocr is required for vendor step")

    run_extraction(
        ocr_path=args.ocr or '',
        output_dir=args.output_dir,
        step=args.step
    )
