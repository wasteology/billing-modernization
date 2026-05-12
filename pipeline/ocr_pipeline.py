"""
OCR Pipeline — PDF to text conversion.
========================================

Pure OCR step: converts PDF invoices to lines of text.
No entity considerations whatsoever — those are handled downstream.

Includes:
- Tesseract OCR with automatic rotation retry (8 configs)
- OCR quality scoring (0-15 scale)
- Document type classification (invoice / report / unknown)
- Quality gate: route failures to review, don't propagate

Design principle: we don't propagate failures or issues through the pipeline.
"""

import re
import logging
import subprocess
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Import OCR dependencies
try:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError as e:
    OCR_AVAILABLE = False
    logger.warning(f"OCR dependencies not available: {e}")


class OCRConfig:
    """Configuration for OCR processing."""

    TESSERACT_LANG = 'eng'
    TESSERACT_CONFIG = '--psm 6'

    # PDF preprocessing
    DPI = 300
    GRAYSCALE = True

    # Quality thresholds
    QUALITY_MIN_SCORE = 5        # Below this + short text = quality failure
    QUALITY_MIN_TEXT_LEN = 200   # Minimum text length for quality gate
    QUALITY_GOOD_SCORE = 8       # Above this = good enough, stop retrying

    # Retry configs: (rotation_degrees, psm_mode)
    RETRY_CONFIGS = [
        (0, 6),      # Default: no rotation, uniform block
        (180, 6),    # Upside down (most common rotation issue)
        (270, 6),    # Rotated left (landscape)
        (90, 6),     # Rotated right (landscape)
        (0, 3),      # No rotation, fully automatic PSM
        (0, 4),      # No rotation, single column
        (180, 3),    # Upside down, fully automatic PSM
        (270, 3),    # Rotated left, fully automatic PSM
    ]


def classify_document(ocr_text: str) -> str:
    """
    Classify document type from OCR text.

    Returns 'invoice', 'report', or 'unknown'.
    Only invoices should be processed downstream.
    """
    if not ocr_text or len(ocr_text.strip()) < 50:
        return 'unknown'

    text_upper = ocr_text.upper()

    # Invoice indicators
    invoice_score = sum([
        'INVOICE' in text_upper,
        'ACCOUNT' in text_upper,
        bool(re.search(r'AMOUNT\s+DUE|TOTAL\s+DUE|BALANCE\s+DUE', text_upper)),
        bool(re.search(r'\$[\d,]+\.\d{2}', ocr_text)),
        'REMIT TO' in text_upper,
        bool(re.search(r'SERVICE\s+(?:DATE|PERIOD|ADDRESS)', text_upper)),
    ])

    # Non-invoice indicators
    report_score = sum([
        'LEED' in text_upper,
        'CERTIFICATION' in text_upper and 'INVOICE' not in text_upper,
        'TONNAGE REPORT' in text_upper,
        'MANIFEST' in text_upper,
        'WEIGHT TICKET' in text_upper and 'INVOICE' not in text_upper,
    ])

    if invoice_score >= 3:
        return 'invoice'
    if report_score >= 2:
        return 'report'
    return 'unknown'


