"""Invoice rendering from Document AI data.

Fetches Document AI JSON from GCS and extracts:
- Page images (base64 JPEG) for human review
- Text blocks with bounding boxes for spatial analysis

Usage:
    from .invoice_renderer import save_invoice_image, render_invoice

    # Save just the page image for human review
    path = save_invoice_image("abc123md5", output_dir=Path("data/bills/"))

    # Full HTML render with embedded image
    path = render_invoice("abc123md5")
"""

import base64
import csv
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

GCS_PROJECT = "academic-torch-405913"
GCS_BUCKET = "invoice_inference_json_output"

DATA_DIR = Path(__file__).parent / "data"
RENDER_DIR = DATA_DIR / "rendered"

# Review file paths (same as processor.py)
_REVIEW_PATHS = {
    "ocr": DATA_DIR / "review" / "step1_ocr_review.csv",
    "vendor": DATA_DIR / "review" / "step2_vendor_review.csv",
    "account": DATA_DIR / "review" / "step3_account_review.csv",
    "lookup": DATA_DIR / "review" / "step4_lookup_review.csv",
    "address": DATA_DIR / "review" / "step5_address_review.csv",
}

# Row grouping threshold (px in page coords — lines within this Y distance merge)
ROW_Y_THRESHOLD = 10


def _get_gcs_client():
    """Lazy-init GCS client."""
    from google.cloud import storage
    return storage.Client(project=GCS_PROJECT)


def fetch_docai_json(md5_hash: str, client=None) -> dict | None:
    """Fetch Document AI JSON from GCS for a given md5_hash."""
    if client is None:
        client = _get_gcs_client()

    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(md5_hash)

    if not blob.exists():
        log.warning("No Document AI JSON found for %s", md5_hash)
        return None

    content = blob.download_as_text()
    return json.loads(content)


def save_invoice_image(md5_hash: str, output_dir: Path,
                       client=None, docai_json: dict = None) -> Path | None:
    """Save the actual invoice page image(s) from Document AI JSON.

    Extracts the embedded base64 JPEG from the Document AI response
    and writes it to disk. For multi-page docs, saves page 1 only
    (the header page with account info).

    Returns the image file path, or None if no image found.
    """
    if docai_json is None:
        docai_json = fetch_docai_json(md5_hash, client=client)
    if not docai_json:
        return None

    doc = docai_json.get('document', docai_json)
    pages = doc.get('pages', [])
    if not pages:
        return None

    # Get first page image
    img_data = pages[0].get('image', {})
    content_b64 = img_data.get('content', '')
    if not content_b64:
        return None

    mime = img_data.get('mimeType', 'image/jpeg')
    ext = 'jpg' if 'jpeg' in mime else mime.split('/')[-1]

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{md5_hash}.{ext}"

    img_bytes = base64.b64decode(content_b64)
    with open(out_path, 'wb') as f:
        f.write(img_bytes)

    return out_path


def _preprocess_text(raw_text: str) -> tuple[str, list[int]]:
    """Replace literal \\n (2-char backslash+n) with single space.

    Document AI JSON from GCS stores newlines as literal \\n sequences.
    textAnchor indices point into the raw text, so we build an index map
    to extract clean text without split artifacts.

    Returns:
        (clean_text, orig_to_clean) where orig_to_clean[i] gives
        the position in clean_text for raw position i.
    """
    clean = []
    orig_to_clean = []
    i = 0
    ci = 0
    while i < len(raw_text):
        if i + 1 < len(raw_text) and raw_text[i] == '\\' and raw_text[i + 1] == 'n':
            clean.append(' ')
            orig_to_clean.append(ci)   # backslash maps to the space
            orig_to_clean.append(ci)   # 'n' maps to same space
            i += 2
            ci += 1
        else:
            clean.append(raw_text[i])
            orig_to_clean.append(ci)
            i += 1
            ci += 1
    # Sentinel for end-of-string lookups
    orig_to_clean.append(ci)
    return ''.join(clean), orig_to_clean


def _get_text_from_layout(layout: dict, clean_text: str,
                          orig_to_clean: list[int]) -> str | None:
    """Extract text using textAnchor references with index remapping."""
    text_anchor = layout.get('textAnchor', {})
    segments = text_anchor.get('textSegments', [])

    if not segments:
        return None

    result = []
    for seg in segments:
        start = int(seg.get('startIndex', 0))
        end = int(seg.get('endIndex', 0))
        if end > start:
            cs = orig_to_clean[start]
            ce = orig_to_clean[end - 1] + 1
            result.append(clean_text[cs:ce])

    text = ''.join(result).replace('\n', ' ').strip()
    return text if text else None



