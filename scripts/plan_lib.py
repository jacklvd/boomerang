"""Shared parsing for the Boomerang implementation plan.

Used by ``split-plan.py`` (plan -> per-task files) and ``build-plan-index.py``
(per-task files -> regenerated ``plan/boomerang-plan.md``).

Design notes that matter for correctness:

* A task body is copied VERBATIM into its task file. Nothing is lifted *out* of
  the body -- the YAML frontmatter is purely additive. That makes the round-trip
  diff exact modulo the frontmatter block alone, and it means prose attached to
  a metadata line (``Conflicts with: Task 4.7 (both touch src/storage/index.ts)``)
  can never be lost.
* Frontmatter scalars are emitted via ``json.dumps``. YAML 1.2 is a JSON
  superset, so the output is valid YAML *and* can be read back with
  ``json.loads`` without a YAML dependency.
"""

from __future__ import annotations

import json
import re
import subprocess
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = REPO_ROOT / "plan" / "boomerang-plan.md"
TASKS_DIR = REPO_ROOT / "plan" / "tasks"
REQUIREMENTS_DOC = REPO_ROOT / "design" / "boomerang-requirements.md"
BASELINE_REF = "cf7e210"

# AUTHORED, NOT DERIVED. The requirements the plan declares as deliberate gaps,
# with the annotation the hand-written traceability table carried. This is the
# ONLY sanctioned way for a requirement to have no covering task: the coverage
# check in ``split-plan.py --verify`` fails on any other uncovered id, and
# ``build-plan-index.py`` renders any other uncovered id as a loud cell.
# Adding an entry here is a deliberate, reviewable act.
DECLARED_GAPS = {
    "FR-3.6.2": "**— (deliberate gap)**",
    "FR-3.6.3": "**— (deliberate gap, out of PoC scope)**",
}


class DeclaredDivergence(NamedTuple):
    """A sanctioned disagreement, with the two numbers it is reconciled against."""
    baseline: int   # the count the baseline's hand-written Plan Summary claims
    corpus: int     # the count the task corpus actually has
    reason: str     # why the two are allowed to differ


# AUTHORED, NOT DERIVED. The Plan Summary rows whose hand-written track count
# the corpus deliberately does NOT match. Each has been investigated; none is a
# defect. This is the ONLY sanctioned way for a summary track count to disagree
# with the corpus: ``split-plan.py --verify`` fails on any other divergence,
# and ``build-plan-index.py`` reports every divergence with the reason below.
#
# The entry records BOTH counts, not just the batch, so this stays an assertion
# rather than a skip-list: if either number moves, the reconciliation no longer
# holds and the reason has to be revisited, so verification fails rather than
# swallowing the new number. An entry whose divergence has gone away is stale
# and fails too -- the same set-equality spirit as INTENDED_BODY_CHANGES in
# ``split-plan.py``. Adding an entry here is a deliberate, reviewable act.
DECLARED_TRACK_COUNT_DIVERGENCES = {
    "1": DeclaredDivergence(2, 4, "stale authored undercount: 866d9a5 added Tracks C and D to Batch 1 without updating the summary"),
    "4": DeclaredDivergence(6, 5, "lane count A, B, C, C', D, E -- C' is the D19 storage-barrel fan-out inside Track C, not a sixth `###` heading"),
    "deployment": DeclaredDivergence(1, 0, "the deployment tasks carry track_heading: null by design; they render as `### Task I.x` headings, which are not tracks"),
}

# Requirement ids are declared by their own heading in the requirements doc.
REQ_HEADING_RE = re.compile(r"^#{2,4} ((?:FR|NFR)-[0-9.]+[a-z]?)\b")

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

# Tasks that the plan's own traceability prose classifies as integration tests /
# CI assertions rather than implementation work: "Tasks 7.2-7.6 drive the
# assembled FastAPI app, Tasks 9.2-9.7 drive the assembled extension, and Tasks
# 10.1 and 10.3 are CI assertions about the shipped bundle and the module
# graph", plus I.2 (the live smoke test) which the NFR-6.5/6.6/6.7 rows list in
# the integration column. This is the one classification that is not derivable
# from a task body; it decides only WHICH COLUMN a task lands in, never whether
# it appears at all.
INTEGRATION_TASK_IDS = {
    "7.2", "7.3", "7.4", "7.5", "7.6",
    "9.2", "9.3", "9.4", "9.5", "9.6", "9.7",
    "10.1", "10.3",
    "I.2",
}

# Tasks that are human gates, not automated evidence. The plan states Task 8.6
# is deliberately absent from the traceability table.
GATE_TASK_IDS = {"8.6"}

HEADING_RE = re.compile(r"^(#{1,6}) (.*)$")
TASK_HEADING_RE = re.compile(r"^#{3,4} Task ([0-9]+\.[0-9]+[a-z]?|I\.[0-9]+): (.*)$")
TRACK_HEADING_RE = re.compile(r"^### (?:Track ([A-Z]): )?(.*?)(?: \[([a-z]+)\])?$")
BATCH_HEADING_RE = re.compile(r"^## Batch ([0-9]+)(?::.*)?$")

# ``Track B: USPS access [external]`` -> ``"B"``. Applied to the heading text
# AFTER the ``### ``. A ``###`` heading that is not a lettered track -- ``Batch
# 4 Commit Checkpoint``, ``Gate: Manual acceptance [extension]``, ``Task I.1:
# ...`` -- yields None. Shared so the renderer (which places a synthesized
# track by letter) and ``split-plan.py --verify`` (which asserts the letters
# are gapless) cannot disagree about what counts as a lettered track.
TRACK_LETTER_RE = re.compile(r"^Track ([A-Z]): ")


def track_letter(heading_text: str) -> str | None:
    """The letter of a track heading, given the text after ``### ``."""
    m = TRACK_LETTER_RE.match(heading_text)
    return m.group(1) if m else None

TASK_ID_RE = r"(?:I\.[0-9]+|[0-9]+\.[0-9]+[a-z]?)"
REQ_RE = re.compile(r"^(?:FR-[0-9]+\.[0-9]+\.[0-9]+[a-z]?|NFR-[0-9]+\.[0-9]+)$")
SECTION_RE = re.compile(r"^§[0-9]+\.[0-9]+$")
PAREN_RE = re.compile(r"\([^()]*\)")
# Comma-separated list item: an optional "Task"/"Tasks" prefix then an id or an
# id range ("6.1-6.3", en dash or hyphen).
LIST_ITEM_RE = re.compile(
    rf"^(?:Tasks?\s+)?({TASK_ID_RE})(?:\s*[–—-]\s*({TASK_ID_RE}))?$"
)


