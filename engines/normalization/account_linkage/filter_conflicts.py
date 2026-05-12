#!/usr/bin/env python3
"""
Account Linkage Quality Analysis (v3 - Trust-Based)

Analyzes linkage output from v3 pipeline which uses link_type for trust classification.

Link Types and Trust Levels:
- DIRECT_SINGLE_VENDOR: HIGH trust - invoice# exact match, billing_ref has ONE vendor
- VOUCHER_VALIDATED: HIGH trust - OCR matched voucher, voucher invoice# = billing_ref
- SUBSTRING_SINGLE_VENDOR: MEDIUM trust - invoice# substring match, single vendor
- DIRECT_MULTI_VENDOR: LOW trust - invoice# exact match, but billing_ref has MULTIPLE vendors

Analysis Categories:
- HIGH_TRUST: DIRECT_SINGLE_VENDOR or VOUCHER_VALIDATED linkages (clean)
- MEDIUM_TRUST: SUBSTRING_SINGLE_VENDOR linkages
- LOW_TRUST: DIRECT_MULTI_VENDOR linkages (needs review)
- TEMPORAL_CONFLICT: same account active with multiple services in overlapping periods
- VENDOR_MISMATCH: detected_vendor doesn't match billing_vendor

This module adds metadata for QA review but does NOT filter/delete linkages.

Usage:
    python -m normalization_engines.account_linkage.filter_conflicts \\
        --lookup account_service_lookup.csv \\
        --billing billing_charges.csv \\
        --output account_service_lookup_analyzed.csv \\
        --report analysis_report.csv
"""

import pandas as pd
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Set
from datetime import datetime


# Link type to trust level mapping
LINK_TYPE_TRUST = {
    'DIRECT_SINGLE_VENDOR': 'HIGH',
    'VOUCHER_VALIDATED': 'HIGH',
    'SUBSTRING_SINGLE_VENDOR': 'MEDIUM',
    'DIRECT_MULTI_VENDOR': 'LOW',
    'VOUCHER_ONLY': 'NONE'
}

# Link type to review priority mapping
LINK_TYPE_PRIORITY = {
    'DIRECT_SINGLE_VENDOR': 'LOW',  # High trust = low priority for review
    'VOUCHER_VALIDATED': 'LOW',
    'SUBSTRING_SINGLE_VENDOR': 'MEDIUM',
    'DIRECT_MULTI_VENDOR': 'HIGH',  # Low trust = high priority for review
    'VOUCHER_ONLY': 'HIGH'
}


def normalize_vendor(name: str) -> str:
    """Normalize vendor name for comparison."""
    if not name or pd.isna(name):
        return ''

    name = str(name).lower().strip()

    # Remove common suffixes
    for suffix in [', inc', ' inc', ', llc', ' llc', ', ltd', ' ltd',
                   ' corp', ' corporation', ' co', ' company', ' services',
                   ' service', ' disposal', ' waste', ' recycling', ' refuse',
                   ' sanitation', ' hauling', ' environmental']:
        name = name.replace(suffix, '')

    # Remove punctuation
    name = name.replace(',', '').replace('.', '').replace('-', ' ')
    name = name.replace("'", '').replace('"', '')

    # Collapse whitespace
    return ' '.join(name.split())


def vendors_match(vendor1: str, vendor2: str) -> bool:
    """Check if two vendor names likely refer to the same entity."""
    v1 = normalize_vendor(vendor1)
    v2 = normalize_vendor(vendor2)

    if not v1 or not v2:
        return False

    if v1 == v2:
        return True

    v1_words = v1.split()
    v2_words = v2.split()

    # First word match (unless ambiguous)
    ambiguous = {'best', 'all', 'american', 'city', 'national', 'united',
                 'first', 'green', 'clean', 'pro', 'a', 'the', 'new', 'big'}

    if v1_words and v2_words and v1_words[0] == v2_words[0]:
        if v1_words[0] not in ambiguous:
            return True
        elif len(v1_words) >= 2 and len(v2_words) >= 2 and v1_words[1] == v2_words[1]:
            return True

    # Substring match
    if len(v1) > len(v2) * 1.5 and v2 in v1:
        return True
    if len(v2) > len(v1) * 1.5 and v1 in v2:
        return True

    return False


def parse_month(date_str: str) -> Optional[str]:
    """Parse date to YYYY-MM format."""
    if not date_str or pd.isna(date_str):
        return None

    date_str = str(date_str).strip()
    for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M:%S.%f']:
        try:
            dt = datetime.strptime(date_str.split()[0], fmt)
            return dt.strftime('%Y-%m')
        except ValueError:
            continue
    return None