def _get_bbox(layout: dict) -> dict | None:
    """Extract bounding box from layout. Returns {x, y, width, height} normalized."""
    bp = layout.get('boundingPoly', {})
    verts = bp.get('normalizedVertices', [])

    if len(verts) < 4:
        return None

    xs = [v.get('x', 0) for v in verts]
    ys = [v.get('y', 0) for v in verts]

    return {
        'x': min(xs),
        'y': min(ys),
        'width': max(xs) - min(xs),
        'height': max(ys) - min(ys),
    }


def extract_text_blocks(docai_json: dict) -> tuple[list[dict], str]:
    """Extract line-level text blocks with bounding boxes from Document AI JSON.

    Uses pages.lines (not individual tokens) for natural text grouping.
    Falls back to paragraphs if no lines present, then tokens as last resort.

    Returns:
        (blocks, full_text) where blocks is a list of dicts:
            {text, page, x, y, width, height, type}
        Coordinates are in page points (scaled from normalized × page dimensions).
    """
    doc = docai_json.get('document', docai_json)
    raw_full_text = doc.get('text', '')
    clean_text, orig_to_clean = _preprocess_text(raw_full_text)
    # Display-friendly version (literal \n → real newlines)
    display_text = clean_text.replace('  ', ' ')  # collapse double spaces from \n replacement
    pages = doc.get('pages', [])

    def _extract(layout):
        return _get_text_from_layout(layout, clean_text, orig_to_clean)

    blocks = []
    for page_idx, page in enumerate(pages):
        page_width = page.get('dimension', {}).get('width', 612)
        page_height = page.get('dimension', {}).get('height', 792)

        # Prefer lines for visual layout
        lines = page.get('lines', [])
        if lines:
            for line in lines:
                text = _extract(line.get('layout', {}))
                bbox = _get_bbox(line.get('layout', {}))
                if text and bbox:
                    blocks.append({
                        'text': text,
                        'x': bbox['x'] * page_width,
                        'y': bbox['y'] * page_height,
                        'width': bbox['width'] * page_width,
                        'height': bbox['height'] * page_height,
                        'page': page_idx,
                        'type': 'line',
                    })

        # Fall back to paragraphs if no lines
        if not lines:
            for para in page.get('paragraphs', []):
                text = _extract(para.get('layout', {}))
                bbox = _get_bbox(para.get('layout', {}))
                if text and bbox:
                    blocks.append({
                        'text': text,
                        'x': bbox['x'] * page_width,
                        'y': bbox['y'] * page_height,
                        'width': bbox['width'] * page_width,
                        'height': bbox['height'] * page_height,
                        'page': page_idx,
                        'type': 'paragraph',
                    })

        # Last resort: tokens
        if not lines and not page.get('paragraphs', []):
            for token in page.get('tokens', []):
                text = _extract(token.get('layout', {}))
                bbox = _get_bbox(token.get('layout', {}))
                if text and bbox:
                    blocks.append({
                        'text': text,
                        'x': bbox['x'] * page_width,
                        'y': bbox['y'] * page_height,
                        'width': bbox['width'] * page_width,
                        'height': bbox['height'] * page_height,
                        'page': page_idx,
                        'type': 'token',
                    })

        # Also extract table cells (these get their own treatment)
        for table in page.get('tables', []):
            for row in table.get('bodyRows', []) + table.get('headerRows', []):
                for cell in row.get('cells', []):
                    text = _extract(cell.get('layout', {}))
                    bbox = _get_bbox(cell.get('layout', {}))
                    if text and bbox:
                        blocks.append({
                            'text': text,
                            'x': bbox['x'] * page_width,
                            'y': bbox['y'] * page_height,
                            'width': bbox['width'] * page_width,
                            'height': bbox['height'] * page_height,
                            'page': page_idx,
                            'type': 'table_cell',
                        })

    return blocks, raw_full_text.replace('\\n', '\n')


def _group_into_rows(blocks: list[dict]) -> list[list[dict]]:
    """Group text blocks into rows by Y-coordinate proximity.

    Blocks within ROW_Y_THRESHOLD pixels of each other are merged into the
    same row. Within each row, blocks are sorted left-to-right by X.
    """
    # Sort by page, then Y, then X
    sorted_blocks = sorted(blocks, key=lambda b: (b['page'], b['y'], b['x']))

    # Use only lines for the visual layout (skip table cells — they overlap)
    line_blocks = [b for b in sorted_blocks if b['type'] in ('line', 'paragraph', 'token')]

    rows = []
    current_row = []
    current_y = -999

    for block in line_blocks:
        if abs(block['y'] - current_y) < ROW_Y_THRESHOLD:
            current_row.append(block)
        else:
            if current_row:
                rows.append(sorted(current_row, key=lambda b: b['x']))
            current_row = [block]
            current_y = block['y']

    if current_row:
        rows.append(sorted(current_row, key=lambda b: b['x']))

    return rows