def read_source(source: str) -> str:
    """Read the plan from a path or from ``git:<ref>[:<path>]``."""
    if source.startswith("git:"):
        spec = source[4:]
        if ":" not in spec:
            spec = f"{spec}:plan/boomerang-plan.md"
        out = subprocess.run(
            ["git", "show", spec],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout
    return Path(source).read_text()


def requirement_ids_from_doc(path: Path = REQUIREMENTS_DOC) -> set[str]:
    """Every requirement id the requirements document declares as a heading.

    This is the universe the coverage check is taken against: a requirement
    exists because the design document gives it a heading, not because some
    task happened to cite it.
    """
    if not path.exists():
        return set()
    return {
        m.group(1).rstrip(".")
        for line in path.read_text().split("\n")
        if (m := REQ_HEADING_RE.match(line))
    }


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


def _expand(lo: str, hi: str) -> list[str]:
    """Expand ``6.1``-``6.3`` to 6.1, 6.2, 6.3. Refuses cross-major ranges."""
    lo_major, lo_minor = lo.split(".", 1)
    hi_major, hi_minor = hi.split(".", 1)
    if lo_major != hi_major or not lo_minor.isdigit() or not hi_minor.isdigit():
        return [lo, hi]
    return [f"{lo_major}.{n}" for n in range(int(lo_minor), int(hi_minor) + 1)]


def parse_id_list(value: str) -> tuple[list[str], list[str]]:
    """Extract task ids from a dependency line value.

    Returns ``(ids, unparsed_fragments)``. Prose fragments ("all server tasks",
    "All of Batches 7-10") are returned as unparsed rather than mined for
    numbers -- mining them would invent dependencies. Parentheticals are
    dropped before splitting, so "(the barrel was written in 4.6)" cannot leak a
    false id, but the full line is preserved verbatim in the task body and in
    the ``*_raw`` frontmatter key.
    """
    value = value.strip()
    if not value or value in {"None", "—", "-"}:
        return [], []
    # "None -- src/storage/pickups.ts only (...)": no dependencies, prose reason.
    if re.match(r"^None\b", value):
        return [], [value]

    stripped = PAREN_RE.sub(" ", value)
    stripped = stripped.replace("**", "")
    ids: list[str] = []
    unparsed: list[str] = []
    for part in stripped.split(","):
        part = part.strip()
        if not part:
            continue
        m = LIST_ITEM_RE.match(part)
        if not m:
            unparsed.append(part)
            continue
        if m.group(2):
            ids.extend(_expand(m.group(1), m.group(2)))
        else:
            ids.append(m.group(1))
    # De-duplicate, preserving order.
    seen: set[str] = set()
    out = [i for i in ids if not (i in seen or seen.add(i))]
    return out, unparsed


def parse_requirements(value: str) -> tuple[list[str], list[str], bool]:
    """Extract FR/NFR ids and design-section refs from a Requirements line.

    Returns ``(requirements, sections, is_prose_only)``.

    A line that opens with an em dash ("-- (validates the assumptions behind
    FR-3.3.4, ...)") declares that the task covers NO requirement; the ids it
    names are context, not coverage. Mining them would add spike and harness
    tasks to traceability rows they do not provide evidence for.
    """
    value = value.strip()
    if value.startswith("—"):
        return [], [], True
    stripped = PAREN_RE.sub(" ", value).replace("**", "")
    reqs: list[str] = []
    sections: list[str] = []
    for part in stripped.split(","):
        part = part.strip()
        if REQ_RE.match(part):
            reqs.append(part)
        elif SECTION_RE.match(part):
            sections.append(part)
    return reqs, sections, False


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


def parse_plan(text: str) -> list[Task]:
    """Parse every task out of the plan document."""
    lines = text.split("\n")
    heading_idx = [i for i, l in enumerate(lines) if HEADING_RE.match(l)]
    heading_pos = {i: n for n, i in enumerate(heading_idx)}

    tasks: list[Task] = []
    batch: str | None = None
    track_heading: str | None = None
    track: str | None = None
    track_scope: str | None = None
    track_seen: dict[str, list[str]] = {}
    order = 0

    for i in heading_idx:
        line = lines[i]
        bm = BATCH_HEADING_RE.match(line)
        if bm:
            batch = bm.group(1)
            track_heading = track = track_scope = None
            continue
        if line.startswith("## Deployment Track"):
            batch = "deployment"
            track_heading = track = track_scope = None
            continue
        if line.startswith("## "):
            # Any other top-level section ends the batch context.
            batch = None
            track_heading = track = track_scope = None
            continue

        tm = TASK_HEADING_RE.match(line)
        if tm:
            if batch is None:
                raise ValueError(f"task outside any batch: {line!r}")
            n = heading_pos[i]
            end = heading_idx[n + 1] if n + 1 < len(heading_idx) else len(lines)
            # Every task span ends with: <blank>, "---", <blank>.
            if lines[end - 2] != "---" or lines[end - 1] != "":
                raise ValueError(f"unexpected task terminator for {line!r}")
            body_lines = lines[i : end - 2]
            key = batch
            track_seen.setdefault(key, [])
            th = track_heading or "<deployment>"
            if th not in track_seen[key]:
                track_seen[key].append(th)
            tasks.append(
                _build_task(
                    task_id=tm.group(1),
                    title=tm.group(2),
                    heading_level=len(line) - len(line.lstrip("#")),
                    batch=batch,
                    track_heading=track_heading,
                    track=track,
                    track_scope=track_scope,
                    track_index=track_seen[key].index(th),
                    order=order,
                    body_lines=body_lines,
                )
            )
            order += 1
            continue

        if line.startswith("### "):
            track_heading = line[4:]
            m = TRACK_HEADING_RE.match(line)
            letter, name, scope = m.group(1), m.group(2), m.group(3)
            track = f"{letter}: {name}" if letter else name
            track_scope = scope

    return tasks


def _build_task(*, task_id, title, heading_level, batch, track_heading, track,
                track_scope, track_index, order, body_lines) -> Task:
    body = "\n".join(body_lines)
    task = Task(
        task_id=task_id,
        title=title,
        heading_level=heading_level,
        batch=batch,
        track_heading=track_heading,
        track=track,
        track_scope=track_scope,
        track_index=track_index,
        order=order,
        body=body,
    )

    # The four dependency/package lines sit at a fixed offset: heading, blank,
    # then the four in order. Validated by the parser rather than assumed.
    expected = METADATA_FIELDS[:4]
    if body_lines[1] != "":
        raise ValueError(f"Task {task_id}: no blank line after heading")
    for k, fieldname in enumerate(expected):
        prefix = f"**{fieldname}:**"
        got = body_lines[2 + k]
        if not got.startswith(prefix):
            raise ValueError(f"Task {task_id}: expected {prefix} at body line {2+k}, got {got!r}")
        task.meta_raw[fieldname] = got[len(prefix) :].strip()

    rc_prefix = "**Requirements covered:**"
    rc = [l for l in body_lines if l.startswith(rc_prefix)]
    if len(rc) != 1:
        raise ValueError(f"Task {task_id}: expected 1 Requirements covered line, got {len(rc)}")
    task.meta_raw["Requirements covered"] = rc[0][len(rc_prefix) :].strip()

    for fieldname in ("Objective", "Instructions", "Verification"):
        hits = [l for l in body_lines if l.startswith(f"**{fieldname}:**")]
        if len(hits) != 1:
            raise ValueError(f"Task {task_id}: expected 1 {fieldname} line, got {len(hits)}")

    task.prerequisites, unp_pre = parse_id_list(task.meta_raw["Prerequisites"])
    task.conflicts_with, unp_con = parse_id_list(task.meta_raw["Conflicts with"])
    task.parallel_with, unp_par = parse_id_list(task.meta_raw["Parallel with"])
    task.requirements, task.sections, task.requirements_prose_only = parse_requirements(
        task.meta_raw["Requirements covered"]
    )
    task.unparsed = {
        k: v for k, v in (
            ("prerequisites", unp_pre),
            ("conflicts_with", unp_con),
            ("parallel_with", unp_par),
        ) if v
    }
    return task


# --------------------------------------------------------------------------
# Frontmatter
# --------------------------------------------------------------------------

def _y(value) -> str:
    """A JSON-encoded scalar/list -- valid YAML, and json.loads round-trips it.

    ``ensure_ascii=False`` keeps em dashes and section signs readable in the
    file rather than escaping them to \\uXXXX.
    """
    return json.dumps(value, ensure_ascii=False)


def render_frontmatter(task: Task) -> str:
    j = _y
    rows: list[str] = [
        f"id: {j(task.task_id)}",
        f"batch: {task.batch if task.batch != 'deployment' else j('deployment')}",
        f"batch_dir: {j(task.batch_dir)}",
        f"order: {task.order}",
        f"track: {j(task.track) if task.track else 'null'}",
        f"track_heading: {j(task.track_heading) if task.track_heading else 'null'}",
        f"track_scope: {j(task.track_scope) if task.track_scope else 'null'}",
        f"title: {j(task.title)}",
        f"kind: {j(task.kind)}",
        f"package: {j(task.package)}",
        f"package_raw: {j(task.package_raw)}",
        f"prerequisites: {j(task.prerequisites)}",
        f"prerequisites_raw: {j(task.meta_raw['Prerequisites'])}",
        f"conflicts_with: {j(task.conflicts_with)}",
        f"conflicts_with_raw: {j(task.meta_raw['Conflicts with'])}",
        f"parallel_with: {j(task.parallel_with)}",
        f"parallel_with_raw: {j(task.meta_raw['Parallel with'])}",
        f"requirements_covered: {j(task.requirements)}",
        f"requirements_covered_raw: {j(task.meta_raw['Requirements covered'])}",
        f"sections_covered: {j(task.sections)}",
        f"status: {j(task.status)}",
    ]
    return "---\n" + "\n".join(rows) + "\n---\n"


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a task file into (frontmatter dict, verbatim body)."""
    if not text.startswith("---\n"):
        raise ValueError("file does not start with a frontmatter block")
    end = text.index("\n---\n", 3)
    block = text[4:end]
    body = text[end + len("\n---\n") :]
    fm: dict = {}
    for line in block.split("\n"):
        if not line.strip():
            continue
        key, _, value = line.partition(": ")
        value = value.strip()
        try:
            fm[key] = json.loads(value)
        except json.JSONDecodeError:
            fm[key] = None if value == "null" else value
    return fm, body


def canonical_sort_key(task: Task) -> tuple:
    """batch 0..10 then deployment; within a batch by track order, then id."""
    batch_rank = 99 if task.batch == "deployment" else int(task.batch)
    if task.task_id.startswith("I."):
        num = (0, int(task.task_id.split(".")[1]))
    else:
        major, minor = task.task_id.split(".")
        num = (int(major), int(re.match(r"[0-9]+", minor).group()))
    return (batch_rank, task.track_index, num)


def load_tasks_from_files(tasks_dir: Path = TASKS_DIR) -> list[dict]:
    """Read every generated task file back as (frontmatter, body) records."""
    out = []
    for path in sorted(tasks_dir.rglob("*.md")):
        fm, body = split_frontmatter(path.read_text())
        out.append({"path": path, "fm": fm, "body": body})
    out.sort(key=lambda r: r["fm"]["order"])
    return out


# --------------------------------------------------------------------------
# Document tables
# --------------------------------------------------------------------------
# Shared with the renderer so that the table ``build-plan-index.py`` rewrites
# and the table ``split-plan.py --verify`` asserts against are read by exactly
# the same code.

def heading_blocks(lines: list[str]) -> list[dict]:
    """Every heading with the line range of the block it owns."""
    idx = []
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            idx.append({"i": i, "level": len(m.group(1)), "text": line})
    for n, h in enumerate(idx):
        end = len(lines)
        for later in idx[n + 1 :]:
            if later["level"] <= h["level"]:
                end = later["i"]
                break
        h["end"] = end
        h["inner_end"] = idx[n + 1]["i"] if n + 1 < len(idx) else len(lines)
    return idx


def find_block(blocks, prefix):
    for h in blocks:
        if h["text"].startswith(prefix):
            return h
    raise KeyError(prefix)


def split_table(body: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Split a section body into (prose_before, table, prose_after)."""
    start = next((i for i, l in enumerate(body) if l.startswith("|")), None)
    if start is None:
        return body, [], []
    end = start
    while end < len(body) and body[end].startswith("|"):
        end += 1
    return body[:start], body[start:end], body[end:]


def parse_table(rows: list[str]) -> list[list[str]]:
    """Parse a markdown table into cell lists, dropping the separator row."""
    out = []
    for row in rows:
        if re.match(r"^\|[\s:|-]+\|$", row):
            continue
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        out.append(cells)
    return out


def batch_order(records) -> list[str]:
    """Batch keys in document order (0..6, deployment, 7..10)."""
    seen = []
    for r in records:  # records are already in document order
        key = str(r["fm"]["batch"])
        if key not in seen:
            seen.append(key)
    return seen


# --------------------------------------------------------------------------
# Plan Summary track counts
# --------------------------------------------------------------------------

def plan_summary_track_counts(records, baseline_text: str) -> dict[str, tuple[int, int]]:
    """``batch key -> (count the summary claims, count the corpus has)``.

    The corpus count is the number of distinct ``track_heading`` values the
    batch's tasks carry -- the same definition ``build-plan-index.py`` renders
    into the Tracks column, so the renderer, the cross-check and the verifier
    cannot disagree about what a track is. Rows whose label is not a batch the
    corpus knows about (``Total``) take no part.
    """
    lines = baseline_text.split("\n")
    h = find_block(heading_blocks(lines), "## Plan Summary")
    _, table, _ = split_table(lines[h["i"] + 1 : h["end"]])
    known = set(batch_order(records))
    out: dict[str, tuple[int, int]] = {}
    for cells in parse_table(table)[1:]:  # drop header
        if len(cells) < 3:
            continue
        label = cells[0].strip("*` ")
        key = "deployment" if label == "—" else label
        if key not in known:
            continue
        rows_b = [r for r in records if str(r["fm"]["batch"]) == key]
        tracks = {r["fm"]["track_heading"] for r in rows_b if r["fm"]["track_heading"]}
        out[key] = (int(cells[2].strip("*` ")), len(tracks))
    return out


def track_count_divergences(records, baseline_text: str) -> dict[str, tuple[int, int]]:
    """The batch rows where the summary's track count and the corpus disagree."""
    return {
        key: counts
        for key, counts in plan_summary_track_counts(records, baseline_text).items()
        if counts[0] != counts[1]
    }


def classify_track_count_divergences(records, baseline_text: str):
    """Observed track-count divergences against ``DECLARED_TRACK_COUNT_DIVERGENCES``.

    Returns ``(observed, undeclared, mismatched, stale)``:

    * ``observed``   -- every divergence found, ``key -> (summary, corpus)``
    * ``undeclared`` -- found but not on the allowlist: a NEW divergence, the
      case that matters most, because a lost track looks exactly like this
    * ``mismatched`` -- on the allowlist, but one of the two counts has moved,
      so the recorded reconciliation no longer describes what is there
    * ``stale``      -- on the allowlist but no longer diverging: the entry is
      dead and should be deleted

    Set equality between declared and observed, not one-way filtering: the same
    shape as the ``INTENDED_BODY_CHANGES`` check, which fails on drift AND on a
    silently reverted declaration.
    """
    observed = track_count_divergences(records, baseline_text)
    declared = DECLARED_TRACK_COUNT_DIVERGENCES
    undeclared = [k for k in observed if k not in declared]
    mismatched = [
        k for k in observed
        if k in declared and (declared[k].baseline, declared[k].corpus) != observed[k]
    ]
    stale = [k for k in declared if k not in observed]
    return observed, undeclared, mismatched, stale


def batch_label(key: str) -> str:
    """``"deployment"`` -> ``"Deployment"``; a numeric key -> ``"Batch N"``."""
    return "Deployment" if key == "deployment" else f"Batch {key}"


# --------------------------------------------------------------------------
# The prerequisite DAG
# --------------------------------------------------------------------------
# Shared so that the renderer (which emits the dependency floor), the makespan
# cross-check and ``split-plan.py --verify`` all take the longest path from
# exactly one implementation. Only ``prerequisites`` are edges here.
# ``conflicts_with`` is an UNDIRECTED MUTEX, not an ordering: two conflicting
# tasks cannot run at the same time, but neither one has to go first. Feeding
# conflicts into a longest-path walk would invent an order the corpus does not
# state, which is precisely the judgment the makespan table makes by hand and
# this module refuses to make on its behalf.

def id_key(task_id: str) -> tuple:
    """Sort key that orders ``4.9`` before ``4.10``. ``I.x`` sorts last."""
    if task_id.startswith("I."):
        return (98, int(task_id.split(".")[1]), "")
    major, minor = task_id.split(".")
    m = re.match(r"^([0-9]+)([a-z]*)$", minor)
    return (int(major), int(m.group(1)), m.group(2))


class Chain(NamedTuple):
    """The result of a longest-path query over the prerequisite DAG."""
    length: int          # number of tasks on a maximal chain
    chain: list[str]     # ONE maximal chain, chosen by the tie-break below
    endpoints: list[str] # every task at which some maximal chain ends
    count: int           # how many DISTINCT maximal chains exist
    depth: dict          # task id -> length of the longest chain ending there


def longest_chain(records, subset=None) -> Chain:
    """The longest prerequisite chain over ``records`` (optionally restricted).

    ``subset`` restricts BOTH the nodes and the edges: a prerequisite outside
    the subset is dropped, so the result is the longest chain *within* the
    restriction rather than a chain that leaves it and comes back.

    THE MAXIMAL CHAIN NEED NOT BE UNIQUE, and in this corpus it is not: the
    full graph has eight chains of the maximum length. ``count`` reports how
    many, and ``chain`` is picked by a documented, order-independent tie-break
    rather than by whatever the traversal happened to reach first:

        start at the LOWEST-NUMBERED task among ``endpoints``, then walk
        backwards, at each step taking the LOWEST-NUMBERED prerequisite that
        still lies on a maximal chain (``depth[p] == depth[n] - 1``).

    "Lowest-numbered" is ``id_key``, so 4.9 precedes 4.10. Nothing in the
    result depends on dictionary iteration order or on filesystem order.
    """
    by = {r["fm"]["id"]: r["fm"] for r in records}
    nodes = set(by) if subset is None else {n for n in subset if n in by}
    pre = {n: [p for p in by[n]["prerequisites"] if p in nodes] for n in nodes}
    succ = defaultdict(list)
    for n in nodes:
        for p in pre[n]:
            succ[p].append(n)

    indeg = {n: len(pre[n]) for n in nodes}
    queue = deque(sorted((n for n in nodes if not indeg[n]), key=id_key))
    topo: list[str] = []
    while queue:
        n = queue.popleft()
        topo.append(n)
        for s in succ[n]:
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    if len(topo) != len(nodes):
        raise ValueError(
            "prerequisite graph contains a cycle among "
            f"{sorted(set(nodes) - set(topo), key=id_key)}"
        )

    depth: dict[str, int] = {}
    ways: dict[str, int] = {}
    for n in topo:
        depth[n] = 1 + max((depth[p] for p in pre[n]), default=0)
        on_path = [p for p in pre[n] if depth[p] == depth[n] - 1]
        ways[n] = sum(ways[p] for p in on_path) if on_path else 1

    length = max(depth.values(), default=0)
    endpoints = sorted((n for n in nodes if depth[n] == length), key=id_key)
    count = sum(ways[e] for e in endpoints)

    chain: list[str] = []
    if endpoints:
        cur = endpoints[0]
        chain.append(cur)
        while True:
            back = sorted(
                (p for p in pre[cur] if depth[p] == depth[cur] - 1), key=id_key
            )
            if not back:
                break
            cur = back[0]
            chain.append(cur)
        chain.reverse()
    return Chain(length, chain, endpoints, count, depth)


def batch_subset(records, key: str) -> list[str]:
    """Task ids belonging to one batch key (``"0"``..``"10"``/``"deployment"``)."""
    return [r["fm"]["id"] for r in records if str(r["fm"]["batch"]) == key]


# --------------------------------------------------------------------------
# The makespan table: a CHECK, not a generator
# --------------------------------------------------------------------------
# ``### The makespan the barrier actually buys`` is AUTHORED and stays
# authored. Its per-batch rows encode a scheduling decision that does not
# follow from the corpus: Batch 3's ``3.1 -> 3.2 -> 3.3 -> 3.4`` orders four
# tasks that are only MUTUALLY CONFLICTING, and picking that order out of the
# 24 possible ones is a human's call. Regenerating the row would silently
# replace that judgment with an arbitrary one.
#
# What CAN be asserted mechanically is that the authored table has not drifted
# away from the corpus underneath it, and -- the failure that would actually
# mislead a reader -- that no row claims FEWER slots than the prerequisite DAG
# already forces. A table below the floor understates what the plan costs.

class ConflictSerialisation(NamedTuple):
    """A mutually-conflicting set the makespan table is allowed to order."""
    ids: frozenset      # the tasks the authored row serialises
    reason: str         # the shared file, and why an order had to be chosen


# AUTHORED, NOT DERIVED. The only ``->`` edges in the makespan table that are
# permitted to be something other than a prerequisite edge. Each entry names a
# set of tasks that conflict with one another PAIRWISE (asserted, not assumed)
# and that the authored table therefore runs one after another. Adding an entry
# is a deliberate, reviewable act: it says "these tasks have no stated order,
# and this table imposes one".
DECLARED_CONFLICT_SERIALISATIONS = {
    "3": ConflictSerialisation(
        frozenset({"3.1", "3.2", "3.3", "3.4"}),
        "all four write `app/models/__init__.py`; the conflict is an undirected "
        "mutex, so the run order is an authored scheduling choice, not an edge",
    ),
}

ARROW = "→"
PARALLEL = "∥"
CRITICAL_PATH_HEADING = "## Critical Path"
FLOOR_HEADING = "### The dependency floor"
MAKESPAN_HEADING = "### The makespan the barrier actually buys"
BARE_ID_RE = re.compile(rf"^{TASK_ID_RE}$")
# "So the barrier costs roughly **15 slots** -- 35 against a floor of 20."
CONCLUSION_RE = re.compile(
    r"roughly \*\*([0-9]+) slots\*\*\s*[—-]+\s*([0-9]+) against a floor of ([0-9]+)"
)


def critical_path_lines(plan_text: str) -> list[str]:
    """The lines of the ``## Critical Path`` section, heading included."""
    lines = plan_text.split("\n")
    h = find_block(heading_blocks(lines), CRITICAL_PATH_HEADING)
    return lines[h["i"]: h["end"]]


FLOOR_LENGTH_RE = re.compile(r"^\*\*Critical path length:\*\* ([0-9]+) tasks\.$")


def rendered_dependency_floor(plan_text: str) -> tuple[list[str], int | None]:
    """The chain and the length as they are RENDERED in the document.

    Read back out of the generated block so a verifier can assert that what a
    reader sees is what the corpus says, without re-running the renderer.
    """
    section = critical_path_lines(plan_text)
    h = find_block(heading_blocks(section), FLOOR_HEADING)
    body = section[h["i"] + 1: h["end"]]
    step = re.compile(rf"^\s*(?:{ARROW}\s*)?({TASK_ID_RE})(?:\s|$)")
    ids: list[str] = []
    length: int | None = None
    inside = False
    for line in body:
        if line.startswith("```"):
            inside = not inside
            continue
        if inside:
            if m := step.match(line):
                ids.append(m.group(1))
        elif m := FLOOR_LENGTH_RE.match(line):
            length = int(m.group(1))
    return ids, length


def makespan_table(plan_text: str) -> list[list[str]]:
    """The parsed rows of the makespan table, header row dropped."""
    section = critical_path_lines(plan_text)
    h = find_block(heading_blocks(section), MAKESPAN_HEADING)
    _, table, _ = split_table(section[h["i"] + 1: h["end"]])
    return parse_table(table)[1:]


def _parse_step(token: str):
    """One ``->``-separated step: an id, or a ``{a || b}`` / ``a || b`` group.

    Returns the list of ids, or None if the token is not one of those two
    shapes. ``9.1 -> any row`` fails here, and the row is reported as UNPARSED
    rather than guessed at -- "any row" is authored shorthand, and inventing a
    meaning for it would be exactly the kind of silent reinterpretation this
    check exists to avoid.
    """
    token = token.strip().strip("*` ").strip()
    if token.startswith("{") and token.endswith("}"):
        token = token[1:-1]
    parts = [p.strip().strip("*` ").strip() for p in token.split(PARALLEL)]
    if parts and all(BARE_ID_RE.match(p) for p in parts):
        return parts
    return None


def parse_makespan_cell(cell: str):
    """``(steps, None)`` or ``(None, offending_token)``.

    The trailing authored parenthetical is dropped before parsing, the same way
    ``parse_id_list`` drops one, so prose attached to a row cannot leak a token.
    """
    text = PAREN_RE.sub(" ", cell).strip()
    if not text:
        return [], None
    steps = []
    for token in text.split(ARROW):
        step = _parse_step(token)
        if step is None:
            return None, token.strip()
        steps.append(step)
    return steps, None


def check_makespan_table(records, plan_text: str):
    """``(findings, info)`` -- findings are defects, info is context.

    Four assertions, plus one reconciliation of the authored conclusion:

    1. every task id the table names exists in the corpus;
    2. every ``->`` edge is a real prerequisite edge, or joins two members of a
       DECLARED_CONFLICT_SERIALISATIONS set that genuinely conflict pairwise;
    3. every row's slot count is >= the prerequisite-only longest chain inside
       that batch -- the table may claim a batch costs MORE than the DAG floor
       (a conflict has to be serialised somehow) but never less;
    4. the stated total equals the sum of the slot column;
    5. "roughly **N slots** -- T against a floor of F" reconciles against the
       table total and the derived critical path length, when that sentence is
       present in the form the check knows.

    Rows whose notation the grammar does not cover are reported as UNPARSED and
    take no part in 2. They still take part in 1, 3 and 4.
    """
    findings: list[str] = []
    info: list[str] = []
    by = {r["fm"]["id"]: r["fm"] for r in records}
    conflicts = {tid: set(fm["conflicts_with"]) for tid, fm in by.items()}

    # --- the allowlist describes something real ---------------------------
    for key, entry in sorted(DECLARED_CONFLICT_SERIALISATIONS.items()):
        missing = sorted(entry.ids - set(by), key=id_key)
        if missing:
            findings.append(
                f"declared conflict serialisation for {batch_label(key)} names "
                f"{missing}, which the corpus does not have"
            )
            continue
        non_clique = [
            f"{a} ↮ {b}"
            for a in sorted(entry.ids, key=id_key)
            for b in sorted(entry.ids, key=id_key)
            if a != b and b not in conflicts[a]
        ]
        if non_clique:
            findings.append(
                f"declared conflict serialisation for {batch_label(key)} is not a "
                f"mutual-conflict set: {non_clique} -- the reason "
                f"({entry.reason}) no longer describes the corpus"
            )

    rows = makespan_table(plan_text)
    slot_total_claimed = None
    slot_sum = 0
    used_serialisations: set[str] = set()
    n_rows = 0

    for cells in rows:
        if len(cells) < 3:
            continue
        label = cells[0].strip("*` ")
        chain_cell, slot_cell = cells[1], cells[2].strip("*`~ ")
        if label.lower() == "total":
            slot_total_claimed = int(slot_cell) if slot_cell.isdigit() else None
            if slot_total_claimed is None:
                findings.append(f"makespan Total slot cell is not a number: {cells[2]!r}")
            continue
        key = "deployment" if label == "—" else label
        n_rows += 1
        subset = batch_subset(records, key)
        if not subset:
            findings.append(f"makespan row {label!r} names no batch the corpus has")
            continue

        # (3) slots vs the prerequisite-only floor
        floor = longest_chain(records, subset).length
        if slot_cell.isdigit():
            slots = int(slot_cell)
            slot_sum += slots
            if slots < floor:
                findings.append(
                    f"{batch_label(key)}: the table claims {slots} slot(s), but the "
                    f"prerequisite DAG alone forces a chain of {floor} "
                    f"({' → '.join(longest_chain(records, subset).chain)}). A slot "
                    f"count BELOW the floor understates what the plan costs."
                )
        else:
            findings.append(f"{batch_label(key)}: slot cell is not a number: {cells[2]!r}")

        steps, offending = parse_makespan_cell(chain_cell)
        if steps is None:
            info.append(
                f"{batch_label(key)}: chain cell UNPARSED at {offending!r} -- authored "
                f"notation outside the id / '{{a {PARALLEL} b}}' grammar; its "
                f"{ARROW} edges are not checked. Cell: {chain_cell.strip()!r}"
            )
            continue

        # (1) ids exist
        named = [tid for step in steps for tid in step]
        unknown = sorted({t for t in named if t not in by}, key=id_key)
        if unknown:
            findings.append(
                f"{batch_label(key)}: the row names {unknown}, which the corpus "
                f"does not have"
            )
            continue
        wrong_batch = sorted({t for t in named if str(by[t]["batch"]) != key}, key=id_key)
        if wrong_batch:
            findings.append(
                f"{batch_label(key)}: the row names "
                + ", ".join(f"{t} (batch {by[t]['batch']})" for t in wrong_batch)
                + " -- a per-batch row may only name that batch's tasks"
            )

        # (2) every edge is a prerequisite edge or a declared serialisation
        entry = DECLARED_CONFLICT_SERIALISATIONS.get(key)
        for left, right in zip(steps, steps[1:]):
            for a in left:
                for b in right:
                    if a in by[b]["prerequisites"]:
                        continue
                    if entry and {a, b} <= entry.ids and b in conflicts[a]:
                        used_serialisations.add(key)
                        continue
                    findings.append(
                        f"{batch_label(key)}: `{a} {ARROW} {b}` is neither a "
                        f"prerequisite edge ({b} requires "
                        f"{by[b]['prerequisites'] or 'nothing'}) nor a declared "
                        f"conflict-driven serialisation"
                    )

    # the allowlist is not a graveyard
    for key in sorted(set(DECLARED_CONFLICT_SERIALISATIONS) - used_serialisations):
        findings.append(
            f"{batch_label(key)}: declared conflict serialisation "
            f"{sorted(DECLARED_CONFLICT_SERIALISATIONS[key].ids, key=id_key)} is no "
            f"longer used by any makespan row -- the entry is stale, delete it"
        )

    # (4) the total is the column
    if slot_total_claimed is not None and slot_total_claimed != slot_sum:
        findings.append(
            f"makespan Total says {slot_total_claimed} slots, the column sums to {slot_sum}"
        )

    # (5) the authored conclusion reconciles
    floor = longest_chain(records).length
    text = "\n".join(critical_path_lines(plan_text))
    m = CONCLUSION_RE.search(text.replace("\n", " "))
    if m is None:
        info.append(
            "the conclusion sentence was not found in the form 'roughly **N slots** "
            "— T against a floor of F'; the slot/total/floor reconciliation was not "
            "asserted"
        )
    else:
        cost, total, claimed_floor = (int(g) for g in m.groups())
        if claimed_floor != floor:
            findings.append(
                f"the conclusion says 'a floor of {claimed_floor}', the derived "
                f"critical path is {floor} tasks"
            )
        if slot_total_claimed is not None and total != slot_total_claimed:
            findings.append(
                f"the conclusion says the makespan is {total}, the table's Total says "
                f"{slot_total_claimed}"
            )
        if cost != total - claimed_floor:
            findings.append(
                f"the conclusion says the barrier costs {cost} slots, but "
                f"{total} - {claimed_floor} = {total - claimed_floor}"
            )
    info.append(
        f"{n_rows} per-batch makespan row(s); slot column sums to {slot_sum}; "
        f"derived critical path floor is {floor}"
    )
    return findings, info


# --------------------------------------------------------------------------
# The authored server-chain sentence: a CHECK, not a generator
# --------------------------------------------------------------------------
# ``### Three things about the shape of this chain`` opens with an authored
# claim about the SERVER's own longest chain -- the counterpart to the derived
# floor above it, and the sentence that tells a reader which track can afford
# to be interrupted. It stayed authored (it is an argument, not a table), and
# for a long time nothing tied it to the corpus: it printed a chain that was
# neither maximal within the server nor server-only -- its last node, 10.2,
# is ``track_scope: null`` and packaged at the repository root.
#
# SERVER-SCOPED means ``track_scope == "server"``. That is the field the
# corpus declares scope in, and it is exactly the field the bad chain violated.
# The obvious alternative -- a ``package`` prefix test -- selects the same set
# apart from 10.3 (``package: server, extension``, a two-workspace sweep) and
# I.3 (``server/app/carriers/usps``, a deployment task with a null scope);
# both carry no track_scope, so neither is a server TRACK, and neither is on
# any maximal chain. The declared field is preferred over parsing a prose
# package string.

SERVER_SCOPE = "server"
THREE_THINGS_HEADING = "### Three things about the shape of this chain"

# English number words, built structurally so the two prose checks that have to
# read a spelled-out count -- the server-chain sentence ("twelve tasks") and the
# restatement check below ("Ninety-one tasks") -- share one table instead of two
# hand-written lists that could drift apart.
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


# The server-chain sentence's own alternation stays capped at 0-25, exactly the
# range it had when CHAIN_LENGTH_RE / CHAIN_TIE_RE were written; the dict is a
# numeric-order slice of NUMBER_WORDS, so ``_COUNT`` is byte-identical to the
# hand-written version it replaced and that check's behaviour is untouched.
_NUMBER_WORDS = {w: n for w, n in NUMBER_WORDS.items() if n <= 25}
_COUNT = r"([0-9]+|" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")"
# "... is twelve tasks ..." / "... fifteen distinct chains tie at that length"
CHAIN_LENGTH_RE = re.compile(rf"\b{_COUNT}\s+tasks\b", re.IGNORECASE)
CHAIN_TIE_RE = re.compile(rf"\b{_COUNT}\s+(?:distinct\s+)?chains\b", re.IGNORECASE)
_ID_AT_END_RE = re.compile(rf"({TASK_ID_RE})\s*$")
_ID_AT_START_RE = re.compile(rf"^\s*({TASK_ID_RE})(?!\.?[0-9])")


def _count_value(token: str) -> int | None:
    return parse_count(token)


def parse_server_chain_sentence(plan_text: str):
    """``(ids, claimed_length, claimed_ties, note)`` for the authored sentence.

    Anchored on STRUCTURE, not on wording: the first paragraph under
    ``### Three things about the shape of this chain`` that carries an ``→``
    run. Nothing here depends on the sentence's phrasing, so the prose can be
    rewritten without silently disabling the check.

    ``ids`` is None -- with ``note`` saying why -- when the paragraph is absent
    or its shape is outside the grammar (a bare-id run joined by ``→``, with
    prose allowed before the first id and after the last). That is the same
    refusal ``parse_makespan_cell`` makes at ``9.1 → any row``: guessing at
    authored notation is how a check starts asserting something it was never
    told.
    """
    section = critical_path_lines(plan_text)
    try:
        h = find_block(heading_blocks(section), THREE_THINGS_HEADING)
    except Exception:
        return None, None, None, f"{THREE_THINGS_HEADING!r} is not in {CRITICAL_PATH_HEADING!r}"

    paragraphs: list[list[str]] = []
    current: list[str] = []
    for line in section[h["i"] + 1: h["end"]]:
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)

    arrowed = [p for p in paragraphs if ARROW in "\n".join(p)]
    if not arrowed:
        return None, None, None, (
            f"no paragraph under {THREE_THINGS_HEADING!r} carries a '{ARROW}' chain"
        )
    text = " ".join(line.strip() for line in arrowed[0])

    tokens = text.split(ARROW)
    ids: list[str] = []
    m = _ID_AT_END_RE.search(tokens[0])
    if m is None:
        return None, None, None, (
            f"the text before the first '{ARROW}' does not end in a task id: "
            f"{tokens[0].strip()[-40:]!r}"
        )
    ids.append(m.group(1))
    for token in tokens[1:-1]:
        bare = token.strip().strip("*` ").strip()
        if not BARE_ID_RE.match(bare):
            return None, None, None, (
                f"a step between arrows is not a bare task id: {bare!r}"
            )
        ids.append(bare)
    m = _ID_AT_START_RE.match(tokens[-1])
    if m is None:
        return None, None, None, (
            f"the text after the last '{ARROW}' does not begin with a task id: "
            f"{tokens[-1].strip()[:40]!r}"
        )
    ids.append(m.group(1))

    m = CHAIN_LENGTH_RE.search(text)
    claimed_length = _count_value(m.group(1)) if m else None
    m = CHAIN_TIE_RE.search(text)
    claimed_ties = _count_value(m.group(1)) if m else None
    return ids, claimed_length, claimed_ties, None


