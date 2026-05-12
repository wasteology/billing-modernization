import csv, sys
sys.path.insert(0, '.')
from vendor_detection.data.vendor_detection_module_v9 import detect_vendor
from dates.date_extraction_additions import VENDOR_DATE_ADDITIONS

targets = ['Express Disposal', 'Waste Services Manchester', "Ava's Waste Removal", 'BKI Recycling',
           'Valley Sanitation LLC', 'Ridgerunner Container', 'Recycling Services of Florida',
           'Rick Taylor', 'Klumm Brothers', 'Green Guy Recycling', 'MARS City of Beatrice', 'Midwest Disposal IL']

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

print(f"Testing {len(samples)} vendors from Tranche 39:\n")
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
