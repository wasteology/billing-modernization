# Normalization Engines
# Exports vendor detection and normalization for use by pipelines

from .vendor_normalization_engine import VendorNormalizer, VENDOR_MAPPING
from .vendor_detection_module_v8 import VENDOR_PATTERNS as VENDOR_PATTERNS_V8

# Contract normalization (for vendor_contract_db pipeline)
from .contract_normalization import (
    ContractNormalizer,
    FilenameParser,
    FilenameVendorNormalizer,
    CustomerNormalizer,
    ContractNormalizationResult,
    ParsedFilename,
    FILENAME_VENDOR_MAP,
    FILENAME_CUSTOMER_MAP,
)

__all__ = [
    # Invoice pipeline
    'VendorNormalizer',
    'VENDOR_MAPPING',
    'VENDOR_PATTERNS_V8',
    # Contract pipeline
    'ContractNormalizer',
    'FilenameParser',
    'FilenameVendorNormalizer',
    'CustomerNormalizer',
    'ContractNormalizationResult',
    'ParsedFilename',
    'FILENAME_VENDOR_MAP',
    'FILENAME_CUSTOMER_MAP',
]
