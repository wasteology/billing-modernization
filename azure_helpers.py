"""
Shared Azure SQL helpers used by azure_etl.py, sync_services.py, and sync_billing.py.

- get_azure_connection(): Azure AD token auth via pyodbc
- derive_is_active(end_date_val): end_date -> bool (single source of truth)
- is_active(val): ERP Yes/No -> bool (legacy, for non-service tables)
- parse_container_size(equipment_type): regex yard/gallon parser
- fmt_date(val): datetime -> date
- fmt_datetime(val): datetime passthrough
- decimal_to_float(val): Decimal -> float
"""

import re
import struct
from datetime import date
from decimal import Decimal

# Azure SQL configuration
SQL_SERVER = "wasteology.database.windows.net"
SQL_DATABASE = "wasteology"
SQL_DRIVER = "{ODBC Driver 18 for SQL Server}"


def get_azure_connection():
    """Connect to Azure SQL using Azure AD token authentication."""
    import pyodbc
    from azure.identity import AzureCliCredential, DefaultAzureCredential

    try:
        credential = AzureCliCredential()
        token = credential.get_token("https://database.windows.net/.default")
    except Exception:
        credential = DefaultAzureCredential()
        token = credential.get_token("https://database.windows.net/.default")

    token_bytes = token.token.encode("UTF-16-LE")
    token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)

    conn_str = (
        f"Driver={SQL_DRIVER};"
        f"Server={SQL_SERVER};"
        f"Database={SQL_DATABASE};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
    )

    SQL_COPT_SS_ACCESS_TOKEN = 1256
    return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})


def derive_is_active(end_date_val) -> bool:
    """Derive is_active from end_date (single source of truth).

    Active: end_date is NULL, sentinel '1900-01-01', or >= today.
    Inactive: end_date < today and not sentinel.
    """
    if end_date_val is None:
        return True
    d = fmt_date(end_date_val)
    if d is None:
        return True
    if d == date(1900, 1, 1):
        return True
    return d >= date.today()


def is_active(val) -> bool:
    """Convert ERP 'Yes'/'No' to True/False."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return bool(val)
    return str(val).strip().lower() == "yes"


def parse_container_size(equipment_type: str) -> float | None:
    """Parse container size in yards from equipment_type string."""
    if not equipment_type:
        return None
    m = re.match(r"(\d+)\s*Yard", equipment_type)
    if m:
        return float(m.group(1))
    m = re.match(r"(\d+)\s*Gallon", equipment_type)
    if m:
        return round(float(m.group(1)) / 201.974, 3)
    return None


def fmt_date(val) -> date | None:
    """Format a datetime value to a Python date object."""
    if val is None:
        return None
    if isinstance(val, date) and not hasattr(val, 'hour'):
        return val
    if hasattr(val, 'date'):
        return val.date()
    s = str(val)[:10] if val else None
    if s:
        from datetime import datetime
        try:
            return datetime.strptime(s, '%Y-%m-%d').date()
        except ValueError:
            return None
    return None


def fmt_datetime(val):
    """Format a datetime value to a Python datetime or string."""
    if val is None:
        return None
    if hasattr(val, 'isoformat'):
        return val
    return str(val) if val else None


def decimal_to_float(val):
    """Convert Decimal to float for psycopg2 compatibility."""
    if isinstance(val, Decimal):
        return float(val)
    return val
