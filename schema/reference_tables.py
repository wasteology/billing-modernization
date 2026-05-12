"""
Reference tables — Phase A (no FK dependencies).

7 tables:
  charge_code_ref, waste_stream_ref, container_size_ref,
  container_type_ref, container_ownership_ref, market_designation,
  pipeline_run
"""

TABLES = {
    "charge_code_ref": """
        CREATE TABLE IF NOT EXISTS charge_code_ref (
            charge_code_id      SERIAL PRIMARY KEY,
            charge_code         TEXT    NOT NULL UNIQUE,
            charge_code_name    TEXT,
            classification      TEXT    CHECK (classification IN (
                'recurring', 'recurring/one time', 'demand', 'demand - haul',
                'demand - haul contra', 'demand - weight', 'variable', 'one time',
                'adverse', 'fuel', 'rebate', 'recycling', 'cost increase',
                'late fee', 'management fee', 'local surcharges/fees',
                'study', 'none', 'unknown'
            )),
            second_attribute    TEXT,
            is_active           BOOLEAN NOT NULL DEFAULT TRUE
        )
    """,

    "waste_stream_ref": """
        CREATE TABLE IF NOT EXISTS waste_stream_ref (
            waste_stream_id       SERIAL PRIMARY KEY,
            waste_stream_code     TEXT    NOT NULL UNIQUE,
            waste_stream_name     TEXT,
            waste_stream_category TEXT,
            is_active             BOOLEAN NOT NULL DEFAULT TRUE
        )
    """,

    "container_size_ref": """
        CREATE TABLE IF NOT EXISTS container_size_ref (
            container_size_id SERIAL PRIMARY KEY,
            size_yards        DOUBLE PRECISION NOT NULL UNIQUE,
            size_label        TEXT
        )
    """,

    "container_type_ref": """
        CREATE TABLE IF NOT EXISTS container_type_ref (
            container_type_id   SERIAL PRIMARY KEY,
            container_type_code TEXT    NOT NULL UNIQUE,
            container_type_name TEXT
        )
    """,

    "container_ownership_ref": """
        CREATE TABLE IF NOT EXISTS container_ownership_ref (
            ownership_id   SERIAL PRIMARY KEY,
            ownership_code TEXT    NOT NULL UNIQUE,
            ownership_name TEXT
        )
    """,

    "market_designation": """
        CREATE TABLE IF NOT EXISTS market_designation (
            market_id        SERIAL PRIMARY KEY,
            zip_code         TEXT    NOT NULL,
            waste_stream_id  INTEGER NOT NULL,
            market_type      TEXT    CHECK (market_type IN ('franchise', 'open')),
            franchise_hauler TEXT,
            effective_date   DATE    NOT NULL,
            source_note      TEXT,
            ordinance_url    TEXT,

            UNIQUE (zip_code, waste_stream_id, effective_date),
            FOREIGN KEY (waste_stream_id) REFERENCES waste_stream_ref (waste_stream_id)
        )
    """,

    "pipeline_run": """
        CREATE TABLE IF NOT EXISTS pipeline_run (
            run_id         SERIAL PRIMARY KEY,
            started_at     TIMESTAMP NOT NULL,
            completed_at   TIMESTAMP,
            status         TEXT    CHECK (status IN ('running', 'completed', 'failed')),
            step_timings   TEXT,
            source_summary TEXT,
            error_message  TEXT,
            notes          TEXT
        )
    """,

    "sync_watermark": """
        CREATE TABLE IF NOT EXISTS sync_watermark (
            watermark_id         SERIAL PRIMARY KEY,
            table_name           TEXT NOT NULL UNIQUE,
            last_sync_at         TIMESTAMP NOT NULL,
            high_water_value     TEXT,
            rows_synced          INTEGER,
            sync_duration_seconds DOUBLE PRECISION,
            notes                TEXT
        )
    """,
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ccr_classification ON charge_code_ref (classification)",
    "CREATE INDEX IF NOT EXISTS idx_md_zip ON market_designation (zip_code)",
]


def create_tables(cursor):
    """Create all reference tables and indexes."""
    for ddl in TABLES.values():
        cursor.execute(ddl)
    for idx in INDEXES:
        cursor.execute(idx)
