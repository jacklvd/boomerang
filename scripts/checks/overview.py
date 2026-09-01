"""The ``## Batch Execution Overview``: a CHECK, not a generator.

107 lines of hand-maintained schedule, the largest restatement of the corpus in
the document. It is CHECKED rather than generated because derived facts are
interleaved with judgment that exists nowhere in frontmatter: the
``--- ... PARALLEL ... ---`` lines carry the REASON a lane is parallel, the
``>>>`` lines state what a barrier buys or what a failed spike blocks. A
generator would delete all of it, so those lines stay authored and only the ids
inside them are asserted to exist.
"""

from __future__ import annotations

import re
from collections import defaultdict

from config import (
    BARE_ID_RE,
    BATCH_HEADING_RE,
    OVERVIEW_HEADING,
    PAREN_RE,
    SORT_LAST,
    TASK_ID_RE,
)
from declared import (
    DECLARED_OVERVIEW_SERIALISATIONS,
    DECLARED_OVERVIEW_TITLE_DIVERGENCES,
)
from document import batch_label, batch_order, overview_block, track_letter
from graph import id_key
from models import OverviewUnit


_OV_BATCH_RE = re.compile(r"^Batch ([0-9]+):")
_OV_DEPLOY_PREFIX = "Deployment track"
# ``Track C' (parallel after 4.7)``. The prime is a SCHEDULING LANE inside Track
# C, not a `###` heading of its own -- the reason Batch 4 is on
# DECLARED_TRACK_COUNT_DIVERGENCES -- so it is parsed and folded back onto its
# base letter rather than failing.
_OV_LABEL_RE = re.compile(
    r"^(?P<label>Track (?P<letter>[A-Z])(?P<prime>')?|Gate)"
    r"(?:\s+\((?P<qual>[^)]*)\))?$"
)
_OV_ANNOTATION_RE = re.compile(r"^\[(.*)\]$")
# "after 4.7", "opens after 6.5", "needs 0.2". ``needs`` is included because the
# Deployment track states one of its two edges that way.
_OV_AFTER_RE = re.compile(rf"\b(?:after|needs)\s+({TASK_ID_RE})\b")
# ``7.7-7.10``: range notation used NOWHERE else in this grammar, and only ever
# inside prose lines. Matched so it can be named UNPARSED rather than silently
# mined for its two endpoints.
_OV_RANGE_RE = re.compile(rf"({TASK_ID_RE})\s*[–—-]\s*({TASK_ID_RE})")
_OV_ID_SCAN_RE = re.compile(rf"(?<![\w.]){TASK_ID_RE}(?![\w.])")
_OV_GAP_RE = re.compile(r"\s{2,}")


def _ov_parse_chain(cell: str):
    """``(steps, per-id after-claims, offending token)`` for one lane's chain.

    A chain is ``->``-separated STEPS; a step is a comma-separated group of bare
    ids that run in parallel, optionally carrying its own ``(after X)``. So
    ``4.8, 4.9, 4.10, 4.11 -> 4.12`` is two steps and the arrow joins EVERY
    member of the group to 4.12 -- the all-pairs reading
    ``check_makespan_table`` gives ``{a ∥ b} → c``. Anything outside that shape
    returns ``(None, None, token)`` so the caller can report it UNPARSED.
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
    (authored judgment, NOT parsed as schedule), and ``problems`` the lines
    whose shape is outside the grammar. A lane line splits on runs of two or
    more spaces into an optional trailing ``[annotation]`` and one or more
    ``label: chain`` units -- Batch 10 writes three tracks on one line.
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

    Asserts, in this order: (1) DECLARED_OVERVIEW_SERIALISATIONS names real
    tasks that really conflict pairwise and every entry is still used; (2)
    sections and batches match BOTH ways; (3) each section title agrees with its
    own ``##`` heading once parentheticals and case are normalised, or is
    declared; (4) every id exists; (5) under the batch its frontmatter gives it;
    (6) per batch, each track LETTER's roster is exactly the corpus's, both ways,
    so a forgotten task fails as loudly as an invented one; (7) labelled and
    unlabelled lanes match ``track_heading``; (8) every ``->`` is a prerequisite
    edge or a declared serialisation; (9) every "after X" / "needs X" claim is a
    real edge; (10) an ``[annotation]`` leading with a known scope is the
    ``track_scope`` of every task on that lane.

    NOT asserted, said out loud rather than left to be discovered: annotations
    outside the leading-scope form (they are free-form prose, and any rule loose
    enough to accept ``[server routes and main]`` would accept almost anything);
    what the ``>>>`` and ``--- ... ---`` lines CLAIM, only that their ids exist;
    and section ORDER, since the block puts the Deployment track last while the
    document renders it between Batches 6 and 7. Rosters compare by LETTER, not
    by lane, because Batch 4 splits Track C across ``Track C`` and ``Track C'``.
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
        for letter in sorted(set(seen) | set(want), key=lambda l: l or SORT_LAST):
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

