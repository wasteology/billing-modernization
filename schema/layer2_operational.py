"""
Layer 2 — Conformed / Operational tables.

17 tables across 5 phases (B–E):
  B  Core entities:  customer, location, vendor
  C  Chain+services: service_chain, container, services_current,
                     service_charge_tier, service_chain_membership,
                     services_history
  D  Transactional:  billing_charges, vendor_contract_terms, customer_contract_terms,
                     price_increase_events, ap_report, account_number_resolution
  E  Mapping:        waste_stream_mapping, charge_code_mapping, vendor_name_mapping
"""

# =========================================================================
# Phase B — Core entity tables (no circular FKs)
# =========================================================================
PHASE_B = {
    "customer": """
        CREATE TABLE IF NOT EXISTS customer (
            customer_id    SERIAL PRIMARY KEY,
            account_name   TEXT,
            erp_account_id TEXT,
            is_active      BOOLEAN,
            created_date   DATE,
            notes          TEXT
        )
    """,

    "location": """
        CREATE TABLE IF NOT EXISTS location (
            location_id    SERIAL PRIMARY KEY,
            customer_id    INTEGER,
            location_name  TEXT,
            site_reference TEXT,
            address        TEXT,
            city           TEXT,
            region         TEXT,
            postal_code    TEXT,
            is_active      BOOLEAN,
            created_date   DATE,

            FOREIGN KEY (customer_id) REFERENCES customer (customer_id)
        )
    """,

    "vendor": """
        CREATE TABLE IF NOT EXISTS vendor (
            vendor_id            SERIAL PRIMARY KEY,
            vendor_name          TEXT,
            hauler_account_number TEXT UNIQUE,
            is_active            BOOLEAN,
            created_date         DATE
        )
    """,
}

PHASE_B_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_cust_account_name   ON customer (account_name)",
    "CREATE INDEX IF NOT EXISTS idx_cust_erp_account_id ON customer (erp_account_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_cust_account_name_uniq ON customer (account_name) WHERE account_name IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_loc_location_name   ON location (location_name)",
    "CREATE INDEX IF NOT EXISTS idx_loc_site_reference  ON location (site_reference)",
    "CREATE INDEX IF NOT EXISTS idx_loc_postal_code     ON location (postal_code)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_loc_natural_key ON location (customer_id, location_name) WHERE location_name IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_vnd_vendor_name     ON vendor (vendor_name)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_vnd_vendor_name_uniq ON vendor (vendor_name) WHERE vendor_name IS NOT NULL",
]

