"""The task corpus: parse the plan into Tasks, and read them back from disk.

Used by ``split-plan.py`` (plan -> per-task files) and ``build-plan-index.py``
(per-task files -> regenerated ``plan/boomerang-plan.md``).

Two invariants make that round trip exact: a task body is copied VERBATIM into
its task file, so the only difference is the additive YAML frontmatter; and
frontmatter scalars are emitted via ``json.dumps``, so the block is valid YAML
that ``json.loads`` reads back without a YAML dependency.

This module is also the IMPORT SURFACE both scripts use. The pieces live next
door -- ``config`` (paths, tokens, patterns), ``models`` (Task and the record
types), ``declared`` (the authored allowlists), ``document`` (headings, tables,
named blocks), ``graph`` (the prerequisite DAG) and ``checks`` (the five
cross-checks) -- and everything either script needs is re-exported here, so a
consumer keeps one import and the split stays an implementation detail.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from checks import (
    CHAIN_LENGTH_RE,
    CHAIN_TIE_RE,
    check_batch_overview,
    check_conflict_annotations,
    check_makespan_table,
    check_restated_quantities,
    check_server_chain_sentence,
    classify_track_count_divergences,
    derived_quantities,
    makespan_slot_total,
    parse_makespan_cell,
    parse_overview,
    parse_server_chain_sentence,
    parse_stated,
    plan_summary_track_counts,
    readable_pattern,
    rendered_dependency_floor,
    restatement_tolerance,
    track_count_divergences,
)
from config import (
    ARROW,
    BARE_ID_RE,
    BASELINE_REF,
    BATCH_HEADING_RE,
    CONCLUSION_RE,
    CRITICAL_PATH_HEADING,
    FLOOR_HEADING,
    FLOOR_LENGTH_RE,
    GATE_TASK_IDS,
    HEADING_RE,
    INTEGRATION_TASK_IDS,
    LIST_ITEM_RE,
    MAKESPAN_HEADING,
    METADATA_FIELDS,
    NUM_PATTERN,
    NUMBER_WORDS,
    OVERVIEW_HEADING,
    PARALLEL,
    PAREN_RE,
    PLAN_PATH,
    PROGRESS_PREFIX,
    RATIO_PATTERN,
    REPO_ROOT,
    REQ_HEADING_RE,
    REQ_RE,
    REQUIREMENTS_DOC,
    SECTION_RE,
    SERVER_SCOPE,
    SORT_LAST,
    TASK_HEADING_RE,
    TASK_ID_RE,
    TASKS_DIR,
    THREE_THINGS_HEADING,
    TRACK_HEADING_RE,
    TRACK_LETTER_RE,
    english_number,
    parse_count,
)
from declared import (
    DECLARED_CONFLICT_SERIALISATIONS,
    DECLARED_GAPS,
    DECLARED_OVERVIEW_SERIALISATIONS,
    DECLARED_OVERVIEW_TITLE_DIVERGENCES,
    DECLARED_RESTATEMENTS,
    DECLARED_TRACK_COUNT_DIVERGENCES,
    DECLARED_UNREVIEWABLE_CONFLICTS,
)
from document import (
    batch_label,
    batch_order,
    critical_path_lines,
    find_block,
    heading_blocks,
    makespan_table,
    overview_block,
    parse_table,
    read_source,
    split_table,
    track_letter,
)
from graph import batch_subset, id_key, longest_chain
from models import (
    Chain,
    Claim,
    ConflictSerialisation,
    DeclaredDivergence,
    DeclaredTitleDivergence,
    DerivedQuantity,
    OverviewUnit,
    Restatement,
    Task,
    UnreviewableConflict,
    pad_id,
    slugify,
)

# Everything above is part of the surface, used here or not; listing it keeps a
# linter from reading the re-exports as dead imports.
__all__ = [
    # config
    "ARROW", "BARE_ID_RE", "BASELINE_REF", "BATCH_HEADING_RE", "CONCLUSION_RE",
    "CRITICAL_PATH_HEADING", "FLOOR_HEADING", "FLOOR_LENGTH_RE", "GATE_TASK_IDS",
    "HEADING_RE", "INTEGRATION_TASK_IDS", "LIST_ITEM_RE", "MAKESPAN_HEADING",
    "METADATA_FIELDS", "NUM_PATTERN", "NUMBER_WORDS", "OVERVIEW_HEADING",
    "PARALLEL", "PAREN_RE", "PLAN_PATH", "PROGRESS_PREFIX", "RATIO_PATTERN",
    "REPO_ROOT", "REQ_HEADING_RE", "REQ_RE", "REQUIREMENTS_DOC", "SECTION_RE",
    "SERVER_SCOPE", "SORT_LAST", "TASK_HEADING_RE", "TASK_ID_RE", "TASKS_DIR",
    "THREE_THINGS_HEADING", "TRACK_HEADING_RE", "TRACK_LETTER_RE",
    "english_number", "parse_count",
    # models
    "Chain", "Claim", "ConflictSerialisation", "DeclaredDivergence",
    "DeclaredTitleDivergence", "DerivedQuantity", "OverviewUnit", "Restatement",
    "Task", "UnreviewableConflict", "pad_id", "slugify",
    # declared
    "DECLARED_CONFLICT_SERIALISATIONS", "DECLARED_GAPS",
    "DECLARED_OVERVIEW_SERIALISATIONS", "DECLARED_OVERVIEW_TITLE_DIVERGENCES",
    "DECLARED_RESTATEMENTS", "DECLARED_TRACK_COUNT_DIVERGENCES",
    "DECLARED_UNREVIEWABLE_CONFLICTS",
    # document
    "batch_label", "batch_order", "critical_path_lines", "find_block",
    "heading_blocks", "makespan_table", "overview_block", "parse_table",
    "read_source", "split_table", "track_letter",
    # graph
    "batch_subset", "id_key", "longest_chain",
    # checks
    "CHAIN_LENGTH_RE", "CHAIN_TIE_RE", "check_batch_overview",
    "check_conflict_annotations", "check_makespan_table",
    "check_restated_quantities", "check_server_chain_sentence",
    "classify_track_count_divergences", "derived_quantities",
    "makespan_slot_total", "parse_makespan_cell", "parse_overview",
    "parse_server_chain_sentence", "parse_stated", "plan_summary_track_counts",
    "readable_pattern", "rendered_dependency_floor", "restatement_tolerance",
    "track_count_divergences",
    # this module
    "canonical_sort_key", "load_tasks_from_files", "parse_id_list", "parse_plan",
    "parse_requirements", "render_frontmatter", "requirement_ids_from_doc",
    "split_frontmatter",
]


def requirement_ids_from_doc(path: Path = REQUIREMENTS_DOC) -> set[str]:
    """Every requirement id the requirements document declares as a heading.

    A requirement exists because the design document gives it a heading, not
    because some task happened to cite it: that is the universe coverage is
    taken against.
    """
    if not path.exists():
        return set()
    return {
        m.group(1).rstrip(".")
        for line in path.read_text().split("\n")
        if (m := REQ_HEADING_RE.match(line))
    }


def _expand(lo: str, hi: str) -> list[str]:
    """Expand ``6.1``-``6.3`` to 6.1, 6.2, 6.3. Refuses cross-major ranges."""
    lo_major, lo_minor = lo.split(".", 1)
    hi_major, hi_minor = hi.split(".", 1)
    if lo_major != hi_major or not lo_minor.isdigit() or not hi_minor.isdigit():
        return [lo, hi]
    return [f"{lo_major}.{n}" for n in range(int(lo_minor), int(hi_minor) + 1)]


def parse_id_list(value: str) -> tuple[list[str], list[str]]:
    """Extract task ids from a dependency line value.

    Returns ``(ids, unparsed_fragments)``. Prose fragments ("all server tasks")
    are returned unparsed rather than mined for numbers, and parentheticals are
    dropped before splitting, because mining either would invent dependencies.
    The full line survives verbatim in the body and in the ``*_raw`` key.
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

    Returns ``(requirements, sections, is_prose_only)``. A line opening with an
    em dash declares that the task covers NO requirement -- the ids it names are
    context -- so mining them would add spike and harness tasks to traceability
    rows they provide no evidence for.
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

