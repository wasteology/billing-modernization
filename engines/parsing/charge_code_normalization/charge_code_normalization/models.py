"""Data models for charge code normalization."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class NormalizedCharge:
    """A raw charge description mapped to a canonical charge code."""
    charge_code: str               # Canonical name (e.g., "Monthly Service Commercial")
    classification: str            # Bucket (e.g., "recurring", "fuel", "demand - weight")
    raw_description: str           # Original input for audit trail
    confidence: str = 'HIGH'       # HIGH = vendor-specific match, MEDIUM = generic match
    match_type: str = 'generic'    # 'exact', 'vendor_specific', 'generic'