# =========================================================================
# Phase C — Chain + Services (circular FK between service_chain ↔ services_current)
# =========================================================================
PHASE_C = {
    # service_chain created BEFORE services_current so services_current can FK to it.
    # The circular FK (current_service_id -> services_current) is added via ALTER TABLE
    # in PHASE_C_POST_ALTER after both tables exist.
    "service_chain": """
        CREATE TABLE IF NOT EXISTS service_chain (
            chain_id           SERIAL PRIMARY KEY,
            location_id        INTEGER,
            customer_id        INTEGER NOT NULL,
            waste_stream_id    INTEGER,
            chain_start_date   DATE,
            chain_end_date     DATE,
            is_active          BOOLEAN,
            current_service_id TEXT,
            vendor_contract_id INTEGER,
            created_date       DATE,

            FOREIGN KEY (location_id)        REFERENCES location (location_id),
            FOREIGN KEY (customer_id)        REFERENCES customer (customer_id),
            FOREIGN KEY (waste_stream_id)    REFERENCES waste_stream_ref (waste_stream_id)
        )
    """,

    "container": """
        CREATE TABLE IF NOT EXISTS container (
            container_id          SERIAL PRIMARY KEY,
            location_id           INTEGER NOT NULL,
            waste_stream_id       INTEGER,
            equipment_type        TEXT,
            container_size_yards  DOUBLE PRECISION,
            is_active             BOOLEAN,
            created_date          DATE,

            FOREIGN KEY (location_id)    REFERENCES location (location_id),
            FOREIGN KEY (waste_stream_id) REFERENCES waste_stream_ref (waste_stream_id)
        )
    """,

    "services_current": """
        CREATE TABLE IF NOT EXISTS services_current (
            service_id           TEXT PRIMARY KEY,
            customer_id          INTEGER,
            location_id          INTEGER,
            vendor_id            INTEGER,
            chain_id             INTEGER,
            container_id         INTEGER,
            vendor_contract_id   INTEGER,
            waste_stream_id      INTEGER,
            container_size_yards DOUBLE PRECISION,
            container_type_code  TEXT,
            container_ownership  TEXT,
            equipment_number_raw TEXT,
            equipment_type       TEXT,
            schedule             TEXT,
            times_a_week         DOUBLE PRECISION,
            pickups_per_month    DOUBLE PRECISION,
            is_on_call           BOOLEAN,
            number_of_pickups    INTEGER,

            -- 5-tier charge structure: type / cost / charge / cost_uom / charge_uom / schedule_type
            -- Kept as raw import format from Azure. Normalized view: service_charge_tier.
            charge_type_1   TEXT,
            cost_1          DOUBLE PRECISION,
            charge_1        DOUBLE PRECISION,
            cost_1_uom      TEXT,
            charge_1_uom    TEXT,
            schedule_type_1 TEXT,

            charge_type_2   TEXT,
            cost_2          DOUBLE PRECISION,
            charge_2        DOUBLE PRECISION,
            cost_2_uom      TEXT,
            charge_2_uom    TEXT,

            charge_type_3   TEXT,
            cost_3          DOUBLE PRECISION,
            charge_3        DOUBLE PRECISION,
            cost_3_uom      TEXT,
            charge_3_uom    TEXT,

            charge_type_4   TEXT,
            cost_4          DOUBLE PRECISION,
            charge_4        DOUBLE PRECISION,
            cost_4_uom      TEXT,
            charge_4_uom    TEXT,

            charge_type_5   TEXT,
            cost_5          DOUBLE PRECISION,
            charge_5        DOUBLE PRECISION,
            cost_5_uom      TEXT,
            charge_5_uom    TEXT,

            start_date          DATE,
            end_date            DATE,
            is_active           BOOLEAN,
            target_weight       DOUBLE PRECISION,
            department          TEXT,
            description         TEXT,
            technology          TEXT,
            material_recovered  TEXT,
            export_datetime     TIMESTAMP,
            monthly_yards       DOUBLE PRECISION,
            profit_structure    TEXT,

            FOREIGN KEY (customer_id)    REFERENCES customer (customer_id),
            FOREIGN KEY (location_id)    REFERENCES location (location_id),
            FOREIGN KEY (vendor_id)      REFERENCES vendor (vendor_id),
            FOREIGN KEY (chain_id)       REFERENCES service_chain (chain_id),
            FOREIGN KEY (container_id)       REFERENCES container (container_id),
            FOREIGN KEY (waste_stream_id)    REFERENCES waste_stream_ref (waste_stream_id)
        )
    """,

    "service_charge_tier": """
        CREATE TABLE IF NOT EXISTS service_charge_tier (
            service_id    TEXT    NOT NULL,
            tier          INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 10),
            charge_type   TEXT    NOT NULL,
            cost          DOUBLE PRECISION,
            charge        DOUBLE PRECISION,
            cost_uom      TEXT,
            charge_uom    TEXT,
            schedule_type TEXT,

            PRIMARY KEY (service_id, tier),
            FOREIGN KEY (service_id) REFERENCES services_current (service_id)
        )
    """,

    "service_chain_membership": """
        CREATE TABLE IF NOT EXISTS service_chain_membership (
            membership_id     SERIAL PRIMARY KEY,
            chain_id          INTEGER NOT NULL,
            service_id        TEXT    NOT NULL,
            sequence_number   INTEGER,
            activation_date   DATE,
            deactivation_date DATE,
            transition_type   TEXT,
            match_confidence  TEXT,
            match_method      TEXT,

            UNIQUE (chain_id, service_id),
            FOREIGN KEY (chain_id)   REFERENCES service_chain (chain_id),
            FOREIGN KEY (service_id) REFERENCES services_current (service_id)
        )
    """,

    "services_history": """
        CREATE TABLE IF NOT EXISTS services_history (
            snapshot_id          SERIAL PRIMARY KEY,
            service_id           TEXT    NOT NULL,
            snapshot_date        DATE    NOT NULL,

            -- Mirror of services_current columns
            customer_id          INTEGER,
            location_id          INTEGER,
            vendor_id            INTEGER,
            chain_id             INTEGER,
            waste_stream_id      INTEGER,
            container_size_yards DOUBLE PRECISION,
            container_type_code  TEXT,
            container_ownership  TEXT,
            equipment_number_raw TEXT,
            equipment_type       TEXT,
            schedule             TEXT,
            times_a_week         DOUBLE PRECISION,
            pickups_per_month    DOUBLE PRECISION,
            is_on_call           BOOLEAN,
            number_of_pickups    INTEGER,

            charge_type_1   TEXT,
            cost_1          DOUBLE PRECISION,
            charge_1        DOUBLE PRECISION,
            cost_1_uom      TEXT,
            charge_1_uom    TEXT,
            schedule_type_1 TEXT,

            charge_type_2   TEXT,
            cost_2          DOUBLE PRECISION,
            charge_2        DOUBLE PRECISION,
            cost_2_uom      TEXT,
            charge_2_uom    TEXT,

            charge_type_3   TEXT,
            cost_3          DOUBLE PRECISION,
            charge_3        DOUBLE PRECISION,
            cost_3_uom      TEXT,
            charge_3_uom    TEXT,

            charge_type_4   TEXT,
            cost_4          DOUBLE PRECISION,
            charge_4        DOUBLE PRECISION,
            cost_4_uom      TEXT,
            charge_4_uom    TEXT,

            charge_type_5   TEXT,
            cost_5          DOUBLE PRECISION,
            charge_5        DOUBLE PRECISION,
            cost_5_uom      TEXT,
            charge_5_uom    TEXT,

            start_date          DATE,
            end_date            DATE,
            is_active           BOOLEAN,
            target_weight       DOUBLE PRECISION,
            department          TEXT,
            description         TEXT,
            technology          TEXT,
            material_recovered  TEXT,
            export_datetime     TIMESTAMP,

            -- Snapshot-specific fields
            change_detected BOOLEAN,
            changed_fields  TEXT
        )
    """,
}

