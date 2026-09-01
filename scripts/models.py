"""The types the plan scripts pass around, and how a task names its file.

Pure data: no parsing, no I/O, no checks. ``plan_lib`` builds these and the
checks return them, so the splitter, the renderer and the verifier all describe
a task, a chain and a declared divergence in the same words.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from typing import NamedTuple

from config import GATE_TASK_IDS, INTEGRATION_TASK_IDS


# --------------------------------------------------------------------------
# Task file naming
# --------------------------------------------------------------------------

def slugify(title: str, limit: int = 50) -> str:
    """Lowercase, strip backticks/punctuation, hyphenate, truncate on a word."""
    text = title.replace("`", "")
    # Fold accents; map the typographic dashes/section sign to separators.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if "-" in cut:
        cut = cut[: cut.rfind("-")]
    return cut.strip("-")


def pad_id(task_id: str) -> str:
    """``4.6`` -> ``4.06`` so files sort lexically. ``I.1`` is left alone."""
    if task_id.startswith("I."):
        return task_id
    major, minor = task_id.split(".", 1)
    suffix = ""
    m = re.match(r"^([0-9]+)([a-z]?)$", minor)
    if m:
        minor, suffix = m.group(1), m.group(2)
    return f"{major}.{int(minor):02d}{suffix}"


# --------------------------------------------------------------------------
# The task
# --------------------------------------------------------------------------

@dataclass
class Task:
    task_id: str
    title: str
    heading_level: int
    batch: str  # "0".."10" or "deployment"
    track_heading: str | None  # verbatim heading text after "### "
    track: str | None  # e.g. "C: Extension storage"
    track_scope: str | None  # "extension" / "server" / "repo" / ...
    track_index: int  # order of first appearance within the batch
    order: int  # global document order
    body: str  # VERBATIM, heading line through the blank line before "---"
    meta_raw: dict[str, str] = field(default_factory=dict)
    prerequisites: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)
    parallel_with: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    requirements_prose_only: bool = False
    unparsed: dict[str, list[str]] = field(default_factory=dict)
    status: str = "not_started"

    @property
    def batch_dir(self) -> str:
        if self.batch == "deployment":
            return "deployment"
        return f"batch-{int(self.batch):02d}"

    @property
    def slug(self) -> str:
        return slugify(self.title)

    @property
    def filename(self) -> str:
        return f"{pad_id(self.task_id)}-{self.slug}.md"

    @property
    def relpath(self) -> str:
        return f"tasks/{self.batch_dir}/{self.filename}"

    @property
    def kind(self) -> str:
        if self.task_id in GATE_TASK_IDS:
            return "gate"
        if self.task_id in INTEGRATION_TASK_IDS:
            return "integration"
        return "implementation"

    @property
    def package_raw(self) -> str:
        return self.meta_raw.get("Package", "").strip()

    @property
    def package(self) -> str:
        """The package path(s) with markdown backticks removed."""
        return self.package_raw.replace("`", "").strip()


# --------------------------------------------------------------------------
# Records the checks build and return
# --------------------------------------------------------------------------

class Chain(NamedTuple):
    """The result of a longest-path query over the prerequisite DAG."""
    length: int          # number of tasks on a maximal chain
    chain: list[str]     # ONE maximal chain, chosen by longest_chain's tie-break
    endpoints: list[str] # every task at which some maximal chain ends
    count: int           # how many DISTINCT maximal chains exist
    depth: dict          # task id -> length of the longest chain ending there


class DeclaredDivergence(NamedTuple):
    """A sanctioned disagreement, with the two numbers it is reconciled against."""
    baseline: int   # the count the baseline's hand-written Plan Summary claims
    corpus: int     # the count the task corpus actually has
    reason: str     # why the two are allowed to differ


class ConflictSerialisation(NamedTuple):
    """A mutually-conflicting set an authored block is allowed to order."""
    ids: frozenset      # the tasks the authored row serialises
    reason: str         # the shared file, and why an order had to be chosen


class DeclaredTitleDivergence(NamedTuple):
    """A batch title the overview states differently from its own ``##`` heading."""
    overview: str   # the line as the overview block carries it
    heading: str    # the ``##`` heading text, without the leading "## "
    reason: str     # why the two are allowed to differ


class UnreviewableConflict(NamedTuple):
    """A conflict annotation knowingly left without a path, and why."""
    raw: str        # the annotation as it stands, verbatim
    reason: str     # why no path could be named
    resolve: str    # what someone would have to establish to fix it


class Claim(NamedTuple):
    """One number inside a site, and the derived quantity it must agree with."""
    pattern: str     # regex over the site's paragraph; group 1 is the stated number
    quantity: str    # a key of derived_quantities()


class Restatement(NamedTuple):
    """An authored sentence that repeats derived numbers, and what it owes them."""
    anchor: str            # a line-leading literal; must start EXACTLY one line
    claims: tuple          # the Claims read out of the paragraph that line sits in
    reason: str            # what the site is for, so a failure says what broke


class DerivedQuantity(NamedTuple):
    """A number the corpus decides, and how it was decided."""
    value: Decimal
    origin: str
    decimals: int   # places to show it to when reporting


class OverviewUnit(NamedTuple):
    """One lane of the block: ``Track X (qualifier): <chain>   [annotation]``.

    ``label``/``letter`` are None for the Deployment track's unlabelled lines,
    whose tasks carry ``track_heading: null``. ``letter`` is None with a label
    for ``Gate (serial): 8.6``, which is a ``###`` heading but not a track.
    """
    batch: str
    label: str | None
    letter: str | None
    qualifier: str | None
    annotation: str | None
    steps: tuple          # tuple of tuples of ids; consecutive steps are `->`
    claims: tuple         # (dependent id, claimed prerequisite id, where it is written)
    lineno: int
    text: str
