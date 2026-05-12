"""
Pattern executor — thin runtime for JSON invoice pattern records.

Loads JSON pattern records, routes OCR text, extracts fields,
applies transforms, validates, and writes vendor extract CSVs.

No vendor-specific code. All knowledge lives in the pattern record.
"""

import csv
import json
import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Charge code reference — loaded once at module level
# ---------------------------------------------------------------------------

def _load_charge_ref():
    """Load canonical charge codes and aliases from output directory.

    Returns:
        canonical_set: set of valid charge code strings
        recurring_codes: set of charge codes with classification='recurring'
        aliases: dict mapping non-canonical → canonical (string or {equip_type: canonical})
    """
    ref_path = Path(__file__).parent / 'output' / 'charge_code_ref.csv'
    alias_path = Path(__file__).parent / 'output' / 'charge_code_aliases.json'

    canonical_set = set()
    recurring_codes = set()
    if ref_path.exists():
        with open(ref_path, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get('charge_code', '').strip()
                if code:
                    canonical_set.add(code)
                    if row.get('classification', '').strip() == 'recurring':
                        recurring_codes.add(code)

    aliases = {}
    if alias_path.exists():
        raw = json.loads(alias_path.read_text())
        aliases = {k: v for k, v in raw.items() if not k.startswith('_')}

    return canonical_set, recurring_codes, aliases


_CANONICAL_CODES, _RECURRING_CODES, _CHARGE_ALIASES = _load_charge_ref()

# Recurring container equipment types — the only containers that require a
# fixed pickup schedule. Roll-offs and compactors are on-demand (ON_CALL).
_RECURRING_EQUIPMENT = {'FRONT_LOAD', 'CART', 'REAR_LOAD'}

# Roll-off / compactor equipment types — disposal charges on these require tonnage.
_ROLLOFF_EQUIPMENT = {'OPEN_TOP', 'COMPACTOR'}

# Disposal charge codes that are billed by weight — must have tonnage on roll-offs.
# Empty & Return is a flat-rate haul and does NOT require tonnage.
_DISPOSAL_CODES = {'Disposal Charge', 'Disposal', 'Disposal Charge Special Waste'}

# The charge codes that represent an actual container pickup on a recurring
# container. Only these trigger NO_SCHEDULE — rentals, fees, and surcharges
# hung to the same container do not independently require a schedule.
_PICKUP_SERVICE_CODES = {
    'Monthly Service Commercial',
    'Monthly Service Industrial',
    'Hand Pick Up Commercial',
    'Hand Pick Up industrial',
    'Recycling',
    'Recycling Service Pick Up',
    'Recycling Service Material',
    'Recycling Service Weight',
    'Addtl Hand Pick Up Commercial',
    'Addtl Recycling Service Pick Up',
}


def _resolve_alias(code, equipment_type, aliases, canonical_set):
    """Resolve a charge code via alias map; return (resolved_code, was_aliased)."""
    if not code:
        return code, False

    if code in canonical_set:
        return code, False

    alias = aliases.get(code)
    if alias is None:
        return code, False

    if isinstance(alias, dict):
        resolved = alias.get(equipment_type or '', alias.get('default', code))
    else:
        resolved = alias

    return resolved, (resolved != code)


_SCHEDULE_ALIASES = {
    'On Call': 'ON_CALL',
    'on call': 'ON_CALL',
    'Every 2 Weeks x1': 'Biweekly',
    'Every Other Week': 'Biweekly',
    '1X_WEEKLY': 'Weekly x1',
    '2X_WEEKLY': 'Weekly x2',
    '3X_WEEKLY': 'Weekly x3',
    '4X_WEEKLY': 'Weekly x4',
    '5X_WEEKLY': 'Weekly x5',
    '6X_WEEKLY': 'Weekly x6',
}

# Canonical material name mapping — case-insensitive lookup, applied post-pipeline
_MATERIAL_CANONICAL = {
    'msw': 'Trash',
    'trash': 'Trash',
    'recycling': 'Recycling',
    'organics': 'Organics',
    'grease': 'Grease',
    'wood': 'Wood',
    'yard_waste': 'Green Waste',
    'occ': 'Cardboard',
    'c&d': 'C&D',
    'single stream': 'Single Stream',
    'cardboard': 'Cardboard',
    'scrap metal': 'Scrap Metal',
    'green waste': 'Green Waste',
}

# Regex for equipment_size normalization — matches "N[space]UNIT" or "NUNIT"
_SIZE_RE = re.compile(
    r'^0*(\d+(?:\.\d+)?)\s*(YARD|YARDS|YD|YDS|GAL|GALLON|GALLONS|G)\b',
    re.IGNORECASE,
)
# Regex for duplicated-number sizes like "3 3YD", "64 64G", "35 35G"
_SIZE_DUP_RE = re.compile(
    r'^(\d+)\s+\1\s*(YARD|YARDS|YD|YDS|GAL|GALLON|GALLONS|G)$',
    re.IGNORECASE,
)


def _norm_size_unit(raw_unit):
    u = raw_unit.upper()
    return 'GAL' if u in ('GAL', 'GALLON', 'GALLONS', 'G') else 'YD'


def _normalize_equipment_size(size):
    """Normalize equipment_size to canonical 'N YD' / 'N GAL' format."""
    if not size:
        return size
    size = size.strip()
    # Duplicated: "3 3YD" → "3 YD", "64 64G" → "64 GAL"
    m = _SIZE_DUP_RE.match(size)
    if m:
        return f'{m.group(1)} {_norm_size_unit(m.group(2))}'
    # Standard: "8YD", "30 Yard", "96GAL", "08 YD" etc.
    m = _SIZE_RE.match(size)
    if m:
        num = m.group(1)
        # Strip leading zeros from integer part
        num = str(int(float(num))) if '.' not in num else num
        return f'{num} {_norm_size_unit(m.group(2))}'
    return size


def _normalize_charge_codes(charges):
    """Normalize charge codes and set per-charge flags.

    For each charge:
    - Apply alias mapping if code is non-canonical
    - Normalize schedule values to canonical format
    - Set charge['_flag'] list with HITL:NO_CHARGE_CODE or HITL:charge_code=X
    - Flag recurring-classified charges missing schedule as NO_SCHEDULE
    """
    for charge in charges:
        charge_flags = []
        code = (charge.get('charge_code') or '').strip()
        equip = (charge.get('equipment_type') or '').strip()

        # Normalize material to canonical title-case name
        mat = (charge.get('material') or '').strip()
        if mat:
            canon_mat = _MATERIAL_CANONICAL.get(mat.lower())
            if canon_mat:
                charge['material'] = canon_mat

        # Normalize equipment_size to canonical "N YD" / "N GAL" format
        raw_size = charge.get('equipment_size') or ''
        if raw_size:
            normed = _normalize_equipment_size(raw_size)
            if normed != raw_size:
                charge['equipment_size'] = normed

        # Normalize schedule to canonical format
        sched = (charge.get('schedule') or '').strip()
        if sched in _SCHEDULE_ALIASES:
            charge['schedule'] = _SCHEDULE_ALIASES[sched]
            sched = charge['schedule']

        if not code:
            charge_flags.append('HITL:NO_CHARGE_CODE')
        else:
            resolved, was_aliased = _resolve_alias(code, equip, _CHARGE_ALIASES, _CANONICAL_CODES)
            if was_aliased:
                charge['charge_code'] = resolved
                code = resolved
            if code and code not in _CANONICAL_CODES:
                charge_flags.append(f'HITL:charge_code={code}')
            elif code in _PICKUP_SERVICE_CODES and equip in _RECURRING_EQUIPMENT and not sched:
                charge_flags.append('NO_SCHEDULE')
            elif code in _DISPOSAL_CODES and equip in _ROLLOFF_EQUIPMENT:
                weight = charge.get('weight')
                if not weight and weight != 0:
                    charge_flags.append('NO_TONNAGE')

        charge['_charge_flags'] = charge_flags


# ---------------------------------------------------------------------------
# Handler registry — 20 types, no vendor-specific logic
# ---------------------------------------------------------------------------

def _handler_currency_parse(context, config):
    """Strip $, commas → float. Config: field, strip_comma, strip_dollar."""
    field = config['field']
    val = context.get(field)
    if val is None:
        return
    if isinstance(val, (int, float)):
        return
    s = str(val)
    if config.get('strip_dollar', True):
        s = s.replace('$', '')
    if config.get('strip_comma', True):
        s = s.replace(',', '')
    try:
        context[field] = float(s)
    except ValueError:
        context[field] = None


def _handler_date_parse(context, config):
    """Parse date string. Config: field, formats (list of strftime fmts)."""
    from datetime import datetime
    field = config['field']
    val = context.get(field)
    if val is None:
        return
    for fmt in config.get('formats', ['%m/%d/%Y']):
        try:
            context[field] = datetime.strptime(str(val).strip(), fmt).strftime('%m/%d/%Y')
            return
        except ValueError:
            continue


def _handler_regex_capture(context, config):
    """Extract value via regex from a field. Config: source_field, pattern, output_field, group (default 1).
    skip_if_set: if true, skip if output_field already has a value."""
    if config.get('skip_if_set') and context.get(config['output_field']):
        return
    src = context.get(config['source_field'], '')
    if not src:
        return
    flags = _compile_flags(config.get('flags', []))
    m = re.search(config['pattern'], str(src), flags)
    if m:
        grp = config.get('group', 1)
        value = m.group(grp)
        tmpl = config.get('transform')
        if tmpl and isinstance(tmpl, str):
            value = tmpl.replace('{0}', value)
        context[config['output_field']] = value
        if config.get('filter_from_source', False):
            context[config['source_field']] = re.sub(config['pattern'], '', str(src), flags=flags).strip()


def _handler_regex_strip(context, config):
    """Remove pattern from text. Config: field, pattern, flags."""
    field = config['field']
    val = context.get(field)
    if val is None:
        return
    flags = _compile_flags(config.get('flags', []))
    context[field] = re.sub(config['pattern'], config.get('replacement', ''), str(val), flags=flags)


def _handler_keyword_classify(context, config):
    """Ordered keyword→label rules on lowercased text. First match wins.
    Config: source_field, output_field, rules (list of {keywords, label}).
    keywords can be a list (all must match) or a string (single match).
    skip_if_set: if true, skip if output_field already has a value.
    """
    if config.get('skip_if_set') and context.get(config['output_field']):
        return
    src = str(context.get(config['source_field'], '')).lower()
    if not src:
        return
    for rule in config['rules']:
        kw = rule['keywords']
        if isinstance(kw, list):
            if all(k in src for k in kw):
                context[config['output_field']] = rule['label']
                return
        elif isinstance(kw, str):
            if kw in src:
                context[config['output_field']] = rule['label']
                return
    if 'default' in config:
        context[config['output_field']] = config['default']


def _handler_lookup_map(context, config):
    """Normalize values via lookup table. Config: field, map, case_insensitive, default."""
    field = config['field']
    val = context.get(field)
    if val is None:
        return
    lookup = config['map']
    key = str(val).lower() if config.get('case_insensitive', True) else str(val)
    # Try exact match first
    for k, v in lookup.items():
        cmp = k.lower() if config.get('case_insensitive', True) else k
        if cmp == key:
            context[field] = v
            return
    # Try substring match if enabled
    if config.get('substring_match', False):
        for k, v in lookup.items():
            cmp = k.lower() if config.get('case_insensitive', True) else k
            if cmp in key:
                context[field] = v
                return
    if 'default' in config:
        context[field] = config['default']


def _handler_charge_normalize(context, config):
    """Equipment-class-aware charge code normalization.
    Config: charge_type_field, equipment_type_field, output_field,
            equipment_class_map, charge_code_map.
    """
    charge_type = context.get(config['charge_type_field'])
    if not charge_type:
        return
    eq_type = context.get(config['equipment_type_field'])
    eq_class_map = config['equipment_class_map']
    eq_class = eq_class_map.get(eq_type, 'commercial')

    code_map = config['charge_code_map']
    val = code_map.get(charge_type)
    if isinstance(val, dict):
        context[config['output_field']] = val.get(eq_class, val.get('commercial'))
    elif val:
        context[config['output_field']] = val


def _handler_multi_heuristic(context, config):
    """Try multiple amount extraction strategies in order.
    Config: source_field, output_fields (charge_total, unit_rate, qty, tax),
            weight_pattern (optional), qty_cap.
    """
    src = str(context.get(config['source_field'], ''))
    if not src:
        return

    # Extract weight first (filter from amounts)
    wt_pattern = config.get('weight_pattern')
    if wt_pattern:
        wt_m = re.search(wt_pattern, src, re.I)
        if wt_m:
            context[config.get('weight_field', 'weight')] = float(wt_m.group(1))
            context[config.get('weight_unit_field', 'weight_unit')] = 'TONS'

    # Extract all amounts (positive and negative)
    neg_re = config.get('neg_amount_pattern', r'\(\$?([\d,]+\.\d{2})\)')
    pos_re = config.get('pos_amount_pattern', r'\$?([\d,]+\.\d{2})')
    combined_re = f'{neg_re}|{pos_re}'

    amts = []
    for m in re.finditer(combined_re, src):
        if m.group(1):  # parenthesized = negative
            amts.append(-float(m.group(1).replace(',', '')))
        else:
            amts.append(float(m.group(2).replace(',', '')))

    if not amts:
        return

    out = config.get('output_fields', {})
    charge_total_field = out.get('charge_total', 'charge_total')
    unit_rate_field = out.get('unit_rate', 'unit_rate')
    qty_field = out.get('qty', 'qty')

    context[charge_total_field] = amts[-1]

    if len(amts) >= 3:
        context[qty_field] = amts[0]
        context[unit_rate_field] = amts[1]
    elif len(amts) == 2 and amts[0] != amts[-1]:
        context[qty_field] = amts[0]
        context[unit_rate_field] = amts[0]  # rate = first when 2 amounts


def _handler_parent_container(context, config):
    """Attach orphan charges to nearest parent. Bidirectional by default.
    Config: charges_field, inherit_fields, direction (backward|forward|both),
            scope_field (optional - only inherit within same scope, e.g. site_id),
            skip_zero (optional - skip charges with charge_total == 0),
            parent_key (optional - field that identifies a parent, default 'equipment_type').
    Operates on a list of charge dicts in context.
    """
    charges = context.get(config['charges_field'], [])
    if not charges:
        return
    inherit = config.get('inherit_fields', ['equipment_type', 'equipment_size', 'material'])
    direction = config.get('direction', 'both')
    scope_field = config.get('scope_field')
    skip_zero = config.get('skip_zero', False)
    parent_key = config.get('parent_key', 'equipment_type')

    for i, charge in enumerate(charges):
        if charge.get(parent_key):
            continue
        if skip_zero and (charge.get('charge_total') or 0) == 0:
            continue
        scope_val = charge.get(scope_field) if scope_field else None
        # Search backward
        parent = None
        if direction in ('backward', 'both'):
            for j in range(i - 1, -1, -1):
                if scope_field and charges[j].get(scope_field) != scope_val:
                    continue
                if charges[j].get(parent_key):
                    parent = charges[j]
                    break
        # Search forward
        if not parent and direction in ('forward', 'both'):
            for j in range(i + 1, len(charges)):
                if scope_field and charges[j].get(scope_field) != scope_val:
                    continue
                if charges[j].get(parent_key):
                    parent = charges[j]
                    break
        if parent:
            for f in inherit:
                if not charge.get(f) and parent.get(f):
                    charge[f] = parent[f]


def _handler_line_filter(context, config):
    """Drop lines matching reject pattern. Config: field, pattern, flags."""
    field = config['field']
    val = context.get(field)
    if val is None:
        return
    flags = _compile_flags(config.get('flags', []))
    pat = re.compile(config['pattern'], flags)
    if isinstance(val, list):
        context[field] = [line for line in val if not pat.search(str(line))]
    elif isinstance(val, str):
        lines = val.split('\n')
        context[field] = '\n'.join(line for line in lines if not pat.search(line))


def _handler_split_field(context, config):
    """Split one field into multiple on delimiter. Config: field, delimiter, output_fields."""
    val = context.get(config['field'])
    if val is None:
        return
    parts = str(val).split(config['delimiter'])
    for i, out_field in enumerate(config['output_fields']):
        if i < len(parts):
            context[out_field] = parts[i].strip()


def _handler_date_split(context, config):
    """Split text block by date lines. Config: source_field, output_field, date_pattern."""
    src = context.get(config['source_field'], '')
    if not src:
        return
    pat = re.compile(config['date_pattern'])
    blocks = []
    current = []
    for line in str(src).split('\n'):
        if pat.match(line.strip()) and current:
            blocks.append('\n'.join(current))
            current = []
        current.append(line)
    if current:
        blocks.append('\n'.join(current))
    context[config['output_field']] = blocks


def _handler_column_positional(context, config):
    """Extract amounts from columnar OCR by position. Config: source_field, columns."""
    pass  # Placeholder — not needed for Robinson


def _handler_line_classify(context, config):
    """Classify lines by type. Config: source_field, output_field, rules."""
    pass  # Placeholder — not needed for Robinson


def _handler_regex_parse_multi(context, config):
    """Parse a field via regex and set multiple output fields from named groups.
    Supports value maps per group and a fixed-value set on match.
    Config: source_field, pattern, flags, group_outputs (list of {group, output_field, map, transform}).
    set_on_match: dict of field→value to set unconditionally when pattern matches.
    skip_if_set: field name — skip if this field already set.
    """
    if config.get('skip_if_set') and context.get(config['skip_if_set']):
        return
    src = str(context.get(config['source_field'], ''))
    if not src:
        return
    flags = _compile_flags(config.get('flags', []))
    m = re.search(config['pattern'], src, flags)
    if not m:
        return

    for go in config.get('group_outputs', []):
        try:
            val = m.group(go['group'])
        except (IndexError, re.error):
            continue
        if val is None:
            continue
        val = val.strip()
        # Apply transform
        transform = go.get('transform')
        if transform == 'lower':
            val = val.lower()
        elif transform == 'upper':
            val = val.upper()
        elif transform == 'replace_O_0':
            val = val.replace('O', '0')
        # Apply value map
        vmap = go.get('map')
        if vmap:
            case_key = val.lower() if go.get('case_insensitive', True) else val
            for k, v in vmap.items():
                if k.lower() == case_key:
                    val = v
                    break
            else:
                # If no map hit, title-case
                if go.get('title_default', False):
                    val = val.title()
        # Apply suffix
        suffix = go.get('suffix')
        if suffix:
            val = f"{val} {suffix}"
        # Apply format template
        fmt = go.get('format')
        if fmt:
            # {value} placeholder
            val = fmt.replace('{value}', val)
            # Check for other group refs
            for g2 in config.get('group_outputs', []):
                try:
                    g2val = m.group(g2['group'])
                    if g2val:
                        val = val.replace('{' + g2['group'] + '}', g2val.strip())
                except (IndexError, re.error):
                    pass
        context[go['output_field']] = val

    # Set fixed values on match
    for k, v in config.get('set_on_match', {}).items():
        context[k] = v


def _handler_single_line_parse(context, config):
    """Parse structured line into multiple fields. Config: source_field, pattern, field_map."""
    src = context.get(config['source_field'], '')
    if not src:
        return
    flags = _compile_flags(config.get('flags', []))
    m = re.search(config['pattern'], str(src), flags)
    if m:
        for group_name, out_field in config['field_map'].items():
            try:
                val = m.group(group_name)
                if val is not None:
                    context[out_field] = val.strip()
            except IndexError:
                pass


def _handler_contract_anchor_walk(context, config):
    """Walk lines, anchor identifies block boundaries.
    Config: source_field, anchor_pattern, charge_pattern, output_field.
    """
    pass  # Placeholder — will be implemented for WM


def _handler_multi_strategy(context, config):
    """Try multiple strategies, first match wins.
    Config: strategies (list of handler configs), each with type + config.
    """
    for strategy in config['strategies']:
        handler_type = strategy['type']
        handler_fn = HANDLER_REGISTRY.get(handler_type)
        if not handler_fn:
            continue
        # Snapshot context to detect changes
        before = dict(context)
        handler_fn(context, strategy)
        # If any output field changed, this strategy matched
        output_fields = strategy.get('output_fields_check', [])
        if output_fields:
            if any(context.get(f) != before.get(f) for f in output_fields):
                return
        else:
            if context != before:
                return


def _handler_line_join(context, config):
    """Join continuation lines (no date prefix) to previous line.
    Config: source_field, output_field, date_pattern (lines starting with date are new).
    """
    src = context.get(config['source_field'], '')
    if not src:
        return
    date_pat = re.compile(config['date_pattern'])
    lines = str(src).split('\n') if isinstance(src, str) else src
    joined = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if date_pat.match(stripped) or not joined:
            joined.append(stripped)
        else:
            joined[-1] = joined[-1] + ' ' + stripped
    context[config['output_field']] = joined


def _handler_dedup_summary(context, config):
    """Remove summary lines when detail lines exist for same category.
    Config: charges_field, summary_pattern, detail_match_field.
    """
    charges = context.get(config['charges_field'], [])
    if not charges:
        return
    summary_pat = re.compile(config['summary_pattern'], re.I)
    detail_field = config.get('detail_match_field', 'charge_type')

    # Find which categories have detail lines
    detail_categories = set()
    summary_indices = []
    for i, c in enumerate(charges):
        desc = str(c.get('description', '')).lower()
        m = summary_pat.search(desc)
        if m:
            summary_indices.append(i)
        else:
            cat = c.get(detail_field)
            if cat:
                detail_categories.add(cat)

    # Remove summary lines where detail exists
    to_remove = set()
    for i in summary_indices:
        cat = charges[i].get(detail_field)
        if cat and cat in detail_categories:
            to_remove.add(i)

    if to_remove:
        context[config['charges_field']] = [c for j, c in enumerate(charges) if j not in to_remove]


def _handler_wo_pair(context, config):
    """WO# pairing — charges sharing a WO# inherit material from each other.
    Specifically: haul charges without material inherit from disposal with same WO#.
    Config: charges_field, wo_field, material_field.
    """
    charges = context.get(config.get('charges_field', '_charges'), [])
    wo_field = config.get('wo_field', 'wo_number')
    mat_field = config.get('material_field', 'material')

    # Build WO → material map from charges that have both
    wo_material = {}
    for c in charges:
        wo = c.get(wo_field)
        mat = c.get(mat_field)
        if wo and mat:
            wo_material[wo] = mat

    # Apply to charges missing material
    for c in charges:
        wo = c.get(wo_field)
        if wo and not c.get(mat_field) and wo in wo_material:
            c[mat_field] = wo_material[wo]


def _handler_renormalize_codes(context, config):
    """Re-run charge_normalize on charges after parent_container resolves equipment.
    Config: charges_field, plus all charge_normalize config fields.
    Only re-normalizes charges where charge_code is currently None.
    """
    charges = context.get(config.get('charges_field', '_charges'), [])
    for charge in charges:
        if charge.get(config.get('output_field', 'charge_code')) is None:
            _handler_charge_normalize(charge, config)


def _handler_per_charge_post(context, config):
    """Re-run a list of per-charge handlers on all charges after post_processing.
    Config: charges_field, transforms (list of {type, ...} configs), skip_if_set (optional).
    """
    charges = context.get(config.get('charges_field', '_charges'), [])
    for charge in charges:
        for t_cfg in config.get('transforms', []):
            skip_field = t_cfg.get('skip_if_set')
            if skip_field and charge.get(skip_field):
                continue
            handler_fn = HANDLER_REGISTRY.get(t_cfg['type'])
            if handler_fn:
                handler_fn(charge, t_cfg)


def _handler_concat_fields(context, config):
    """Concatenate fields with separator. Config: fields, separator, output_field."""
    parts = []
    for f in config['fields']:
        val = context.get(f, '')
        if val:
            parts.append(str(val))
    if parts:
        context[config['output_field']] = config.get('separator', ' ').join(parts)


def _handler_copy_if_null(context, config):
    """Copy source to target if target is null/empty.
    Config: source_field, target_field.
    """
    if not context.get(config['target_field']):
        val = context.get(config['source_field'])
        if val is not None:
            context[config['target_field']] = val


def _handler_copy_if_not_null(context, config):
    """Copy source to target if source is not null/empty (override).
    Config: source_field, target_field.
    """
    val = context.get(config['source_field'])
    if val is not None and val != '':
        context[config['target_field']] = val


def _handler_copy_field_if(context, config):
    """Conditionally copy source to target when condition field matches value.
    Config: condition_field, condition_value, source_field, target_field.
    Also sets optional fixed fields via set_fields dict.
    """
    cond_val = context.get(config['condition_field'])
    if cond_val is None:
        return
    if str(cond_val).lower() != str(config['condition_value']).lower():
        return
    # Copy source -> target
    val = context.get(config['source_field'])
    if val is not None:
        context[config['target_field']] = val
    # Set any fixed fields
    for k, v in config.get('set_fields', {}).items():
        context[k] = v


def _handler_set_field(context, config):
    """Set a field to a computed value. Config: output_field, value (literal)
    or source_field + transform (lower, upper, strip).
    """
    if 'value' in config:
        context[config['output_field']] = config['value']
    elif 'source_field' in config:
        val = context.get(config['source_field'], '')
        transform = config.get('transform')
        if transform == 'lower':
            val = str(val).lower()
        elif transform == 'upper':
            val = str(val).upper()
        elif transform == 'strip':
            val = str(val).strip()
        context[config['output_field']] = val


# Handler registry
HANDLER_REGISTRY = {
    'currency_parse': _handler_currency_parse,
    'date_parse': _handler_date_parse,
    'regex_capture': _handler_regex_capture,
    'regex_strip': _handler_regex_strip,
    'keyword_classify': _handler_keyword_classify,
    'lookup_map': _handler_lookup_map,
    'charge_normalize': _handler_charge_normalize,
    'multi_heuristic': _handler_multi_heuristic,
    'parent_container': _handler_parent_container,
    'line_filter': _handler_line_filter,
    'split_field': _handler_split_field,
    'date_split': _handler_date_split,
    'column_positional': _handler_column_positional,
    'line_classify': _handler_line_classify,
    'regex_parse_multi': _handler_regex_parse_multi,
    'single_line_parse': _handler_single_line_parse,
    'contract_anchor_walk': _handler_contract_anchor_walk,
    'multi_strategy': _handler_multi_strategy,
    'line_join': _handler_line_join,
    'dedup_summary': _handler_dedup_summary,
    'concat_fields': _handler_concat_fields,
    'copy_if_null': _handler_copy_if_null,
    'copy_if_not_null': _handler_copy_if_not_null,
    'wo_pair': _handler_wo_pair,
    'renormalize_codes': _handler_renormalize_codes,
    'per_charge_post': _handler_per_charge_post,
    'set_field': _handler_set_field,
    'copy_field_if': _handler_copy_field_if,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_pdf_link(pdf_path):
    """Build file:// URL from pdf_path. Fix case, encode spaces."""
    if not pdf_path:
        return ''
    from urllib.parse import quote
    path = pdf_path.replace('/Invoices/', '/invoices/')
    encoded = quote(path, safe='/:@')
    return 'file://' + encoded


def _compile_flags(flag_list):
    """Convert flag name strings to re flags."""
    flag_map = {
        'IGNORECASE': re.IGNORECASE, 'I': re.IGNORECASE,
        'DOTALL': re.DOTALL, 'S': re.DOTALL,
        'MULTILINE': re.MULTILINE, 'M': re.MULTILINE,
    }
    result = 0
    for f in flag_list:
        result |= flag_map.get(f.upper(), 0)
    return result


# ---------------------------------------------------------------------------
# Core executor functions
# ---------------------------------------------------------------------------

def load_patterns(source='json', pattern_dir=None):
    """Load pattern records from JSON files.
    Returns list of pattern dicts.
    """
    if pattern_dir is None:
        pattern_dir = Path(__file__).parent / 'patterns' / 'json'
    else:
        pattern_dir = Path(pattern_dir)

    patterns = []
    for f in sorted(pattern_dir.glob('*.json')):
        with open(f, 'r') as fh:
            pat = json.load(fh)
            if pat.get('is_active', True):
                patterns.append(pat)
    # Sort by routing_priority (lower = higher priority)
    patterns.sort(key=lambda p: p.get('routing_priority', 100))
    return patterns


def route(ocr_text, patterns):
    """Match OCR text against pattern routing regexes. Returns first match or None."""
    for pat in patterns:
        regex = pat.get('routing_regex')
        if not regex:
            continue
        flags = _compile_flags(pat.get('routing_flags', []))
        if re.search(regex, ocr_text, flags):
            return pat
    return None


def extract(ocr_text, pattern):
    """Run extraction_stages against OCR text. Returns context dict."""
    context = {'_raw_text': ocr_text}

    for stage in pattern.get('extraction_stages', []):
        name = stage.get('name', 'unnamed')
        method = stage.get('method', 'search')
        regex = stage.get('pattern')
        if not regex:
            continue

        flags = _compile_flags(stage.get('flags', []))
        field_map = stage.get('field_map', {})

        # Skip stage if all mapped output fields already have values
        skip_fields = stage.get('skip_if_set', [])
        if skip_fields and all(context.get(f) for f in skip_fields):
            continue

        if method == 'search':
            m = re.search(regex, ocr_text, flags)
            if m:
                for group_name, out_field in field_map.items():
                    try:
                        val = m.group(group_name)
                        if val is not None:
                            context[out_field] = val.strip()
                    except (IndexError, re.error):
                        pass

        elif method == 'finditer':
            results = []
            for m in re.finditer(regex, ocr_text, flags):
                row = {}
                for group_name, out_field in field_map.items():
                    try:
                        val = m.group(group_name)
                        if val is not None:
                            row[out_field] = val.strip()
                    except (IndexError, re.error):
                        pass
                results.append(row)
            output_field = stage.get('output_field', f'_{name}')
            context[output_field] = results

        elif method == 'body_extract':
            # Extract a body region between start/end markers
            m = re.search(regex, ocr_text, flags)
            if m:
                out_field = stage.get('output_field', '_body')
                context[out_field] = m.group(stage.get('group', 1))

        elif method == 'body_extract_all':
            # Extract ALL matching body regions and concatenate (multi-page support)
            group_num = stage.get('group', 1)
            out_field = stage.get('output_field', '_body')
            parts = []
            for m in re.finditer(regex, ocr_text, flags):
                try:
                    parts.append(m.group(group_num))
                except (IndexError, re.error):
                    pass
            if parts:
                context[out_field] = '\n'.join(parts)

    return context


def transform(context, pattern):
    """Run execution_plan transforms against context. Returns updated context."""
    plan = pattern.get('execution_plan', [])
    rules = pattern.get('transform_rules', {})

    for step_key in plan:
        rule = rules.get(step_key)
        if not rule:
            continue
        handler_type = rule.get('type')
        handler_fn = HANDLER_REGISTRY.get(handler_type)
        if not handler_fn:
            continue
        handler_fn(context, rule)

    return context


def validate(context, pattern):
    """Validate extracted data against output_spec. Returns (valid, flags)."""
    spec = pattern.get('output_spec', {})
    flags = []

    # Header required fields
    for field in spec.get('required_header', []):
        if not context.get(field):
            flags.append(f'HDR_MISSING: {field}')

    # Charge-level validation
    charges = context.get('_charges', [])
    for i, charge in enumerate(charges):
        for field in spec.get('required_charge', []):
            if charge.get(field) is None:
                flags.append(f'CHG_MISSING[{i}]: {field}')

    # Charge sum check
    if spec.get('charge_sum_check', False):
        charge_sum = sum(c.get('charge_total', 0) or 0 for c in charges)
        charge_sum = round(charge_sum, 2)
        context['_charge_sum'] = charge_sum

        total_field = spec.get('total_field', 'invoice_total')
        total_val = context.get(total_field)
        if total_val is not None:
            try:
                total_val = float(total_val)
                diff = round(total_val - charge_sum, 2)
                context['_diff'] = diff
                if abs(diff) >= 0.02:
                    flags.append(f'DIFF: charge_sum != {total_field} (diff={diff})')
                    context['_valid'] = False
                else:
                    context['_valid'] = True
            except (ValueError, TypeError):
                context['_valid'] = None
                context['_diff'] = None
        else:
            context['_valid'] = None
            context['_diff'] = None

    if not charges:
        flags.append('NO_CHARGES')

    return context.get('_valid', None), flags


def process_invoice(ocr_text, pattern):
    """Full pipeline: extract → transform → validate. Returns result dict."""
    context = extract(ocr_text, pattern)
    context = transform(context, pattern)

    # Run the charge processing pipeline if defined
    charge_pipeline = pattern.get('charge_pipeline')
    if charge_pipeline:
        context = _run_charge_pipeline(context, pattern, charge_pipeline)

    # Normalize charge codes and set per-charge flags
    _normalize_charge_codes(context.get('_charges', []))

    valid, flags = validate(context, pattern)

    return {
        'context': context,
        'valid': valid,
        'flags': flags,
        'pattern': pattern.get('format_label', 'unknown'),
    }


def _run_charge_pipeline(context, pattern, pipeline_config):
    """Process charge lines through the charge extraction pipeline.

    Supports two modes:
    1. Flat mode (Robinson): body → lines → service_line context → charge lines
    2. Block mode (Cockey's): body → site blocks → line join → charge lines

    Config in pattern['charge_pipeline']:
      - source_field: where the body text is
      - block_split: optional regex to split body into blocks (site/location)
      - line_join_config: optional line joining config for continuation lines
      - service_line: optional regex for service/equipment context headers
      - skip_patterns: list of regexes for lines to skip
      - special_lines: list of {pattern, fields} for non-standard charge lines
      - charge_detect: how to identify charge lines
      - charge_extract: how to parse charge fields
      - context_fields: fields inherited from service line to charges
      - per_charge_transforms: ordered list of transform rule keys
      - post_processing: ordered list of transform rule keys for all charges
      - desc_extract: how to extract description (mode: after_date, before_amounts, before_wo)
    """
    transform_rules = pattern.get('transform_rules', {})
    charge_detect = pipeline_config.get('charge_detect', {})
    charge_extract = pipeline_config.get('charge_extract', {})
    per_charge_transforms = pipeline_config.get('per_charge_transforms', [])
    skip_compiled = [re.compile(p, re.I) for p in pipeline_config.get('skip_patterns', [])]
    special_lines = pipeline_config.get('special_lines', [])
    special_compiled = [(re.compile(s['pattern'], re.I), s) for s in special_lines]

    # Amount pattern
    amt_combined = charge_extract.get('amount_pattern', r'\(\$?([\d,]+\.\d{2})\)|\$?(-?[\d,]+\.\d{2})')
    date_pattern = charge_detect.get('date_pattern')
    date_re_compiled = re.compile(date_pattern) if date_pattern else None

    # Determine blocks to iterate
    block_split = pipeline_config.get('block_split')
    if block_split:
        blocks = _split_into_blocks(context, pipeline_config)
        if not blocks and block_split.get('fallback_flat', False):
            # No blocks found — fall back to flat mode with full body
            body = context.get(pipeline_config['source_field'], '')
            if not body:
                context['_charges'] = []
                return context
            for strip_cfg in pipeline_config.get('body_strip', []):
                flags = _compile_flags(strip_cfg.get('flags', []))
                body = re.sub(strip_cfg['pattern'], strip_cfg.get('replacement', ''), body, flags=flags)
            blocks = [{'_block_text': body}]
    else:
        # Single block mode (flat)
        body = context.get(pipeline_config['source_field'], '')
        if not body:
            context['_charges'] = []
            return context
        # Pre-process body
        for strip_cfg in pipeline_config.get('body_strip', []):
            flags = _compile_flags(strip_cfg.get('flags', []))
            body = re.sub(strip_cfg['pattern'], strip_cfg.get('replacement', ''), body, flags=flags)
        blocks = [{'_block_text': body}]

    all_charges = []
    svc_re = pipeline_config.get('service_line')

    for block in blocks:
        block_text = block.get('_block_text', '')
        block_fields = {k: v for k, v in block.items() if not k.startswith('_')}

        # Pre-strip body within block
        for strip_cfg in pipeline_config.get('body_strip', []):
            flags = _compile_flags(strip_cfg.get('flags', []))
            block_text = re.sub(strip_cfg['pattern'], strip_cfg.get('replacement', ''), block_text, flags=flags)

        # Line splitting
        chunk_mode = pipeline_config.get('chunk_mode')
        join_cfg = pipeline_config.get('line_join_config')
        if chunk_mode == 'date_split_raw' and date_re_compiled:
            # Split raw block text at each date position, flatten to single lines
            date_positions = list(date_re_compiled.finditer(block_text))
            lines = []
            for i, dm in enumerate(date_positions):
                end = date_positions[i + 1].start() if i + 1 < len(date_positions) else len(block_text)
                chunk_text = block_text[dm.start():end].strip()
                chunk_text = re.sub(r'\s*\n\s*', ' ', chunk_text)
                lines.append(chunk_text)
        elif join_cfg:
            lines = _join_lines(block_text, join_cfg)
        else:
            lines = [l.strip() for l in block_text.split('\n') if l.strip()]

        # Service line state
        svc_ctx = {}
        for f in pipeline_config.get('context_fields', []):
            svc_ctx[f] = None

        for line in lines:
            stripped = line.strip() if isinstance(line, str) else line
            if not stripped:
                continue

            # Check service line (Robinson-style context headers)
            if svc_re:
                svc_flags = _compile_flags(svc_re.get('flags', []))
                svc_m = re.search(svc_re['pattern'], stripped, svc_flags)
                if svc_m:
                    for f in pipeline_config.get('context_fields', []):
                        svc_ctx[f] = None
                    for group_name, out_field in svc_re.get('field_map', {}).items():
                        try:
                            val = svc_m.group(group_name)
                            if val is not None:
                                svc_ctx[out_field] = val.strip()
                        except (IndexError, re.error):
                            pass
                    for t_key in svc_re.get('transforms', []):
                        rule = transform_rules.get(t_key)
                        if rule:
                            handler_fn = HANDLER_REGISTRY.get(rule['type'])
                            if handler_fn:
                                handler_fn(svc_ctx, rule)
                    continue

            # Check skip patterns
            if any(sp.search(stripped) for sp in skip_compiled):
                continue

            # Check special lines (Tax, Fuel Surcharge, etc.)
            special_match = None
            for sp_re, sp_cfg in special_compiled:
                if sp_re.match(stripped):
                    special_match = sp_cfg
                    break
            if special_match:
                amts = [float(a.replace(',', '')) for a in re.findall(r'-?[\d,]+\.\d{2}', stripped)]
                if amts and amts[-1] != 0:
                    charge = dict(block_fields)
                    charge['charge_total'] = amts[-1]
                    for k, v in special_match.get('fields', {}).items():
                        charge[k] = v
                    all_charges.append(charge)
                continue

            # Must have an amount
            if not re.search(r'[\d,]+\.\d{2}', stripped):
                continue

            # Must have text content
            text_only = re.sub(r'\s*\(?\$?-?[\d,]+\.\d{2}\)?\s*', '', stripped).strip()
            if not re.search(r'[A-Za-z]', text_only):
                continue

            # Build charge dict
            charge = dict(block_fields)
            for f in pipeline_config.get('context_fields', []):
                if svc_ctx.get(f) is not None:
                    charge[f] = svc_ctx[f]

            # Extract date
            if date_re_compiled:
                dm = date_re_compiled.search(stripped) if chunk_mode == 'date_split_raw' else date_re_compiled.match(stripped)
                if dm:
                    date_fmt = charge_detect.get('date_format', '{0}-{1}')
                    charge['service_date'] = date_fmt.format(*dm.groups())
                elif charge_detect.get('require_date', False):
                    continue  # Skip lines without date if required

            # Extract amounts — pre-clean OCR garble
            amt_text = re.sub(r'(\d) +\.(\d)', r'\1.\2', stripped)  # space-in-amount: "478 .32" → "478.32"
            amt_text = re.sub(r'(\d)\. +(\d)', r'\1.\2', amt_text)  # space-after-dot: "478. 32" → "478.32"
            amt_text = re.sub(r'(\d),(\d{2})(?!\d)', r'\1.\2', amt_text)  # comma-as-decimal: "-4,98" → "-4.98"
            amt_text = re.sub(r'-\$', '$-', amt_text)  # normalize "-$177.00" → "$-177.00" so capture group sees minus
            amts = []
            for m in re.finditer(amt_combined, amt_text):
                if m.group(1):  # parenthesized negative: (amount)
                    amts.append(-float(m.group(1).replace(',', '')))
                elif m.group(2):  # plain positive: amount
                    amts.append(float(m.group(2).replace(',', '')))
                elif m.lastindex and m.lastindex >= 3 and m.group(3):  # dash negative: -amount
                    amts.append(-float(m.group(3).replace(',', '')))
            if not amts:
                continue
            min_amts = charge_extract.get('min_amounts', 1)
            if len(amts) < min_amts:
                continue

            # Filter out weight/tonnage values from amounts before selection
            wt_pattern = charge_extract.get('weight_pattern')
            if wt_pattern and len(amts) > 1:
                wt_m = re.search(wt_pattern, stripped, re.I)
                if wt_m:
                    try:
                        wt_val = float(wt_m.group(1))
                        # Remove tonnage from end of amounts list only
                        if amts and abs(amts[-1] - wt_val) < 0.01:
                            amts = amts[:-1]
                    except (ValueError, IndexError):
                        pass
                if not amts:
                    continue

            # Amount assignment (configurable)
            amt_mode = charge_extract.get('amount_mode', 'last_is_total')
            if amt_mode == 'last_is_total':
                charge['charge_total'] = amts[-1]
                if len(amts) >= 3:
                    charge['qty'] = amts[-3]
                    charge['unit_rate'] = amts[-2]
                elif len(amts) == 2 and amts[0] != amts[-1]:
                    charge['qty'] = amts[0]
                    charge['unit_rate'] = amts[0]
            elif amt_mode == 'last3_qru':
                # Cockey's: last=TOTAL, second-to-last=RATE, third-to-last=QTY
                charge['charge_total'] = amts[-1]
                if len(amts) >= 2:
                    charge['unit_rate'] = amts[-2]
                if len(amts) >= 3:
                    charge['qty'] = amts[-3]

            # Extract description
            desc_mode = charge_extract.get('desc_extract_mode', 'after_date')
            desc = stripped
            if desc_mode == 'after_date' and date_re_compiled:
                dm = date_re_compiled.search(stripped) if chunk_mode == 'date_split_raw' else date_re_compiled.match(stripped)
                if dm:
                    desc = stripped[dm.end():].strip()
            elif desc_mode == 'before_wo':
                # Cockey's: desc is between date and first WO#/amount cluster
                dm = date_re_compiled.match(stripped) if date_re_compiled else None
                if dm:
                    remainder = stripped[dm.end():].strip()
                else:
                    remainder = stripped
                # Find where description ends (before WO# or amount cluster)
                wo_or_amt = re.search(r'\s+\d{7}\b|\s+(?:-?\d[\d,]*\.\d{2}\s)', remainder)
                if wo_or_amt:
                    desc = remainder[:wo_or_amt.start()].strip()
                else:
                    desc = remainder.strip()

            # Clean description
            desc_clean = re.sub(r'\s*\(?\$?-?[\d,]+\.\d{2}\)?', '', desc).strip()
            desc_clean = re.sub(r'^[|_\s]+', '', desc_clean).strip()
            charge['description'] = desc_clean

            # Extract work order
            wo_pattern = charge_extract.get('wo_pattern')
            if wo_pattern:
                # Search in remainder (not just desc) to find WO after description
                search_text = stripped
                if date_re_compiled:
                    dm = date_re_compiled.match(stripped)
                    if dm:
                        search_text = stripped[dm.end():]
                wo_m = re.search(wo_pattern, search_text, re.I)
                if wo_m:
                    charge['wo_number'] = wo_m.group(1)

            # Extract reference
            ref_pattern = charge_extract.get('ref_pattern')
            if ref_pattern:
                ref_m = re.search(ref_pattern, desc)
                if ref_m:
                    charge['reference'] = ref_m.group(1)

            # Extract weight (from charge_extract config)
            wt_pattern = charge_extract.get('weight_pattern')
            if wt_pattern:
                wt_m = re.search(wt_pattern, desc, re.I)
                if wt_m:
                    charge['weight'] = float(wt_m.group(1))
                    charge['weight_unit'] = 'TONS'

            # Run per-charge transforms
            for t_key in per_charge_transforms:
                rule = transform_rules.get(t_key)
                if rule:
                    handler_fn = HANDLER_REGISTRY.get(rule['type'])
                    if handler_fn:
                        handler_fn(charge, rule)

            all_charges.append(charge)

    # Post-processing (runs on all charges)
    for t_key in pipeline_config.get('post_processing', []):
        rule = transform_rules.get(t_key)
        if rule:
            handler_fn = HANDLER_REGISTRY.get(rule['type'])
            if handler_fn:
                post_ctx = {'_charges': all_charges}
                post_ctx.update(context)
                handler_fn(post_ctx, rule)
                all_charges = post_ctx.get('_charges', all_charges)

    context['_charges'] = all_charges
    return context


def _split_into_blocks(context, pipeline_config):
    """Split body text into blocks using regex."""
    block_cfg = pipeline_config['block_split']
    body = context.get(pipeline_config['source_field'], '')
    if not body:
        return []

    # Pre-clean OCR garble for block_split matching
    body = re.sub(r'(\d) +\.(\d)', r'\1.\2', body)
    body = re.sub(r'(\d)\. +(\d)', r'\1.\2', body)
    body = re.sub(r'(\d),(\d{2})(?!\d)', r'\1.\2', body)

    flags = _compile_flags(block_cfg.get('flags', []))
    field_map = block_cfg.get('field_map', {})
    text_field = block_cfg.get('text_group', 'lines')

    blocks = []
    for m in re.finditer(block_cfg['pattern'], body, flags):
        block = {}
        for group_name, out_field in field_map.items():
            try:
                val = m.group(group_name)
                if val is not None:
                    block[out_field] = val.strip()
            except (IndexError, re.error):
                pass
        # Get the text content for this block
        try:
            block['_block_text'] = m.group(text_field)
        except (IndexError, re.error):
            block['_block_text'] = ''

        # Extract block-level context fields (e.g., service_address per location block)
        block_context_cfg = pipeline_config.get('block_context')
        if block_context_cfg and block.get('_block_text'):
            bc_flags = _compile_flags(block_context_cfg.get('flags', []))
            bc_m = re.search(block_context_cfg['pattern'], block['_block_text'], bc_flags)
            if bc_m:
                for group_name, out_field in block_context_cfg.get('field_map', {}).items():
                    try:
                        val = bc_m.group(group_name)
                        if val is not None:
                            block[out_field] = re.sub(r'\s+', ' ', val).strip()
                    except (IndexError, re.error):
                        pass

        blocks.append(block)

    return blocks


def _join_lines(text, join_cfg):
    """Join continuation lines to previous line."""
    new_line_pat = re.compile(join_cfg['new_line_pattern'], re.I)
    skip_join = [re.compile(p, re.I) for p in join_cfg.get('skip_join_patterns', [])]

    lines = text.split('\n') if isinstance(text, str) else text
    joined = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Check if this starts a new line
        if new_line_pat.match(stripped) or not joined:
            joined.append(stripped)
        elif any(sp.match(stripped) for sp in skip_join):
            # Skip these lines entirely (don't join them)
            continue
        else:
            joined[-1] = joined[-1] + ' ' + stripped
    return joined


def process_batch(ocr_df, patterns, output_dir=None, tracker_path=None):
    """Process a batch of invoices from OCR results DataFrame.
    Writes vendor extract CSVs and updates tracker.

    Args:
        ocr_df: list of dicts with at least pdf_filename, raw_ocr_text
        patterns: list of pattern dicts
        output_dir: directory for output CSVs (default: Invoices/output/vendor_extracts/)
        tracker_path: path to invoice_tracker.csv (default: Invoices/output/invoice_tracker.csv)
    """
    if output_dir is None:
        output_dir = Path(__file__).parent / 'output' / 'vendor_extracts'
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Group results by pattern
    results_by_pattern = {}
    tracker_rows = []

    for row in ocr_df:
        ocr_text = row.get('raw_ocr_text', '')
        pdf_filename = row.get('pdf_filename', '')
        pdf_link = row.get('pdf_path', row.get('pdf_link', ''))
        site_code = row.get('site_code', '')
        month_folder = row.get('month_folder', '')

        # Route
        matched = route(ocr_text, patterns)
        if not matched:
            tracker_rows.append({
                'pdf_filename': pdf_filename,
                'pdf_link': pdf_link,
                'site_code': site_code,
                'month_folder': month_folder,
                'vendor_file': row.get('vendor_name', ''),
                'pattern': '',
                'account_number': '',
                'invoice_number': '',
                'invoice_date': '',
                'bill_total': '',
                'charge_sum': '',
                'diff': '',
                'charge_count': 0,
                'status': 'NO_PATTERN',
                'reason': 'no routing regex matched',
            })
            continue

        # Process
        result = process_invoice(ocr_text, matched)
        ctx = result['context']
        charges = ctx.get('_charges', [])
        format_label = matched.get('format_label', 'unknown')

        # Build output rows according to pattern's output_spec
        output_spec = matched.get('output_spec', {})
        header_fields = output_spec.get('header_fields', [])
        charge_fields = output_spec.get('charge_fields', [])

        # Compute charge_sum
        charge_sum = round(sum(c.get('charge_total', 0) or 0 for c in charges), 2)

        if format_label not in results_by_pattern:
            results_by_pattern[format_label] = {
                'columns': output_spec.get('csv_columns', []),
                'rows': [],
            }

        for charge in charges:
            out_row = {}
            # Add metadata
            out_row['pdf_filename'] = pdf_filename
            out_row['pdf_link'] = _build_pdf_link(pdf_link)
            # Add header fields
            for f in header_fields:
                out_row[f] = ctx.get(f, '')
            # Add computed fields
            out_row['charge_sum'] = charge_sum
            out_row['num_charges'] = len(charges)
            out_row['valid'] = result['valid']
            out_row['diff'] = ctx.get('_diff', '')
            # Add charge fields
            for f in charge_fields:
                out_row[f] = charge.get(f, '')
            # Add flag — merge invoice-level flags with per-charge flags
            all_flags = list(result['flags'])
            all_flags.extend(charge.get('_charge_flags', []))
            out_row['flag'] = '; '.join(all_flags) if all_flags else ''

            results_by_pattern[format_label]['rows'].append(out_row)

        # Tracker entry
        valid = result['valid']
        diff = ctx.get('_diff')
        charge_count = len(charges)

        if valid is True:
            status = 'VALID'
            reason = ''
        elif valid is False:
            if diff and diff > 0:
                status = 'UNDER_CAPTURE'
                reason = f'diff=${diff} — charges missing'
            else:
                status = 'DIFF'
                reason = f'diff=${diff}'
        else:
            status = 'UNVALIDATED'
            reason = 'invoice_total garbled or missing'

        tracker_rows.append({
            'pdf_filename': pdf_filename,
            'pdf_link': pdf_link,
            'site_code': site_code,
            'month_folder': month_folder,
            'vendor_file': row.get('vendor_name', ''),
            'pattern': format_label,
            'account_number': ctx.get('account_number', ''),
            'invoice_number': ctx.get('invoice_number', ''),
            'invoice_date': ctx.get('invoice_date', ''),
            'bill_total': ctx.get('bill_total', ''),
            'charge_sum': charge_sum,
            'diff': diff if diff is not None else '',
            'charge_count': charge_count,
            'status': status,
            'reason': reason,
        })

    # Write vendor extract CSVs
    for format_label, data in results_by_pattern.items():
        out_path = output_dir / f'{format_label}.csv'
        rows = data['rows']
        if not rows:
            continue
        columns = data['columns'] if data['columns'] else list(rows[0].keys())
        with open(out_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
        print(f"  Wrote {len(rows)} rows → {out_path}")

    # Write/update tracker
    if tracker_path and tracker_rows:
        tracker_path = Path(tracker_path)
        tracker_cols = [
            'pdf_filename', 'pdf_link', 'site_code', 'month_folder', 'vendor_file',
            'pattern', 'account_number', 'invoice_number', 'invoice_date', 'bill_total',
            'charge_sum', 'diff', 'charge_count', 'status', 'reason',
        ]
        with open(tracker_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=tracker_cols, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(tracker_rows)
        print(f"  Tracker: {len(tracker_rows)} rows → {tracker_path}")

    return results_by_pattern, tracker_rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Invoice pattern executor')
    parser.add_argument('--ocr', required=True, help='Path to ocr_results.csv')
    parser.add_argument('--patterns', default=None, help='Pattern JSON directory')
    parser.add_argument('--output', default=None, help='Output directory')
    parser.add_argument('--tracker', default=None, help='Tracker CSV path')
    parser.add_argument('--filter-pattern', default=None, help='Only process this format_label')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of invoices')
    args = parser.parse_args()

    # Load OCR data
    with open(args.ocr, 'r') as f:
        reader = csv.DictReader(f)
        ocr_data = list(reader)
    print(f"Loaded {len(ocr_data)} OCR records")

    # Load patterns
    patterns = load_patterns(pattern_dir=args.patterns)
    print(f"Loaded {len(patterns)} active patterns")

    if args.filter_pattern:
        patterns = [p for p in patterns if p['format_label'] == args.filter_pattern]
        print(f"Filtered to pattern: {args.filter_pattern}")

    if args.limit:
        ocr_data = ocr_data[:args.limit]
        print(f"Limited to {args.limit} invoices")

    # Process
    results, tracker = process_batch(ocr_data, patterns, args.output, args.tracker)
    print(f"\nDone. {len(tracker)} invoices processed.")


if __name__ == '__main__':
    main()
