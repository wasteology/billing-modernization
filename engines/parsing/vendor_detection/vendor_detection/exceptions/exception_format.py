"""
Standard exception format for vendor detection engine.

Any pipeline using vendor detection should output exceptions in this format.
This allows the ML-assisted pattern suggester to work with any pipeline.

Usage:
    from parsing_engines.vendor_detection.exceptions import ExceptionRecord, ExceptionBatch

    batch = ExceptionBatch(pipeline="invoice-volume-dashboard")
    batch.add(ExceptionRecord(
        doc_id="abc123",
        raw_text="ACME WASTE SERVICES...",
        failure_type="no_match",
        potential_value="ACME WASTE SERVICES"
    ))
    batch.save("exceptions/vendor_detection_failures.csv")
"""

import csv
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class ExceptionRecord:
    """A single vendor detection exception."""

    # Required fields
    raw_text: str                           # The OCR text that failed detection
    failure_type: str                       # "no_match", "multiple_match"

    # Optional but recommended
    doc_id: str = ""                        # Unique document identifier (MD5, filename, etc.)
    potential_value: str = ""               # Extracted text that might be vendor name
    timestamp: str = ""                     # When the exception occurred

    # Context (optional)
    text_preview: str = ""                  # First N chars of text for quick review
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.text_preview and self.raw_text:
            self.text_preview = self.raw_text[:200].replace('\n', ' ')


@dataclass
class ExceptionBatch:
    """A collection of exceptions from a pipeline run."""

    pipeline: str                           # Which pipeline produced this
    records: List[ExceptionRecord] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def add(self, record: ExceptionRecord):
        """Add an exception record to the batch."""
        self.records.append(record)

    def save(self, path: str):
        """Save exceptions to CSV."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if self.records:
            fieldnames = ['doc_id', 'raw_text', 'failure_type', 'potential_value',
                         'timestamp', 'text_preview']
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                for record in self.records:
                    writer.writerow(asdict(record))

        # Save batch metadata as JSON sidecar
        meta_path = path.with_suffix('.meta.json')
        with open(meta_path, 'w') as f:
            json.dump({
                'engine': 'vendor_detection',
                'pipeline': self.pipeline,
                'created_at': self.created_at,
                'record_count': len(self.records)
            }, f, indent=2)

        print(f"Saved {len(self.records)} exceptions to {path}")

    @classmethod
    def load(cls, path: str) -> 'ExceptionBatch':
        """Load exceptions from CSV."""
        path = Path(path)

        # Load metadata if exists
        meta_path = path.with_suffix('.meta.json')
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
        else:
            meta = {'pipeline': 'unknown'}

        batch = cls(pipeline=meta.get('pipeline', 'unknown'))

        # Load records
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Handle aggregated format (potential_vendor, count)
                if 'potential_vendor' in row and 'count' in row and 'raw_text' not in row:
                    count = int(row.get('count', 1))
                    for _ in range(count):
                        batch.add(ExceptionRecord(
                            doc_id='',
                            raw_text=row.get('potential_vendor', ''),
                            failure_type='no_match',
                            potential_value=row.get('potential_vendor', ''),
                            text_preview=row.get('potential_vendor', '')[:200]
                        ))
                else:
                    batch.add(ExceptionRecord(
                        doc_id=row.get('doc_id', row.get('invoice_md5', '')),
                        raw_text=row.get('raw_text', row.get('text_preview', '')),
                        failure_type=row.get('failure_type', 'no_match'),
                        potential_value=row.get('potential_value', row.get('potential_vendor', '')),
                        timestamp=row.get('timestamp', ''),
                        text_preview=row.get('text_preview', '')
                    ))

        return batch


def load_exceptions(path: str) -> ExceptionBatch:
    """Convenience function to load exceptions from any CSV format."""
    return ExceptionBatch.load(path)
