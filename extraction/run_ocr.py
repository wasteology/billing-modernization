"""
Batch OCR runner — processes all invoice PDFs through Tesseract.

Outputs a single CSV: output/ocr_results.csv
Columns: pdf_filename, pdf_path, month_folder, site_code, vendor_name,
         raw_ocr_text, ocr_quality_score, document_type

Processes in batches, saves progress incrementally.
"""

import sys
import re
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ocr_pipeline import OCRPipeline, classify_document

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent / '031826'  # default, overridable via --input
OUTPUT_DIR = Path(__file__).parent / 'output'
OUTPUT_CSV = OUTPUT_DIR / 'ocr_results.csv'
REVIEW_CSV = OUTPUT_DIR / 'ocr_review.csv'

# Parse site code and vendor from filename
# Pattern: SITE_CODE - MONTH - VENDOR.pdf  (with variations)
FILENAME_RE = re.compile(
    r'^(?P<site>[A-Z]{2}[A-Z0-9]{2,4})'   # site code: 4-6 alphanum starting with 2 letters
    r'[\s\-]+'                               # separator
    r'(?P<month_part>.+?)'                   # month portion
    r'[\s\-]+'                               # separator
    r'(?P<vendor>.+?)'                       # vendor name
    r'(?:\s*\(\d+\))?'                       # optional duplicate number
    r'(?:\s*\d+(?:st|nd|rd|th)?\s*invoice)?'  # optional "2nd invoice" etc
    r'\.pdf$',                               # extension
    re.IGNORECASE
)


def parse_filename(filename: str) -> dict:
    """Extract site_code and vendor_name from filename."""
    m = FILENAME_RE.match(filename)
    if m:
        return {
            'site_code': m.group('site').upper(),
            'vendor_name': m.group('vendor').strip(),
        }
    # Fallback: try splitting on ' - '
    parts = filename.rsplit('.', 1)[0].split(' - ')
    if len(parts) >= 3:
        return {
            'site_code': parts[0].strip().upper(),
            'vendor_name': parts[-1].strip(),
        }
    # Last resort: try splitting on '-'
    parts = filename.rsplit('.', 1)[0].split('-')
    if len(parts) >= 3:
        return {
            'site_code': parts[0].strip().upper(),
            'vendor_name': parts[-1].strip(),
        }
    return {'site_code': '', 'vendor_name': ''}


def collect_pdfs() -> list[dict]:
    """Collect all PDFs with metadata. Walks recursively to handle any nesting depth."""
    pdfs = []
    for pdf_path in sorted(BASE_DIR.rglob('*.pdf')):
        # month_folder = first subdirectory relative to BASE_DIR
        rel = pdf_path.relative_to(BASE_DIR)
        month_name = rel.parts[0] if len(rel.parts) > 1 else ''
        info = parse_filename(pdf_path.name)
        # If site_code not in filename, try to extract from parent folder name
        if not info['site_code'] and pdf_path.parent != BASE_DIR:
            folder_site = re.match(r'^([A-Z]{2}[A-Z0-9]{2,6})', pdf_path.parent.name)
            if folder_site:
                info['site_code'] = folder_site.group(1).upper()
        info['pdf_filename'] = pdf_path.name
        info['pdf_path'] = str(pdf_path)
        info['month_folder'] = month_name
        pdfs.append(info)
    return pdfs


