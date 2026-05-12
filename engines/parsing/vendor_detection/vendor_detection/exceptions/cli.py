#!/usr/bin/env python3
"""
CLI for vendor detection exception workflow.

Usage:
    # Analyze exceptions and show suggestions
    python -m parsing_engines.vendor_detection.exceptions.cli analyze exceptions.csv

    # Export suggestions for review
    python -m parsing_engines.vendor_detection.exceptions.cli analyze exceptions.csv --export suggestions.csv

    # Validate a pattern against exception texts
    python -m parsing_engines.vendor_detection.exceptions.cli validate "WALL\\s*RECYCLING" --file exceptions.csv

    # Generate pattern code for high-confidence suggestions
    python -m parsing_engines.vendor_detection.exceptions.cli generate exceptions.csv --confidence high
"""

import argparse
import sys
from pathlib import Path

from .pattern_suggester import PatternSuggester
from .exception_format import load_exceptions


def cmd_analyze(args):
    """Analyze exceptions and suggest patterns."""
    suggester = PatternSuggester(min_occurrences=args.min)
    suggestions = suggester.analyze(args.file)

    print(f"\\n{'='*60}")
    print(f"PATTERN SUGGESTIONS")
    print(f"{'='*60}")
    print(f"Source: {args.file}")
    print(f"Minimum occurrences: {args.min}")
    print(f"Suggestions found: {len(suggestions)}")
    print(f"{'='*60}\\n")

    if args.confidence:
        suggestions = [s for s in suggestions if s.confidence == args.confidence]
        print(f"Filtered to {args.confidence} confidence: {len(suggestions)} remaining\\n")

    for i, s in enumerate(suggestions[:args.top], 1):
        status = "✓" if s.confidence == "high" else "?" if s.confidence == "medium" else "✗"
        print(f"{i:3}. [{status}] {s.vendor_name}")
        print(f"     Count: {s.occurrence_count}  |  Confidence: {s.confidence}")
        print(f"     Pattern: {s.suggested_pattern}")
        print()

    if len(suggestions) > args.top:
        print(f"... and {len(suggestions) - args.top} more suggestions")

    if args.export:
        suggester.export_for_review(args.export)


def cmd_validate(args):
    """Validate a pattern against exception texts."""
    import re

    batch = load_exceptions(args.file)
    all_texts = [r.raw_text for r in batch.records if r.raw_text and r.raw_text != 'NO_TEXT']

    print(f"\\n{'='*60}")
    print(f"PATTERN VALIDATION")
    print(f"{'='*60}")
    print(f"Pattern: {args.pattern}")
    print(f"Testing against: {len(all_texts)} texts (excluding NO_TEXT)")
    print(f"{'='*60}\\n")

    try:
        regex = re.compile(args.pattern, re.IGNORECASE)
    except re.error as e:
        print(f"ERROR: Invalid regex - {e}")
        return 1

    matches = [text for text in all_texts if regex.search(text)]

    print(f"Matches: {len(matches)}")

    if matches:
        print(f"\\nThis pattern would capture {len(matches)} previously undetected invoices")
        if args.show_matches:
            print(f"\\nSample matches:")
            seen = set()
            for m in matches:
                preview = m[:80].replace('\\n', ' ')
                if preview not in seen:
                    print(f"  - {preview}")
                    seen.add(preview)
                if len(seen) >= 5:
                    break
    else:
        print("\\nNo matches found in exception set")

    return 0


def cmd_generate(args):
    """Generate pattern code for suggestions."""
    suggester = PatternSuggester(min_occurrences=args.min)
    suggester.analyze(args.file)

    if args.confidence:
        suggester.suggestions = [s for s in suggester.suggestions if s.confidence == args.confidence]

    suggester.suggestions = suggester.suggestions[:args.top]

    print(f"# Generated patterns for {len(suggester.suggestions)} vendors")
    print("# Add to VENDOR_PATTERNS in vendor_detection_module_v9.py\\n")
    for s in suggester.suggestions:
        print(s.to_code())


def main():
    parser = argparse.ArgumentParser(
        description='Vendor detection exception workflow',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze exceptions')
    analyze_parser.add_argument('file', help='Path to exceptions CSV')
    analyze_parser.add_argument('--min', type=int, default=5,
                               help='Minimum occurrences (default: 5)')
    analyze_parser.add_argument('--top', type=int, default=20,
                               help='Show top N suggestions (default: 20)')
    analyze_parser.add_argument('--confidence', choices=['high', 'medium', 'low'],
                               help='Filter by confidence level')
    analyze_parser.add_argument('--export', help='Export suggestions to CSV')

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate a pattern')
    validate_parser.add_argument('pattern', help='Regex pattern to validate')
    validate_parser.add_argument('--file', required=True, help='Exceptions file')
    validate_parser.add_argument('--show-matches', action='store_true',
                                help='Show sample matches')

    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate pattern code')
    generate_parser.add_argument('file', help='Path to exceptions CSV')
    generate_parser.add_argument('--min', type=int, default=10,
                                help='Minimum occurrences (default: 10)')
    generate_parser.add_argument('--top', type=int, default=20,
                                help='Number of patterns (default: 20)')
    generate_parser.add_argument('--confidence', choices=['high', 'medium', 'low'],
                                help='Filter by confidence level')

    args = parser.parse_args()

    if args.command == 'analyze':
        cmd_analyze(args)
    elif args.command == 'validate':
        return cmd_validate(args)
    elif args.command == 'generate':
        cmd_generate(args)
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
