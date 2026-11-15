"""
wait_for_graph.py — MODULE 2: builds Wait-For Graphs (process -> process).

Edge  Pi -> Pj  (labelled with resource r)  means:
"Pi is waiting for units of r, and Pj holds some of them."

Two variants are built:

1. current_wait_for_edges(state)
   The ordinary WFG of the current state: Pi waits on r when
   Request[i][r] > Available[r]. Useful for visualisation. With
   multi-instance resources a cycle here does NOT prove a deadlock.

2. stuck_wait_for_edges(state, finish, final_work)
   Built only among the processes the detection algorithm could NOT finish,
   using the free units left at the end (final_work). Every stuck process has
   at least one outgoing edge here, so this graph always contains a cycle when
   the stuck set is non-empty — that cycle IS the circular wait that causes
   the deadlock.
"""

from __future__ import annotations

from typing import Dict, List

from deadlock_tool.models import SystemState

Edge = Dict[str, str]


def _edges(state: SystemState, members: List[int], free: List[int]) -> List[Edge]:
    edges: List[Edge] = []
    member_set = set(members)
    for i in members:
        for r in range(state.m):
            if state.request[i][r] > 0 and state.request[i][r] > free[r]:
                for j in range(state.n):
                    if j != i and j in member_set and state.allocation[j][r] > 0:
                        edges.append({
                            "from": state.processes[i],
                            "to": state.processes[j],
                            "resource": state.resources[r],
                        })
    return edges


def current_wait_for_edges(state: SystemState) -> List[Edge]:
    return _edges(state, list(range(state.n)), state.available)


def stuck_wait_for_edges(state: SystemState, finish: List[bool], final_work: List[int]) -> List[Edge]:
    stuck = [i for i in range(state.n) if not finish[i]]
    return _edges(state, stuck, final_work)
