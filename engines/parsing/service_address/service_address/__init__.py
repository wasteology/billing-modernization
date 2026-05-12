"""Service address extraction from invoice OCR text."""

from .service_address_engine import extract_service_address, VENDOR_ADDRESSES

__all__ = ["extract_service_address", "VENDOR_ADDRESSES"]
