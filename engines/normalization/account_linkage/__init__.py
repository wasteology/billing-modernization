"""
Account Linkage Module

Links hauler invoice account numbers to CIE trade service IDs via transitive join:

    OCR Invoice → Billing Charges → Service ID
    (account#)    (billing_ref)     (service_id)

Coverage: 71.0% of active services (17,311 / 24,374)

Usage:
    from normalization_engines.account_linkage import AccountLinker

    linker = AccountLinker()
    service_id = linker.get_service_id(vendor='Waste Management', account='12345678')
"""

from .linkage import AccountLinker, run_linkage_pipeline

__all__ = ['AccountLinker', 'run_linkage_pipeline']
