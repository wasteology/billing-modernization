"""
HTTP API server for the invoice processing review UI.

Lightweight Flask app with JSON API endpoints for:
- Pipeline status and gate status
- Review queue browsing and resolution
- Document rendering (OCR text + invoice image)
- Meta Regex Helper (test, validate, deploy patterns)
- Fix log management

Usage:
    python -m src.invoice_processing.app [--port 8080]
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, date

from flask import Flask, jsonify, request, send_from_directory

log = logging.getLogger(__name__)

app = Flask(__name__,
            static_folder=None)


@app.errorhandler(Exception)
def handle_exception(e):
    """Return JSON for all errors so the UI never gets HTML error pages."""
    log.exception("Unhandled error: %s", e)
    return app.response_class(
        response=json.dumps({'error': str(e)}),
        status=500,
        mimetype='application/json',
    )


@app.errorhandler(404)
def handle_404(e):
    return app.response_class(
        response=json.dumps({'error': 'Not found'}),
        status=404,
        mimetype='application/json',
    )


def _json_serial(obj):
    """JSON serializer for objects not serializable by default."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _json_response(data, status=200):
    return app.response_class(
        response=json.dumps(data, default=_json_serial),
        status=status,
        mimetype='application/json',
    )


# =============================================================================
# Pipeline status
# =============================================================================

@app.route('/api/status')
def api_status():
    """Gate status + queue counts per step."""
    from .db_helpers import get_gate_status_summary
    from .database import get_connection as _get_conn
    import psycopg2.extras as _extras

    summary = get_gate_status_summary()
    # Reshape for UI: {steps: [{step, open, passed, excluded, blocked}, ...]}
    steps = []
    for step_num in sorted(summary.keys()):
        s = summary[step_num]
        steps.append({
            'step': step_num,
            'open': s.get('open_review', 0),
            'passed': s.get('passed', 0),
            'excluded': s.get('excluded', 0),
            'blocked': s.get('blocked', 0),
        })

    # Add validation summary as step 7 (if not already in gate summary)
    if 7 not in summary:
        try:
            conn = _get_conn()
            cur = conn.cursor(cursor_factory=_extras.RealDictCursor)
            cur.execute("""
                SELECT
                    COUNT(DISTINCT md5_hash) AS total,
                    COUNT(DISTINCT md5_hash) FILTER (
                        WHERE md5_hash NOT IN (
                            SELECT md5_hash FROM ip_validation_result WHERE check_result = 'FAIL'
                        )
                    ) AS passed,
                    COUNT(DISTINCT md5_hash) FILTER (
                        WHERE md5_hash IN (
                            SELECT md5_hash FROM ip_validation_result WHERE check_result = 'FAIL'
                        )
                    ) AS failed
                FROM ip_validation_result
            """)
            vr = cur.fetchone()
            conn.close()
            if vr and vr['total'] > 0:
                steps.append({
                    'step': 7,
                    'open': vr['failed'],
                    'passed': vr['passed'],
                    'excluded': 0,
                    'blocked': 0,
                })
        except Exception:
            pass  # ip_validation_result may not exist yet

    return _json_response({'steps': steps})


# =============================================================================
# Processed data (staging view)
# =============================================================================

