"""
cycles.py — MODULE 2: cycle analysis on a directed graph (DFS based).

Two DFS-based tools:

1. strongly_connected_components()  — Tarjan's algorithm, O(V + E).
   A strongly connected component (SCC) is a group where every node can reach
   every other node. A node lies on SOME cycle  <=>  its SCC has >= 2 nodes
   (our graphs have no self-loops). So the non-trivial SCCs of the stuck
   wait-for graph are exactly the "deadlock groups", and every edge inside
   such a group lies on a cycle.

2. find_cycle_in()  — classic DFS with three colours that returns ONE example
   cycle (used for the human explanation "P1 -> P2 -> P3 -> P1").
       WHITE = not visited, GREY = on the current DFS path, BLACK = finished.
       Reaching a GREY node again means we walked in a circle.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple

Graph = Dict[str, List[str]]


def build_adjacency(nodes: Iterable[str], edges: Iterable[Tuple[str, str]]) -> Graph:
    graph: Graph = {v: [] for v in nodes}
    for u, v in edges:
        graph.setdefault(u, [])
        graph.setdefault(v, [])
        if v not in graph[u]:
            graph[u].append(v)
    return graph


def strongly_connected_components(graph: Graph) -> List[List[str]]:
    """Tarjan's SCC algorithm (recursive DFS). Returns SCCs as lists of nodes."""
    index_of: Dict[str, int] = {}
    low: Dict[str, int] = {}
    on_stack: Set[str] = set()
    stack: List[str] = []
    result: List[List[str]] = []
    counter = [0]

    def visit(v: str) -> None:
        index_of[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph.get(v, []):
            if w not in index_of:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index_of[w])
        if low[v] == index_of[v]:            # v is the root of an SCC
            component = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == v:
                    break
            result.append(component)

    for v in graph:
        if v not in index_of:
            visit(v)
    return result


def find_cycle_in(graph: Graph, allowed: Optional[Set[str]] = None) -> Optional[List[str]]:
    """
    Three-colour DFS. Returns one cycle as [v0, v1, ..., v0] or None.
    If `allowed` is given, only nodes in that set are explored.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    nodes = [v for v in graph if allowed is None or v in allowed]
    colour = {v: WHITE for v in nodes}
    parent: Dict[str, Optional[str]] = {}

    def dfs(u: str) -> Optional[List[str]]:
        colour[u] = GREY
        for w in graph.get(u, []):
            if w not in colour:
                continue
            if colour[w] == GREY:            # back edge -> cycle found
                cycle = [w]
                x = u
                while x != w:
                    cycle.append(x)
                    x = parent[x]
                cycle.append(w)
                cycle.reverse()
                return cycle
            if colour[w] == WHITE:
                parent[w] = u
                found = dfs(w)
                if found:
                    return found
        colour[u] = BLACK
        return None

    for v in nodes:
        if colour[v] == WHITE:
            parent[v] = None
            found = dfs(v)
            if found:
                return found
    return None