# FKs that reference tables created in later phases (cross-phase dependencies).
# Added via ALTER TABLE after ALL tables exist. Idempotent (skips if already present).
DEFERRED_FKS = [
    # Circular: service_chain -> services_current
    """DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'service_chain_current_service_id_fkey') THEN
            ALTER TABLE service_chain
                ADD CONSTRAINT service_chain_current_service_id_fkey
                FOREIGN KEY (current_service_id) REFERENCES services_current (service_id)
                DEFERRABLE INITIALLY DEFERRED;
        END IF;
    END $$""",
    # Phase C -> Phase D: service_chain -> vendor_contract_terms
    """DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'service_chain_vendor_contract_id_fkey') THEN
            ALTER TABLE service_chain
                ADD CONSTRAINT service_chain_vendor_contract_id_fkey
                FOREIGN KEY (vendor_contract_id) REFERENCES vendor_contract_terms (vendor_contract_id);
        END IF;
    END $$""",
    # Phase C -> Phase D: services_current -> vendor_contract_terms
    """DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'services_current_vendor_contract_id_fkey') THEN
            ALTER TABLE services_current
                ADD CONSTRAINT services_current_vendor_contract_id_fkey
                FOREIGN KEY (vendor_contract_id) REFERENCES vendor_contract_terms (vendor_contract_id);
        END IF;
    END $$""",
]