def render_invoice_html(md5_hash: str, docai_json: dict,
                        full_text: str = '', metadata: dict = None) -> str:
    """Generate HTML with the actual Document AI page image + metadata.

    The page image is embedded as a base64 JPEG directly from the
    Document AI JSON — no bounding-box reconstruction needed.
    """
    from html import escape

    meta = metadata or {}
    doc = docai_json.get('document', docai_json)
    pages = doc.get('pages', [])

    # Metadata header
    meta_html = ''
    if meta:
        meta_rows = []
        for key in ('detected_vendor', 'fail_category', 'suggestion',
                     'account_format', 'confidence'):
            val = meta.get(key, '')
            if val:
                label = key.replace('_', ' ').title()
                meta_rows.append(
                    f'<tr><td class="ml">{escape(label)}</td>'
                    f'<td>{escape(str(val))}</td></tr>'
                )
        if meta_rows:
            meta_html = '<div class="meta"><table>' + ''.join(meta_rows) + '</table></div>'

    # Page images
    img_html = []
    for i, page in enumerate(pages):
        img_data = page.get('image', {})
        content = img_data.get('content', '')
        mime = img_data.get('mimeType', 'image/jpeg')
        if content:
            img_html.append(
                f'<div class="page"><img src="data:{mime};base64,{content}" '
                f'alt="Page {i+1}"></div>'
            )

    # Raw OCR text
    raw_html = ''
    if full_text:
        raw_html = (
            '<details class="raw"><summary>Raw OCR Text</summary>'
            f'<pre>{escape(full_text)}</pre></details>'
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Invoice — {escape(md5_hash[:12])}</title>
<style>
body {{ font-family: sans-serif; margin: 20px; background: #f5f5f5; }}
h1 {{ font-size: 16px; color: #333; margin: 0 0 4px 0; }}
.md5 {{ font-size: 12px; color: #666; font-family: monospace; margin-bottom: 12px; }}
.meta {{ margin-bottom: 16px; padding: 12px; background: #f0f4f8; border-radius: 6px;
         font-family: monospace; font-size: 13px; }}
.ml {{ font-weight: bold; padding-right: 12px; white-space: nowrap; }}
.page {{ margin: 10px auto; max-width: 800px; }}
.page img {{ width: 100%; border: 1px solid #ccc; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
.raw {{ margin: 15px 0; font-size: 11px; }}
.raw summary {{ cursor: pointer; color: #666; }}
.raw pre {{ background: #f9f9f9; padding: 10px; overflow-x: auto; max-height: 400px;
            border: 1px solid #eee; font-size: 11px; line-height: 1.4; }}
</style>
</head>
<body>
<h1>Invoice Document</h1>
<div class="md5">{escape(md5_hash)}</div>
{meta_html}
{''.join(img_html)}
{raw_html}
</body>
</html>"""


def render_invoice(md5_hash: str, metadata: dict = None,
                   output_dir: Path = None, client=None) -> Path | None:
    """Fetch Document AI data and render invoice to HTML with embedded page image.

    Returns the output file path, or None if no data found.
    """
    docai = fetch_docai_json(md5_hash, client=client)
    if not docai:
        return None

    doc = docai.get('document', docai)
    raw_full_text = doc.get('text', '')
    full_text = raw_full_text.replace('\\n', '\n')

    html = render_invoice_html(md5_hash, docai, full_text=full_text,
                               metadata=metadata)

    out_dir = output_dir or RENDER_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{md5_hash}.html"

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return out_path


def render_review_invoices(step: str, output_dir: Path = None) -> dict:
    """Render invoices for all documents in a step's review file.

    Returns summary dict with counts.
    """
    review_path = _REVIEW_PATHS.get(step)
    if not review_path or not review_path.exists():
        print(f"  No review file for step '{step}'")
        return {"total": 0}

    # Load review rows
    with open(review_path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print(f"  Review file empty for step '{step}'")
        return {"total": 0}

    out_dir = output_dir or RENDER_DIR / step
    out_dir.mkdir(parents=True, exist_ok=True)

    client = _get_gcs_client()
    rendered = 0
    failed = 0

    for i, row in enumerate(rows, 1):
        md5 = (row.get('md5_hash') or '').strip()
        if not md5:
            continue

        # Pass review metadata for the header
        metadata = {k: v for k, v in row.items()
                    if k not in ('md5_hash', 'raw_ocr_text', 'raw_ocr_snippet', 'notes')}

        path = render_invoice(md5, metadata=metadata, output_dir=out_dir, client=client)
        if path:
            rendered += 1
        else:
            failed += 1

        if i % 10 == 0:
            print(f"  Rendered {i}/{len(rows)}...")

    print(f"\n  Rendered: {rendered}/{len(rows)}")
    if failed:
        print(f"  Failed:   {failed}")
    print(f"  Output:   {out_dir}/")

    return {"total": len(rows), "rendered": rendered, "failed": failed}
