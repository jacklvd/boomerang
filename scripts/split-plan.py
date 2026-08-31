#!/usr/bin/env python3
"""Split plan/boomerang-plan.md into one file per task under plan/tasks/.

    scripts/split-plan.py --source git:cf7e210      # write plan/tasks/** (one-time)
    scripts/split-plan.py --verify                  # structural + baseline assertions

--verify is the gate. It asserts the corpus is structurally sound -- 91 tasks,
every metadata field present, frontmatter agreeing with the body line it was
parsed from, no dangling or self references, conflicts reciprocal, every
requirement in the design document covered by some task, every track_heading
actually rendered in the index and each batch's track letters gapless from
A -- and then compares
against the pre-split baseline, requiring that exactly the declared set of task
bodies (INTENDED_BODY_CHANGES) differs from it and that exactly the declared set
of Plan Summary track counts (DECLARED_TRACK_COUNT_DIVERGENCES) disagrees with
the corpus.

The split is lossless by construction: each task file is a YAML frontmatter
block followed by the task body copied VERBATIM out of the plan -- heading line
through the blank line before the ``---`` separator. No line is lifted out of
the body, so the only difference between the corpus and the original task spans
is the frontmatter block itself.
"""

from __future__ import annotations

import argparse
import difflib
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_lib import (  # noqa: E402
    BASELINE_REF,
    BATCH_HEADING_RE,
    DECLARED_GAPS,
    DECLARED_TRACK_COUNT_DIVERGENCES,
    METADATA_FIELDS,
    PLAN_PATH,
    TASKS_DIR,
    track_letter,
    batch_label,
    canonical_sort_key,
    classify_track_count_divergences,
    load_tasks_from_files,
    pad_id,
    parse_id_list,
    parse_plan,
    parse_requirements,
    read_source,
    render_frontmatter,
    requirement_ids_from_doc,
    slugify,
    TASK_HEADING_RE,
)

SEPARATOR = "\n---\n\n"  # the blank line is already the last line of each body

# A markdown link with a relative target (not http(s):, not a bare anchor).
LINK_RE = re.compile(r"\]\((?!https?:|#)([^)]+)\)")

# --------------------------------------------------------------------------
# The historical baseline
# --------------------------------------------------------------------------
# ``--baseline`` (default ``git:cf7e210``) is the pre-split plan. Task bodies
# were byte-identical to it at the moment of the split; they are no longer,
# because the adjudication round corrected defects the split exposed. The
# baseline check is therefore NOT "the diff is empty" -- it is "the set of
# tasks whose body differs from the baseline is EXACTLY this declared set".
# That fails on unintended drift AND on a reverted intended change, which an
# empty-diff assertion could not do once any edit was legitimate.
#
# Every entry names the finding it settles. Editing a task without adding it
# here fails verification; so does listing a task and then reverting it.
INTENDED_BODY_CHANGES = {
    "1.2":  "B/G: reciprocal conflict with 1.4 (wxt.config.ts); AGENTS.md link repointed",
    "3.8":  "D: heading names the X-Boomerang-Client-Version gate (decision D16)",
    "3.14": "A: Task 0.1 added as a prerequisite (0.1 records the flow it is built from)",
    "4.5":  "D: heading annotated '(test double)' (decision D21)",
    "4.6":  "D: heading names the barrel, which 4.10's conflicts line refers back to",
    "4.7":  "B: reciprocal conflict with 4.12 (src/storage/coordinator.ts)",
    "4.14": "A/C/D/E: 3.18 prerequisite; FR-3.4.5b and NFR-6.3 coverage; '(runtime stub)'",
    "6.5":  "D: heading names adapter selection (step 7, cited by 4.14)",
    "8.5":  "C/D: FR-3.4.5b coverage; heading names the simulated-booking marker",
    "9.1":  "A: prerequisite 8.5 -> 8.6, matching the authored critical-path floor",
    "10.1": "E: NFR-6.6 belongs to the deployment track (low-level design §8.4)",
    "10.2": "D: heading names the configuration sweep (step 2)",
    "I.2":  "E: NFR-6.6 coverage, per low-level design §8.4",
}


def cmd_split(source: str, tasks_dir: Path, force: bool = False) -> int:
    text = read_source(source)
    tasks = parse_plan(text)
    print(f"parsed {len(tasks)} tasks from {source}")

    if tasks_dir.exists():
        if not force:
            raise SystemExit(
                f"{tasks_dir} already exists. The split is a ONE-TIME bootstrap: the task "
                f"files are now the source of truth and carry edits the baseline plan does "
                f"not have (see INTENDED_BODY_CHANGES). Re-splitting would silently revert "
                f"them. Pass --force if that is genuinely what you want."
            )
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


