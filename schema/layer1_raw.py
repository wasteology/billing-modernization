"""
Layer 1 — Raw Inbound tables.

3 tables:
  ocr_document, invoice_raw, line_item_raw
"""

TABLES = {
    "ocr_document": """
        CREATE TABLE IF NOT EXISTS ocr_document (
            md5_hash        TEXT PRIMARY KEY,
            raw_text        TEXT NOT NULL,
            sp_created_date DATE
        )
    """,

    "invoice_raw": """
        CREATE TABLE IF NOT EXISTS invoice_raw (
            invoice_raw_id    SERIAL PRIMARY KEY,
            md5_hash          TEXT    UNIQUE,
            vendor_id         INTEGER,
            hauler_account_number TEXT,
            hauler_invoice_number TEXT,
            bill_date         DATE,
            service_month     INTEGER,
            service_year      INTEGER,
            raw_total         DOUBLE PRECISION,
            document_path     TEXT,
            ocr_confidence    DOUBLE PRECISION,
            processing_status TEXT CHECK (processing_status IN
                ('received', 'ocr_complete', 'interpreted', 'conformed', 'exception')),
            received_datetime TIMESTAMP,
            export_datetime   TIMESTAMP,

            FOREIGN KEY (vendor_id) REFERENCES vendor (vendor_id)
        )
    """,

    "line_item_raw": """
        CREATE TABLE IF NOT EXISTS line_item_raw (
            line_item_raw_id     SERIAL PRIMARY KEY,
            invoice_raw_id       INTEGER NOT NULL,
            line_number          INTEGER,
            raw_charge_description TEXT,
            raw_waste_stream     TEXT,
            raw_container_detail TEXT,
            raw_quantity         DOUBLE PRECISION,
            raw_unit_price       DOUBLE PRECISION,
            raw_amount           DOUBLE PRECISION,
            raw_weight           DOUBLE PRECISION,
            raw_weight_uom       TEXT,
            ocr_confidence       DOUBLE PRECISION,

            FOREIGN KEY (invoice_raw_id) REFERENCES invoice_raw (invoice_raw_id)
        )
    """,
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ir_processing_status ON invoice_raw (processing_status)",
    "CREATE INDEX IF NOT EXISTS idx_ir_hauler_account    ON invoice_raw (hauler_account_number)",
    "CREATE INDEX IF NOT EXISTS idx_ir_hauler_invoice    ON invoice_raw (hauler_invoice_number)",
]


def create_tables(cursor):
    """Create all Layer 1 tables and indexes."""
    for ddl in TABLES.values():
        cursor.execute(ddl)
    for idx in INDEXES:
        cursor.execute(idx)
