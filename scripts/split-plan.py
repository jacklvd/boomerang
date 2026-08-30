#!/usr/bin/env python3
"""Split plan/boomerang-plan.md into one file per task under plan/tasks/.

    scripts/split-plan.py --source git:cf7e210      # write plan/tasks/**
    scripts/split-plan.py --verify                  # round-trip + assertions

The split is lossless by construction: each task file is a YAML frontmatter
block followed by the task body copied VERBATIM out of the plan -- heading line
through the blank line before the ``---`` separator. No line is lifted out of
the body, so the only difference between the corpus and the original task spans
is the frontmatter block itself.
"""

from __future__ import annotations

import argparse
import difflib
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_lib import (  # noqa: E402
    BASELINE_REF,
    METADATA_FIELDS,
    TASKS_DIR,
    canonical_sort_key,
    load_tasks_from_files,
    parse_plan,
    read_source,
    render_frontmatter,
)

SEPARATOR = "\n---\n\n"  # the blank line is already the last line of each body


def cmd_split(source: str, tasks_dir: Path) -> int:
    text = read_source(source)
    tasks = parse_plan(text)
    print(f"parsed {len(tasks)} tasks from {source}")

    if tasks_dir.exists():
        shutil.rmtree(tasks_dir)

    names: dict[tuple[str, str], str] = {}
    for task in tasks:
        key = (task.batch_dir, task.filename)
        if key in names:
            raise SystemExit(f"filename collision: {key} ({task.task_id} vs {names[key]})")
        names[key] = task.task_id
        out = tasks_dir / task.batch_dir / task.filename
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_frontmatter(task) + task.body)

    per_dir = Counter(t.batch_dir for t in tasks)
    for d in sorted(per_dir):
        print(f"  {d:12s} {per_dir[d]:3d} tasks")
    print(f"wrote {len(tasks)} files to {tasks_dir}")
    return 0


def _diff(expected: str, actual: str, label: str) -> list[str]:
    if expected == actual:
        return []
    return list(
        difflib.unified_diff(
            expected.split("\n"),
            actual.split("\n"),
            fromfile=f"{label}:baseline",
            tofile=f"{label}:generated",
            lineterm="",
            n=1,
        )
    )


