"""Restatements of the derived quantities in authored prose: a CHECK.

Three numbers are DERIVED -- the task count, the critical-path floor and the
makespan slot total. Inside ``## Critical Path`` each is generated or already
asserted; OUTSIDE it they are restated in authored ARGUMENT, where nothing tied
them to the corpus, so the floor could move from 20 to 22 and those sentences
would go on saying 20. Regenerating the argument would flatten the writing into
a number dump, so the numbers it argues from are checked instead.
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal

from config import (
    CRITICAL_PATH_HEADING,
    NUM_PATTERN,
    PROGRESS_PREFIX,
    RATIO_PATTERN,
    parse_count,
)
from declared import DECLARED_RESTATEMENTS
from document import find_block, heading_blocks, makespan_table
from graph import longest_chain
from models import DerivedQuantity


def makespan_slot_total(plan_text: str) -> int | None:
    """The makespan table's slot column, summed over the per-batch rows.

    The same definition check_makespan_table reconciles the authored
    ``**Total**`` cell against, so the restated ~35 and the table's own Total
    cannot be checked against two different numbers. ``None`` when no row
    carries a numeric slot count: an unreadable table is that check's finding.
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

    Ratios are quantities in their own right: ``4.5x`` is an assertion ABOUT
    two derived numbers and can be wrong while both of them are right.
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


def restatement_tolerance(decimals: int) -> Decimal:
    """Half a unit in the last place the document prints.

    The prose rounds, so equality is the wrong test: 91/20 is 4.55 and the
    document says **4.5x**. Tightening with precision makes an integer
    restatement exact while **4.5x** is held to +/-0.05, and every site that
    states a ratio also declares the integers it is a ratio of.
    """
    return Decimal(1).scaleb(-decimals) / 2


def parse_stated(token: str) -> tuple[Decimal, int] | None:
    """``"4.5"`` -> ``(Decimal("4.5"), 1)``; ``"Ninety-one"`` -> ``(91, 0)``."""
    t = token.strip().lower()
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", t):
        return Decimal(t), len(t.partition(".")[2])
    n = parse_count(t)
    return None if n is None else (Decimal(n), 0)


def readable_pattern(pattern: str) -> str:
    """A claim's regex with the number alternations folded to a placeholder.

    ``NUM_PATTERN`` is a hundred-way alternation of English number words;
    printing it raw buries the one thing a reader needs -- which PHRASE stopped
    matching -- under six lines of "seventy-three|seventy-seven".
    """
    return pattern.replace(NUM_PATTERN, "<number>").replace(RATIO_PATTERN, "<ratio>")


def _show(value: Decimal, decimals: int) -> str:
    q = value.quantize(Decimal(1).scaleb(-decimals)) if decimals else value
    return f"{q.normalize():f}" if decimals else f"{q:f}"


# UNDECLARED restatements. Hunting bare numbers fires on unrelated 20s, so the
# sweep matches only these SHAPES and only while the number still AGREES with a
# derived quantity -- the realistic failure is a sentence written correctly
# today going stale later. LIMIT: a restatement phrased outside these shapes, or
# one that already disagrees, is NOT detected and must be declared by hand.
_RESTATEMENT_SHAPES = (
    ("a number wearing a unit", rf"~?\b({NUM_PATTERN})(?:-|\s+)(?:tasks?|slots?)\b"),
    ("a bold header field", rf"^\*\*[^*]+:\*\*\s+~?({NUM_PATTERN})\b"),
    ("an 'N over' ratio phrase", rf"\b({NUM_PATTERN})\s+over\b"),
    ("a bold multiplier", rf"\*\*~?{RATIO_PATTERN}x\*\*"),
)

# Regions the sweep does not scan, and why each one is already covered.
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

    Asserts that every declared site is still locatable by its anchor and every
    claim inside it still readable (a site rewritten past its anchor FAILS
    rather than quietly dropping out), that every stated number is a correct
    rounding of the derived value at the precision the prose states, and that no
    restatement in a known shape sits outside a declared site.
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

