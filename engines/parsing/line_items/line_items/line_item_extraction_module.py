"""
Line Item Field Extraction Patterns - Easy Vendors
Universal Waste, Active Waste, Boren Brothers

Extracts: equipment_size, equipment_type, material
"""

import re
from typing import Optional, Dict

# =============================================================================
# UNIVERSAL WASTE
# =============================================================================
# Examples:
#   "6YD FL Trash"
#   "3YD FL Trash"
#   "Lock"

UNIVERSAL_WASTE_PATTERNS = {
    'equipment_size': re.compile(r'(\d+)\s*YD', re.IGNORECASE),
    'equipment_type': re.compile(r'\d+\s*YD\s+(FL|FRONT\s*LOAD)', re.IGNORECASE),
    'material': re.compile(r'(?:FL|FRONT\s*LOAD)\s+(Trash|Recycl(?:e|ing)?|MSW|OCC)', re.IGNORECASE),
}

def extract_universal_waste(description: str) -> Dict[str, Optional[str]]:
    """Extract fields from Universal Waste line item description."""
    result = {
        'equipment_size': None,
        'equipment_type': None,
        'material': None,
    }
    
    # Equipment size: "6YD", "3YD"
    size_match = UNIVERSAL_WASTE_PATTERNS['equipment_size'].search(description)
    if size_match:
        result['equipment_size'] = f"{size_match.group(1)} YD"
    
    # Equipment type: FL = Front Load
    type_match = UNIVERSAL_WASTE_PATTERNS['equipment_type'].search(description)
    if type_match:
        result['equipment_type'] = 'FRONT LOAD'
    
    # Material: Trash, Recycle, etc.
    material_match = UNIVERSAL_WASTE_PATTERNS['material'].search(description)
    if material_match:
        mat = material_match.group(1).upper()
        # Normalize
        if mat.startswith('RECYCL'):
            mat = 'RECYCLING'
        result['material'] = mat
    
    return result


# =============================================================================
# ACTIVE WASTE
# =============================================================================
# Examples:
#   "2 YD FRONT LOAD TRASH W/ LOCK BAR"
#   "95 GALLON RECYCLE SVC - COMMERCIAL"
#   "8 YD FRONT LOAD - OCC"
#   "8 YD FRONT LOAD RECYCLE"
#   "6 YD FRONT LOAD TRASH"
#   "LOCKBAR MONTHLY CHARGE"

ACTIVE_WASTE_PATTERNS = {
    # Size: "2 YD", "8 YD", "95 GALLON", "40YD"
    'equipment_size_yd': re.compile(r'(\d+)\s*YD', re.IGNORECASE),
    'equipment_size_gal': re.compile(r'(\d+)\s*GALLON', re.IGNORECASE),
    
    # Type: FRONT LOAD, ROLL OFF
    'equipment_type': re.compile(r'(FRONT\s*LOAD|ROLL\s*OFF)', re.IGNORECASE),
    
    # Material: after equipment type or at end
    'material_frontload': re.compile(
        r'(?:FRONT\s*LOAD)\s*[-]?\s*(TRASH|RECYCLE|RECYCLING|OCC|MSW|SOLID\s*WASTE)',
        re.IGNORECASE
    ),
    # Roll-off material comes before HAUL/DISPOSAL in Active Waste format
    # e.g. "DISPOSAL CHARGE - PERMANENT TRASH" or standalone "TRASH" line
    'material_rolloff': re.compile(
        r'(?:DISPOSAL|HAUL)\s+CHARGE\s*[-]?\s*(?:PERMANENT\s*)?(TRASH|MSW|C\s*&\s*D|OCC|RECYCL\w*)',
        re.IGNORECASE
    ),
}

def extract_active_waste(description: str) -> Dict[str, Optional[str]]:
    """Extract fields from Active Waste line item description."""
    result = {
        'equipment_size': None,
        'equipment_type': None,
        'material': None,
    }
    
    # Equipment size - check YD first, then GALLON
    size_yd = ACTIVE_WASTE_PATTERNS['equipment_size_yd'].search(description)
    size_gal = ACTIVE_WASTE_PATTERNS['equipment_size_gal'].search(description)
    
    if size_yd:
        result['equipment_size'] = f"{size_yd.group(1)} YD"
    elif size_gal:
        result['equipment_size'] = f"{size_gal.group(1)} GAL"
        result['equipment_type'] = 'CART'  # GALLON implies cart
    
    # Check for explicit equipment type
    type_match = ACTIVE_WASTE_PATTERNS['equipment_type'].search(description)
    if type_match:
        result['equipment_type'] = type_match.group(1).upper().replace('  ', ' ')
    elif size_yd and not result['equipment_type']:
        # Default YD to front load unless roll-off detected
        result['equipment_type'] = 'FRONT LOAD'
    
    # Material - try front load pattern first, then roll-off
    mat_match = ACTIVE_WASTE_PATTERNS['material_frontload'].search(description)
    if not mat_match:
        mat_match = ACTIVE_WASTE_PATTERNS['material_rolloff'].search(description)
    
    # Also check for gallon + material pattern
    if not mat_match:
        gal_mat = re.search(r'GALLON\s+(RECYCLE|TRASH|MSW)\s*SVC', description, re.IGNORECASE)
        if gal_mat:
            mat_match = gal_mat
    
    if mat_match:
        mat = mat_match.group(1).upper().replace('  ', ' ')
        # Normalize
        if mat.startswith('RECYCL'):
            mat = 'RECYCLING'
        elif mat == 'SOLID WASTE':
            mat = 'MSW'
        result['material'] = mat
    
    return result


# =============================================================================
# BOREN BROTHERS
# =============================================================================
# Examples:
#   "8 YD FRONT LOAD TRASH"
#   "8 YD FRONT LOAD RECYCLE"
#   "30YD ROLL OFF - SCRAP METAL"
#   "30YD ROLL OFF - SCRAP METAL - 1 days of no activity"
#   "Compactor Repair - PO OC403336"

BOREN_BROTHERS_PATTERNS = {
    # Size: "8 YD", "30YD"
    'equipment_size': re.compile(r'(\d+)\s*YD', re.IGNORECASE),
    
    # Type: FRONT LOAD, ROLL OFF, Compactor
    'equipment_type': re.compile(r'(FRONT\s*LOAD|ROLL\s*OFF|COMPACTOR)', re.IGNORECASE),
    
    # Material: TRASH, RECYCLE, SCRAP METAL, etc.
    'material_frontload': re.compile(
        r'FRONT\s*LOAD\s+(TRASH|RECYCLE|RECYCLING|OCC|MSW)',
        re.IGNORECASE
    ),
    'material_rolloff': re.compile(
        r'ROLL\s*OFF\s*[-]?\s*(TRASH|SCRAP\s*METAL|C\s*&\s*D|OCC|RECYCLING?|MSW)',
        re.IGNORECASE
    ),
}

def extract_boren_brothers(description: str) -> Dict[str, Optional[str]]:
    """Extract fields from Boren Brothers line item description."""
    result = {
        'equipment_size': None,
        'equipment_type': None,
        'material': None,
    }
    
    # Equipment size
    size_match = BOREN_BROTHERS_PATTERNS['equipment_size'].search(description)
    if size_match:
        result['equipment_size'] = f"{size_match.group(1)} YD"
    
    # Equipment type
    type_match = BOREN_BROTHERS_PATTERNS['equipment_type'].search(description)
    if type_match:
        etype = type_match.group(1).upper().replace('  ', ' ')
        result['equipment_type'] = etype
    
    # Material - depends on equipment type
    if result['equipment_type'] == 'FRONT LOAD':
        mat_match = BOREN_BROTHERS_PATTERNS['material_frontload'].search(description)
    elif result['equipment_type'] == 'ROLL OFF':
        mat_match = BOREN_BROTHERS_PATTERNS['material_rolloff'].search(description)
    else:
        mat_match = None
    
    if mat_match:
        mat = mat_match.group(1).upper().replace('  ', ' ')
        # Normalize
        if mat == 'RECYCLE':
            mat = 'RECYCLING'
        elif mat == 'SCRAP METAL':
            mat = 'METAL'
        result['material'] = mat
    
    return result