@app.route('/api/staging')
def api_staging():
    """Processed invoice data from ip_staging_invoice view."""
    from .database import get_connection
    import psycopg2.extras

    vendor = request.args.get('vendor')
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Count
    count_sql = "SELECT count(*) FROM ip_staging_invoice WHERE step1_status = 'PASSED'"
    params = []
    if vendor:
        count_sql += " AND detected_vendor = %s"
        params.append(vendor)
    cur.execute(count_sql, params)
    total = cur.fetchone()['count']

    # Rows
    sql = """
        SELECT md5_hash, sp_created_date, source_file,
               detected_vendor, hauler_account_number,
               hauler_invoice_number, invoice_date, bill_total,
               step1_status, step2_status, step3_status,
               step4_status, step5_status, step6_status
        FROM ip_staging_invoice
        WHERE step1_status = 'PASSED'
    """
    if vendor:
        sql += " AND detected_vendor = %s"
    sql += " ORDER BY detected_vendor, sp_created_date DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]

    # Vendor summary
    cur.execute("""
        SELECT detected_vendor, count(*) AS cnt
        FROM ip_staging_invoice
        WHERE step1_status = 'PASSED' AND detected_vendor IS NOT NULL
        GROUP BY detected_vendor ORDER BY cnt DESC
    """)
    vendors = [dict(r) for r in cur.fetchall()]

    conn.close()
    return _json_response({
        'rows': rows,
        'total': total,
        'limit': limit,
        'offset': offset,
        'vendors': vendors,
    })


# =============================================================================
# Review queue
# =============================================================================

@app.route('/api/review/<int:step>')
def api_review(step):
    """Review queue rows grouped by vendor + document format fingerprint."""
    from .db_helpers import (get_review_queue, get_extraction_values_batch,
                             get_ocr_text_batch)
    from .ai_suggestions import format_fingerprint, describe_format_group

    status = request.args.get('status', 'OPEN')
    rows = get_review_queue(step, status=status)

    if not rows:
        return _json_response({'groups': [], 'total': 0})

    # Enrich with vendor info + OCR text for fingerprinting
    md5_list = [r['md5_hash'] for r in rows]
    vendor_map = get_extraction_values_batch(md5_list, 'detected_vendor') if step > 2 else {}
    ocr_map = get_ocr_text_batch(md5_list)

    # Group by vendor + fail_category + format fingerprint
    # This clusters documents with the same invoice template together
    # so the HITL can review one representative and bulk-resolve the group.
    groups = {}
    for r in rows:
        vendor = vendor_map.get(r['md5_hash'], '(unknown)')
        ocr_text = ocr_map.get(r['md5_hash'], '')
        fp = format_fingerprint(ocr_text)
        key = f"{vendor}|{r['fail_category']}|{fp}"
        if key not in groups:
            groups[key] = {
                'vendor': vendor,
                'fail_category': r['fail_category'],
                'fingerprint': fp,
                'ai_suggestion': r.get('ai_suggestion'),
                'suggestion_confidence': r.get('suggestion_confidence'),
                'format_description': None,
                'count': 0,
                'rows': [],
                '_ocr_texts': [],
            }
        groups[key]['count'] += 1
        groups[key]['rows'].append(r)
        groups[key]['_ocr_texts'].append(ocr_text)

    # Generate format descriptions per group
    for g in groups.values():
        g['format_description'] = describe_format_group(
            g['_ocr_texts'], step, g['vendor'])
        del g['_ocr_texts']  # don't send raw OCR in response

    # Sort by count descending
    sorted_groups = sorted(groups.values(), key=lambda g: -g['count'])

    return _json_response({
        'groups': sorted_groups,
        'total': len(rows),
    })


@app.route('/api/review/<int:step>/rows')
def api_review_rows(step):
    """Paginated review queue rows for a step."""
    from .db_helpers import get_review_queue

    status = request.args.get('status', 'OPEN')
    vendor = request.args.get('vendor')
    limit = int(request.args.get('limit', 50))

    rows = get_review_queue(step, status=status, vendor=vendor, limit=limit)
    return _json_response({'rows': rows, 'count': len(rows)})


# =============================================================================
# Document view
# =============================================================================

