"""The prerequisite DAG: task ordering and longest-path queries.

Only ``prerequisites`` are edges. ``conflicts_with`` is an UNDIRECTED MUTEX,
not an ordering, so feeding it into a longest-path walk would invent an order
the corpus does not state. Shared so the renderer, the makespan cross-check and
``--verify`` all take the longest path from one implementation.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque

from models import Chain


def id_key(task_id: str) -> tuple:
    """Sort key that orders ``4.9`` before ``4.10``. ``I.x`` sorts last."""
    if task_id.startswith("I."):
        return (98, int(task_id.split(".")[1]), "")
    major, minor = task_id.split(".")
    m = re.match(r"^([0-9]+)([a-z]*)$", minor)
    return (int(major), int(m.group(1)), m.group(2))



def longest_chain(records, subset=None) -> Chain:
    """The longest prerequisite chain over ``records`` (optionally restricted).

    ``subset`` restricts BOTH nodes and edges, so the result is the longest
    chain *within* the restriction rather than one that leaves it and comes
    back. THE MAXIMAL CHAIN NEED NOT BE UNIQUE, and in this corpus it is not, so
    ``count`` reports how many and ``chain`` is picked by an order-independent
    tie-break: start at the LOWEST-NUMBERED task among ``endpoints``, then walk
    back taking the LOWEST-NUMBERED prerequisite still on a maximal chain
    (``depth[p] == depth[n] - 1``). "Lowest" is ``id_key``, so 4.9 precedes
    4.10; nothing depends on dict or filesystem order.
    """
    by = {r["fm"]["id"]: r["fm"] for r in records}
    nodes = set(by) if subset is None else {n for n in subset if n in by}
    pre = {n: [p for p in by[n]["prerequisites"] if p in nodes] for n in nodes}
    succ = defaultdict(list)
    for n in nodes:
        for p in pre[n]:
            succ[p].append(n)

    indeg = {n: len(pre[n]) for n in nodes}
    queue = deque(sorted((n for n in nodes if not indeg[n]), key=id_key))
    topo: list[str] = []
    while queue:
        n = queue.popleft()
        topo.append(n)
        for s in succ[n]:
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    if len(topo) != len(nodes):
        raise ValueError(
            "prerequisite graph contains a cycle among "
            f"{sorted(set(nodes) - set(topo), key=id_key)}"
        )

    depth: dict[str, int] = {}
    ways: dict[str, int] = {}
    for n in topo:
        depth[n] = 1 + max((depth[p] for p in pre[n]), default=0)
        on_path = [p for p in pre[n] if depth[p] == depth[n] - 1]
        ways[n] = sum(ways[p] for p in on_path) if on_path else 1

    length = max(depth.values(), default=0)
    endpoints = sorted((n for n in nodes if depth[n] == length), key=id_key)
    count = sum(ways[e] for e in endpoints)

    chain: list[str] = []
    if endpoints:
        cur = endpoints[0]
        chain.append(cur)
        while True:
            back = sorted(
                (p for p in pre[cur] if depth[p] == depth[cur] - 1), key=id_key
            )
            if not back:
                break
            cur = back[0]
            chain.append(cur)
        chain.reverse()
    return Chain(length, chain, endpoints, count, depth)



def batch_subset(records, key: str) -> list[str]:
    """Task ids belonging to one batch key (``"0"``..``"10"``/``"deployment"``)."""
    return [r["fm"]["id"] for r in records if str(r["fm"]["batch"]) == key]
