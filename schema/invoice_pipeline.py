"""
Invoice Processing Pipeline tables (ip_ prefix).

12 objects in FK-safe creation order:
  1. ip_raw_document          (no FKs)
  2. ip_vendor_pattern        (self-referencing FK only)
  3. ip_vendor_profile        (no FKs)
  4. ip_service_catalog       (no FKs — ERP-seeded)
  5. ip_extraction_result     (→ ip_raw_document, → ip_vendor_pattern)
  6. ip_validation_result     (→ ip_extraction_result)
  7. ip_review_queue          (→ ip_raw_document)
  8. ip_pipeline_event        (→ ip_raw_document, → ip_review_queue, self-ref)
  9. ip_gate_result           (→ ip_raw_document, → ip_pipeline_event)
 10. ip_fix_log               (→ ip_vendor_pattern, → ip_review_queue)
 11. ip_invoice_line_item     (→ ip_raw_document)
 12. ip_staging_invoice       (VIEW)

Pilot: Republic Services, Anytime Waste, Waste Management, GFL.
"""

TABLES = {
    "ip_raw_document": """
        CREATE TABLE IF NOT EXISTS ip_raw_document (
            md5_hash         TEXT PRIMARY KEY,
            sp_created_date  DATE,
            source_file      TEXT,
            raw_ocr_text     TEXT,
            sync_date        TIMESTAMP DEFAULT NOW(),
            sync_status      TEXT CHECK (sync_status IN ('OK', 'NO_TEXT', 'NOT_FOUND', 'ERROR'))
        )
    """,

    "ip_vendor_pattern": """
        CREATE TABLE IF NOT EXISTS ip_vendor_pattern (
            vendor_pattern_id   SERIAL PRIMARY KEY,
            vendor_name         TEXT NOT NULL,
            field               TEXT NOT NULL,
            format_variant      INTEGER DEFAULT 1,
            pattern_type        TEXT CHECK (pattern_type IN ('PRIMARY', 'FALLBACK', 'GENERIC')),
            priority            INTEGER NOT NULL,
            regex_pattern       TEXT NOT NULL,
            regex_flags         TEXT DEFAULT 'IGNORECASE',
            capture_group       INTEGER DEFAULT 1,
            normalization       TEXT DEFAULT 'NONE',
            scan_type           TEXT DEFAULT 'INLINE' CHECK (scan_type IN
                                    ('INLINE', 'FORWARD_COLUMNAR', 'REVERSE_COLUMNAR', 'WIDE_COLUMNAR')),
            scan_lines          INTEGER DEFAULT 1,
            date_format         TEXT,
            is_no_account       BOOLEAN DEFAULT FALSE,
            is_active           BOOLEAN DEFAULT TRUE,
            version             INTEGER DEFAULT 1,
            prior_version_id    INTEGER REFERENCES ip_vendor_pattern (vendor_pattern_id),
            valid_from          TIMESTAMP DEFAULT NOW(),
            valid_to            TIMESTAMP,
            deployed_by         TEXT,
            deployed_at         TIMESTAMP DEFAULT NOW(),
            notes               TEXT,

            -- Multi-match charge extraction columns (steps 2-6 use defaults)
            execution_mode      TEXT DEFAULT 'SINGLE'
                                CHECK (execution_mode IN ('SINGLE', 'MULTI')),
            capture_map         JSONB,
            pattern_tier        TEXT DEFAULT 'TIER_1'
                                CHECK (pattern_tier IN ('TIER_1', 'TIER_2', 'TIER_FALLBACK')),
            activation_condition TEXT,
            description_template TEXT,

            UNIQUE (vendor_name, field, format_variant, priority, version)
        )
    """,

    "ip_vendor_profile": """
        CREATE TABLE IF NOT EXISTS ip_vendor_profile (
            vendor_profile_id       SERIAL PRIMARY KEY,
            vendor_name             TEXT NOT NULL,
            field                   TEXT NOT NULL,
            format_variant          INTEGER DEFAULT 1,
            detection_zone          TEXT,
            co_occurrence_markers   TEXT,
            layout_fingerprint      TEXT,
            value_length_min        INTEGER,
            value_length_max        INTEGER,
            value_composition       TEXT,
            value_prefix_pattern    TEXT,
            known_value_examples    TEXT,
            confirmed_invoice_count INTEGER DEFAULT 0,
            profile_status          TEXT DEFAULT 'ACTIVE' CHECK (profile_status IN
                                        ('ACTIVE', 'STALE', 'BUILDING')),
            created_at              TIMESTAMP DEFAULT NOW(),
            updated_at              TIMESTAMP DEFAULT NOW(),

            UNIQUE (vendor_name, field, format_variant)
        )
    """,

    "ip_extraction_result": """
        CREATE TABLE IF NOT EXISTS ip_extraction_result (
            extraction_result_id  SERIAL PRIMARY KEY,
            md5_hash              TEXT NOT NULL,
            step                  INTEGER NOT NULL,
            attempt               INTEGER DEFAULT 1,
            field                 TEXT NOT NULL,
            extracted_value       TEXT,
            extraction_source     TEXT CHECK (extraction_source IN ('ENGINE', 'OVERRIDE', 'REPROCESS')),
            vendor_pattern_id     INTEGER,
            extracted_at          TIMESTAMP DEFAULT NOW(),

            FOREIGN KEY (md5_hash)          REFERENCES ip_raw_document (md5_hash),
            FOREIGN KEY (vendor_pattern_id) REFERENCES ip_vendor_pattern (vendor_pattern_id)
        )
    """,

    "ip_validation_result": """
        CREATE TABLE IF NOT EXISTS ip_validation_result (
            validation_result_id    SERIAL PRIMARY KEY,
            extraction_result_id    INTEGER NOT NULL,
            md5_hash                TEXT NOT NULL,
            step                    INTEGER NOT NULL,
            check_name              TEXT NOT NULL,
            check_result            TEXT NOT NULL CHECK (check_result IN ('PASS', 'FAIL')),
            confidence              TEXT CHECK (confidence IN ('HIGH', 'LOW')),
            detail                  TEXT,
            checked_at              TIMESTAMP DEFAULT NOW(),

            FOREIGN KEY (extraction_result_id) REFERENCES ip_extraction_result (extraction_result_id)
        )
    """,

    "ip_review_queue": """
        CREATE TABLE IF NOT EXISTS ip_review_queue (
            review_queue_id         SERIAL PRIMARY KEY,
            md5_hash                TEXT NOT NULL,
            step                    INTEGER NOT NULL,
            fail_category           TEXT NOT NULL,
            ai_suggestion           TEXT,
            suggestion_confidence   TEXT CHECK (suggestion_confidence IN ('HIGH', 'MEDIUM', 'LOW', 'NONE')),
            suggestion_reason       TEXT,
            human_action            TEXT CHECK (human_action IN
                                        ('ACCEPT', 'SET', 'SKIP', 'EXCLUDE', 'REROUTE', 'CONFIRM_NO_ACCOUNT',
                                         'MAP', 'ADD_TO_CATALOG', 'EXCLUDE_CONTAINER',
                                         'ACCEPT_VARIANCE', 'DISPUTE', 'ACCEPT_NEW_CHARGE', 'REJECT_CHARGE')),
            corrected_value         TEXT,
            reroute_target          TEXT,
            notes                   TEXT,
            status                  TEXT DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'RESOLVED', 'REROUTED')),
            opened_at               TIMESTAMP DEFAULT NOW(),
            resolved_at             TIMESTAMP,
            resolved_by             TEXT,
            pdf_link                TEXT,

            FOREIGN KEY (md5_hash) REFERENCES ip_raw_document (md5_hash)
        )
    """,

    "ip_pipeline_event": """
        CREATE TABLE IF NOT EXISTS ip_pipeline_event (
            pipeline_event_id   SERIAL PRIMARY KEY,
            md5_hash            TEXT NOT NULL,
            step                INTEGER NOT NULL,
            event_type          TEXT NOT NULL CHECK (event_type IN (
                                    'EXTRACTED', 'VALIDATION_PASS', 'VALIDATION_FAIL',
                                    'QUEUED_REVIEW', 'ACCEPTED', 'CORRECTED',
                                    'EXCLUDED', 'REROUTED', 'GATE_PASSED',
                                    'GATE_BLOCKED', 'REPROCESSED', 'EXCLUSION_REVERSED',
                                    'DISPUTE', 'REJECTED_CHARGE', 'CATALOG_UPDATED')),
            field               TEXT,
            value               TEXT,
            prior_event_id      INTEGER,
            human_actor         TEXT,
            review_queue_id     INTEGER,
            notes               TEXT,
            event_at            TIMESTAMP DEFAULT NOW(),

            FOREIGN KEY (md5_hash)        REFERENCES ip_raw_document (md5_hash),
            FOREIGN KEY (prior_event_id)  REFERENCES ip_pipeline_event (pipeline_event_id),
            FOREIGN KEY (review_queue_id) REFERENCES ip_review_queue (review_queue_id)
        )
    """,

    "ip_gate_result": """
        CREATE TABLE IF NOT EXISTS ip_gate_result (
            gate_result_id   SERIAL PRIMARY KEY,
            md5_hash         TEXT NOT NULL,
            step             INTEGER NOT NULL,
            gate_status      TEXT NOT NULL CHECK (gate_status IN ('PASSED', 'BLOCKED', 'EXCLUDED')),
            passed_at        TIMESTAMP,
            last_event_id    INTEGER,

            UNIQUE (md5_hash, step),
            FOREIGN KEY (md5_hash)      REFERENCES ip_raw_document (md5_hash),
            FOREIGN KEY (last_event_id) REFERENCES ip_pipeline_event (pipeline_event_id)
        )
    """,

    "ip_fix_log": """
        CREATE TABLE IF NOT EXISTS ip_fix_log (
            fix_log_id       SERIAL PRIMARY KEY,
            created_at       TIMESTAMP DEFAULT NOW(),
            step             INTEGER NOT NULL,
            fail_category    TEXT NOT NULL,
            vendor           TEXT NOT NULL,
            md5_sample       TEXT,
            ocr_sample       TEXT,
            fix_type         TEXT CHECK (fix_type IN ('NEW_PATTERN', 'PATTERN_FIX', 'NO_ACCOUNT_CONFIRM')),
            fix_status       TEXT DEFAULT 'OPEN' CHECK (fix_status IN
                                ('OPEN', 'IN_PROGRESS', 'DEPLOYED', 'CLOSED')),
            vendor_pattern_id INTEGER,
            deployed_at      TIMESTAMP,
            closed_at        TIMESTAMP,
            review_queue_id  INTEGER,
            notes            TEXT,

            FOREIGN KEY (vendor_pattern_id) REFERENCES ip_vendor_pattern (vendor_pattern_id),
            FOREIGN KEY (review_queue_id)   REFERENCES ip_review_queue (review_queue_id)
        )
    """,

    "ip_service_catalog": """
        CREATE TABLE IF NOT EXISTS ip_service_catalog (
            catalog_id                SERIAL PRIMARY KEY,
            service_id                TEXT NOT NULL,
            account_number            TEXT NOT NULL,
            vendor                    TEXT NOT NULL,
            container_id              TEXT NOT NULL,
            container_index           INTEGER NOT NULL,
            equipment_type            TEXT NOT NULL,
            equipment_size            TEXT,
            material                  TEXT,
            schedule                  TEXT,
            charge_type               TEXT NOT NULL,
            expected_rate             NUMERIC(12,4),
            rate_uom                  TEXT,
            invoice_level_charge_pct  NUMERIC(6,4),
            catalog_status            TEXT NOT NULL DEFAULT 'BUILDING'
                                      CHECK (catalog_status IN ('BUILDING', 'CONFIRMED', 'STALE')),
            confirmed_at              TIMESTAMP,
            confirmed_by              TEXT,
            created_at                TIMESTAMP DEFAULT NOW(),
            updated_at                TIMESTAMP DEFAULT NOW()
        )
    """,

    "ip_invoice_line_item": """
        CREATE TABLE IF NOT EXISTS ip_invoice_line_item (
            line_item_id        SERIAL PRIMARY KEY,
            md5_hash            TEXT NOT NULL,
            invoice_date        DATE,
            invoice_total       NUMERIC(12,2),
            vendor              TEXT,
            account_number      TEXT,
            container_index     INTEGER NOT NULL,
            equipment_type      TEXT,
            equipment_size      TEXT,
            material            TEXT,
            schedule            TEXT,
            container_id        TEXT,
            service_id          TEXT,
            charge_type         TEXT,
            billed_amount       NUMERIC(12,4),
            expected_amount     NUMERIC(12,4),
            variance            NUMERIC(12,4),
            variance_pct        NUMERIC(8,4),
            status              TEXT NOT NULL CHECK (status IN (
                                    'MATCH', 'RATE_VARIANCE', 'UNEXPECTED_CHARGE',
                                    'MISSING_CHARGE', 'UNMATCHED_CONTAINER',
                                    'INVOICE_LEVEL_VARIANCE', 'PENDING', 'EXCLUDED')),
            created_at          TIMESTAMP DEFAULT NOW(),

            FOREIGN KEY (md5_hash) REFERENCES ip_raw_document (md5_hash)
        )
    """,
}

