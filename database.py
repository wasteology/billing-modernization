"""
Database connection helpers and schema orchestrator for PostgreSQL.

- get_connection(): psycopg2 connection with search_path set
- get_cursor(): context manager for transactional work (with rollback)
- atomic_rebuild(): context manager for idempotent table rebuilds
- atomic_update(): context manager for SAVEPOINT-based updates (no DELETE)
- scalar(): helper to fetch a single scalar value
- populate_charge_tiers(): normalize 5-tier → service_charge_tier
- init_database(): creates schema + all tables in FK-safe order
- reset_database(): DROP SCHEMA CASCADE + recreate
- export_ddl(): generate standalone SQL script
"""

import logging
import time
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from .config import PG_CONFIG, SCHEMA_NAME
from .schema import reference_tables, layer1_raw, layer2_operational, layer3_analytical, invoice_pipeline, dashboard_auth
from .invoice_linkage.schema import create_tables as create_linkage_tables, TABLES as LINKAGE_TABLES, INDEXES as LINKAGE_INDEXES

log = logging.getLogger(__name__)


def get_connection():
    """Get PostgreSQL connection with search_path set to wasteology_ops."""
    conn = psycopg2.connect(**PG_CONFIG)
    conn.autocommit = False
    # Azure server sets default_transaction_read_only=on; override for writes
    cur = conn.cursor()
    cur.execute("SET default_transaction_read_only = off")
    conn.commit()
    cur.close()
    return conn


@contextmanager
def get_cursor():
    """Context manager for database cursor with auto-commit and rollback on error.

    Uses RealDictCursor so rows are accessed as dicts.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def atomic_rebuild(conn, tables: list[str], disable_fk: bool = False):
    """Context manager for atomic table rebuilds using savepoints.

    Deletes rows from the named tables, yields the cursor for inserts,
    then commits on success or rolls back on failure. If disable_fk is True,
    FK constraints are deferred for the duration.

    Usage:
        conn = get_connection()
        with atomic_rebuild(conn, ['chain_monthly']) as cursor:
            # cursor is ready — tables have been cleared
            cursor.execute("INSERT INTO chain_monthly ...")
    """
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    savepoint = f"rebuild_{'_'.join(tables)}"

    if disable_fk:
        cursor.execute("SET CONSTRAINTS ALL DEFERRED")

    cursor.execute(f"SAVEPOINT {savepoint}")
    try:
        for table in tables:
            cursor.execute(f"DELETE FROM {table}")

        yield cursor

        cursor.execute(f"RELEASE SAVEPOINT {savepoint}")
        conn.commit()
    except Exception:
        cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        cursor.execute(f"RELEASE SAVEPOINT {savepoint}")
        conn.commit()  # commit the rollback
        raise
    finally:
        if disable_fk:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


@contextmanager
def atomic_update(conn):
    """Context manager for SAVEPOINT-based updates without DELETE.

    Same pattern as atomic_rebuild but does not clear any tables.
    Used by update-only pipeline mode.
    """
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    savepoint = f"update_{int(time.time())}"
    cursor.execute(f"SAVEPOINT {savepoint}")
    try:
        yield cursor
        cursor.execute(f"RELEASE SAVEPOINT {savepoint}")
        conn.commit()
    except Exception:
        cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        cursor.execute(f"RELEASE SAVEPOINT {savepoint}")
        conn.commit()
        raise


def scalar(conn, sql, params=None):
    """Execute a query and return the first column of the first row."""
    cursor = conn.cursor()
    cursor.execute(sql, params or ())
    row = cursor.fetchone()
    return row[0] if row else None


def populate_charge_tiers(conn):
    """Populate service_charge_tier from services_current 5-tier columns.

    Normalizes the repeating charge_type_{1..5} groups into rows.
    Idempotent: deletes existing rows and rebuilds.
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM service_charge_tier")

    # CAST to DOUBLE PRECISION handles embedded UOM like '45.00 ST' -> 45.0
    cursor.execute("""
        INSERT INTO service_charge_tier
            (service_id, tier, charge_type, cost, charge, cost_uom, charge_uom, schedule_type)
        SELECT service_id, 1, charge_type_1, CAST(cost_1 AS DOUBLE PRECISION), CAST(charge_1 AS DOUBLE PRECISION), cost_1_uom, charge_1_uom, schedule_type_1
        FROM services_current WHERE charge_type_1 IS NOT NULL AND TRIM(charge_type_1) != ''
        UNION ALL
        SELECT service_id, 2, charge_type_2, CAST(cost_2 AS DOUBLE PRECISION), CAST(charge_2 AS DOUBLE PRECISION), cost_2_uom, charge_2_uom, NULL
        FROM services_current WHERE charge_type_2 IS NOT NULL AND TRIM(charge_type_2) != ''
        UNION ALL
        SELECT service_id, 3, charge_type_3, CAST(cost_3 AS DOUBLE PRECISION), CAST(charge_3 AS DOUBLE PRECISION), cost_3_uom, charge_3_uom, NULL
        FROM services_current WHERE charge_type_3 IS NOT NULL AND TRIM(charge_type_3) != ''
        UNION ALL
        SELECT service_id, 4, charge_type_4, CAST(cost_4 AS DOUBLE PRECISION), CAST(charge_4 AS DOUBLE PRECISION), cost_4_uom, charge_4_uom, NULL
        FROM services_current WHERE charge_type_4 IS NOT NULL AND TRIM(charge_type_4) != ''
        UNION ALL
        SELECT service_id, 5, charge_type_5, CAST(cost_5 AS DOUBLE PRECISION), CAST(charge_5 AS DOUBLE PRECISION), cost_5_uom, charge_5_uom, NULL
        FROM services_current WHERE charge_type_5 IS NOT NULL AND TRIM(charge_type_5) != ''
    """)
    count = cursor.rowcount
    conn.commit()
    log.info("service_charge_tier: %d rows populated", count)
    return count


