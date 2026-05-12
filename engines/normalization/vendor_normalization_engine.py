"""
Vendor Normalization Engine
===========================
Maps extracted vendor names (from vendor_detection_module) to normalized 
database vendor names (from services/billing tables in Wasteology database).

Usage:
    from vendor_normalization_engine import VendorNormalizer
    
    normalizer = VendorNormalizer()
    
    # Get database patterns for a detected vendor
    db_patterns = normalizer.get_db_patterns("Waste Connections")
    # Returns: ['Waste Connections%', 'WASTE CONNECTIONS%']
    
    # Get canonical name
    canonical = normalizer.get_canonical_name("Republic Services")
    # Returns: 'Republic Services'
    
    # Match a database vendor name to detected vendor
    detected = normalizer.match_db_vendor("Waste Connections - Tennessee 6032")
    # Returns: 'Waste Connections'
"""

import re
from typing import Optional, List, Dict, Tuple


# =============================================================================
# VENDOR NORMALIZATION MAPPING
# =============================================================================
# Format: detected_vendor -> (canonical_name, [db_pattern_prefixes], [exact_matches])
#
# db_pattern_prefixes: Used for LIKE queries (e.g., "Waste Connections%")
# exact_matches: Specific database names that don't follow the pattern
# =============================================================================