class OCRPipeline:
    """
    OCR pipeline for processing PDF invoices.

    Converts PDFs to text using Tesseract OCR with rotation retry.
    Scores quality and classifies document type.
    Routes failures to review — does NOT propagate bad data downstream.

    No entity extraction. That's handled by downstream steps.
    """

    def __init__(self, pdf_directory: Path):
        self.pdf_directory = Path(pdf_directory)
        self.tesseract_available = self._check_tesseract()

        logger.info("OCR Pipeline initialized")
        logger.info(f"  PDF directory: {self.pdf_directory}")
        logger.info(f"  Tesseract available: {self.tesseract_available}")

    def _check_tesseract(self) -> bool:
        """Check if Tesseract is installed."""
        try:
            result = subprocess.run(
                ['tesseract', '--version'],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def score_ocr_quality(text: str) -> int:
        """
        Score OCR output quality 0-15. Higher = better.

        Checks: keyword presence, ASCII ratio, word length, digit presence,
        line structure.
        """
        if not text or len(text.strip()) < 50:
            return 0

        score = 0

        # 1. Invoice keyword detection (0-5 points)
        invoice_keywords = [
            r'\binvoice\b', r'\baccount\b', r'\btotal\b', r'\bdate\b',
            r'\bservice\b', r'\bcharge\b', r'\bamount\b', r'\bpayment\b',
            r'\baddress\b', r'\bphone\b', r'\bbill\b', r'\bpickup\b',
            r'\byard[s]?\b', r'\bwaste\b', r'\brecycl', r'\btrash\b',
            r'\bcontainer\b', r'\bhauling\b', r'\bdisposal\b',
            r'\bmonthly\b', r'\bweekly\b', r'\bquarterly\b',
        ]
        keyword_hits = sum(
            1 for kw in invoice_keywords
            if re.search(kw, text, re.IGNORECASE)
        )
        score += min(keyword_hits, 5)

        # 2. ASCII printable ratio (0-3 points)
        printable = sum(1 for c in text if c.isprintable() or c in '\n\r\t')
        ratio = printable / len(text) if text else 0
        if ratio > 0.95:
            score += 3
        elif ratio > 0.85:
            score += 2
        elif ratio > 0.70:
            score += 1

        # 3. Word length distribution (0-3 points)
        words = text.split()
        if words:
            avg_len = sum(len(w) for w in words) / len(words)
            if 3.0 <= avg_len <= 9.0:
                score += 3
            elif 2.5 <= avg_len <= 12.0:
                score += 2
            elif 2.0 <= avg_len <= 15.0:
                score += 1

        # 4. Digit presence (0-2 points) — invoices always have numbers
        digits = sum(1 for c in text if c.isdigit())
        digit_ratio = digits / len(text) if text else 0
        if 0.03 <= digit_ratio <= 0.30:
            score += 2
        elif 0.01 <= digit_ratio <= 0.40:
            score += 1

        # 5. Line structure (0-2 points)
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            line_lens = [len(l) for l in lines]
            avg_line = sum(line_lens) / len(line_lens)
            if 10 <= avg_line <= 80 and len(lines) >= 5:
                score += 2
            elif 5 <= avg_line <= 120 and len(lines) >= 3:
                score += 1

        return score

    def _ocr_single_config(self, image: 'Image.Image', rotation: int, psm: int) -> str:
        """Run OCR on an image with a specific rotation and PSM mode."""
        img = image.copy()

        if rotation != 0:
            img = img.rotate(-rotation, expand=True)

        if img.mode != 'L':
            img = img.convert('L')

        config = f'--psm {psm}'
        text = pytesseract.image_to_string(
            img, lang=OCRConfig.TESSERACT_LANG, config=config
        )
        return text

    def extract_text_from_pdf(self, pdf_path: Path) -> Optional[str]:
        """
        Extract text from PDF using Tesseract OCR.

        Tries multiple rotation/PSM configurations, picks the best result.
        Stops early if good quality found.

        Returns raw text or None if failed.
        """
        if not self.tesseract_available or not OCR_AVAILABLE:
            logger.warning("Tesseract/OCR not available, skipping")
            return None

        logger.debug(f"  Processing: {pdf_path.name}")

        try:
            images = convert_from_path(
                pdf_path, dpi=OCRConfig.DPI, grayscale=OCRConfig.GRAYSCALE
            )

            # Try default config first
            default_rot, default_psm = OCRConfig.RETRY_CONFIGS[0]
            all_text = []
            for image in images:
                text = self._ocr_single_config(image, default_rot, default_psm)
                all_text.append(text)

            best_text = '\n'.join(all_text)
            best_score = self.score_ocr_quality(best_text)

            if best_score >= OCRConfig.QUALITY_GOOD_SCORE:
                logger.debug(f"    {len(best_text)} chars, quality={best_score} (good)")
                return best_text

            # Quality below threshold — try alternative configs
            logger.debug(f"    Quality {best_score}<{OCRConfig.QUALITY_GOOD_SCORE}, retrying...")

            for rotation, psm in OCRConfig.RETRY_CONFIGS[1:]:
                try:
                    retry_parts = []
                    for image in images:
                        text = self._ocr_single_config(image, rotation, psm)
                        retry_parts.append(text)

                    retry_text = '\n'.join(retry_parts)
                    retry_score = self.score_ocr_quality(retry_text)

                    if retry_score > best_score:
                        best_text = retry_text
                        best_score = retry_score

                    if best_score >= OCRConfig.QUALITY_GOOD_SCORE:
                        break

                except Exception as e:
                    logger.debug(f"      rot={rotation}, psm={psm}: failed ({e})")
                    continue

            logger.debug(f"    Final: {len(best_text)} chars, quality={best_score}")
            return best_text

        except Exception as e:
            logger.error(f"  OCR failed for {pdf_path.name}: {e}")
            return None

    def process_pdf_directory(
        self,
        limit: Optional[int] = None,
        recursive: bool = True
    ) -> pd.DataFrame:
        """
        Process all PDFs in directory. Pure OCR — no entity extraction.

        Output columns: pdf_filename, pdf_path, raw_ocr_text,
                        ocr_quality_score, document_type

        Quality gate: records with score < QUALITY_MIN_SCORE and
        text < QUALITY_MIN_TEXT_LEN are routed to review CSV.
        """
        logger.info(f"Processing PDFs in {self.pdf_directory}...")

        if not self.pdf_directory.exists():
            logger.error(f"Directory not found: {self.pdf_directory}")
            return pd.DataFrame()

        if recursive:
            pdf_files = list(self.pdf_directory.rglob("*.pdf"))
            pdf_files += list(self.pdf_directory.rglob("*.PDF"))
        else:
            pdf_files = list(self.pdf_directory.glob("*.pdf"))
            pdf_files += list(self.pdf_directory.glob("*.PDF"))

        # Deduplicate by name
        seen = set()
        unique = []
        for p in pdf_files:
            if p.name not in seen:
                seen.add(p.name)
                unique.append(p)
        pdf_files = unique

        logger.info(f"  Found {len(pdf_files)} unique PDF files")

        if limit:
            pdf_files = pdf_files[:limit]
            logger.info(f"  Processing first {limit} files only")

        results = []
        quality_failures = []
        ocr_failures = 0

        for i, pdf_path in enumerate(pdf_files, 1):
            if i % 50 == 0:
                logger.info(f"  Progress: {i}/{len(pdf_files)}")

            ocr_text = self.extract_text_from_pdf(pdf_path)

            if not ocr_text or len(ocr_text.strip()) < 50:
                ocr_failures += 1
                continue

            quality_score = self.score_ocr_quality(ocr_text)
            doc_type = classify_document(ocr_text)

            # Quality gate: don't propagate failures
            if (quality_score < OCRConfig.QUALITY_MIN_SCORE
                    and len(ocr_text.strip()) < OCRConfig.QUALITY_MIN_TEXT_LEN):
                quality_failures.append({
                    'pdf_filename': pdf_path.name,
                    'pdf_path': str(pdf_path),
                    'ocr_quality_score': quality_score,
                    'ocr_text_length': len(ocr_text.strip()),
                    'document_type': doc_type,
                    'reason': 'OCR_QUALITY_FAILURE',
                })
                continue  # Don't propagate

            results.append({
                'pdf_filename': pdf_path.name,
                'pdf_path': str(pdf_path),
                'raw_ocr_text': ocr_text,
                'ocr_quality_score': quality_score,
                'document_type': doc_type,
            })

        df = pd.DataFrame(results)

        # Summary
        logger.info(f"  OCR complete: {len(df)} succeeded, "
                     f"{ocr_failures} OCR failures, "
                     f"{len(quality_failures)} quality failures")

        if len(df) > 0:
            for dt, cnt in df['document_type'].value_counts().items():
                logger.info(f"    {dt}: {cnt}")

        # Save quality failures to review
        if quality_failures:
            review_dir = self.pdf_directory.parent / 'review'
            review_dir.mkdir(parents=True, exist_ok=True)
            review_path = review_dir / 'ocr_quality_review.csv'
            pd.DataFrame(quality_failures).to_csv(review_path, index=False)
            logger.warning(f"  {len(quality_failures)} quality failures saved to {review_path}")

        return df


def setup_ocr_dependencies():
    """Check and guide setup of OCR dependencies."""
    instructions = """
    OCR Pipeline Dependencies Setup
    ================================

    Required packages:

    1. Tesseract OCR:
       Ubuntu/Debian: sudo apt-get install tesseract-ocr
       macOS: brew install tesseract
       Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki

    2. Poppler (for PDF to image):
       Ubuntu/Debian: sudo apt-get install poppler-utils
       macOS: brew install poppler
       Windows: Download from https://github.com/oschwartz10612/poppler-windows

    3. Python packages:
       pip install pytesseract pdf2image Pillow

    Verify installation:
       tesseract --version
       python -c "import pytesseract; print('OK')"
    """

    print(instructions)

    checks = {'tesseract': False, 'pytesseract': False, 'pdf2image': False}

    try:
        subprocess.run(['tesseract', '--version'], capture_output=True, timeout=5)
        checks['tesseract'] = True
    except Exception:
        pass

    try:
        import pytesseract  # noqa: F811
        checks['pytesseract'] = True
    except ImportError:
        pass

    try:
        import pdf2image  # noqa: F811
        checks['pdf2image'] = True
    except ImportError:
        pass

    print("\nDependency Status:")
    for dep, status in checks.items():
        print(f"  {dep}: {'OK' if status else 'NOT FOUND'}")

    all_ready = all(checks.values())
    print(f"\nOCR Pipeline Ready: {'YES' if all_ready else 'NO'}")
    return all_ready


if __name__ == "__main__":
    setup_ocr_dependencies()