def cmd_verify(baseline: str, tasks_dir: Path) -> int:
    ok = True
    text = read_source(baseline)
    baseline_tasks = parse_plan(text)
    records = load_tasks_from_files(tasks_dir)

    print("=" * 72)
    print("ROUND-TRIP VERIFICATION")
    print("=" * 72)

    # --- count assertions -------------------------------------------------
    n_files = len(records)
    print(f"[{'PASS' if n_files == 91 else 'FAIL'}] task files on disk: {n_files} (expect 91)")
    ok &= n_files == 91
    print(f"[{'PASS' if len(baseline_tasks) == 91 else 'FAIL'}] tasks parsed from {baseline}: "
          f"{len(baseline_tasks)} (expect 91)")
    ok &= len(baseline_tasks) == 91

    corpus = "\n".join(r["body"] for r in records)
    for fieldname in METADATA_FIELDS:
        n = sum(1 for line in corpus.split("\n") if line.startswith(f"**{fieldname}:**"))
        good = n == 91
        ok &= good
        print(f"[{'PASS' if good else 'FAIL'}] **{fieldname}:** appears {n} times (expect 91)")

    # --- round trip, document order --------------------------------------
    by_id = {r["fm"]["id"]: r for r in records}
    missing = [t.task_id for t in baseline_tasks if t.task_id not in by_id]
    if missing:
        print(f"[FAIL] no file for tasks: {missing}")
        return 1

    expected = SEPARATOR.join(t.body for t in baseline_tasks)
    actual = SEPARATOR.join(by_id[t.task_id]["body"] for t in baseline_tasks)
    d = _diff(expected, actual, "document-order")
    print(f"[{'PASS' if not d else 'FAIL'}] document-order round-trip diff "
          f"({len(expected.split(chr(10)))} lines) -- {'empty' if not d else str(len(d)) + ' diff lines'}")
    if d:
        ok = False
        print("\n".join(d[:200]))

    # --- round trip, canonical order (batch -> track -> id) ---------------
    canon = sorted(baseline_tasks, key=canonical_sort_key)
    expected_c = SEPARATOR.join(t.body for t in canon)
    actual_c = SEPARATOR.join(by_id[t.task_id]["body"] for t in canon)
    d = _diff(expected_c, actual_c, "canonical-order")
    print(f"[{'PASS' if not d else 'FAIL'}] canonical-order round-trip diff -- "
          f"{'empty' if not d else str(len(d)) + ' diff lines'}")
    if d:
        ok = False
        print("\n".join(d[:200]))

    # --- per-task exactness ----------------------------------------------
    bad = [t.task_id for t in baseline_tasks if by_id[t.task_id]["body"] != t.body]
    print(f"[{'PASS' if not bad else 'FAIL'}] per-task byte-exact bodies "
          f"({len(baseline_tasks) - len(bad)}/{len(baseline_tasks)})")
    if bad:
        ok = False
        for tid in bad[:5]:
            print("\n".join(_diff(next(t.body for t in baseline_tasks if t.task_id == tid),
                                  by_id[tid]["body"], f"task-{tid}")[:60]))

    # --- dangling references ---------------------------------------------
    universe = set(by_id)
    dangling = defaultdict(list)
    for r in records:
        for fieldname in ("prerequisites", "conflicts_with", "parallel_with"):
            for ref in r["fm"][fieldname]:
                if ref not in universe:
                    dangling[ref].append(f"{r['fm']['id']}.{fieldname}")
    if dangling:
        ok = False
        print(f"[FAIL] {len(dangling)} dangling task-id reference(s):")
        for ref, where in sorted(dangling.items()):
            print(f"       {ref!r} referenced by {', '.join(where)}")
    else:
        print("[PASS] no dangling prerequisites / conflicts_with / parallel_with ids")

    # --- self references / symmetry (informational) -----------------------
    selfrefs = [
        f"{r['fm']['id']}.{f}"
        for r in records
        for f in ("prerequisites", "conflicts_with", "parallel_with")
        if r["fm"]["id"] in r["fm"][f]
    ]
    if selfrefs:
        print(f"[INFO] self-references: {', '.join(selfrefs)}")

    asym = []
    conflicts = {r["fm"]["id"]: set(r["fm"]["conflicts_with"]) for r in records}
    for tid, cs in conflicts.items():
        for other in cs:
            if other in conflicts and tid not in conflicts[other]:
                asym.append(f"{tid} -> {other} (not reciprocated)")
    if asym:
        print(f"[INFO] {len(asym)} non-reciprocal conflict edge(s):")
        for a in sorted(asym):
            print(f"       {a}")
    else:
        print("[INFO] all conflict edges are reciprocal")

    # --- prose that could not be parsed into ids (informational) ----------
    unparsed = [
        (t.task_id, k, v) for t in baseline_tasks for k, v in t.unparsed.items()
    ]
    print(f"[INFO] {len(unparsed)} dependency line(s) carry prose alongside ids "
          f"(preserved verbatim in body + *_raw frontmatter)")

    print("=" * 72)
    print("RESULT:", "ALL CHECKS PASS" if ok else "FAILURES ABOVE")
    print("=" * 72)
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", default=f"git:{BASELINE_REF}",
                   help="plan to split: a path, or git:<ref>")
    p.add_argument("--baseline", default=f"git:{BASELINE_REF}",
                   help="plan to verify against: a path, or git:<ref>")
    p.add_argument("--tasks-dir", default=str(TASKS_DIR))
    p.add_argument("--verify", action="store_true", help="verify only, write nothing")
    args = p.parse_args()

    tasks_dir = Path(args.tasks_dir)
    if args.verify:
        return cmd_verify(args.baseline, tasks_dir)
    return cmd_split(args.source, tasks_dir)


if __name__ == "__main__":
    raise SystemExit(main())