VENDOR_MAPPING: Dict[str, Tuple[str, List[str], List[str]]] = {
    
    # =========================================================================
    # TIER 1: MAJOR NATIONAL HAULERS (35,000+ invoices combined)
    # =========================================================================
    
    "Waste Connections": (
        "Waste Connections",
        ["Waste Connections", "WASTE CONNECTIONS"],
        []
    ),
    
    "Republic Services": (
        "Republic Services",
        ["Republic Services", "REPUBLIC SERVICES"],
        []
    ),
    
    "Waste Management": (
        "Waste Management",
        ["Waste Management", "WASTE MANAGEMENT", "WM "],
        ["Waste Management - National"]
    ),
    
    "GFL": (
        "GFL Environmental",
        ["GFL", "GFL Environmental"],
        []
    ),
    
    # =========================================================================
    # TIER 2: LARGE REGIONAL HAULERS (1,000+ invoices)
    # =========================================================================
    
    "Anytime Waste": (
        "Anytime Waste Systems",
        ["Anytime Waste", "ANYTIME WASTE"],
        ["ANYTIME WASTE SYSTEMS"]
    ),
    
    "Rumpke": (
        "Rumpke",
        ["Rumpke", "RUMPKE"],
        []
    ),
    
    "Waste Pro": (
        "Waste Pro",
        ["Waste Pro", "WASTE PRO"],
        []
    ),
    
    "Cockey's Enterprises": (
        "Cockey's Enterprises",
        ["Cockey", "COCKEY"],
        ["COCKEY'S ENTERPRISES"]
    ),
    
    "Universal Waste": (
        "Universal Waste Systems",
        ["Universal Waste", "UNIVERSAL WASTE"],
        ["UNIVERSAL WASTE SYSTEMS"]
    ),
    
    "Robinson Waste": (
        "Robinson Waste Services",
        ["Robinson Waste", "ROBINSON WASTE"],
        ["Robinson Waste Services-Utah", "Robinson Waste Disposal Svc"]
    ),
    
    "Standard Waste": (
        "Standard Waste Services",
        ["Standard Waste", "STANDARD WASTE"],
        ["STANDARD WASTE SERVICES"]
    ),
    
    "Hamilton Alliance": (
        "Hamilton Alliance",
        ["Hamilton Alliance", "HAMILTON ALLIANCE"],
        []
    ),
    
    "Active Waste": (
        "Active Waste Solutions",
        ["Active Waste", "ACTIVE WASTE"],
        ["Active Waste Solutions"]
    ),
    
    "Casella": (
        "Casella Waste Systems",
        ["Casella", "CASELLA"],
        ["CASELLA WASTE SYSTEMS", "Casella - National", "Casella Major Accounts Services LLC"]
    ),
    
    "Boren Brothers": (
        "Boren Brothers LLC",
        ["Boren Brothers", "BOREN BROTHERS"],
        ["Boren Brothers LLC"]
    ),
    
    "Priority Waste": (
        "Priority Waste",
        ["Priority Waste", "PRIORITY WASTE"],
        ["Priority Waste MI", "Priority Waste IN", "Priority Waste TN"]
    ),
    
    "Aspen Waste": (
        "Aspen Waste Systems",
        ["Aspen Waste", "ASPEN WASTE"],
        ["Aspen Waste Systems Inc", "Aspen Waste Systems of Missouri"]
    ),
    
    "Meridian Waste": (
        "Meridian Waste",
        ["Meridian Waste", "MERIDIAN WASTE"],
        ["MERIDIAN WASTE", "MERIDIAN WASTE FLORIDA", "Meridian Waste-Georgia", 
         "Meridian Waste-Knoxville Hauling", "Meridian Waste-North Carolina",
         "Meridian Waste-Virginia", "Meridian Waste - Eco Waste Services",
         "Meridian Waste - Huntsville Hauling"]
    ),
    
    # =========================================================================
    # TIER 3: MID-SIZE REGIONAL HAULERS (300-999 invoices)
    # =========================================================================
    
    "Best Cleaner": (
        "Best Cleaner Disposal",
        ["Best Cleaner", "BEST CLEANER"],
        ["Best Cleaner Disposal"]
    ),
    
    "Frontier Waste": (
        "Frontier Waste",
        ["Frontier Waste", "FRONTIER WASTE"],
        ["Frontier Waste", "Frontier Waste - Austin", "Frontier Waste - McKinney",
         "Frontier Waste - San Antonio", "Frontier Waste -Dayton"]
    ),
    
    "FCC Environmental": (
        "FCC Environmental Services",
        ["FCC Environmental", "FCC ENVIRONMENTAL"],
        ["FCC Environmental Services", "Houston Waste Services - FCC Environmental"]
    ),
    
    "SmartTrash": (
        "SmartTrash",
        ["SmartTrash", "SMARTTRASH", "Smart Trash"],
        []
    ),
    
    "Fusion Waste": (
        "Fusion Waste",
        ["Fusion Waste", "FUSION WASTE", "Fusion Site"],
        ["Fusion Waste", "Fusion Site Tennessee"]
    ),
    
    "LRS": (
        "LRS",
        ["LRS"],
        ["LRS", "LRS - Jackson Disposal", "LRS - Wisconsin"]
    ),
    
    "Coastal Waste": (
        "Coastal Waste & Recycling",
        ["Coastal Waste", "COASTAL WASTE"],
        ["Coastal Waste & Recycling", "Coastal Waste Services", "Coastal Waste Landfill"]
    ),
    
    "Flood Brothers": (
        "Flood Brothers",
        ["Flood Brothers", "FLOOD BROTHERS"],
        []
    ),
    
    "Alaska Waste": (
        "Alaska Waste",
        ["Alaska Waste", "ALASKA WASTE", "Waste Connections - Alaska Waste"],
        []
    ),
    
    "Eagle Disposal": (
        "Eagle Disposal",
        ["Eagle Disposal", "EAGLE DISPOSAL"],
        []
    ),
    
    "Papillion Sanitation": (
        "Papillion Sanitation",
        ["Papillion", "PAPILLION", "Waste Connections - Papillion"],
        ["Waste Connections - Papillion Sanitation 3050"]
    ),
    
    "Ware Disposal": (
        "Ware Disposal",
        ["Ware Disposal", "WARE DISPOSAL"],
        []
    ),
    
    "Murreys Disposal": (
        "Murreys Disposal",
        ["Murreys", "MURREYS", "Murrey"],
        []
    ),
    
    "Lawrence Waste": (
        "Lawrence Waste Services Corp",
        ["Lawrence Waste", "LAWRENCE WASTE"],
        ["LAWRENCE WASTE SERVICES CORP"]
    ),
    
    "Capital Waste": (
        "Capital Waste",
        ["Capital Waste", "CAPITAL WASTE"],
        []
    ),
    
    "American Disposal": (
        "American Disposal",
        ["American Disposal", "AMERICAN DISPOSAL"],
        ["American Disposal Systems-PA", "Waste Connections - American Disposal"]
    ),
    
    "Burrtec": (
        "Burrtec Waste Industries",
        ["Burrtec", "BURRTEC"],
        ["Burrtec Waste-Jurupa Valley-Riverside", "Burrtec Waste Industries"]
    ),
    
    "Friedman Recycling": (
        "Friedman's Recycling",
        ["Friedman", "FRIEDMAN"],
        ["Friedman's Recycling"]
    ),
    
    "Navajo Sanitation": (
        "Navajo Sanitation",
        ["Navajo", "NAVAJO"],
        []
    ),
    
    "Waste Zero": (
        "Waste Zero",
        ["Waste Zero", "WASTE ZERO"],
        []
    ),
    
    "Novak Sanitary": (
        "Novak Sanitary Service",
        ["Novak", "NOVAK", "Waste Connections - Novak"],
        ["Waste Connections - Novak Sanitary Service 3031"]
    ),
    
    "Liberty Waste": (
        "Liberty Waste Solutions",
        ["Liberty Waste", "LIBERTY WASTE"],
        ["Liberty Waste Solutions"]
    ),
    
    "Win Waste": (
        "Win Waste Innovations",
        ["Win Waste", "WIN WASTE"],
        ["WIN WASTE INNOVATIONS"]
    ),
    
    "Best Way Disposal": (
        "Best Way Disposal",
        ["Best Way", "BEST WAY", "Bestway"],
        ["Best Way - Burlington"]
    ),
    
    "EcoSouth": (
        "EcoSouth",
        ["EcoSouth", "ECOSOUTH", "Eco South"],
        []
    ),
    
    "Athens Services": (
        "Athens Services",
        ["Athens", "ATHENS"],
        ["Athens Services"]
    ),
    
    "Compactor Rentals of America": (
        "Compactor Rentals of America",
        ["Compactor Rentals", "COMPACTOR RENTALS", "CRA"],
        []
    ),
    
    # =========================================================================
    # TIER 4: SMALLER REGIONAL HAULERS (100-299 invoices)
    # =========================================================================
    
    "Tower Compactor": (
        "Tower Compactor Rental",
        ["Tower Compactor", "TOWER COMPACTOR"],
        ["TOWER COMPACTOR RENTAL"]
    ),
    
    "American Recycling": (
        "American Recycling",
        ["American Recycling", "AMERICAN RECYCLING"],
        []
    ),
    
    "Homewood Disposal": (
        "Homewood Disposal Service",
        ["Homewood", "HOMEWOOD"],
        ["Homewood Disposal Service"]
    ),
    
    "CR&R": (
        "CR&R Inc Environmental Services",
        ["CR&R", "CR & R"],
        ["CR&R Inc Environmental Services"]
    ),
    
    "Kimble": (
        "Kimble Companies",
        ["Kimble", "KIMBLE"],
        ["Kimble Companies"]
    ),
    
    "Harter's": (
        "Harter's Fox Valley Disposal",
        ["Harter", "HARTER"],
        ["Harter's Fox Valley Disposal"]
    ),
    
    "Redbox+": (
        "Redbox+",
        ["Redbox", "REDBOX", "Red Box"],
        []
    ),
    
    "CRI Curbside": (
        "CRI-Curbside Rolloff Inc",
        ["CRI", "Curbside Rolloff"],
        ["CRI-Curbside Rolloff Inc"]
    ),
    
    "Delta Waste": (
        "Delta Waste Solutions",
        ["Delta Waste", "DELTA WASTE"],
        ["Delta Waste Solutions"]
    ),
    
    "Rocky Ridge": (
        "Rocky Ridge",
        ["Rocky Ridge", "ROCKY RIDGE"],
        []
    ),
    
    "SBC Waste": (
        "SBC Waste Solutions Inc",
        ["SBC", "SBC Waste"],
        ["SBC Waste Solutions Inc"]
    ),
    
    "Interstate Waste": (
        "Interstate Waste Services",
        ["Interstate Waste", "INTERSTATE WASTE"],
        ["Interstate Waste Services"]
    ),
    
    "National Equipment Solutions": (
        "National Equipment Solutions",
        ["National Equipment", "NATIONAL EQUIPMENT"],
        []
    ),
    
    "EL Harvey": (
        "EL Harvey",
        ["EL Harvey", "E.L. Harvey", "E L Harvey"],
        []
    ),
    
    "Walters Recycling": (
        "Walter's Recycling & Refuse",
        ["Walter", "WALTER"],
        ["Walter's Recycling & Refuse"]
    ),
    
    "Specific Waste": (
        "Specific Waste",
        ["Specific Waste", "SPECIFIC WASTE"],
        []
    ),
    
    "Wasatch Waste": (
        "Wasatch Waste",
        ["Wasatch", "WASATCH"],
        ["Wasatch Integrated Waste Management District"]
    ),
    
    "Empire Waste": (
        "Empire Waste",
        ["Empire Waste", "EMPIRE WASTE"],
        []
    ),
    
    "Apex Waste": (
        "Apex Waste",
        ["Apex Waste", "APEX WASTE"],
        []
    ),
    
    "JP Mascaro": (
        "J.P. Mascaro",
        ["Mascaro", "MASCARO", "J.P. Mascaro", "JP Mascaro"],
        ["J.P. Mascaro"]
    ),
    
    "Huntsville Hauling": (
        "Meridian Waste - Huntsville Hauling",
        ["Huntsville Hauling", "HUNTSVILLE HAULING"],
        ["Meridian Waste - Huntsville Hauling"]
    ),
    
    "Eco-Tech": (
        "Ecotech",
        ["Eco-Tech", "Ecotech", "ECOTECH", "ECO-TECH"],
        ["Ecotech"]
    ),
    
    "Boyas Recycling": (
        "Boyas Recycling",
        ["Boyas", "BOYAS"],
        []
    ),
    
    "My Trash": (
        "My Trash",
        ["My Trash", "MY TRASH"],
        []
    ),
    
    "Panzarella Waste": (
        "Panzarella Waste & Recycling Services",
        ["Panzarella", "PANZARELLA"],
        ["Panzarella Waste & Recycling Services"]
    ),
    
    "EDCO Disposal": (
        "EDCO Waste & Recycling Services",
        ["EDCO", "E.D.C.O."],
        ["EDCO WASTE & RECYCLING SERVICES"]
    ),
    
    "Metalpro": (
        "Metalpro",
        ["Metalpro", "METALPRO", "Metal Pro"],
        []
    ),
    
    "Idaho Falls Utilities": (
        "Idaho Falls Utilities",
        ["Idaho Falls", "IDAHO FALLS"],
        []
    ),
    
    "RAM Waste": (
        "RAM Waste",
        ["RAM Waste", "RAM WASTE"],
        []
    ),
    
    "Las Vegas Recycling": (
        "Las Vegas Recycling",
        ["Las Vegas Recycling", "LAS VEGAS RECYCLING"],
        []
    ),
    
    "County Hauling": (
        "County Hauling",
        ["County Hauling", "COUNTY HAULING"],
        []
    ),
    
    "Nitti Sanitation": (
        "Nitti Sanitation",
        ["Nitti", "NITTI"],
        ["NITTI SANITATION"]
    ),
    
    "KMG Hauling": (
        "KMG Hauling Inc",
        ["KMG", "KMG Hauling"],
        ["KMG HAULING INC"]
    ),
    
    "Mountain State Waste": (
        "Mountain State Waste",
        ["Mountain State", "MOUNTAIN STATE"],
        []
    ),
    
    "Howard Disposal": (
        "Howard Disposal",
        ["Howard Disposal", "HOWARD DISPOSAL"],
        []
    ),
    
    "Mark Dunning": (
        "MDI - Mark Dunning Industries Inc",
        ["Mark Dunning", "MDI", "MARK DUNNING"],
        ["MDI - Mark Dunning Industries Inc"]
    ),
    
    "VLS Environmental": (
        "VLS Environmental Solutions",
        ["VLS", "VLS Environmental"],
        ["VLS Environmental Solutions"]
    ),
    
    "Lightning Disposal": (
        "Lightning Disposal Inc",
        ["Lightning", "LIGHTNING"],
        ["Lightning Disposal Inc"]
    ),
    
    "121 Disposal": (
        "121 Disposal",
        ["121 Disposal", "121 DISPOSAL"],
        []
    ),
    
    "Renewable Resources": (
        "Renewable Resources",
        ["Renewable Resources", "RENEWABLE RESOURCES"],
        []
    ),
    
    "Detroit Disposal": (
        "Detroit Disposal",
        ["Detroit Disposal", "DETROIT DISPOSAL"],
        []
    ),
    
    "Atlas Disposal": (
        "Atlas Disposal",
        ["Atlas Disposal", "ATLAS DISPOSAL"],
        []
    ),
    
    "Stevens Disposal": (
        "Stevens Disposal",
        ["Stevens Disposal", "STEVENS DISPOSAL"],
        []
    ),
    
    "USA Waste": (
        "USA Waste & Recycling",
        ["USA Waste", "USA WASTE"],
        ["USA Waste & Recycling"]
    ),
    
    "ACES Disposal": (
        "ACES Disposal",
        ["ACES", "Ace Disposal", "ACE Recycling"],
        ["ACE RECYCLING AND DISPOSAL"]
    ),
    
    "Wise Environmental": (
        "Wise Environmental",
        ["Wise Environmental", "WISE ENVIRONMENTAL"],
        []
    ),
    
    "All American Waste": (
        "All American Waste",
        ["All American", "ALL AMERICAN"],
        []
    ),
    
    "Nexus Disposal": (
        "Nexus Disposal",
        ["Nexus", "NEXUS"],
        ["Nexus Disposal"]
    ),
    
    "Five Star Waste": (
        "Five Star Waste",
        ["Five Star", "FIVE STAR"],
        []
    ),
    
    "RDT Inc": (
        "RDT Inc",
        ["RDT", "R.D.T."],
        []
    ),
    
    "KnightHorst": (
        "KnightHorst",
        ["KnightHorst", "KNIGHTHORST", "Knight Horst"],
        []
    ),
    
    "All Waste": (
        "All Waste Inc",
        ["All Waste", "ALL WASTE"],
        ["All Waste Inc"]
    ),
    
    "Trash Taxi": (
        "Trash Taxi",
        ["Trash Taxi", "TRASH TAXI"],
        []
    ),
    
    "Patriot Waste": (
        "Patriot Disposal",
        ["Patriot", "PATRIOT"],
        ["PATRIOT DISPOSAL - VIRGINIA"]
    ),
    
    # =========================================================================
    # TIER 5: SMALLER HAULERS (50-99 invoices)
    # =========================================================================
    
    "1-800-Got-Junk": (
        "1-800-GOT-JUNK National",
        ["1-800-GOT-JUNK", "1800GOTJUNK", "Got Junk"],
        ["1-800-GOT-JUNK National"]
    ),
    
    "Ace Recycling": (
        "ACE Recycling and Disposal",
        ["ACE Recycling", "ACE RECYCLING", "Ace Recycling"],
        ["ACE RECYCLING AND DISPOSAL"]
    ),
    
    "Advance Disposal": (
        "Advance Disposal",
        ["Advance Disposal", "ADVANCE DISPOSAL"],
        []
    ),
    
    "Alameda County Industries": (
        "Alameda County Industries",
        ["Alameda County", "ALAMEDA COUNTY"],
        []
    ),
    
    "Amwaste": (
        "AMWASTE",
        ["Amwaste", "AMWASTE", "AM Waste"],
        ["AMWASTE"]
    ),
    
    "Arrowhead Waste": (
        "Arrowhead Waste Services",
        ["Arrowhead", "ARROWHEAD"],
        ["Arrowhead Waste Services"]
    ),
    
    "ABC Waste": (
        "ABC Waste Of Savannah",
        ["ABC Waste", "ABC WASTE"],
        ["ABC Waste Of Savannah"]
    ),
    
    "Texas Disposal": (
        "Texas Disposal",
        ["Texas Disposal", "TEXAS DISPOSAL"],
        []
    ),
    
    "Recology": (
        "Recology",
        ["Recology", "RECOLOGY"],
        ["RECOLOGY-KING COUNTY-WASHINGTON"]
    ),
    
    "Granger": (
        "Granger Waste Services",
        ["Granger", "GRANGER"],
        ["GRANGER WASTE SERVICES"]
    ),
    
    "Modern Disposal": (
        "Modern Disposal Services",
        ["Modern Disposal", "MODERN DISPOSAL"],
        ["Modern Disposal Services"]
    ),
    
    "Tiger Trash": (
        "Tiger Trash",
        ["Tiger Trash", "TIGER TRASH"],
        ["TIGER TRASH"]
    ),
    
    "Shred-it": (
        "Shred-it",
        ["Shred-it", "SHRED-IT", "Shredit"],
        []
    ),
    
    "Iron Mountain": (
        "Iron Mountain",
        ["Iron Mountain", "IRON MOUNTAIN"],
        []
    ),
    
    "ZARC Recycling": (
        "Zarc Recycling",
        ["ZARC", "Zarc"],
        ["Zarc Recycling"]
    ),
    
    "Conigliaro": (
        "Conigliaro Industries",
        ["Conigliaro", "CONIGLIARO"],
        ["Conigliaro Industries"]
    ),
    
    "Pete & Pete": (
        "Pete & Pete Container Service",
        ["Pete & Pete", "PETE & PETE", "Pete and Pete"],
        ["Pete & Pete Container Service"]
    ),
    
    "West Central Sanitation": (
        "West Central Sanitation",
        ["West Central", "WEST CENTRAL"],
        []
    ),
    
    "Grogan Waste": (
        "Grogan Waste Services",
        ["Grogan", "GROGAN"],
        ["GROGAN WASTE SERVICES"]
    ),
    
    "Honolulu Disposal": (
        "Honolulu Disposal Service",
        ["Honolulu", "HONOLULU"],
        ["HONOLULU DISPOSAL SERVICE"]
    ),
    
    "Econo Waste": (
        "Econo Waste Inc",
        ["Econo Waste", "ECONO WASTE"],
        ["Econo Waste Inc"]
    ),
    
    "CWPM": (
        "CWPM",
        ["CWPM"],
        []
    ),
    
    "Gateway Disposal": (
        "Gateway Disposal",
        ["Gateway Disposal", "GATEWAY DISPOSAL"],
        []
    ),
    
    "Great Waste": (
        "Great Waste & Recycling Services",
        ["Great Waste", "GREAT WASTE"],
        ["Great Waste & Recycling Services"]
    ),
    
    "Northern Waste": (
        "Northern Waste",
        ["Northern Waste", "NORTHERN WASTE"],
        []
    ),
    
    "Community Disposal": (
        "Community Disposal Service",
        ["Community Disposal", "COMMUNITY DISPOSAL"],
        ["Community Disposal Service"]
    ),
    
    "Dependable Sanitation": (
        "Dependable Sanitation Inc",
        ["Dependable", "DEPENDABLE"],
        ["Dependable Sanitation Inc"]
    ),
    
    "Mid South Waste": (
        "Mid South Waste Disposal",
        ["Mid South", "MID SOUTH"],
        ["Mid South Waste Disposal"]
    ),
    
    "Absolute Waste": (
        "Absolute Waste Removal",
        ["Absolute Waste", "ABSOLUTE WASTE"],
        ["ABSOLUTE WASTE REMOVAL"]
    ),
    
    "WestRock": (
        "WestRock",
        ["WestRock", "WESTROCK", "West Rock"],
        []
    ),
    
    "Orlando Recycling": (
        "Orlando Recycling",
        ["Orlando Recycling", "ORLANDO RECYCLING"],
        []
    ),
    
    # =========================================================================
    # TIER 6: ADDITIONAL DETECTED VENDORS (< 100 invoices)
    # =========================================================================
    
    "Arrowaste": (
        "Arrowaste",
        ["Arrowaste", "ARROWASTE"],
        []
    ),
    
    "Heavenly Trash": (
        "Heavenly Trash",
        ["Heavenly Trash", "HEAVENLY TRASH"],
        []
    ),
    
    "Disposal Management": (
        "Disposal Management",
        ["Disposal Management", "DISPOSAL MANAGEMENT"],
        []
    ),
    
    "Live Oak": (
        "Live Oak",
        ["Live Oak", "LIVE OAK"],
        []
    ),
    
    "Granger Waste": (
        "Granger Waste Services",
        ["Granger", "GRANGER"],
        ["GRANGER WASTE SERVICES"]
    ),
    
    "Ankeny Sanitation": (
        "Ankeny Sanitation",
        ["Ankeny", "ANKENY"],
        []
    ),
    
    "Solid Waste Authority": (
        "Solid Waste Authority",
        ["Solid Waste Authority"],
        ["Hopkinsville Solid Waste Authority", "South Central Solid Waste Authority",
         "Baldwin County Solid Waste Authority"]
    ),
    
    "Tiger Sanitation": (
        "Tiger Sanitation",
        ["Tiger Sanitation", "TIGER SANITATION"],
        []
    ),
    
    "Stericycle": (
        "Stericycle",
        ["Stericycle", "STERICYCLE"],
        []
    ),
    
    "Troiano Waste": (
        "Troiano Waste Services",
        ["Troiano", "TROIANO"],
        ["Troiano Waste Services"]
    ),
    
    "Basin Disposal": (
        "Basin Disposal Inc",
        ["Basin Disposal", "BASIN DISPOSAL"],
        ["Basin Disposal Inc", "BASIN DISPOSAL - WASHINGTON"]
    ),
    
    "Becker360": (
        "Becker360",
        ["Becker360", "BECKER360", "Becker 360"],
        []
    ),
    
    "Grizzly Disposal": (
        "Grizzly Disposal",
        ["Grizzly", "GRIZZLY"],
        []
    ),
    
    "Blue Diamond Disposal": (
        "Blue Diamond Disposal",
        ["Blue Diamond", "BLUE DIAMOND"],
        ["BLUE DIAMOND DISPOSAL"]
    ),
    
    "Valley Vista": (
        "Valley Vista",
        ["Valley Vista", "VALLEY VISTA"],
        []
    ),
    
    "SSW Frontload": (
        "SSW Frontload",
        ["SSW", "SSW Frontload"],
        ["SSW-Box Services"]
    ),
    
    "Velpen Trucking": (
        "Velpen Trucking",
        ["Velpen", "VELPEN"],
        []
    ),
    
    "Gotta Go Waste": (
        "Gotta Go Waste",
        ["Gotta Go", "GOTTA GO"],
        []
    ),
    
    "Louisiana Waste": (
        "Louisiana Waste Systems",
        ["Louisiana Waste", "LOUISIANA WASTE"],
        ["Louisiana Waste Systems"]
    ),
    
    "Smith Creek": (
        "Smith Creek",
        ["Smith Creek", "SMITH CREEK"],
        []
    ),
    
    "Liberty Disposal": (
        "Liberty Disposal",
        ["Liberty Disposal", "LIBERTY DISPOSAL"],
        []
    ),
    
    "JLT Trucking": (
        "JLT Trucking",
        ["JLT", "JLT Trucking"],
        []
    ),
    
    "Independent Recycling": (
        "Independent Recycling",
        ["Independent Recycling", "INDEPENDENT RECYCLING"],
        []
    ),
    
    "Ryland Environmental": (
        "Ryland Environmental",
        ["Ryland", "RYLAND"],
        []
    ),
    
    "Moore Coal": (
        "Moore Coal",
        ["Moore Coal", "MOORE COAL"],
        []
    ),
    
    "Premier Waste": (
        "Premier Waste",
        ["Premier Waste", "PREMIER WASTE"],
        []
    ),
    
    "Pelican Waste": (
        "Pelican Waste",
        ["Pelican", "PELICAN"],
        []
    ),
    
    "D Crescio Trucking": (
        "D Crescio Trucking",
        ["Crescio", "D Crescio"],
        []
    ),
    
    "NK Waste": (
        "NK Waste",
        ["NK Waste", "NK WASTE"],
        []
    ),
    
    "Modern Recycling": (
        "Modern Recycling",
        ["Modern Recycling", "MODERN RECYCLING"],
        []
    ),
    
    "Redgate Disposal": (
        "Redgate Disposal",
        ["Redgate", "REDGATE"],
        []
    ),
    
    "Community Waste": (
        "Community Waste",
        ["Community Waste", "COMMUNITY WASTE"],
        []
    ),
    
    "Western Disposal": (
        "Western Disposal",
        ["Western Disposal", "WESTERN DISPOSAL"],
        []
    ),
    
    "WG Waste": (
        "WG Waste",
        ["WG Waste", "WG WASTE"],
        []
    ),
    
    "City of Boise": (
        "City of Boise",
        ["City of Boise", "CITY OF BOISE"],
        []
    ),
    
    "Gulf Coast Containers": (
        "Gulf Coast Containers",
        ["Gulf Coast", "GULF COAST"],
        []
    ),
    
    "City of Jackson": (
        "City of Jackson",
        ["City of Jackson", "CITY OF JACKSON"],
        []
    ),
    
    "Lexington Site Services": (
        "Lexington Site Services",
        ["Lexington Site", "LEXINGTON SITE"],
        []
    ),
    
    "TK Trash": (
        "TK Trash",
        ["TK Trash", "TK TRASH"],
        []
    ),
    
    "J&K Trash": (
        "J&K Trash",
        ["J&K Trash", "J&K TRASH"],
        []
    ),
    
    "Specialty Pallet": (
        "Specialty Pallet",
        ["Specialty Pallet", "SPECIALTY PALLET"],
        []
    ),
    
    "Clean Slate": (
        "Clean Slate",
        ["Clean Slate", "CLEAN SLATE"],
        []
    ),
    
    "Olympic Compactor Rentals": (
        "Olympic Compactor Rentals",
        ["Olympic Compactor", "OLYMPIC COMPACTOR"],
        []
    ),
    
    "Walker Lake Disposal": (
        "Walker Lake Disposal",
        ["Walker Lake", "WALKER LAKE"],
        []
    ),
    
    "Trident Waste": (
        "Trident Waste",
        ["Trident", "TRIDENT"],
        []
    ),
    
    "Blue Hills Environmental": (
        "Blue Hills Environmental",
        ["Blue Hills", "BLUE HILLS"],
        []
    ),
    
    "Vogel Disposal": (
        "Vogel Disposal",
        ["Vogel", "VOGEL"],
        []
    ),
    
    "Ohio Valley Waste": (
        "Ohio Valley Waste",
        ["Ohio Valley", "OHIO VALLEY"],
        []
    ),
    
    "City Waste": (
        "City Waste",
        ["City Waste", "CITY WASTE"],
        []
    ),
    
    "Boro Wide": (
        "Boro Wide",
        ["Boro Wide", "BORO WIDE"],
        []
    ),
    
    "WillScot": (
        "WillScot",
        ["WillScot", "WILLSCOT", "Will Scot"],
        []
    ),
    
    "Chrin Hauling": (
        "Chrin Hauling",
        ["Chrin", "CHRIN"],
        []
    ),
    
    "Cards Mo": (
        "Cards Mo",
        ["Cards Mo", "CARDS MO"],
        []
    ),
    
    "Direct Waste Services": (
        "Direct Waste Services",
        ["Direct Waste", "DIRECT WASTE"],
        []
    ),
    
    "Lakeshore Recycling": (
        "Lakeshore Recycling",
        ["Lakeshore", "LAKESHORE"],
        []
    ),
    
    "Roll Off Systems": (
        "Roll Off Systems",
        ["Roll Off Systems", "ROLL OFF SYSTEMS"],
        []
    ),
    
    "EOMS Recycling": (
        "EOMS Recycling",
        ["EOMS", "E.O.M.S."],
        []
    ),
    
    "Cooks Wastepaper": (
        "Cooks Wastepaper",
        ["Cooks Wastepaper", "COOKS WASTEPAPER"],
        ["Waste Connections - Cooks Waste Paper & Recycline 6032"]
    ),
    
    "Waste Services LLC": (
        "Waste Services LLC",
        ["Waste Services LLC", "WASTE SERVICES LLC"],
        []
    ),
    
    "Green Guys": (
        "Green Guys",
        ["Green Guys", "GREEN GUYS"],
        []
    ),
    
    "Modern Corporation": (
        "Modern Corporation",
        ["Modern Corporation", "MODERN CORPORATION"],
        []
    ),
    
    "Ace Waste Systems": (
        "Ace Waste Systems",
        ["Ace Waste Systems", "ACE WASTE SYSTEMS"],
        []
    ),
    
    "Vista Recycling": (
        "Vista Recycling",
        ["Vista Recycling", "VISTA RECYCLING"],
        []
    ),
    
    "Atlantic Waste": (
        "Atlantic Waste",
        ["Atlantic Waste", "ATLANTIC WASTE"],
        []
    ),
    
    "Mid Valley Disposal": (
        "Mid Valley Disposal",
        ["Mid Valley", "MID VALLEY"],
        []
    ),
    
    "Schaap Sanitation": (
        "Schaap Sanitation",
        ["Schaap", "SCHAAP"],
        []
    ),
    
    "Pascon": (
        "Pascon",
        ["Pascon", "PASCON"],
        []
    ),
    
    "Thompson Sanitation": (
        "Thompson Sanitation",
        ["Thompson Sanitation", "THOMPSON SANITATION"],
        []
    ),
    
    "Conex Recycling": (
        "Conex Recycling",
        ["Conex", "CONEX"],
        []
    ),
    
    "City of Blackfoot": (
        "City of Blackfoot",
        ["City of Blackfoot", "CITY OF BLACKFOOT"],
        []
    ),
    
    "Western Elite": (
        "Western Elite",
        ["Western Elite", "WESTERN ELITE"],
        []
    ),
    
    "Cards Recycling": (
        "Cards Recycling",
        ["Cards Recycling", "CARDS RECYCLING"],
        []
    ),
    
    "Southern Sanitation": (
        "Southern Sanitation",
        ["Southern Sanitation", "SOUTHERN SANITATION"],
        []
    ),
    
    "City of Meridian": (
        "City of Meridian",
        ["City of Meridian", "CITY OF MERIDIAN"],
        []
    ),
    
    # =========================================================================
    # TIER 7: REMAINING VENDORS FOR 95%+ COVERAGE
    # =========================================================================
    
    "Advance Machine & Hydraulic": (
        "Advance Machine & Hydraulic",
        ["Advance Machine", "ADVANCE MACHINE"],
        []
    ),
    
    "SSW-Box Services": (
        "SSW-Box Services",
        ["SSW-Box", "SSW Box"],
        []
    ),
    
    "Chambersburg Waste Paper": (
        "Chambersburg Waste Paper",
        ["Chambersburg", "CHAMBERSBURG"],
        []
    ),
    
    "Florida Express Waste": (
        "Florida Express Waste",
        ["Florida Express", "FLORIDA EXPRESS"],
        []
    ),
    
    "Curbside": (
        "Curbside",
        ["Curbside", "CURBSIDE"],
        []
    ),
    
    "Hill Country Waste": (
        "Hill Country Waste",
        ["Hill Country", "HILL COUNTRY"],
        []
    ),
    
    "DeKalb County": (
        "DeKalb County",
        ["DeKalb County", "DEKALB COUNTY"],
        []
    ),
    
    "Brask Enterprises": (
        "Brask Enterprises",
        ["Brask", "BRASK"],
        []
    ),
    
    "Kahut Waste": (
        "Kahut Waste",
        ["Kahut", "KAHUT"],
        []
    ),
    
    "F & L Construction": (
        "F and L Construction Inc",
        ["F & L", "F&L", "F and L"],
        ["F AND L CONSTRUCTION INC"]
    ),
    
    "Total Reclaim": (
        "Total Reclaim",
        ["Total Reclaim", "TOTAL RECLAIM"],
        []
    ),
    
    "All Metals Recycling": (
        "All Metals Recycling",
        ["All Metals", "ALL METALS"],
        []
    ),
    
    "Black Hawk Waste": (
        "Black Hawk Waste",
        ["Black Hawk", "BLACK HAWK"],
        []
    ),
    
    "Orlando Waste Paper": (
        "Orlando Waste Paper",
        ["Orlando Waste Paper", "ORLANDO WASTE PAPER"],
        []
    ),
    
    "Midwest Paper": (
        "Midwest Paper",
        ["Midwest Paper", "MIDWEST PAPER"],
        []
    ),
    
    "AAA Disposal Service": (
        "AAA Disposal Service",
        ["AAA Disposal", "AAA DISPOSAL"],
        []
    ),
    
    "Jay Mecham's": (
        "Jay Mecham's",
        ["Jay Mecham", "JAY MECHAM"],
        []
    ),
    
    "City of Fargo": (
        "City of Fargo",
        ["City of Fargo", "CITY OF FARGO"],
        []
    ),
    
    "River Parish Disposal": (
        "River Parish Disposal",
        ["River Parish", "RIVER PARISH"],
        []
    ),
    
    "Greif": (
        "Greif",
        ["Greif", "GREIF"],
        []
    ),
    
    "Heiberg Garbage": (
        "Heiberg Garbage",
        ["Heiberg", "HEIBERG"],
        []
    ),
    
    "South Shore Disposal": (
        "South Shore Disposal",
        ["South Shore", "SOUTH SHORE"],
        []
    ),
    
    "Waste Path": (
        "Waste Path",
        ["Waste Path", "WASTE PATH"],
        []
    ),
    
    "UDP TN Hauling": (
        "UDP TN Hauling",
        ["UDP TN", "UDP"],
        []
    ),
    
    "Sonny's Solid Waste": (
        "Sonny's Solid Waste",
        ["Sonny's", "SONNY'S"],
        []
    ),
    
    "Prestige Disposal": (
        "Prestige Disposal",
        ["Prestige", "PRESTIGE"],
        []
    ),
    
    "Lawrence County Solid Waste": (
        "Lawrence County Solid Waste",
        ["Lawrence County", "LAWRENCE COUNTY"],
        []
    ),
    
    "Trash Control": (
        "Trash Control",
        ["Trash Control", "TRASH CONTROL"],
        []
    ),
    
    "Southern Illinois Waste": (
        "Southern Illinois Waste",
        ["Southern Illinois", "SOUTHERN ILLINOIS"],
        []
    ),
    
    "Kootenai County Solid Waste": (
        "Kootenai County Solid Waste",
        ["Kootenai", "KOOTENAI"],
        []
    ),
    
    "North Georgia Waste": (
        "North Georgia Waste",
        ["North Georgia", "NORTH GEORGIA"],
        []
    ),
    
    "Town of Gardnerville": (
        "Town of Gardnerville",
        ["Gardnerville", "GARDNERVILLE"],
        []
    ),
    
    "BFI Waste": (
        "BFI Waste",
        ["BFI", "B.F.I."],
        []
    ),
    
    "Recycling Services of Florida": (
        "Recycling Services of Florida",
        ["Recycling Services of Florida", "RECYCLING SERVICES OF FLORIDA"],
        []
    ),
    
    "Island Disposal": (
        "Island Disposal",
        ["Island Disposal", "ISLAND DISPOSAL"],
        []
    ),
    
    "Island Refuse": (
        "Island Refuse",
        ["Island Refuse", "ISLAND REFUSE"],
        []
    ),
    
    "Good's Disposal": (
        "Good's Disposal",
        ["Good's Disposal", "GOOD'S DISPOSAL"],
        []
    ),
    
    "Debris to Green": (
        "Debris to Green",
        ["Debris to Green", "DEBRIS TO GREEN"],
        []
    ),
    
    "Total Disposal Inc": (
        "Total Disposal Inc",
        ["Total Disposal", "TOTAL DISPOSAL"],
        []
    ),
    
    "Town & Country Disposal": (
        "Town & Country Disposal",
        ["Town & Country", "TOWN & COUNTRY"],
        []
    ),
    
    "Tri-County Industries": (
        "Tri-County Industries",
        ["Tri-County", "TRI-COUNTY"],
        []
    ),
    
    "Tri-City Disposal": (
        "Tri-City Disposal",
        ["Tri-City", "TRI-CITY"],
        []
    ),
    
    "Tri-State Disposal": (
        "Tri-State Disposal",
        ["Tri-State", "TRI-STATE"],
        []
    ),
    
    "Tri-State Carting": (
        "Tri-State Carting",
        ["Tri-State Carting", "TRI-STATE CARTING"],
        []
    ),

    "Tri-State Waste & Recycling": (
        "Tri-State Waste & Recycling Inc",
        ["Tri-State Waste"],
        ["Tri-State Waste & Recycling Inc"]
    ),
    
    "Trinity Disposal": (
        "Trinity Disposal",
        ["Trinity", "TRINITY"],
        []
    ),
    
    "Tropical Trash": (
        "Tropical Trash",
        ["Tropical Trash", "TROPICAL TRASH"],
        []
    ),
    
    "Troupe Waste": (
        "Troupe Waste",
        ["Troupe", "TROUPE"],
        []
    ),
    
    "Tygarts Valley Sanitation": (
        "Tygarts Valley Sanitation",
        ["Tygarts Valley", "TYGARTS VALLEY"],
        []
    ),
    
    "U & I Sanitation": (
        "U & I Sanitation",
        ["U & I", "U&I"],
        []
    ),
    
    "Universal Waste": (
        "Universal Waste Systems",
        ["Universal Waste", "UNIVERSAL WASTE"],
        ["UNIVERSAL WASTE SYSTEMS"]
    ),
    
    "Updike Industries": (
        "Updike Industries",
        ["Updike", "UPDIKE"],
        []
    ),
    
    "Upper Valley Disposal": (
        "Upper Okanogan Valley Disposal",
        ["Upper Valley", "UPPER VALLEY"],
        ["Upper Okanogan Valley Disposal"]
    ),
    
    "Uribe Refuse": (
        "Uribe Refuse",
        ["Uribe", "URIBE"],
        []
    ),
    
    "Valley Sanitation LLC": (
        "Valley Sanitation LLC",
        ["Valley Sanitation", "VALLEY SANITATION"],
        []
    ),
    
    "Valley Waste Service": (
        "Valley Waste Service",
        ["Valley Waste", "VALLEY WASTE"],
        []
    ),
    
    "Vanderpoel Disposal": (
        "Vanderpoel Disposal",
        ["Vanderpoel", "VANDERPOEL"],
        []
    ),
    
    "Walters Sanitary Service": (
        "Walters Sanitary Service",
        ["Walters Sanitary", "WALTERS SANITARY"],
        []
    ),
    
    "Washler Garbage": (
        "Washler Garbage",
        ["Washler", "WASHLER"],
        []
    ),
    
    "Waste Away": (
        "Waste Away",
        ["Waste Away", "WASTE AWAY"],
        []
    ),
    
    "Waste Control": (
        "Waste Control",
        ["Waste Control", "WASTE CONTROL"],
        []
    ),
    
    "Waste Harmonics": (
        "Waste Harmonics",
        ["Waste Harmonics", "WASTE HARMONICS"],
        []
    ),
    
    "Waste Masters": (
        "Waste Masters",
        ["Waste Masters", "WASTE MASTERS"],
        []
    ),
    
    "WasteVision": (
        "Waste Vision",
        ["WasteVision", "Waste Vision", "WASTEVISION"],
        []
    ),
    
    "Wasteless Solutions": (
        "Wasteless Solutions",
        ["Wasteless", "WASTELESS"],
        []
    ),
    
    "Waterman Recycling": (
        "Waterman Recycling",
        ["Waterman", "WATERMAN"],
        []
    ),
    
    "Watertown Iron": (
        "Watertown Iron",
        ["Watertown Iron", "WATERTOWN IRON"],
        []
    ),
    
    "Wayne County Utah": (
        "Wayne County Utah",
        ["Wayne County", "WAYNE COUNTY"],
        []
    ),
    
    "Weidle Sanitation": (
        "Weidle Sanitation",
        ["Weidle", "WEIDLE"],
        []
    ),
    
    "Wemiga Waste": (
        "Wemiga Waste",
        ["Wemiga", "WEMIGA"],
        []
    ),
    
    "West Oahu Aggregate": (
        "West Oahu Aggregate",
        ["West Oahu", "WEST OAHU"],
        []
    ),
    
    "Western Kane County": (
        "Western Kane County",
        ["Western Kane", "WESTERN KANE"],
        []
    ),
    
    "Westside Disposal": (
        "Westside Disposal",
        ["Westside", "WESTSIDE"],
        []
    ),
    
    "Whitecap Waste": (
        "Whitecap Waste",
        ["Whitecap", "WHITECAP"],
        []
    ),
    
    "Willey Disposal": (
        "Willey Disposal",
        ["Willey", "WILLEY"],
        []
    ),
    
    "William Sullivan": (
        "William Sullivan",
        ["William Sullivan", "WILLIAM SULLIVAN"],
        []
    ),
    
    "Wisneski Westmoreland": (
        "Wisneski Westmoreland",
        ["Wisneski", "WISNESKI"],
        []
    ),
    
    "Woodward's Disposal": (
        "Woodward's Disposal",
        ["Woodward", "WOODWARD"],
        []
    ),
    
    "Wyoming Waste Services": (
        "Wyoming Waste Services",
        ["Wyoming Waste", "WYOMING WASTE"],
        []
    ),
    
    "Young Refuse": (
        "Young Refuse",
        ["Young Refuse", "YOUNG REFUSE"],
        []
    ),
    
    "Yreka Transfer": (
        "Yreka Transfer",
        ["Yreka", "YREKA"],
        []
    ),
    
    "Zero Waste": (
        "Zero Waste",
        ["Zero Waste", "ZERO WASTE"],
        []
    ),
    
    # =========================================================================
    # TIER 8: FINAL VENDORS FOR 95%+ COVERAGE
    # =========================================================================
    
    "First Piedmont": (
        "First Piedmont",
        ["First Piedmont", "FIRST PIEDMONT"],
        []
    ),
    
    "Intermountain Disposal": (
        "Intermountain Disposal",
        ["Intermountain", "INTERMOUNTAIN"],
        []
    ),
    
    "Cavossa Disposal": (
        "Cavossa Disposal",
        ["Cavossa", "CAVOSSA"],
        []
    ),
    
    "Pennohio": (
        "Pennohio",
        ["Pennohio", "PENNOHIO"],
        []
    ),
    
    "Pak Rite Rentals": (
        "Pak Rite Rentals",
        ["Pak Rite", "PAK RITE"],
        []
    ),
    
    "Reliable Sanitation": (
        "Reliable Sanitation",
        ["Reliable Sanitation", "RELIABLE SANITATION"],
        []
    ),
    
    "County Waste Systems": (
        "County Waste Systems",
        ["County Waste Systems", "COUNTY WASTE SYSTEMS"],
        []
    ),
    
    "Pellitteri": (
        "Pellitteri",
        ["Pellitteri", "PELLITTERI"],
        []
    ),
    
    "Indiana Waste": (
        "Indiana Waste",
        ["Indiana Waste", "INDIANA WASTE"],
        []
    ),
    
    "K-Town Disposal": (
        "K-Town Disposal",
        ["K-Town", "KTOWN", "K Town"],
        []
    ),
    
    "Texas Pride Disposal": (
        "Texas Pride Disposal",
        ["Texas Pride", "TEXAS PRIDE"],
        []
    ),
    
    "Geodom Carting": (
        "Geodom Carting",
        ["Geodom", "GEODOM"],
        []
    ),
    
    "Pacific Waste": (
        "Pacific Waste",
        ["Pacific Waste", "PACIFIC WASTE"],
        []
    ),
    
    "Reworld": (
        "Reworld",
        ["Reworld", "REWORLD"],
        []
    ),
    
    "Garden Isle Disposal": (
        "Garden Isle Disposal",
        ["Garden Isle", "GARDEN ISLE"],
        []
    ),
    
    "CSD Disposal": (
        "CSD Disposal",
        ["CSD", "C.S.D."],
        []
    ),
    
    "Circle Sanitation": (
        "Circle Sanitation",
        ["Circle Sanitation", "CIRCLE SANITATION"],
        []
    ),
    
    "Royal Document Destruction": (
        "Royal Document Destruction",
        ["Royal Document", "ROYAL DOCUMENT"],
        []
    ),
    
    "All Florida Scrap Metals": (
        "All Florida Scrap Metals",
        ["All Florida", "ALL FLORIDA"],
        []
    ),
    
    "Pro Waste Services": (
        "Pro Waste Services",
        ["Pro Waste", "PRO WASTE"],
        []
    ),
    
    "Grace Hauling": (
        "Grace Hauling",
        ["Grace Hauling", "GRACE HAULING"],
        []
    ),
    
    "ABC Disposal Systems": (
        "ABC Disposal Systems",
        ["ABC Disposal Systems", "ABC DISPOSAL SYSTEMS"],
        []
    ),
    
    "AT Disposal": (
        "AT Disposal",
        ["AT Disposal", "AT DISPOSAL"],
        []
    ),
    
    "AWS": (
        "AWS",
        ["AWS"],
        []
    ),
    
    "Richardson Waste": (
        "Richardson Waste",
        ["Richardson", "RICHARDSON"],
        []
    ),
    
    "Roosevelt UT": (
        "Roosevelt UT",
        ["Roosevelt UT", "ROOSEVELT UT"],
        []
    ),
    
    "IV Waste": (
        "IV Waste",
        ["IV Waste", "IV WASTE"],
        []
    ),
    
    "Countryside Disposal": (
        "Countryside Disposal",
        ["Countryside Disposal", "COUNTRYSIDE DISPOSAL"],
        []
    ),
    
    "Sanitary Service Company": (
        "Sanitary Service Company",
        ["Sanitary Service Company", "SANITARY SERVICE COMPANY"],
        []
    ),
    
    "City of Deerfield Beach": (
        "City of Deerfield Beach",
        ["City of Deerfield", "CITY OF DEERFIELD"],
        []
    ),
    
    "Al Clawson Disposal": (
        "Al Clawson Disposal",
        ["Al Clawson", "AL CLAWSON"],
        []
    ),
    
    "Allen Disposal": (
        "Allen Disposal",
        ["Allen Disposal", "ALLEN DISPOSAL"],
        []
    ),
    
    "Alpha Waste Disposal": (
        "Alpha Waste Disposal",
        ["Alpha Waste", "ALPHA WASTE"],
        []
    ),
    
    "American Eagle Waste": (
        "American Eagle Waste",
        ["American Eagle", "AMERICAN EAGLE"],
        []
    ),
    
    "American Sanitation": (
        "American Sanitation",
        ["American Sanitation", "AMERICAN SANITATION"],
        []
    ),
    
    "American Waste Control": (
        "American Waste Control",
        ["American Waste Control", "AMERICAN WASTE CONTROL"],
        []
    ),
    
    "Ameriwaste": (
        "Ameriwaste",
        ["Ameriwaste", "AMERIWASTE"],
        []
    ),
    
    "Anaconda Disposal": (
        "Anaconda Disposal",
        ["Anaconda", "ANACONDA"],
        []
    ),
    
    "Anchorage Solid Waste": (
        "Anchorage Solid Waste",
        ["Anchorage Solid Waste", "ANCHORAGE SOLID WASTE"],
        []
    ),
    
    "Apple Valley Waste": (
        "Apple Valley Waste",
        ["Apple Valley", "APPLE VALLEY"],
        []
    ),
    
    "Art's Garbage": (
        "Art's Garbage",
        ["Art's Garbage", "ARTS GARBAGE"],
        ["Waste Connections - Arts Garbage Service"]
    ),
    
    "Ava's Waste Removal": (
        "Ava's Waste Removal",
        ["Ava's Waste", "AVAS WASTE"],
        []
    ),
    
    "B&L Disposal": (
        "B&L Disposal",
        ["B&L", "B & L"],
        []
    ),
    
    "BCC Waste Solutions": (
        "BCC Waste Solutions",
        ["BCC Waste", "BCC WASTE"],
        []
    ),
    
    "BCDA The Trash Company": (
        "BCDA The Trash Company",
        ["BCDA", "B.C.D.A."],
        []
    ),
    
    "BKI Recycling": (
        "BKI Recycling",
        ["BKI", "B.K.I."],
        []
    ),
    
    "BNB Disposal": (
        "BNB Disposal",
        ["BNB", "B.N.B."],
        []
    ),
    
    "BP Trucking": (
        "BP Trucking",
        ["BP Trucking", "BP TRUCKING"],
        []
    ),
    
    "BTS Inc": (
        "BTS Inc",
        ["BTS", "B.T.S."],
        []
    ),
    
    "Basin Haulage": (
        "Basin Haulage",
        ["Basin Haulage", "BASIN HAULAGE"],
        []
    ),
    
    "Becker Complete": (
        "Becker Complete",
        ["Becker Complete", "BECKER COMPLETE"],
        []
    ),
    
    "BestTrash": (
        "BestTrash",
        ["BestTrash", "BESTTRASH", "Best Trash"],
        []
    ),
    
    "Bi-County Disposal": (
        "Bi-County Disposal",
        ["Bi-County", "BI-COUNTY"],
        []
    ),
    
    "Big River Disposal": (
        "Big River Disposal",
        ["Big River", "BIG RIVER"],
        []
    ),
    
    "Black Earth Compost": (
        "Black Earth Compost",
        ["Black Earth", "BLACK EARTH"],
        []
    ),
    
    "Bliss Environmental": (
        "Bliss Environmental",
        ["Bliss Environmental", "BLISS ENVIRONMENTAL"],
        []
    ),
    
    "Bloom Waste": (
        "Bloom Waste",
        ["Bloom Waste", "BLOOM WASTE"],
        []
    ),
    
    "Blue Moon": (
        "Blue Moon",
        ["Blue Moon", "BLUE MOON"],
        []
    ),
    
    "Blue Ridge Waste": (
        "Blue Ridge Waste",
        ["Blue Ridge", "BLUE RIDGE"],
        []
    ),
    
    "Boston Baler": (
        "Boston Baler",
        ["Boston Baler", "BOSTON BALER"],
        []
    ),
    
    "Bozzuto BRS Services": (
        "Bozzuto BRS Services",
        ["Bozzuto", "BOZZUTO"],
        []
    ),
    
    "Break It Down": (
        "Break It Down",
        ["Break It Down", "BREAK IT DOWN"],
        []
    ),
    
    "4G Futures": (
        "4G Futures",
        ["4G Futures", "4G FUTURES"],
        []
    ),
    
    "501 Sanitation": (
        "501 Sanitation",
        ["501 Sanitation", "501 SANITATION"],
        []
    ),
    
    "A&C Waste Collection": (
        "A&C Waste Collection",
        ["A&C Waste", "A&C WASTE"],
        []
    ),
    
    "A&I Pallets": (
        "A&I Pallets",
        ["A&I Pallets", "A&I PALLETS"],
        []
    ),
    
    "A&J Trash": (
        "A&J Trash",
        ["A&J Trash", "A&J TRASH"],
        []
    ),
    
    "A&L Compaction": (
        "A&L Compaction",
        ["A&L Compaction", "A&L COMPACTION"],
        []
    ),
    
    "A&W Iron Metal": (
        "A&W Iron Metal",
        ["A&W Iron", "A&W IRON"],
        []
    ),
    
    "A-1 Disposal": (
        "A-1 Disposal",
        ["A-1 Disposal", "A1 Disposal"],
        []
    ),
    
    "A-1 Little John": (
        "A-1 Little John",
        ["A-1 Little John", "A1 Little John"],
        []
    ),
    
    "A1 Porta Potty": (
        "A1 Porta Potty",
        ["A1 Porta Potty", "A1 PORTA POTTY"],
        []
    ),
    
    "AB-8 Waste Solutions": (
        "AB-8 Waste Solutions",
        ["AB-8", "AB8"],
        []
    ),
    
    "AG Logistics": (
        "AG Logistics",
        ["AG Logistics", "AG LOGISTICS"],
        []
    ),
    
    "AJ Waste Systems": (
        "AJ Waste Systems",
        ["AJ Waste", "AJ WASTE"],
        []
    ),
    
    "AM Disposal": (
        "AM Disposal",
        ["AM Disposal", "AM DISPOSAL"],
        []
    ),
    
    "AMG Resources": (
        "AMG Resources",
        ["AMG Resources", "AMG RESOURCES"],
        []
    ),
    
    "Absolute Services": (
        "Absolute Services",
        ["Absolute Services", "ABSOLUTE SERVICES"],
        []
    ),
    
    "Ace Equipment Company": (
        "Ace Equipment Company",
        ["Ace Equipment", "ACE EQUIPMENT"],
        []
    ),
    
    "Ace Sanitation Service": (
        "Ace Sanitation Service",
        ["Ace Sanitation", "ACE SANITATION"],
        []
    ),
    
    "Adam's Disposal": (
        "Adam's Disposal",
        ["Adam's Disposal", "ADAMS DISPOSAL"],
        []
    ),
    
    "Agri-Cycle": (
        "Agri-Cycle",
        ["Agri-Cycle", "AGRI-CYCLE", "AgriCycle"],
        []
    ),
    
    "Akat Scrap Metal": (
        "Akat Scrap Metal",
        ["Akat", "AKAT"],
        []
    ),
    
    "All Star Roll-Off": (
        "All Star Roll-Off",
        ["All Star Roll", "ALL STAR ROLL"],
        []
    ),
    
    "All States Services": (
        "All States Services",
        ["All States", "ALL STATES"],
        []
    ),
    
    "Arg Services": (
        "Arg Services",
        ["Arg Services", "ARG SERVICES"],
        []
    ),
    
    "Texas Dumpsters": (
        "Texas Dumpsters",
        ["Texas Dumpsters", "TEXAS DUMPSTERS"],
        []
    ),
    
    "The Shred Truck": (
        "The Shred Truck",
        ["Shred Truck", "SHRED TRUCK"],
        []
    ),
    
    "The Trash Guys": (
        "The Trash Guys",
        ["Trash Guys", "TRASH GUYS"],
        []
    ),
    
    "The Trash Man": (
        "The Trash Man",
        ["Trash Man", "TRASH MAN"],
        []
    ),
    
    "Thomas Trash": (
        "Thomas Trash",
        ["Thomas Trash", "THOMAS TRASH"],
        []
    ),
    
    "Thompson's Sanitary Service": (
        "Thompson's Sanitary Service",
        ["Thompson's Sanitary", "THOMPSONS SANITARY"],
        []
    ),
    
    "Tim's Trash Service": (
        "Tim's Trash Service",
        ["Tim's Trash", "TIMS TRASH"],
        []
    ),
    
    "Timmons Waste Service": (
        "Timmons Waste Service",
        ["Timmons", "TIMMONS"],
        []
    ),
    
    "Top of the Line Dumpsters": (
        "Top of the Line Dumpsters",
        ["Top of the Line", "TOP OF THE LINE"],
        []
    ),
    
    "Toro Waste": (
        "Toro Waste",
        ["Toro Waste", "TORO WASTE"],
        []
    ),
    
    "Tovar Equipment": (
        "Tovar Equipment",
        ["Tovar", "TOVAR"],
        []
    ),
    
    "Town of Dutch John": (
        "Town of Dutch John",
        ["Dutch John", "DUTCH JOHN"],
        []
    ),
    
    "Town of Greeneville": (
        "Town of Greeneville",
        ["Greeneville", "GREENEVILLE"],
        []
    ),
    
    "Town of Lusk": (
        "Town of Lusk",
        ["Town of Lusk", "TOWN OF LUSK"],
        []
    ),
    
    "TransTrash": (
        "TransTrash",
        ["TransTrash", "TRANSTRASH", "Trans Trash"],
        []
    ),
    
    "Trash Rangers": (
        "Trash Rangers",
        ["Trash Rangers", "TRASH RANGERS"],
        []
    ),
    
    "Treasure Coast Recycling": (
        "Treasure Coast Recycling",
        ["Treasure Coast", "TREASURE COAST"],
        []
    ),
    
    "Talon Sanitation": (
        "Talon Sanitation",
        ["Talon", "TALON"],
        []
    ),
    
    "Taylor & Sons": (
        "Taylor & Sons",
        ["Taylor & Sons", "TAYLOR & SONS"],
        []
    ),
    
    "Tahoe Basin Container": (
        "Tahoe Basin Container",
        ["Tahoe Basin", "TAHOE BASIN"],
        []
    ),
    
    # =========================================================================
    # TIER 9: FINAL BATCH FOR 95%+ COVERAGE (20+ invoices each)
    # =========================================================================
    
    "Marborg": (
        "Marborg",
        ["Marborg", "MARBORG"],
        []
    ),
    
    "Hart Sanitation": (
        "Hart Sanitation",
        ["Hart Sanitation", "HART SANITATION"],
        []
    ),
    
    "Burgmeier's Hauling": (
        "Burgmeier's Hauling",
        ["Burgmeier", "BURGMEIER"],
        []
    ),
    
    "Dunham": (
        "Dunham",
        ["Dunham", "DUNHAM"],
        []
    ),
    
    "TFC Recycling": (
        "TFC Recycling",
        ["TFC Recycling", "TFC RECYCLING"],
        []
    ),
    
    "City of Pembroke Pines": (
        "City of Pembroke Pines",
        ["Pembroke Pines", "PEMBROKE PINES"],
        []
    ),
    
    "Lusk Disposal": (
        "Lusk Disposal",
        ["Lusk Disposal", "LUSK DISPOSAL"],
        []
    ),
    
    "K & K Sanitation": (
        "K & K Sanitation",
        ["K & K", "K&K"],
        []
    ),
    
    "Hugill Sanitation": (
        "Hugill Sanitation",
        ["Hugill", "HUGILL"],
        []
    ),
    
    "Stryker Environmental": (
        "Stryker Environmental",
        ["Stryker", "STRYKER"],
        []
    ),
    
    "Cleeton Sanitation": (
        "Cleeton Sanitation",
        ["Cleeton", "CLEETON"],
        []
    ),
    
    "Salandro Refuse": (
        "Salandro Refuse",
        ["Salandro", "SALANDRO"],
        []
    ),
    
    "CRP Sanitation": (
        "CRP Sanitation",
        ["CRP Sanitation", "CRP SANITATION"],
        []
    ),
    
    "Charlie's Waste": (
        "Charlie's Waste",
        ["Charlie's Waste", "CHARLIES WASTE"],
        []
    ),
    
    "Butler Disposal Systems": (
        "Butler Disposal Systems",
        ["Butler Disposal", "BUTLER DISPOSAL"],
        []
    ),
    
    "CTL 3R Technology": (
        "CTL 3R Technology",
        ["CTL 3R", "CTL3R"],
        []
    ),
    
    "Cards KS": (
        "Cards KS",
        ["Cards KS", "CARDS KS"],
        []
    ),
    
    "Redwood Waste": (
        "Redwood Waste",
        ["Redwood Waste", "REDWOOD WASTE"],
        []
    ),
    
    "Suburban Waste Services": (
        "Suburban Waste Services",
        ["Suburban Waste", "SUBURBAN WASTE"],
        []
    ),
    
    "Penn Waste": (
        "Penn Waste",
        ["Penn Waste", "PENN WASTE"],
        []
    ),
    
    "Filco": (
        "Filco",
        ["Filco", "FILCO"],
        []
    ),
    
    "Earthwise Waste Solutions": (
        "Earthwise Waste Solutions",
        ["Earthwise", "EARTHWISE"],
        []
    ),
    
    "Nevada Recycling": (
        "Nevada Recycling",
        ["Nevada Recycling", "NEVADA RECYCLING"],
        []
    ),
    
    "Major Waste": (
        "Major Waste",
        ["Major Waste", "MAJOR WASTE"],
        []
    ),
    
    "Hometown Sanitation": (
        "Hometown Sanitation",
        ["Hometown", "HOMETOWN"],
        []
    ),
    
    "Mike's Rubbish": (
        "Mike's Rubbish",
        ["Mike's Rubbish", "MIKES RUBBISH"],
        []
    ),
    
    "City of Conyers": (
        "City of Conyers",
        ["City of Conyers", "CITY OF CONYERS"],
        []
    ),
    
    "Green Planet 21": (
        "Green Planet 21",
        ["Green Planet", "GREEN PLANET"],
        []
    ),
    
    "Swinger Sanitation": (
        "Swinger Sanitation",
        ["Swinger", "SWINGER"],
        []
    ),
    
    "Kern County Public Works": (
        "Kern County Public Works",
        ["Kern County", "KERN COUNTY"],
        []
    ),
    
    "MCUD Manatee": (
        "MCUD Manatee",
        ["MCUD", "M.C.U.D."],
        []
    ),
    
    "RAD Curbside": (
        "RAD Curbside",
        ["RAD Curbside", "RAD CURBSIDE"],
        []
    ),
    
    "Hoss Disposal": (
        "Hoss Disposal",
        ["Hoss Disposal", "HOSS DISPOSAL"],
        []
    ),
    
    "Larry D Marshall Disposal": (
        "Larry D Marshall Disposal",
        ["Larry D Marshall", "LARRY D MARSHALL"],
        []
    ),
    
    "Marpan Supply": (
        "Marpan Supply",
        ["Marpan", "MARPAN"],
        []
    ),
    
    "Iron City Express": (
        "Iron City Express",
        ["Iron City", "IRON CITY"],
        []
    ),
    
    "Star Waste": (
        "Star Waste",
        ["Star Waste", "STAR WASTE"],
        []
    ),
    
    # =========================================================================
    # SPECIAL CASES / OTHER
    # =========================================================================
    
    "OTHER": (
        "OTHER",
        [],
        []
    ),
    
    "Wasteology": (
        "Wasteology",
        ["Wasteology", "WASTEOLOGY"],
        []
    ),
    
    "G2 Revolution": (
        "G2 Revolution",
        ["G2 Revolution", "G2 REVOLUTION"],
        []
    ),
    
    "J&T Environmental": (
        "J&T Environmental Fleet Services",
        ["J&T Environmental", "J&T ENVIRONMENTAL"],
        ["J&T Environmental Fleet Services"]
    ),
    
    "SA Recycling": (
        "SA Recycling LLC",
        ["SA Recycling", "SA RECYCLING"],
        ["SA Recycling LLC"]
    ),
    
    "Groot Industries": (
        "Waste Connections - Groot Industries",
        ["Groot", "GROOT"],
        ["Waste Connections - Groot Industries"]
    ),
    
    "Ontario Municipal": (
        "Ontario Municipal Utilities Company",
        ["Ontario Municipal", "ONTARIO MUNICIPAL"],
        ["Ontario Municipal Utilities Company"]
    ),
    
    "Smash Franchise": (
        "Smash Franchise Partners",
        ["Smash Franchise", "SMASH FRANCHISE"],
        ["Smash Franchise Partners"]
    ),
    
    "F and L Construction": (
        "F and L Construction Inc",
        ["F and L", "F AND L", "F&L"],
        ["F AND L CONSTRUCTION INC"]
    ),
    
    "GHW Waste": (
        "GHW Waste Services",
        ["GHW", "GHW Waste"],
        ["GHW Waste Services"]
    ),
    
    "Zach Erwin": (
        "Zach Erwin Construction Inc",
        ["Zach Erwin", "ZACH ERWIN"],
        ["Zach Erwin Construction Inc"]
    ),
    
    "Waste Vision": (
        "Waste Vision",
        ["Waste Vision", "WASTE VISION", "WasteVision"],
        []
    ),

    # =========================================================================
    # TIER 10: MISSING VENDORS FROM TRAINING DATA (451 vendors, 10337 invoices)
    # =========================================================================

    "Miami-Dade DSWM": (
        "PANZARELLA",
        ["Miami-Dade DSWM"],
        []
    ),

    "Bruin Waste Management": (
        "Bruin Waste Management",
        ["Bruin Waste Management"],
        []
    ),

    "PRIDE Disposal": (
        "Pride Disposal",
        ["PRIDE Disposal"],
        []
    ),

    "Allstate Equipment Services": (
        "Allstate Equipment Services, LLC",
        ["Allstate Equipment Services"],
        []
    ),

    "E.J. Harrison & Sons": (
        "E.J. HARRISON & SONS, INC",
        ["E.J. Harrison & Sons"],
        []
    ),

    "Efficient Roll-Off & Recycling": (
        "Roll-Off & Recycling, Inc.",
        ["Efficient Roll-Off & Recycling"],
        []
    ),

    "City of Bardstown": (
        "City of Bardstown",
        ["City of Bardstown"],
        []
    ),

    "Haul Away Rubbish": (
        "Haul Away Rubbish Service Co., Inc.",
        ["Haul Away Rubbish"],
        []
    ),

    "HMP Inc": (
        "HMP",
        ["HMP Inc"],
        []
    ),

    "Pete and Pete": (
        "CONTAINER SERVICE, INC.",
        ["Pete and Pete"],
        []
    ),

    "Waste Resources Gardena": (
        "Waste Resources",
        ["Waste Resources Gardena"],
        []
    ),

    "Junk King": (
        "GEORGIA WASTE SYSTEMS, LLC.",
        ["Junk King"],
        []
    ),

    "Hogland's Transfer": (
        "HOGLAND'S",
        ["Hogland's Transfer"],
        []
    ),

    "South Tahoe Refuse": (
        "South Tahoe Refuse & Recycling Services",
        ["South Tahoe Refuse"],
        []
    ),

    "Amber Disposal": (
        "Disposal, LLC.",
        ["Amber Disposal"],
        []
    ),

    "Container Rental Co": (
        "CONTAINER RENTAL CO INC",
        ["Container Rental Co"],
        []
    ),

    "Martin Environmental": (
        "ENVIRONMENTAL SERVICES, INC.",
        ["Martin Environmental"],
        []
    ),

    "Glendale Arizona Utilities": (
        "City of Glendale",
        ["Glendale Arizona Utilities"],
        []
    ),

    "Hughes Trash Removal": (
        "HUGHES TRASH REMOVAL, INC.",
        ["Hughes Trash Removal"],
        []
    ),

    "Disposal Services LLC": (
        "Disposal Services LLC",
        ["Disposal Services LLC"],
        []
    ),

    "Miamitown Auto Parts": (
        "MIAMITOWN AUTO PARTS & RECYCLING INC",
        ["Miamitown Auto Parts"],
        []
    ),

    "Cram-A-Lot": (
        "Cram-A-Lot",
        ["Cram-A-Lot"],
        []
    ),

    "TRASHCO": (
        "TRASHCO",
        ["TRASHCO"],
        []
    ),

    "City of Tulsa": (
        "City of Tulsa",
        ["City of Tulsa"],
        []
    ),

    "NEI Pennsylvania": (
        "NOBLE ENVIRONMENTAL",
        ["NEI Pennsylvania"],
        []
    ),

    "City of Sulphur Springs": (
        "Sulphur Springs",
        ["City of Sulphur Springs"],
        []
    ),

    "Grand Rapids Iron": (
        "Grand Rapids Iron & Metal",
        ["Grand Rapids Iron"],
        []
    ),

    "Appalachian Waste Management": (
        "Appalachian Waste Management LLC",
        ["Appalachian Waste Management"],
        []
    ),

    "Midwest Sanitation": (
        "MIDWEST",
        ["Midwest Sanitation"],
        []
    ),

    "Mt Diablo Resource Recovery": (
        "Mt. Diablo Resource Recovery",
        ["Mt Diablo Resource Recovery"],
        []
    ),

    "Golden Triangle Waste": (
        "Golden Triangle Waste Services",
        ["Golden Triangle Waste"],
        []
    ),

    "CWRR": (
        "Commercial Waste",
        ["CWRR"],
        []
    ),

    "LK Specialties": (
        "LK Specialties, LLC",
        ["LK Specialties"],
        []
    ),

    "Hiltz": (
        "WASTE DISPOSAL",
        ["Hiltz"],
        []
    ),

    "Royal Oak Recycling": (
        "Royal Oak Recycling",
        ["Royal Oak Recycling"],
        []
    ),

    "Hillside Solutions": (
        "Hillside Solutions, LLC",
        ["Hillside Solutions"],
        []
    ),

    "McGree Trucking": (
        "McGree Trucking",
        ["McGree Trucking"],
        []
    ),

    "Madison Materials": (
        "MADISON MATERIALS",
        ["Madison Materials"],
        []
    ),

    "Sunshine Disposal & Recycling": (
        "Sunshine",
        ["Sunshine Disposal & Recycling"],
        []
    ),

    "Keys Sanitary": (
        "Keys Sanitary Service",
        ["Keys Sanitary"],
        []
    ),

    "Junk Removed Now": (
        "JUNK REMOVED",
        ["Junk Removed Now"],
        []
    ),

    "Cedar Grove": (
        "CEDAR GROVE ORGANICS RECYCLING LLC",
        ["Cedar Grove"],
        []
    ),

    "L&L Site Services": (
        "L&L",
        ["L&L Site Services"],
        []
    ),

    "KC Disposal": (
        "KC DISPOSAL",
        ["KC Disposal"],
        []
    ),

    "WM Compactor Solutions": (
        "WM COMPACTOR SOLUTIONS, INC.",
        ["WM Compactor Solutions"],
        []
    ),

    "City of Mesquite": (
        "CITY OF MESQUITE",
        ["City of Mesquite"],
        []
    ),

    "Complete Solutions & Sourcing": (
        "Complete Solutions",
        ["Complete Solutions & Sourcing"],
        []
    ),

    "Escondido Disposal": (
        "ESCONDIDO DISPOSAL INC.",
        ["Escondido Disposal"],
        []
    ),

    "Waste Services Manchester": (
        "Waste Services",
        ["Waste Services Manchester"],
        []
    ),

    "Fayette Waste": (
        "Fayette Waste LLC",
        ["Fayette Waste"],
        []
    ),

    "Sage Disposal": (
        "SAGE",
        ["Sage Disposal"],
        []
    ),

    "Mills Brothers": (
        "MILLS BROTHERS GARBAGE SVC",
        ["Mills Brothers"],
        []
    ),

    "NS Disposal": (
        "N.S. DISPOSAL SERVICE, INC.",
        ["NS Disposal"],
        []
    ),

    "Bridge City Sanitation": (
        "BRIDGE CITY SANITATION LLC",
        ["Bridge City Sanitation"],
        []
    ),

    "Greenway Waste": (
        "Wind River Environmental LLC.",
        ["Greenway Waste"],
        []
    ),

    "Marck Recycling and Waste": (
        "RECYCLING & WASTE",
        ["Marck Recycling and Waste"],
        []
    ),

    "Myers Container Service": (
        "MYERS CONTAINER SERVICE CORP.",
        ["Myers Container Service"],
        []
    ),

    "City of St Anthony": (
        "City of St Anthony",
        ["City of St Anthony"],
        []
    ),

    "Hotchkiss Disposal": (
        "HOTCHKISS DISPOSAL SERVICES, LTD",
        ["Hotchkiss Disposal"],
        []
    ),

    "Roadrunner Rubbish": (
        "Roadrunner Rubbish, LLC.",
        ["Roadrunner Rubbish"],
        []
    ),

    "T & G Sanitation": (
        "T & G Sanitation",
        ["T & G Sanitation"],
        []
    ),

    "Ramona Disposal": (
        "RAMONA DISPOSAL SERVICE",
        ["Ramona Disposal"],
        []
    ),

    "Salt River Pima": (
        "PIMA-",
        ["Salt River Pima"],
        []
    ),

    "California Waste Recovery": (
        "CAL-WASTE CALIFORNIA WASTE RECOVERY",
        ["California Waste Recovery"],
        []
    ),

    "Bozeman MT Utilities": (
        "BOZEMAN",
        ["Bozeman MT Utilities"],
        []
    ),

    "LaVeine Sanitation": (
        "LaVeine Sanitation Service, Inc.",
        ["LaVeine Sanitation"],
        []
    ),

    "Apex Recycling & Disposal": (
        "Apex",
        ["Apex Recycling & Disposal"],
        []
    ),

    "Crane Roll-Off": (
        "Crane Roll-Off",
        ["Crane Roll-Off"],
        []
    ),

    "Lift Waste": (
        "Lift Waste & Recycling",
        ["Lift Waste"],
        []
    ),

    "EZ Disposal": (
        "DISPOSAL SERVICE, INC.",
        ["EZ Disposal"],
        []
    ),

    "Lake Area Disposal": (
        "LAKE AREA DISPOSAL SERVICE, INC.",
        ["Lake Area Disposal"],
        []
    ),

    "Chesapeake Waste": (
        "Chesapeake Waste Industries",
        ["Chesapeake Waste"],
        []
    ),

    "MARS City of Beatrice": (
        "CITY OF BEATRICE",
        ["MARS City of Beatrice"],
        []
    ),

    "Patterson Sanitation": (
        "PATTERSON SANITATION SERVICES",
        ["Patterson Sanitation"],
        []
    ),

    "United Rentals": (
        "United Rentals",
        ["United Rentals"],
        []
    ),

    "City of Sherman": (
        "City of Sherman",
        ["City of Sherman"],
        []
    ),

    "Choice Waste Services": (
        "Choice Waste Services",
        ["Choice Waste Services"],
        []
    ),

    "Cumberland Services": (
        "Cumberland Services, LLC",
        ["Cumberland Services"],
        []
    ),

    "Shank Waste": (
        "SHANK WASTE SERVICE INC",
        ["Shank Waste"],
        []
    ),

    "Green OBKY": (
        "Go Recycling",
        ["Green OBKY"],
        []
    ),

    "Miedema Sanitation": (
        "MIEDEMA Sanitation INC",
        ["Miedema Sanitation"],
        []
    ),

    "City of Hickory": (
        "CITY OF HICKORY",
        ["City of Hickory"],
        []
    ),

    "Forever Clean": (
        "Forever Clean",
        ["Forever Clean"],
        []
    ),

    "Smurfit": (
        "Smurfit Westrock",
        ["Smurfit"],
        []
    ),

    "Bulldog Disposal": (
        "Bulldog Disposal & Recycling, Inc.",
        ["Bulldog Disposal"],
        []
    ),

    "Kamps Pallets": (
        "KAMPS",
        ["Kamps Pallets"],
        []
    ),

    "City of Tullahoma": (
        "City of Tullahoma",
        ["City of Tullahoma"],
        []
    ),

    "Roadrunner Sanitation": (
        "Roadrunner Sanitation",
        ["Roadrunner Sanitation"],
        []
    ),

    "Pacific Sanitation Co": (
        "Pacific Sanitation Inc.",
        ["Pacific Sanitation Co"],
        []
    ),

    "Citrus County Utilities": (
        "WASTE PRO",
        ["Citrus County Utilities"],
        []
    ),

    "Oregon City Garbage": (
        "MOLALLA SANITARY SERVICE",
        ["Oregon City Garbage"],
        []
    ),

    "Lemhi Sanitation": (
        "Lemhi Sanitation",
        ["Lemhi Sanitation"],
        []
    ),

    "Cogent Waste Solutions": (
        "COGENT WASTE SOLUTIONS LLC",
        ["Cogent Waste Solutions"],
        []
    ),

    "P&M Reis Trucking": (
        "P & M Reis Trucking",
        ["P&M Reis Trucking"],
        []
    ),

    "Rubatino Refuse": (
        "REFUSE REMOVAL LLC.",
        ["Rubatino Refuse"],
        []
    ),

    "City of Great Falls": (
        "City of Great Falls",
        ["City of Great Falls"],
        []
    ),

    "Joseph J. Runner": (
        "JOSEPH J. BRUNNER, INC.",
        ["Joseph J. Runner"],
        []
    ),

    "Pro Disposal": (
        "PRO DISPOSAL, INC.",
        ["Pro Disposal"],
        []
    ),

    "Miles City Sanitation": (
        "Miles City Sanitation",
        ["Miles City Sanitation"],
        []
    ),

    "Diamond Disposal": (
        "The Diamond Disposal, Inc",
        ["Diamond Disposal"],
        []
    ),

    "Express Disposal": (
        "EXPRESS DISPOSAL & RECYCLING LLC",
        ["Express Disposal"],
        []
    ),

    "City of Fayette": (
        "City of Fayette",
        ["City of Fayette"],
        []
    ),

    "Olathe Kansas": (
        "City of Olathe",
        ["Olathe Kansas"],
        []
    ),

    "Golden Environmental": (
        "GOLDEN ENVIRONMENTAL, LLC",
        ["Golden Environmental"],
        []
    ),

    "HBS Denver": (
        "HBS",
        ["HBS Denver"],
        []
    ),

    "Waste Advantage": (
        "Waste Advantage",
        ["Waste Advantage"],
        []
    ),

    "NVA Services": (
        "NASA",
        ["NVA Services"],
        []
    ),

    "City of Grand Junction": (
        "City of Grand Junction",
        ["City of Grand Junction"],
        []
    ),

    "Suburban Disposal": (
        "SUBURBAN DISPOSAL",
        ["Suburban Disposal"],
        []
    ),

    "JD Parker": (
        "DP",
        ["JD Parker"],
        []
    ),

    "DC Waste": (
        "Waste & Recycling",
        ["DC Waste"],
        []
    ),

    "Lex Serv": (
        "LEXINGTON",
        ["Lex Serv"],
        []
    ),

    "Porter Trash": (
        "Porter Trash Service",
        ["Porter Trash"],
        []
    ),

    "Serv-Wel Disposal": (
        "DISPOSAL AND RECYCLING and its subsidiary",
        ["Serv-Wel Disposal"],
        []
    ),

    "Cressman Sanitation": (
        "Cressman Sanitation",
        ["Cressman Sanitation"],
        []
    ),

    "Ridgerunner Container": (
        "Ridgerunner Container",
        ["Ridgerunner Container"],
        []
    ),

    "Reliable Paper Recycling": (
        "Reliable Paper Recycling",
        ["Reliable Paper Recycling"],
        []
    ),

    "Olson Sanitation": (
        "Olson Sanitation Inc",
        ["Olson Sanitation"],
        []
    ),

    "Best Pick Disposal": (
        "BEST PICK DISPOSAL INC",
        ["Best Pick Disposal"],
        []
    ),

    "R-Local Sanitation": (
        "R-Local Sanitation",
        ["R-Local Sanitation"],
        []
    ),

    "Rapid Removal": (
        "Rapid Removal Disposal",
        ["Rapid Removal"],
        []
    ),

    "City of Dickinson": (
        "City of Dickinson",
        ["City of Dickinson"],
        []
    ),

    "Pullman Disposal": (
        "Pullman Disposal",
        ["Pullman Disposal"],
        []
    ),

    "Napa Recycling": (
        "NAPA RECYCLING & WASTE SERVICES, LLC",
        ["Napa Recycling"],
        []
    ),

    "Shawnee County Solid Waste": (
        "SHAWNEE COUNTY SOLID WASTE DEPARTMENT",
        ["Shawnee County Solid Waste"],
        []
    ),

    "City of Mesa": (
        "Mesa",
        ["City of Mesa"],
        []
    ),

    "Fogle's": (
        "FOGLE'S",
        ["Fogle's"],
        []
    ),

    "Denali Disposal": (
        "DENALI REFUSE",
        ["Denali Disposal"],
        []
    ),

    "Sonoco Recycling": (
        "Sonoco Recycling, LLC",
        ["Sonoco Recycling"],
        []
    ),

    "Capital City": (
        "CAPITAL CITY Refuse",
        ["Capital City"],
        []
    ),

    "Rhino Waste": (
        "RHINO WASTE & RECYCLING, INC.",
        ["Rhino Waste"],
        []
    ),

    "Hale County Public Works": (
        "Hale County Public Works",
        ["Hale County Public Works"],
        []
    ),

    "Sutton Disposal": (
        "Sutton Disposal Service, LLC",
        ["Sutton Disposal"],
        []
    ),

    "Heartland Waste Management": (
        "Heartland Waste Management, Inc.",
        ["Heartland Waste Management"],
        []
    ),

    "Elite Recycling": (
        "Elite Recycling & Disposal",
        ["Elite Recycling"],
        []
    ),

    "Shular's Trash Service": (
        "SHULAR'S TRASH SERVICE, LLC",
        ["Shular's Trash Service"],
        []
    ),

    "City of Fort Smith": (
        "City of Fort Smith",
        ["City of Fort Smith"],
        []
    ),

    "Palm Springs Disposal": (
        "Palm Springs Disposal Services",
        ["Palm Springs Disposal"],
        []
    ),

    "Quincy Recycling": (
        "Quincy RECYCLE",
        ["Quincy Recycling"],
        []
    ),

    "Florida Waste Solutions": (
        "Florida Waste Solutions, LLC",
        ["Florida Waste Solutions"],
        []
    ),

    "City of Oakland Park": (
        "OAKLAND PARK",
        ["City of Oakland Park"],
        []
    ),

    "Empire Recycling Corporation": (
        "Empire Recycling Corporation",
        ["Empire Recycling Corporation"],
        []
    ),

    "Mazza Recycling": (
        "MAZZA",
        ["Mazza Recycling"],
        []
    ),

    "Kurtzman's Sanitation": (
        "Kurtzman's Sanitation",
        ["Kurtzman's Sanitation"],
        []
    ),

    "Mike Spano & Sons": (
        "Mike Spano & Sons, Inc.",
        ["Mike Spano & Sons"],
        []
    ),

    "Stewart Sanitation": (
        "Stewart Sanitation",
        ["Stewart Sanitation"],
        []
    ),

    "Smoky Mountain Waste": (
        "Smoky Mountain Waste, LLC",
        ["Smoky Mountain Waste"],
        []
    ),

    "Eastern Waste": (
        "EASTERN WASTE DISPOSAL",
        ["Eastern Waste"],
        []
    ),

    "City of Nampa": (
        "City of Nampa",
        ["City of Nampa"],
        []
    ),

    "Niese Hauling": (
        "Niese Hauling",
        ["Niese Hauling"],
        []
    ),

    "Emterra Environmental": (
        "Emterra Environmental USA Corp",
        ["Emterra Environmental"],
        []
    ),

    "Jettison Environmental": (
        "Jettison Environmental",
        ["Jettison Environmental"],
        []
    ),

    "Steve's Sanitation": (
        "Steve's Sanitation",
        ["Steve's Sanitation"],
        []
    ),

    "Local Waste Solution": (
        "Local Waste Solution",
        ["Local Waste Solution"],
        []
    ),

    "McCullough Rubbish": (
        "McCullough Rubbish",
        ["McCullough Rubbish"],
        []
    ),

    "City of Tracy": (
        "CITY OF TRACY",
        ["City of Tracy"],
        []
    ),

    "Jim's Sanitation": (
        "Jim's Sanitation and Truck Repair",
        ["Jim's Sanitation"],
        []
    ),

    "Pacific Disposal": (
        "PACIFIC DISPOSAL",
        ["Pacific Disposal"],
        []
    ),

    "City of Foley": (
        "City of Foley",
        ["City of Foley"],
        []
    ),

    "City of Wolf Point": (
        "CITY OF WOLF POINT",
        ["City of Wolf Point"],
        []
    ),

    "Goode Companies": (
        "GOODE COMPANIES, INC.",
        ["Goode Companies"],
        []
    ),

    "Barbarino Disposal": (
        "Disposal & Recycling",
        ["Barbarino Disposal"],
        []
    ),

    "Marick's Waste Disposal": (
        "MARICK'S WASTE DISPOSAL INC.",
        ["Marick's Waste Disposal"],
        []
    ),

    "City of Douglasville": (
        "City of Douglasville",
        ["City of Douglasville"],
        []
    ),

    "Okon Recycling": (
        "Okon Recycling",
        ["Okon Recycling"],
        []
    ),

    "City of Winters": (
        "WINTERS BRAS.",
        ["City of Winters"],
        []
    ),

    "Control Waste": (
        "CONTROL WASTE SERVICES, LLC",
        ["Control Waste"],
        []
    ),

    "City of Emporia": (
        "Emporia City of Emporia",
        ["City of Emporia"],
        []
    ),

    "Engebretson & Sons": (
        "SCHAAP SANITATION",
        ["Engebretson & Sons"],
        []
    ),

    "Hughes & Sons": (
        "Hughes & Sons, Inc",
        ["Hughes & Sons"],
        []
    ),

    "Weaver's Sanitation": (
        "Weaver's Sanitation Svc, Inc.",
        ["Weaver's Sanitation"],
        []
    ),

    "Timberline LLC": (
        "Timberline LLC",
        ["Timberline LLC"],
        []
    ),

    "Long Beach Container": (
        "Long Beach Container Co.",
        ["Long Beach Container"],
        []
    ),

    "Greenbrier Valley Solid Waste": (
        "Greenbrier Valley Solid Waste Inc",
        ["Greenbrier Valley Solid Waste"],
        []
    ),

    "Friends Garbage": (
        "Friends Garbage",
        ["Friends Garbage"],
        []
    ),

    "City of Lamar": (
        "City of Lamar",
        ["City of Lamar"],
        []
    ),

    "Paso Robles Waste": (
        "Paso Robles Waste&",
        ["Paso Robles Waste"],
        []
    ),

    "City of Richardson": (
        "CITY OF RICHARDSON",
        ["City of Richardson"],
        []
    ),

    "H-Town Hauling": (
        "HAULING COMPANY",
        ["H-Town Hauling"],
        []
    ),

    "City of Bakersfield": (
        "City of Bakersfield",
        ["City of Bakersfield"],
        []
    ),

    "Texas Commercial Waste": (
        "TEXAS COMMERCIAL WASTE",
        ["Texas Commercial Waste"],
        []
    ),

    "DC Metals": (
        "DC Metals, Inc.",
        ["DC Metals"],
        []
    ),

    "Tahoe Truckee Sierra Disposal": (
        "Tahoe Truckee Sierra Disposal",
        ["Tahoe Truckee Sierra Disposal"],
        []
    ),

    "Gear For Waste": (
        "Gear For Waste LLC",
        ["Gear For Waste"],
        []
    ),

    "R&S Waste": (
        "R & SWASTE DISPOSAL",
        ["R&S Waste"],
        []
    ),

    "Golden Valley Disposal": (
        "Golden Valley Disposal, LLC",
        ["Golden Valley Disposal"],
        []
    ),

    "Triple H Enterprises": (
        "TRIPLE H ENTERPRISES LLC",
        ["Triple H Enterprises"],
        []
    ),

    "Bright Disposal Services": (
        "Bright Disposal Services, LLC.",
        ["Bright Disposal Services"],
        []
    ),

    "Solomon Container Service": (
        "SCS",
        ["Solomon Container Service"],
        []
    ),

    "Garden State Waste Management": (
        "Garden State Waste Management",
        ["Garden State Waste Management"],
        []
    ),

    "Waste Eliminator": (
        "WASTE ELIMINATOR LLC",
        ["Waste Eliminator"],
        []
    ),

    "Perdue Environmental": (
        "PERDUE ENVIRONMENTAL CONTRACTING COMPANY, INC.",
        ["Perdue Environmental"],
        []
    ),

    "Abe's Trash Service": (
        "ABE'S TRASH SERVICE, INC.",
        ["Abe's Trash Service"],
        []
    ),

    "Snake River Dispose-All": (
        "Snake River Dispose-All, Inc.",
        ["Snake River Dispose-All"],
        []
    ),

    "Lake Disposal Service": (
        "Lake Disposal Service of Northern Ohio",
        ["Lake Disposal Service"],
        []
    ),

    "Georgetown Paper Stock": (
        "Georgetown Paper Stock of Rockville, Inc.",
        ["Georgetown Paper Stock"],
        []
    ),

    "Nisswa Sanitation": (
        "NISSWA SANITATION INC",
        ["Nisswa Sanitation"],
        []
    ),

    "Moler Sanitation": (
        "MOLER SANITATION",
        ["Moler Sanitation"],
        []
    ),

    "Minnkota Recycling": (
        "MinnKota",
        ["Minnkota Recycling"],
        []
    ),

    "Panola County Solid Waste": (
        "PANOLA COUNTY SOLID WASTE",
        ["Panola County Solid Waste"],
        []
    ),

    "Cheyenne Board of Public Utilities": (
        "Board of Public Utilities",
        ["Cheyenne Board of Public Utilities"],
        []
    ),

    "Elecke": (
        "LECK WASTE SERVICES",
        ["Elecke"],
        []
    ),

    "City of Sallisaw": (
        "City of Sallisaw",
        ["City of Sallisaw"],
        []
    ),

    "Hilltopper Refuse": (
        "HILLTOPPER REFUSE & RECYCLING SVC. INC.",
        ["Hilltopper Refuse"],
        []
    ),

    "Ozark Disposal": (
        "Ozark Disposal Company",
        ["Ozark Disposal"],
        []
    ),

    "Southwest Sanitation": (
        "SS Southwest Sanitation",
        ["Southwest Sanitation"],
        []
    ),

    "Nooksack Valley Disposal": (
        "Nooksack Valley Disposal",
        ["Nooksack Valley Disposal"],
        []
    ),

    "Douglas Disposal": (
        "DOUGLAS DISPOSAL INC",
        ["Douglas Disposal"],
        []
    ),

    "Jim Dedman's Sanitation": (
        "Jim Dedman's Sanitation",
        ["Jim Dedman's Sanitation"],
        []
    ),

    "Central Valley Disposal": (
        "CENTRAL VALLEY DISPOSAL",
        ["Central Valley Disposal"],
        []
    ),

    "Dan's Sanitation": (
        "Dan's Sanitation, Inc.",
        ["Dan's Sanitation"],
        []
    ),

    "Dayne's Waste Disposal": (
        "DAYNE'S WASTE DISPOSAL, INC",
        ["Dayne's Waste Disposal"],
        []
    ),

    "Howie's Trash Service": (
        "HOWIE'S TRASH SERVICE",
        ["Howie's Trash Service"],
        []
    ),

    "City of McDonough": (
        "City of McDonough",
        ["City of McDonough"],
        []
    ),

    "City of Athens GA": (
        "City of Athens",
        ["City of Athens GA"],
        []
    ),

    "Buldo Container & Disposal": (
        "CONTAINER & DISPOSAL",
        ["Buldo Container & Disposal"],
        []
    ),

    "City of Kirkland": (
        "CITY OF KIRKLAND UTILITY BILLING",
        ["City of Kirkland"],
        []
    ),

    "South San Francisco Scavenger": (
        "SCAVENGER",
        ["South San Francisco Scavenger"],
        []
    ),

    "Breezy Hollow": (
        "Breezy Hollow",
        ["Breezy Hollow"],
        []
    ),

    "Dedicated Dumpster Service": (
        "DDS",
        ["Dedicated Dumpster Service"],
        []
    ),

    "Klumm Brothers": (
        "Klumm Brothers Waste Solutions",
        ["Klumm Brothers"],
        []
    ),

    "Ely Disposal Service": (
        "ELY DISPOSAL SERVICE INC",
        ["Ely Disposal Service"],
        []
    ),

    "Anchor Technical": (
        "Anchor Technical Services, LLC",
        ["Anchor Technical"],
        []
    ),

    "Seadrunar Recycling": (
        "Seadrunar",
        ["Seadrunar Recycling"],
        []
    ),

    "City of Culver City": (
        "CITY OF CULVER CITY",
        ["City of Culver City"],
        []
    ),

    "Metech Recycling": (
        "Metech Recycling, Inc.",
        ["Metech Recycling"],
        []
    ),

    "Full Circle Recycling": (
        "Full Circle",
        ["Full Circle Recycling"],
        []
    ),

    "City of Temple TX": (
        "CITY OF TEMPLE",
        ["City of Temple TX"],
        []
    ),

    "Kluesner Sanitation": (
        "SANITATION LLC",
        ["Kluesner Sanitation"],
        []
    ),

    "Kalamazoo Transfer Station": (
        "KALAMAZOO TRANSFER STATION - 3080",
        ["Kalamazoo Transfer Station"],
        []
    ),

    "Junk Solutions": (
        "JUNK SOLUTIONS HAULING AND REMOVAL",
        ["Junk Solutions"],
        []
    ),

    "City of Madisonville": (
        "Madisonville Municipal",
        ["City of Madisonville"],
        []
    ),

    "Step Up Disposals": (
        "STEP UP DISPOSALS",
        ["Step Up Disposals"],
        []
    ),

    "Pratt Sanitation": (
        "Pratt Sanitation Inc.",
        ["Pratt Sanitation"],
        []
    ),

    "R&R Recycling Inc": (
        "R&R RECYCLING, INC",
        ["R&R Recycling Inc"],
        []
    ),

    "Enevo": (
        "Enevo, Inc.",
        ["Enevo"],
        []
    ),

    "Tacoma Public Utilities": (
        "SOLID WASTE MANAGEMENT",
        ["Tacoma Public Utilities", "City of Tacoma"],
        ["City of Tacoma Public Utilities"]
    ),

    "Lance Refuse": (
        "Lance Refuse Service Inc",
        ["Lance Refuse"],
        []
    ),

    "Town of Apple Valley": (
        "The Town of Apple Valley",
        ["Town of Apple Valley"],
        ["Burrtec Waste - Town of Apple Valley"]
    ),

    "New Prague Sanitary": (
        "Lakers NEW PRAGUE SANITARY INC",
        ["New Prague Sanitary"],
        []
    ),

    "Real Waste Solutions": (
        "Real Waste Solutions. LLC.",
        ["Real Waste Solutions"],
        []
    ),

    "City of Del Rio": (
        "City of Del Rio",
        ["City of Del Rio"],
        []
    ),

    "City of Visalia": (
        "City of Visalia",
        ["City of Visalia"],
        []
    ),

    "Helgerson Property Maintenance": (
        "Helgerson Property Maintenance",
        ["Helgerson Property Maintenance"],
        []
    ),

    "Humpty Dumpsters": (
        "HUMPTY DUMPSTERS",
        ["Humpty Dumpsters"],
        []
    ),

    "City of Somerset": (
        "Somerset Utilities",
        ["City of Somerset"],
        []
    ),

    "Olcese Waste Services": (
        "Olcese Waste Services, Inc.",
        ["Olcese Waste Services"],
        []
    ),

    "Recycling Center of North Dakota": (
        "Recycling Center of North Dakota, LLC",
        ["Recycling Center of North Dakota"],
        []
    ),

    "Davis Disposal": (
        "Davis Disposal",
        ["Davis Disposal"],
        []
    ),

    "Mountain Disposal Inc": (
        "MOUNTAIN DISPOSAL, INC.",
        ["Mountain Disposal Inc"],
        []
    ),

    "Pike County Solid Waste": (
        "PIKE COUNTY SOLID WASTE DEPARTMENT",
        ["Pike County Solid Waste"],
        []
    ),

    "Hepaco": (
        "HEPACO",
        ["Hepaco"],
        []
    ),

    "CompostNow": (
        "CompostNow Inc.",
        ["CompostNow"],
        []
    ),

    "Pendleton Sanitary Service": (
        "Pendleton Sanitary Service, Inc.",
        ["Pendleton Sanitary Service"],
        []
    ),

    "Madden Sanitation": (
        "Madden Sanitation Inc",
        ["Madden Sanitation"],
        []
    ),

    "Coastal Environmental Service": (
        "Coastal Environmental Services of LA LLC",
        ["Coastal Environmental Service"],
        []
    ),

    "Mackenzie Disposal": (
        "MACKENZIE DISPOSAL, INC.",
        ["Mackenzie Disposal"],
        []
    ),

    "City of Sidney": (
        "City of Sidney",
        ["City of Sidney"],
        []
    ),

    "Eagle Equipment Corporation": (
        "EAGLE EQUIPMENT CORPORATION",
        ["Eagle Equipment Corporation"],
        []
    ),

    "Gardner Disposal Service": (
        "GARDNER DISPOSAL SERVICE, INC",
        ["Gardner Disposal Service"],
        []
    ),

    "Pyles Demolition Recycling": (
        "Pyles Demolition Recycling",
        ["Pyles Demolition Recycling"],
        []
    ),

    "Pluffmud Recycling": (
        "Pluffmud",
        ["Pluffmud Recycling"],
        []
    ),

    "Maverick Waste": (
        "Maverick Waste Systems",
        ["Maverick Waste"],
        []
    ),

    "Clark's Disposal": (
        "Clark's Disposal Inc.",
        ["Clark's Disposal"],
        []
    ),

    "Cook Maintenance": (
        "Cook Maintenance",
        ["Cook Maintenance"],
        []
    ),

    "City of Green River": (
        "City of Green River",
        ["City of Green River"],
        []
    ),

    "Wright's Environmental": (
        "Wright's Environmental",
        ["Wright's Environmental"],
        []
    ),

    "Eco Sanitation": (
        "Eco Sanitation LLC",
        ["Eco Sanitation"],
        []
    ),

    "Dugger Trash Service": (
        "DUGGER TRASH SERVICE",
        ["Dugger Trash Service"],
        []
    ),

    "Capital Area Refuse": (
        "Capital Area Refuse LLC/River Bottom Sa",
        ["Capital Area Refuse"],
        []
    ),

    "Dillon Disposal": (
        "Dillon Disposal LLC",
        ["Dillon Disposal"],
        []
    ),

    "Volunteer Disposal West": (
        "Volunteer Disposal West",
        ["Volunteer Disposal West"],
        []
    ),

    "Solid Rock Waste": (
        "Solid Rock Waste LLC",
        ["Solid Rock Waste"],
        []
    ),

    "Jackson County Solid Waste": (
        "Jackson County Solid Waste",
        ["Jackson County Solid Waste"],
        []
    ),

    "Ferrell's Disposal": (
        "Ferrell's Disposal Service",
        ["Ferrell's Disposal"],
        []
    ),

    "D&S Portable Toilets": (
        "Portable Toilets, LLC",
        ["D&S Portable Toilets"],
        []
    ),

    "Ogborne Hauling": (
        "Ogborne Hauling Inc.",
        ["Ogborne Hauling"],
        []
    ),

    "Canusa Hershman": (
        "CANUSA HERSHMAN RECYCLING OF ARIZONA, LLC",
        ["Canusa Hershman"],
        []
    ),

    "Happy Can Disposal": (
        "Happy Can Disposal",
        ["Happy Can Disposal"],
        []
    ),

    "Martin's Trash Service": (
        "Martin's Trash Service",
        ["Martin's Trash Service"],
        []
    ),

    "City of Lakeland FL": (
        "Lakeland",
        ["City of Lakeland FL"],
        []
    ),

    "Scraps Compost": (
        "Scraps",
        ["Scraps Compost"],
        []
    ),

    "Norris Sanitation": (
        "NORRIS C SANITATION, LLC",
        ["Norris Sanitation"],
        []
    ),

    "Maui Disposal Co": (
        "Maui Disposal Co., Inc.",
        ["Maui Disposal Co"],
        []
    ),

    "J&Jay Services": (
        "J & Jay Services",
        ["J&Jay Services"],
        []
    ),

    "Brothers Disposal": (
        "Brothers Disposal",
        ["Brothers Disposal"],
        []
    ),

    "City of Quincy": (
        "CITY OF QUINCY",
        ["City of Quincy"],
        []
    ),

    "Rockwood Sustainable Solutions": (
        "Rockwood Sustainable Solutions LLC",
        ["Rockwood Sustainable Solutions"],
        []
    ),

    "City of Durant": (
        "City of Durant",
        ["City of Durant"],
        []
    ),

    "TDS LLC": (
        "TDS, LLC",
        ["TDS LLC"],
        []
    ),

    "City of Cartersville": (
        "CITY OF CARTERSVILLE",
        ["City of Cartersville"],
        []
    ),

    "ABS Sanitation": (
        "ABS Sanitation",
        ["ABS Sanitation"],
        []
    ),

    "City of Sevierville": (
        "CITY OF SEVIERVILLE",
        ["City of Sevierville"],
        []
    ),

    "T-Mac Inc": (
        "T-MAC, INC.",
        ["T-Mac Inc"],
        []
    ),

    "Southern Disposal AR": (
        "SOUTHERN DISPOSAL",
        ["Southern Disposal AR"],
        []
    ),

    "Kohlmorgan Hauling": (
        "KOHLMORGAN HAULING",
        ["Kohlmorgan Hauling"],
        []
    ),

    "Omni": (
        "Omni",
        ["Omni"],
        []
    ),

    "Document Destruction of Virginia": (
        "Document Destruction of Virginia, LLC",
        ["Document Destruction of Virginia"],
        []
    ),

    "City of Scottsbluff": (
        "CITY OF SCOTTSBLUFF",
        ["City of Scottsbluff"],
        []
    ),

    "City of Snellville": (
        "City of Snellville Public Works Department",
        ["City of Snellville"],
        []
    ),

    "City of Winfield": (
        "CITY OF WINFIELD - SOLID WASTE",
        ["City of Winfield"],
        []
    ),

    "City of Devils Lake": (
        "City of Devils Lake",
        ["City of Devils Lake"],
        []
    ),

    "Coles County Sanitation": (
        "Coles County Sanitation & Recycling, Inc",
        ["Coles County Sanitation"],
        []
    ),

    "Sunrise Sanitation Service": (
        "Sunrise Sanitation Service, Inc.",
        ["Sunrise Sanitation Service"],
        []
    ),

    "Nauset Disposal": (
        "NAUSET DISPOSAL HOLDINGS, INC.",
        ["Nauset Disposal"],
        []
    ),

    "Hamilton Recycling Disposal": (
        "Hamilton Recycling & Disposal",
        ["Hamilton Recycling Disposal"],
        []
    ),

    "DuMontelle Waste": (
        "WASTE",
        ["DuMontelle Waste"],
        []
    ),

    "Gresham Sanitary Service": (
        "GSS",
        ["Gresham Sanitary Service"],
        []
    ),

    "Reliable Paper": (
        "Reliable Paper Recycling, Inc.",
        ["Reliable Paper"],
        []
    ),

    "Westside Waste Management": (
        "Westside Waste",
        ["Westside Waste Management"],
        []
    ),

    "D&S Waste": (
        "D&S WASTE REMOVAL, INC.",
        ["D&S Waste"],
        []
    ),

    "Industrial Waste & Salvage": (
        "Industrial Waste & Salvage",
        ["Industrial Waste & Salvage"],
        []
    ),

    "Midwest Disposal IL": (
        "MIDWEST DISPOSAL",
        ["Midwest Disposal IL"],
        []
    ),

    "Desert Green Disposal": (
        "Desert Green Disposal and Industrial LLC",
        ["Desert Green Disposal"],
        []
    ),

    "Copper State Sanitation": (
        "COPPER STATE SANITATION, INC.",
        ["Copper State Sanitation"],
        []
    ),

    "City of Colby": (
        "CITY OF COLBY",
        ["City of Colby"],
        []
    ),

    "East Central Kansas": (
        "EAST CENTRAL KANSAS REFUSE",
        ["East Central Kansas"],
        []
    ),

    "All State Waste Inc": (
        "ALL STATE WASTE",
        ["All State Waste Inc"],
        []
    ),

    "EarthSavers": (
        "EarthSavers, LLC",
        ["EarthSavers"],
        []
    ),

    "Hillsboro Garbage Disposal": (
        "Hillsboro Garbage Disposal",
        ["Hillsboro Garbage Disposal"],
        []
    ),

    "Industrial Services Lincoln": (
        "Industrial Services, Inc",
        ["Industrial Services Lincoln"],
        []
    ),

    "Darob": (
        "Darob, Inc.",
        ["Darob"],
        []
    ),

    "Garland County Landfill": (
        "GARLAND COUNTY LANDFILL",
        ["Garland County Landfill"],
        []
    ),

    "City of Craig": (
        "City of Craig",
        ["City of Craig"],
        []
    ),

    "Miller Enterprises": (
        "Miller Enterprises Inc",
        ["Miller Enterprises"],
        []
    ),

    "Gilton Solid Waste": (
        "Gilton Solid Waste",
        ["Gilton Solid Waste"],
        []
    ),

    "North Lincoln Sanitary": (
        "North Lincoln Sanitary Service",
        ["North Lincoln Sanitary"],
        []
    ),

    "Food To Power": (
        "Food To Power",
        ["Food To Power"],
        []
    ),

    "CWSI": (
        "Controlled Waste Systems Inc.",
        ["CWSI"],
        []
    ),

    "Chum Refuse": (
        "CH UM REFUSE",
        ["Chum Refuse"],
        []
    ),

    "City of Laramie": (
        "City of Laramie",
        ["City of Laramie"],
        []
    ),

    "CDA Garbage": (
        "Coeur d' Alene",
        ["CDA Garbage"],
        []
    ),

    "Golden Eagle Services": (
        "Golden Eagle",
        ["Golden Eagle Services"],
        []
    ),

    "Missoula Compost": (
        "Missoula Compost LLC",
        ["Missoula Compost"],
        []
    ),

    "Roseburg Disposal": (
        "ROSEBURG DISPOSAL COMPANY",
        ["Roseburg Disposal"],
        []
    ),

    "Dyersburg Gas & Water": (
        "Dyersburg Gas",
        ["Dyersburg Gas & Water"],
        []
    ),

    "Town of Lake Park": (
        "TOWN OF LAKE PARK",
        ["Town of Lake Park"],
        []
    ),

    "Enviromax Recycling": (
        "After Hours Cleaning",
        ["Enviromax Recycling"],
        []
    ),

    "City of Rolla": (
        "City of Rolla",
        ["City of Rolla"],
        []
    ),

    "Wayn-O's Disposal Service": (
        "WAYN-O'S DISPOSAL SERVICE LLC.",
        ["Wayn-O's Disposal Service"],
        []
    ),

    "Franklin Disposal": (
        "Franklin Disposal",
        ["Franklin Disposal"],
        []
    ),

    "North Country Disposal": (
        "NORTH COUNTRY",
        ["North Country Disposal"],
        []
    ),

    "City of Socorro": (
        "CITY OF SOCORRO",
        ["City of Socorro"],
        []
    ),

    "CTL Washington": (
        "CTL Washington",
        ["CTL Washington"],
        []
    ),

    "Lakeland Disposal WI": (
        "LAKELAND DISPOSAL",
        ["Lakeland Disposal WI"],
        []
    ),

    "J&R Sanitation": (
        "J & R Sanitation, LLC",
        ["J&R Sanitation"],
        []
    ),

    "City of Mont Belvieu": (
        "City of Mont Belvieu",
        ["City of Mont Belvieu"],
        []
    ),

    "Empire Disposal": (
        "EMPIRE DISPOSAL, INC.",
        ["Empire Disposal"],
        []
    ),

    "Durflinger Disposal Service": (
        "DURFLINGER DISPOSAL SERVICE, INC.",
        ["Durflinger Disposal Service"],
        []
    ),

    "Snake River Rubbish": (
        "Snake River Rubbish, LLC",
        ["Snake River Rubbish"],
        []
    ),

    "MDS Waste": (
        "MDS Waste & Recycle, INC",
        ["MDS Waste"],
        []
    ),

    "Gil's Sanitation": (
        "Gil's Sanitation Inc.",
        ["Gil's Sanitation"],
        []
    ),

    "Liberty Ashes": (
        "LIBERTY ASHES INC.",
        ["Liberty Ashes"],
        []
    ),

    "City of Gainesville TX": (
        "City of Gainesville",
        ["City of Gainesville TX"],
        []
    ),

    "Horn Sanitation": (
        "Horn Sanitation Inc",
        ["Horn Sanitation"],
        []
    ),

    "Mountain High Disposal": (
        "Mountain High",
        ["Mountain High Disposal"],
        []
    ),

    "Sunny Trash Hauling": (
        "Sunny Trash Hauling",
        ["Sunny Trash Hauling"],
        []
    ),

    "Cowboy Sanitation": (
        "Cowboy Sanitation",
        ["Cowboy Sanitation"],
        []
    ),

    "Sound Disposal Inc": (
        "Sound Disposal Inc.",
        ["Sound Disposal Inc"],
        []
    ),

    "Nisly Brothers": (
        "NISLY",
        ["Nisly Brothers"],
        []
    ),

    "Centre Water Works": (
        "Centre Water Works & Sewer Board",
        ["Centre Water Works"],
        []
    ),

    "Walker Garbage and Recycling": (
        "WALKER",
        ["Walker Garbage and Recycling"],
        []
    ),

    "Mauldin Trash": (
        "MAULDIN TRASH, INC. -- #2",
        ["Mauldin Trash"],
        []
    ),

    "Wampler Services": (
        "Wampler Services, Inc.",
        ["Wampler Services"],
        []
    ),

    "Standing Rock Sanitation": (
        "Standing Rock Sanitation Service, Inc.",
        ["Standing Rock Sanitation"],
        []
    ),

    "Revolution Recycling": (
        "Revolution Recycling",
        ["Revolution Recycling"],
        []
    ),

    "Brookings Dumpster Service": (
        "BROOKINGS",
        ["Brookings Dumpster Service"],
        []
    ),

    "C & D Disposal": (
        "C&D Disposal",
        ["C&D Disposal", "C & D Disposal"],
        ["C&D Disposal"]
    ),

    "C&S Disposal": (
        "C & S Disposal, Inc.",
        ["C&S Disposal"],
        []
    ),

    "Deep South Sanitation": (
        "Deep South Sanitation LLC",
        ["Deep South Sanitation"],
        []
    ),

    "Delta Garbage Service": (
        "Delta Garbage Service",
        ["Delta Garbage Service"],
        []
    ),

    "Edward Arnold Scrap Processors": (
        "EDWARD ARNOLD SCRAP PROCESSORS, INC.",
        ["Edward Arnold Scrap Processors"],
        []
    ),

    "Mid-Ohio Sanitation & Recycling": (
        "Mid-Ohio Sanitation & Recycling LLC",
        ["Mid-Ohio Sanitation & Recycling"],
        []
    ),

    "City of Loganville": (
        "CITY OF LOGANVILLE",
        ["City of Loganville"],
        []
    ),

    "Roberts Enterprises": (
        "ROBERTS ENTERPRISES, INC.",
        ["Roberts Enterprises"],
        []
    ),

    "Miller and Sons Disposal": (
        "Miller and Sons Disposal",
        ["Miller and Sons Disposal"],
        []
    ),

    "United Waste Systems": (
        "United Waste Systems",
        ["United Waste Systems"],
        []
    ),

    "Delta Disposal": (
        "DELTA DISPOSAL",
        ["Delta Disposal"],
        []
    ),

    "Edge Waste": (
        "Edge Waste",
        ["Edge Waste"],
        []
    ),

    "City of Mount Vernon WA": (
        "City of Mount Vernon",
        ["City of Mount Vernon WA"],
        []
    ),

    "Franklin Pallet": (
        "FRANKLIN PALLET INC.",
        ["Franklin Pallet"],
        []
    ),

    "Bud's Clean Up Service": (
        "Bud's Clean Up",
        ["Bud's Clean Up Service"],
        []
    ),

    "Ed's Disposal": (
        "ED'S",
        ["Ed's Disposal"],
        []
    ),

    "Generated Materials Recovery": (
        "Champion Acquisition LLC",
        ["Generated Materials Recovery"],
        []
    ),

    "Checksammy": (
        "Check Sammy",
        ["Checksammy"],
        []
    ),

    "LCI Services": (
        "LCI SERVICES DUMPSTER RENTALS",
        ["LCI Services"],
        []
    ),

    "Town of Limon": (
        "TOWN OF LIMON",
        ["Town of Limon"],
        []
    ),

    "Southern Oregon Sanitation": (
        "Southern Oregon Sanitation, Inc.",
        ["Southern Oregon Sanitation"],
        []
    ),

    "Humboldt County Landfill": (
        "Humboldt County Landfill",
        ["Humboldt County Landfill"],
        []
    ),

    "City of Vinita": (
        "City of Vinita",
        ["City of Vinita"],
        []
    ),

    "United States Disposal": (
        "UNITED STATES DISPOSAL SERVICE",
        ["United States Disposal"],
        []
    ),

    "Coos Bay Sanitary": (
        "Coos Bay Sanitary Service",
        ["Coos Bay Sanitary"],
        []
    ),

    "Federal Recycling & Waste Solutions": (
        "Federal Recycling",
        ["Federal Recycling & Waste Solutions"],
        []
    ),

    "Equipment Depot Northeast": (
        "AJ Waste",
        ["Equipment Depot Northeast"],
        []
    ),

    "JDog Junk Removal": (
        "Junk Removal & Hauling",
        ["JDog Junk Removal"],
        []
    ),

    "Loren Fischer Disposal": (
        "Loren Fischer Disposal INC.",
        ["Loren Fischer Disposal"],
        []
    ),

    "Nowrush Recycling": (
        "NOWRUSH RECYCLING",
        ["Nowrush Recycling"],
        []
    ),

    "Mulberry Ventures": (
        "MULBERRY VENTURES, LLC",
        ["Mulberry Ventures"],
        []
    ),

    "Mac's Wood Products": (
        "Mac's Wood Products",
        ["Mac's Wood Products"],
        []
    ),

    "Ideal Trash and Recycling": (
        "IDEAL TRASH AND RECYCLING LLC",
        ["Ideal Trash and Recycling"],
        []
    ),

    "SRG Spartanburg": (
        "SRG Spartanburg (Yard 2)",
        ["SRG Spartanburg"],
        []
    ),

    "Gibson Truck Service": (
        "GIBSON",
        ["Gibson Truck Service"],
        []
    ),

    "Kings Roll-Off": (
        "Kings Roll-Off Services",
        ["Kings Roll-Off"],
        []
    ),

    "Vasco Road Landfill": (
        "VASCO ROAD LANDFILL - 3850",
        ["Vasco Road Landfill"],
        []
    ),

    "Civicorps Recycling": (
        "Civicorps",
        ["Civicorps Recycling"],
        []
    ),

    "Waterman Recy & Disposal": (
        "WATERMAN RECY & DISPOSAL",
        ["Waterman Recy & Disposal"],
        []
    ),

    "Harper Sanitation": (
        "Harper Sanitation Service Inc",
        ["Harper Sanitation"],
        []
    ),

    "Russell County Sanitation": (
        "Russell County Utilities",
        ["Russell County Sanitation"],
        []
    ),

    "P&S Trucking": (
        "P&S Trucking",
        ["P&S Trucking"],
        []
    ),

    "Seagraves Plumbing": (
        "SEAGRAVES PLUMBING",
        ["Seagraves Plumbing"],
        []
    ),

    "Chris Rizzo Trucking": (
        "Chris Rizzo Trucking Inc.",
        ["Chris Rizzo Trucking"],
        []
    ),

    "Advanced Document Solutions": (
        "Advanced Document Solutions",
        ["Advanced Document Solutions"],
        []
    ),

    "Guido's Services": (
        "Guido's SERVICES INC.",
        ["Guido's Services"],
        []
    ),

    "Shamrock Waste": (
        "SHAMROCK WASTE",
        ["Shamrock Waste"],
        []
    ),

    "Community Sanitation": (
        "COMMUNITY SANITATION",
        ["Community Sanitation"],
        []
    ),

    "American Metal & Paper": (
        "AMERICAN METAL & PAPER",
        ["American Metal & Paper"],
        []
    ),

    "Sweetland": (
        "SWEETLAND LTD",
        ["Sweetland"],
        []
    ),

    "Potties for the Rockies": (
        "Columbia Potties",
        ["Potties for the Rockies"],
        []
    ),

    "EWE Equipment": (
        "SWS Equipment, LLC.",
        ["EWE Equipment"],
        []
    ),

    "Graybill Equipment & Repair": (
        "GRAYBILL EQUIPMENT & REPAIR, INC.",
        ["Graybill Equipment & Repair"],
        []
    ),

    "TEG Lease": (
        "TEG",
        ["TEG Lease"],
        []
    ),

    "Hopper Disposal": (
        "Hopper Disposal Inc.",
        ["Hopper Disposal"],
        []
    ),

    "Brew Crew Environmental": (
        "Brew Crew Environmental",
        ["Brew Crew Environmental"],
        []
    ),

    "Sanitation One": (
        "SANITATION ONE",
        ["Sanitation One"],
        []
    ),

    "J&J Sanitation": (
        "J&J SANITATION",
        ["J&J Sanitation"],
        []
    ),

    "City of Henagar": (
        "CITY OF HENAGAR",
        ["City of Henagar"],
        []
    ),

    "Roll-Off Chick": (
        "Roll-Off Chick",
        ["Roll-Off Chick"],
        []
    ),

    "S.B. Cox": (
        "S.B.COX",
        ["S.B. Cox"],
        []
    ),

    "Far West Recycling": (
        "Far West Recycling",
        ["Far West Recycling"],
        []
    ),

    "J & M Sanitation": (
        "J & M Sanitation",
        ["J & M Sanitation"],
        []
    ),

    "Mavilyn Industries": (
        "MAVILYN Industries",
        ["Mavilyn Industries"],
        []
    ),

    "My Green Michigan": (
        "MYGREEN MICHIGAN",
        ["My Green Michigan"],
        []
    ),

    "Harley Hollan": (
        "HARLEY HOLLAN COMPANIES",
        ["Harley Hollan"],
        []
    ),

    "Prolex Compacting": (
        "Prolex Compacting Solutions",
        ["Prolex Compacting"],
        []
    ),

    "Kept Companies": (
        "COMPANIES",
        ["Kept Companies"],
        []
    ),

    "Miller Waste Systems": (
        "Miller Waste Systems- Durham Division",
        ["Miller Waste Systems"],
        []
    ),

    "Dirty Boyz Sanitation": (
        "Dirty Boyz Sanitation",
        ["Dirty Boyz Sanitation"],
        []
    ),

    "Reed Maintenance": (
        "Reed Maintenance Services, Inc.",
        ["Reed Maintenance"],
        []
    ),

    "City of Hidalgo": (
        "City of Hidalgo Utility Department",
        ["City of Hidalgo"],
        []
    ),

    "Metalico Youngstown": (
        "Metalico Youngstown",
        ["Metalico Youngstown"],
        []
    ),

    "City of Redwood": (
        "City of Redwood City",
        ["City of Redwood"],
        []
    ),

    "NW Dumpsters": (
        "NW Dumpsters",
        ["NW Dumpsters"],
        []
    ),

    "Styro Recycle": (
        "Styro Recycle LLC",
        ["Styro Recycle"],
        []
    ),

    "Redfish Recycling": (
        "REDFISH RECYCLING",
        ["Redfish Recycling"],
        []
    ),

    "Total Waste Management": (
        "Total Waste Management",
        ["Total Waste Management"],
        []
    ),

    "Blue Compactor": (
        "BLUE COMPACTOR SERVICES, LLC",
        ["Blue Compactor"],
        []
    ),

    "Happen Ventures": (
        "Happen Ventures LLC",
        ["Happen Ventures"],
        []
    ),

    "Hudgins Disposal": (
        "Hudgins Disposal",
        ["Hudgins Disposal"],
        []
    ),

    "Hillsborough County SW": (
        "SOLID WASTE MANAGEMENT",
        ["Hillsborough County SW"],
        []
    ),

    "DKMM Solid Waste": (
        "Waste Management of Ohio Inc.",
        ["DKMM Solid Waste"],
        []
    ),

    "TNR Hauling": (
        "TNR Hauling",
        ["TNR Hauling"],
        []
    ),

    "Eagle Equipment Service 1": (
        "Eagle Equipment Service 1, Corp.",
        ["Eagle Equipment Service 1"],
        []
    ),

    # Invoice processing gap closures — vendor address matching (March 9, 2026)
    "A1 Waste": (
        "A1 Waste, LLC",
        ["A1 Waste"],
        ["A1 Waste, LLC"]
    ),

    "Craven Ag Services": (
        "Craven Ag Services, Inc",
        ["Craven Ag"],
        ["Craven Ag Services, Inc"]
    ),

    "Jamaica Ash & Rubbish": (
        "JAMAICA ASH RUBBISH REMOVAL CO",
        ["Jamaica Ash"],
        ["JAMAICA ASH RUBBISH REMOVAL CO"]
    ),

    "Royal Sanitation": (
        "Royal Sanitation LLC",
        ["Royal Sanitation"],
        ["Royal Sanitation LLC"]
    ),

    "Woody & Sons Disposal": (
        "Woody & Sons",
        ["Woody & Sons", "Woody and Sons"],
        ["Woody & Sons"]
    ),

    "Organix Recycling": (
        "Denali Water - Organix Recycling",
        ["Organix"],
        ["Denali Water - Organix Recycling"]
    ),
}


