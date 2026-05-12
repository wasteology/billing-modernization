"""
Central configuration constants for the analytical pipeline.

All thresholds, timing windows, and classification parameters in one place.
"""

# Chain building
MAX_GAP_DAYS = 60                   # Max days between deactivation → activation for chain link
SENTINEL_END_DATE = '1900-01-01'    # ERP sentinel meaning "no end date" (i.e., active)

# Price increase timing
INITIAL_PI_MONTHS = 24              # First customer PI eligibility (months from chain start)
RECURRING_PI_MONTHS = 12            # Subsequent customer PI cadence

# Margin targets
TARGET_MARGIN_PCT = 0.18            # 18% target margin

# Leak categories
LEAK_CATEGORIES = {
    1: "Vendor PI Outside Contract",
    2: "Missed Customer PI",
    3: "Margin Contraction on Change",
    4: "Disposal Not Passed Through",
    5: "Charges Absorbed",
    6: "Variable Charge Mishandling",
    7: "Surcharge Step Change Not Offset",
}

# Margin trend thresholds (cumulative erosion)
MARGIN_TREND_IMPROVING = 0.02      # erosion > +2% → improving
MARGIN_TREND_CRITICAL = -0.05      # erosion < -5% → critical
MARGIN_TREND_DECLINING = -0.01     # erosion < -1% → declining

# Variable charge analysis
VARIABLE_COST_CV_THRESHOLD = 0.05  # Leak 6: cost CV > 5%
VARIABLE_CHARGE_FLAT_CV = 0.03     # Leak 6: charge CV < 3% = effectively flat

# Surcharge step detection
SURCHARGE_WINDOW_SIZE = 3          # Months for rolling median comparison (Leak 7)

# Market rate benchmarks
BENCHMARK_MIN_SAMPLE_SIZE = 3      # Minimum observations per group for statistical validity

# PostgreSQL connection
import os

SCHEMA_NAME = "wasteology_ops"

PG_CONFIG = {
    "host": os.environ.get("PG_HOST", "pg-wasteology.postgres.database.azure.com"),
    "port": int(os.environ.get("PG_PORT", 5432)),
    "dbname": os.environ.get("PG_DBNAME", "wasteology_dev"),
    "user": os.environ.get("PG_USER", "sstclair"),
    "password": os.environ.get("PG_PASSWORD", ""),
    "options": f"-c search_path={SCHEMA_NAME},public",
    "sslmode": "require",
}
