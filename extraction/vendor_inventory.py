"""
Step 2 — Vendor inventory from OCR text.
Identifies unique vendors and counts invoices per vendor.
"""

import pandas as pd
import re

df = pd.read_csv('/home/scstclair/projects/ng-report/Invoices/output/ocr_results.csv')

# Ordered by specificity — first match wins on multi-match
patterns = [
    ('Waste Management', r'WASTE\s*MANAGEMENT'),
    ('Republic Services', r'REPUBLIC\s*S\s*ERVICES|REPUBLIC.*ACCOUNT\s*NUMBER'),
    ("Cockey's", r'COCKEY'),
    ("Burgmeier's", r'BURGMEIER'),
    ('Athens Services', r'ATHENS\s*SERVICES'),
    ('Robinson Waste', r'ROBINSON\s*WASTE'),
    ('Universal Waste Systems', r'UNIVERSAL\s*WASTE'),
    ('SBC Waste Solutions', r'SBC\s*WASTE'),
    ('Town of Gilbert', r'TOWN\s*OF\s*GILBERT|GILBERT.*UTILITY\s*STATEMENT'),
    ('KMG Hauling', r'KMG\s*HAULING'),
    ('EDCO', r'EDCO\s*(DISPOSAL|WASTE)'),
    ('Meridian Waste', r'MERIDIAN\s*W'),
    ('Rumpke', r'RUMPKE'),
    ('Modern Disposal', r'MODERN\s*(DISPOSAL|CORPORATION)'),
    ('121 Disposal', r'121\s*DISPOSAL'),
    ('Marborg Industries', r'MARBORG'),
    ('Casella Waste', r'CASELLA'),
    ('Waste Connections', r'WASTE\s*CONNECTIONS'),
    ('Ace Recycling', r'ACE\s*RECYCL'),
    ('Veit Disposal', r'VEIT\s*(DISPOSAL|&)'),
    ('LePage and Sons', r'LEPAGE'),
    ('Waste Pro', r'WASTE\s*PRO\b'),
    ('USA Waste', r'USA\s*WASTE'),
    ('1-800-Got-Junk', r'GOT[\-\s]*JUNK'),
    ('National Waste Services', r'NATIONAL\s*WASTE\s*SERVICE'),
    ('Tate Services', r'TATE\s*SERVICES'),
    ('Waste Disposal Inc', r'WASTE\s*DISPOSAL\s*(INC|OF)'),
    ('AAA Rubbish', r'AAA\s*RUBBISH'),
    ('Container Rentals', r'CONTAINER\s*RENTALS'),
    ('City of Oxnard', r'CITY\s*OF\s*OXNARD'),
    ('Van Der Linde', r'VAN\s*DER\s*LINDE'),
    ('Jamaica Ash', r'JAMAICA\s*ASH'),
    ('Good Guys', r'GOOD\s*GUYS'),
    ('Forever Clean', r'FOREVER\s*CLEAN'),
    ('Zero Waste', r'ZERO\s*WASTE\s*(USA|ENERGY)'),
    ('Earthwise', r'EARTHWISE'),
    ('Aspen Waste', r'ASPEN\s*WASTE'),
    ('CheckSammy', r'CHECK\s*SAMMY|CHECKSAMMY'),
    ('Waste Masters', r'WASTE\s*MASTERS'),
    ('Haul-Away Rubbish', r'HAUL[\-\s]*AWAY'),
    ('Unique Sanitation', r'UNIQUE\s*SANITATION'),
    ('Atlas Disposal', r'ATLAS\s*DISPOSAL'),
    ('Mark Dunning Industries', r'MARK\s*DUNNING'),
    ('C&M Topsoil', r'C\s*[&]\s*M\s*TOPSOIL'),
    ('Choice Contractors', r'CHOICE\s*CONTRACTOR'),
    ('AARCO', r'AARCO'),
]

results = []
for _, row in df.iterrows():
    text = str(row['raw_ocr_text'])[:3000].upper()
    matched = []
    for vendor, pat in patterns:
        if re.search(pat, text):
            matched.append(vendor)

    if matched:
        v = matched[0]
    else:
        v = 'UNMATCHED'

    results.append({
        'pdf_filename': row['pdf_filename'],
        'pdf_path': row['pdf_path'],
        'site_code': row['site_code'],
        'month_folder': row['month_folder'],
        'vendor_file': row['vendor_name'],
        'ocr_vendor': v,
        'document_type': row['document_type'],
        'ocr_quality_score': row['ocr_quality_score'],
        'match_count': len(matched),
    })

rdf = pd.DataFrame(results)

matched_count = (rdf['ocr_vendor'] != 'UNMATCHED').sum()
unmatched_count = (rdf['ocr_vendor'] == 'UNMATCHED').sum()

print(f'Matched:   {matched_count}')
print(f'Unmatched: {unmatched_count}')

print()
print('=== VENDOR INVENTORY ===')
print()
vc = rdf[rdf['ocr_vendor'] != 'UNMATCHED']['ocr_vendor'].value_counts()
for v, c in vc.items():
    pct = c / len(df) * 100
    sites = rdf[rdf['ocr_vendor'] == v]['site_code'].nunique()
    print(f'  {c:>5}  ({pct:4.1f}%)  {sites:>3} sites  {v}')

print(f'\n  Total matched: {matched_count} / {len(df)} ({matched_count/len(df)*100:.1f}%)')
print(f'  Unique vendors: {vc.shape[0]}')

print()
print('=== UNMATCHED ===')
unmatched = rdf[rdf['ocr_vendor'] == 'UNMATCHED']
for _, row in unmatched.iterrows():
    print(f'  {row["pdf_filename"]}  (file says: {row["vendor_file"]})')

# Save inventory
rdf.to_csv('/home/scstclair/projects/ng-report/Invoices/output/vendor_inventory.csv', index=False)
print(f'\nSaved to output/vendor_inventory.csv')

# Also show doc_type breakdown per vendor
print()
print('=== NON-INVOICE DOCUMENTS ===')
non_inv = rdf[rdf['document_type'] != 'invoice']
if len(non_inv) > 0:
    print(f'Total non-invoice: {len(non_inv)}')
    print()
    for dt in non_inv['document_type'].unique():
        subset = non_inv[non_inv['document_type'] == dt]
        print(f'  {dt}: {len(subset)}')
        vc2 = subset['ocr_vendor'].value_counts()
        for v, c in vc2.items():
            print(f'    {c:>4}  {v}')
