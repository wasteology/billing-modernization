"""
HITL disposition handler for the review queue.

Handles all human actions:
- Steps 1-7: ACCEPT, SET, EXCLUDE, REROUTE, CONFIRM_NO_ACCOUNT, SKIP
- Step 9: MAP, ADD_TO_CATALOG, EXCLUDE_CONTAINER
- Step 10: ACCEPT_VARIANCE, DISPUTE, ACCEPT_NEW_CHARGE, REJECT_CHARGE
"""

import logging
from datetime import datetime

from .database import get_connection
from .db_helpers import (
    write_extraction_results,
    write_gate_results,
    write_pipeline_events,
    update_review_queue,
    write_review_queue,
    write_line_items,
    write_service_catalog,
    update_service_catalog,
)

log = logging.getLogger(__name__)


def resolve_row(review_queue_id: int, disposition: str,
                corrected_value: str = None, reroute_to_step: int = None,
                notes: str = None, resolved_by: str = 'HITL') -> dict:
    """Apply a human disposition to a review queue row.

    Args:
        review_queue_id: ID of the review queue row
        disposition: One of ACCEPT, SET, EXCLUDE, REROUTE, CONFIRM_NO_ACCOUNT, SKIP
        corrected_value: Value to use (required for SET, optional for ACCEPT)
        notes: Human notes
        resolved_by: Who resolved this

    Returns:
        Dict with {success: bool, message: str, md5_hash, step}
    """
    conn = get_connection()
    cur = conn.cursor()

    # Fetch the review row
    cur.execute(
        "SELECT review_queue_id, md5_hash, step, fail_category, ai_suggestion, status"
        " FROM ip_review_queue WHERE review_queue_id = %s",
        (review_queue_id,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return {'success': False, 'message': f'Review row {review_queue_id} not found'}

    rq_id, md5, step, fail_cat, ai_suggestion, status = row
    if status != 'OPEN':
        conn.close()
        return {'success': False, 'message': f'Review row {rq_id} is already {status}'}

    result = {'success': True, 'md5_hash': md5, 'step': step}

    if disposition == 'ACCEPT':
        # Accept the AI suggestion or extracted value
        value = corrected_value or ai_suggestion
        if not value:
            conn.close()
            return {'success': False, 'message': 'No value to accept (no suggestion and no corrected_value)'}

        _write_accepted_value(conn, md5, step, value, rq_id, resolved_by, notes)
        result['message'] = f'Accepted value: {value}'

    elif disposition == 'SET':
        # Use human-provided corrected value
        if not corrected_value:
            conn.close()
            return {'success': False, 'message': 'SET requires corrected_value'}

        _write_corrected_value(conn, md5, step, corrected_value, rq_id, resolved_by, notes)
        result['message'] = f'Set value: {corrected_value}'

    elif disposition == 'EXCLUDE':
        # Mark document as excluded at this step
        _write_exclusion(conn, md5, step, rq_id, resolved_by, notes)
        result['message'] = 'Document excluded'

    elif disposition == 'REROUTE':
        # Reroute to upstream step
        reroute_target = reroute_to_step or corrected_value
        if not reroute_target:
            conn.close()
            return {'success': False, 'message': 'REROUTE requires target step'}

        _write_reroute(conn, md5, step, int(reroute_target), rq_id, resolved_by, notes)
        result['message'] = f'Rerouted to step {reroute_target}'

    elif disposition == 'CONFIRM_NO_ACCOUNT':
        # Mark as no-account vendor for this step
        _write_no_account(conn, md5, step, rq_id, resolved_by, notes)
        result['message'] = 'Confirmed NO_ACCOUNT'

    elif disposition == 'SKIP':
        # Leave open for now — just update notes
        update_review_queue(rq_id, 'SKIP', notes=notes, resolved_by=resolved_by, conn=conn)
        # Don't close the row, it stays OPEN
        cur.execute(
            "UPDATE ip_review_queue SET status = 'OPEN', human_action = 'SKIP'"
            " WHERE review_queue_id = %s", (rq_id,))
        result['message'] = 'Skipped (remains open)'

    # ---- Step 9 dispositions ----

    elif disposition == 'MAP':
        # Map unmatched container to existing catalog entry
        _write_map_container(conn, md5, step, corrected_value, rq_id, resolved_by, notes)
        result['message'] = f'Mapped container to catalog entry {corrected_value}'

    elif disposition == 'ADD_TO_CATALOG':
        # Add new container to ip_service_catalog, then close review
        _write_add_to_catalog(conn, md5, step, corrected_value, rq_id, resolved_by, notes)
        result['message'] = 'Added new entry to service catalog'

    elif disposition == 'EXCLUDE_CONTAINER':
        # Mark line items as EXCLUDED for this doc
        _write_exclude_container(conn, md5, step, rq_id, resolved_by, notes)
        result['message'] = 'Container excluded'

    # ---- Step 10 dispositions ----

    elif disposition == 'ACCEPT_VARIANCE':
        # Accept rate change — update catalog rate forward-looking
        _write_accept_variance(conn, md5, step, corrected_value, rq_id, resolved_by, notes)
        result['message'] = 'Variance accepted — catalog rate updated'

    elif disposition == 'DISPUTE':
        # Flag for vendor dispute
        _write_dispute(conn, md5, step, rq_id, resolved_by, notes)
        result['message'] = 'Flagged for vendor dispute'

    elif disposition == 'ACCEPT_NEW_CHARGE':
        # Unexpected charge is legitimate — add to catalog
        _write_accept_new_charge(conn, md5, step, corrected_value, rq_id, resolved_by, notes)
        result['message'] = 'New charge accepted — added to catalog'

    elif disposition == 'REJECT_CHARGE':
        # Charge should not be billed — flag for dispute
        _write_reject_charge(conn, md5, step, rq_id, resolved_by, notes)
        result['message'] = 'Charge rejected — flagged for dispute'

    else:
        conn.close()
        return {'success': False, 'message': f'Unknown disposition: {disposition}'}

    conn.commit()
    conn.close()
    return result


def _get_result_field(step: int) -> str:
    """Get the extraction result field name for a step."""
    from .step_runner import STEP_FIELDS
    return STEP_FIELDS[step][0]


def _write_accepted_value(conn, md5, step, value, rq_id, resolved_by, notes):
    """Write accepted value to extraction_result, update gate, close review."""
    field = _get_result_field(step)

    write_extraction_results([{
        'md5_hash': md5, 'step': step, 'field': field,
        'extracted_value': value, 'extraction_source': 'OVERRIDE',
    }], conn=conn)

    write_gate_results([{
        'md5_hash': md5, 'step': step, 'gate_status': 'PASSED',
    }], conn=conn)

    write_pipeline_events([{
        'md5_hash': md5, 'step': step, 'event_type': 'ACCEPTED',
        'field': field, 'value': value,
        'human_actor': resolved_by, 'review_queue_id': rq_id,
        'notes': notes,
    }], conn=conn)

    update_review_queue(rq_id, 'ACCEPT', notes=notes,
                        resolved_by=resolved_by, conn=conn)


def _write_corrected_value(conn, md5, step, value, rq_id, resolved_by, notes):
    """Write corrected value to extraction_result, update gate, close review."""
    field = _get_result_field(step)

    write_extraction_results([{
        'md5_hash': md5, 'step': step, 'field': field,
        'extracted_value': value, 'extraction_source': 'OVERRIDE',
    }], conn=conn)

    write_gate_results([{
        'md5_hash': md5, 'step': step, 'gate_status': 'PASSED',
    }], conn=conn)

    write_pipeline_events([{
        'md5_hash': md5, 'step': step, 'event_type': 'CORRECTED',
        'field': field, 'value': value,
        'human_actor': resolved_by, 'review_queue_id': rq_id,
        'notes': notes,
    }], conn=conn)

    update_review_queue(rq_id, 'SET', corrected_value=value,
                        notes=notes, resolved_by=resolved_by, conn=conn)


def _write_exclusion(conn, md5, step, rq_id, resolved_by, notes):
    """Exclude document at this step."""
    write_gate_results([{
        'md5_hash': md5, 'step': step, 'gate_status': 'EXCLUDED',
    }], conn=conn)

    write_pipeline_events([{
        'md5_hash': md5, 'step': step, 'event_type': 'EXCLUDED',
        'field': _get_result_field(step),
        'human_actor': resolved_by, 'review_queue_id': rq_id,
        'notes': notes,
    }], conn=conn)

    update_review_queue(rq_id, 'EXCLUDE', notes=notes,
                        resolved_by=resolved_by, conn=conn)


def _write_reroute(conn, md5, step, target_step, rq_id, resolved_by, notes):
    """Reroute to upstream step."""
    write_pipeline_events([{
        'md5_hash': md5, 'step': step, 'event_type': 'REROUTED',
        'field': _get_result_field(step),
        'value': str(target_step),
        'human_actor': resolved_by, 'review_queue_id': rq_id,
        'notes': notes,
    }], conn=conn)

    # Close current review row
    update_review_queue(rq_id, 'REROUTE', notes=notes,
                        resolved_by=resolved_by,
                        reroute_target=str(target_step), conn=conn)

    # Create new review row at the target step — carry notes forward
    write_review_queue([{
        'md5_hash': md5, 'step': target_step,
        'fail_category': f'REROUTED_FROM_STEP_{step}',
        'suggestion_reason': f'Rerouted from step {step}' + (f': {notes}' if notes else ''),
        'notes': notes,
    }], conn=conn)

    # Reset gate at current step
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM ip_gate_result WHERE md5_hash = %s AND step = %s",
        (md5, step),
    )


def _write_no_account(conn, md5, step, rq_id, resolved_by, notes):
    """Confirm no-account for this document."""
    field = _get_result_field(step)

    write_extraction_results([{
        'md5_hash': md5, 'step': step, 'field': field,
        'extracted_value': 'NO_ACCOUNT', 'extraction_source': 'OVERRIDE',
    }], conn=conn)

    write_gate_results([{
        'md5_hash': md5, 'step': step, 'gate_status': 'PASSED',
    }], conn=conn)

    write_pipeline_events([{
        'md5_hash': md5, 'step': step, 'event_type': 'ACCEPTED',
        'field': field, 'value': 'NO_ACCOUNT',
        'human_actor': resolved_by, 'review_queue_id': rq_id,
        'notes': notes or 'Confirmed NO_ACCOUNT',
    }], conn=conn)

    update_review_queue(rq_id, 'CONFIRM_NO_ACCOUNT', notes=notes,
                        resolved_by=resolved_by, conn=conn)


# =============================================================================
# Step 9 dispositions
# =============================================================================

def _write_map_container(conn, md5, step, corrected_value, rq_id, resolved_by, notes):
    """Map unmatched container to an existing catalog entry (by catalog_id)."""
    import json
    cur = conn.cursor()

    # corrected_value is JSON: {"line_item_id": X, "catalog_id": Y}
    try:
        mapping = json.loads(corrected_value) if corrected_value else {}
    except (json.JSONDecodeError, TypeError):
        mapping = {}

    catalog_id = mapping.get('catalog_id')
    line_item_id = mapping.get('line_item_id')

    if catalog_id:
        # Fetch catalog entry
        cur.execute(
            "SELECT container_id, service_id, expected_rate FROM ip_service_catalog"
            " WHERE catalog_id = %s",
            (catalog_id,),
        )
        cat = cur.fetchone()
        if cat and line_item_id:
            container_id, service_id, expected_rate = cat
            cur.execute("""
                UPDATE ip_invoice_line_item SET
                    container_id = %s, service_id = %s, expected_amount = %s,
                    status = 'PENDING'
                WHERE line_item_id = %s
            """, (container_id, service_id, expected_rate, line_item_id))

    write_pipeline_events([{
        'md5_hash': md5, 'step': step, 'event_type': 'CORRECTED',
        'field': 'catalog_match', 'value': corrected_value,
        'human_actor': resolved_by, 'review_queue_id': rq_id,
        'notes': notes,
    }], conn=conn)

    # Check if doc still has unmatched containers
    cur.execute(
        "SELECT COUNT(*) FROM ip_invoice_line_item"
        " WHERE md5_hash = %s AND status = 'UNMATCHED_CONTAINER'",
        (md5,),
    )
    remaining = cur.fetchone()[0]
    if remaining == 0:
        write_gate_results([{
            'md5_hash': md5, 'step': step, 'gate_status': 'PASSED',
        }], conn=conn)

    update_review_queue(rq_id, 'MAP', corrected_value=corrected_value,
                        notes=notes, resolved_by=resolved_by, conn=conn)


def _write_add_to_catalog(conn, md5, step, corrected_value, rq_id, resolved_by, notes):
    """Add new container to ip_service_catalog from review data."""
    import json
    try:
        new_entry = json.loads(corrected_value) if corrected_value else {}
    except (json.JSONDecodeError, TypeError):
        new_entry = {}

    if new_entry:
        write_service_catalog([new_entry], conn=conn)

    write_pipeline_events([{
        'md5_hash': md5, 'step': step, 'event_type': 'CATALOG_UPDATED',
        'field': 'catalog_match', 'value': corrected_value,
        'human_actor': resolved_by, 'review_queue_id': rq_id,
        'notes': notes or 'New catalog entry from review',
    }], conn=conn)

    update_review_queue(rq_id, 'ADD_TO_CATALOG', corrected_value=corrected_value,
                        notes=notes, resolved_by=resolved_by, conn=conn)


def _write_exclude_container(conn, md5, step, rq_id, resolved_by, notes):
    """Exclude unmatched containers for this document."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE ip_invoice_line_item SET status = 'EXCLUDED'
        WHERE md5_hash = %s AND status = 'UNMATCHED_CONTAINER'
    """, (md5,))

    write_gate_results([{
        'md5_hash': md5, 'step': step, 'gate_status': 'EXCLUDED',
    }], conn=conn)

    write_pipeline_events([{
        'md5_hash': md5, 'step': step, 'event_type': 'EXCLUDED',
        'field': 'catalog_match',
        'human_actor': resolved_by, 'review_queue_id': rq_id,
        'notes': notes or 'Containers excluded by HITL',
    }], conn=conn)

    update_review_queue(rq_id, 'EXCLUDE_CONTAINER', notes=notes,
                        resolved_by=resolved_by, conn=conn)