PHASE_C_INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_container_natural_key ON container (location_id, waste_stream_id, equipment_type, container_size_yards)",
    "CREATE INDEX IF NOT EXISTS idx_sc_container_id  ON services_current (container_id)",
    "CREATE INDEX IF NOT EXISTS idx_sc_is_active     ON services_current (is_active)",
    "CREATE INDEX IF NOT EXISTS idx_sc_loc_ws        ON services_current (location_id, waste_stream_id)",
    "CREATE INDEX IF NOT EXISTS idx_sct_charge_type  ON service_charge_tier (charge_type)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sh_svc_snapshot ON services_history (service_id, snapshot_date)",
    "CREATE INDEX IF NOT EXISTS idx_chain_is_active  ON service_chain (is_active)",
]

# =========================================================================
# Phase D — Transactional tables
# =========================================================================
PHASE_D = {
    "billing_charges": """
        CREATE TABLE IF NOT EXISTS billing_charges (
            billing_charge_id      SERIAL PRIMARY KEY,
            service_id             TEXT    NOT NULL,
            chain_id               INTEGER,
            invoice_id             TEXT,
            group_invoice_id       TEXT,
            billing_reference      TEXT,
            invoice_date           DATE,
            transaction_date       DATE,
            transaction_month      INTEGER,
            transaction_year       INTEGER,
            account_name           TEXT,
            location_name          TEXT,
            vendor_name            TEXT,
            charge_description     TEXT,
            service_type           TEXT,
            equipment_type         TEXT,
            equipment_number       TEXT,
            material               TEXT,
            price                  DOUBLE PRECISION,
            cost                   DOUBLE PRECISION,
            charge                 DOUBLE PRECISION,
            sales                  DOUBLE PRECISION,
            margin                 DOUBLE PRECISION,
            weight                 DOUBLE PRECISION,
            unit_of_measure        TEXT,
            billing_mode           TEXT,
            status                 TEXT,
            department             TEXT,
            trade_type             TEXT,
            job_no                 TEXT,
            address                TEXT,
            city                   TEXT,
            region                 TEXT,
            postal_code            TEXT,
            site                   TEXT,
            site_reference         TEXT,
            reference              TEXT,
            item_id                TEXT,
            customer_reference     TEXT,
            invoice_type           TEXT,
            include_fuel_surcharge BOOLEAN,
            username               TEXT,
            email_sent             BOOLEAN,
            user_defined_field_1   TEXT,
            market_type_location   TEXT,
            material_recovered     TEXT,
            export_datetime        TIMESTAMP,
            charge_code_id         INTEGER,

            FOREIGN KEY (service_id) REFERENCES services_current (service_id),
            FOREIGN KEY (chain_id)   REFERENCES service_chain (chain_id),
            FOREIGN KEY (charge_code_id) REFERENCES charge_code_ref (charge_code_id)
        )
    """,

    "vendor_contract_terms": """
        CREATE TABLE IF NOT EXISTS vendor_contract_terms (
            vendor_contract_id        SERIAL PRIMARY KEY,
            vendor_id                 INTEGER,
            contract_effective_date   DATE,
            contract_expiration_date  DATE,
            pi_cap_percent            DOUBLE PRECISION,
            pi_trigger_date           DATE,
            pi_schedule               TEXT,
            pi_notice_days            INTEGER,
            disposal_passthrough_required BOOLEAN,
            fuel_passthrough_required    BOOLEAN,
            other_passthrough_terms   TEXT,
            auto_renewal              BOOLEAN,
            renewal_terms             TEXT,
            source_document           TEXT,
            extracted_date            DATE,
            notes                     TEXT,

            FOREIGN KEY (vendor_id) REFERENCES vendor (vendor_id)
        )
    """,

    "customer_contract_terms": """
        CREATE TABLE IF NOT EXISTS customer_contract_terms (
            customer_contract_id    SERIAL PRIMARY KEY,
            customer_id             INTEGER,
            chain_id                INTEGER,
            contract_effective_date DATE,
            contract_roll_date      DATE,
            pi_percent_agreed       DOUBLE PRECISION,
            pi_frequency            TEXT,
            next_pi_eligible_date   DATE,
            last_pi_executed_date   DATE,
            last_pi_percent_applied DOUBLE PRECISION,
            auto_renewal            BOOLEAN,
            source_document         TEXT,
            extracted_date          DATE,
            notes                   TEXT,

            FOREIGN KEY (customer_id) REFERENCES customer (customer_id),
            FOREIGN KEY (chain_id)    REFERENCES service_chain (chain_id)
        )
    """,

    "price_increase_events": """
        CREATE TABLE IF NOT EXISTS price_increase_events (
            pi_event_id          SERIAL PRIMARY KEY,
            chain_id             INTEGER,
            service_id           TEXT,
            side                 TEXT CHECK (side IN ('cost', 'charge')),
            event_date           DATE,
            charge_category      TEXT,
            previous_rate        DOUBLE PRECISION,
            new_rate             DOUBLE PRECISION,
            rate_uom             TEXT,
            pct_change           DOUBLE PRECISION,
            dollar_impact_monthly DOUBLE PRECISION,
            detection_source     TEXT,
            linked_contract_id   INTEGER,
            notes                TEXT,

            FOREIGN KEY (chain_id)   REFERENCES service_chain (chain_id),
            FOREIGN KEY (service_id) REFERENCES services_current (service_id)
        )
    """,

    "ap_report": """
        CREATE TABLE IF NOT EXISTS ap_report (
            ap_record_id         SERIAL PRIMARY KEY,
            vendor_name          TEXT,
            hauler_account_number TEXT,
            invoice_date         DATE,
            invoice_total        DOUBLE PRECISION,
            payment_date         DATE,
            payment_amount       DOUBLE PRECISION,
            check_number         TEXT,
            import_datetime      TIMESTAMP
        )
    """,

    "account_number_resolution": """
        CREATE TABLE IF NOT EXISTS account_number_resolution (
            resolution_id        SERIAL PRIMARY KEY,
            vendor_id            INTEGER,
            hauler_account_number TEXT,
            customer_id          INTEGER,
            location_id          INTEGER,
            chain_id             INTEGER,
            service_id           TEXT,
            match_confidence     TEXT CHECK (match_confidence IN ('high', 'medium', 'low', 'manual')),
            match_method         TEXT,
            first_verified_date  DATE,
            last_verified_date   DATE,
            verification_count   INTEGER,
            is_active            BOOLEAN,

            UNIQUE (vendor_id, hauler_account_number, location_id, service_id),
            FOREIGN KEY (vendor_id)   REFERENCES vendor (vendor_id),
            FOREIGN KEY (customer_id) REFERENCES customer (customer_id),
            FOREIGN KEY (location_id) REFERENCES location (location_id),
            FOREIGN KEY (chain_id)    REFERENCES service_chain (chain_id),
            FOREIGN KEY (service_id)  REFERENCES services_current (service_id)
        )
    """,
}