def check_server_chain_sentence(records, plan_text: str):
    """``(findings, info)`` -- the authored server chain against the corpus.

    1. every id it names exists;
    2. every ``→`` is a real prerequisite edge;
    3. every task on it is server-scoped -- the assertion 10.2 would have
       failed, and the reason this check exists;
    4. its length is the derived server-only maximum, and the count the
       sentence states in words or digits agrees with the chain it prints.

    An absent or unparseable sentence is INFO, not a finding, following the
    makespan conclusion: the document is allowed to stop making the claim, it
    is not allowed to make a false one.
    """
    findings: list[str] = []
    info: list[str] = []
    by = {r["fm"]["id"]: r["fm"] for r in records}
    server = {tid for tid, fm in by.items() if fm.get("track_scope") == SERVER_SCOPE}
    derived = longest_chain(records, server)

    ids, claimed_length, claimed_ties, note = parse_server_chain_sentence(plan_text)
    if ids is None:
        info.append(
            f"the authored server-chain sentence was not read ({note}); the chain "
            f"it names was not asserted. The corpus says {derived.length} tasks "
            f"over {len(server)} server-scoped ones, {derived.count} chain(s) tied"
        )
        return findings, info

    printed = " → ".join(ids)
    unknown = sorted({t for t in ids if t not in by}, key=id_key)
    if unknown:
        findings.append(
            f"the authored server chain names {unknown}, which the corpus does "
            f"not have. Chain: {printed}"
        )
        return findings, info

    not_server = [
        f"{t} (track_scope: {by[t].get('track_scope') or 'null'}, package: "
        f"{by[t].get('package') or 'none'})"
        for t in ids if t not in server
    ]
    if not_server:
        findings.append(
            "the authored server chain is not server-only -- "
            + "; ".join(not_server)
            + f". A chain that leaves the server does not say when the server is "
              f"done. Chain: {printed}"
        )

    non_edges = [
        f"{a} {ARROW} {b} ({b} requires {by[b]['prerequisites'] or 'nothing'})"
        for a, b in zip(ids, ids[1:]) if a not in by[b]["prerequisites"]
    ]
    if non_edges:
        findings.append(
            "the authored server chain names steps that are not prerequisite "
            "edges: " + "; ".join(non_edges)
        )

    if len(ids) != derived.length:
        findings.append(
            f"the authored server chain is {len(ids)} tasks, but the longest "
            f"chain within track_scope: server is {derived.length} "
            f"({' → '.join(derived.chain)})"
        )
    if claimed_length is None:
        info.append(
            "the authored server-chain sentence states no length in the form "
            "'<n> tasks'; only the printed chain was asserted"
        )
    elif claimed_length != len(ids):
        findings.append(
            f"the authored server-chain sentence says {claimed_length} tasks; the "
            f"chain it prints is {len(ids)}: {printed}"
        )
    if claimed_ties is not None and claimed_ties != derived.count:
        findings.append(
            f"the authored server-chain sentence says {claimed_ties} chain(s) tie "
            f"at that length; the corpus has {derived.count}"
        )

    info.append(
        f"authored server chain: {len(ids)} tasks over {len(server)} server-scoped "
        f"tasks; {derived.count} chain(s) tie at {derived.length}, ending at "
        f"{', '.join(derived.endpoints)}"
    )
    return findings, info