# =============================================================================
# Step 10 dispositions
# =============================================================================

def _write_accept_variance(conn, md5, step, corrected_value, rq_id, resolved_by, notes):
    """Accept rate variance — update catalog rate forward-looking."""
    import json
    cur = conn.cursor()

    # corrected_value may contain catalog_id + new_rate
    try:
        data = json.loads(corrected_value) if corrected_value else {}
    except (json.JSONDecodeError, TypeError):
        data = {}

    catalog_id = data.get('catalog_id')
    new_rate = data.get('new_rate')

    if catalog_id and new_rate is not None:
        update_service_catalog(catalog_id, {
            'expected_rate': new_rate,
            'catalog_status': 'STALE',
        }, conn=conn)

    # Update line items for this doc: accept all variances
    cur.execute("""
        UPDATE ip_invoice_line_item SET status = 'MATCH'
        WHERE md5_hash = %s AND status = 'RATE_VARIANCE'
    """, (md5,))

    write_gate_results([{
        'md5_hash': md5, 'step': step, 'gate_status': 'PASSED',
    }], conn=conn)

    write_pipeline_events([{
        'md5_hash': md5, 'step': step, 'event_type': 'ACCEPTED',
        'field': 'charge_validation', 'value': corrected_value,
        'human_actor': resolved_by, 'review_queue_id': rq_id,
        'notes': notes or 'Variance accepted',
    }], conn=conn)

    update_review_queue(rq_id, 'ACCEPT_VARIANCE', corrected_value=corrected_value,
                        notes=notes, resolved_by=resolved_by, conn=conn)


