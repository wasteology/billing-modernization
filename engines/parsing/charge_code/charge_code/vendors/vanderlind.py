"""Vanderlind Recycling - same billing system as Container Rentals."""
from typing import List
from ..models import ChargeItem
from .container_rentals import _extract_container_rentals_format

def extract_vanderlind(text: str) -> List[ChargeItem]:
    return _extract_container_rentals_format(text)
