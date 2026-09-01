"""Reading the plan document and finding things in it.

Headings, tables and the fenced blocks the checks work over. Knows the shape of
a markdown document, not the meaning of a task: no Task objects, no allowlists,
no assertions. Shared so the renderer, the cross-checks and ``--verify`` locate
a section by exactly the same rule.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from config import (
    CRITICAL_PATH_HEADING,
    HEADING_RE,
    MAKESPAN_HEADING,
    OVERVIEW_HEADING,
    REPO_ROOT,
    TRACK_LETTER_RE,
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


def track_letter(heading_text: str) -> str | None:
    """The letter of a track heading, given the text after ``### ``."""
    m = TRACK_LETTER_RE.match(heading_text)
    return m.group(1) if m else None


# --------------------------------------------------------------------------
# Headings and tables
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


def batch_order(records) -> list[str]:
    """Batch keys in document order (0..6, deployment, 7..10)."""
    seen = []
    for r in records:  # records are already in document order
        key = str(r["fm"]["batch"])
        if key not in seen:
            seen.append(key)
    return seen



def batch_label(key: str) -> str:
    """``"deployment"`` -> ``"Deployment"``; a numeric key -> ``"Batch N"``."""
    return "Deployment" if key == "deployment" else f"Batch {key}"



# --------------------------------------------------------------------------
# Named blocks the checks read
# --------------------------------------------------------------------------

def critical_path_lines(plan_text: str) -> list[str]:
    """The lines of the ``## Critical Path`` section, heading included."""
    lines = plan_text.split("\n")
    h = find_block(heading_blocks(lines), CRITICAL_PATH_HEADING)
    return lines[h["i"]: h["end"]]


def makespan_table(plan_text: str) -> list[list[str]]:
    """The parsed rows of the makespan table, header row dropped."""
    section = critical_path_lines(plan_text)
    h = find_block(heading_blocks(section), MAKESPAN_HEADING)
    _, table, _ = split_table(section[h["i"] + 1: h["end"]])
    return parse_table(table)[1:]


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
