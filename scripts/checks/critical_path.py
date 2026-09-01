"""The ``## Critical Path`` section: two authored blocks, cross-checked.

The makespan table's rows order tasks that only CONFLICT with one another, and
the chain sentence under ``### Three things ...`` is an argument. Both stay
authored -- picking a serialisation is a human's call a generator would silently
replace -- so they are asserted against the corpus instead: nothing has drifted,
no row claims fewer slots than the prerequisite DAG already forces, and the
sentence still describes a real, server-only, maximal chain. (For a long time
nothing tied that sentence to the corpus and it printed a chain that was neither.
SERVER-SCOPED means ``track_scope == "server"``, the declared field: a
``package`` prefix test would also pull in 10.3 and I.3.)
"""

from __future__ import annotations

import re

from config import (
    ARROW,
    BARE_ID_RE,
    CONCLUSION_RE,
    CRITICAL_PATH_HEADING,
    FLOOR_HEADING,
    FLOOR_LENGTH_RE,
    NUMBER_WORDS,
    PARALLEL,
    PAREN_RE,
    SERVER_SCOPE,
    TASK_ID_RE,
    THREE_THINGS_HEADING,
    parse_count,
)
from declared import DECLARED_CONFLICT_SERIALISATIONS
from document import (
    batch_label,
    critical_path_lines,
    find_block,
    heading_blocks,
    makespan_table,
)
from graph import batch_subset, id_key, longest_chain


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


def _parse_step(token: str):
    """One ``->``-separated step: an id, or a ``{a || b}`` / ``a || b`` group.

    Returns the list of ids, or None if the token is neither shape. ``9.1 ->
    any row`` fails here and the row is reported UNPARSED rather than guessed
    at: inventing a meaning for authored shorthand is the silent
    reinterpretation this check exists to avoid.
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

    The trailing authored parenthetical is dropped first, the same way
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

    Asserts that (1) every id named exists; (2) every ``->`` edge is a real
    prerequisite edge or joins two members of a DECLARED_CONFLICT_SERIALISATIONS
    set that genuinely conflict pairwise; (3) no row's slot count is below the
    prerequisite-only longest chain inside that batch -- a table may claim MORE
    than the floor, never less; (4) the stated total equals the slot column; and
    (5) the authored "roughly **N slots**" conclusion reconciles with the table
    total and the derived floor. Rows outside the grammar are reported UNPARSED
    and take no part in (2).
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
# The authored server-chain sentence
# --------------------------------------------------------------------------

# This sentence's own alternation stays capped at 0-25, the range it had when
# CHAIN_LENGTH_RE / CHAIN_TIE_RE were written, so ``_COUNT`` is byte-identical
# to the hand-written list it replaced and the check's behaviour is untouched.
_NUMBER_WORDS = {w: n for w, n in NUMBER_WORDS.items() if n <= 25}
_COUNT = r"([0-9]+|" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")"
# "... is twelve tasks ..." / "... fifteen distinct chains tie at that length"
CHAIN_LENGTH_RE = re.compile(rf"\b{_COUNT}\s+tasks\b", re.IGNORECASE)
CHAIN_TIE_RE = re.compile(rf"\b{_COUNT}\s+(?:distinct\s+)?chains\b", re.IGNORECASE)
_ID_AT_END_RE = re.compile(rf"({TASK_ID_RE})\s*$")
_ID_AT_START_RE = re.compile(rf"^\s*({TASK_ID_RE})(?!\.?[0-9])")


def parse_server_chain_sentence(plan_text: str):
    """``(ids, claimed_length, claimed_ties, note)`` for the authored sentence.

    Anchored on STRUCTURE, not wording: the first paragraph under ``### Three
    things about the shape of this chain`` carrying an ``→`` run, so the prose
    can be rewritten without silently disabling the check. ``ids`` is None --
    with ``note`` saying why -- when the paragraph is absent or outside the
    grammar, the same refusal ``parse_makespan_cell`` makes at ``9.1 → any row``.
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
    claimed_length = parse_count(m.group(1)) if m else None
    m = CHAIN_TIE_RE.search(text)
    claimed_ties = parse_count(m.group(1)) if m else None
    return ids, claimed_length, claimed_ties, None


def check_server_chain_sentence(records, plan_text: str):
    """``(findings, info)`` -- the authored server chain against the corpus.

    Asserts that every id it names exists, every ``→`` is a real prerequisite
    edge, every task on it is server-scoped (the assertion 10.2 would have
    failed, and the reason this exists), and its length is the derived
    server-only maximum that the stated count agrees with. An absent or
    unparseable sentence is INFO: the document may stop making the claim, it
    may not make a false one.
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