def analyze_linkages(
    lookup_path: str,
    billing_path: str,
    output_path: str,
    report_path: str = None
) -> dict:
    """
    Analyze linkages and add QA flags based on link_type.

    Args:
        lookup_path: Path to account_service_lookup.csv
        billing_path: Path to billing_charges CSV
        output_path: Path for output with analysis columns
        report_path: Optional path for summary report

    Returns:
        Statistics dict
    """
    print("Loading lookup table...")
    lookup_df = pd.read_csv(lookup_path, dtype=str)
    print(f"  {len(lookup_df):,} rows, {lookup_df['service_id'].nunique():,} unique services")

    # Check for link_type column (v3) vs confidence column (v2)
    has_link_type = 'link_type' in lookup_df.columns
    has_confidence = 'confidence' in lookup_df.columns

    if has_link_type:
        print(f"  link_type column found - using v3 trust-based analysis")
        link_type_counts = lookup_df['link_type'].value_counts()
        for lt, count in link_type_counts.items():
            trust = LINK_TYPE_TRUST.get(lt, 'UNKNOWN')
            print(f"    {lt}: {count:,} ({trust} trust)")
    elif has_confidence:
        print(f"  confidence column found - using v2 analysis (legacy)")
        confidence_counts = lookup_df['confidence'].value_counts()
        for conf, count in confidence_counts.items():
            print(f"    {conf}: {count:,}")

    # Load billing data for temporal analysis
    print("\nLoading billing charges...")
    try:
        billing_cols = ['service_id', 'vendor_name', 'transaction_date']
        billing_df = pd.read_csv(billing_path, dtype=str, usecols=billing_cols)
    except ValueError:
        billing_df = pd.read_csv(billing_path, dtype=str)

    billing_df = billing_df[~billing_df['service_id'].isin(['0', '', 'nan', None])]
    billing_df = billing_df[billing_df['service_id'].notna()]
    print(f"  {len(billing_df):,} billing records")

    # Parse months
    billing_df['month'] = billing_df['transaction_date'].apply(parse_month)

    # Build billing index: service_id -> {vendor: {months}}
    print("Building billing index...")
    billing_index = defaultdict(lambda: defaultdict(set))

    for _, row in billing_df.iterrows():
        sid = str(row['service_id']).strip()
        vendor = str(row['vendor_name']).strip() if pd.notna(row.get('vendor_name')) else ''
        month = row['month']

        if sid and vendor and month:
            billing_index[sid][vendor].add(month)

    print(f"  Indexed {len(billing_index):,} services")

    # ==========================================================================
    # ANALYSIS PHASE
    # ==========================================================================

    print("\nAnalyzing linkages...")
    results = []
    category_counts = defaultdict(int)

    # Group by account_number to find potential conflicts
    account_groups = lookup_df.groupby('account_number')

    for account_num, group in account_groups:
        service_ids = group['service_id'].unique()

        # Single service = no temporal conflict possible
        if len(service_ids) == 1:
            temporal_status = 'SINGLE_SERVICE'
        else:
            # Multiple services - check for temporal overlap
            all_months = {}  # service_id -> set of months

            for sid in service_ids:
                sid = str(sid)
                if sid in billing_index:
                    # Collect all months across all vendors for this service
                    months = set()
                    for vendor_months in billing_index[sid].values():
                        months.update(vendor_months)
                    all_months[sid] = months

            # Check for overlap between services
            has_overlap = False
            overlap_services = []

            service_list = list(all_months.keys())
            for i, s1 in enumerate(service_list):
                for s2 in service_list[i + 1:]:
                    if all_months[s1] & all_months[s2]:
                        has_overlap = True
                        overlap_services.extend([s1, s2])

            if has_overlap:
                temporal_status = 'TEMPORAL_CONFLICT'
            elif len(all_months) < len(service_ids):
                temporal_status = 'NO_BILLING_DATA'
            else:
                temporal_status = 'SEQUENTIAL'

        # Process each row in the group
        for _, row in group.iterrows():
            result = dict(row)

            detected = row.get('detected_vendor', '')
            billing = row.get('billing_vendor', '')
            link_type = row.get('link_type', '')

            # Check vendor match
            vendor_matches = vendors_match(detected, billing)

            # Determine trust level and category
            if has_link_type:
                trust_level = LINK_TYPE_TRUST.get(link_type, 'UNKNOWN')
                base_priority = LINK_TYPE_PRIORITY.get(link_type, 'MEDIUM')
            else:
                # Legacy v2 confidence mapping
                confidence = row.get('confidence', '')
                trust_level = confidence if confidence else 'UNKNOWN'
                base_priority = 'HIGH' if confidence == 'LOW' else \
                               'MEDIUM' if confidence == 'MEDIUM' else 'LOW'

            # Determine final category
            if temporal_status == 'TEMPORAL_CONFLICT':
                category = 'TEMPORAL_CONFLICT'
                review_priority = 'HIGH'
            elif trust_level == 'LOW':
                category = 'LOW_TRUST'
                review_priority = 'HIGH'
            elif not vendor_matches and trust_level != 'HIGH':
                category = 'VENDOR_MISMATCH'
                review_priority = 'MEDIUM'
            elif trust_level == 'HIGH':
                category = 'HIGH_TRUST'
                review_priority = 'LOW'
            elif trust_level == 'MEDIUM':
                category = 'MEDIUM_TRUST'
                review_priority = 'MEDIUM'
            else:
                category = 'UNCLASSIFIED'
                review_priority = 'MEDIUM'

            result['trust_level'] = trust_level
            result['qa_category'] = category
            result['review_priority'] = review_priority
            result['temporal_status'] = temporal_status
            result['vendor_matches'] = vendor_matches

            results.append(result)
            category_counts[category] += 1

    # Save results
    results_df = pd.DataFrame(results)

    # Column order
    priority_cols = ['detected_vendor', 'account_number', 'service_id', 'billing_vendor',
                     'invoice_number', 'link_type', 'trust_level',
                     'qa_category', 'review_priority', 'temporal_status', 'vendor_matches']
    cols = [c for c in priority_cols if c in results_df.columns]
    other_cols = [c for c in results_df.columns if c not in cols]
    results_df = results_df[cols + other_cols]

    results_df.to_csv(output_path, index=False)
    print(f"\nSaved {len(results_df):,} rows to {output_path}")

    # Generate report
    if report_path:
        report_data = []

        # Category summary
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            services = results_df[results_df['qa_category'] == cat]['service_id'].nunique()
            report_data.append({
                'category': cat,
                'linkage_count': count,
                'service_count': services,
                'pct_of_total': f"{100 * count / len(results_df):.1f}%"
            })

        report_df = pd.DataFrame(report_data)
        report_df.to_csv(report_path, index=False)
        print(f"Saved report to {report_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("QUALITY ANALYSIS SUMMARY (v3 - Trust-Based)")
    print("=" * 60)
    print(f"\nTotal linkages: {len(results_df):,}")
    print(f"Unique services: {results_df['service_id'].nunique():,}")
    print(f"Unique accounts: {results_df['account_number'].nunique():,}")

    print("\nBy QA Category:")
    for cat in ['HIGH_TRUST', 'MEDIUM_TRUST', 'LOW_TRUST',
                'TEMPORAL_CONFLICT', 'VENDOR_MISMATCH', 'UNCLASSIFIED']:
        if cat in category_counts:
            count = category_counts[cat]
            pct = 100 * count / len(results_df)
            print(f"  {cat:20} {count:>6,} ({pct:>5.1f}%)")

    print("\nBy Review Priority:")
    for priority in ['HIGH', 'MEDIUM', 'LOW']:
        count = len(results_df[results_df['review_priority'] == priority])
        pct = 100 * count / len(results_df)
        print(f"  {priority:10} {count:>6,} ({pct:>5.1f}%)")

    if has_link_type:
        print("\nBy Link Type:")
        for lt in ['DIRECT_SINGLE_VENDOR', 'VOUCHER_VALIDATED',
                   'SUBSTRING_SINGLE_VENDOR', 'DIRECT_MULTI_VENDOR']:
            count = len(results_df[results_df['link_type'] == lt])
            pct = 100 * count / len(results_df) if len(results_df) > 0 else 0
            trust = LINK_TYPE_TRUST.get(lt, 'UNKNOWN')
            print(f"  {lt:25} {count:>6,} ({pct:>5.1f}%) [{trust}]")

    print("\nBy Trust Level:")
    for trust in ['HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']:
        count = len(results_df[results_df['trust_level'] == trust])
        pct = 100 * count / len(results_df) if len(results_df) > 0 else 0
        print(f"  {trust:10} {count:>6,} ({pct:>5.1f}%)")

    return {
        'total_linkages': len(results_df),
        'unique_services': results_df['service_id'].nunique(),
        'unique_accounts': results_df['account_number'].nunique(),
        'categories': dict(category_counts)
    }


def generate_review_files(
    analyzed_path: str,
    output_dir: str
) -> None:
    """
    Split analyzed file into separate review files by priority.

    Args:
        analyzed_path: Path to analyzed lookup CSV
        output_dir: Directory for output files
    """
    df = pd.read_csv(analyzed_path, dtype=str)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # HIGH priority - low trust and temporal conflicts
    high = df[df['review_priority'] == 'HIGH']
    if len(high) > 0:
        high.to_csv(output_dir / 'review_HIGH_priority.csv', index=False)
        print(f"HIGH priority: {len(high):,} rows -> review_HIGH_priority.csv")

    # MEDIUM priority - medium trust and vendor mismatches
    medium = df[df['review_priority'] == 'MEDIUM']
    if len(medium) > 0:
        medium.to_csv(output_dir / 'review_MEDIUM_priority.csv', index=False)
        print(f"MEDIUM priority: {len(medium):,} rows -> review_MEDIUM_priority.csv")

    # LOW trust linkages specifically
    if 'trust_level' in df.columns:
        low_trust = df[df['trust_level'] == 'LOW']
        if len(low_trust) > 0:
            low_trust.to_csv(output_dir / 'review_LOW_trust.csv', index=False)
            print(f"LOW trust: {len(low_trust):,} rows -> review_LOW_trust.csv")

    # Temporal conflicts specifically
    temporal = df[df['qa_category'] == 'TEMPORAL_CONFLICT']
    if len(temporal) > 0:
        temporal.to_csv(output_dir / 'review_temporal_conflicts.csv', index=False)
        print(f"Temporal conflicts: {len(temporal):,} rows -> review_temporal_conflicts.csv")

    # Vendor mismatches
    if 'vendor_matches' in df.columns:
        vendor_mismatch = df[df['vendor_matches'] == 'False']
        if len(vendor_mismatch) > 0:
            vendor_mismatch.to_csv(output_dir / 'review_vendor_mismatch.csv', index=False)
            print(f"Vendor mismatches: {len(vendor_mismatch):,} rows -> review_vendor_mismatch.csv")

    # By link type (if present)
    if 'link_type' in df.columns:
        for lt in df['link_type'].unique():
            if pd.notna(lt) and lt:
                lt_df = df[df['link_type'] == lt]
                filename = f'review_link_type_{lt.lower()}.csv'
                lt_df.to_csv(output_dir / filename, index=False)
                print(f"{lt}: {len(lt_df):,} rows -> {filename}")


def generate_coverage_report(
    lookup_path: str,
    services_path: str,
    output_path: str
) -> dict:
    """
    Generate coverage report showing how many services are linked.

    Args:
        lookup_path: Path to account_service_lookup.csv
        services_path: Path to services CSV with all active services
        output_path: Path for coverage report output

    Returns:
        Coverage statistics dict
    """
    print("Loading lookup table...")
    lookup_df = pd.read_csv(lookup_path, dtype=str)
    linked_services = set(lookup_df['service_id'].unique())
    print(f"  {len(linked_services):,} services in lookup table")

    print("Loading services list...")
    services_df = pd.read_csv(services_path, dtype=str)
    all_services = set(services_df['service_id'].unique())
    print(f"  {len(all_services):,} total services")

    # Calculate coverage
    linked = linked_services & all_services
    unlinked = all_services - linked_services

    coverage_pct = 100 * len(linked) / len(all_services) if all_services else 0

    print(f"\nCoverage: {len(linked):,} / {len(all_services):,} ({coverage_pct:.1f}%)")
    print(f"Unlinked: {len(unlinked):,} services")

    # Group by link_type if available
    if 'link_type' in lookup_df.columns:
        print("\nCoverage by Link Type:")
        for lt in ['DIRECT_SINGLE_VENDOR', 'VOUCHER_VALIDATED',
                   'SUBSTRING_SINGLE_VENDOR', 'DIRECT_MULTI_VENDOR']:
            lt_services = set(lookup_df[lookup_df['link_type'] == lt]['service_id'].unique())
            count = len(lt_services & all_services)
            pct = 100 * count / len(all_services) if all_services else 0
            print(f"  {lt}: {count:,} ({pct:.1f}%)")

    # Save unlinked services
    if output_path:
        unlinked_df = services_df[services_df['service_id'].isin(unlinked)]
        unlinked_df.to_csv(output_path, index=False)
        print(f"\nSaved {len(unlinked_df):,} unlinked services to {output_path}")

    return {
        'total_services': len(all_services),
        'linked_services': len(linked),
        'unlinked_services': len(unlinked),
        'coverage_pct': coverage_pct
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Account linkage quality analysis (v3)')
    parser.add_argument('--lookup', required=True, help='Path to lookup CSV')
    parser.add_argument('--billing', required=True, help='Path to billing charges CSV')
    parser.add_argument('--output', required=True, help='Output path for analyzed CSV')
    parser.add_argument('--report', help='Optional path for summary report CSV')
    parser.add_argument('--split-reviews', action='store_true',
                        help='Generate separate files by review priority')
    parser.add_argument('--coverage-report', help='Path to services CSV for coverage report')
    parser.add_argument('--unlinked-output', help='Output path for unlinked services')

    args = parser.parse_args()

    stats = analyze_linkages(
        args.lookup, args.billing, args.output, args.report
    )

    if args.split_reviews:
        generate_review_files(args.output, Path(args.output).parent)

    if args.coverage_report:
        coverage_stats = generate_coverage_report(
            args.lookup,
            args.coverage_report,
            args.unlinked_output or 'unlinked_services.csv'
        )
