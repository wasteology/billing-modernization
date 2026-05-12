"""USA Waste & Recycling - same WM billing system."""

from typing import List
from ..models import ChargeItem
from .waste_management import extract_waste_management


def extract_usa_waste(text: str) -> List[ChargeItem]:
    return extract_waste_management(text)