@app.route('/api/document/<md5_hash>')
def api_document(md5_hash):
    """Get document details: OCR text, extracted values, review history."""
    from .database import get_connection
    import psycopg2.extras

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Raw document
    cur.execute(
        "SELECT md5_hash, sp_created_date, raw_ocr_text, source_file"
        " FROM ip_raw_document WHERE md5_hash = %s",
        (md5_hash,),
    )
    doc = cur.fetchone()
    if not doc:
        conn.close()
        return _json_response({'error': 'Document not found'}, 404)

    # Extraction results
    cur.execute(
        "SELECT step, field, extracted_value, extraction_source, extracted_at"
        " FROM ip_extraction_result WHERE md5_hash = %s"
        " ORDER BY step, extracted_at DESC",
        (md5_hash,),
    )
    extractions = [dict(r) for r in cur.fetchall()]

    # Gate results
    cur.execute(
        "SELECT step, gate_status, passed_at"
        " FROM ip_gate_result WHERE md5_hash = %s ORDER BY step",
        (md5_hash,),
    )
    gates = [dict(r) for r in cur.fetchall()]

    # Review history
    cur.execute(
        "SELECT review_queue_id, step, fail_category, ai_suggestion,"
        " suggestion_confidence, human_action, corrected_value, status, opened_at"
        " FROM ip_review_queue WHERE md5_hash = %s ORDER BY opened_at DESC",
        (md5_hash,),
    )
    reviews = [dict(r) for r in cur.fetchall()]

    conn.close()

    return _json_response({
        'document': dict(doc),
        'extractions': extractions,
        'gates': gates,
        'reviews': reviews,
    })


@app.route('/api/document/<md5_hash>/image')
def api_document_image(md5_hash):
    """Serve the invoice page image from GCS Document AI JSON."""
    import base64
    try:
        from .invoice_renderer import fetch_docai_json
        docai_json = fetch_docai_json(md5_hash)
        if not docai_json:
            return _json_response({'error': 'No Document AI data found'}, 404)

        doc = docai_json.get('document', docai_json)
        pages = doc.get('pages', [])
        if not pages:
            return _json_response({'error': 'No pages in document'}, 404)

        # Get requested page (default page 1)
        page_num = int(request.args.get('page', 0))
        if page_num >= len(pages):
            page_num = 0

        img_data = pages[page_num].get('image', {})
        content_b64 = img_data.get('content', '')
        if not content_b64:
            return _json_response({'error': 'No image data on page'}, 404)

        mime = img_data.get('mimeType', 'image/jpeg')
        img_bytes = base64.b64decode(content_b64)

        from flask import Response
        return Response(img_bytes, mimetype=mime,
                        headers={'Cache-Control': 'public, max-age=3600'})
    except Exception as e:
        log.warning("Image fetch error for %s: %s", md5_hash, e)
        return _json_response({'error': str(e)}, 500)


# =============================================================================
# Resolve (HITL disposition)
# =============================================================================

@app.route('/api/resolve', methods=['POST'])
def api_resolve():
    """Apply disposition to a review queue row."""
    from .review_resolver import resolve_row

    data = request.get_json()
    if not data:
        return _json_response({'error': 'Missing JSON body'}, 400)

    review_queue_id = data.get('review_queue_id')
    disposition = data.get('disposition')

    if not review_queue_id or not disposition:
        return _json_response({'error': 'review_queue_id and disposition required'}, 400)

    result = resolve_row(
        review_queue_id=int(review_queue_id),
        disposition=disposition,
        corrected_value=data.get('corrected_value'),
        reroute_to_step=data.get('reroute_to_step'),
        notes=data.get('notes'),
        resolved_by=data.get('resolved_by', 'HITL'),
    )
    return _json_response(result)


@app.route('/api/resolve-bulk', methods=['POST'])
def api_resolve_bulk():
    """Apply disposition to multiple review queue rows at once."""
    from .review_resolver import resolve_row

    data = request.get_json()
    if not data:
        return _json_response({'error': 'Missing JSON body'}, 400)

    ids = data.get('review_queue_ids', [])
    disposition = data.get('disposition')
    if not ids or not disposition:
        return _json_response({'error': 'review_queue_ids and disposition required'}, 400)

    resolved = 0
    errors = 0
    for rid in ids:
        try:
            row_data = {
                'corrected_value': data.get('corrected_value'),
                'reroute_to_step': data.get('reroute_to_step'),
                'notes': data.get('notes', f'Bulk {disposition}'),
                'resolved_by': data.get('resolved_by', 'HITL_BULK'),
            }
            # For ACCEPT, get the AI suggestion for each row
            result = resolve_row(
                review_queue_id=int(rid),
                disposition=disposition,
                **row_data,
            )
            if result.get('success'):
                resolved += 1
            else:
                errors += 1
        except Exception as e:
            log.warning("Bulk resolve error for %s: %s", rid, e)
            errors += 1

    return _json_response({
        'success': True,
        'resolved': resolved,
        'errors': errors,
        'message': f'Resolved {resolved} of {len(ids)} items',
    })


