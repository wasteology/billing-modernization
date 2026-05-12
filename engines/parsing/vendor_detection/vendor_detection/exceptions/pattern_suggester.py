"""
ML-assisted pattern suggestion for vendor detection engine.

Analyzes exception batches and suggests regex patterns.
Designed to work with Claude Code for interactive pattern development.

Usage:
    from parsing_engines.vendor_detection.exceptions import PatternSuggester

    suggester = PatternSuggester()
    suggestions = suggester.analyze("path/to/exceptions.csv")

    # Review suggestions
    for s in suggestions:
        print(s.to_prompt())  # Copy to Claude for refinement

    # Validate a pattern
    suggester.validate(pattern=r'ACME\\s*WASTE', test_texts=[...])
"""

import re
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from .exception_format import ExceptionBatch, load_exceptions


@dataclass
class PatternSuggestion:
    """A suggested regex pattern for a vendor."""

    vendor_name: str                        # Normalized vendor name
    suggested_pattern: str                  # Regex pattern
    sample_texts: List[str]                 # OCR samples that should match
    occurrence_count: int                   # How many exceptions this would fix
    confidence: str                         # "high", "medium", "low"
    notes: str = ""

    def to_prompt(self) -> str:
        """Generate a prompt for Claude to refine the pattern."""
        samples = '\\n'.join(f'  - "{t[:150]}..."' for t in self.sample_texts[:5])
        return f"""
## Pattern Suggestion: {self.vendor_name}

**Occurrences:** {self.occurrence_count}
**Confidence:** {self.confidence}
**Initial Pattern:** `{self.suggested_pattern}`

**Sample texts that should match:**
{samples}

**Task:** Review and refine this regex pattern. Consider:
1. Is the pattern specific enough to avoid false positives?
2. Does it handle OCR variations (spaces, case, special chars)?
3. Are there edge cases in the samples?

Respond with:
- Final pattern: `YOUR_PATTERN`
- Validation status: APPROVED / NEEDS_REVIEW / REJECTED
- Notes: Any concerns or edge cases
"""

    def to_code(self) -> str:
        """Generate Python code for VENDOR_PATTERNS entry."""
        return f'    "{self.vendor_name}": r\'{self.suggested_pattern}\','

    def to_dict(self) -> dict:
        return {
            'vendor_name': self.vendor_name,
            'suggested_pattern': self.suggested_pattern,
            'occurrence_count': self.occurrence_count,
            'confidence': self.confidence,
            'notes': self.notes,
            'sample_count': len(self.sample_texts)
        }