class VendorNormalizer:
    """
    Maps extracted vendor names to normalized database vendor names.
    """
    
    def __init__(self):
        self.mapping = VENDOR_MAPPING
        self._build_reverse_index()
    
    def _build_reverse_index(self):
        """Build reverse lookup from DB patterns to detected vendors."""
        self.reverse_index = {}
        
        for detected_vendor, (canonical, patterns, exact_matches) in self.mapping.items():
            # Index patterns
            for pattern in patterns:
                pattern_lower = pattern.lower()
                if pattern_lower not in self.reverse_index:
                    self.reverse_index[pattern_lower] = detected_vendor
            
            # Index exact matches
            for exact in exact_matches:
                exact_lower = exact.lower()
                self.reverse_index[exact_lower] = detected_vendor
    
    def get_canonical_name(self, detected_vendor: str) -> Optional[str]:
        """
        Get the canonical database vendor name for a detected vendor.
        
        Args:
            detected_vendor: Vendor name from vendor_detection_module
            
        Returns:
            Canonical vendor name or None if not found
        """
        if detected_vendor in self.mapping:
            return self.mapping[detected_vendor][0]
        return None
    
    def get_db_patterns(self, detected_vendor: str) -> List[str]:
        """
        Get SQL LIKE patterns for matching database vendor names.
        
        Args:
            detected_vendor: Vendor name from vendor_detection_module
            
        Returns:
            List of patterns suitable for SQL LIKE queries (e.g., 'Waste Connections%')
        """
        if detected_vendor not in self.mapping:
            return []
        
        _, patterns, _ = self.mapping[detected_vendor]
        return [f"{p}%" for p in patterns]
    
    def get_exact_matches(self, detected_vendor: str) -> List[str]:
        """
        Get exact database vendor name matches.
        
        Args:
            detected_vendor: Vendor name from vendor_detection_module
            
        Returns:
            List of exact database vendor names
        """
        if detected_vendor not in self.mapping:
            return []
        
        return self.mapping[detected_vendor][2]
    
    def match_db_vendor(self, db_vendor_name: str) -> Optional[str]:
        """
        Find the detected vendor name for a database vendor name.
        
        Args:
            db_vendor_name: Vendor name from services/billing tables
            
        Returns:
            Detected vendor name or None if no match
        """
        db_lower = db_vendor_name.lower().strip()
        
        # Check exact matches first
        if db_lower in self.reverse_index:
            return self.reverse_index[db_lower]
        
        # Check prefix matches
        for pattern, detected_vendor in self.reverse_index.items():
            if db_lower.startswith(pattern):
                return detected_vendor
        
        return None
    
    def build_sql_where_clause(self, detected_vendor: str, column: str = "vendor_name") -> str:
        """
        Build a SQL WHERE clause for matching vendor names.
        
        Args:
            detected_vendor: Vendor name from vendor_detection_module
            column: Database column name (default: 'vendor_name')
            
        Returns:
            SQL WHERE clause string
        """
        if detected_vendor not in self.mapping:
            return f"{column} = 'UNKNOWN'"
        
        _, patterns, exact_matches = self.mapping[detected_vendor]
        
        conditions = []
        
        # Add LIKE conditions for patterns
        for pattern in patterns:
            conditions.append(f"{column} LIKE '{pattern}%'")
            conditions.append(f"UPPER({column}) LIKE '{pattern.upper()}%'")
        
        # Add exact match conditions
        for exact in exact_matches:
            conditions.append(f"{column} = '{exact}'")
        
        if not conditions:
            return f"{column} = '{detected_vendor}'"
        
        return " OR ".join(conditions)
    
    def get_all_detected_vendors(self) -> List[str]:
        """Get list of all detected vendor names."""
        return list(self.mapping.keys())
    
    def get_mapping_summary(self) -> Dict[str, Dict]:
        """
        Get a summary of all vendor mappings.
        
        Returns:
            Dictionary with vendor mapping details
        """
        summary = {}
        for detected, (canonical, patterns, exact) in self.mapping.items():
            summary[detected] = {
                'canonical': canonical,
                'pattern_count': len(patterns),
                'exact_match_count': len(exact),
                'patterns': patterns,
                'exact_matches': exact
            }
        return summary


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def normalize_vendor(detected_vendor: str) -> str:
    """
    Quick normalization function.
    
    Args:
        detected_vendor: Vendor name from vendor_detection_module
        
    Returns:
        Canonical database vendor name
    """
    normalizer = VendorNormalizer()
    canonical = normalizer.get_canonical_name(detected_vendor)
    return canonical if canonical else detected_vendor


