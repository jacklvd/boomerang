"""The five cross-checks the plan scripts run over the document.

Each answers the same question about a different authored block: does what the
document says still agree with what the task corpus says? None of them rewrites
anything -- they return ``(findings, info)`` so the caller decides whether a
finding is a hard failure (``split-plan.py --verify``) or a report
(``build-plan-index.py``).
"""

from __future__ import annotations

from checks.corpus import (
    check_conflict_annotations,
    classify_track_count_divergences,
    plan_summary_track_counts,
    track_count_divergences,
)
from checks.critical_path import (
    CHAIN_LENGTH_RE,
    CHAIN_TIE_RE,
    check_makespan_table,
    check_server_chain_sentence,
    parse_makespan_cell,
    parse_server_chain_sentence,
    rendered_dependency_floor,
)
from checks.overview import check_batch_overview, parse_overview
from checks.restatements import (
    check_restated_quantities,
    derived_quantities,
    makespan_slot_total,
    parse_stated,
    readable_pattern,
    restatement_tolerance,
)

__all__ = [
    "CHAIN_LENGTH_RE",
    "CHAIN_TIE_RE",
    "check_batch_overview",
    "check_conflict_annotations",
    "check_makespan_table",
    "check_restated_quantities",
    "check_server_chain_sentence",
    "classify_track_count_divergences",
    "derived_quantities",
    "makespan_slot_total",
    "parse_makespan_cell",
    "parse_overview",
    "parse_server_chain_sentence",
    "parse_stated",
    "plan_summary_track_counts",
    "readable_pattern",
    "rendered_dependency_floor",
    "restatement_tolerance",
    "track_count_divergences",
]
