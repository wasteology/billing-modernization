import csv, sys
sys.path.insert(0, '.')
from vendor_detection.data.vendor_detection_module_v9 import detect_vendor
from dates.date_extraction_additions import VENDOR_DATE_ADDITIONS
from collections import Counter

configured = set(VENDOR_DATE_ADDITIONS.keys())
unconfigured_counts = Counter()

with open('training_data/ocr_chunks/raw_ocr_text.csv', 'r') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= 20000:
            break
        text = row.get('raw_text', '')
        vendor = detect_vendor(text)
        if vendor and vendor not in configured and vendor != 'OTHER':
            unconfigured_counts[vendor] += 1

print(f"Top unconfigured vendors (sample of 20k rows):\n")
for vendor, count in unconfigured_counts.most_common(15):
    print(f"  {vendor}: {count}")