def _write_dispute(conn, md5, step, rq_id, resolved_by, notes):
    """Flag charges for vendor dispute."""
    write_pipeline_events([{
        'md5_hash': md5, 'step': step, 'event_type': 'DISPUTE',
        'field': 'charge_validation',
        'human_actor': resolved_by, 'review_queue_id': rq_id,
        'notes': notes or 'Flagged for vendor dispute',
    }], conn=conn)

    write_gate_results([{
        'md5_hash': md5, 'step': step, 'gate_status': 'PASSED',
    }], conn=conn)

    update_review_queue(rq_id, 'DISPUTE', notes=notes,
                        resolved_by=resolved_by, conn=conn)


def _write_accept_new_charge(conn, md5, step, corrected_value, rq_id, resolved_by, notes):
    """Accept unexpected charge — add to catalog."""
    import json
    try:
        new_entry = json.loads(corrected_value) if corrected_value else {}
    except (json.JSONDecodeError, TypeError):
        new_entry = {}

    if new_entry:
        write_service_catalog([new_entry], conn=conn)

    cur = conn.cursor()
    cur.execute("""
        UPDATE ip_invoice_line_item SET status = 'MATCH'
        WHERE md5_hash = %s AND status = 'UNEXPECTED_CHARGE'
    """, (md5,))

    write_gate_results([{
        'md5_hash': md5, 'step': step, 'gate_status': 'PASSED',
    }], conn=conn)

    write_pipeline_events([{
        'md5_hash': md5, 'step': step, 'event_type': 'CATALOG_UPDATED',
        'field': 'charge_validation', 'value': corrected_value,
        'human_actor': resolved_by, 'review_queue_id': rq_id,
        'notes': notes or 'New charge accepted into catalog',
    }], conn=conn)

    update_review_queue(rq_id, 'ACCEPT_NEW_CHARGE', corrected_value=corrected_value,
                        notes=notes, resolved_by=resolved_by, conn=conn)


def _write_reject_charge(conn, md5, step, rq_id, resolved_by, notes):
    """Reject charge — flag for vendor dispute."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE ip_invoice_line_item SET status = 'EXCLUDED'
        WHERE md5_hash = %s AND status IN ('UNEXPECTED_CHARGE', 'RATE_VARIANCE')
    """, (md5,))

    write_pipeline_events([{
        'md5_hash': md5, 'step': step, 'event_type': 'REJECTED_CHARGE',
        'field': 'charge_validation',
        'human_actor': resolved_by, 'review_queue_id': rq_id,
        'notes': notes or 'Charge rejected',
    }], conn=conn)

    write_gate_results([{
        'md5_hash': md5, 'step': step, 'gate_status': 'PASSED',
    }], conn=conn)

    update_review_queue(rq_id, 'REJECT_CHARGE', notes=notes,
                        resolved_by=resolved_by, conn=conn)