def find_vendor_from_db_name(db_vendor_name: str) -> Optional[str]:
    """
    Find detected vendor from a database vendor name.
    
    Args:
        db_vendor_name: Vendor name from database
        
    Returns:
        Detected vendor name or None
    """
    normalizer = VendorNormalizer()
    return normalizer.match_db_vendor(db_vendor_name)


# =============================================================================
# MAIN / TESTING
# =============================================================================

if __name__ == "__main__":
    import sys
    
    normalizer = VendorNormalizer()
    
    print("=" * 70)
    print("VENDOR NORMALIZATION ENGINE - TEST")
    print("=" * 70)
    
    # Test mappings
    test_cases = [
        ("Waste Connections", "Waste Connections - Tennessee 6032"),
        ("Republic Services", "Republic Services #620"),
        ("GFL", "GFL Environmental - Detroit"),
        ("Waste Management", "Waste Management - National"),
        ("Anytime Waste", "ANYTIME WASTE SYSTEMS"),
        ("Casella", "CASELLA WASTE SYSTEMS"),
        ("Priority Waste", "Priority Waste MI"),
    ]
    
    print("\nForward Mapping (Detected -> DB Patterns):")
    print("-" * 70)
    
    for detected, expected_db in test_cases:
        canonical = normalizer.get_canonical_name(detected)
        patterns = normalizer.get_db_patterns(detected)
        exact = normalizer.get_exact_matches(detected)
        
        print(f"\n{detected}:")
        print(f"  Canonical: {canonical}")
        print(f"  Patterns:  {patterns[:3]}...")  # Show first 3
        print(f"  Exact:     {exact[:3]}...")  # Show first 3
    
    print("\n" + "-" * 70)
    print("Reverse Mapping (DB Name -> Detected):")
    print("-" * 70)
    
    db_test_names = [
        "Waste Connections - Tennessee 6032",
        "Republic Services #620",
        "GFL Environmental - Detroit",
        "CASELLA WASTE SYSTEMS",
        "Priority Waste MI",
        "Burrtec Waste-Jurupa Valley-Riverside",
        "ANYTIME WASTE SYSTEMS",
    ]
    
    for db_name in db_test_names:
        detected = normalizer.match_db_vendor(db_name)
        print(f"  {db_name[:45]:45} -> {detected}")
    
    print("\n" + "-" * 70)
    print("SQL WHERE Clause Examples:")
    print("-" * 70)
    
    for vendor in ["Waste Connections", "GFL", "Casella"]:
        where = normalizer.build_sql_where_clause(vendor)
        print(f"\n{vendor}:")
        print(f"  {where[:100]}...")
    
    print("\n" + "=" * 70)
    print(f"Total vendors mapped: {len(normalizer.get_all_detected_vendors())}")
    print("=" * 70)