# =============================================================================
# RUMPKE
# =============================================================================
# Examples:
#   "8YD FL/MONTH-MSW"
#   "8YD FL/MONTH-CRDBD"
#   "8YD FL/MONTH-COM MIX"
#   "8YD FL/EXTRA-MSW"
#   "20YD RO LEASE"
#   "20YD RO/LOAD-C&D"
#   "40YD RO/LOAD-STEEL"
#   "20YD ROLL OFF-DELIVER"
#   "RO DISP/TON-C&D"
#   "RO DISP/TON-STEEL"
#   "FUEL SURCHARGE FL"
#   "FUEL SURCHARGE RO"

RUMPKE_PATTERNS = {
    # Size: "8YD", "20YD", "40YD", "6YD", "4YD"
    'equipment_size': re.compile(r'(\d+)\s*YD', re.IGNORECASE),
    
    # Type: FL (Front Load), RO (Roll Off), ROLL OFF
    'equipment_type_fl': re.compile(r'\d+\s*YD\s*(FL)', re.IGNORECASE),
    'equipment_type_ro': re.compile(r'\d+\s*YD\s*(RO|ROLL\s*OFF)', re.IGNORECASE),
    'equipment_type_disp': re.compile(r'^RO\s*DISP', re.IGNORECASE),  # disposal line (no size)
    
    # Material: after dash in FL format or RO format
    # FL: 8YD FL/MONTH-MSW, 8YD FL/EXTRA-CRDBD
    'material_fl': re.compile(
        r'FL/(?:MONTH|EXTRA|WEEK)\s*-\s*(MSW|CRDBD|COM\s*MIX|RECY|OCC|RECYCL\w*)',
        re.IGNORECASE
    ),
    # RO Load: 20YD RO/LOAD-C&D
    'material_ro_load': re.compile(
        r'RO/LOAD\s*-\s*(C\s*&\s*D|STEEL|MSW|TRASH|OCC|CRDBD|RECY)',
        re.IGNORECASE
    ),
    # RO Disposal: RO DISP/TON-C&D
    'material_ro_disp': re.compile(
        r'RO\s*DISP/TON\s*-\s*(C\s*&\s*D|STEEL|MSW|TRASH|OCC|CRDBD)',
        re.IGNORECASE
    ),
}

def extract_rumpke(description: str) -> Dict[str, Optional[str]]:
    """Extract fields from Rumpke line item description."""
    result = {
        'equipment_size': None,
        'equipment_type': None,
        'material': None,
    }
    
    # Equipment size
    size_match = RUMPKE_PATTERNS['equipment_size'].search(description)
    if size_match:
        result['equipment_size'] = f"{size_match.group(1)} YD"
    
    # Equipment type - check FL first, then RO
    if RUMPKE_PATTERNS['equipment_type_fl'].search(description):
        result['equipment_type'] = 'FRONT LOAD'
    elif RUMPKE_PATTERNS['equipment_type_ro'].search(description):
        result['equipment_type'] = 'ROLL OFF'
    elif RUMPKE_PATTERNS['equipment_type_disp'].search(description):
        result['equipment_type'] = 'ROLL OFF'  # disposal is for roll-off
    
    # Material - try FL pattern first, then RO patterns
    mat_match = RUMPKE_PATTERNS['material_fl'].search(description)
    if not mat_match:
        mat_match = RUMPKE_PATTERNS['material_ro_load'].search(description)
    if not mat_match:
        mat_match = RUMPKE_PATTERNS['material_ro_disp'].search(description)
    
    if mat_match:
        mat = mat_match.group(1).upper().replace(' ', '')
        # Normalize material names
        mat_map = {
            'MSW': 'MSW',
            'CRDBD': 'CARDBOARD',
            'COMMIX': 'COMMERCIAL MIX',
            'C&D': 'C&D',
            'STEEL': 'METAL',
            'RECY': 'RECYCLING',
            'RECYCLING': 'RECYCLING',
            'OCC': 'OCC',
            'TRASH': 'MSW',
        }
        result['material'] = mat_map.get(mat, mat)
    
    return result


# =============================================================================
# COCKEY'S ENTERPRISES
# =============================================================================
# Examples:
#   "FL-Comm-Recycling-08yd"
#   "FL-Comm-Trash-08yd"
#   "FL-Comm-Trash-04yd"
#   "RL-Comm-Recycling-95gl"  (Rear Load cart)
#   "RO Haul Charge - Open Top"
#   "RO Haul Charge - Compactor"
#   "RODisposal Charge - per Ton"
#   "RO - Disposal Charge - per Ton"

COCKEYS_PATTERNS = {
    # FL format: FL-Comm-Material-XXyd
    'fl_full': re.compile(
        r'FL-Comm-(\w+)-(\d+)yd',
        re.IGNORECASE
    ),

    # RL (Rear Load/Cart) format: RL-Comm-Recycling-95gl
    'rl_full': re.compile(
        r'RL-Comm-(\w+)-(\d+)gl',
        re.IGNORECASE
    ),

    # RO format with equipment type: RO Haul Charge - Open Top / Compactor
    'ro_haul_type': re.compile(r'RO\s*-?\s*Haul\s*Charge\s*-\s*(Open\s*Top|Compactor)', re.IGNORECASE),
    'ro_disposal': re.compile(r'RO\s*-?\s*Disposal\s*Charge', re.IGNORECASE),

    # Statement format: "MONTHLY TRASH SERVICE", "SINGLE STREAM RECYCLING"
    'stmt_trash': re.compile(r'MONTHLY\s+TRASH\s+SERVICE', re.IGNORECASE),
    'stmt_recycle': re.compile(r'SINGLE\s+STREAM\s+RECYCLING', re.IGNORECASE),
    # Statement format: "HAUL RATE ON XX YD"
    'stmt_haul': re.compile(r'HAUL\s+RATE\s+ON\s+(\d+)\s*YD', re.IGNORECASE),
    'stmt_disposal': re.compile(r'MINIMUM\s+DISPOSAL\s+CHARGE', re.IGNORECASE),
}

def extract_cockeys(description: str) -> Dict[str, Optional[str]]:
    """Extract fields from Cockey's Enterprises line item description."""
    result = {
        'equipment_size': None,
        'equipment_type': None,
        'material': None,
    }
    
    # Try FL format first: FL-Comm-Recycling-08yd
    fl_match = COCKEYS_PATTERNS['fl_full'].search(description)
    if fl_match:
        material_raw = fl_match.group(1).upper()
        size = fl_match.group(2)
        
        result['equipment_size'] = f"{int(size)} YD"  # Remove leading zero
        result['equipment_type'] = 'FRONT LOAD'
        
        # Normalize material
        if material_raw == 'RECYCLING':
            result['material'] = 'RECYCLING'
        elif material_raw == 'TRASH':
            result['material'] = 'MSW'
        else:
            result['material'] = material_raw
        
        return result
    
    # Try RL (cart) format: RL-Comm-Recycling-95gl
    rl_match = COCKEYS_PATTERNS['rl_full'].search(description)
    if rl_match:
        material_raw = rl_match.group(1).upper()
        size = rl_match.group(2)
        
        result['equipment_size'] = f"{int(size)} GAL"
        result['equipment_type'] = 'CART'
        
        if material_raw == 'RECYCLING':
            result['material'] = 'RECYCLING'
        elif material_raw == 'TRASH':
            result['material'] = 'MSW'
        else:
            result['material'] = material_raw
        
        return result
    
    # Check RO patterns with equipment type
    ro_type_match = COCKEYS_PATTERNS['ro_haul_type'].search(description)
    if ro_type_match:
        equip_type = ro_type_match.group(1).upper().replace(' ', '')
        if equip_type == 'OPENTOP':
            result['equipment_type'] = 'ROLL OFF'
        elif equip_type == 'COMPACTOR':
            result['equipment_type'] = 'COMPACTOR'
        return result
    
    if COCKEYS_PATTERNS['ro_disposal'].search(description):
        result['equipment_type'] = 'ROLL OFF'
        return result

    # Statement format: MONTHLY TRASH SERVICE
    if COCKEYS_PATTERNS['stmt_trash'].search(description):
        result['equipment_type'] = 'FRONT LOAD'
        result['material'] = 'MSW'
        return result

    # Statement format: SINGLE STREAM RECYCLING
    if COCKEYS_PATTERNS['stmt_recycle'].search(description):
        result['equipment_type'] = 'FRONT LOAD'
        result['material'] = 'RECYCLING'
        return result

    # Statement format: HAUL RATE ON 40 YD
    haul_match = COCKEYS_PATTERNS['stmt_haul'].search(description)
    if haul_match:
        result['equipment_type'] = 'ROLL OFF'
        result['equipment_size'] = f"{int(haul_match.group(1))} YD"
        return result

    # Statement format: MINIMUM DISPOSAL CHARGE
    if COCKEYS_PATTERNS['stmt_disposal'].search(description):
        result['equipment_type'] = 'ROLL OFF'
        return result

    return result