PHASE_D_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_bc_service_id         ON billing_charges (service_id)",
    "CREATE INDEX IF NOT EXISTS idx_bc_chain_id           ON billing_charges (chain_id)",
    "CREATE INDEX IF NOT EXISTS idx_bc_invoice_id         ON billing_charges (invoice_id)",
    "CREATE INDEX IF NOT EXISTS idx_bc_billing_reference  ON billing_charges (billing_reference)",
    "CREATE INDEX IF NOT EXISTS idx_bc_invoice_date       ON billing_charges (invoice_date)",
    "CREATE INDEX IF NOT EXISTS idx_bc_txn_period         ON billing_charges (transaction_month, transaction_year)",
    "CREATE INDEX IF NOT EXISTS idx_bc_account_name       ON billing_charges (account_name)",
    "CREATE INDEX IF NOT EXISTS idx_bc_vendor_name        ON billing_charges (vendor_name)",
    "CREATE INDEX IF NOT EXISTS idx_bc_charge_description ON billing_charges (charge_description)",
    "CREATE INDEX IF NOT EXISTS idx_bc_material           ON billing_charges (material)",
    "CREATE INDEX IF NOT EXISTS idx_bc_svc_period         ON billing_charges (service_id, transaction_year, transaction_month, service_type)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_bc_item_id_uniq ON billing_charges (item_id) WHERE item_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_bc_charge_code_id     ON billing_charges (charge_code_id)",
    "CREATE INDEX IF NOT EXISTS idx_cct_roll_date         ON customer_contract_terms (contract_roll_date)",
    "CREATE INDEX IF NOT EXISTS idx_cct_next_pi           ON customer_contract_terms (next_pi_eligible_date)",
    "CREATE INDEX IF NOT EXISTS idx_pie_chain_side_date   ON price_increase_events (chain_id, side, event_date)",
    "CREATE INDEX IF NOT EXISTS idx_pie_chain_cat_date    ON price_increase_events (chain_id, charge_category, event_date)",
    "CREATE INDEX IF NOT EXISTS idx_ap_vendor_name        ON ap_report (vendor_name)",
    "CREATE INDEX IF NOT EXISTS idx_ap_hauler_account     ON ap_report (hauler_account_number)",
    "CREATE INDEX IF NOT EXISTS idx_ap_invoice_date       ON ap_report (invoice_date)",
    "CREATE INDEX IF NOT EXISTS idx_ap_invoice_total      ON ap_report (invoice_total)",
    "CREATE INDEX IF NOT EXISTS idx_anr_hauler_account    ON account_number_resolution (hauler_account_number)",
]

