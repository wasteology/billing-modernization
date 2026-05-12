import csv, sys
sys.path.insert(0, '.')
from vendor_detection.data.vendor_detection_module_v9 import detect_vendor
from dates.date_extraction_additions import VENDOR_DATE_ADDITIONS

targets = ['City of Somerset', 'Tahoe Truckee Sierra Disposal', 'Shamrock Waste', 'City of Wolf Point',
           'Lex Serv', 'Stewart Sanitation', 'Humboldt County Landfill', 'Olson Sanitation',
           'Trash Rangers', 'Wingfield Service', 'A&J Trash', 'City of Rowlett']

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

print(f"Testing {len(samples)} vendors from Tranche 59:\n")
passed = 0
failed = 0

for vendor in targets:
    if vendor in samples:
        extractor = VENDOR_DATE_ADDITIONS[vendor]['extract']
        result = extractor(samples[vendor])
        status = "✓" if result else "✗"
        if result:
            passed += 1
        else:
            failed += 1
        print(f"  {status} {vendor}: {result}")
    else:
        print(f"  ? {vendor}: NO SAMPLE")

print(f"\nResults: {passed}/{passed+failed} passed")