# --------------------------------------------------------------------------
# Restatements of the derived quantities in authored prose: a CHECK
# --------------------------------------------------------------------------
# Three numbers in this plan are DERIVED: the task count (the corpus), the
# critical-path floor (the longest prerequisite chain) and the makespan slot
# total (the makespan table's slot column, which check_makespan_table holds to
# its own Total cell). Inside ``## Critical Path`` each of them is either
# generated or already asserted. OUTSIDE that section they are restated in
# authored argument -- the header field a reader sees first, and the
# "Theoretical speedup, honestly stated" paragraph -- where nothing tied them to
# the corpus, so the floor could move from 20 to 22 and those sentences would go
# on saying 20 forever.
#
# This is a CHECK, not a generator, for the same reason the makespan table is:
# the prose is an ARGUMENT ("that ceiling is unreachable under the commit
# barrier this plan imposes"), and regenerating it would flatten the writing
# into a number dump. What can be asserted is that the numbers it argues from
# are still this corpus's numbers.

class Claim(NamedTuple):
    """One number inside a site, and the derived quantity it must agree with."""
    pattern: str     # regex over the site's paragraph; group 1 is the stated number
    quantity: str    # a key of derived_quantities()


class Restatement(NamedTuple):
    """An authored sentence that repeats derived numbers, and what it owes them."""
    anchor: str            # a line-leading literal; must start EXACTLY one line
    claims: tuple          # the Claims read out of the paragraph that line sits in
    reason: str            # what the site is for, so a failure says what broke


# ANCHORING. A site is located by a line-leading literal -- a bold field label
# or a bold paragraph lead-in -- and the region searched is the whole PARAGRAPH
# that line begins or belongs to. Deliberately NOT a full sentence: a sentence
# anchor turns ordinary copy-editing into a build failure, and re-wrapping a
# paragraph would break a mid-sentence phrase anchor. Labels and lead-ins are
# the document's own structure and change only when the section changes.
#
# Within the paragraph each claim is read by the shortest phrase that says WHICH
# number is meant -- a unit noun ("slots", "-task", "-slot makespan") or, for a
# bare ratio, the denominator it is a ratio OF, reached across a bounded gap of
# non-`*` characters so the connecting words ("is a", "which is") can be
# rewritten freely. FAILURE MODE: if a site's label or its unit phrasing is
# rewritten away, the claim is reported NOT FOUND -- loudly -- never silently
# skipped. That is the trade this check makes: it will occasionally ask a
# copy-editor to update a pattern, and it will never quietly stop asserting.
_NUM = "(?:[0-9]+|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + ")"
_RATIO = r"([0-9]+(?:\.[0-9]+)?)"

