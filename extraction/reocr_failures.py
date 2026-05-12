#!/home/scstclair/projects/.venv/bin/python
"""
Re-OCR invoices with UNDER_CAPTURE or DIFF status.

Reads invoice_tracker.csv for failures, re-runs OCR via OCRPipeline,
and replaces ocr_results.csv rows where the new OCR is better
(more decimal amounts or longer text).
"""

import csv
import re
import sys
import logging
from pathlib import Path

from ocr_pipeline import OCRPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (relative to invoices/ working directory)
# ---------------------------------------------------------------------------
TRACKER_PATH = Path("output/invoice_tracker.csv")
OCR_RESULTS_PATH = Path("output/ocr_results.csv")
TARGET_STATUSES = {"UNDER_CAPTURE", "DIFF"}


def count_amounts(text: str) -> int:
    """Count decimal amount patterns (e.g. 123.45) in text."""
    return len(re.findall(r"\d+\.\d{2}", text))


def fix_pdf_path(raw_path: str) -> str:
    """Fix stale uppercase /Invoices/ -> /invoices/ in pdf_path."""
    return raw_path.replace("/Invoices/", "/invoices/")


def collect_failure_filenames() -> set:
    """Read invoice_tracker.csv and return pdf_filenames with target statuses."""
    filenames = set()
    with open(TRACKER_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status", "").strip() in TARGET_STATUSES:
                filenames.add(row["pdf_filename"].strip())
    log.info("Found %d invoices with status in %s", len(filenames), TARGET_STATUSES)
    return filenames


def load_ocr_results():
    """
    Load ocr_results.csv into a list of dicts + fieldnames.
    Build index of pdf_filename -> list index for fast lookup.
    """
    with open(OCR_RESULTS_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    index = {}
    for i, row in enumerate(rows):
        index[row["pdf_filename"].strip()] = i
    log.info("Loaded %d rows from ocr_results.csv", len(rows))
    return rows, fieldnames, index


def save_ocr_results(rows, fieldnames):
    """Write updated rows back to ocr_results.csv."""
    with open(OCR_RESULTS_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    log.info("Wrote %d rows to ocr_results.csv", len(rows))


def main():
    # ------------------------------------------------------------------
    # 1. Collect failure filenames from tracker
    # ------------------------------------------------------------------
    failure_filenames = collect_failure_filenames()
    if not failure_filenames:
        log.info("No UNDER_CAPTURE or DIFF invoices found. Nothing to do.")
        return

    # ------------------------------------------------------------------
    # 2. Load ocr_results and build index
    # ------------------------------------------------------------------
    rows, fieldnames, index = load_ocr_results()

    # Match failures to ocr_results rows
    targets = []  # list of (pdf_filename, row_index, pdf_path)
    missing = []
    for fn in sorted(failure_filenames):
        if fn in index:
            row = rows[index[fn]]
            pdf_path = fix_pdf_path(row["pdf_path"].strip())
            targets.append((fn, index[fn], pdf_path))
        else:
            missing.append(fn)

    if missing:
        log.warning(
            "%d failure filenames not found in ocr_results.csv: %s",
            len(missing),
            missing[:5],
        )

    log.info("Will re-OCR %d PDFs", len(targets))

    # ------------------------------------------------------------------
    # 3. Initialize OCR pipeline (needs a directory but we use
    #    extract_text_from_pdf directly with absolute paths)
    # ------------------------------------------------------------------
    # Use the parent of the first PDF as a dummy directory
    if not targets:
        log.info("No valid targets after matching. Nothing to do.")
        return

    dummy_dir = Path(targets[0][2]).parent
    pipeline = OCRPipeline(dummy_dir)

    # ------------------------------------------------------------------
    # 4. Re-OCR each PDF and compare
    # ------------------------------------------------------------------
    improved = []
    unchanged = []
    failed = []

    for pdf_filename, row_idx, pdf_path in targets:
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            log.warning("  SKIP  %s — file not found: %s", pdf_filename, pdf_path)
            failed.append((pdf_filename, "file_not_found"))
            continue

        old_text = rows[row_idx].get("raw_ocr_text", "")
        old_amounts = count_amounts(old_text)
        old_len = len(old_text)

        log.info("  OCR   %s  (old: %d amounts, %d chars)", pdf_filename, old_amounts, old_len)

        new_text = pipeline.extract_text_from_pdf(pdf_file)

        if new_text is None:
            log.warning("  FAIL  %s — OCR returned None", pdf_filename)
            failed.append((pdf_filename, "ocr_returned_none"))
            continue

        new_amounts = count_amounts(new_text)
        new_len = len(new_text)
        new_score = OCRPipeline.score_ocr_quality(new_text)

        # Decide: replace if new OCR has more amounts OR is longer
        if new_amounts > old_amounts or new_len > old_len:
            rows[row_idx]["raw_ocr_text"] = new_text
            rows[row_idx]["ocr_quality_score"] = str(new_score)
            improved.append(
                (pdf_filename, old_amounts, new_amounts, old_len, new_len)
            )
            log.info(
                "  UP    %s  amounts %d->%d  chars %d->%d",
                pdf_filename, old_amounts, new_amounts, old_len, new_len,
            )
        else:
            unchanged.append(
                (pdf_filename, old_amounts, new_amounts, old_len, new_len)
            )
            log.info(
                "  SAME  %s  amounts %d->%d  chars %d->%d",
                pdf_filename, old_amounts, new_amounts, old_len, new_len,
            )

    # ------------------------------------------------------------------
    # 5. Write back if anything improved
    # ------------------------------------------------------------------
    if improved:
        save_ocr_results(rows, fieldnames)
    else:
        log.info("No improvements found — ocr_results.csv unchanged.")

    # ------------------------------------------------------------------
    # 6. Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print(f"RE-OCR SUMMARY: {len(targets)} PDFs processed")
    print("=" * 72)

    if improved:
        print(f"\nIMPROVED ({len(improved)}):")
        for fn, old_a, new_a, old_l, new_l in improved:
            print(f"  {fn}")
            print(f"    amounts: {old_a} -> {new_a}  chars: {old_l} -> {new_l}")

    if unchanged:
        print(f"\nUNCHANGED ({len(unchanged)}):")
        for fn, old_a, new_a, old_l, new_l in unchanged:
            print(f"  {fn}")
            print(f"    amounts: {old_a} -> {new_a}  chars: {old_l} -> {new_l}")

    if failed:
        print(f"\nFAILED ({len(failed)}):")
        for fn, reason in failed:
            print(f"  {fn}  ({reason})")

    print()


if __name__ == "__main__":
    main()