INDEXES = [
    # ip_raw_document
    "CREATE INDEX IF NOT EXISTS idx_ip_rd_sync_status ON ip_raw_document (sync_status)",
    "CREATE INDEX IF NOT EXISTS idx_ip_rd_sp_date     ON ip_raw_document (sp_created_date)",

    # ip_vendor_pattern
    "CREATE INDEX IF NOT EXISTS idx_ip_vp_vendor_field ON ip_vendor_pattern (vendor_name, field) WHERE is_active = TRUE",
    "CREATE INDEX IF NOT EXISTS idx_ip_vp_active       ON ip_vendor_pattern (is_active)",
    "CREATE INDEX IF NOT EXISTS idx_ip_vp_field        ON ip_vendor_pattern (field)",

    # ip_vendor_profile
    "CREATE INDEX IF NOT EXISTS idx_ip_vpr_vendor_field ON ip_vendor_profile (vendor_name, field)",
    "CREATE INDEX IF NOT EXISTS idx_ip_vpr_status       ON ip_vendor_profile (profile_status)",

    # ip_extraction_result
    "CREATE INDEX IF NOT EXISTS idx_ip_er_md5_step ON ip_extraction_result (md5_hash, step)",
    "CREATE INDEX IF NOT EXISTS idx_ip_er_field    ON ip_extraction_result (field)",
    "CREATE INDEX IF NOT EXISTS idx_ip_er_pattern  ON ip_extraction_result (vendor_pattern_id)",

    # ip_validation_result
    "CREATE INDEX IF NOT EXISTS idx_ip_vr_extraction ON ip_validation_result (extraction_result_id)",
    "CREATE INDEX IF NOT EXISTS idx_ip_vr_md5_step   ON ip_validation_result (md5_hash, step)",
    "CREATE INDEX IF NOT EXISTS idx_ip_vr_result     ON ip_validation_result (check_result)",

    # ip_review_queue
    "CREATE INDEX IF NOT EXISTS idx_ip_rq_md5_step  ON ip_review_queue (md5_hash, step)",
    "CREATE INDEX IF NOT EXISTS idx_ip_rq_status    ON ip_review_queue (status)",
    "CREATE INDEX IF NOT EXISTS idx_ip_rq_step_open ON ip_review_queue (step) WHERE status = 'OPEN'",
    "CREATE INDEX IF NOT EXISTS idx_ip_rq_vendor    ON ip_review_queue (fail_category)",

    # ip_pipeline_event
    "CREATE INDEX IF NOT EXISTS idx_ip_pe_md5        ON ip_pipeline_event (md5_hash)",
    "CREATE INDEX IF NOT EXISTS idx_ip_pe_md5_step   ON ip_pipeline_event (md5_hash, step)",
    "CREATE INDEX IF NOT EXISTS idx_ip_pe_event_type ON ip_pipeline_event (event_type)",
    "CREATE INDEX IF NOT EXISTS idx_ip_pe_event_at       ON ip_pipeline_event (event_at)",
    "CREATE INDEX IF NOT EXISTS idx_ip_pe_review_queue_id ON ip_pipeline_event (review_queue_id)",
    "CREATE INDEX IF NOT EXISTS idx_ip_pe_prior_event_id  ON ip_pipeline_event (prior_event_id)",

    # ip_gate_result
    "CREATE INDEX IF NOT EXISTS idx_ip_gr_status ON ip_gate_result (gate_status)",
    "CREATE INDEX IF NOT EXISTS idx_ip_gr_md5    ON ip_gate_result (md5_hash)",

    # ip_fix_log
    "CREATE INDEX IF NOT EXISTS idx_ip_fl_status ON ip_fix_log (fix_status)",
    "CREATE INDEX IF NOT EXISTS idx_ip_fl_vendor ON ip_fix_log (vendor)",
    "CREATE INDEX IF NOT EXISTS idx_ip_fl_step             ON ip_fix_log (step)",
    "CREATE INDEX IF NOT EXISTS idx_ip_fl_review_queue_id  ON ip_fix_log (review_queue_id)",

    # ip_service_catalog
    "CREATE INDEX IF NOT EXISTS idx_ip_sc_account_vendor ON ip_service_catalog (account_number, vendor)",
    "CREATE INDEX IF NOT EXISTS idx_ip_sc_service_id     ON ip_service_catalog (service_id)",
    "CREATE INDEX IF NOT EXISTS idx_ip_sc_status         ON ip_service_catalog (catalog_status)",

    # ip_invoice_line_item
    "CREATE INDEX IF NOT EXISTS idx_ip_ili_md5           ON ip_invoice_line_item (md5_hash)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_ip_ili_md5_ct_ct ON ip_invoice_line_item (md5_hash, container_index, charge_type)",
    "CREATE INDEX IF NOT EXISTS idx_ip_ili_status        ON ip_invoice_line_item (status)",
    "CREATE INDEX IF NOT EXISTS idx_ip_ili_service_id    ON ip_invoice_line_item (service_id)",
]