def load_completed() -> set:
    """Load already-processed pdf_paths from output CSV."""
    if OUTPUT_CSV.exists():
        df = pd.read_csv(OUTPUT_CSV, usecols=['pdf_path'])
        return set(df['pdf_path'].tolist())
    return set()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=str, help='Input directory (overrides default BASE_DIR)')
    parser.add_argument('--output-csv', type=str, help='Output CSV path (overrides default)')
    args = parser.parse_args()

    global BASE_DIR, OUTPUT_CSV, REVIEW_CSV
    if args.input:
        BASE_DIR = Path(__file__).parent / args.input
    if args.output_csv:
        OUTPUT_CSV = Path(args.output_csv)
        REVIEW_CSV = OUTPUT_CSV.parent / OUTPUT_CSV.name.replace('.csv', '_review.csv')

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    all_pdfs = collect_pdfs()
    logger.info(f"Found {len(all_pdfs)} PDFs across {len(set(p['month_folder'] for p in all_pdfs))} months")

    completed = load_completed()
    remaining = [p for p in all_pdfs if p['pdf_path'] not in completed]
    logger.info(f"Already processed: {len(completed)}, remaining: {len(remaining)}")

    if not remaining:
        logger.info("All PDFs already processed!")
        return

    # Use a dummy pipeline just for the OCR method
    pipeline = OCRPipeline(BASE_DIR)
    if not pipeline.tesseract_available:
        logger.error("Tesseract not available!")
        sys.exit(1)

    results = []
    review = []
    start_time = time.time()
    BATCH_SAVE = 50  # save progress every 50 PDFs

    for i, pdf_info in enumerate(remaining, 1):
        pdf_path = Path(pdf_info['pdf_path'])

        ocr_text = pipeline.extract_text_from_pdf(pdf_path)

        if not ocr_text or len(ocr_text.strip()) < 50:
            review.append({
                **pdf_info,
                'ocr_quality_score': 0,
                'document_type': 'unknown',
                'reason': 'OCR_FAILURE' if not ocr_text else 'TEXT_TOO_SHORT',
            })
            continue

        quality_score = pipeline.score_ocr_quality(ocr_text)
        doc_type = classify_document(ocr_text)

        if quality_score < 5 and len(ocr_text.strip()) < 200:
            review.append({
                **pdf_info,
                'ocr_quality_score': quality_score,
                'document_type': doc_type,
                'reason': 'OCR_QUALITY_FAILURE',
            })
            continue

        results.append({
            'pdf_filename': pdf_info['pdf_filename'],
            'pdf_path': pdf_info['pdf_path'],
            'month_folder': pdf_info['month_folder'],
            'site_code': pdf_info['site_code'],
            'vendor_name': pdf_info['vendor_name'],
            'raw_ocr_text': ocr_text,
            'ocr_quality_score': quality_score,
            'document_type': doc_type,
        })

        # Progress logging
        if i % 10 == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed
            eta = (len(remaining) - i) / rate if rate > 0 else 0
            logger.info(
                f"  Progress: {i}/{len(remaining)} "
                f"({i/len(remaining)*100:.1f}%) | "
                f"{rate:.1f} pdf/s | "
                f"ETA: {eta/60:.0f}m | "
                f"OK: {len(results)}, Review: {len(review)}"
            )

        # Incremental save
        if i % BATCH_SAVE == 0 and results:
            _save_batch(results, review)
            results.clear()
            review.clear()

    # Final save
    if results or review:
        _save_batch(results, review)

    # Final summary
    elapsed = time.time() - start_time
    total_ok = len(pd.read_csv(OUTPUT_CSV)) if OUTPUT_CSV.exists() else 0
    total_review = len(pd.read_csv(REVIEW_CSV)) if REVIEW_CSV.exists() else 0
    logger.info(f"\nOCR COMPLETE in {elapsed/60:.1f} minutes")
    logger.info(f"  Success: {total_ok}")
    logger.info(f"  Review:  {total_review}")
    logger.info(f"  Output:  {OUTPUT_CSV}")


def _save_batch(results: list, review: list):
    """Append batch results to CSV files."""
    if results:
        df = pd.DataFrame(results)
        if OUTPUT_CSV.exists():
            df.to_csv(OUTPUT_CSV, mode='a', header=False, index=False)
        else:
            df.to_csv(OUTPUT_CSV, index=False)

    if review:
        df_r = pd.DataFrame(review)
        if REVIEW_CSV.exists():
            df_r.to_csv(REVIEW_CSV, mode='a', header=False, index=False)
        else:
            df_r.to_csv(REVIEW_CSV, index=False)


if __name__ == '__main__':
    main()
