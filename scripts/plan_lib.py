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
from dataclasses import dataclass, field
from pathlib import Path

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
