"""
app.py — 6-gate HITL invoice review (ng-report/invoices)
Uses same wasteology_ops PostgreSQL schema as invoice-poc.
Port: 5051
"""
import csv, io, os
from flask import Flask, jsonify, request, send_from_directory, make_response, send_file
from flask_cors import CORS
import db

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

PDF_BASE = "/home/scstclair/projects/ng-report"


# ── Static ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ── Run lifecycle ─────────────────────────────────────────────────────────

@app.route("/api/runs")
def list_runs():
    return jsonify(db.get_all_runs())


@app.route("/api/run/<run_id>")
def get_run(run_id):
    summary = db.get_run_summary(run_id)
    if not summary:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(summary)


# ── Gate data ─────────────────────────────────────────────────────────────

@app.route("/api/run/<run_id>/gate/<int:gate>/results")
def gate_results(run_id, gate):
    return jsonify(db.get_gate_results(run_id, gate))


@app.route("/api/run/<run_id>/gate/<int:gate>/exceptions")
def gate_exceptions(run_id, gate):
    return jsonify(db.get_gate_exceptions(run_id, gate))


# ── Validation (Gates 4 & 5) ──────────────────────────────────────────────

@app.route("/api/run/<run_id>/validate", methods=["POST"])
def run_validation(run_id):
    try:
        count = db.run_validation(run_id)
        return jsonify({"ok": True, "findings": count})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── HITL actions ──────────────────────────────────────────────────────────

@app.route("/api/run/<run_id>/gate/<int:gate>/resolve", methods=["POST"])
def resolve_exception(run_id, gate):
    body   = request.get_json()
    action = body.get("action")
    issue  = body.get("issue")
    ids    = body.get("doc_ids", "all")
    resolved = db.resolve_exception(run_id, gate, issue, ids, action)
    return jsonify({"ok": True, "resolved": resolved})


@app.route("/api/run/<run_id>/push", methods=["POST"])
def push_run(run_id):
    db.push_run(run_id)
    return jsonify({"ok": True})


# ── Gate 6 stats ──────────────────────────────────────────────────────────

@app.route("/api/run/<run_id>/stats")
def run_stats(run_id):
    return jsonify(db.get_run_stats(run_id))


# ── Document detail ───────────────────────────────────────────────────────

@app.route("/api/run/<run_id>/doc/<doc_id>")
def doc_detail(run_id, doc_id):
    doc = db.get_doc_detail(run_id, doc_id)
    if not doc:
        return jsonify({"error": "Not found"}), 404
    return jsonify(doc)


# ── PDF serving ───────────────────────────────────────────────────────────

@app.route("/api/pdf")
def serve_pdf():
    """Serve a PDF by its path (passed as ?path=... query param)."""
    pdf_path = request.args.get("path", "")
    if not pdf_path:
        return "Missing path", 400
    # Normalise case: /Invoices/ → /invoices/
    pdf_path = pdf_path.replace("/Invoices/", "/invoices/")
    # Security: must be under the known base
    real_path = os.path.realpath(pdf_path)
    real_base = os.path.realpath(PDF_BASE)
    if not real_path.startswith(real_base):
        return "Forbidden", 403
    if not os.path.isfile(real_path):
        return "Not found", 404
    return send_file(real_path, mimetype="application/pdf")


# ── CSV export ────────────────────────────────────────────────────────────

@app.route("/api/run/<run_id>/export")
def export_csv(run_id):
    rows = db.get_export_rows(run_id)
    if not rows:
        return jsonify({"error": "No rows to export"}), 404

    for row in rows:
        pdf_path = (row.pop("pdf_path", "") or "").replace("/Invoices/", "/invoices/")
        row["pdf_link"] = "file://" + pdf_path.replace(" ", "%20") if pdf_path else ""

    cols = [
        "pdf_filename", "pdf_link", "invoice_number", "invoice_date",
        "account_number", "bill_total", "charge_sum", "num_charges",
        "valid", "diff", "service_date", "description", "charge_type",
        "charge_total", "equipment_type", "equipment_size", "material",
        "schedule", "charge_code", "weight", "weight_unit", "flag",
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv"
    response.headers["Content-Disposition"] = f"attachment; filename=run_{run_id}.csv"
    return response


if __name__ == "__main__":
    app.run(debug=True, port=5051)
