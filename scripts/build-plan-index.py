#!/usr/bin/env python3
"""Regenerate plan/boomerang-plan.md as an index over plan/tasks/**.

    scripts/build-plan-index.py                 # regenerate the index
    scripts/build-plan-index.py --check-only    # cross-check tables, write nothing

Authored prose is carried through VERBATIM from a prose source (by default the
current index, which retains every preserved section, so the build is
idempotent and re-runnable). Three things are DERIVED from task frontmatter:

  * the Task Status Tracker table
  * the Requirements Traceability matrix
  * the per-track task lists under each Track heading
  * a small derived-facts table in the Parallelization Summary

Every derived table is cross-checked against the hand-written table in the
baseline commit; disagreements are reported, never silently resolved.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_lib import (  # noqa: E402
    BASELINE_REF,
    DECLARED_GAPS,
    PLAN_PATH,
    TASKS_DIR,
    HEADING_RE,
    TASK_HEADING_RE,
    load_tasks_from_files,
    parse_id_list,
    read_source,
    requirement_ids_from_doc,
)

# ``DECLARED_GAPS`` -- the requirements the plan declares as deliberate gaps --
# lives in ``plan_lib`` so this renderer and the coverage assertion in
# ``split-plan.py --verify`` cannot disagree about which gaps are sanctioned.

EN = "–"  # en dash, as used by the original tables


# --------------------------------------------------------------------------
# Document structure
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------

def id_key(task_id: str) -> tuple:
    if task_id.startswith("I."):
        return (98, int(task_id.split(".")[1]), "")
    major, minor = task_id.split(".")
    m = re.match(r"^([0-9]+)([a-z]*)$", minor)
    return (int(major), int(m.group(1)), m.group(2))


def compress_ids(ids: list[str]) -> str:
    """['3.1'..'3.10','3.12'..'3.17'] -> '3.1-3.10, 3.12-3.17' (en dashes)."""
    if not ids:
        return "None"
    ordered = sorted(set(ids), key=id_key)
    parts: list[str] = []
    run: list[str] = []

    def flush():
        if not run:
            return
        if len(run) >= 3:
            parts.append(f"{run[0]}{EN}{run[-1]}")
        else:
            parts.extend(run)
        run.clear()

    for tid in ordered:
        if run:
            pk, ck = id_key(run[-1]), id_key(tid)
            if pk[0] == ck[0] and ck[1] == pk[1] + 1 and not pk[2] and not ck[2]:
                run.append(tid)
                continue
            flush()
        run.append(tid)
    flush()
    return ", ".join(parts)


def plain_ids(ids: list[str]) -> str:
    return ", ".join(sorted(set(ids), key=id_key)) if ids else "None"


# --------------------------------------------------------------------------
# Derived tables
# --------------------------------------------------------------------------

def batch_order(records) -> list[str]:
    """Batch keys in document order (0..6, deployment, 7..10)."""
    seen = []
    for r in records:  # records are already in document order
        key = str(r["fm"]["batch"])
        if key not in seen:
            seen.append(key)
    return seen


def tracker_rows(records) -> list[dict]:
    """Tracker order: batch in document order, then numeric task id."""
    order = batch_order(records)
    return sorted(
        records,
        key=lambda r: (order.index(str(r["fm"]["batch"])), id_key(r["fm"]["id"])),
    )


STATUS_MARK = {"not_started": "[ ]", "in_progress": "[~]", "completed": "[x]"}


def build_tracker_table(records) -> list[str]:
    out = [
        "| Task | Description | Prerequisites | Conflicts | Parallel with | Status |",
        "|------|-------------|---------------|-----------|---------------|--------|",
    ]
    for r in tracker_rows(records):
        fm = r["fm"]
        link = f"[{fm['id']}]({fm['batch_dir'] and 'tasks/' + fm['batch_dir'] + '/' + Path(r['path']).name})"
        out.append(
            f"| {link} | {fm['title']} | {plain_ids(fm['prerequisites'])} "
            f"| {plain_ids(fm['conflicts_with'])} | {compress_ids(fm['parallel_with'])} "
            f"| {STATUS_MARK.get(fm['status'], '[ ]')} |"
        )
    return out


def requirement_universe(records, original_rows) -> list[str]:
    reqs: set[str] = set()
    for r in records:
        reqs.update(r["fm"]["requirements_covered"])
    reqs.update(original_rows)
    reqs.update(requirement_ids_from_doc())
    def key(r):
        head, _, rest = r.partition("-")
        nums = re.findall(r"[0-9]+", rest)
        suffix = re.sub(r"[0-9.]", "", rest)
        return (head != "FR", [int(n) for n in nums], suffix)
    return sorted(reqs, key=key)


def build_traceability_table(records, original_rows) -> tuple[list[str], list[str]]:
    by_req_impl = defaultdict(list)
    by_req_int = defaultdict(list)
    for r in records:
        fm = r["fm"]
        for req in fm["requirements_covered"]:
            (by_req_int if fm["kind"] == "integration" else by_req_impl)[req].append(fm["id"])

    out = [
        "| Requirement | Implementation Task(s) | Unit Test Task(s) | Integration Test Task(s) |",
        "|-------------|------------------------|-------------------|--------------------------|",
    ]
    uncovered: list[str] = []
    for req in requirement_universe(records, original_rows):
        impl = sorted(set(by_req_impl.get(req, [])), key=id_key)
        integ = sorted(set(by_req_int.get(req, [])), key=id_key)
        if not impl and not integ:
            uncovered.append(req)
            cell = DECLARED_GAPS.get(req, "**— NO TASK CITES THIS REQUIREMENT**")
            out.append(f"| {req} | {cell} | — | — |")
            continue
        impl_cell = ", ".join(impl) if impl else "—"
        if not impl:
            unit = "—"
        elif len(impl) > 9:
            unit = "in-task (as listed)"
        else:
            unit = f"in-task ({', '.join(impl)})"
        out.append(f"| {req} | {impl_cell} | {unit} | {', '.join(integ) if integ else '—'} |")
    return out, uncovered


def build_plan_summary_table(records, table: list[str]) -> list[str]:
    """Rewrite the Plan Summary's Tasks and Tracks columns from the corpus.

    The Batch label and the Theme cell are authored prose and are carried
    through verbatim; the two count columns are derived, so a task added,
    moved or re-tracked can never leave the summary asserting a stale number.
    The ``Tracks`` cell counts distinct ``###`` track headings owned by that
    batch's tasks -- the same definition the cross-check uses.
    """
    order = batch_order(records)
    out: list[str] = []
    seen_data = 0
    for row in table:
        if re.match(r"^\|[\s:|-]+\|$", row) or seen_data == 0:
            # Header row and separator row: verbatim.
            out.append(row)
            seen_data += not re.match(r"^\|[\s:|-]+\|$", row)
            continue
        cells = row.strip().strip("|").split("|")
        if len(cells) < 4:
            out.append(row)
            continue
        label_cell, tasks_cell, tracks_cell = cells[0], cells[1], cells[2]
        theme_cell = "|".join(cells[3:])
        label = label_cell.strip().strip("*` ")
        if label.lower() == "total":
            tasks_cell = f" **{len(records)}** "
        else:
            key = "deployment" if label == "—" else label
            if key in order:
                rows_b = [r for r in records if str(r["fm"]["batch"]) == key]
                tracks = {r["fm"]["track_heading"] for r in rows_b if r["fm"]["track_heading"]}
                tasks_cell = f" {len(rows_b)} "
                tracks_cell = f" {len(tracks)} "
        out.append(f"|{label_cell}|{tasks_cell}|{tracks_cell}|{theme_cell}|")
    return out


DERIVED_MARKER = "**Derived from the task files.**"


def drop_derived_block(after: list[str]) -> list[str]:
    """Remove a previously generated derived-facts block from a prose tail.

    The block is the ``**Derived from the task files.**`` note plus the table
    that follows it. Leaving it in place would make each rebuild append
    another copy.
    """
    for i, line in enumerate(after):
        if line.startswith(DERIVED_MARKER):
            j = i
            while j < len(after) and not after[j].startswith("|"):
                j += 1
            while j < len(after) and after[j].startswith("|"):
                j += 1
            head = after[:i]
            while head and not head[-1].strip():
                head.pop()
            return head + after[j:]
    return after


def build_derived_facts_table(records) -> list[str]:
    order = batch_order(records)
    out = [
        "| Batch | Tasks | Track headings | Conflict pairs |",
        "|-------|-------|----------------|----------------|",
    ]
    for key in order:
        rows = [r for r in records if str(r["fm"]["batch"]) == key]
        tracks: list[str] = []
        for r in rows:
            th = r["fm"]["track_heading"]
            if th and th not in tracks:
                tracks.append(th)
        pairs = set()
        for r in rows:
            for other in r["fm"]["conflicts_with"]:
                pairs.add(tuple(sorted((r["fm"]["id"], other), key=id_key)))
        label = "Deployment" if key == "deployment" else key
        letters = ", ".join(
            (m.group(1) if (m := re.match(r"^Track ([A-Z]):", t)) else t.split(":")[0])
            for t in tracks
        ) or "—"
        pair_cell = ", ".join(f"{a} ↔ {b}" for a, b in sorted(pairs, key=lambda p: (id_key(p[0]), id_key(p[1])))) or "None"
        out.append(f"| {label} | {len(rows)} | {len(tracks)} ({letters}) | {pair_cell} |")
    return out


# --------------------------------------------------------------------------
# Cross-check against the hand-written baseline tables
# --------------------------------------------------------------------------

def cross_check(records, baseline_text: str) -> list[str]:
    findings: list[str] = []
    lines = baseline_text.split("\n")
    blocks = heading_blocks(lines)
    by_id = {r["fm"]["id"]: r["fm"] for r in records}

    # ---- Task Status Tracker -------------------------------------------
    h = find_block(blocks, "## Task Status Tracker")
    _, table, _ = split_table(lines[h["i"] + 1 : h["end"]])
    rows = parse_table(table)[1:]  # drop header
    seen_ids = set()
    findings.append("### Task Status Tracker")
    n_ok = 0
    for cells in rows:
        tid, desc, pre_cell, con_cell, status_cell = cells[0], cells[1], cells[2], cells[3], cells[4]
        tid = tid.strip("*` ")
        seen_ids.add(tid)
        fm = by_id.get(tid)
        if fm is None:
            findings.append(f"- **{tid}**: tracker row has no matching task file")
            continue
        hand_pre, _ = parse_id_list(pre_cell)
        hand_con, _ = parse_id_list(con_cell)
        gen_pre, gen_con = fm["prerequisites"], fm["conflicts_with"]
        row_ok = True
        if sorted(hand_pre, key=id_key) != sorted(gen_pre, key=id_key):
            findings.append(
                f"- **{tid} prerequisites DIFFER**\n"
                f"    - hand-written tracker: `{pre_cell}`  -> {sorted(hand_pre, key=id_key)}\n"
                f"    - task body (generated): `{fm['prerequisites_raw']}`  -> {sorted(gen_pre, key=id_key)}"
            )
            row_ok = False
        if sorted(hand_con, key=id_key) != sorted(gen_con, key=id_key):
            findings.append(
                f"- **{tid} conflicts DIFFER**\n"
                f"    - hand-written tracker: `{con_cell}`  -> {sorted(hand_con, key=id_key)}\n"
                f"    - task body (generated): `{fm['conflicts_with_raw']}`  -> {sorted(gen_con, key=id_key)}"
            )
            row_ok = False
        if desc.strip() != fm["title"].strip():
            findings.append(
                f"- **{tid} description differs from task title** (wording only)\n"
                f"    - hand-written tracker: `{desc}`\n"
                f"    - task heading:         `{fm['title']}`"
            )
            row_ok = False
        if status_cell.strip() != "[ ]" and fm["status"] == "not_started":
            findings.append(f"- **{tid} status**: tracker `{status_cell}` vs frontmatter `not_started`")
            row_ok = False
        n_ok += row_ok
    for tid in sorted(set(by_id) - seen_ids, key=id_key):
        findings.append(f"- **{tid}**: task exists but has NO row in the hand-written tracker")
    findings.append(f"- {n_ok}/{len(rows)} tracker rows agree with the task bodies in every column")

    # ---- Requirements Traceability -------------------------------------
    findings.append("")
    findings.append("### Requirements Traceability")
    h = find_block(blocks, "## Requirements Traceability")
    _, table, _ = split_table(lines[h["i"] + 1 : h["end"]])
    rows = parse_table(table)[1:]
    hand: dict[str, tuple[list[str], list[str]]] = {}
    for cells in rows:
        req = cells[0].strip("*` ")
        impl, _ = parse_id_list(cells[1])
        integ, _ = parse_id_list(cells[3])
        hand[req] = (impl, integ)

    gen_impl = defaultdict(set)
    gen_int = defaultdict(set)
    for r in records:
        fm = r["fm"]
        for req in fm["requirements_covered"]:
            (gen_int if fm["kind"] == "integration" else gen_impl)[req].add(fm["id"])

    all_reqs = requirement_universe(records, list(hand))
    n_ok = 0
    for req in all_reqs:
        h_impl, h_int = hand.get(req, (None, None))
        g_impl = sorted(gen_impl.get(req, set()), key=id_key)
        g_int = sorted(gen_int.get(req, set()), key=id_key)
        if req not in hand:
            findings.append(
                f"- **{req} MISSING from the hand-written matrix entirely**\n"
                f"    - generated implementation: {g_impl or '(none)'}\n"
                f"    - generated integration:    {g_int or '(none)'}"
            )
            continue
        row_ok = True
        if sorted(h_impl, key=id_key) != g_impl:
            findings.append(
                f"- **{req} implementation tasks DIFFER**\n"
                f"    - hand-written: {sorted(h_impl, key=id_key) or '(none)'}\n"
                f"    - generated:    {g_impl or '(none)'}\n"
                f"    - only in hand-written: {sorted(set(h_impl) - set(g_impl), key=id_key) or '[]'}"
                f" | only in generated: {sorted(set(g_impl) - set(h_impl), key=id_key) or '[]'}"
            )
            row_ok = False
        if sorted(h_int, key=id_key) != g_int:
            findings.append(
                f"- **{req} integration tasks DIFFER**\n"
                f"    - hand-written: {sorted(h_int, key=id_key) or '(none)'}\n"
                f"    - generated:    {g_int or '(none)'}\n"
                f"    - only in hand-written: {sorted(set(h_int) - set(g_int), key=id_key) or '[]'}"
                f" | only in generated: {sorted(set(g_int) - set(h_int), key=id_key) or '[]'}"
            )
            row_ok = False
        n_ok += row_ok
    findings.append(f"- {n_ok}/{len(hand)} traceability rows agree exactly")

    # ---- Plan Summary counts -------------------------------------------
    findings.append("")
    findings.append("### Plan Summary counts")
    h = find_block(blocks, "## Plan Summary")
    _, table, _ = split_table(lines[h["i"] + 1 : h["end"]])
    order = batch_order(records)
    n_ok = 0
    total_rows = 0
    for cells in parse_table(table)[1:]:
        label = cells[0].strip("*` ")
        if label.lower() == "total":
            claimed = int(cells[1].strip("*` "))
            good = claimed == len(records)
            n_ok += good
            total_rows += 1
            if not good:
                findings.append(f"- **Total tasks**: summary says {claimed}, corpus has {len(records)}")
            continue
        key = "deployment" if label == "—" else label
        if key not in order:
            continue
        total_rows += 1
        rows_b = [r for r in records if str(r["fm"]["batch"]) == key]
        tracks = {r["fm"]["track_heading"] for r in rows_b if r["fm"]["track_heading"]}
        c_tasks, c_tracks = int(cells[1].strip("*` ")), int(cells[2].strip("*` "))
        row_ok = True
        if c_tasks != len(rows_b):
            findings.append(f"- **Batch {label} task count**: summary says {c_tasks}, corpus has {len(rows_b)}")
            row_ok = False
        if c_tracks != len(tracks):
            findings.append(
                f"- **Batch {label} track count**: summary says {c_tracks}, "
                f"document has {len(tracks)} `###` track heading(s): "
                f"{sorted(tracks) if tracks else '(none)'}"
            )
            row_ok = False
        n_ok += row_ok
    findings.append(f"- {n_ok}/{total_rows} Plan Summary rows agree with the corpus")
    return findings


# --------------------------------------------------------------------------
# Index rendering
# --------------------------------------------------------------------------

def task_bullet(fm, path: Path) -> str:
    link = f"tasks/{fm['batch_dir']}/{path.name}"
    pre = plain_ids(fm["prerequisites"]).replace("None", "none")
    con = plain_ids(fm["conflicts_with"]).replace("None", "none")
    return (
        f"- [Task {fm['id']}: {fm['title']}]({link})"
        f" — prerequisites: {pre} · conflicts: {con}"
    )


GENERATED_BULLET_RE = re.compile(r"^- \[Task [^\]]*\]\(tasks/")


def drop_generated(lines: list[str]) -> list[str]:
    """Truncate a prose span at the first generated task bullet.

    Generated bullets are re-derived from the task files every build; keeping
    them in the "authored prose" span would duplicate them on a rebuild.
    """
    for i, line in enumerate(lines):
        if GENERATED_BULLET_RE.match(line):
            return lines[:i]
    return lines


def build_index(records, prose_lines: list[str]) -> str:
    blocks = heading_blocks(prose_lines)
    out: list[str] = []

    def verbatim(h):
        out.extend(prose_lines[h["i"] : h["end"]])

    first = find_block(blocks, "## Reading this plan")
    out.extend(prose_lines[: first["i"]])
    for prefix in ("## Reading this plan", "## Package Dependency Graph",
                   "## Batch Execution Overview"):
        verbatim(find_block(blocks, prefix))

    by_batch = defaultdict(list)
    for r in records:
        by_batch[str(r["fm"]["batch"])].append(r)

    # Batch sections, in the order they appear in the prose source.
    for h in blocks:
        if h["level"] != 2:
            continue
        m = re.match(r"^## Batch ([0-9]+)", h["text"])
        is_deploy = h["text"].startswith("## Deployment Track")
        if not m and not is_deploy:
            continue
        key = "deployment" if is_deploy else m.group(1)
        out.append(h["text"])
        # Authored intro prose only. When the prose source is a previously
        # generated index, a batch whose tasks own no Track heading (the
        # deployment track) has its bullet list sitting directly in this span;
        # cut it off so the rebuild regenerates rather than duplicates it.
        out.extend(drop_generated(prose_lines[h["i"] + 1 : h["inner_end"]]))

        rows = by_batch.get(key, [])
        emitted: set[str] = set()
        inner = [b for b in blocks if b["level"] == 3 and h["i"] < b["i"] < h["end"]]

        # Tasks that are their own `### Task I.x` heading (the deployment
        # track) belong to no Track heading. Render them as one bullet list at
        # the position of the first such heading, never as verbatim bodies.
        untracked = [r for r in rows if r["fm"]["track_heading"] is None]
        untracked_done = False

        for b in inner:
            heading_text = b["text"][4:]
            if TASK_HEADING_RE.match(b["text"]):
                if not untracked_done:
                    for r in untracked:
                        out.append(task_bullet(r["fm"], r["path"]))
                        emitted.add(r["fm"]["id"])
                    out.append("")
                    out.append("---")
                    out.append("")
                    untracked_done = True
                continue
            members = [r for r in rows if r["fm"]["track_heading"] == heading_text]
            if members:
                out.append(b["text"])
                out.append("")
                for r in members:
                    out.append(task_bullet(r["fm"], r["path"]))
                    emitted.add(r["fm"]["id"])
                out.append("")
                out.append("---")
                out.append("")
            else:
                # A gate or commit checkpoint that owns no task: verbatim.
                out.extend(prose_lines[b["i"] : b["end"]])

        if untracked and not untracked_done:
            # No `### Task I.x` heading in the prose source -- either the
            # source is already a generated index, or the section never had
            # one. Emit the bullet list right after the intro prose, which is
            # exactly where the heading-driven branch would have put it.
            for r in untracked:
                out.append(task_bullet(r["fm"], r["path"]))
                emitted.add(r["fm"]["id"])
            out.append("")
            out.append("---")
            out.append("")

        orphans = [r for r in rows if r["fm"]["id"] not in emitted]
        if orphans:
            raise SystemExit(f"batch {key}: tasks with no rendered track: "
                             f"{[r['fm']['id'] for r in orphans]}")

    # ---- Task Status Tracker -------------------------------------------
    h = find_block(blocks, "## Task Status Tracker")
    before, _, after = split_table(prose_lines[h["i"] + 1 : h["end"]])
    out.append(h["text"])
    out.extend(before)
    out.extend(build_tracker_table(records))
    done = sum(1 for r in records if r["fm"]["status"] == "completed")
    after = [
        f"**Progress:** {done} / {len(records)} tasks complete"
        if l.startswith("**Progress:**") else l
        for l in after
    ]
    out.extend(after)

    verbatim(find_block(blocks, "## Critical Path"))

    # ---- Parallelization Summary ---------------------------------------
    h = find_block(blocks, "## Parallelization Summary")
    before, table, after = split_table(prose_lines[h["i"] + 1 : h["end"]])
    out.append(h["text"])
    out.extend(before)
    out.extend(table)
    out.append("")
    out.append("**Derived from the task files.** The table above is authored analysis; the counts and")
    out.append("conflict pairs below are generated from task frontmatter and will follow the task files")
    out.append("if either changes.")
    out.append("")
    out.extend(build_derived_facts_table(records))
    out.extend(drop_derived_block(after))

    # ---- Requirements Traceability -------------------------------------
    h = find_block(blocks, "## Requirements Traceability")
    before, table, after = split_table(prose_lines[h["i"] + 1 : h["end"]])
    original_reqs = [c[0].strip("*` ") for c in parse_table(table)[1:]]
    out.append(h["text"])
    out.extend(before)
    gen_table, uncovered = build_traceability_table(records, original_reqs)
    out.extend(gen_table)
    out.extend(after)

    # ---- Plan Summary --------------------------------------------------
    h = find_block(blocks, "## Plan Summary")
    before, table, after = split_table(prose_lines[h["i"] + 1 : h["end"]])
    out.append(h["text"])
    out.extend(before)
    out.extend(build_plan_summary_table(records, table))
    out.extend(after)

    text = "\n".join(out)
    return re.sub(r"\n{4,}", "\n\n\n", text).rstrip("\n") + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prose-source", default=str(PLAN_PATH),
                   help="where authored prose is carried from: a path or git:<ref>")
    p.add_argument("--baseline", default=f"git:{BASELINE_REF}",
                   help="hand-written tables to cross-check against")
    p.add_argument("--tasks-dir", default=str(TASKS_DIR))
    p.add_argument("--out", default=str(PLAN_PATH))
    p.add_argument("--check-only", action="store_true")
    args = p.parse_args()

    records = load_tasks_from_files(Path(args.tasks_dir))
    print(f"loaded {len(records)} task files")

    print()
    print("=" * 72)
    print("CROSS-CHECK: hand-written tables (baseline) vs task-body-derived")
    print("=" * 72)
    for line in cross_check(records, read_source(args.baseline)):
        print(line)
    print("=" * 72)

    prose = read_source(args.prose_source).split("\n")
    text = build_index(records, prose)

    if args.check_only:
        # The index is GENERATED. A hand-edit to any derived table -- the
        # tracker, the traceability matrix, the per-track bullet lists, the
        # Plan Summary counts -- is erased by the next rebuild, so it is a
        # silent divergence between what a reader sees and what the corpus
        # says. Rebuilding into memory and comparing catches that.
        current = Path(args.out).read_text() if Path(args.out).exists() else ""
        stale = current != text
        print()
        print(f"[{'FAIL' if stale else 'PASS'}] {args.out} is up to date with the task files"
              + (" -- rerun scripts/build-plan-index.py" if stale else ""))
        if stale:
            import difflib
            for line in list(difflib.unified_diff(
                    current.split("\n"), text.split("\n"),
                    fromfile="on-disk", tofile="rebuilt", lineterm="", n=1))[:60]:
                print(f"       {line}")
        return 1 if stale else 0

    Path(args.out).write_text(text)
    print(f"\nwrote {args.out} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
