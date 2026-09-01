"""Corpus-wide checks that belong to no one section of the document.

The Plan Summary's hand-written track counts against the corpus, and the rule
that every conflict mutex has to name the file it is a mutex over.
"""

from __future__ import annotations

import re

from declared import (
    DECLARED_TRACK_COUNT_DIVERGENCES,
    DECLARED_UNREVIEWABLE_CONFLICTS,
)
from document import batch_order, find_block, heading_blocks, parse_table, split_table
from graph import id_key


def plan_summary_track_counts(records, baseline_text: str) -> dict[str, tuple[int, int]]:
    """``batch key -> (count the summary claims, count the corpus has)``.

    The corpus count is the number of distinct ``track_heading`` values a
    batch's tasks carry -- the same definition the renderer puts in the Tracks
    column, so renderer, cross-check and verifier cannot disagree about what a
    track is. Rows whose label is not a batch (``Total``) take no part.
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

    Returns ``(observed, undeclared, mismatched, stale)``. ``undeclared`` is the
    case that matters most -- a lost track looks exactly like a new divergence.
    ``mismatched`` means a count moved so the recorded reconciliation no longer
    describes what is there; ``stale`` means a declared entry no longer
    diverges. Set equality, not one-way filtering: drift and a silently
    reverted declaration both fail.
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



# --------------------------------------------------------------------------
# Conflict annotations: a mutex has to name the thing it is a mutex over
# --------------------------------------------------------------------------
# A mutex is only reviewable if it says WHAT the two tasks collide over. "Tasks
# 8.4, 8.5 (same popup shell and route table)" cannot be checked, refuted or
# retired; "Tasks 3.1, 3.2, 3.3 (`app/models/__init__.py`)" names a path a
# reader can open. So a task with a non-empty ``conflicts_with`` must name at
# least one backticked span with a directory separator or a file extension; a
# backticked identifier (`ActionKind`) is not one.

_CONFLICT_TICKS_RE = re.compile(r"`([^`]+)`")
_CONFLICT_PATH_RE = re.compile(r"/|^[\w.\-]+\.[A-Za-z0-9]{1,5}$")
_CONFLICT_BODY_RE = re.compile(r"^\*\*Conflicts with:\*\*\s*(.*)$", re.MULTILINE)


def check_conflict_annotations(records):
    """``(findings, info)`` -- every conflict mutex names what it collides over.

    Asserts that a task with a non-empty ``conflicts_with`` names at least one
    path in ``conflicts_with_raw`` or is declared unreviewable; that a declared
    entry still matches the annotation on disk and still names no path (one that
    has gained a path is stale); and that the body's ``**Conflicts with:**``
    line and the frontmatter agree, so an annotation cannot be fixed in one and
    left stale in the other.

    NOT checked: that the path exists (this is a plan; most of these files are
    not written yet), that both sides of a mutex name the same path, or that
    the path is the right one. Those need a built tree or a human.
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

        # frontmatter and body must not drift apart.
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
