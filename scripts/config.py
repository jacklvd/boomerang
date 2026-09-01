"""Paths, tokens and patterns shared by the plan scripts.

Imported by ``plan_lib``, ``split-plan.py`` and ``build-plan-index.py`` so the
splitter, the renderer and the verifier read the document with one set of
definitions and cannot disagree about what a task, a track or a batch is.

Definition order matters: several patterns are built from ``TASK_ID_RE`` and
from ``NUM_PATTERN``, so keep the sections in the order they appear here.
"""

from __future__ import annotations

import re
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = REPO_ROOT / "plan" / "boomerang-plan.md"
TASKS_DIR = REPO_ROOT / "plan" / "tasks"
REQUIREMENTS_DOC = REPO_ROOT / "design" / "boomerang-requirements.md"
BASELINE_REF = "cf7e210"

# --------------------------------------------------------------------------
# Document tokens
# --------------------------------------------------------------------------
# These three are PARSER tokens, not just render tokens: the values below are
# matched against the literal characters in plan/boomerang-plan.md, so changing
# a value (to "->", say) stops the checks finding the chains they assert.

ARROW = "\u2192"     # RIGHTWARDS ARROW, the chain separator in the plan
PARALLEL = "\u2225"  # PARALLEL TO, the "runs alongside" marker in the plan

# Sentinel that sorts after every assigned track letter (U+FFFF is a permanent
# non-character, so no real letter can collide with it). Written as an escape:
# as a literal it is invisible in an editor and in a diff.
SORT_LAST = "\uffff"

SERVER_SCOPE = "server"

CRITICAL_PATH_HEADING = "## Critical Path"
FLOOR_HEADING = "### The dependency floor"
MAKESPAN_HEADING = "### The makespan the barrier actually buys"
THREE_THINGS_HEADING = "### Three things about the shape of this chain"
OVERVIEW_HEADING = "## Batch Execution Overview"
PROGRESS_PREFIX = "**Progress:**"

# --------------------------------------------------------------------------
# Structural constants
# --------------------------------------------------------------------------

# The eight bold metadata fields every task carries, in document order.
METADATA_FIELDS = [
    "Prerequisites",
    "Conflicts with",
    "Parallel with",
    "Package",
    "Objective",
    "Instructions",
    "Verification",
    "Requirements covered",
]

# Tasks the plan's traceability prose classifies as integration tests / CI
# assertions rather than implementation work. Not derivable from a task body;
# decides only WHICH COLUMN a task lands in, never whether it appears at all.
INTEGRATION_TASK_IDS = {
    "7.2", "7.3", "7.4", "7.5", "7.6",
    "9.2", "9.3", "9.4", "9.5", "9.6", "9.7",
    "10.1", "10.3",
    "I.2",
}

# Human gates, not automated evidence: deliberately absent from traceability.
GATE_TASK_IDS = {"8.6"}

# --------------------------------------------------------------------------
# Patterns
# --------------------------------------------------------------------------

# Requirement ids are declared by their own heading in the requirements doc.
REQ_HEADING_RE = re.compile(r"^#{2,4} ((?:FR|NFR)-[0-9.]+[a-z]?)\b")

HEADING_RE = re.compile(r"^(#{1,6}) (.*)$")
TASK_HEADING_RE = re.compile(r"^#{3,4} Task ([0-9]+\.[0-9]+[a-z]?|I\.[0-9]+): (.*)$")
TRACK_HEADING_RE = re.compile(r"^### (?:Track ([A-Z]): )?(.*?)(?: \[([a-z]+)\])?$")
BATCH_HEADING_RE = re.compile(r"^## Batch ([0-9]+)(?::.*)?$")

# Applied to a `###` heading's text AFTER the "### ". A heading that is not a
# lettered track (a checkpoint, a gate, a `Task I.x`) yields no match, which is
# what keeps the renderer and the verifier agreeing on what a track is.
TRACK_LETTER_RE = re.compile(r"^Track ([A-Z]): ")

TASK_ID_RE = r"(?:I\.[0-9]+|[0-9]+\.[0-9]+[a-z]?)"
REQ_RE = re.compile(r"^(?:FR-[0-9]+\.[0-9]+\.[0-9]+[a-z]?|NFR-[0-9]+\.[0-9]+)$")
SECTION_RE = re.compile(r"^§[0-9]+\.[0-9]+$")
PAREN_RE = re.compile(r"\([^()]*\)")
# Comma-separated list item: an optional "Task"/"Tasks" prefix then an id or an
# id range ("6.1-6.3", en dash or hyphen).
LIST_ITEM_RE = re.compile(
    rf"^(?:Tasks?\s+)?({TASK_ID_RE})(?:\s*[–—-]\s*({TASK_ID_RE}))?$"
)
BARE_ID_RE = re.compile(rf"^{TASK_ID_RE}$")

FLOOR_LENGTH_RE = re.compile(r"^\*\*Critical path length:\*\* ([0-9]+) tasks\.$")
# "So the barrier costs roughly **15 slots** -- 35 against a floor of 20."
CONCLUSION_RE = re.compile(
    r"roughly \*\*([0-9]+) slots\*\*\s*[—-]+\s*([0-9]+) against a floor of ([0-9]+)"
)

# --------------------------------------------------------------------------
# Prose numbers
# --------------------------------------------------------------------------
# Two checks have to read a spelled-out count -- the server-chain sentence
# ("twelve tasks") and the restatement check ("Ninety-one tasks"). One table,
# built structurally, so the two cannot drift apart.

_UNITS = ("zero one two three four five six seven eight nine ten eleven twelve "
          "thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()


def english_number(n: int) -> str:
    """``91 -> "ninety-one"``. Defined for 0-99, the only range prose needs."""
    if n < 20:
        return _UNITS[n]
    tens, unit = divmod(n, 10)
    return _TENS[tens - 2] + (f"-{_UNITS[unit]}" if unit else "")


NUMBER_WORDS = {english_number(n): n for n in range(100)}


def parse_count(token: str) -> int | None:
    """``"91"`` / ``"Ninety-one"`` / ``"twelve"`` -> an int; anything else None."""
    t = token.strip().lower()
    return int(t) if t.isdigit() else NUMBER_WORDS.get(t)


# Regex fragments for a stated number and a stated ratio. Longest-first so the
# alternation cannot match "seventy" inside "seventy-three".
NUM_PATTERN = "(?:[0-9]+|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + ")"
RATIO_PATTERN = r"([0-9]+(?:\.[0-9]+)?)"