def migrate_schema_v2():
    """Apply schema v2 changes — idempotent ALTER TABLE + CREATE TABLE.

    Adds:
      - billing_charges.charge_code_id (INTEGER FK → charge_code_ref)
      - services_current.monthly_yards (DOUBLE PRECISION)
      - chain_monthly.cost_per_yard, chain_monthly.charge_per_yard (DOUBLE PRECISION)
      - service_charge_lifecycle table (new)
      - market_rate_benchmark table (new)

    Safe to run multiple times — all statements use IF NOT EXISTS / IF NOT EXISTS.
    """
    conn = get_connection()
    cursor = conn.cursor()

    alterations = [
        # Fix 1: charge_code_id on billing_charges
        ("billing_charges", "charge_code_id", "INTEGER"),
        # Fix 2: monthly_yards on services_current
        ("services_current", "monthly_yards", "DOUBLE PRECISION"),
        # Fix 2: cost_per_yard, charge_per_yard on chain_monthly
        ("chain_monthly", "cost_per_yard", "DOUBLE PRECISION"),
        ("chain_monthly", "charge_per_yard", "DOUBLE PRECISION"),
        # SKU report: profit_structure on services_current
        ("services_current", "profit_structure", "TEXT"),
        # Invoice processing: sp_created_date on ocr_document
        ("ocr_document", "sp_created_date", "DATE"),
    ]

    for table, column, dtype in alterations:
        cursor.execute(f"""
            DO $$ BEGIN
                ALTER TABLE {table} ADD COLUMN {column} {dtype};
            EXCEPTION WHEN duplicate_column THEN
                NULL;
            END $$
        """)

    # FK for billing_charges.charge_code_id
    cursor.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'billing_charges_charge_code_id_fkey') THEN
                ALTER TABLE billing_charges
                    ADD CONSTRAINT billing_charges_charge_code_id_fkey
                    FOREIGN KEY (charge_code_id) REFERENCES charge_code_ref (charge_code_id);
            END IF;
        END $$
    """)

    # Index for billing_charges.charge_code_id
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bc_charge_code_id ON billing_charges (charge_code_id)")

    # Index for chain_monthly.cost_per_yard
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cm_cost_per_yard ON chain_monthly (cost_per_yard) WHERE cost_per_yard IS NOT NULL")

    conn.commit()

    # New tables (Fix 4 + Fix 5) — handled by layer3_analytical.create_tables
    # which uses CREATE TABLE IF NOT EXISTS
    layer3_analytical.create_tables(cursor)
    conn.commit()

    # Views (CREATE OR REPLACE — always safe to re-run)
    layer3_analytical.create_views(cursor)
    conn.commit()

    log.info("Schema v2 migration complete")

    # Verify
    cursor.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
    """, (SCHEMA_NAME,))
    count = cursor.fetchone()[0]
    print(f"Schema migration complete. Tables: {count}")

    conn.close()