# =========================================================================
# Phase E — Mapping tables
# =========================================================================
PHASE_E = {
    "waste_stream_mapping": """
        CREATE TABLE IF NOT EXISTS waste_stream_mapping (
            mapping_id      SERIAL PRIMARY KEY,
            vendor_id       INTEGER,
            raw_description TEXT,
            waste_stream_id INTEGER,
            match_type      TEXT CHECK (match_type IN ('exact', 'regex', 'fuzzy')),
            created_date    DATE,

            FOREIGN KEY (vendor_id)       REFERENCES vendor (vendor_id),
            FOREIGN KEY (waste_stream_id) REFERENCES waste_stream_ref (waste_stream_id)
        )
    """,

    "charge_code_mapping": """
        CREATE TABLE IF NOT EXISTS charge_code_mapping (
            mapping_id      SERIAL PRIMARY KEY,
            vendor_id       INTEGER,
            raw_description TEXT,
            charge_code_id  INTEGER,
            match_type      TEXT CHECK (match_type IN ('exact', 'case_insensitive', 'regex', 'fuzzy', 'typo_correction')),
            created_date    DATE,

            FOREIGN KEY (vendor_id)      REFERENCES vendor (vendor_id),
            FOREIGN KEY (charge_code_id) REFERENCES charge_code_ref (charge_code_id)
        )
    """,

    "vendor_name_mapping": """
        CREATE TABLE IF NOT EXISTS vendor_name_mapping (
            mapping_id      SERIAL PRIMARY KEY,
            raw_vendor_name TEXT,
            vendor_id       INTEGER,
            source          TEXT,
            created_date    DATE,

            FOREIGN KEY (vendor_id) REFERENCES vendor (vendor_id)
        )
    """,
}

PHASE_E_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_wsm_raw_description ON waste_stream_mapping (raw_description)",
    "CREATE INDEX IF NOT EXISTS idx_ccm_raw_description ON charge_code_mapping (raw_description)",
    "CREATE INDEX IF NOT EXISTS idx_vnm_raw_vendor_name ON vendor_name_mapping (raw_vendor_name)",
]


def create_tables(cursor):
    """Create all Layer 2 tables and indexes in FK-safe order."""
    for phase_tables, phase_indexes in [
        (PHASE_B, PHASE_B_INDEXES),
        (PHASE_C, PHASE_C_INDEXES),
        (PHASE_D, PHASE_D_INDEXES),
        (PHASE_E, PHASE_E_INDEXES),
    ]:
        for ddl in phase_tables.values():
            cursor.execute(ddl)
        for idx in phase_indexes:
            cursor.execute(idx)

    # Add cross-phase FKs now that all tables exist
    for fk_sql in DEFERRED_FKS:
        cursor.execute(fk_sql)