# =============================================================================
# Fix log
# =============================================================================

@app.route('/api/fix-log')
def api_fix_log():
    """Get open fix_log entries."""
    from .database import get_connection
    import psycopg2.extras

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    status = request.args.get('status', 'OPEN')
    cur.execute(
        "SELECT * FROM ip_fix_log WHERE fix_status = %s ORDER BY created_at DESC",
        (status,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return _json_response({'rows': rows, 'count': len(rows)})


# =============================================================================
# Meta Regex Helper
# =============================================================================

@app.route('/api/generate-pattern', methods=['POST'])
def api_generate_pattern():
    """Auto-generate regex patterns from a target value and OCR context."""
    from .meta_helper import generate_regex

    data = request.get_json()
    candidates = generate_regex(
        target_value=data.get('target_value', ''),
        sample_text=data.get('sample_text', ''),
        field=data.get('field', ''),
        vendor=data.get('vendor', ''),
    )
    return _json_response({'candidates': candidates})


@app.route('/api/test-pattern', methods=['POST'])
def api_test_pattern():
    """Test a regex pattern against sample text."""
    from .meta_helper import test_pattern

    data = request.get_json()
    result = test_pattern(
        regex_pattern=data.get('pattern', ''),
        sample_text=data.get('sample_text', ''),
        regex_flags=data.get('flags', 'IGNORECASE'),
        capture_group=int(data.get('capture_group', 1)),
    )
    return _json_response(result)


@app.route('/api/validate-pattern', methods=['POST'])
def api_validate_pattern():
    """Run 3-gate validation on a pattern."""
    from .meta_helper import test_pattern, check_regression, check_collision

    data = request.get_json()
    pattern = data.get('pattern', '')
    sample = data.get('sample_text', '')
    step = int(data.get('step', 2))
    vendor = data.get('vendor', '')
    field = data.get('field', '')
    flags = data.get('flags', 'IGNORECASE')
    capture = int(data.get('capture_group', 1))

    # Gate 1: Sample match
    gate1 = test_pattern(pattern, sample, flags, capture)

    # Gate 2: Regression check
    scan_type = data.get('scan_type', 'INLINE')
    gate2 = check_regression(pattern, step, vendor, field, flags, capture,
                             scan_type=scan_type)

    # Gate 3: Collision check (skipped for universal fields like date/amount)
    gate3 = check_collision(pattern, step, vendor, flags, field=field)

    all_pass = gate1.get('matched') and gate2.get('passed') and gate3.get('passed')

    return _json_response({
        'all_pass': all_pass,
        'gate1_sample': gate1,
        'gate2_regression': gate2,
        'gate3_collision': gate3,
    })


@app.route('/api/deploy-pattern', methods=['POST'])
def api_deploy_pattern():
    """Deploy a new pattern (after 3-gate validation passes)."""
    from .meta_helper import deploy_pattern

    data = request.get_json()
    try:
        new_id = deploy_pattern(
            regex_pattern=data.get('pattern', ''),
            step=int(data.get('step', 2)),
            vendor_slug=data.get('vendor', ''),
            field=data.get('field', ''),
            prior_pattern_id=data.get('prior_pattern_id'),
            regex_flags=data.get('flags', 'IGNORECASE'),
            capture_group=int(data.get('capture_group', 1)),
            scan_type=data.get('scan_type', 'INLINE'),
            scan_lines=int(data.get('scan_lines', 1)),
            normalization=data.get('normalization', 'NONE'),
            date_format=data.get('date_format'),
            notes=data.get('notes'),
            deployed_by=data.get('deployed_by', 'meta_helper'),
        )
        return _json_response({'success': True, 'pattern_id': new_id})
    except Exception as e:
        return _json_response({'success': False, 'error': str(e)}, 500)


@app.route('/api/patterns')
def api_patterns():
    """Get current patterns for a vendor+field."""
    from .meta_helper import get_current_patterns

    vendor = request.args.get('vendor', '')
    field = request.args.get('field', '')
    patterns = get_current_patterns(vendor, field)
    return _json_response({'patterns': patterns})


# =============================================================================
# Line items + catalog endpoints
# =============================================================================

@app.route('/api/line-items/<md5_hash>')
def api_line_items(md5_hash):
    """Get line items for a document."""
    from .db_helpers import get_line_items
    rows = get_line_items(md5_hash)
    return _json_response({'rows': rows, 'count': len(rows)})


@app.route('/api/catalog/<account_number>/<vendor>')
def api_catalog(account_number, vendor):
    """Get catalog entries for an account+vendor."""
    from .db_helpers import get_service_catalog
    rows = get_service_catalog(account_number, vendor)
    return _json_response({'rows': rows, 'count': len(rows)})


# =============================================================================
# Pipeline execution (background thread)
# =============================================================================

_run_state = {
    'running': False,
    'action': None,
    'step': None,
    'started_at': None,
    'finished_at': None,
    'result': None,
    'error': None,
}
_run_lock = threading.Lock()
_cancel_event = threading.Event()


def _run_in_background(action: str, fn, kwargs: dict, step: int = None):
    """Execute a pipeline function in a background thread."""
    with _run_lock:
        if _run_state['running']:
            return False
        _cancel_event.clear()
        _run_state.update({
            'running': True,
            'action': action,
            'step': step,
            'started_at': time.time(),
            'finished_at': None,
            'result': None,
            'error': None,
        })

    # Pass cancel_event so step runners can check it
    kwargs['_cancel_event'] = _cancel_event

    def _worker():
        try:
            result = fn(**kwargs)
            with _run_lock:
                if _cancel_event.is_set():
                    _run_state['error'] = 'Cancelled by user'
                else:
                    _run_state['result'] = result
        except Exception as e:
            log.exception("Pipeline execution error: %s", e)
            with _run_lock:
                _run_state['error'] = str(e)
        finally:
            with _run_lock:
                _run_state['running'] = False
                _run_state['finished_at'] = time.time()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return True


@app.route('/api/pipeline/run-step', methods=['POST'])
def api_run_step():
    """Run a single pipeline step in the background."""
    from .step_runner import (
        run_step_1, run_step_2, run_step_3,
        run_step_4, run_step_5, run_step_6,
        run_validation, run_step_8, run_step_9, run_step_10,
    )

    data = request.get_json() or {}
    step = int(data.get('step', 0))
    wipe = bool(data.get('wipe', False))
    limit = data.get('limit')
    if limit is not None:
        limit = int(limit)

    step_fns = {
        1: run_step_1, 2: run_step_2, 3: run_step_3,
        4: run_step_4, 5: run_step_5, 6: run_step_6,
        7: run_validation, 8: run_step_8, 9: run_step_9, 10: run_step_10,
    }
    fn = step_fns.get(step)
    if not fn:
        return _json_response({'error': f'Invalid step: {step}'}, 400)

    kwargs = {'wipe': wipe}
    if limit and step <= 6:
        kwargs['limit'] = limit
    elif limit and step in (8, 9, 10):
        kwargs['limit'] = limit

    started = _run_in_background(f'run_step_{step}', fn, kwargs, step=step)
    if not started:
        return _json_response({'error': 'Another operation is already running'}, 409)

    return _json_response({'started': True, 'action': f'run_step_{step}', 'step': step})


@app.route('/api/pipeline/wipe', methods=['POST'])
def api_wipe():
    """Wipe extraction results (all or specific step)."""
    from .db_helpers import wipe_extraction_results

    data = request.get_json() or {}
    step = data.get('step')  # None = wipe all

    started = _run_in_background(
        'wipe', wipe_extraction_results,
        {'step': int(step) if step else None},
    )
    if not started:
        return _json_response({'error': 'Another operation is already running'}, 409)

    return _json_response({'started': True, 'action': 'wipe', 'step': step})


@app.route('/api/pipeline/seed-profiles', methods=['POST'])
def api_seed_profiles():
    """Seed vendor profiles for POC vendors."""
    from .validators import seed_vendor_profiles

    started = _run_in_background('seed_profiles', seed_vendor_profiles, {})
    if not started:
        return _json_response({'error': 'Another operation is already running'}, 409)

    return _json_response({'started': True, 'action': 'seed_profiles'})


@app.route('/api/pipeline/seed-catalog', methods=['POST'])
def api_seed_catalog():
    """Seed ip_service_catalog from ERP data for POC vendors."""
    from .catalog_seeder import seed_catalog

    data = request.get_json() or {}
    dry_run = bool(data.get('dry_run', False))
    vendor_filter = data.get('vendor_filter')  # optional override

    kwargs = {'dry_run': dry_run}
    if vendor_filter:
        kwargs['vendor_filter'] = vendor_filter

    started = _run_in_background('seed_catalog', seed_catalog, kwargs)
    if not started:
        return _json_response({'error': 'Another operation is already running'}, 409)

    return _json_response({'started': True, 'action': 'seed_catalog'})


@app.route('/api/pipeline/status')
def api_run_status():
    """Get current pipeline execution status."""
    with _run_lock:
        elapsed = None
        if _run_state['started_at']:
            end = _run_state['finished_at'] or time.time()
            elapsed = round(end - _run_state['started_at'], 1)

        return _json_response({
            'running': _run_state['running'],
            'action': _run_state['action'],
            'step': _run_state['step'],
            'elapsed': elapsed,
            'result': _run_state['result'],
            'error': _run_state['error'],
        })


# =============================================================================
# Cancel running operation
# =============================================================================

@app.route('/api/pipeline/cancel', methods=['POST'])
def api_cancel():
    """Cancel the currently running pipeline operation."""
    with _run_lock:
        if not _run_state['running']:
            return _json_response({'error': 'Nothing is running'}, 400)
        _cancel_event.set()
    return _json_response({'message': 'Cancel signal sent'})


# =============================================================================
# Server shutdown
# =============================================================================

@app.route('/api/shutdown', methods=['POST'])
def api_shutdown():
    """Gracefully shut down the Flask server."""
    import signal
    resp = _json_response({'message': 'Server shutting down...'})
    def _shutdown():
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=_shutdown, daemon=True).start()
    return resp


# =============================================================================
# Serve the review UI
# =============================================================================

@app.after_request
def add_no_cache(response):
    """Disable caching so browser always gets fresh HTML/JS."""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response


@app.route('/')
def index():
    """Serve the review UI."""
    ui_dir = os.path.join(os.path.dirname(__file__), 'ui')
    return send_from_directory(ui_dir, 'app.html')


# =============================================================================
# Main
# =============================================================================

def run_server(port: int = 8080, debug: bool = False):
    """Run the review API server."""
    # Suppress noisy GCP/google-cloud library warnings
    for noisy in ('google', 'google.auth', 'google.cloud', 'urllib3', 'grpc'):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    print(f"\n  Invoice Processing Review Server")
    print(f"  {'=' * 40}")
    print(f"  URL: http://localhost:{port}")
    print(f"  API: http://localhost:{port}/api/status")
    print(f"  UI:  http://localhost:{port}/")
    app.run(host='0.0.0.0', port=port, debug=debug)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    run_server(port=args.port, debug=args.debug)