# =============================================================================
# ROBINSON WASTE
# =============================================================================
# Examples:
#   "Serv #001 Front Load Trash - Permanent 1 - 3YD"
#   "Serv #001 Front Load Trash - Permanent 1 - 2YD"
#   "001 3.00YD Front Load Trash - Permanent"

ROBINSON_WASTE_PATTERNS = {
    # Format: Serv #XXX [Type] [Material] - Permanent X - [Size]YD
    'full_pattern': re.compile(
        r'(?:Serv\s*#\d+\s+)?(Front\s*Load|Roll\s*Off)\s+(Trash|Recycl\w*|MSW|OCC)\s*-\s*Permanent[^-]*-\s*(\d+)\s*YD',
        re.IGNORECASE
    ),
    # Alternate: X.XXYD Front Load Trash
    'alt_pattern': re.compile(
        r'(\d+(?:\.\d+)?)\s*YD\s+(Front\s*Load|Roll\s*Off)\s+(Trash|Recycl\w*|MSW|OCC)',
        re.IGNORECASE
    ),
}

def extract_robinson_waste(description: str) -> Dict[str, Optional[str]]:
    """Extract fields from Robinson Waste line item description."""
    result = {
        'equipment_size': None,
        'equipment_type': None,
        'material': None,
    }
    
    # Try full pattern first
    match = ROBINSON_WASTE_PATTERNS['full_pattern'].search(description)
    if match:
        equip_type = match.group(1).upper().replace('  ', ' ')
        material = match.group(2).upper()
        size = match.group(3)
        
        result['equipment_type'] = 'FRONT LOAD' if 'FRONT' in equip_type else 'ROLL OFF'
        result['equipment_size'] = f"{int(float(size))} YD"
        result['material'] = 'RECYCLING' if material.startswith('RECYCL') else ('MSW' if material == 'TRASH' else material)
        return result
    
    # Try alternate pattern
    match = ROBINSON_WASTE_PATTERNS['alt_pattern'].search(description)
    if match:
        size = match.group(1)
        equip_type = match.group(2).upper().replace('  ', ' ')
        material = match.group(3).upper()
        
        result['equipment_size'] = f"{int(float(size))} YD"
        result['equipment_type'] = 'FRONT LOAD' if 'FRONT' in equip_type else 'ROLL OFF'
        result['material'] = 'RECYCLING' if material.startswith('RECYCL') else ('MSW' if material == 'TRASH' else material)
        return result
    
    return result


# =============================================================================
# STANDARD WASTE
# =============================================================================
# Examples:
#   Code "30YDRO" with description "30 YARD OPEN TOP"
#   Code "40YDCO" with description "40 YARD COMPACTOR"
#   Code "40YDREC" with description "40 YARD COMPACTOR RECYCLING"
#   Code "TONS-MSW" with description "TONS - MSW (1 TON MIN)"
#   Code "TONS-OCC" with description "TONS- OCC"

STANDARD_WASTE_PATTERNS = {
    # Equipment codes: 30YDRO, 40YDCO, 40YDREC
    'equip_code': re.compile(r'(\d+)YD(RO|CO|REC)', re.IGNORECASE),
    
    # Full description: "30 YARD OPEN TOP", "40 YARD COMPACTOR"
    'full_desc': re.compile(
        r'(\d+)\s*YARD\s+(OPEN\s*TOP|COMPACTOR)(?:\s+(RECYCLING|MSW|TRASH|OCC))?',
        re.IGNORECASE
    ),
    
    # Tonnage: TONS-MSW, TONS-OCC, TONS - MSW
    'tonnage': re.compile(r'TONS\s*-?\s*(MSW|OCC|TRASH|C&D|RECYCL\w*)', re.IGNORECASE),
}

def extract_standard_waste(description: str) -> Dict[str, Optional[str]]:
    """Extract fields from Standard Waste line item description."""
    result = {
        'equipment_size': None,
        'equipment_type': None,
        'material': None,
    }
    
    # Try equipment code first
    code_match = STANDARD_WASTE_PATTERNS['equip_code'].search(description)
    if code_match:
        size = code_match.group(1)
        type_code = code_match.group(2).upper()
        
        result['equipment_size'] = f"{size} YD"
        
        if type_code == 'RO':
            result['equipment_type'] = 'ROLL OFF'
        elif type_code == 'CO':
            result['equipment_type'] = 'COMPACTOR'
        elif type_code == 'REC':
            result['equipment_type'] = 'COMPACTOR'
            result['material'] = 'RECYCLING'
    
    # Try full description
    desc_match = STANDARD_WASTE_PATTERNS['full_desc'].search(description)
    if desc_match:
        if not result['equipment_size']:
            result['equipment_size'] = f"{desc_match.group(1)} YD"
        
        equip = desc_match.group(2).upper().replace(' ', '')
        if equip == 'OPENTOP':
            result['equipment_type'] = 'ROLL OFF'
        elif equip == 'COMPACTOR':
            result['equipment_type'] = 'COMPACTOR'
        
        if desc_match.group(3):
            mat = desc_match.group(3).upper()
            result['material'] = 'RECYCLING' if mat.startswith('RECYCL') else mat
    
    # Check tonnage for material
    ton_match = STANDARD_WASTE_PATTERNS['tonnage'].search(description)
    if ton_match:
        mat = ton_match.group(1).upper()
        if mat.startswith('RECYCL'):
            result['material'] = 'RECYCLING'
        elif mat == 'TRASH':
            result['material'] = 'MSW'
        else:
            result['material'] = mat
    
    return result


# =============================================================================
# HAMILTON ALLIANCE
# =============================================================================
# Examples:
#   "Disposal Charge - Trash"
#   "Haul Charge Open Top"
#   "Haul Charge 30yd Open Top"
#   "Haul Charge-40yd Open Top"
#   "Haul Charge Compactor"

HAMILTON_ALLIANCE_PATTERNS = {
    # Disposal line: "Disposal Charge - Trash/Concrete/etc"
    'disposal': re.compile(r'Disposal\s+Charge\s*-\s*(Trash|Concrete|C\s*&\s*D|MSW|OCC)', re.IGNORECASE),
    
    # Haul with size: "Haul Charge 30yd Open Top" or "Haul Charge-40yd Open Top"
    'haul_with_size': re.compile(
        r'Haul\s+Charge\s*-?\s*(\d+)\s*yd\s+(Open\s*Top|Compactor)',
        re.IGNORECASE
    ),
    
    # Haul without size: "Haul Charge Open Top" or "Haul Charge Compactor"
    'haul_no_size': re.compile(
        r'Haul\s+Charge\s+(Open\s*Top|Compactor)',
        re.IGNORECASE
    ),
}

def extract_hamilton_alliance(description: str) -> Dict[str, Optional[str]]:
    """Extract fields from Hamilton Alliance line item description."""
    result = {
        'equipment_size': None,
        'equipment_type': None,
        'material': None,
    }
    
    # Check disposal charge for material
    disp_match = HAMILTON_ALLIANCE_PATTERNS['disposal'].search(description)
    if disp_match:
        mat = disp_match.group(1).upper().replace(' ', '')
        if mat == 'TRASH':
            result['material'] = 'MSW'
        elif mat == 'CONCRETE' or mat == 'C&D':
            result['material'] = 'C&D'
        else:
            result['material'] = mat
        return result
    
    # Check haul with size
    haul_size_match = HAMILTON_ALLIANCE_PATTERNS['haul_with_size'].search(description)
    if haul_size_match:
        result['equipment_size'] = f"{haul_size_match.group(1)} YD"
        equip = haul_size_match.group(2).upper().replace(' ', '')
        result['equipment_type'] = 'ROLL OFF' if equip == 'OPENTOP' else 'COMPACTOR'
        return result
    
    # Check haul without size
    haul_match = HAMILTON_ALLIANCE_PATTERNS['haul_no_size'].search(description)
    if haul_match:
        equip = haul_match.group(1).upper().replace(' ', '')
        result['equipment_type'] = 'ROLL OFF' if equip == 'OPENTOP' else 'COMPACTOR'
        return result
    
    return result


