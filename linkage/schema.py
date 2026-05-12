"""
DDL for invoice linkage tables.

3 tables:
  invoice_registry       — One row per invoice PDF (GAPI + regex + manual layers)
  invoice_service_match  — Links invoices to billing_charges rows
  account_location_map   — Final output: account → location
"""

TABLES = {
    "invoice_registry": """
        CREATE TABLE IF NOT EXISTS invoice_registry (
            invoice_md5            TEXT PRIMARY KEY,

            -- Doc AI baseline (from vw_sharepoint_gapi_all)
            gapi_vendor_name       TEXT,
            gapi_service_address   TEXT,
            gapi_invoice_date      DATE,
            gapi_invoice_amount    DOUBLE PRECISION,
            gapi_account_number    TEXT,
            gapi_invoice_number    TEXT,
            gapi_counterparty      TEXT,
            gapi_site_state        TEXT,
            gapi_status            TEXT,

            -- Regex overrides (from parsing_engines via ocr_document)
            regex_vendor_name      TEXT,
            regex_service_address  TEXT,
            regex_service_city     TEXT,
            regex_service_state    TEXT,
            regex_service_postal   TEXT,
            regex_invoice_date     DATE,
            regex_invoice_amount   DOUBLE PRECISION,
            regex_account_number   TEXT,
            regex_invoice_number   TEXT,

            -- Manual overrides (human corrections, survive re-runs)
            manual_vendor_name     TEXT,
            manual_service_address TEXT,
            manual_service_city    TEXT,
            manual_service_state   TEXT,
            manual_service_postal  TEXT,
            manual_invoice_date    DATE,
            manual_invoice_amount  DOUBLE PRECISION,
            manual_account_number  TEXT,
            manual_invoice_number  TEXT,

            -- Resolved best values: COALESCE(manual, regex, gapi)
            resolved_vendor_name   TEXT,
            resolved_vendor_id     INTEGER REFERENCES vendor (vendor_id),
            resolved_address       TEXT,
            resolved_city          TEXT,
            resolved_state         TEXT,
            resolved_postal_code   TEXT,
            resolved_invoice_date  DATE,
            resolved_invoice_amount DOUBLE PRECISION,
            resolved_account_number TEXT,
            resolved_invoice_number TEXT,

            -- Status tracking
            sp_created_date        DATE,
            enrichment_status      TEXT CHECK (enrichment_status IN
                ('pending', 'gapi_only', 'enriched', 'manual_review')),
            match_status           TEXT CHECK (match_status IN
                ('unmatched', 'matched', 'ambiguous', 'excluded')),
            match_location_id      INTEGER REFERENCES location (location_id),
            match_confidence       TEXT CHECK (match_confidence IN ('high', 'medium', 'low')),

            created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,

    "invoice_service_match": """
        CREATE TABLE IF NOT EXISTS invoice_service_match (
            match_id               SERIAL PRIMARY KEY,
            invoice_md5            TEXT NOT NULL REFERENCES invoice_registry (invoice_md5),
            billing_charge_id      INTEGER NOT NULL REFERENCES billing_charges (billing_charge_id),
            service_id             TEXT NOT NULL REFERENCES services_current (service_id),
            location_id            INTEGER REFERENCES location (location_id),

            vendor_match           BOOLEAN NOT NULL,
            address_match_score    DOUBLE PRECISION,
            date_match             BOOLEAN NOT NULL,
            amount_residual        DOUBLE PRECISION,

            match_method           TEXT,
            match_confidence       TEXT CHECK (match_confidence IN ('high', 'medium', 'low')),
            created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,

    "account_location_map": """
        CREATE TABLE IF NOT EXISTS account_location_map (
            map_id                 SERIAL PRIMARY KEY,
            vendor_id              INTEGER NOT NULL REFERENCES vendor (vendor_id),
            hauler_account_number  TEXT NOT NULL,
            location_id            INTEGER NOT NULL REFERENCES location (location_id),
            customer_id            INTEGER REFERENCES customer (customer_id),

            invoice_count          INTEGER,
            first_seen_date        DATE,
            last_seen_date         DATE,
            total_invoiced_amount  DOUBLE PRECISION,
            confidence             TEXT CHECK (confidence IN ('high', 'medium', 'low', 'manual')),
            evidence_summary       TEXT,

            is_active              BOOLEAN DEFAULT TRUE,
            is_manual_override     BOOLEAN DEFAULT FALSE,
            created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE (vendor_id, hauler_account_number, location_id)
        )
    """,
}

INDEXES = [
    # invoice_registry
    "CREATE INDEX IF NOT EXISTS idx_ir2_vendor_id        ON invoice_registry (resolved_vendor_id)",
    "CREATE INDEX IF NOT EXISTS idx_ir2_enrichment       ON invoice_registry (enrichment_status)",
    "CREATE INDEX IF NOT EXISTS idx_ir2_match_status     ON invoice_registry (match_status)",
    "CREATE INDEX IF NOT EXISTS idx_ir2_invoice_date     ON invoice_registry (resolved_invoice_date)",
    "CREATE INDEX IF NOT EXISTS idx_ir2_account          ON invoice_registry (resolved_account_number)",
    "CREATE INDEX IF NOT EXISTS idx_ir2_location         ON invoice_registry (match_location_id)",
    # invoice_service_match
    "CREATE INDEX IF NOT EXISTS idx_ism_invoice_md5      ON invoice_service_match (invoice_md5)",
    "CREATE INDEX IF NOT EXISTS idx_ism_billing_charge   ON invoice_service_match (billing_charge_id)",
    "CREATE INDEX IF NOT EXISTS idx_ism_location_id      ON invoice_service_match (location_id)",
    "CREATE INDEX IF NOT EXISTS idx_ism_service_id       ON invoice_service_match (service_id)",
    # account_location_map
    "CREATE INDEX IF NOT EXISTS idx_alm_vendor_account   ON account_location_map (vendor_id, hauler_account_number)",
    "CREATE INDEX IF NOT EXISTS idx_alm_location_id      ON account_location_map (location_id)",
    "CREATE INDEX IF NOT EXISTS idx_alm_customer_id      ON account_location_map (customer_id)",
]


def create_tables(cursor):
    """Create all invoice linkage tables and indexes."""
    for ddl in TABLES.values():
        cursor.execute(ddl)
    for idx in INDEXES:
        cursor.execute(idx)