def init_database():
    """Initialize database with all tables in FK-safe order.

    Creates schema if needed. Circular FK (service_chain <-> services_current)
    is handled by DEFERRABLE INITIALLY DEFERRED on the FK declaration.
    """
    conn = psycopg2.connect(**PG_CONFIG)
    conn.autocommit = False
    cursor = conn.cursor()

    # Create schema if it doesn't exist (may fail on shared servers where
    # we have USAGE but not CREATE — that's fine if the schema already exists)
    try:
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}")
    except psycopg2.errors.InsufficientPrivilege:
        conn.rollback()  # clear error state
    cursor.execute(f"SET search_path TO {SCHEMA_NAME}, public")

    # Defer constraints during creation (circular FK)
    cursor.execute("SET CONSTRAINTS ALL DEFERRED")

    # Phase A: Reference tables (no FKs except market_designation -> waste_stream_ref)
    reference_tables.create_tables(cursor)

    # Phases B-E: Layer 2 operational (17 tables)
    layer2_operational.create_tables(cursor)

    # Phase F: Layer 1 raw inbound (2 tables)
    layer1_raw.create_tables(cursor)

    # Phase G: Layer 3 analytical (3 tables)
    layer3_analytical.create_tables(cursor)

    # Phase H: Views (depends on all tables)
    layer3_analytical.create_views(cursor)

    # Invoice linkage tables (depends on Layer 2 vendor/location/customer + billing_charges)
    create_linkage_tables(cursor)

    # Invoice processing pipeline (ip_ tables — no deps on other layers)
    invoice_pipeline.create_tables(cursor)
    invoice_pipeline.create_views(cursor)

    # Dashboard user management (standalone, no FKs)
    dashboard_auth.create_tables(cursor)

    conn.commit()

    # Verify table count
    cursor.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
    """, (SCHEMA_NAME,))
    count = cursor.fetchone()[0]
    conn.close()

    print(f"Database initialized (schema: {SCHEMA_NAME})")
    print(f"  Tables created: {count}")


def reset_database():
    """Drop all tables and recreate.

    Tries DROP SCHEMA CASCADE first. If the current user doesn't own the
    schema (common on shared Azure Postgres), falls back to dropping all
    tables individually with CASCADE.
    """
    conn = psycopg2.connect(**PG_CONFIG)
    conn.autocommit = True
    cursor = conn.cursor()

    try:
        cursor.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME} CASCADE")
    except psycopg2.errors.InsufficientPrivilege:
        # Don't own the schema — drop tables individually
        conn.rollback()
        cursor.execute(f"SET search_path TO {SCHEMA_NAME}, public")
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
        """, (SCHEMA_NAME,))
        tables = [r[0] for r in cursor.fetchall()]
        if tables:
            # DROP all in one statement to handle FK ordering
            cursor.execute("DROP TABLE IF EXISTS " +
                           ", ".join(tables) + " CASCADE")
            log.info("Dropped %d tables from %s", len(tables), SCHEMA_NAME)

    conn.close()
    init_database()


def get_table_names() -> list[str]:
    """Return sorted list of all user table names in the schema."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """, (SCHEMA_NAME,))
    names = [row[0] for row in cursor.fetchall()]
    conn.close()
    return names


