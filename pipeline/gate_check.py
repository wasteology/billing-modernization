"""
DB-driven gate enforcement for the invoice processing pipeline.

Each step requires all upstream steps to have zero open review rows
before it can execute. This replaces the CSV-based _check_gate() in processor.py.
"""

from .db_helpers import get_open_review_count


class GateBlockedError(Exception):
    """Raised when a step cannot run because upstream gates are not clear."""

    def __init__(self, step: int, blocking_step: int, open_count: int):
        self.step = step
        self.blocking_step = blocking_step
        self.open_count = open_count
        super().__init__(
            f"Step {step} BLOCKED: step {blocking_step} has {open_count} open review rows"
        )


STEP_NAMES = {
    1: "OCR Validation",
    2: "Vendor Detection",
    3: "Account Number",
    4: "Invoice Number",
    5: "Invoice Date",
    6: "Amount Due",
    7: "Validation",
    8: "Line Item Extraction",
    9: "Catalog Match",
    10: "Charge Validation",
}


def gate_check(step: int) -> None:
    """Verify all upstream steps have 0 open review rows.

    Raises GateBlockedError if any upstream step has unresolved items.
    Step 1 has no prerequisites and always passes.
    """
    for upstream in range(1, step):
        count = get_open_review_count(upstream)
        if count > 0:
            raise GateBlockedError(step, upstream, count)


def gate_status_display() -> str:
    """Return a formatted string showing gate status for all steps."""
    lines = ["\n  Pipeline Gate Status", "  " + "=" * 50]
    for step in range(1, 11):
        open_count = get_open_review_count(step)
        status = "CLEAR" if open_count == 0 else f"BLOCKED ({open_count} open)"
        indicator = "  " if open_count == 0 else "  "
        name = STEP_NAMES.get(step, f"Step {step}")
        lines.append(f"  Step {step:>2}: {name:<22s} {indicator} {status}")
    return "\n".join(lines)
