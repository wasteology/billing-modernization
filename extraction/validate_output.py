#!/usr/bin/env python3
"""
validate_output.py — Cross-invoice semantic validation checks.

Reads all vendor_extracts CSVs and runs checks that go beyond the
per-invoice charge_sum == bill_total check already done by executor.py.

Usage:
    python validate_output.py
    python validate_output.py --extracts output/vendor_extracts --out output/validation_report.csv
"""

import argparse
import glob
import os
import sys

import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EXTRACTS_DIR = "output/vendor_extracts"
REPORT_PATH = "output/validation_report.csv"
SUPPRESSIONS_PATH = "output/validation_suppressions.csv"

# Equipment buckets
ONCALL_EQUIP = {"roll_off", "compactor", "open_top"}
RECURRING_EQUIP = {"front_load", "rear_load", "cart", "toter"}

# Charge codes that should NOT appear on on-call containers
MONTHLY_SERVICE_CODES = {"monthly_service_commercial", "monthly_service_residential"}

# Charge codes that are clearly on-call (haul/disposal) — unusual on recurring containers
ONCALL_CODES = {"haul", "disposal", "pull", "delivery"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def scol(df, col):
    """Return lowercase stripped string series; empty string for nulls."""
    if col not in df.columns:
        return pd.Series([""] * len(df), index=df.index)
    return df[col].fillna("").str.strip().str.lower()


def load_extracts(extracts_dir):
    paths = [p for p in glob.glob(os.path.join(extracts_dir, "*.csv"))
             if "baseline" not in os.path.basename(p)]
    if not paths:
        sys.exit(f"No vendor extract CSVs found in {extracts_dir}")

    frames = []
    for path in paths:
        try:
            df = pd.read_csv(path, dtype=str, low_memory=False)
            df["_source_file"] = os.path.basename(path)
            frames.append(df)
        except Exception as e:
            print(f"  Warning: could not read {path}: {e}")

    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Check runners
# ---------------------------------------------------------------------------

def check_invoice_number_uniqueness(df):
    """DUPLICATE_INVOICE_NUMBER — same invoice# on multiple PDFs."""
    findings = []
    if "invoice_number" not in df.columns:
        return findings

    inv_col = scol(df, "invoice_number")
    pdf_col = scol(df, "pdf_filename")

    tmp = df[inv_col.ne("") & pdf_col.ne("")].copy()
    tmp["_inv"] = inv_col
    tmp["_pdf"] = pdf_col

    counts = tmp.groupby("_inv")["_pdf"].nunique()
    dupes = counts[counts > 1].index

    for inv in dupes:
        rows = tmp[tmp["_inv"] == inv].drop_duplicates("_pdf")
        pdfs = rows["_pdf"].tolist()
        for _, r in rows.iterrows():
            findings.append(_finding(r, "DUPLICATE_INVOICE_NUMBER", "WARNING",
                                     f"Invoice# '{inv}' found on {len(pdfs)} PDFs: {pdfs}"))
    return findings


def check_account_number_stability(df):
    """ACCOUNT_UNSTABLE — same site + same vendor, different account numbers across months.

    Groups by (site_code, source_file) so that a site served by two different vendors
    (each with their own account) is not flagged.
    """
    findings = []
    if "account_number" not in df.columns or "pdf_filename" not in df.columns:
        return findings

    site = df["pdf_filename"].str.extract(r'^([A-Z]{2,6}\d{1,4})', expand=False)
    acct = scol(df, "account_number")

    tmp = df[site.notna() & acct.ne("")].copy()
    tmp["_site"] = site
    tmp["_acct"] = acct
    tmp["_vendor"] = tmp.get("_source_file", pd.Series([""] * len(tmp), index=tmp.index))

    # One row per (pdf_filename × account_number) to avoid charge-row inflation
    tmp2 = tmp[["_site", "_vendor", "_acct", "pdf_filename", "pdf_link", "invoice_number",
                "_source_file"]].drop_duplicates(["pdf_filename", "_acct"])

    for (site_code, vendor), grp in tmp2.groupby(["_site", "_vendor"]):
        accts = grp["_acct"].unique()
        if len(accts) <= 1:
            continue
        for _, r in grp.drop_duplicates("pdf_filename").iterrows():
            findings.append(_finding(r, "ACCOUNT_UNSTABLE", "WARNING",
                                     f"Site {site_code} ({vendor}) has {len(accts)} distinct "
                                     f"account numbers: {sorted(accts)}"))
    return findings


def check_per_row(df):
    """Per-charge-row checks: missing fields, equip/code compatibility."""
    findings = []

    equip = scol(df, "equipment_type")
    code = scol(df, "charge_code")
    sched = scol(df, "schedule")
    weight = scol(df, "weight")
    material = scol(df, "material")
    charge_total = scol(df, "charge_total")

    for idx in df.index:
        r = df.loc[idx]

        # Skip rows with no charge_total (header / summary rows from multi-row CSVs)
        if not charge_total[idx]:
            continue

        eq = equip[idx]
        cd = code[idx]
        sc = sched[idx]
        wt = weight[idx]
        mat = material[idx]

        _desc_lower = str(r.get("description", "") or "").lower()
        _code_lower = cd  # already lowercased

        # --- Missing equipment type ---
        # Exempt clearly non-service charge lines (finance, late fee, delivery, inactivity)
        _is_non_service_row = any(kw in _desc_lower for kw in [
            "finance charge", "late fee", "inactivity fee", "activity charge",
            "delivery charge", "extra pickup", "service attempt"
        ])
        if not eq:
            if not _is_non_service_row:
                findings.append(_finding(r, "MISSING_EQUIPMENT_TYPE", "ERROR",
                                         "charge row has no equipment_type"))
            continue  # most other checks need equip — skip rest for this row

        # --- Missing material ---
        # Skip charge types where material doesn't apply (fees, inactivity, rentals, surcharges)
        _is_fee_charge = (
            "inactivity" in _code_lower or
            ("late" in _desc_lower and "fee" in _desc_lower) or
            "demurrage" in _desc_lower or
            "sweeper" in _desc_lower or
            "surcharge" in _code_lower or
            "rental" in _code_lower or    # container rental — material not required
            "rental" in _desc_lower       # description says rental (e.g. TIPPING BINRENTAL)
        )
        if not mat and not _is_fee_charge:
            # For on-call containers, only flag material missing on disposal lines specifically.
            # Haul charges (Empty & Return, Trip Charge, Delivery, Relocate) don't carry
            # a material type — material is on the disposal line.
            if eq in ONCALL_EQUIP:
                _is_disposal_line = "disposal" in _code_lower or "disposal" in _desc_lower
                if _is_disposal_line:
                    findings.append(_finding(r, "MISSING_MATERIAL", "WARNING",
                                             f"charge row ({eq}) disposal has no material"))
            else:
                findings.append(_finding(r, "MISSING_MATERIAL", "WARNING",
                                         f"charge row ({eq}) has no material"))

        # --- Front load / recurring: must have schedule ---
        # Skip fee/surcharge charges — they inherit equipment_type from parent but don't carry service schedule
        if eq in RECURRING_EQUIP and not sc and not _is_fee_charge:
            _cd_lower = cd
            _is_ancillary = (
                "surcharge" in _cd_lower or "fee" in _cd_lower or
                "offset" in _cd_lower or "tax" in _cd_lower or
                "lock" in _cd_lower or "late" in _cd_lower or
                "administrative" in _cd_lower or "franchise" in _cd_lower or
                "contamination" in _cd_lower or "rental" in _cd_lower or
                "overage" in _cd_lower or
                "relocation" in _desc_lower or "delivery" in _desc_lower or
                "late fee" in _desc_lower or "late charge" in _desc_lower or
                "rental" in _desc_lower
            )
            if not _is_ancillary:
                findings.append(_finding(r, "RECURRING_NO_SCHEDULE", "WARNING",
                                         f"{eq} charge has no schedule"))

        # --- Roll-off / compactor: disposal line should have weight ---
        # Only flag the disposal charge specifically — haul, rent, fuel surcharge etc. don't carry weight
        if eq in ONCALL_EQUIP and "disposal" in cd and not wt:
            findings.append(_finding(r, "ROLLOFF_NO_WEIGHT", "INFO",
                                     f"{eq} disposal charge has no weight recorded"))

        # --- Charge code compatibility ---
        if cd:
            # Monthly service on a roll-off container
            if eq in ONCALL_EQUIP and cd in MONTHLY_SERVICE_CODES:
                findings.append(_finding(r, "EQUIP_CODE_MISMATCH", "WARNING",
                                         f"{eq} with charge_code '{cd}' — "
                                         f"monthly service on on-call container is unusual"))

            # Haul/disposal on a recurring (front load) container
            if eq in RECURRING_EQUIP and cd in ONCALL_CODES:
                findings.append(_finding(r, "EQUIP_CODE_MISMATCH", "WARNING",
                                         f"{eq} with charge_code '{cd}' — "
                                         f"haul/disposal code on recurring container is unusual"))

    return findings


# ---------------------------------------------------------------------------
# Finding builder
# ---------------------------------------------------------------------------

def _finding(row, check, severity, detail):
    if isinstance(row, pd.Series):
        g = lambda col: row.get(col, "") if isinstance(row, pd.Series) else row.get(col, "")
    else:
        g = lambda col: row.get(col, "")

    return {
        "check": check,
        "severity": severity,
        "detail": detail,
        "pdf_filename": g("pdf_filename"),
        "pdf_link": g("pdf_link"),
        "invoice_number": g("invoice_number"),
        "account_number": g("account_number"),
        "equipment_type": g("equipment_type"),
        "equipment_size": g("equipment_size"),
        "material": g("material"),
        "schedule": g("schedule"),
        "charge_code": g("charge_code"),
        "charge_total": g("charge_total"),
        "weight": g("weight"),
        "description": g("description"),
        "service_date": g("service_date"),
        "_source_file": g("_source_file"),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CHECK_DESCRIPTIONS = {
    "DUPLICATE_INVOICE_NUMBER": "Same invoice# found on multiple PDFs",
    "ACCOUNT_UNSTABLE":         "Site has different account numbers across invoices",
    "MISSING_EQUIPMENT_TYPE":   "Charge row has no equipment_type",
    "MISSING_MATERIAL":         "Charge row has no material",
    "RECURRING_NO_SCHEDULE":    "Front load / cart charge has no schedule",
    "ROLLOFF_NO_WEIGHT":        "Roll-off / compactor charge has no weight",
    "EQUIP_CODE_MISMATCH":      "Charge code is inconsistent with equipment type",
}


def load_suppressions(path):
    """Load suppression rules. Returns list of dicts with check/scope/value keys."""
    if not os.path.exists(path):
        return []
    df = pd.read_csv(path, dtype=str).fillna("")
    return df.to_dict("records")


def is_suppressed(finding, rules):
    """Return True if any suppression rule matches this finding."""
    for rule in rules:
        if rule["check"] not in ("*", finding["check"]):
            continue
        scope = rule.get("scope", "all").strip()
        value = rule.get("value", "").strip().lower()
        if scope == "all":
            return True
        elif scope == "source_file":
            if finding.get("_source_file", "").lower() == value:
                return True
        elif scope == "pdf_filename":
            if finding.get("pdf_filename", "").lower() == value:
                return True
        elif scope == "site_code":
            import re
            m = re.match(r'^([a-z]{2,6}\d{1,4})', finding.get("pdf_filename", "").lower())
            if m and m.group(1) == value:
                return True
    return False


def print_samples(report, n):
    """Print n sample rows per check to the console for quick review."""
    SAMPLE_COLS = ["pdf_filename", "equipment_type", "material", "schedule",
                   "charge_code", "charge_total", "description", "detail"]
    for check, grp in report.groupby("check"):
        print(f"\n{'─' * 60}")
        print(f"  {check}  ({len(grp)} findings)")
        print(f"{'─' * 60}")
        sample = grp.head(n)
        for _, row in sample.iterrows():
            print(f"  PDF:   {row.get('pdf_filename', '')}")
            print(f"  Note:  {row.get('detail', '')}")
            for col in ["equipment_type", "material", "schedule", "charge_code",
                        "charge_total", "description"]:
                val = row.get(col, "")
                if val and str(val) not in ("nan", ""):
                    print(f"  {col:<16} {val}")
            print()
        if len(grp) > n:
            print(f"  ... and {len(grp) - n} more. See {REPORT_PATH}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extracts", default=EXTRACTS_DIR)
    parser.add_argument("--out", default=REPORT_PATH)
    parser.add_argument("--suppressions", default=SUPPRESSIONS_PATH)
    parser.add_argument("--sample", type=int, default=0,
                        help="Print N sample rows per check to console (default: 0 = off)")
    parser.add_argument("--check", default=None,
                        help="Only show samples for this check name (use with --sample)")
    args = parser.parse_args()

    print(f"Loading vendor extracts from {args.extracts}...")
    df = load_extracts(args.extracts)
    n_invoices = df["pdf_filename"].nunique() if "pdf_filename" in df.columns else "?"
    print(f"  {len(df):,} rows across {n_invoices} invoices\n")

    all_findings = []
    checks = [
        ("Invoice# uniqueness",    check_invoice_number_uniqueness),
        ("Account stability",      check_account_number_stability),
        ("Per-row field checks",   check_per_row),
    ]

    for label, fn in checks:
        results = fn(df)
        all_findings.extend(results)
        print(f"  {label}: {len(results)} raw findings")

    if not all_findings:
        print("\nNo issues found.")
        return

    # Apply suppressions
    rules = load_suppressions(args.suppressions)
    if rules:
        before = len(all_findings)
        all_findings = [f for f in all_findings if not is_suppressed(f, rules)]
        print(f"\n  Suppressed {before - len(all_findings)} known false positives "
              f"({len(rules)} rules from {args.suppressions})")

    report = pd.DataFrame(all_findings)

    # Sort: severity (ERROR first), then check name, then filename
    sev_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    report["_sev_order"] = report["severity"].map(sev_order).fillna(9)
    report = report.sort_values(["_sev_order", "check", "pdf_filename"]).drop(columns="_sev_order")

    report.to_csv(args.out, index=False)

    print(f"\nValidation report → {args.out}")
    print(f"\n{'Check':<30} {'Sev':<8} {'Count':>6}")
    print("-" * 48)
    for (check, sev), grp in report.groupby(["check", "severity"]):
        print(f"{check:<30} {sev:<8} {len(grp):>6}")

    totals = report["severity"].value_counts()
    print("-" * 48)
    for sev in ["ERROR", "WARNING", "INFO"]:
        if sev in totals:
            print(f"{'Total ' + sev:<30}          {totals[sev]:>6}")

    if args.sample:
        view = report
        if args.check:
            view = report[report["check"].str.upper() == args.check.upper()]
            if view.empty:
                print(f"\nNo findings for check: {args.check}")
            else:
                print_samples(view, args.sample)
        else:
            print_samples(view, args.sample)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# PostgreSQL validation (called from db.py)
# ---------------------------------------------------------------------------

def run_pg_validation(run_id, pg_config):
    """
    Populate ip_validation_result for a run:
      G3 findings (CHARGE_DIFF, UNDER_CAPTURE, MISSING_BILL_TOTAL) — computed from
        vendor_extracts CSVs (one finding per invoice where valid != True).
      G4 findings (MISSING_EQUIPMENT_TYPE, MISSING_MATERIAL, etc.) — from
        output/validation_report.csv (pre-generated by validate_output.py main).
    Returns total finding count.
    """
    import os
    import csv
    import glob as _glob
    import psycopg2
    import psycopg2.extras

    base = os.path.dirname(__file__)

    conn = psycopg2.connect(**pg_config)
    try:
        cur = conn.cursor()

        # Build pdf_filename → md5_hash map for this run
        cur.execute("""
            SELECT rd.pdf_filename, rd.md5_hash
            FROM wasteology_ops.ip_run_doc d
            JOIN wasteology_ops.ip_raw_document rd ON d.md5_hash = rd.md5_hash
            WHERE d.run_id = %s
        """, (run_id,))
        pdf_to_md5 = {row[0]: row[1] for row in cur.fetchall()}

        # Clear previous results for this run
        cur.execute(
            "DELETE FROM wasteology_ops.ip_validation_result WHERE run_id = %s",
            (run_id,)
        )

        INSERT_SQL = """
            INSERT INTO wasteology_ops.ip_validation_result
              (run_id, md5_hash, check_name, severity, detail,
               pdf_filename, invoice_number, account_number, vendor_name,
               equipment_type, material, schedule, charge_code,
               charge_total, description, service_date,
               prior_value, current_value, variance_pct)
            VALUES %s
        """

        # ── G3: charge-total findings from vendor_extracts ─────────────────
        g3_rows = []
        extracts_dir = os.path.join(base, "output", "vendor_extracts")
        for csv_path in _glob.glob(os.path.join(extracts_dir, "*.csv")):
            if "baseline" in os.path.basename(csv_path):
                continue
            try:
                with open(csv_path, newline="", encoding="utf-8") as cf:
                    seen = set()
                    for row in csv.DictReader(cf):
                        pdf = row.get("pdf_filename", "").strip()
                        if not pdf or pdf in seen:
                            continue
                        seen.add(pdf)
                        md5 = pdf_to_md5.get(pdf)
                        if not md5:
                            continue
                        bt_raw = row.get("bill_total", "").strip()
                        cs_raw = row.get("charge_sum", "").strip()
                        valid  = row.get("valid", "").strip().lower()
                        if not bt_raw:
                            check, sev = "MISSING_BILL_TOTAL", "WARNING"
                            detail = "Invoice total could not be parsed from OCR"
                        elif valid == "false":
                            try:
                                bt_f = float(bt_raw.replace(",", "").replace("$", ""))
                                cs_f = float(cs_raw.replace(",", "").replace("$", "")) if cs_raw else 0.0
                                diff = cs_f - bt_f
                                if cs_f < bt_f:
                                    check, sev = "UNDER_CAPTURE", "WARNING"
                                    detail = (f"charge_sum ${cs_f:,.2f} < "
                                              f"bill_total ${bt_f:,.2f}  (Δ${abs(diff):,.2f})")
                                else:
                                    check, sev = "CHARGE_DIFF", "ERROR"
                                    detail = (f"charge_sum ${cs_f:,.2f} ≠ "
                                              f"bill_total ${bt_f:,.2f}  (Δ${abs(diff):,.2f})")
                            except (ValueError, TypeError):
                                check, sev = "CHARGE_DIFF", "ERROR"
                                detail = f"charge_sum mismatch: cs={cs_raw!r}, bt={bt_raw!r}"
                        else:
                            continue  # valid — no finding
                        g3_rows.append((
                            run_id, md5, check, sev, detail,
                            pdf,
                            row.get("invoice_number", ""), row.get("account_number", ""),
                            row.get("vendor_name", "") or "",
                            None, None, None, None, None, None, None,
                            None, None, None,
                        ))
            except Exception:
                pass

        if g3_rows:
            psycopg2.extras.execute_values(cur, INSERT_SQL, g3_rows, page_size=500)

        # ── G4: per-row field findings from validation_report.csv ──────────
        report_path = os.path.join(base, "output", "validation_report.csv")
        g4_rows = []
        if os.path.exists(report_path):
            with open(report_path, newline="", encoding="utf-8") as f:
                for fnd in csv.DictReader(f):
                    pdf = fnd.get("pdf_filename", "")
                    md5 = pdf_to_md5.get(pdf)
                    if not md5:
                        continue
                    g4_rows.append((
                        run_id, md5,
                        fnd.get("check", ""),
                        fnd.get("severity", ""),
                        fnd.get("detail", ""),
                        pdf,
                        fnd.get("invoice_number", ""),
                        fnd.get("account_number", ""),
                        fnd.get("vendor_name") or "",
                        fnd.get("equipment_type", ""),
                        fnd.get("material", ""),
                        fnd.get("schedule", ""),
                        fnd.get("charge_code", ""),
                        fnd.get("charge_total", "") or None,
                        fnd.get("description", ""),
                        fnd.get("service_date", "") or None,
                        None, None, None,
                    ))

        if g4_rows:
            psycopg2.extras.execute_values(cur, INSERT_SQL, g4_rows, page_size=500)

        conn.commit()
        return len(g3_rows) + len(g4_rows)
    finally:
        conn.close()


def _run_pg_validation_from_db(run_id, pg_config):
    """
    [Legacy] Pull charge rows from PostgreSQL for the given run, run all validation
    checks, clear old results for this run, and insert new findings into
    ip_validation_result.  Returns total finding count.
    """
    import re
    import psycopg2
    import psycopg2.extras

    ONCALL_EQUIP   = {"roll_off", "compactor", "open_top"}
    RECURRING_EQUIP = {"front_load", "rear_load", "cart", "toter"}
    MONTHLY_SERVICE_CODES = {"monthly_service_commercial", "monthly_service_residential"}
    ONCALL_CODES   = {"haul", "disposal", "pull", "delivery"}

    conn = psycopg2.connect(**pg_config)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Pull all charge rows for this run (with invoice + doc context)
        cur.execute("""
            SELECT
                rd.pdf_filename, rd.pdf_path,
                inv.vendor_name, inv.invoice_number, inv.account_number,
                c.charge_idx, c.service_date, c.description,
                c.charge_type, c.charge_total,
                c.equipment_type, c.equipment_size,
                c.material, c.schedule, c.charge_code,
                c.weight, c.weight_unit, c.flag,
                d.md5_hash
            FROM wasteology_ops.ip_run_doc d
            JOIN wasteology_ops.ip_raw_document rd ON d.md5_hash = rd.md5_hash
            LEFT JOIN wasteology_ops.ip_invoice inv ON d.md5_hash = inv.md5_hash
            LEFT JOIN wasteology_ops.ip_charge c ON d.md5_hash = c.md5_hash
            WHERE d.run_id = %s
            ORDER BY rd.pdf_filename, c.charge_idx
        """, (run_id,))
        rows = cur.fetchall()

        def s(row, col):
            v = row[col] if col in row.keys() else None
            return (str(v).strip().lower() if v is not None else "")

        findings = []

        def add(row, check, severity, detail,
                prior_value=None, current_value=None, variance_pct=None):
            findings.append({
                "run_id":         run_id,
                "md5_hash":       row["md5_hash"],
                "check_name":     check,
                "severity":       severity,
                "detail":         detail,
                "pdf_filename":   row["pdf_filename"] or "",
                "invoice_number": row["invoice_number"] or "",
                "account_number": row["account_number"] or "",
                "vendor_name":    row["vendor_name"] or "",
                "equipment_type": row["equipment_type"] or "",
                "material":       row["material"] or "",
                "schedule":       row["schedule"] or "",
                "charge_code":    row["charge_code"] or "",
                "charge_total":   str(row["charge_total"]) if row["charge_total"] is not None else "",
                "description":    row["description"] or "",
                "service_date":   str(row["service_date"]) if row["service_date"] is not None else "",
                "prior_value":    prior_value,
                "current_value":  current_value,
                "variance_pct":   variance_pct,
            })

        # ── Per-charge checks ──────────────────────────────────────────────
        for row in rows:
            if not row["charge_total"]:   # skip invoice-level rows with no charges
                continue

            eq  = s(row, "equipment_type")
            cd  = s(row, "charge_code")
            sc  = s(row, "schedule")
            wt  = s(row, "weight")
            mat = s(row, "material")
            desc = s(row, "description")

            is_fee = (
                "inactivity" in cd or
                ("late" in desc and "fee" in desc) or
                "demurrage" in desc or
                "sweeper" in desc or
                "surcharge" in cd
            )

            # Missing equipment type
            if not eq:
                add(row, "MISSING_EQUIPMENT_TYPE", "ERROR",
                    "charge row has no equipment_type")
                continue

            # Missing material
            if not mat and not is_fee:
                add(row, "MISSING_MATERIAL", "WARNING",
                    f"charge row ({eq}) has no material")

            # Recurring container: must have schedule
            if eq in RECURRING_EQUIP and not sc and not is_fee:
                is_ancillary = any(k in cd for k in (
                    "surcharge", "fee", "offset", "tax",
                    "lock", "late", "administrative",
                    "franchise", "contamination",
                ))
                if not is_ancillary:
                    add(row, "RECURRING_NO_SCHEDULE", "WARNING",
                        f"{eq} charge has no schedule")

            # Roll-off disposal: should have weight
            if eq in ONCALL_EQUIP and "disposal" in cd and not wt:
                add(row, "ROLLOFF_NO_WEIGHT", "INFO",
                    f"{eq} disposal charge has no weight recorded")

            # Charge code / equipment mismatch
            if cd:
                if eq in ONCALL_EQUIP and cd in MONTHLY_SERVICE_CODES:
                    add(row, "EQUIP_CODE_MISMATCH", "WARNING",
                        f"{eq} with '{cd}' — monthly service on on-call container")
                if eq in RECURRING_EQUIP and cd in ONCALL_CODES:
                    add(row, "EQUIP_CODE_MISMATCH", "WARNING",
                        f"{eq} with '{cd}' — haul/disposal code on recurring container")

        # ── Invoice-level checks ───────────────────────────────────────────

        # Duplicate invoice numbers (across PDFs in this run)
        inv_to_pdfs = {}
        for row in rows:
            inv = s(row, "invoice_number")
            pdf = row["pdf_filename"] or ""
            if inv and pdf:
                inv_to_pdfs.setdefault(inv, set()).add(pdf)

        # Index a representative row per PDF for duplicate reporting
        pdf_to_row = {}
        for row in rows:
            k = row["pdf_filename"]
            if k and k not in pdf_to_row:
                pdf_to_row[k] = row

        for inv, pdfs in inv_to_pdfs.items():
            if len(pdfs) > 1:
                pdf_list = sorted(pdfs)
                for pdf in pdf_list:
                    row = pdf_to_row.get(pdf)
                    if row:
                        add(row, "DUPLICATE_INVOICE_NUMBER", "WARNING",
                            f"Invoice# '{inv}' found on {len(pdfs)} PDFs: {pdf_list}")

        # Account number stability (same site prefix + vendor, different account#)
        site_vendor_accts = {}  # (site_prefix, vendor_name) → {acct: representative_row}
        for row in rows:
            pdf = row["pdf_filename"] or ""
            acct = s(row, "account_number")
            vendor = s(row, "vendor_name")
            m = re.match(r'^([A-Za-z]{2,6}\d{1,4})', pdf)
            if m and acct and vendor:
                key = (m.group(1).upper(), vendor)
                d = site_vendor_accts.setdefault(key, {})
                if acct not in d:
                    d[acct] = row

        for (site, vendor), acct_map in site_vendor_accts.items():
            if len(acct_map) > 1:
                accts = sorted(acct_map.keys())
                for acct, row in acct_map.items():
                    add(row, "ACCOUNT_UNSTABLE", "WARNING",
                        f"Site {site} ({vendor}) has {len(accts)} account numbers: {accts}")

        # ── Write to ip_validation_result ─────────────────────────────────
        # Clear previous results for this run
        cur.execute(
            "DELETE FROM wasteology_ops.ip_validation_result WHERE run_id = %s",
            (run_id,)
        )

        if findings:
            insert_sql = """
                INSERT INTO wasteology_ops.ip_validation_result
                  (run_id, md5_hash, check_name, severity, detail,
                   pdf_filename, invoice_number, account_number, vendor_name,
                   equipment_type, material, schedule, charge_code,
                   charge_total, description, service_date,
                   prior_value, current_value, variance_pct)
                VALUES %s
            """
            psycopg2.extras.execute_values(cur, insert_sql, [
                (
                    f["run_id"], f["md5_hash"], f["check_name"], f["severity"], f["detail"],
                    f["pdf_filename"], f["invoice_number"], f["account_number"], f["vendor_name"],
                    f["equipment_type"], f["material"], f["schedule"], f["charge_code"],
                    f["charge_total"], f["description"], f["service_date"] or None,
                    f["prior_value"], f["current_value"], f["variance_pct"],
                )
                for f in findings
            ], page_size=500)

        conn.commit()
        return len(findings)
    finally:
        conn.close()