def _collect_all_ddl() -> list[tuple[str, str, str]]:
    """Collect all DDL statements in creation order.

    Returns list of (section_name, table_name, ddl_sql) tuples.
    """
    result = []

    for name, ddl in reference_tables.TABLES.items():
        result.append(("Reference Tables", name, ddl))

    for phase_name, phase_dict in [
        ("Layer 2 — Core Entities", layer2_operational.PHASE_B),
        ("Layer 2 — Chain + Services", layer2_operational.PHASE_C),
        ("Layer 2 — Transactional", layer2_operational.PHASE_D),
        ("Layer 2 — Mapping", layer2_operational.PHASE_E),
    ]:
        for name, ddl in phase_dict.items():
            result.append((phase_name, name, ddl))

    for name, ddl in layer1_raw.TABLES.items():
        result.append(("Layer 1 — Raw Inbound", name, ddl))

    for name, ddl in layer3_analytical.TABLES.items():
        result.append(("Layer 3 — Analytical", name, ddl))

    for name, ddl in LINKAGE_TABLES.items():
        result.append(("Invoice Linkage", name, ddl))

    for name, ddl in invoice_pipeline.TABLES.items():
        result.append(("Invoice Processing Pipeline", name, ddl))

    return result


def _collect_all_indexes() -> list[tuple[str, str]]:
    """Collect all index statements in creation order.

    Returns list of (section_name, index_sql) tuples.
    """
    result = []

    for idx in reference_tables.INDEXES:
        result.append(("Reference Tables", idx))

    for phase_name, indexes in [
        ("Layer 2 — Core Entities", layer2_operational.PHASE_B_INDEXES),
        ("Layer 2 — Chain + Services", layer2_operational.PHASE_C_INDEXES),
        ("Layer 2 — Transactional", layer2_operational.PHASE_D_INDEXES),
        ("Layer 2 — Mapping", layer2_operational.PHASE_E_INDEXES),
    ]:
        for idx in indexes:
            result.append((phase_name, idx))

    for idx in layer1_raw.INDEXES:
        result.append(("Layer 1 — Raw Inbound", idx))

    for idx in layer3_analytical.INDEXES:
        result.append(("Layer 3 — Analytical", idx))

    for idx in LINKAGE_INDEXES:
        result.append(("Invoice Linkage", idx))

    for idx in invoice_pipeline.INDEXES:
        result.append(("Invoice Processing Pipeline", idx))

    return result


def export_ddl(output_path=None):
    """Export standalone SQL DDL script."""
    import textwrap
    from pathlib import Path

    path = output_path or Path(__file__).parent.parent / "schema" / "ops_database.sql"
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("-- =============================================================================")
    lines.append("-- Wasteology Operations Database — Standalone DDL (PostgreSQL)")
    lines.append(f"-- Schema: {SCHEMA_NAME}")
    lines.append("-- Tables across 3 layers + reference tables")
    lines.append("--")
    lines.append(f"-- Usage: psql -d wasteology_dev -f ops_database.sql")
    lines.append("-- =============================================================================")
    lines.append("")
    lines.append(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME};")
    lines.append(f"SET search_path TO {SCHEMA_NAME}, public;")
    lines.append("")
    lines.append("SET CONSTRAINTS ALL DEFERRED;")
    lines.append("")

    # Tables grouped by section
    current_section = None
    for section, name, ddl in _collect_all_ddl():
        if section != current_section:
            current_section = section
            lines.append(f"-- ---------------------------------------------------------------------------")
            lines.append(f"-- {section}")
            lines.append(f"-- ---------------------------------------------------------------------------")
            lines.append("")
        cleaned = textwrap.dedent(ddl).strip()
        lines.append(f"{cleaned};")
        lines.append("")

    # Indexes grouped by section
    lines.append("-- ---------------------------------------------------------------------------")
    lines.append("-- Indexes")
    lines.append("-- ---------------------------------------------------------------------------")
    lines.append("")
    for _, idx_sql in _collect_all_indexes():
        lines.append(f"{idx_sql};")
    lines.append("")

    # Views
    all_views = list(layer3_analytical.VIEWS.items()) + list(invoice_pipeline.VIEWS.items())
    if all_views:
        lines.append("-- ---------------------------------------------------------------------------")
        lines.append("-- Views")
        lines.append("-- ---------------------------------------------------------------------------")
        lines.append("")
        for name, view_sql in all_views:
            cleaned = textwrap.dedent(view_sql).strip()
            lines.append(f"{cleaned};")
            lines.append("")

    path.write_text("\n".join(lines))
    print(f"DDL exported to {path}")
    return path