def tracks_by_batch(plan_text: str) -> dict[str, list[str]]:
    """Every ``###`` heading the plan renders, keyed by the batch owning it.

    Headings are returned as the text AFTER ``### ``, which is the same form
    ``track_heading`` frontmatter carries, so the two compare directly.
    """
    out: dict[str, list[str]] = {}
    batch: str | None = None
    for line in plan_text.split("\n"):
        if bm := BATCH_HEADING_RE.match(line):
            batch = bm.group(1)
            out.setdefault(batch, [])
        elif line.startswith("## Deployment Track"):
            batch = "deployment"
            out.setdefault(batch, [])
        elif line.startswith("## "):
            batch = None
        elif line.startswith("### ") and batch is not None:
            out[batch].append(line[4:])
    return out


def cmd_verify(baseline: str, tasks_dir: Path) -> int:
    state = {"ok": True}

    def report(good: bool, msg: str, detail: list[str] | None = None) -> bool:
        state["ok"] &= bool(good)
        print(f"[{'PASS' if good else 'FAIL'}] {msg}")
        if not good and detail:
            for line in detail[:30]:
                print(f"       {line}")
        return bool(good)

    text = read_source(baseline)
    baseline_tasks = parse_plan(text)
    records = load_tasks_from_files(tasks_dir)

    print("=" * 72)
    print("STRUCTURAL VERIFICATION")
    print("=" * 72)

    # --- count assertions -------------------------------------------------
    n_files = len(records)
    report(n_files == 91, f"task files on disk: {n_files} (expect 91)")
    report(len(baseline_tasks) == 91,
           f"tasks parsed from {baseline}: {len(baseline_tasks)} (expect 91)")

    corpus = "\n".join(r["body"] for r in records)
    for fieldname in METADATA_FIELDS:
        n = sum(1 for line in corpus.split("\n") if line.startswith(f"**{fieldname}:**"))
        report(n == 91, f"**{fieldname}:** appears {n} times (expect 91)")

    by_id = {r["fm"]["id"]: r for r in records}
    missing = [t.task_id for t in baseline_tasks if t.task_id not in by_id]
    if missing:
        print(f"[FAIL] no file for tasks: {missing}")
        return 1

    # --- file naming and heading agreement --------------------------------
    bad_names = [
        f"{r['path'].name} != {pad_id(r['fm']['id'])}-{slugify(r['fm']['title'])}.md"
        for r in records
        if r["path"].name != f"{pad_id(r['fm']['id'])}-{slugify(r['fm']['title'])}.md"
    ]
    report(not bad_names,
           f"filenames are pad_id(id)-slugify(title).md ({len(records) - len(bad_names)}/{len(records)})",
           bad_names)

    bad_heads = []
    for r in records:
        m = TASK_HEADING_RE.match(r["body"].split("\n")[0])
        if not m:
            bad_heads.append(f"{r['fm']['id']}: body does not open with a task heading")
        elif m.group(1) != r["fm"]["id"] or m.group(2) != r["fm"]["title"]:
            bad_heads.append(
                f"{r['fm']['id']}: heading says {m.group(1)}/{m.group(2)!r}, "
                f"frontmatter says {r['fm']['id']}/{r['fm']['title']!r}"
            )
    report(not bad_heads,
           f"body heading id + title match frontmatter ({len(records) - len(bad_heads)}/{len(records)})",
           bad_heads)

    # --- frontmatter / body agreement -------------------------------------
    # The same fact is stated twice -- once for the parser, once for the human
    # reading the task. A dependency edited in one place and not the other is
    # the exact defect class this corpus was split to eliminate.
    disagree = []
    body_fields = [
        ("prerequisites", "Prerequisites"),
        ("conflicts_with", "Conflicts with"),
        ("parallel_with", "Parallel with"),
    ]
    for r in records:
        fm, lines = r["fm"], r["body"].split("\n")
        for key, label in body_fields:
            prefix = f"**{label}:**"
            hits = [l for l in lines if l.startswith(prefix)]
            if len(hits) != 1:
                disagree.append(f"{fm['id']}: {len(hits)} {prefix} lines in body")
                continue
            raw = hits[0][len(prefix):].strip()
            if raw != fm[f"{key}_raw"]:
                disagree.append(f"{fm['id']}.{key}_raw: body {raw!r} != frontmatter {fm[f'{key}_raw']!r}")
            ids, _ = parse_id_list(raw)
            if ids != fm[key]:
                disagree.append(f"{fm['id']}.{key}: body parses to {ids}, frontmatter says {fm[key]}")
        prefix = "**Requirements covered:**"
        hits = [l for l in lines if l.startswith(prefix)]
        if len(hits) != 1:
            disagree.append(f"{fm['id']}: {len(hits)} {prefix} lines in body")
        else:
            raw = hits[0][len(prefix):].strip()
            if raw != fm["requirements_covered_raw"]:
                disagree.append(
                    f"{fm['id']}.requirements_covered_raw: body {raw!r} != "
                    f"frontmatter {fm['requirements_covered_raw']!r}"
                )
            reqs, sections, _ = parse_requirements(raw)
            if reqs != fm["requirements_covered"]:
                disagree.append(
                    f"{fm['id']}.requirements_covered: body parses to {reqs}, "
                    f"frontmatter says {fm['requirements_covered']}"
                )
            if sections != fm["sections_covered"]:
                disagree.append(
                    f"{fm['id']}.sections_covered: body parses to {sections}, "
                    f"frontmatter says {fm['sections_covered']}"
                )
    report(not disagree,
           f"frontmatter agrees with the body line it was parsed from "
           f"({len(records) * 4 - len(disagree)}/{len(records) * 4} lines)",
           disagree)

    # --- dangling / self references ---------------------------------------
    universe = set(by_id)
    dangling = defaultdict(list)
    for r in records:
        for fieldname in ("prerequisites", "conflicts_with", "parallel_with"):
            for ref in r["fm"][fieldname]:
                if ref not in universe:
                    dangling[ref].append(f"{r['fm']['id']}.{fieldname}")
    report(not dangling,
           f"no dangling prerequisites / conflicts_with / parallel_with ids"
           + (f" ({len(dangling)} dangling)" if dangling else ""),
           [f"{ref!r} referenced by {', '.join(where)}" for ref, where in sorted(dangling.items())])

    selfrefs = [
        f"{r['fm']['id']}.{f}"
        for r in records
        for f in ("prerequisites", "conflicts_with", "parallel_with")
        if r["fm"]["id"] in r["fm"][f]
    ]
    report(not selfrefs, "no task depends on, conflicts with, or parallels itself", selfrefs)

    # --- conflict reciprocity (hard) --------------------------------------
    # A conflict is a property of a PAIR of tasks. Recorded on one side only,
    # the agent who opens the other task never learns of the contention -- and
    # decision D24 puts two agents in flight at once.
    conflicts = {r["fm"]["id"]: set(r["fm"]["conflicts_with"]) for r in records}
    asym = [
        f"{tid} lists {other}, but {other} does not list {tid}"
        for tid, cs in conflicts.items()
        for other in sorted(cs)
        if other in conflicts and tid not in conflicts[other]
    ]
    report(not asym, f"all {sum(len(c) for c in conflicts.values()) // 2} conflict edges are reciprocal", asym)

    # --- conflicts and parallelism are exclusive --------------------------
    both = [
        f"{r['fm']['id']}: {sorted(set(r['fm']['conflicts_with']) & set(r['fm']['parallel_with']))}"
        for r in records
        if set(r["fm"]["conflicts_with"]) & set(r["fm"]["parallel_with"])
    ]
    report(not both, "no task is both conflicting with and parallel to the same task", both)

    # --- requirement coverage (hard) --------------------------------------
    # Every requirement the design document declares must be claimed by some
    # task, unless it is on the DECLARED_GAPS allowlist in plan_lib. This is
    # the check that catches a normative requirement no task ever picked up.
    declared = requirement_ids_from_doc()
    covered: set[str] = set()
    for r in records:
        covered.update(r["fm"]["requirements_covered"])
    uncovered = sorted(declared - covered - set(DECLARED_GAPS))
    report(not uncovered,
           f"every requirement in the design doc is cited by a task "
           f"({len(declared & covered)}/{len(declared)} cited, "
           f"{len(DECLARED_GAPS)} declared gaps)",
           [f"{req}: no task cites it, and it is not in plan_lib.DECLARED_GAPS" for req in uncovered])

    unknown = sorted(covered - declared)
    report(not unknown, "no task cites a requirement the design doc does not declare",
           [f"{req}: cited by tasks, absent from the requirements document" for req in unknown])

    stale_gaps = sorted(set(DECLARED_GAPS) & covered)
    report(not stale_gaps, "no declared gap is actually covered (allowlist is not stale)",
           [f"{req}: on the DECLARED_GAPS allowlist, but covered by a task" for req in stale_gaps])

    # --- relative links resolve -------------------------------------------
    # Task bodies were written when they lived in plan/; every relative link in
    # them moved two directories down when the plan was split.
    broken = []
    for r in records:
        for m in LINK_RE.finditer(r["body"]):
            target = m.group(1).split("#")[0].strip()
            if not target:
                continue
            if not (r["path"].parent / target).resolve().exists():
                broken.append(f"{r['fm']['id']}: {target} does not resolve from {r['path'].parent}")
    report(not broken, "every relative link in a task body resolves to a file that exists", broken)

    # --- track headings: no orphans -----------------------------------------
    # Task 0.2 was parked under Track A because the Track B heading it belonged
    # to had been lost from the document, and nothing asserted the two agreed.
    # A track_heading in frontmatter that the generated index does not render
    # means the reader and the corpus disagree about where a task lives.
    rendered_tracks = tracks_by_batch(PLAN_PATH.read_text() if PLAN_PATH.exists() else "")
    orphans = [
        f"{r['fm']['id']}: track_heading {r['fm']['track_heading']!r} is not a `###` "
        f"heading under Batch {r['fm']['batch']} in {PLAN_PATH.name}"
        for r in records
        if r["fm"]["track_heading"]
        and r["fm"]["track_heading"] not in rendered_tracks.get(str(r["fm"]["batch"]), [])
    ]
    n_tracked = sum(1 for r in records if r["fm"]["track_heading"])
    report(not orphans,
           f"every task's track_heading is rendered in {PLAN_PATH.name} "
           f"({n_tracked - len(orphans)}/{n_tracked} tracked tasks)",
           orphans)

    # --- track letters are gapless from A -----------------------------------
    # The Track B heading going missing left Batch 0 running A, C. A gap is the
    # visible symptom of a lost track, so it is the thing worth asserting: the
    # letters a batch's tasks name must be A..X with nothing skipped. Headings
    # with no letter (`Gate: Manual acceptance [extension]`) are not tracks and
    # take no part in the sequence.
    letters_by_batch = defaultdict(set)
    for r in records:
        th = r["fm"]["track_heading"]
        if th and (letter := track_letter(th)):
            letters_by_batch[str(r["fm"]["batch"])].add(letter)
    gaps = []
    for key in sorted(letters_by_batch, key=lambda k: (k == "deployment", k.zfill(3))):
        letters = sorted(letters_by_batch[key])
        expected = [chr(ord("A") + i) for i in range(len(letters))]
        if letters != expected:
            gaps.append(
                f"batch {key}: track letters {', '.join(letters)} -- expected a gapless "
                f"A{'..' + expected[-1] if len(expected) > 1 else ''}; "
                f"missing {', '.join(l for l in expected if l not in letters)}"
            )
    report(not gaps,
           f"track letters in each batch are gapless from A "
           f"({len(letters_by_batch) - len(gaps)}/{len(letters_by_batch)} batches)",
           gaps)

    print()
    print("=" * 72)
    print(f"BASELINE COMPARISON ({baseline})")
    print("=" * 72)

    # --- baseline: intended changes, and nothing else ---------------------
    changed = {t.task_id for t in baseline_tasks if by_id[t.task_id]["body"] != t.body}
    intended = set(INTENDED_BODY_CHANGES)
    unexpected = sorted(changed - intended)
    reverted = sorted(intended - changed)
    detail = [f"{tid}: changed from baseline, not declared in INTENDED_BODY_CHANGES" for tid in unexpected]
    detail += [f"{tid}: declared as changed, but is byte-identical to the baseline" for tid in reverted]
    report(changed == intended,
           f"{len(changed)} task bodies differ from the baseline; "
           f"{len(intended)} declared intended changes; sets match",
           detail)
    for tid in sorted(intended, key=lambda x: (x.startswith("I."), pad_id(x))):
        mark = "changed" if tid in changed else "MISSING"
        print(f"       {mark:8s} {tid:5s} {INTENDED_BODY_CHANGES[tid]}")

    # --- baseline: declared Plan Summary track-count divergences ----------
    # Same shape as the check above, over a different axis. The baseline's
    # hand-written Plan Summary claims a track count per batch; the corpus
    # counts distinct ``###`` track headings. Three rows disagree for reasons
    # that have been investigated and are recorded in
    # ``plan_lib.DECLARED_TRACK_COUNT_DIVERGENCES`` with BOTH numbers, so this
    # is set equality between declared and observed, not a skip-list: a new
    # divergence (a lost track looks exactly like one), a declared divergence
    # whose numbers have moved, and a declared divergence that has gone away
    # all fail here.
    observed, undeclared, mismatched, stale = classify_track_count_divergences(
        records, text
    )
    detail = [
        f"{batch_label(k)}: summary says {observed[k][0]}, corpus has {observed[k][1]} "
        f"`###` track heading(s) -- not declared in DECLARED_TRACK_COUNT_DIVERGENCES"
        for k in undeclared
    ]
    detail += [
        f"{batch_label(k)}: summary says {observed[k][0]}, corpus has {observed[k][1]}, "
        f"but the allowlist reconciles {DECLARED_TRACK_COUNT_DIVERGENCES[k].baseline} "
        f"against {DECLARED_TRACK_COUNT_DIVERGENCES[k].corpus} "
        f"({DECLARED_TRACK_COUNT_DIVERGENCES[k].reason}) -- the reason needs revisiting"
        for k in mismatched
    ]
    detail += [
        f"{batch_label(k)}: declared as diverging "
        f"({DECLARED_TRACK_COUNT_DIVERGENCES[k].baseline} vs "
        f"{DECLARED_TRACK_COUNT_DIVERGENCES[k].corpus}), but the summary and the "
        f"corpus now agree -- the entry is stale, delete it"
        for k in stale
    ]
    report(not detail,
           f"{len(observed)} Plan Summary track count(s) diverge from the corpus; "
           f"{len(DECLARED_TRACK_COUNT_DIVERGENCES)} declared divergences; sets match",
           detail)
    for key in sorted(DECLARED_TRACK_COUNT_DIVERGENCES,
                      key=lambda k: (k == "deployment", k.zfill(3))):
        entry = DECLARED_TRACK_COUNT_DIVERGENCES[key]
        mark = "diverges" if key in observed else "MISSING"
        print(f"       {mark:8s} {batch_label(key):11s} {entry.baseline} vs "
              f"{entry.corpus}  {entry.reason}")

    # --- round trip over the UNCHANGED tasks ------------------------------
    # Ordering and per-task exactness are still asserted byte-for-byte; the
    # intended edits above are excluded by id, never by loosening the diff.
    stable = [t for t in baseline_tasks if t.task_id not in intended]
    expected = SEPARATOR.join(t.body for t in stable)
    actual = SEPARATOR.join(by_id[t.task_id]["body"] for t in stable)
    d = _diff(expected, actual, "document-order")
    report(not d, f"document-order round-trip over {len(stable)} unchanged tasks "
                  f"({len(expected.split(chr(10)))} lines) -- "
                  f"{'empty' if not d else str(len(d)) + ' diff lines'}", d)

    canon = sorted(stable, key=canonical_sort_key)
    expected_c = SEPARATOR.join(t.body for t in canon)
    actual_c = SEPARATOR.join(by_id[t.task_id]["body"] for t in canon)
    d = _diff(expected_c, actual_c, "canonical-order")
    report(not d, f"canonical-order round-trip over {len(canon)} unchanged tasks -- "
                  f"{'empty' if not d else str(len(d)) + ' diff lines'}", d)

    bad = [t.task_id for t in stable if by_id[t.task_id]["body"] != t.body]
    report(not bad, f"per-task byte-exact bodies for unchanged tasks "
                    f"({len(stable) - len(bad)}/{len(stable)})")

    # --- prose that could not be parsed into ids (informational) ----------
    unparsed = [
        (t.task_id, k, v) for t in baseline_tasks for k, v in t.unparsed.items()
    ]
    print(f"[INFO] {len(unparsed)} dependency line(s) carry prose alongside ids "
          f"(preserved verbatim in body + *_raw frontmatter)")

    print("=" * 72)
    print("RESULT:", "ALL CHECKS PASS" if state["ok"] else "FAILURES ABOVE")
    print("=" * 72)
    return 0 if state["ok"] else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", default=f"git:{BASELINE_REF}",
                   help="plan to split: a path, or git:<ref>")
    p.add_argument("--baseline", default=f"git:{BASELINE_REF}",
                   help="plan to verify against: a path, or git:<ref>")
    p.add_argument("--tasks-dir", default=str(TASKS_DIR))
    p.add_argument("--verify", action="store_true", help="verify only, write nothing")
    p.add_argument("--force", action="store_true",
                   help="allow --source to overwrite an existing task corpus")
    args = p.parse_args()

    tasks_dir = Path(args.tasks_dir)
    if args.verify:
        return cmd_verify(args.baseline, tasks_dir)
    return cmd_split(args.source, tasks_dir, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
