"""
Vendor Detection V9 Test Script
Run locally to validate detection accuracy against OCR data.

Usage:
    python test_vendor_detection_v9.py

Inputs:
    - raw_ocr_text.csv (md5_hash, raw_text)
    - vendor_detection_module_v9.py (in same directory)

Outputs:
    - detection_results.csv: All detections
    - detection_summary.csv: Counts by vendor
    - undetected_samples.csv: Sample of invoices with no vendor match
    - detection_samples.csv: Random samples per vendor for manual review
"""

import pandas as pd
import os
from pathlib import Path
from collections import Counter
import random

# Import the detection module (must be in same directory)
from vendor_detection_module_v9 import detect_vendor

# =============================================================================
# CONFIGURATION
# =============================================================================

DATA_DIR = Path(r"C:\Users\sstclair\OneDrive - Wasteology Group\Desktop\Hauler Bill Parsing\01_vendor_name\data")
OCR_FILE = "raw_ocr_text.csv"
OUTPUT_DIR = DATA_DIR / "test_results"

# How many samples per vendor to save for manual review
SAMPLES_PER_VENDOR = 5
RANDOM_SEED = 42

# =============================================================================
# MAIN SCRIPT
# =============================================================================

def main():
    random.seed(RANDOM_SEED)
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    print("=" * 60)
    print("VENDOR DETECTION V9 TEST")
    print("=" * 60)
    
    # Load OCR data
    ocr_path = DATA_DIR / OCR_FILE
    print(f"\nLoading: {ocr_path}")
    
    if not ocr_path.exists():
        print(f"ERROR: File not found: {ocr_path}")
        print(f"Make sure {OCR_FILE} is in {DATA_DIR}")
        return
    
    df = pd.read_csv(ocr_path)
    print(f"Loaded {len(df):,} invoices")
    print(f"Columns: {list(df.columns)}")
    
    # Run detection
    print("\nRunning vendor detection...")
    results = []
    
    for i, row in df.iterrows():
        md5 = row['md5_hash']
        text = str(row['raw_text']) if pd.notna(row['raw_text']) else ''
        
        vendor = detect_vendor(text)
        results.append({
            'md5_hash': md5,
            'detected_vendor': vendor,
            'text_preview': text[:200].replace('\n', ' ').replace('\\n', ' ')
        })
        
        if (i + 1) % 10000 == 0:
            print(f"  Processed {i + 1:,} / {len(df):,}")
    
    results_df = pd.DataFrame(results)
    
    # ==========================================================================
    # OUTPUT 1: All detection results
    # ==========================================================================
    results_path = OUTPUT_DIR / "detection_results.csv"
    results_df.to_csv(results_path, index=False)
    print(f"\nSaved: {results_path}")
    
    # ==========================================================================
    # OUTPUT 2: Summary by vendor
    # ==========================================================================
    vendor_counts = results_df['detected_vendor'].value_counts()
    summary_df = pd.DataFrame({
        'vendor': vendor_counts.index,
        'count': vendor_counts.values,
        'pct': (vendor_counts.values / len(results_df) * 100).round(2)
    })
    
    summary_path = OUTPUT_DIR / "detection_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"Saved: {summary_path}")
    
    # ==========================================================================
    # OUTPUT 3: Undetected samples
    # ==========================================================================
    undetected = results_df[results_df['detected_vendor'] == 'Unknown']
    undetected_sample = undetected.sample(min(100, len(undetected)), random_state=RANDOM_SEED)
    
    undetected_path = OUTPUT_DIR / "undetected_samples.csv"
    undetected_sample.to_csv(undetected_path, index=False)
    print(f"Saved: {undetected_path}")
    
    # ==========================================================================
    # OUTPUT 4: Samples per vendor for manual review
    # ==========================================================================
    samples = []
    for vendor in results_df['detected_vendor'].unique():
        if vendor == 'Unknown':
            continue
        vendor_df = results_df[results_df['detected_vendor'] == vendor]
        n = min(SAMPLES_PER_VENDOR, len(vendor_df))
        vendor_sample = vendor_df.sample(n, random_state=RANDOM_SEED)
        samples.append(vendor_sample)
    
    if samples:
        samples_df = pd.concat(samples, ignore_index=True)
        samples_path = OUTPUT_DIR / "detection_samples.csv"
        samples_df.to_csv(samples_path, index=False)
        print(f"Saved: {samples_path}")
    
    # ==========================================================================
    # PRINT SUMMARY
    # ==========================================================================
    detected = len(results_df[results_df['detected_vendor'] != 'Unknown'])
    detection_rate = detected / len(results_df) * 100
    
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"Total invoices:     {len(results_df):,}")
    print(f"Detected:           {detected:,} ({detection_rate:.1f}%)")
    print(f"Undetected:         {len(undetected):,} ({100 - detection_rate:.1f}%)")
    print(f"Unique vendors:     {len(vendor_counts) - 1}")  # -1 for Unknown
    
    print("\nTop 20 Detected Vendors:")
    print("-" * 40)
    for vendor, count in vendor_counts.head(20).items():
        if vendor != 'Unknown':
            print(f"  {count:>6,}  {vendor}")
    
    print("\n" + "=" * 60)
    print("MANUAL REVIEW")
    print("=" * 60)
    print(f"Review these files in: {OUTPUT_DIR}")
    print("  1. detection_samples.csv - Check for FALSE POSITIVES")
    print("     (Is the detected vendor actually on that invoice?)")
    print("  2. undetected_samples.csv - Check for FALSE NEGATIVES")
    print("     (Can you identify a vendor that should have been detected?)")


if __name__ == "__main__":
    main()