# AUTHORED, NOT DERIVED. Every place outside ``## Critical Path`` where the plan
# restates a derived quantity in prose. Set equality with what is actually
# found, the same spirit as INTENDED_BODY_CHANGES: a stated number that has
# drifted fails, and so does an entry whose site can no longer be located.
# Adding an entry here is a deliberate, reviewable act.
DECLARED_RESTATEMENTS = {
    "header / total tasks": Restatement(
        anchor="**Total Tasks:**",
        claims=(
            Claim(rf"\*\*Total Tasks:\*\*\s+~?({_NUM})\b", "tasks"),
        ),
        reason="the headline count a reader meets before anything else",
    ),
    "header / makespan": Restatement(
        anchor="**Makespan under the batch barrier:**",
        claims=(
            Claim(rf"~?({_NUM})\s+slots\b", "makespan"),
            Claim(rf"~?({_NUM})-task\b", "floor"),
        ),
        reason="the header's summary of the Critical Path section, four hundred "
               "lines before the section itself",
    ),
    "speedup / ceiling": Restatement(
        anchor="**Theoretical speedup, honestly stated.**",
        claims=(
            Claim(rf"\b({_NUM})\b[^*]{{0,30}}?\bdependency\s+floor\b", "tasks"),
            Claim(rf"~?({_NUM})-task\s+dependency\s+floor\b", "floor"),
            Claim(rf"\bdependency\s+floor\b[^*]{{0,60}}?\*\*~?{_RATIO}x\*\*",
                  "tasks per floor task"),
        ),
        reason="the unreachable upper bound the paragraph argues against",
    ),
    "speedup / makespan": Restatement(
        anchor="**Theoretical speedup, honestly stated.**",
        claims=(
            Claim(rf"\b({_NUM})\b[^*]{{0,20}}?~?[0-9]+-slot\b", "tasks"),
            Claim(rf"~?({_NUM})-slot\s+makespan\b", "makespan"),
            Claim(rf"-slot\s+makespan\b[^*]{{0,60}}?\*\*~?{_RATIO}x\*\*",
                  "tasks per slot"),
        ),
        reason="the speedup the paragraph says actually matters",
    ),
    "speedup / non-agent tasks": Restatement(
        anchor="**Theoretical speedup, honestly stated.**",
        claims=(
            Claim(rf"\bof\s+the\s+~?({_NUM})\s+tasks\b", "tasks"),
        ),
        reason="the two tasks that are not agent work, stated as a fraction of "
               "the corpus",
    ),
}


class DerivedQuantity(NamedTuple):
    """A number the corpus decides, and how it was decided."""
    value: Decimal
    origin: str
    decimals: int   # places to show it to when reporting


def makespan_slot_total(plan_text: str) -> int | None:
    """The makespan table's slot column, summed over the per-batch rows.

    The same definition check_makespan_table sums to reconcile the authored
    ``**Total**`` cell against, so the restated ~35 and the table's own Total
    cannot be checked against two different numbers. ``None`` when no per-batch
    row carries a numeric slot count -- the table is unreadable, which is
    check_makespan_table's finding to make, not this one's.
    """
    total = 0
    seen = False
    for cells in makespan_table(plan_text):
        if len(cells) < 3 or cells[0].strip("*` ").lower() == "total":
            continue
        slot = cells[2].strip("*`~ ")
        if slot.isdigit():
            total += int(slot)
            seen = True
    return total if seen else None


def derived_quantities(records, plan_text: str) -> dict[str, DerivedQuantity]:
    """The numbers the authored restatements are held to.

    Ratios are included as quantities in their own right: ``4.5x`` is not a
    number the document repeats from somewhere else, it is an assertion ABOUT
    two derived numbers, and it can be wrong while both of them are right.
    """
    out = {
        "tasks": DerivedQuantity(
            Decimal(len(records)), "the number of tasks in the corpus", 0),
        "floor": DerivedQuantity(
            Decimal(longest_chain(records).length),
            "the longest chain through the prerequisite graph", 0),
    }
    slots = makespan_slot_total(plan_text)
    if slots is not None:
        out["makespan"] = DerivedQuantity(
            Decimal(slots), "the makespan table's slot column", 0)
    out["tasks per floor task"] = DerivedQuantity(
        out["tasks"].value / out["floor"].value,
        f"{out['tasks'].value} tasks / a floor of {out['floor'].value}", 4)
    if "makespan" in out:
        out["tasks per slot"] = DerivedQuantity(
            out["tasks"].value / out["makespan"].value,
            f"{out['tasks'].value} tasks / {out['makespan'].value} slots", 4)
    return out


# ROUNDING. The prose rounds, so equality is the wrong test: 91/20 is 4.55 and
# the document says **4.5x**. The rule is "the stated number is a CORRECT
# ROUNDING of the derived one, to the precision the document itself states":
#
#     |stated - derived| <= 0.5 * 10 ** -decimals(stated)
#
# where decimals(stated) is the number of digits printed after the point. Ties
# are accepted in EITHER direction -- 4.55 may be written 4.5 or 4.6, both are
# honest -- which is why the bound is inclusive.
#
# The rule is deliberately not a fixed tolerance. It tightens as the prose gets
# more precise, so an integer restatement ("20 tasks", "~35 slots") must be
# EXACT: the tolerance there is 0.5, and the 20 that should have become 22 is
# off by 2. At one decimal the tolerance is 0.05, so **4.5x** survives a floor
# of 20 (4.55) and fails a floor of 21 (4.333) or 22 (4.136).
#
# Where it is loose, and honestly: a one-decimal ratio can absorb a small move
# in its denominator -- 91/36 is 2.528, only 0.072 from a stated 2.6, but 0.072
# > 0.05 so even that fires. What a ratio cannot do is be the ONLY guard, which
# is why every site that states a ratio also declares the raw numbers it is a
# ratio of; the raw ones are integers and admit no slack at all.
#
# The `~` the document puts on "~35" and "~2.6x" is an authored hedge about the
# scheduling model, not about the digit. It is stripped before parsing and does
# NOT widen the tolerance: the makespan table's Total really is 35.

def restatement_tolerance(decimals: int) -> Decimal:
    """Half a unit in the last place the document prints."""
    return Decimal(1).scaleb(-decimals) / 2


def parse_stated(token: str) -> tuple[Decimal, int] | None:
    """``"4.5"`` -> ``(Decimal("4.5"), 1)``; ``"Ninety-one"`` -> ``(91, 0)``."""
    t = token.strip().lower()
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", t):
        return Decimal(t), len(t.partition(".")[2])
    n = parse_count(t)
    return None if n is None else (Decimal(n), 0)


def readable_pattern(pattern: str) -> str:
    """A claim's regex with the number alternations folded back to a placeholder.

    ``_NUM`` is a hundred-way alternation of English number words. Printing it
    raw in a failure message buries the one thing the reader needs -- which
    PHRASE stopped matching -- under six lines of "seventy-three|seventy-seven".
    """
    return pattern.replace(_NUM, "<number>").replace(_RATIO, "<ratio>")


def _show(value: Decimal, decimals: int) -> str:
    q = value.quantize(Decimal(1).scaleb(-decimals)) if decimals else value
    return f"{q.normalize():f}" if decimals else f"{q:f}"


# UNDECLARED restatements. Hunting bare numbers in prose fires on unrelated 20s,
# so the sweep is narrowed twice and its limits are stated rather than papered
# over. It matches only these SHAPES -- a number wearing a unit, a bold header
# field, an "N over" ratio phrase, and a bold multiplier -- and only when the
# number AGREES with a derived quantity. Agreement is the gate because the
# realistic failure is a new sentence being WRITTEN correctly today and going
# stale later; a sentence that is already wrong is caught by whichever declared
# site covers it, or not at all.
#
# LIMIT, stated plainly: a restatement phrased outside these shapes -- "ninety
# one units of work", "a floor of twenty" -- is NOT detected, and a restatement
# that already disagrees with the corpus is NOT detected. New restatement sites
# must still be declared by hand in DECLARED_RESTATEMENTS. This sweep is a net
# that catches the common shapes, not a proof that none escaped.
_RESTATEMENT_SHAPES = (
    ("a number wearing a unit", rf"~?\b({_NUM})(?:-|\s+)(?:tasks?|slots?)\b"),
    ("a bold header field", rf"^\*\*[^*]+:\*\*\s+~?({_NUM})\b"),
    ("an 'N over' ratio phrase", rf"\b({_NUM})\s+over\b"),
    ("a bold multiplier", rf"\*\*~?{_RATIO}x\*\*"),
)

# Regions the sweep does not scan, and why each one is already covered.
PROGRESS_PREFIX = "**Progress:**"
_EXEMPT_REASONS = {
    "critical path": f"inside {CRITICAL_PATH_HEADING!r}, whose numbers are "
                     f"generated (the dependency floor) or already asserted by "
                     f"check_makespan_table / check_server_chain_sentence",
    "progress": f"a paragraph carrying a {PROGRESS_PREFIX!r} line, which "
                f"build-plan-index.py regenerates from the corpus every build",
}


def _paragraphs(lines: list[str]) -> list[tuple[int, list[str]]]:
    """``(index of the first line, the lines)`` per run of non-blank lines."""
    out: list[tuple[int, list[str]]] = []
    start, current = 0, []
    for i, line in enumerate(lines):
        if line.strip():
            if not current:
                start = i
            current.append(line)
        elif current:
            out.append((start, current))
            current = []
    if current:
        out.append((start, current))
    return out


def check_restated_quantities(records, plan_text: str):
    """``(findings, info)`` -- the authored restatements against the corpus.

    1. every declared site is still locatable by its anchor, and every claim
       inside it still readable -- a site that has been deleted or rewritten
       past its anchor FAILS rather than quietly dropping out of the check;
    2. every stated number is a correct rounding of the derived value, at the
       precision the document itself states;
    3. no restatement in one of the known shapes sits outside a declared site.

    Set equality in the INTENDED_BODY_CHANGES spirit: drift fails, a stale
    declaration fails, and an undeclared restatement fails -- with (3) limited
    to the shapes _RESTATEMENT_SHAPES knows, which is said out loud in the info
    lines rather than left for a reader to discover.
    """
    findings: list[str] = []
    info: list[str] = []
    derived = derived_quantities(records, plan_text)
    lines = plan_text.split("\n")
    paragraphs = _paragraphs(lines)

    try:
        h = find_block(heading_blocks(lines), CRITICAL_PATH_HEADING)
        critical_path = range(h["i"], h["end"])
    except Exception:
        critical_path = range(0)

    # site key -> {paragraph start line -> [spans of the numbers it asserts]}
    covered: dict[int, list[tuple[int, int]]] = defaultdict(list)
    n_claims = 0

    for key, site in DECLARED_RESTATEMENTS.items():
        hits = [p for p in paragraphs
                if any(line.startswith(site.anchor) for line in p[1])]
        if not hits:
            findings.append(
                f"restatement site {key!r} was not found: no line starts with "
                f"{site.anchor!r}. Either the site was deleted or its prose was "
                f"rewritten past the anchor -- the entry says it restates "
                f"{', '.join(sorted({c.quantity for c in site.claims}))} "
                f"({site.reason}). Re-anchor it or delete the declaration."
            )
            continue
        if len(hits) > 1:
            findings.append(
                f"restatement site {key!r} is ambiguous: {len(hits)} lines start "
                f"with {site.anchor!r} (lines "
                f"{', '.join(str(p[0] + 1) for p in hits)}). An anchor has to "
                f"name one site."
            )
            continue
        start, para = hits[0]
        region = "\n".join(para)

        for claim in site.claims:
            n_claims += 1
            quantity = derived.get(claim.quantity)
            matches = list(re.finditer(claim.pattern, region, re.IGNORECASE))
            if not matches:
                findings.append(
                    f"{key}: the {claim.quantity} it restates was not found in the "
                    f"paragraph at line {start + 1}. The phrasing the claim reads "
                    f"({readable_pattern(claim.pattern)}) is gone, so the number is "
                    f"no longer asserted -- update the pattern or drop the claim."
                )
                continue
            if len(matches) > 1:
                findings.append(
                    f"{key}: the {claim.quantity} claim matches "
                    f"{len(matches)} places in the paragraph at line {start + 1} "
                    f"({', '.join(repr(m.group(0)) for m in matches)}); it has to "
                    f"identify one number"
                )
                continue
            m = matches[0]
            covered[start].append(m.span(1))
            if quantity is None:
                info.append(
                    f"{key}: {claim.quantity} is not derivable from this document "
                    f"right now, so the stated {m.group(1)!r} was not asserted"
                )
                continue
            stated = parse_stated(m.group(1))
            if stated is None:
                findings.append(
                    f"{key}: {m.group(1)!r} is not a number this check can read "
                    f"(digits, or an English number word up to ninety-nine)"
                )
                continue
            value, decimals = stated
            tol = restatement_tolerance(decimals)
            if abs(quantity.value - value) > tol:
                findings.append(
                    f"{key}: the document states {m.group(0).strip()!r} -- "
                    f"{claim.quantity} = {_show(value, decimals)} -- but the corpus "
                    f"says {_show(quantity.value, quantity.decimals)} "
                    f"({quantity.origin}). At the {decimals}-decimal precision the "
                    f"prose states, a correct rounding has to be within "
                    f"{tol} of it."
                )

    # --- restatements nobody declared ------------------------------------
    exact = {q.value for name, q in derived.items() if q.decimals == 0}
    undeclared: list[str] = []
    for start, para in paragraphs:
        if start in critical_path:
            continue
        if any(line.startswith(PROGRESS_PREFIX) for line in para):
            continue
        region = "\n".join(para)
        for shape, pattern in _RESTATEMENT_SHAPES:
            for m in re.finditer(pattern, region, re.IGNORECASE | re.MULTILINE):
                if any(a < m.end(1) and m.start(1) < b for a, b in covered[start]):
                    continue
                stated = parse_stated(m.group(1))
                if stated is None:
                    continue
                value, decimals = stated
                agrees = [
                    name for name, q in derived.items()
                    if abs(q.value - value) <= restatement_tolerance(decimals)
                    and (decimals > 0 or value in exact)
                ]
                if agrees:
                    undeclared.append(
                        f"line {start + 1}: {m.group(0).strip()!r} ({shape}) "
                        f"restates {' / '.join(sorted(agrees))}"
                    )
    if undeclared:
        findings.append(
            "restatements of a derived quantity that no DECLARED_RESTATEMENTS "
            "entry covers: " + "; ".join(undeclared)
            + ". Each is a number that will go stale silently -- declare it with "
              "an anchor and a claim, or move the sentence into "
            + repr(CRITICAL_PATH_HEADING)
        )

    info.append(
        f"{len(DECLARED_RESTATEMENTS)} declared restatement site(s), {n_claims} "
        f"claim(s), against " + ", ".join(
            f"{name} = {_show(q.value, q.decimals)}"
            for name, q in derived.items()
        )
    )
    info.append(
        "agreement is 'a correct rounding to the precision the prose states' "
        "(|stated - derived| <= half a unit in the last printed place), so an "
        "integer restatement must be exact and '**4.5x**' is held to +/-0.05"
    )
    info.append(
        "undeclared restatements are swept for only in the shapes "
        + ", ".join(repr(s) for s, _ in _RESTATEMENT_SHAPES)
        + ", and only while they still AGREE with the corpus; a restatement "
          "phrased outside them must be declared by hand. Not scanned: "
        + "; ".join(_EXEMPT_REASONS.values())
    )
    return findings, info