# =============================================================================
# CASELLA
# =============================================================================
# Examples:
#   "8YD FL WEEKLY TRASH # P/U: 05"
#   "4YD FL EOW TRASH"
#   "96GL CART EOW ZERO SO"
#   "96GL TOTER WEEKLY MSW"
#   "8YD FL WEEKLY ZERO SO"
#   "40YD REMOVAL"
#   "40YD STR BOX D&R OCC"
#   "6YD FL EXTRA P/U - TRASH"
#   "DISPOSAL-I/C OCC"

CASELLA_PATTERNS = {
    # Front Load: XYD FL [FREQ] [MATERIAL]
    'front_load': re.compile(
        r'(\d+)YD\s+FL\s+(?:WEEKLY|EOW|EXTRA\s*P/U\s*-?\s*)?\s*(TRASH|ZERO\s*SO|MSW|OCC|RECYCL\w*)',
        re.IGNORECASE
    ),
    
    # Cart/Toter: XXGL CART/TOTER [FREQ] [MATERIAL]
    'cart': re.compile(
        r'(\d+)GL\s+(?:CART|TOTER)\s+(?:WEEKLY|EOW|EXTRA\s*P/U\s*-?\s*)?\s*(TRASH|ZERO\s*SO|MSW|OCC|RECYC\w*)',
        re.IGNORECASE
    ),
    
    # Roll-off: XXYD REMOVAL or XXYD STR BOX or XXYD CLOSED TOP (with material at end)
    'rolloff': re.compile(
        r'(\d+)YD\s+(?:REMOVAL|STR\s*BOX[^A-Z]*|CLOSED\s*TOP|TEMP\s*MTH\s*USAGE)[^A-Z]*(TRASH|METAL|OCC|MSW)?',
        re.IGNORECASE
    ),
    
    # STR BOX specifically to capture OCC at end (handles D&R, USAGE, etc in between)
    'str_box': re.compile(r'(\d+)YD\s+STR\s*BOX\s+.*?(OCC|METAL|MSW|TRASH)\b', re.IGNORECASE),
    
    # Disposal line: DISPOSAL-I/C OCC or DISPOSAL [material]
    'disposal': re.compile(r'DISPOSAL[^A-Z]*/?\s*(?:I/C\s*)?(OCC|MSW|TRASH|METAL|RECYCL\w*)', re.IGNORECASE),
}

def extract_casella(description: str) -> Dict[str, Optional[str]]:
    """Extract fields from Casella line item description."""
    result = {
        'equipment_size': None,
        'equipment_type': None,
        'material': None,
    }
    
    # Try front load pattern
    fl_match = CASELLA_PATTERNS['front_load'].search(description)
    if fl_match:
        result['equipment_size'] = f"{fl_match.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
        mat = fl_match.group(2).upper().replace(' ', '')
        if mat == 'ZEROSO':
            result['material'] = 'RECYCLING'
        elif mat == 'TRASH':
            result['material'] = 'MSW'
        else:
            result['material'] = mat
        return result
    
    # Try cart pattern
    cart_match = CASELLA_PATTERNS['cart'].search(description)
    if cart_match:
        result['equipment_size'] = f"{cart_match.group(1)} GAL"
        result['equipment_type'] = 'CART'
        mat = cart_match.group(2).upper().replace(' ', '')
        if mat == 'ZEROSO':
            result['material'] = 'RECYCLING'
        elif mat == 'TRASH':
            result['material'] = 'MSW'
        else:
            result['material'] = mat
        return result
    
    # Try STR BOX pattern specifically (compactor with material)
    str_box_match = CASELLA_PATTERNS['str_box'].search(description)
    if str_box_match:
        result['equipment_size'] = f"{str_box_match.group(1)} YD"
        result['equipment_type'] = 'COMPACTOR'
        result['material'] = str_box_match.group(2).upper()
        return result
    
    # Try roll-off pattern
    ro_match = CASELLA_PATTERNS['rolloff'].search(description)
    if ro_match:
        result['equipment_size'] = f"{ro_match.group(1)} YD"
        # Determine type based on description
        if 'STR BOX' in description.upper():
            result['equipment_type'] = 'COMPACTOR'
        elif 'CLOSED TOP' in description.upper():
            result['equipment_type'] = 'ROLL OFF'
        else:
            result['equipment_type'] = 'ROLL OFF'
        
        if ro_match.group(2):
            mat = ro_match.group(2).upper()
            result['material'] = mat
        return result
    
    # Try disposal pattern for material only
    disp_match = CASELLA_PATTERNS['disposal'].search(description)
    if disp_match:
        mat = disp_match.group(1).upper()
        if mat.startswith('RECYCL'):
            result['material'] = 'RECYCLING'
        elif mat == 'TRASH':
            result['material'] = 'MSW'
        else:
            result['material'] = mat
        return result
    
    return result


# =============================================================================
# WASTE PRO
# =============================================================================
WASTE_PRO_PATTERNS = {
    'frontload': re.compile(r'FRONTLOAD\s+(\d+)\s*YD\s*-\s*(SOLID\s*WASTE|RECYCLE)\s*SERVICE', re.IGNORECASE),
    'cart': re.compile(r'(\d+)\s*Gal\s+Toter\s*-\s*(Solid\s*Waste|Recycl\w*)', re.IGNORECASE),
    'rolloff': re.compile(r'(\d+)\s*YD\s+ROLLOFF\s+HAUL', re.IGNORECASE),
}