class PatternSuggester:
    """Analyzes exceptions and suggests patterns."""

    def __init__(self, min_occurrences: int = 3):
        self.min_occurrences = min_occurrences
        self.suggestions: List[PatternSuggestion] = []

    def analyze(self, exceptions_path: str) -> List[PatternSuggestion]:
        """Analyze exceptions and generate pattern suggestions."""
        batch = load_exceptions(exceptions_path)
        return self.analyze_batch(batch)

    def analyze_batch(self, batch: ExceptionBatch) -> List[PatternSuggestion]:
        """Analyze an ExceptionBatch and generate suggestions."""

        # Group by potential value
        groups = defaultdict(list)
        for record in batch.records:
            key = self._normalize_potential(record.potential_value)
            if key and key != 'NO_TEXT':
                groups[key].append(record)

        # Generate suggestions for groups meeting threshold
        suggestions = []
        for potential_value, records in groups.items():
            if len(records) >= self.min_occurrences:
                suggestion = self._create_suggestion(potential_value, records)
                if suggestion:
                    suggestions.append(suggestion)

        # Sort by occurrence count
        suggestions.sort(key=lambda s: s.occurrence_count, reverse=True)
        self.suggestions = suggestions
        return suggestions

    def _normalize_potential(self, value: str) -> str:
        """Normalize a potential vendor name for grouping."""
        if not value:
            return ""
        value = value.strip().upper()
        value = re.sub(r'\\\\+[nN]|\\n', ' ', value)
        value = re.sub(r'\\s+', ' ', value)
        return value[:100]

    def _create_suggestion(self, potential_value: str, records: list) -> Optional[PatternSuggestion]:
        """Create a pattern suggestion from grouped exceptions."""
        sample_texts = [r.raw_text for r in records if r.raw_text][:10]
        if not sample_texts:
            return None

        pattern, confidence = self._suggest_pattern(potential_value, sample_texts)

        return PatternSuggestion(
            vendor_name=self._to_vendor_name(potential_value),
            suggested_pattern=pattern,
            sample_texts=sample_texts,
            occurrence_count=len(records),
            confidence=confidence,
            notes=f"Auto-generated from {len(records)} exceptions"
        )

    def _suggest_pattern(self, value: str, samples: List[str]) -> Tuple[str, str]:
        """Suggest a regex pattern for a potential vendor."""
        words = value.split()

        if len(words) >= 2:
            key_words = [w for w in words if len(w) > 2][:3]
            pattern = r'\\s*'.join(re.escape(w) for w in key_words)
            confidence = "medium"
        elif len(words) == 1 and len(words[0]) > 4:
            pattern = re.escape(words[0])
            confidence = "low"
        else:
            pattern = re.escape(value)
            confidence = "low"

        # Validate pattern against samples
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            matches = sum(1 for s in samples if regex.search(s))
            if matches == len(samples):
                confidence = "high" if confidence == "medium" else confidence
            elif matches < len(samples) // 2:
                confidence = "low"
        except re.error:
            confidence = "low"

        return pattern, confidence

    def _to_vendor_name(self, value: str) -> str:
        """Convert potential value to a clean vendor name."""
        name = value.title()
        name = re.sub(r'[.\\-,;:]+$', '', name)
        return name.strip()

    def validate(self, pattern: str, test_texts: List[str]) -> Dict:
        """Validate a regex pattern against test texts."""
        result = {
            'valid': True,
            'matches': 0,
            'total': len(test_texts),
            'match_rate': 0.0,
            'errors': [],
            'matched_samples': [],
            'failed_samples': []
        }

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            result['valid'] = False
            result['errors'].append(f"Invalid regex: {e}")
            return result

        for text in test_texts:
            if regex.search(text):
                result['matches'] += 1
                result['matched_samples'].append(text[:100])
            else:
                result['failed_samples'].append(text[:100])

        result['match_rate'] = result['matches'] / result['total'] if result['total'] > 0 else 0

        if result['match_rate'] < 0.8:
            result['errors'].append(f"Low match rate: {result['match_rate']:.1%}")

        return result

    def export_for_review(self, output_path: str):
        """Export suggestions as CSV for review."""
        if not self.suggestions:
            print("No suggestions to export. Run analyze() first.")
            return

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'vendor_name', 'suggested_pattern', 'occurrence_count',
                'confidence', 'notes', 'sample_count', 'status'
            ])
            writer.writeheader()
            for s in self.suggestions:
                row = s.to_dict()
                row['status'] = 'PENDING'
                writer.writerow(row)

        print(f"Exported {len(self.suggestions)} suggestions to {path}")

    def generate_pattern_code(self) -> str:
        """Generate Python code for approved patterns."""
        code_lines = ["# Add to VENDOR_PATTERNS in vendor_detection_module_v9.py", ""]
        for s in self.suggestions:
            code_lines.append(s.to_code())
        return "\\n".join(code_lines)

    def generate_ml_prompt(self, top_n: int = 10) -> str:
        """Generate a prompt for Claude to review top suggestions."""
        if not self.suggestions:
            return "No suggestions available. Run analyze() first."

        prompts = []
        for s in self.suggestions[:top_n]:
            prompts.append(s.to_prompt())

        header = f"""
# Pattern Review Request

I have {len(self.suggestions)} vendor detection exceptions that need patterns.
Below are the top {min(top_n, len(self.suggestions))} by occurrence count.

For each, please:
1. Review the suggested pattern
2. Refine if needed (handle OCR variations, avoid false positives)
3. Mark as APPROVED, NEEDS_REVIEW, or REJECTED

---
"""
        return header + '\\n---\\n'.join(prompts)