# --------------------------------------------------------------------------
# The Batch Execution Overview: a CHECK, not a generator
# --------------------------------------------------------------------------
# ``## Batch Execution Overview`` is 107 lines of hand-maintained schedule --
# the largest single restatement of the corpus in the document, and until this
# check the only large one nothing held to it. It names every task id, the
# track each one runs in, the order they run in, and which lanes are parallel.
#
# It is CHECKED, not generated, for the same reason the makespan table is: the
# derived facts are interleaved with judgment that exists nowhere in
# frontmatter. The ``--- ... PARALLEL ... ---`` lines carry the REASON a lane
# is parallel ("different workspaces", "CONFLICT-free but B depends on 8.2 for
# messaging"); every ``>>> Commit checkpoint:`` / ``>>> Gate:`` line states
# what the barrier buys; Batch 0's ``>>> Blocks ...`` line states the blast
# radius of a failed spike. None of that is derivable, and a generator would
# delete all of it.
#
# WHAT IS ASSERTED (see check_batch_overview for the enumerated list): ids
# exist, each task is under the batch and the track letter its frontmatter
# says, each batch's roster is exactly the corpus's, every ``->`` is a
# prerequisite edge or a declared conflict serialisation, and every "after X"
# claim is a prerequisite edge.
#
# WHAT IS NOT: the ``>>>`` and ``--- ... ---`` lines are authored prose. Their
# ids are asserted to EXIST and nothing more -- "Blocks 2.8, 3.13, 3.14,
# 7.7-7.10 and the Batch 9 driving rows ONLY" uses a range notation that
# appears nowhere else in this grammar and a phrase ("the Batch 9 driving
# rows") that is not a task reference at all, so the range is reported UNPARSED
# and the claim itself is left to a human. That is the refusal
# ``parse_makespan_cell`` makes at ``9.1 → any row``.

OVERVIEW_HEADING = "## Batch Execution Overview"


class DeclaredTitleDivergence(NamedTuple):
    """A batch title the overview states differently from its own ``##`` heading."""
    overview: str   # the line as the overview block carries it
    heading: str    # the ``##`` heading text, without the leading "## "
    reason: str     # why the two are allowed to differ


# AUTHORED, NOT DERIVED. Titles are compared with parentheticals dropped and
# case folded away -- the block is deliberately lower-cased ("Schemas,
# protocols, leaf modules" for "## Batch 3: Schemas, Protocols, Leaf Modules")
# and Batch 0 carries an extra "(BLOCKING, not code)" annotation, and neither of
# those is a defect. What is left after that normalisation is real wording, and
# a real difference has to be declared here with BOTH strings, the same
# set-equality shape as DECLARED_TRACK_COUNT_DIVERGENCES: an undeclared
# difference fails, a declared entry whose strings have moved fails, and a
# declared entry whose difference has gone away fails as stale.
DECLARED_OVERVIEW_TITLE_DIVERGENCES = {
    "6": DeclaredTitleDivergence(
        "Batch 6: Routes and app; driver core",
        "Batch 6: Routes and Application; Driver Core",
        "the fenced block abbreviates 'Application' to 'app' to hold the column "
        "width the ASCII lanes are aligned on; both name the same batch",
    ),
}


# AUTHORED, NOT DERIVED. The only ``->`` arrows in the overview permitted to be
# something other than a prerequisite edge. Exactly the DECLARED_CONFLICT_-
# SERIALISATIONS idea, kept as a SEPARATE table because that one is keyed by
# batch and asserted against the makespan table's rows: an entry there that no
# makespan row uses is reported stale, so the overview's extra lanes cannot be
# folded into it without breaking that check.
#
# Each entry names a set of tasks that conflict with one another PAIRWISE
# (asserted below, not assumed) and that this authored block therefore runs one
# after another. ``conflicts_with`` is an UNDIRECTED MUTEX -- it says two tasks
# cannot run at once, never which goes first -- so writing them in an order is a
# scheduling decision a human made, and adding an entry here is the deliberate,
# reviewable act of recording that.
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


_OV_BATCH_RE = re.compile(r"^Batch ([0-9]+):")
_OV_DEPLOY_PREFIX = "Deployment track"
# ``Track C' (parallel after 4.7)``. The prime is a SCHEDULING LANE inside Track
# C (decision D19's storage-barrel fan-out), not a `###` heading of its own --
# it is the reason Batch 4 is on DECLARED_TRACK_COUNT_DIVERGENCES, so it is
# parsed and then folded back onto its base letter rather than failing.
_OV_LABEL_RE = re.compile(
    r"^(?P<label>Track (?P<letter>[A-Z])(?P<prime>')?|Gate)"
    r"(?:\s+\((?P<qual>[^)]*)\))?$"
)
_OV_ANNOTATION_RE = re.compile(r"^\[(.*)\]$")
# "after 4.7", "opens after 6.5", "needs 0.2". ``needs`` is included because the
# Deployment track states one of its two edges that way -- "(after I.1, needs
# 0.2)" -- and both halves are prerequisite claims about the same task.
_OV_AFTER_RE = re.compile(rf"\b(?:after|needs)\s+({TASK_ID_RE})\b")
# ``7.7-7.10`` / ``4.8-4.11``: range notation used NOWHERE else in this block's
# grammar, and only ever inside prose lines. Matched so it can be named as
# UNPARSED rather than silently mined for its two endpoints.
_OV_RANGE_RE = re.compile(rf"({TASK_ID_RE})\s*[–—-]\s*({TASK_ID_RE})")
_OV_ID_SCAN_RE = re.compile(rf"(?<![\w.]){TASK_ID_RE}(?![\w.])")
_OV_GAP_RE = re.compile(r"\s{2,}")


def overview_block(plan_text: str):
    """``(lines of the fenced block, 1-based line number of its first line)``.

    ``(None, None)`` when the section or its fence is absent -- the caller
    reports that, rather than this raising into the middle of a check run.
    """
    lines = plan_text.split("\n")
    try:
        h = find_block(heading_blocks(lines), OVERVIEW_HEADING)
    except KeyError:
        return None, None
    body = lines[h["i"] + 1: h["end"]]
    start = next((i for i, l in enumerate(body) if l.startswith("```")), None)
    if start is None:
        return None, None
    end = next((i for i in range(start + 1, len(body)) if body[i].startswith("```")),
               None)
    if end is None:
        return None, None
    return body[start + 1: end], h["i"] + 1 + start + 2


def _ov_parse_chain(cell: str):
    """``(steps, per-id after-claims, offending token)`` for one lane's chain.

    A chain is ``->``-separated STEPS; a step is a comma-separated group of bare
    ids that run in parallel, optionally carrying its own ``(after X)``
    parenthetical. ``4.8, 4.9, 4.10, 4.11 -> 4.12`` is therefore two steps, and
    the arrow is read as joining EVERY member of the group to 4.12 -- the same
    all-pairs reading ``check_makespan_table`` gives ``{a ∥ b} → c``.

    Anything outside that shape returns ``(None, None, token)`` so the caller
    can report it UNPARSED instead of guessing at it.
    """
    steps: list[list[str]] = []
    claims: dict[str, list[str]] = defaultdict(list)
    for token in cell.split("->"):
        token = token.strip()
        if not token:
            return None, None, cell.strip()
        after = _OV_AFTER_RE.findall(token)
        ids: list[str] = []
        for part in PAREN_RE.sub(" ", token).split(","):
            part = part.strip()
            if not part:
                continue
            if not BARE_ID_RE.match(part):
                return None, None, part
            ids.append(part)
        if not ids:
            return None, None, token
        for tid in ids:
            claims[tid].extend(after)
        steps.append(ids)
    return steps, dict(claims), None


def parse_overview(plan_text: str):
    """``(sections, units, prose, problems)`` for the authored overview block.

    ``sections`` is ``[(batch key, header line, lineno)]`` in block order,
    ``units`` the parsed lanes, ``prose`` the ``>>>`` and ``--- ... ---`` lines
    (which are authored judgment and are NOT parsed as schedule), and
    ``problems`` the lines whose shape is outside the grammar.

    A lane line is split on runs of two or more spaces: a trailing
    ``[annotation]`` field, and one or more ``label: chain`` units -- Batch 10
    writes its three tracks on one line, which is part of the grammar, not a
    special case.
    """
    block, base = overview_block(plan_text)
    if block is None:
        return None, None, None, [
            f"the fenced block under {OVERVIEW_HEADING!r} was not found; the "
            f"whole overview check could not run"
        ]

    sections: list[tuple[str, str, int]] = []
    units: list[OverviewUnit] = []
    prose: list[tuple[str, str, int]] = []
    problems: list[str] = []
    key: str | None = None
    pending: list[str] = []   # after-claims from a section header

    for n, raw in enumerate(block):
        lineno = base + n
        if not raw.strip():
            continue

        if not raw.startswith(" "):
            text = raw.strip()
            if m := _OV_BATCH_RE.match(text):
                key = m.group(1)
            elif text.startswith(_OV_DEPLOY_PREFIX):
                key = "deployment"
            else:
                problems.append(
                    f"line {lineno}: {text!r} starts a section but is neither "
                    f"'Batch N: ...' nor '{_OV_DEPLOY_PREFIX} ...'"
                )
                key = None
                continue
            sections.append((key, text, lineno))
            pending = list(_OV_AFTER_RE.findall(text))
            continue

        text = raw.strip()
        if key is None:
            problems.append(f"line {lineno}: {text!r} sits under no section header")
            continue
        if text.startswith(">>>") or text.startswith("---"):
            prose.append((key, text, lineno))
            continue

        fields = [f for f in _OV_GAP_RE.split(text) if f]
        annotation = None
        if fields and (m := _OV_ANNOTATION_RE.match(fields[-1])):
            annotation = m.group(1)
            fields = fields[:-1]
        if not fields:
            problems.append(
                f"line {lineno}: {text!r} carries an annotation but no lane"
            )
            continue

        for field in fields:
            label = letter = qualifier = None
            head, sep, chain = field.partition(":")
            if sep and (lm := _OV_LABEL_RE.match(head.strip())):
                label = lm.group("label")
                letter = lm.group("letter")
                qualifier = lm.group("qual")
            elif sep:
                problems.append(
                    f"line {lineno}: lane label {head.strip()!r} is UNPARSED -- "
                    f"outside the 'Track X', \"Track X'\" and 'Gate' grammar, "
                    f"with an optional '(qualifier)'"
                )
                continue
            else:
                chain = field

            steps, per_id, offending = _ov_parse_chain(chain)
            if steps is None:
                problems.append(
                    f"line {lineno}: lane {field.strip()!r} is UNPARSED at "
                    f"{offending!r} -- outside the 'a, b -> c' bare-id grammar; "
                    f"its ids, edges and claims are not checked"
                )
                continue

            claims: list[tuple[str, str, str]] = []
            for tid, sources in per_id.items():
                for src in sources:
                    claims.append((tid, src, f"{tid}'s own parenthetical"))
            line_after: list[str] = []
            where: list[str] = []
            if qualifier and (found := _OV_AFTER_RE.findall(qualifier)):
                line_after += found
                where.append(f"the lane qualifier ({qualifier})")
            if annotation and (found := _OV_AFTER_RE.findall(annotation)):
                line_after += found
                where.append(f"the annotation [{annotation}]")
            if pending:
                line_after += pending
                where.append("the section header")
                pending = []
            for src in line_after:
                for tid in steps[0]:
                    claims.append((tid, src, " and ".join(where)))

            units.append(OverviewUnit(
                batch=key,
                label=label,
                letter=letter,
                qualifier=qualifier,
                annotation=annotation,
                steps=tuple(tuple(s) for s in steps),
                claims=tuple(claims),
                lineno=lineno,
                text=field.strip(),
            ))

    return sections, units, prose, problems


