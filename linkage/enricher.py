"""
Enrich invoice_registry with parsing_engines regex extractions.

Joins invoice_registry with ocr_document (on invoice_md5 = md5_hash) to get
raw text, then runs parsing_engines extractors. Updates regex_* columns and
recomputes resolved_* = COALESCE(manual, regex, gapi).
"""

import logging
import sys
from datetime import date

import psycopg2.extras

from ..database import get_connection

log = logging.getLogger(__name__)

# Add parsing_engines to path (sibling project)
_PE_PATH = "/home/scstclair/projects"
if _PE_PATH not in sys.path:
    sys.path.insert(0, _PE_PATH)

BATCH_SIZE_DEFAULT = 1000
COMMIT_EVERY = 5_000


def _import_parsing_engines():
    """Lazy import parsing_engines to avoid import errors when not available."""
    from parsing_engines.vendor_detection import detect_vendor
    from parsing_engines.account_number.account_extraction_engine import extract_account
    from parsing_engines.invoice_number.invoice_extraction_engine import extract_invoice_number
    from parsing_engines.amount_due import extract_bill_total
    from parsing_engines.dates import extract_invoice_date
    from parsing_engines.service_address import extract_service_address

    return {
        "detect_vendor": detect_vendor,
        "extract_account": extract_account,
        "extract_invoice_number": extract_invoice_number,
        "extract_bill_total": extract_bill_total,
        "extract_invoice_date": extract_invoice_date,
        "extract_service_address": extract_service_address,
    }


def _parse_date_string(date_str: str | None) -> date | None:
    """Parse YYYY-MM-DD string to date object."""
    if not date_str:
        return None
    try:
        parts = date_str.split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def _build_vendor_cache(cursor) -> dict[str, int]:
    """Pre-load vendor name → vendor_id mapping."""
    cursor.execute("SELECT vendor_id, vendor_name FROM vendor WHERE vendor_name IS NOT NULL")
    cache = {}
    for row in cursor.fetchall():
        cache[row["vendor_name"].strip().lower()] = row["vendor_id"]
    return cache


def _resolve_vendor_cached(cache: dict[str, int], vendor_name: str | None) -> int | None:
    """Resolve vendor_id from cache."""
    if not vendor_name:
        return None
    name_lower = vendor_name.strip().lower()
    if not name_lower:
        return None
    if name_lower in cache:
        return cache[name_lower]
    # Substring: query contains a vendor name
    matches = [(k, v) for k, v in cache.items() if k in name_lower]
    if not matches:
        matches = [(k, v) for k, v in cache.items() if name_lower in k]
    if matches:
        matches.sort(key=lambda x: len(x[0]))
        return matches[0][1]
    return None


