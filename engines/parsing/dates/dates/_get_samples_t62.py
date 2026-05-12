import csv, sys
sys.path.insert(0, '.')
from vendor_detection.data.vendor_detection_module_v9 import detect_vendor

targets = ['Overton Recycling', 'Helgerson Property Maintenance', 'Okon Recycling', 'Waste Services Inc',
           "Fogle's", "Wayn-O's Disposal Service", 'Solid Waste Services WV', 'Dyersburg Gas & Water',
           'Volunteer Disposal West', 'Certified Enterprises', 'Becker Complete', 'Reliable Paper']

samples = {}
with open('training_data/ocr_chunks/raw_ocr_text.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        text = row.get('raw_text', '')
        vendor = detect_vendor(text)
        if vendor in targets and vendor not in samples:
            samples[vendor] = text
        if len(samples) == len(targets):
            break

for vendor in targets:
    if vendor in samples:
        print(f'===== {vendor} =====')
        text = samples[vendor].replace('\\n', '\n')
        lines = text.split('\n')
        for i, line in enumerate(lines[:30]):
            print(f'{i:3}: {line[:80]}')
        print()
    else:
        print(f'===== {vendor} ===== NO SAMPLE FOUND')
        print()