def extract_waste_pro(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    fl = WASTE_PRO_PATTERNS['frontload'].search(description)
    if fl:
        result['equipment_size'] = f"{fl.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
        result['material'] = 'MSW' if 'SOLID' in fl.group(2).upper() else 'RECYCLING'
        return result
    cart = WASTE_PRO_PATTERNS['cart'].search(description)
    if cart:
        result['equipment_size'] = f"{cart.group(1)} GAL"
        result['equipment_type'] = 'CART'
        result['material'] = 'MSW' if 'SOLID' in cart.group(2).upper() else 'RECYCLING'
        return result
    ro = WASTE_PRO_PATTERNS['rolloff'].search(description)
    if ro:
        result['equipment_size'] = f"{ro.group(1)} YD"
        result['equipment_type'] = 'ROLL OFF'
        return result
    return result


# =============================================================================
# GFL
# =============================================================================
GFL_PATTERNS = {
    'comm_fl': re.compile(r'COMM\s+FL\s+(?:WASTE|RECYC)\s+PERM\s+(\d+)YD', re.IGNORECASE),
    'cy_fl': re.compile(r'(\d+)\s*CY\s+FRONT\s*LOAD\s+SVC\s*(MSW|RECYCL\w*|TRASH)?', re.IGNORECASE),
    'gallon': re.compile(r'(\d+)\s*GAL\s+(?:RESIDENTIAL|COMMERCIAL)?\s*SVC', re.IGNORECASE),
}

def extract_gfl(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    comm = GFL_PATTERNS['comm_fl'].search(description)
    if comm:
        result['equipment_size'] = f"{comm.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
        result['material'] = 'RECYCLING' if 'RECYC' in description.upper() else 'MSW'
        return result
    cy = GFL_PATTERNS['cy_fl'].search(description)
    if cy:
        result['equipment_size'] = f"{cy.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
        if cy.group(2):
            result['material'] = 'MSW' if cy.group(2).upper() in ('MSW','TRASH') else cy.group(2).upper()
        return result
    gal = GFL_PATTERNS['gallon'].search(description)
    if gal:
        result['equipment_size'] = f"{gal.group(1)} GAL"
        result['equipment_type'] = 'CART'
        return result
    return result


# =============================================================================
# WASTE CONNECTIONS
# =============================================================================
WASTE_CONNECTIONS_PATTERNS = {
    'yard': re.compile(r'(\d+)\s*(?:-)?(\d+)?\s*Y[Dd]\s+(?:(REC|CONT|RECYC|TRASH)?\s*)?(?:\d+\s*X?\s*(?:WK|WEEK))', re.IGNORECASE),
    'gallon': re.compile(r'(\d+)\s*G[Ll]?\s+(?:\d+\s*X?\s*WK)?\s*(?:COM)?\s*\d*', re.IGNORECASE),
}

def extract_waste_connections(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    yd = WASTE_CONNECTIONS_PATTERNS['yard'].search(description)
    if yd:
        size = yd.group(2) if yd.group(2) else yd.group(1)
        result['equipment_size'] = f"{size} YD"
        result['equipment_type'] = 'FRONT LOAD'
        if yd.group(3):
            mat = yd.group(3).upper()
            result['material'] = 'RECYCLING' if mat in ('REC','RECYC') else 'MSW'
        return result
    gl = WASTE_CONNECTIONS_PATTERNS['gallon'].search(description)
    if gl:
        result['equipment_size'] = f"{gl.group(1)} GAL"
        result['equipment_type'] = 'CART'
        if 'REC' in description.upper():
            result['material'] = 'RECYCLING'
        return result
    return result


# =============================================================================
# ANYTIME WASTE
# =============================================================================
ANYTIME_WASTE_PATTERNS = {
    'rolloff': re.compile(r'(\d+)\s*YD\s+Roll\s*Off', re.IGNORECASE),
    'fees': re.compile(r'(?:Disposal|Haul)\s+Fees?\s+(Trash|Cardboard|Recycl\w*|OCC|MSW)', re.IGNORECASE),
}

def extract_anytime_waste(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    ro = ANYTIME_WASTE_PATTERNS['rolloff'].search(description)
    if ro:
        result['equipment_size'] = f"{ro.group(1)} YD"
        result['equipment_type'] = 'ROLL OFF'
        return result
    fee = ANYTIME_WASTE_PATTERNS['fees'].search(description)
    if fee:
        mat = fee.group(1).upper()
        result['material'] = 'MSW' if mat == 'TRASH' else ('OCC' if mat == 'CARDBOARD' else mat)
        return result
    return result


# =============================================================================
# WASTE MANAGEMENT
# =============================================================================
WASTE_MANAGEMENT_PATTERNS = {
    'yards': re.compile(r'(?:Pickup|Container)\s+(?:Service\s+Charge\s+)?(\d+)\s*Yards?\s+(Trash|Recycl\w*|MSW)\s+(DMP|TOT|FEL)', re.IGNORECASE),
    'gallons': re.compile(r'Pickup\s+(\d+)\s*Gallons?\s+(Trash|Recycl\w*|MSW)\s+(TOT|CART)', re.IGNORECASE),
}

def extract_waste_management(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    yd = WASTE_MANAGEMENT_PATTERNS['yards'].search(description)
    if yd:
        result['equipment_size'] = f"{yd.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD' if yd.group(3).upper() in ('DMP','FEL') else 'CART'
        result['material'] = 'MSW' if yd.group(2).upper() == 'TRASH' else yd.group(2).upper()
        return result
    gal = WASTE_MANAGEMENT_PATTERNS['gallons'].search(description)
    if gal:
        result['equipment_size'] = f"{gal.group(1)} GAL"
        result['equipment_type'] = 'CART'
        result['material'] = 'MSW' if gal.group(2).upper() == 'TRASH' else gal.group(2).upper()
        return result
    return result


# =============================================================================
# REPUBLIC SERVICES
# =============================================================================
REPUBLIC_SERVICES_PATTERNS = {
    'container': re.compile(r'(?:Waste|Recycle)\s+(Container|Compactor)\s+(\d+)\s*Cu\s*Yd', re.IGNORECASE),
    'cart': re.compile(r'(?:Mixed\s+Organics|Recycle|Waste)\s+Cart\s+(\d+)/?\d*\s*Gal', re.IGNORECASE),
}

def extract_republic_services(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    cont = REPUBLIC_SERVICES_PATTERNS['container'].search(description)
    if cont:
        result['equipment_size'] = f"{cont.group(2)} YD"
        result['equipment_type'] = 'COMPACTOR' if cont.group(1).upper() == 'COMPACTOR' else 'FRONT LOAD'
        result['material'] = 'RECYCLING' if 'recycle' in description.lower() else 'MSW'
        return result
    cart = REPUBLIC_SERVICES_PATTERNS['cart'].search(description)
    if cart:
        result['equipment_size'] = f"{cart.group(1)} GAL"
        result['equipment_type'] = 'CART'
        if 'organics' in description.lower():
            result['material'] = 'ORGANICS'
        elif 'recycle' in description.lower():
            result['material'] = 'RECYCLING'
        return result
    return result


# =============================================================================
# UNIFIED DISPATCHER
# =============================================================================

def extract_line_item_fields(vendor: str, description: str) -> Dict[str, Optional[str]]:
    """
    Extract equipment_size, equipment_type, material from line item description.
    
    Args:
        vendor: Normalized vendor name
        description: Raw line item description from invoice
    
    Returns:
        Dict with keys: equipment_size, equipment_type, material
    """
    vendor_lower = vendor.lower().strip()
    
    if 'universal waste' in vendor_lower:
        return extract_universal_waste(description)
    elif 'active waste' in vendor_lower:
        return extract_active_waste(description)
    elif 'boren' in vendor_lower:
        return extract_boren_brothers(description)
    elif 'rumpke' in vendor_lower:
        return extract_rumpke(description)
    elif 'cockey' in vendor_lower:
        return extract_cockeys(description)
    elif 'robinson' in vendor_lower:
        return extract_robinson_waste(description)
    elif 'standard waste' in vendor_lower:
        return extract_standard_waste(description)
    elif 'hamilton' in vendor_lower:
        return extract_hamilton_alliance(description)
    elif 'casella' in vendor_lower:
        return extract_casella(description)
    elif 'waste pro' in vendor_lower:
        return extract_waste_pro(description)
    elif 'gfl' in vendor_lower:
        return extract_gfl(description)
    elif 'waste connections' in vendor_lower:
        return extract_waste_connections(description)
    elif 'anytime' in vendor_lower:
        return extract_anytime_waste(description)
    elif 'waste management' in vendor_lower:
        return extract_waste_management(description)
    elif 'republic' in vendor_lower:
        return extract_republic_services(description)
    # Tranche 2 vendors
    elif 'priority waste' in vendor_lower:
        return extract_priority_waste(description)
    elif 'aspen' in vendor_lower:
        return extract_aspen_waste(description)
    elif 'meridian' in vendor_lower:
        return extract_meridian_waste(description)
    elif 'frontier' in vendor_lower:
        return extract_frontier_waste(description)
    elif 'fcc' in vendor_lower:
        return extract_fcc_environmental(description)
    elif 'lrs' in vendor_lower:
        return extract_lrs(description)
    elif 'coastal' in vendor_lower:
        return extract_coastal_waste(description)
    elif 'flood' in vendor_lower:
        return extract_flood_brothers(description)
    elif 'burrtec' in vendor_lower:
        return extract_burrtec(description)
    elif 'win waste' in vendor_lower:
        return extract_win_waste(description)
    elif 'ecosouth' in vendor_lower:
        return extract_ecosouth(description)
    elif 'athens' in vendor_lower:
        return extract_athens_services(description)
    elif 'novak' in vendor_lower:
        return extract_novak_sanitary(description)
    elif 'compactor rentals' in vendor_lower:
        return extract_compactor_rentals(description)
    # Generic fallback for other T2 vendors
    elif any(v in vendor_lower for v in ['alaska', 'eagle', 'papillion', 'ware disposal', 'murreys', 
            'lawrence', 'capital waste', 'american disposal', 'friedman', 'navajo', 'waste zero',
            'liberty waste', 'best way', 'best cleaner', 'smarttrash', 'fusion']):
        return extract_generic_t2(description)
    # Tranche 3 vendors - specific
    elif 'cr&r' in vendor_lower:
        return extract_crr(description)
    elif 'kimble' in vendor_lower:
        return extract_kimble(description)
    elif 'harter' in vendor_lower:
        return extract_harters(description)
    elif 'cri curbside' in vendor_lower or 'cri ' in vendor_lower:
        return extract_cri_curbside(description)
    elif 'rocky ridge' in vendor_lower:
        return extract_rocky_ridge(description)
    elif 'interstate' in vendor_lower:
        return extract_interstate_waste(description)
    elif 'mascaro' in vendor_lower:
        return extract_jp_mascaro(description)
    elif 'nitti' in vendor_lower:
        return extract_nitti(description)
    # T3 generic fallback - covers remaining ~100 vendors
    elif any(v in vendor_lower for v in ['tower', 'american recycl', 'homewood', 'redbox', 'delta waste',
            'sbc waste', 'el harvey', 'walters', 'wasatch', 'empire waste', 'apex', 'edco',
            'specific waste', 'eco-tech', 'boyas', 'my trash', 'panzarella', 'metalpro',
            'idaho falls', 'ram waste', 'las vegas', 'county haul', 'kmg', 'mountain state',
            'howard', 'mark dunning', 'vls', '121 disposal', 'lightning', 'renewable',
            'detroit', 'atlas', 'stevens', 'usa waste', 'aces', 'all american', 'wise',
            'nexus', 'five star', 'knighthorst', 'heartland', 'groot', 'lakeshore',
            'sterling', 'advance', 'cleanway', 'emerald', 'golden', 'green waste',
            'national waste', 'ocean', 'pacific', 'phoenix', 'premier', 'pride',
            'pro waste', 'quality', 'rapid', 'reliable', 'royal', 'select', 'sierra',
            'simple', 'solid', 'southern', 'star', 'suburban', 'summit', 'sun',
            'superior', 'sustainable', 'town', 'tri', 'trinity', 'united', 'universal',
            'valley', 'verde', 'village', 'virgin', 'vision', 'waste away', 'waste ind',
            'western', 'winters', 'woodford', 'zee', 'zero waste']):
        return extract_generic_t3(description)
    else:
        # Ultimate fallback - try generic T3 for any unknown vendor
        return extract_generic_t3(description)


# =============================================================================
# TEST CASES
# =============================================================================

if __name__ == '__main__':
    
    test_cases = [
        # Universal Waste
        ('Universal Waste', '6YD FL Trash'),
        ('Universal Waste', '3YD FL Trash'),
        ('Universal Waste', 'Lock'),
        
        # Active Waste
        ('Active Waste', '2 YD FRONT LOAD TRASH W/ LOCK BAR'),
        ('Active Waste', '95 GALLON RECYCLE SVC - COMMERCIAL'),
        ('Active Waste', '8 YD FRONT LOAD - OCC'),
        ('Active Waste', '8 YD FRONT LOAD RECYCLE'),
        ('Active Waste', '6 YD FRONT LOAD TRASH'),
        ('Active Waste', 'LOCKBAR MONTHLY CHARGE'),
        ('Active Waste', 'DISPOSAL CHARGE - PERMANENT TRASH'),
        ('Active Waste', 'HAUL CHARGE - 40YD ROLL OFF'),
        
        # Boren Brothers
        ('Boren Brothers', '8 YD FRONT LOAD TRASH'),
        ('Boren Brothers', '8 YD FRONT LOAD RECYCLE'),
        ('Boren Brothers', '30YD ROLL OFF - SCRAP METAL'),
        ('Boren Brothers', '30YD ROLL OFF - SCRAP METAL - 1 days of no activity PO: OC081925CL'),
        ('Boren Brothers', 'Compactor Repair - PO OC403336'),
        
        # Rumpke
        ('Rumpke', '8YD FL/MONTH-MSW'),
        ('Rumpke', '8YD FL/MONTH-CRDBD'),
        ('Rumpke', '8YD FL/MONTH-COM MIX'),
        ('Rumpke', '6YD FL/EXTRA-MSW'),
        ('Rumpke', '20YD RO LEASE'),
        ('Rumpke', '20YD RO/LOAD-C&D'),
        ('Rumpke', '40YD RO/LOAD-STEEL'),
        ('Rumpke', 'RO DISP/TON-C&D'),
        ('Rumpke', 'RO DISP/TON-STEEL'),
        ('Rumpke', 'FUEL SURCHARGE FL'),
        ('Rumpke', '20YD ROLL OFF-DELIVER'),
        
        # Cockey's Enterprises
        ("Cockey's Enterprises", 'FL-Comm-Recycling-08yd'),
        ("Cockey's Enterprises", 'FL-Comm-Trash-08yd'),
        ("Cockey's Enterprises", 'FL-Comm-Trash-04yd'),
        ("Cockey's Enterprises", 'RL-Comm-Recycling-95gl'),
        ("Cockey's Enterprises", 'RO Haul Charge - Open Top'),
        ("Cockey's Enterprises", 'RO Haul Charge - Compactor'),
        ("Cockey's Enterprises", 'RODisposal Charge - per Ton'),
        ("Cockey's Enterprises", 'RO - Disposal Charge - per Ton'),
        
        # Robinson Waste
        ('Robinson Waste', 'Serv #001 Front Load Trash - Permanent 1 - 3YD'),
        ('Robinson Waste', 'Serv #001 Front Load Trash - Permanent 1 - 2YD'),
        ('Robinson Waste', '3.00YD Front Load Trash - Permanent'),
        ('Robinson Waste', 'Container Service Fee'),
        
        # Standard Waste
        ('Standard Waste', '30YDRO 30 YARD OPEN TOP'),
        ('Standard Waste', '40YDCO 40 YARD COMPACTOR'),
        ('Standard Waste', '40YDREC 40 YARD COMPACTOR RECYCLING'),
        ('Standard Waste', 'TONS-MSW TONS - MSW (1 TON MIN)'),
        ('Standard Waste', 'TONS-OCC TONS- OCC'),
        ('Standard Waste', 'FUEL SURCHARGE'),
        
        # Hamilton Alliance
        ('Hamilton Alliance', 'Disposal Charge - Trash'),
        ('Hamilton Alliance', 'Haul Charge Open Top'),
        ('Hamilton Alliance', 'Haul Charge 30yd Open Top'),
        ('Hamilton Alliance', 'Haul Charge-40yd Open Top'),
        ('Hamilton Alliance', 'Haul Charge Compactor'),
        
        # Casella
        ('Casella', '8YD FL WEEKLY TRASH # P/U: 05'),
        ('Casella', '4YD FL EOW TRASH'),
        ('Casella', '96GL CART EOW ZERO SO'),
        ('Casella', '8YD FL WEEKLY ZERO SO'),
        ('Casella', '40YD REMOVAL'),
        ('Casella', '40YD STR BOX D&R OCC'),
        ('Casella', '6YD FL EXTRA P/U - TRASH'),
        ('Casella', 'DISPOSAL-I/C OCC'),
        
        # Waste Pro
        ('Waste Pro', 'FRONTLOAD 4 YD - SOLID WASTE SERVICE'),
        ('Waste Pro', 'FRONTLOAD 4 YD - RECYCLE SERVICE'),
        ('Waste Pro', '96 Gal Toter - Solid Waste'),
        ('Waste Pro', '30 YD ROLLOFF HAUL FEE'),
        
        # GFL
        ('GFL', 'COMM FL WASTE PERM 8YD'),
        ('GFL', '02 CY FRONT LOAD SVC MSW'),
        ('GFL', '96 GAL RESIDENTIAL SVC'),
        
        # Waste Connections
        ('Waste Connections', '8 Yd 3X Wk 1'),
        ('Waste Connections', '95 GL 1X WK COM 1'),
        ('Waste Connections', '1-3YD REC 2 X WEEKLY'),
        ('Waste Connections', '1-3YD CONT 2 X WEEKLY'),
        
        # Anytime Waste
        ('Anytime Waste', 'Disposal Fees Trash'),
        ('Anytime Waste', 'Switch Out 20 YD Roll Off'),
        ('Anytime Waste', 'Haul Fees Cardboard'),
        
        # Waste Management
        ('Waste Management', 'Pickup 1 Yards Trash DMP Weekly x1'),
        ('Waste Management', 'Pickup 96 Gallons Trash TOT Weekly x2'),
        
        # Republic Services
        ('Republic Services', '1 Waste Container 2 Cu Yd, 1 Lift Per Week'),
        ('Republic Services', '1 Waste Compactor 40 Cu Yd, On Call Service'),
        ('Republic Services', '1 Recycle Cart 95/96 Gal, 1 Lift Per Week'),
    ]
    
    print("=" * 80)
    print("LINE ITEM EXTRACTION TEST RESULTS")
    print("=" * 80)
    
    for vendor, desc in test_cases:
        result = extract_line_item_fields(vendor, desc)
        print(f"\nVendor: {vendor}")
        print(f"Input:  {desc}")
        print(f"Output: size={result['equipment_size']}, type={result['equipment_type']}, material={result['material']}")


# =============================================================================
# TRANCHE 2 VENDORS
# =============================================================================

# Priority Waste: "Monthly Waste Service XX YD [MATERIAL] Front Load"
def extract_priority_waste(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'Monthly\s+(?:Waste|Recycl\w*)\s+Service\s+(\d+)\s*YD.*?(TRASH|MSW|Cardboard|Paper|Recycl)', description, re.I)
    if m:
        result['equipment_size'] = f"{m.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
        mat = m.group(2).upper()
        result['material'] = 'OCC' if mat in ('CARDBOARD','PAPER') else ('MSW' if mat in ('TRASH','MSW') else 'RECYCLING')
    return result

# Aspen Waste: "40YD D&R - DEMO", "MONTHLY WASTE DISPOSAL"
def extract_aspen_waste(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(\d+)YD\s+D&R', description, re.I)
    if m:
        result['equipment_size'] = f"{m.group(1)} YD"
        result['equipment_type'] = 'ROLL OFF'
        return result
    if re.search(r'MONTHLY\s+WASTE\s+DISPOSAL', description, re.I):
        result['material'] = 'MSW'
    elif re.search(r'MONTHLY\s+RECYCLING', description, re.I):
        result['material'] = 'RECYCLING'
    return result

# Meridian Waste: "2YD FEL TRASH EOW", "40YD ROL COMPACTOR HAUL"
def extract_meridian_waste(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    fel = re.search(r'(\d+)YD\s+FEL\s*(TRASH|RECYC|OCC)?', description, re.I)
    if fel:
        result['equipment_size'] = f"{fel.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
        if fel.group(2):
            result['material'] = 'MSW' if fel.group(2).upper() == 'TRASH' else fel.group(2).upper()
        return result
    rol = re.search(r'(\d+)YD\s+ROL\s*(COMPACTOR)?', description, re.I)
    if rol:
        result['equipment_size'] = f"{rol.group(1)} YD"
        result['equipment_type'] = 'COMPACTOR' if rol.group(2) else 'ROLL OFF'
    return result

# Frontier Waste: "02 Yard FL Trash Service", "Roll Off Haul/Disposal"
def extract_frontier_waste(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    fl = re.search(r'(\d+)\s*Yard\s+FL\s+(Trash|Recycl)', description, re.I)
    if fl:
        result['equipment_size'] = f"{int(fl.group(1))} YD"
        result['equipment_type'] = 'FRONT LOAD'
        result['material'] = 'MSW' if fl.group(2).upper() == 'TRASH' else 'RECYCLING'
        return result
    if re.search(r'Roll\s*Off\s+Haul', description, re.I):
        result['equipment_type'] = 'ROLL OFF'
    elif re.search(r'Roll\s*Off\s+Disposal', description, re.I):
        result['equipment_type'] = 'ROLL OFF'
    return result

# FCC Environmental: "Comm. FLMSW Dumpster - X Yard", "X Yard Front Load - MSW"
def extract_fcc_environmental(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(\d+)\s*Yard\s+Front\s*Load\s*-?\s*(MSW|Trash|Recycl)?', description, re.I)
    if m:
        result['equipment_size'] = f"{m.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
        if m.group(2):
            result['material'] = 'MSW' if m.group(2).upper() in ('MSW','TRASH') else 'RECYCLING'
        return result
    m2 = re.search(r'Dumpster\s*-\s*(\d+)\s*Yard', description, re.I)
    if m2:
        result['equipment_size'] = f"{m2.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
    if 'MSW' in description.upper() or 'FLMSW' in description.upper():
        result['material'] = 'MSW'
    return result

# LRS: "Xct COMML FL TRASH"
def extract_lrs(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    if re.search(r'COMML\s+FL\s+(TRASH|RECYCL)', description, re.I):
        result['equipment_type'] = 'FRONT LOAD'
        result['material'] = 'MSW' if 'TRASH' in description.upper() else 'RECYCLING'
    return result

# Coastal Waste: "FRONT END MSW 1 - XYD", "FEL MSW 1 - XYD"
def extract_coastal_waste(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(?:FRONT\s*END|FEL)\s*(MSW|OCC|RECYC)?\s*\d?\s*-?\s*(\d+)YD', description, re.I)
    if m:
        result['equipment_type'] = 'FRONT LOAD'
        if m.group(2):
            result['equipment_size'] = f"{m.group(2)} YD"
        if m.group(1):
            result['material'] = m.group(1).upper()
    return result

# Flood Brothers: "XYD TRASH SERVICE"
def extract_flood_brothers(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(\d+)YD\s+(TRASH|RECYCL\w*)\s+SERVICE', description, re.I)
    if m:
        result['equipment_size'] = f"{m.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
        result['material'] = 'MSW' if m.group(2).upper() == 'TRASH' else 'RECYCLING'
    return result

# Burrtec: "TRASH SERVICE X.X YD-XX"
def extract_burrtec(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(TRASH|RECYCL\w*)\s+SERVICE.*?(\d+(?:\.\d+)?)\s*YD', description, re.I)
    if m:
        result['material'] = 'MSW' if m.group(1).upper() == 'TRASH' else 'RECYCLING'
        result['equipment_size'] = f"{int(float(m.group(2)))} YD"
        result['equipment_type'] = 'FRONT LOAD'
    return result

# Win Waste: "Comm - FEL - MSW - XXYd"
def extract_win_waste(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(?:Comm\s*-\s*)?FEL\s*-\s*(MSW|OCC|Recycl\w*)\s*-?\s*(\d+)Y[Dd]?', description, re.I)
    if m:
        result['equipment_type'] = 'FRONT LOAD'
        result['material'] = m.group(1).upper()
        result['equipment_size'] = f"{m.group(2)} YD"
        return result
    ro = re.search(r'Roll[- ]?Off.*?(\d+)Y[Dd]', description, re.I)
    if ro:
        result['equipment_type'] = 'ROLL OFF'
        result['equipment_size'] = f"{ro.group(1)} YD"
    return result

# EcoSouth: "XX YD Front Load, MSW"
def extract_ecosouth(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(\d+)\s*YD\s+Front\s*Load.*?(MSW|Trash|Recycl)', description, re.I)
    if m:
        result['equipment_size'] = f"{m.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
        result['material'] = 'MSW' if m.group(2).upper() in ('MSW','TRASH') else 'RECYCLING'
    return result

# Athens Services: "XYD S/W & RECY"
def extract_athens_services(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(\d+)YD\s+(?:S/W|TRASH|RECYC)', description, re.I)
    if m:
        result['equipment_size'] = f"{m.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
        result['material'] = 'MSW' if 'S/W' in description.upper() or 'TRASH' in description.upper() else 'RECYCLING'
    return result

# Novak Sanitary (Waste Connections): "FL TRASH/CARDBOARD SERVICE"
def extract_novak_sanitary(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    if re.search(r'FL\s+(TRASH|CARDBOARD|RECYCL)', description, re.I):
        result['equipment_type'] = 'FRONT LOAD'
        if 'TRASH' in description.upper():
            result['material'] = 'MSW'
        elif 'CARDBOARD' in description.upper():
            result['material'] = 'OCC'
        else:
            result['material'] = 'RECYCLING'
    return result

# Compactor Rentals: "XX CY SC COMPACTOR"
def extract_compactor_rentals(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(\d+)\s*CY\s+(?:SC\s+)?COMPACTOR', description, re.I)
    if m:
        result['equipment_size'] = f"{m.group(1)} YD"
        result['equipment_type'] = 'COMPACTOR'
    return result

# Generic fallback for simple patterns
def extract_generic_t2(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    # Try size + YD pattern
    size = re.search(r'(\d+)\s*(?:YD|YARD|CY)', description, re.I)
    if size:
        result['equipment_size'] = f"{size.group(1)} YD"
    # Try equipment type
    if re.search(r'FRONT\s*LOAD|FEL|FL\b', description, re.I):
        result['equipment_type'] = 'FRONT LOAD'
    elif re.search(r'ROLL\s*OFF|RO\b', description, re.I):
        result['equipment_type'] = 'ROLL OFF'
    elif re.search(r'COMPACTOR', description, re.I):
        result['equipment_type'] = 'COMPACTOR'
    # Try material
    if re.search(r'\bTRASH\b|\bMSW\b|WASTE', description, re.I):
        result['material'] = 'MSW'
    elif re.search(r'RECYCL|OCC|CARDBOARD', description, re.I):
        result['material'] = 'RECYCLING' if 'RECYCL' in description.upper() else 'OCC'
    return result


# =============================================================================
# TRANCHE 3 VENDORS - Enhanced Generic + Specific
# =============================================================================

# CR&R: "6YD COMMERCIAL BIN # P/U: 3", "6YD MIXED RECYCLE BIN"
def extract_crr(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(\d+)YD\s+(?:COMMERCIAL\s+)?(?:BIN|MIXED\s+RECYCLE)', description, re.I)
    if m:
        result['equipment_size'] = f"{m.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
        result['material'] = 'RECYCLING' if 'RECYCLE' in description.upper() else 'MSW'
    elif re.search(r'(\d+)G\s+COMM\s+ORGANIC', description, re.I):
        result['equipment_type'] = 'CART'
        result['material'] = 'ORGANICS'
    return result

# Kimble: Similar to Waste Connections format
def extract_kimble(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(\d+)\s*(?:YD|YARD|CY)', description, re.I)
    if m:
        result['equipment_size'] = f"{m.group(1)} YD"
    if re.search(r'FRONT\s*LOAD|FL\b|FEL|FE\b', description, re.I):
        result['equipment_type'] = 'FRONT LOAD'
    elif re.search(r'ROLL\s*OFF|RO\b', description, re.I):
        result['equipment_type'] = 'ROLL OFF'
    if re.search(r'TRASH|WASTE|MSW', description, re.I):
        result['material'] = 'MSW'
    elif re.search(r'RECYCL|OCC|CARDBOARD', description, re.I):
        result['material'] = 'RECYCLING' if 'RECYCL' in description.upper() else 'OCC'
    return result

# Harter's: "95G TRASH SERVICE"
def extract_harters(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(\d+)G\s+(TRASH|RECYCL)', description, re.I)
    if m:
        result['equipment_size'] = f"{m.group(1)} GAL"
        result['equipment_type'] = 'CART'
        result['material'] = 'MSW' if m.group(2).upper() == 'TRASH' else 'RECYCLING'
        return result
    m2 = re.search(r'(\d+)\s*(?:YD|YARD)', description, re.I)
    if m2:
        result['equipment_size'] = f"{m2.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
    return result

# CRI Curbside: "30 YARD CONTAINER"
def extract_cri_curbside(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(\d+)\s*YARD\s+CONTAINER', description, re.I)
    if m:
        result['equipment_size'] = f"{m.group(1)} YD"
        result['equipment_type'] = 'ROLL OFF'
    if 'TRASH' in description.upper():
        result['material'] = 'MSW'
    return result

# Rocky Ridge: "3 yd Front Loader"
def extract_rocky_ridge(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(\d+)\s*(?:yd|yard)\s+Front\s*Load', description, re.I)
    if m:
        result['equipment_size'] = f"{m.group(1)} YD"
        result['equipment_type'] = 'FRONT LOAD'
    return result

# Interstate Waste: Standard format
def extract_interstate_waste(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'(\d+)\s*(?:YD|YARD|CU\s*YD)', description, re.I)
    if m:
        result['equipment_size'] = f"{m.group(1)} YD"
    if re.search(r'FRONT|FEL|FL\b', description, re.I):
        result['equipment_type'] = 'FRONT LOAD'
    elif re.search(r'ROLL|RO\b', description, re.I):
        result['equipment_type'] = 'ROLL OFF'
    if re.search(r'TRASH|WASTE|MSW', description, re.I):
        result['material'] = 'MSW'
    elif re.search(r'RECYCL', description, re.I):
        result['material'] = 'RECYCLING'
    return result

# JP Mascaro: "FE - WASTE 1 - 2YD"
def extract_jp_mascaro(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'FE\s*-\s*(WASTE|RECYCL)\s*\d*\s*-\s*(\d+)YD', description, re.I)
    if m:
        result['equipment_type'] = 'FRONT LOAD'
        result['material'] = 'MSW' if m.group(1).upper() == 'WASTE' else 'RECYCLING'
        result['equipment_size'] = f"{m.group(2)} YD"
    return result

# Nitti: "Commercial Front Load Trash 1 - 3YD"
def extract_nitti(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    m = re.search(r'Front\s*Load\s*(Trash|Recycl\w*).*?(\d+)YD', description, re.I)
    if m:
        result['equipment_type'] = 'FRONT LOAD'
        result['material'] = 'MSW' if m.group(1).upper() == 'TRASH' else 'RECYCLING'
        result['equipment_size'] = f"{m.group(2)} YD"
    return result

# Enhanced generic for T3 - handles most common patterns
def extract_generic_t3(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    
    # Size patterns - try multiple formats
    size_patterns = [
        r'(\d+)\s*(?:YD|YARD|CY|CU\s*YD)',  # 6YD, 6 YARD, 6CY
        r'(\d+)\s*(?:GAL|GALLON|G)\b',       # 96GAL, 96G
        r'-\s*(\d+)YD',                       # - 6YD
        r'(\d+)\s*yd\s+',                     # 6 yd
        r'(\d+)\s*(?:Cu|Cubic)\s*(?:Yd|Yard)', # 6 Cu Yd
        r'#\s*P/U.*?(\d+)YD',                 # # P/U: 1 ... 6YD
    ]
    for pat in size_patterns:
        m = re.search(pat, description, re.I)
        if m:
            val = m.group(1)
            if 'GAL' in description.upper() or 'GALLON' in description.upper():
                result['equipment_size'] = f"{val} GAL"
            elif int(val) >= 30 and int(val) <= 96 and not re.search(r'YD|YARD|CY', description, re.I):
                result['equipment_size'] = f"{val} GAL"
            else:
                result['equipment_size'] = f"{val} YD"
            break
    
    # Equipment type - broader patterns
    if re.search(r'FRONT\s*LOAD|FEL\b|FL\b|FE\b|F/L|DUMPSTER|BIN|COMMERCIAL\s+BIN', description, re.I):
        result['equipment_type'] = 'FRONT LOAD'
    elif re.search(r'ROLL\s*OFF|RO\b|R/O|CONTAINER.*YARD|OPEN\s*TOP|HAUL.*\d+\s*Y', description, re.I):
        result['equipment_type'] = 'ROLL OFF'
    elif re.search(r'COMPACTOR', description, re.I):
        result['equipment_type'] = 'COMPACTOR'
    elif re.search(r'CART|TOTER|TOTE\b|CAN\b|\d+G\b', description, re.I):
        result['equipment_type'] = 'CART'
    elif result['equipment_size']:
        # Default based on size if nothing else matches
        size_val = int(re.search(r'\d+', result['equipment_size']).group())
        if size_val <= 10:
            result['equipment_type'] = 'FRONT LOAD'
        elif size_val >= 15 and size_val <= 50:
            result['equipment_type'] = 'ROLL OFF'
    
    # Material - broader patterns
    if re.search(r'\bTRASH\b|\bMSW\b|\bWASTE\b(?!\s*ZERO)|\bSOLID\b|\bS/W\b|REFUSE', description, re.I):
        result['material'] = 'MSW'
    elif re.search(r'\bOCC\b|\bCARDBOARD\b|\bPAPER\b', description, re.I):
        result['material'] = 'OCC'
    elif re.search(r'\bRECYCL', description, re.I):
        result['material'] = 'RECYCLING'
    elif re.search(r'\bORGANIC\b|\bFOOD\b|\bCOMPOST\b', description, re.I):
        result['material'] = 'ORGANICS'
    elif re.search(r'\bMETAL\b|\bSCRAP\b|\bSTEEL\b', description, re.I):
        result['material'] = 'METAL'
    elif re.search(r'\bC\s*&\s*D\b|\bDEMO\b|\bCONSTRUCTION\b', description, re.I):
        result['material'] = 'C&D'
    
    return result