def enrich_invoices(batch_size: int = BATCH_SIZE_DEFAULT) -> dict:
    """Run parsing_engines regex against OCR text for pending invoices.

    Processes invoices where enrichment_status IN ('gapi_only', 'pending').
    Updates regex_* columns and recomputes resolved_* via COALESCE.

    Returns dict with counts: processed, vendor_improved, account_improved, etc.
    """
    engines = _import_parsing_engines()
    detect_vendor = engines["detect_vendor"]
    extract_account = engines["extract_account"]
    extract_invoice_number = engines["extract_invoice_number"]
    extract_bill_total = engines["extract_bill_total"]
    extract_invoice_date = engines["extract_invoice_date"]
    extract_service_address = engines["extract_service_address"]

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Pre-load vendor cache
    vendor_cache = _build_vendor_cache(cursor)

    # Count pending rows
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM invoice_registry
        WHERE enrichment_status IN ('gapi_only', 'pending')
    """)
    pending_count = cursor.fetchone()["cnt"]
    log.info("Pending invoices to enrich: %d", pending_count)

    if pending_count == 0:
        conn.close()
        return {"processed": 0}

    # Process in batches using cursor-based pagination
    stats = {
        "processed": 0,
        "vendor_improved": 0,
        "account_improved": 0,
        "amount_improved": 0,
        "date_improved": 0,
        "address_improved": 0,
        "invoice_num_improved": 0,
        "no_ocr_text": 0,
    }

    offset = 0
    while offset < pending_count:
        cursor.execute("""
            SELECT ir.invoice_md5,
                   ir.gapi_vendor_name, ir.gapi_account_number,
                   ir.gapi_invoice_number, ir.gapi_invoice_amount,
                   ir.gapi_invoice_date, ir.gapi_service_address,
                   ir.gapi_site_state,
                   ir.manual_vendor_name, ir.manual_service_address,
                   ir.manual_service_city, ir.manual_service_state,
                   ir.manual_service_postal, ir.manual_invoice_date,
                   ir.manual_invoice_amount, ir.manual_account_number,
                   ir.manual_invoice_number,
                   od.raw_text
            FROM invoice_registry ir
            LEFT JOIN ocr_document od ON ir.invoice_md5 = od.md5_hash
            WHERE ir.enrichment_status IN ('gapi_only', 'pending')
            ORDER BY ir.invoice_md5
            LIMIT %s OFFSET %s
        """, (batch_size, offset))

        rows = cursor.fetchall()
        if not rows:
            break

        updates = []
        for row in rows:
            md5 = row["invoice_md5"]
            raw_text = row["raw_text"]

            if not raw_text:
                stats["no_ocr_text"] += 1
                # Still mark as enriched (no OCR available)
                updates.append((
                    None, None, None, None, None,
                    None, None, None, None,
                    # resolved = COALESCE(manual, regex=None, gapi)
                    row["manual_vendor_name"] or row["gapi_vendor_name"],
                    None,  # vendor_id recomputed below
                    row["manual_service_address"] or row["gapi_service_address"],
                    row["manual_service_city"],
                    row["manual_service_state"] or row["gapi_site_state"],
                    row["manual_service_postal"],
                    _parse_date_string(str(row["manual_invoice_date"])) if row["manual_invoice_date"] else row["gapi_invoice_date"],
                    row["manual_invoice_amount"] or row["gapi_invoice_amount"],
                    row["manual_account_number"] or row["gapi_account_number"],
                    row["manual_invoice_number"] or row["gapi_invoice_number"],
                    "enriched",
                    md5,
                ))
                stats["processed"] += 1
                continue

            # Normalize OCR text
            text = raw_text.replace("\\n", "\n")

            # Run extractors
            regex_vendor = detect_vendor(text)
            if regex_vendor == "OTHER":
                regex_vendor = None

            # Use best vendor name for downstream extractors
            best_vendor = regex_vendor or row["gapi_vendor_name"] or ""

            regex_account = extract_account(best_vendor, text) if best_vendor else None
            regex_invoice_num = extract_invoice_number(best_vendor, text) if best_vendor else None
            regex_amount = extract_bill_total(text)
            regex_date_str = extract_invoice_date(best_vendor, text) if best_vendor else extract_invoice_date(text)
            regex_date = _parse_date_string(regex_date_str)

            addr_result = extract_service_address(best_vendor, text) if best_vendor else None
            regex_address = addr_result.get("street") if addr_result else None
            regex_city = addr_result.get("city") if addr_result else None
            regex_state = addr_result.get("state") if addr_result else None
            regex_postal = addr_result.get("postal_code") if addr_result else None

            # Track improvements over GAPI
            if regex_vendor and not row["gapi_vendor_name"]:
                stats["vendor_improved"] += 1
            if regex_account and not row["gapi_account_number"]:
                stats["account_improved"] += 1
            if regex_amount and not row["gapi_invoice_amount"]:
                stats["amount_improved"] += 1
            if regex_date and not row["gapi_invoice_date"]:
                stats["date_improved"] += 1
            if regex_address and not row["gapi_service_address"]:
                stats["address_improved"] += 1
            if regex_invoice_num and not row["gapi_invoice_number"]:
                stats["invoice_num_improved"] += 1

            # Compute resolved values: COALESCE(manual, regex, gapi)
            resolved_vendor = row["manual_vendor_name"] or regex_vendor or row["gapi_vendor_name"]
            resolved_address = row["manual_service_address"] or regex_address or row["gapi_service_address"]
            resolved_city = row["manual_service_city"] or regex_city
            resolved_state = row["manual_service_state"] or regex_state or row["gapi_site_state"]
            resolved_postal = row["manual_service_postal"] or regex_postal

            resolved_date = (
                row["manual_invoice_date"]
                or regex_date
                or row["gapi_invoice_date"]
            )
            resolved_amount = (
                row["manual_invoice_amount"]
                or regex_amount
                or row["gapi_invoice_amount"]
            )
            resolved_account = (
                row["manual_account_number"]
                or regex_account
                or row["gapi_account_number"]
            )
            resolved_invoice_num = (
                row["manual_invoice_number"]
                or regex_invoice_num
                or row["gapi_invoice_number"]
            )

            resolved_vendor_id = _resolve_vendor_cached(vendor_cache, resolved_vendor)

            updates.append((
                regex_vendor, regex_address, regex_city, regex_state, regex_postal,
                regex_date, regex_amount, regex_account, regex_invoice_num,
                resolved_vendor, resolved_vendor_id,
                resolved_address, resolved_city, resolved_state, resolved_postal,
                resolved_date, resolved_amount, resolved_account, resolved_invoice_num,
                "enriched",
                md5,
            ))
            stats["processed"] += 1

        # Batch update
        if updates:
            psycopg2.extras.execute_batch(cursor, """
                UPDATE invoice_registry SET
                    regex_vendor_name     = %s,
                    regex_service_address = %s,
                    regex_service_city    = %s,
                    regex_service_state   = %s,
                    regex_service_postal  = %s,
                    regex_invoice_date    = %s,
                    regex_invoice_amount  = %s,
                    regex_account_number  = %s,
                    regex_invoice_number  = %s,
                    resolved_vendor_name  = %s,
                    resolved_vendor_id    = %s,
                    resolved_address      = %s,
                    resolved_city         = %s,
                    resolved_state        = %s,
                    resolved_postal_code  = %s,
                    resolved_invoice_date = %s,
                    resolved_invoice_amount = %s,
                    resolved_account_number = %s,
                    resolved_invoice_number = %s,
                    enrichment_status     = %s,
                    updated_at            = CURRENT_TIMESTAMP
                WHERE invoice_md5 = %s
            """, updates, page_size=1000)
            conn.commit()

        offset += batch_size
        log.info("  Enriched %d / %d...", min(offset, pending_count), pending_count)

    conn.close()
    log.info("Enrichment complete: %s", stats)
    return stats
