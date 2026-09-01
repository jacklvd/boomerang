"""AUTHORED, NOT DERIVED: the allowlists that sanction a disagreement.

Every table here records a place where the plan document and the task corpus
are permitted to differ, together with the reason and the two values being
reconciled. They are asserted by SET EQUALITY, not used as skip-lists: an
undeclared divergence fails, a declared entry whose values have moved fails,
and a declared entry whose divergence has gone away fails as stale. Adding an
entry is therefore a deliberate, reviewable act, and no entry can quietly
outlive the thing it was written about.
"""

from __future__ import annotations

from config import NUM_PATTERN, RATIO_PATTERN
from models import (
    Claim,
    ConflictSerialisation,
    DeclaredDivergence,
    DeclaredTitleDivergence,
    Restatement,
    UnreviewableConflict,
)

# The only sanctioned way for a requirement to have no covering task: any other
# uncovered id fails `split-plan.py --verify` and renders as a loud cell.
DECLARED_GAPS = {
    "FR-3.6.2": "**— (deliberate gap)**",
    "FR-3.6.3": "**— (deliberate gap, out of PoC scope)**",
}

# Plan Summary rows whose hand-written track count the corpus deliberately does
# not match. Both counts are recorded so a move in either one reopens the case.
DECLARED_TRACK_COUNT_DIVERGENCES = {
    "1": DeclaredDivergence(2, 4, "stale authored undercount: 866d9a5 added Tracks C and D to Batch 1 without updating the summary"),
    "4": DeclaredDivergence(6, 5, "lane count A, B, C, C', D, E -- C' is the D19 storage-barrel fan-out inside Track C, not a sixth `###` heading"),
    "deployment": DeclaredDivergence(1, 0, "the deployment tasks carry track_heading: null by design; they render as `### Task I.x` headings, which are not tracks"),
}

# The only `->` edges in the MAKESPAN TABLE permitted to be something other than
# a prerequisite edge. Each names a set that conflicts pairwise (asserted, not
# assumed) and that the authored row therefore runs one after another.
DECLARED_CONFLICT_SERIALISATIONS = {
    "3": ConflictSerialisation(
        frozenset({"3.1", "3.2", "3.3", "3.4"}),
        "all four write `app/models/__init__.py`; the conflict is an undirected "
        "mutex, so the run order is an authored scheduling choice, not an edge",
    ),
}

# The same idea for the BATCH EXECUTION OVERVIEW, kept as a separate table: the
# one above is keyed by batch and reported stale when no makespan row uses it,
# so the overview's extra lanes cannot be folded into it without breaking that.
DECLARED_OVERVIEW_SERIALISATIONS = {
    "3 / Track A": ConflictSerialisation(
        frozenset({"3.1", "3.2", "3.3", "3.4"}),
        "all four re-export through `app/models/__init__.py`; only 3.1 -> 3.2 and "
        "3.4 -> 3.5 are prerequisite edges, so the lane's middle is an authored "
        "run order (the same one the makespan table's Batch 3 row picks)",
    ),
    "3 / Track J": ConflictSerialisation(
        frozenset({"3.15", "3.16"}),
        "both export from `src/validation/index.ts`; 3.16 does not require 3.15, "
        "so the lane orders a mutex",
    ),
    "4 / Track B": ConflictSerialisation(
        frozenset({"4.3", "4.4", "4.5"}),
        "all three write `app/carriers/usps/__init__.py`; 4.4 -> 4.5 is not a "
        "prerequisite edge (4.5 requires 3.5 and 3.4), so the lane orders a mutex",
    ),
}

# Batch titles the overview states differently from their own `##` heading.
# Titles are compared with parentheticals dropped and case folded away, so what
# is declared here is a real wording difference, recorded with BOTH strings.
DECLARED_OVERVIEW_TITLE_DIVERGENCES = {
    "6": DeclaredTitleDivergence(
        "Batch 6: Routes and app; driver core",
        "Batch 6: Routes and Application; Driver Core",
        "the fenced block abbreviates 'Application' to 'app' to hold the column "
        "width the ASCII lanes are aligned on; both name the same batch",
    ),
}

# Every place OUTSIDE `## Critical Path` where authored prose restates a derived
# quantity. A site is located by a line-leading literal -- a bold field label or
# lead-in, which is document structure -- and the region searched is the whole
# paragraph, so ordinary copy-editing does not break the build. Within it each
# claim is read by the shortest phrase that says WHICH number is meant; if that
# phrasing is rewritten away the claim is reported NOT FOUND, never skipped.
DECLARED_RESTATEMENTS = {
    "header / total tasks": Restatement(
        anchor="**Total Tasks:**",
        claims=(
            Claim(rf"\*\*Total Tasks:\*\*\s+~?({NUM_PATTERN})\b", "tasks"),
        ),
        reason="the headline count a reader meets before anything else",
    ),
    "header / makespan": Restatement(
        anchor="**Makespan under the batch barrier:**",
        claims=(
            Claim(rf"~?({NUM_PATTERN})\s+slots\b", "makespan"),
            Claim(rf"~?({NUM_PATTERN})-task\b", "floor"),
        ),
        reason="the header's summary of the Critical Path section, four hundred "
               "lines before the section itself",
    ),
    "speedup / ceiling": Restatement(
        anchor="**Theoretical speedup, honestly stated.**",
        claims=(
            Claim(rf"\b({NUM_PATTERN})\b[^*]{{0,30}}?\bdependency\s+floor\b", "tasks"),
            Claim(rf"~?({NUM_PATTERN})-task\s+dependency\s+floor\b", "floor"),
            Claim(rf"\bdependency\s+floor\b[^*]{{0,60}}?\*\*~?{RATIO_PATTERN}x\*\*",
                  "tasks per floor task"),
        ),
        reason="the unreachable upper bound the paragraph argues against",
    ),
    "speedup / makespan": Restatement(
        anchor="**Theoretical speedup, honestly stated.**",
        claims=(
            Claim(rf"\b({NUM_PATTERN})\b[^*]{{0,20}}?~?[0-9]+-slot\b", "tasks"),
            Claim(rf"~?({NUM_PATTERN})-slot\s+makespan\b", "makespan"),
            Claim(rf"-slot\s+makespan\b[^*]{{0,60}}?\*\*~?{RATIO_PATTERN}x\*\*",
                  "tasks per slot"),
        ),
        reason="the speedup the paragraph says actually matters",
    ),
    "speedup / non-agent tasks": Restatement(
        anchor="**Theoretical speedup, honestly stated.**",
        claims=(
            Claim(rf"\bof\s+the\s+~?({NUM_PATTERN})\s+tasks\b", "tasks"),
        ),
        reason="the two tasks that are not agent work, stated as a fraction of "
               "the corpus",
    ),
}

# Mutexes nobody could name a shared file for. Each is a real gap, written down
# instead of papered over, and each fails as stale once its annotation gains a
# path -- the allowlist is not a graveyard.
DECLARED_UNREVIEWABLE_CONFLICTS: dict[str, UnreviewableConflict] = {}