def _ov_norm_title(text: str) -> str:
    """Parentheticals dropped, whitespace collapsed, case folded away."""
    return re.sub(r"\s+", " ", PAREN_RE.sub(" ", text)).strip().casefold()


def _ov_section_headings(plan_text: str) -> dict[str, str]:
    """``batch key -> the ``##`` heading text`` (without the leading ``## ``)."""
    out: dict[str, str] = {}
    for line in plan_text.split("\n"):
        if m := BATCH_HEADING_RE.match(line):
            out[m.group(1)] = line[3:]
        elif line.startswith("## Deployment Track"):
            out["deployment"] = line[3:]
    return out


def check_batch_overview(records, plan_text: str):
    """``(findings, info)`` -- the authored Batch Execution Overview vs the corpus.

    Findings are defects; info is context, including everything the grammar
    refused to parse.

     1. the allowlist in DECLARED_OVERVIEW_SERIALISATIONS names real tasks that
        really do conflict pairwise, and every entry is still used by some lane;
     2. every section is a batch the corpus has, and every batch the corpus has
        gets a section -- both directions;
     3. each section's title agrees with its own ``##`` heading once
        parentheticals and case are normalised away, or is declared in
        DECLARED_OVERVIEW_TITLE_DIVERGENCES with both strings;
     4. every task id the lanes name exists;
     5. every task is named under the batch its frontmatter puts it in;
     6. per batch, the roster of each track letter is EXACTLY the set of that
        batch's tasks carrying that letter -- both directions, so a task the
        overview forgot fails just as loudly as one it invented;
     7. a lane with a label but no letter (``Gate``) names tasks whose
        ``track_heading`` starts with that label; an unlabelled lane (the
        Deployment track) names tasks whose ``track_heading`` is null;
     8. every ``->`` edge is a prerequisite edge, or joins two members of a
        declared conflict serialisation that genuinely conflict;
     9. every "after X" / "needs X" claim -- written in a lane qualifier, an
        annotation, a per-id parenthetical, or the Deployment section header --
        is a real prerequisite edge;
    10. an ``[annotation]`` whose leading word is one of the track scopes the
        corpus uses is the ``track_scope`` of every task on that lane.

    NOT asserted, and said out loud in the info lines rather than left for a
    reader to find:

    * (10) is the honest limit of the annotation check. The tag is free-form
      authored prose: some are exactly a scope (``[server]``), some are a scope
      plus description (``[extension storage core]``, ``[repo CI]``), some carry
      a dependency (``[server window, after 3.2]``, checked by (9)), and some
      name neither a scope nor a package (``[harness]``, ``[manual acceptance in
      a real browser]``, ``[infra terraform, infra AGENTS.md]``). Only the
      leading-token form can be decided; the rest are listed as UNCHECKED. It is
      deliberately NOT checked against ``package``: ``[server routes and main]``
      covers tasks packaged at ``server/app/routes`` and ``server/app``, and any
      rule loose enough to accept that would accept almost anything.
    * The ``>>>`` and ``--- ... ---`` lines are authored judgment. Their ids are
      asserted to exist; their claims -- what a checkpoint buys, what a failed
      spike blocks, which lanes are parallel and why -- are not.
    * The block orders the Deployment track last while the document renders it
      between Batch 6 and Batch 7. That is presentation, so section ORDER is not
      asserted, only the section SET.
    * Per-track rosters are compared by LETTER, not by lane, because Batch 4
      splits Track C across ``Track C`` and ``Track C'``.
    """
    findings: list[str] = []
    info: list[str] = []
    by = {r["fm"]["id"]: r["fm"] for r in records}
    conflicts = {tid: set(fm["conflicts_with"]) for tid, fm in by.items()}
    scopes = {fm["track_scope"] for fm in by.values() if fm.get("track_scope")}

    # --- (1) the allowlist describes something real -----------------------
    for name, entry in sorted(DECLARED_OVERVIEW_SERIALISATIONS.items()):
        missing = sorted(entry.ids - set(by), key=id_key)
        if missing:
            findings.append(
                f"declared overview serialisation {name!r} names {missing}, which "
                f"the corpus does not have"
            )
            continue
        non_clique = [
            f"{a} ↮ {b}"
            for a in sorted(entry.ids, key=id_key)
            for b in sorted(entry.ids, key=id_key)
            if a != b and b not in conflicts[a]
        ]
        if non_clique:
            findings.append(
                f"declared overview serialisation {name!r} is not a mutual-conflict "
                f"set: {non_clique} -- the reason ({entry.reason}) no longer "
                f"describes the corpus"
            )

    sections, units, prose, problems = parse_overview(plan_text)
    findings.extend(problems)
    if sections is None:
        return findings, info

    # --- (2) sections vs batches ------------------------------------------
    section_keys = [k for k, _, _ in sections]
    dupes = sorted({k for k in section_keys if section_keys.count(k) > 1},
                   key=lambda k: (k == "deployment", k.zfill(3)))
    if dupes:
        findings.append(
            "the overview opens more than one section for "
            + ", ".join(batch_label(k) for k in dupes)
        )
    corpus_keys = set(batch_order(records))
    for key in sorted(set(section_keys) - corpus_keys,
                      key=lambda k: (k == "deployment", k.zfill(3))):
        findings.append(
            f"the overview has a section for {batch_label(key)}, which the corpus "
            f"has no tasks in"
        )
    for key in sorted(corpus_keys - set(section_keys),
                      key=lambda k: (k == "deployment", k.zfill(3))):
        findings.append(
            f"{batch_label(key)} has tasks in the corpus but no section in the "
            f"overview -- every task in it is silently missing from the schedule"
        )

    # --- (3) section titles ------------------------------------------------
    headings = _ov_section_headings(plan_text)
    declared_titles = DECLARED_OVERVIEW_TITLE_DIVERGENCES
    observed_titles: set[str] = set()
    for key, text, lineno in sections:
        heading = headings.get(key)
        if heading is None:
            findings.append(
                f"line {lineno}: the overview's {batch_label(key)} section has no "
                f"matching '## ' heading in the document"
            )
            continue
        if _ov_norm_title(text) == _ov_norm_title(heading):
            continue
        observed_titles.add(key)
        entry = declared_titles.get(key)
        if entry is None:
            findings.append(
                f"line {lineno}: the overview calls it {text!r}, the heading calls "
                f"it {heading!r}. Titles are compared with parentheticals dropped "
                f"and case folded, so this is a real wording difference -- fix one, "
                f"or declare it in DECLARED_OVERVIEW_TITLE_DIVERGENCES"
            )
        elif (entry.overview, entry.heading) != (text, heading):
            findings.append(
                f"line {lineno}: {batch_label(key)}'s title divergence is declared "
                f"as {entry.overview!r} vs {entry.heading!r}, but the document now "
                f"has {text!r} vs {heading!r} -- the stated reason "
                f"({entry.reason}) has to be revisited"
            )
    for key in sorted(set(declared_titles) - observed_titles,
                      key=lambda k: (k == "deployment", k.zfill(3))):
        findings.append(
            f"{batch_label(key)}: declared title divergence "
            f"({declared_titles[key].overview!r} vs "
            f"{declared_titles[key].heading!r}) no longer diverges -- the entry is "
            f"stale, delete it"
        )

    # --- (4) ids exist, (5) under the right batch --------------------------
    named: list[tuple[OverviewUnit, str]] = [
        (u, tid) for u in units for step in u.steps for tid in step
    ]
    unknown = sorted({tid for _, tid in named if tid not in by}, key=id_key)
    if unknown:
        findings.append(
            f"the overview names {unknown}, which the corpus does not have"
        )
    real = [(u, tid) for u, tid in named if tid in by]

    wrong_batch = sorted(
        {(u.batch, tid, str(by[tid]["batch"])) for u, tid in real
         if str(by[tid]["batch"]) != u.batch},
        key=lambda t: id_key(t[1]),
    )
    for section_key, tid, actual in wrong_batch:
        findings.append(
            f"{tid} is scheduled under {batch_label(section_key)} in the overview, "
            f"but its frontmatter puts it in {batch_label(actual)}"
        )

    # --- (6) per-batch, per-letter rosters ---------------------------------
    # A primed lane (``Track C'``) is folded onto its base letter: it is a
    # scheduling lane inside Track C, not a `###` heading, which is exactly what
    # DECLARED_TRACK_COUNT_DIVERGENCES["4"] records.
    overview_roster: dict[str, dict[str | None, set[str]]] = defaultdict(
        lambda: defaultdict(set))
    for u, tid in real:
        overview_roster[u.batch][u.letter].add(tid)
    corpus_roster: dict[str, dict[str | None, set[str]]] = defaultdict(
        lambda: defaultdict(set))
    for r in records:
        fm = r["fm"]
        th = fm["track_heading"]
        corpus_roster[str(fm["batch"])][track_letter(th) if th else None].add(fm["id"])

    def _lane(letter):
        return f"Track {letter}" if letter else "the unlettered lane"

    for key in sorted(corpus_keys | set(overview_roster),
                      key=lambda k: (k == "deployment", k.zfill(3))):
        seen, want = overview_roster.get(key, {}), corpus_roster.get(key, {})
        for letter in sorted(set(seen) | set(want), key=lambda l: l or "￿"):
            got, expect = seen.get(letter, set()), want.get(letter, set())
            if got == expect:
                continue
            extra = sorted(got - expect, key=id_key)
            absent = sorted(expect - got, key=id_key)
            findings.append(
                f"{batch_label(key)} / {_lane(letter)}: the overview schedules "
                f"{sorted(got, key=id_key) or '[]'}, the corpus puts "
                f"{sorted(expect, key=id_key) or '[]'} there"
                + (f" -- named but not a member: {extra}" if extra else "")
                + (f" -- MISSING from the overview: {absent}" if absent else "")
            )

    # --- (7) labelled-but-unlettered and unlabelled lanes ------------------
    for u, tid in real:
        th = by[tid]["track_heading"]
        if u.letter is not None:
            continue
        if u.label is None and th is not None:
            findings.append(
                f"{tid} is on an unlabelled lane (line {u.lineno}), but its "
                f"track_heading is {th!r}, not null"
            )
        elif u.label is not None and not (th or "").startswith(u.label):
            findings.append(
                f"{tid} is on the {u.label!r} lane (line {u.lineno}), but its "
                f"track_heading is {th or 'null'!r}"
            )

    # --- (8) every arrow ---------------------------------------------------
    n_edges = 0
    used: set[str] = set()
    for u in units:
        for left, right in zip(u.steps, u.steps[1:]):
            for a in left:
                for b in right:
                    n_edges += 1
                    if a not in by or b not in by:
                        continue
                    if a in by[b]["prerequisites"]:
                        continue
                    hit = next(
                        (name for name, e in DECLARED_OVERVIEW_SERIALISATIONS.items()
                         if {a, b} <= e.ids and b in conflicts[a]),
                        None,
                    )
                    if hit:
                        used.add(hit)
                        continue
                    findings.append(
                        f"line {u.lineno} ({u.text!r}): `{a} -> {b}` is neither a "
                        f"prerequisite edge ({b} requires "
                        f"{by[b]['prerequisites'] or 'nothing'}) nor a declared "
                        f"conflict-driven serialisation"
                    )
    for name in sorted(set(DECLARED_OVERVIEW_SERIALISATIONS) - used):
        findings.append(
            f"declared overview serialisation {name!r} "
            f"({sorted(DECLARED_OVERVIEW_SERIALISATIONS[name].ids, key=id_key)}) is "
            f"no longer used by any lane -- the entry is stale, delete it"
        )

    # --- (9) every "after X" / "needs X" claim -----------------------------
    n_claims = 0
    for u in units:
        for tid, src, where in u.claims:
            n_claims += 1
            if tid not in by:
                continue
            if src not in by:
                findings.append(
                    f"line {u.lineno} ({u.text!r}): {where} names {src}, which the "
                    f"corpus does not have"
                )
                continue
            if src not in by[tid]["prerequisites"]:
                findings.append(
                    f"line {u.lineno} ({u.text!r}): {where} says {tid} runs after "
                    f"{src}, but {tid} requires "
                    f"{by[tid]['prerequisites'] or 'nothing'}"
                )

    # --- (10) the [annotation] tag against track_scope ---------------------
    n_scope_checked = 0
    unchecked: list[str] = []
    for u in units:
        if not u.annotation:
            continue
        lead = re.split(r"[\s,]+", u.annotation.strip())[0].casefold()
        ids = [tid for step in u.steps for tid in step if tid in by]
        if lead not in scopes:
            unchecked.append(f"line {u.lineno}: [{u.annotation}]")
            continue
        n_scope_checked += 1
        bad = [f"{tid} (track_scope: {by[tid]['track_scope'] or 'null'})"
               for tid in ids if by[tid].get("track_scope") != lead]
        if bad:
            findings.append(
                f"line {u.lineno} ({u.text!r}): the annotation "
                f"[{u.annotation}] leads with the scope {lead!r}, but "
                + ", ".join(bad)
            )

    # --- prose lines: ids exist, and nothing else --------------------------
    n_prose_ids = 0
    for key, text, lineno in prose:
        masked = text
        for m in _OV_RANGE_RE.finditer(text):
            info.append(
                f"line {lineno} ({batch_label(key)}): UNPARSED at {m.group(0)!r} -- "
                f"range notation, which appears nowhere else in this block's "
                f"grammar. Its endpoints are not expanded and nothing about it is "
                f"asserted. Line: {text!r}"
            )
            masked = masked.replace(m.group(0), " " * len(m.group(0)))
        for m in _OV_ID_SCAN_RE.finditer(masked):
            n_prose_ids += 1
            if m.group(0) not in by:
                findings.append(
                    f"line {lineno}: the prose line names {m.group(0)}, which the "
                    f"corpus does not have. Line: {text!r}"
                )

    # --- context -----------------------------------------------------------
    primed = [f"line {u.lineno} ({u.text.split(':')[0]})" for u in units
              if u.label and u.label.endswith("'")]
    info.append(
        f"{len(sections)} section(s), {len(units)} lane(s), {len(real)} task id(s) "
        f"named, {n_edges} '->' edge(s), {n_claims} 'after'/'needs' claim(s); "
        f"section ORDER is not asserted (the block puts the Deployment track last, "
        f"the document renders it after Batch 6)"
    )
    if primed:
        info.append(
            "primed lane(s) folded onto their base track letter: "
            + ", ".join(primed)
            + " -- a scheduling lane inside its track, not a `###` heading; this is "
              "the divergence DECLARED_TRACK_COUNT_DIVERGENCES['4'] records"
        )
    info.append(
        f"{n_scope_checked} annotation(s) checked against track_scope; "
        f"{len(unchecked)} UNCHECKED because the tag does not lead with one of the "
        f"corpus's scopes ({', '.join(sorted(scopes))}): "
        + ("; ".join(unchecked) if unchecked else "(none)")
        + ". Annotations are free-form authored prose and are NOT checked against "
          "`package`: one tag covers a lane whose tasks sit in several packages"
    )
    info.append(
        f"{len(prose)} '>>>' / '--- ... ---' line(s) are authored judgment: "
        f"{n_prose_ids} task id(s) in them are asserted to EXIST and nothing more. "
        f"What they claim -- what a checkpoint buys, what a failed spike blocks, "
        f"which lanes are parallel and why -- is not asserted, and neither is any "
        f"phrase that is not a task id ('the Batch 9 driving rows')"
    )
    return findings, info