VIEWS = {
    "ip_staging_invoice": """
        CREATE OR REPLACE VIEW ip_staging_invoice AS
        SELECT
            r.md5_hash,
            r.sp_created_date,
            r.source_file,
            e_vendor.extracted_value    AS detected_vendor,
            e_account.extracted_value   AS hauler_account_number,
            e_invoice.extracted_value   AS hauler_invoice_number,
            e_date.extracted_value      AS invoice_date,
            e_amount.extracted_value    AS bill_total,
            g1.gate_status              AS step1_status,
            g2.gate_status              AS step2_status,
            g3.gate_status              AS step3_status,
            g4.gate_status              AS step4_status,
            g5.gate_status              AS step5_status,
            g6.gate_status              AS step6_status,
            g7.gate_status              AS step7_status
        FROM ip_raw_document r
        JOIN ip_gate_result g1 ON r.md5_hash = g1.md5_hash AND g1.step = 1
            AND g1.gate_status IN ('PASSED', 'EXCLUDED')
        LEFT JOIN ip_gate_result g2 ON r.md5_hash = g2.md5_hash AND g2.step = 2
        LEFT JOIN ip_gate_result g3 ON r.md5_hash = g3.md5_hash AND g3.step = 3
        LEFT JOIN ip_gate_result g4 ON r.md5_hash = g4.md5_hash AND g4.step = 4
        LEFT JOIN ip_gate_result g5 ON r.md5_hash = g5.md5_hash AND g5.step = 5
        LEFT JOIN ip_gate_result g6 ON r.md5_hash = g6.md5_hash AND g6.step = 6
        LEFT JOIN ip_gate_result g7 ON r.md5_hash = g7.md5_hash AND g7.step = 7
        LEFT JOIN ip_extraction_result e_vendor
            ON r.md5_hash = e_vendor.md5_hash AND e_vendor.field = 'detected_vendor'
        LEFT JOIN ip_extraction_result e_account
            ON r.md5_hash = e_account.md5_hash AND e_account.field = 'hauler_account_number'
        LEFT JOIN ip_extraction_result e_invoice
            ON r.md5_hash = e_invoice.md5_hash AND e_invoice.field = 'hauler_invoice_number'
        LEFT JOIN ip_extraction_result e_date
            ON r.md5_hash = e_date.md5_hash AND e_date.field = 'invoice_date'
        LEFT JOIN ip_extraction_result e_amount
            ON r.md5_hash = e_amount.md5_hash AND e_amount.field = 'bill_total'
    """,
}


def create_tables(cursor):
    """Create all invoice pipeline tables and indexes."""
    for ddl in TABLES.values():
        cursor.execute(ddl)
    for idx in INDEXES:
        cursor.execute(idx)


def create_views(cursor):
    """Create all invoice pipeline views."""
    for name, ddl in VIEWS.items():
        cursor.execute(f"DROP VIEW IF EXISTS {name}")
        cursor.execute(ddl)