# --------------------------------------------------------------------------
# Conflict annotations: a mutex has to name the thing it is a mutex over
# --------------------------------------------------------------------------
# ``conflicts_with`` is an UNDIRECTED MUTEX -- "these two cannot be in flight at
# once" -- and it is a different claim from ``prerequisites``, which is a
# DIRECTED EDGE. The distinction is load-bearing everywhere else in this file:
# prerequisites go into the DAG that longest_chain walks, conflicts never do,
# and DECLARED_CONFLICT_SERIALISATIONS exists precisely because writing a mutex
# down in an order is a human scheduling choice rather than a derived fact.
#
# A mutex is only reviewable if it says WHAT the two tasks collide over. "Tasks
# 8.4, 8.5 (same popup shell and route table)" cannot be checked against
# anything, cannot be refuted, and cannot be retired when the collision goes
# away -- it will outlive the file it was about. "Tasks 3.1, 3.2, 3.3
# (`app/models/__init__.py`)" can be: the path is a claim a reader can open.
#
# So: a task with a non-empty ``conflicts_with`` must name at least one path in
# backticks in its annotation. A path is a backticked span with a directory
# separator (`app/models/__init__.py`, `extension/entrypoints/popup/`) or a
# file extension (`wxt.config.ts`). A backticked identifier -- `ActionKind`,
# `ReadOnlyStore` -- is not a path and does not satisfy this.
#
# What this DOESN'T check: that the path exists on disk (most of this plan's
# files are not written yet -- that is the point of a plan), that both sides of
# a mutex name the SAME path, or that the path is the right one. Those need a
# built tree or a human. This check draws the one line a checker can hold: an
# unreviewable mutex is a defect.

# A backticked span counts as a path if it has a separator or an extension.
_CONFLICT_TICKS_RE = re.compile(r"`([^`]+)`")
_CONFLICT_PATH_RE = re.compile(r"/|^[\w.\-]+\.[A-Za-z0-9]{1,5}$")
_CONFLICT_BODY_RE = re.compile(r"^\*\*Conflicts with:\*\*\s*(.*)$", re.MULTILINE)


class UnreviewableConflict(NamedTuple):
    """A conflict annotation knowingly left without a path, and why."""
    raw: str        # the annotation as it stands, verbatim
    reason: str     # why no path could be named
    resolve: str    # what someone would have to establish to fix it


# AUTHORED, NOT DERIVED. Every entry is a mutex nobody could name a shared file
# for. Each one is a real gap, written down instead of papered over, and each
# fails as stale the moment the annotation gains a path -- the allowlist is not
# a graveyard.
DECLARED_UNREVIEWABLE_CONFLICTS: dict[str, UnreviewableConflict] = {}


def check_conflict_annotations(records):
    """``(findings, info)`` -- every conflict mutex names what it collides over.

     1. a task with a non-empty ``conflicts_with`` names at least one path in
        backticks in ``conflicts_with_raw``, or is declared unreviewable;
     2. a declared entry still matches the annotation on disk verbatim, still
        names a task that still has conflicts, and still fails to name a path --
        an entry whose annotation has gained one is stale and has to go;
     3. the body's ``**Conflicts with:**`` line and the ``conflicts_with_raw``
        frontmatter agree, so an annotation cannot be fixed in one and left
        stale in the other.

    NOT checked: that the path exists (this is a plan; most of these files are
    not written yet), that both sides of a mutex name the same path, or that
    the path is the right one.
    """
    findings: list[str] = []
    info: list[str] = []
    by = {r["fm"]["id"]: r for r in records}
    named: set[str] = set()
    n_paths = 0

    for tid in sorted(by, key=id_key):
        rec = by[tid]
        fm = rec["fm"]
        raw = fm["conflicts_with_raw"] or ""

        # (3) frontmatter and body must not drift apart.
        m = _CONFLICT_BODY_RE.search(rec["body"])
        if m is None:
            findings.append(
                f"{tid} ({rec['path'].name}): the body has no "
                f"'**Conflicts with:**' line, but the frontmatter carries "
                f"conflicts_with_raw: {raw!r}"
                if raw else
                f"{tid} ({rec['path'].name}): the body has no "
                f"'**Conflicts with:**' line"
            )
        elif m.group(1).strip() != raw.strip():
            findings.append(
                f"{tid} ({rec['path'].name}): the body says "
                f"'**Conflicts with:** {m.group(1).strip()}' but the frontmatter "
                f"says conflicts_with_raw: {raw!r} -- the two have drifted, and "
                f"the rendered document takes the frontmatter"
            )

        if not fm["conflicts_with"]:
            if tid in DECLARED_UNREVIEWABLE_CONFLICTS:
                findings.append(
                    f"{tid} is in DECLARED_UNREVIEWABLE_CONFLICTS but has no "
                    f"conflicts at all any more -- the entry is stale, delete it"
                )
                named.add(tid)
            continue

        paths = [t for t in _CONFLICT_TICKS_RE.findall(raw)
                 if _CONFLICT_PATH_RE.search(t.strip())]
        entry = DECLARED_UNREVIEWABLE_CONFLICTS.get(tid)
        if entry is not None:
            named.add(tid)
            if paths:
                findings.append(
                    f"{tid} is declared unreviewable but its annotation now names "
                    f"{paths} -- the entry is stale, delete it"
                )
            elif entry.raw != raw:
                findings.append(
                    f"{tid}: the declared unreviewable annotation was "
                    f"{entry.raw!r}, the file now has {raw!r}. It still names no "
                    f"path, but the reason on record ({entry.reason}) was written "
                    f"about the old wording -- re-check it and update the entry"
                )
            continue
        n_paths += len(paths)
        if not paths:
            ticked = _CONFLICT_TICKS_RE.findall(raw)
            findings.append(
                f"{tid} ({rec['path'].name}) conflicts with "
                f"{sorted(fm['conflicts_with'], key=id_key)}, but its annotation "
                f"{raw!r} names no path. A conflict is an undirected MUTEX: it "
                f"says these tasks cannot be in flight together, and it is only "
                f"reviewable if it says what they collide over. Name the shared "
                f"file or directory in backticks"
                + (f" -- {ticked} is/are backticked but not a path (no '/' and no "
                   f"extension)" if ticked else "")
            )

    for tid in sorted(set(DECLARED_UNREVIEWABLE_CONFLICTS) - named, key=id_key):
        findings.append(
            f"DECLARED_UNREVIEWABLE_CONFLICTS names {tid}, which the corpus does "
            f"not have -- the entry is stale, delete it"
        )

    n_conf = sum(1 for r in records if r["fm"]["conflicts_with"])
    n_unreviewable = len(DECLARED_UNREVIEWABLE_CONFLICTS)
    # The colon exists to introduce the list. With an empty allowlist there is
    # nothing to introduce, so both go, and the count still reads as a sentence.
    declared = "; ".join(f"{tid} ({DECLARED_UNREVIEWABLE_CONFLICTS[tid].raw!r})"
                         for tid in sorted(DECLARED_UNREVIEWABLE_CONFLICTS, key=id_key))
    info.append(
        f"{n_conf} task(s) declare a conflict; "
        f"{n_conf - n_unreviewable} name a path "
        f"({n_paths} backticked path(s) in all), "
        f"{n_unreviewable} are declared unreviewable"
        + (f": {declared}" if declared else "")
    )
    info.append(
        "a path is a backticked span with a '/' or a file extension; an "
        "identifier in backticks is not one. NOT checked: that the path exists "
        "(most of this plan's files are not written yet), that both sides of a "
        "mutex name the same path, or that the path is the right one"
    )
    return findings, info
