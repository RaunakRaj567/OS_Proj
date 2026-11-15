"""
detection.py — MODULE 2: the multi-instance deadlock DETECTION algorithm.

Intuition ("be optimistic")
---------------------------
If a process's CURRENT request fits in the free resources, assume it gets
them, runs to completion and returns everything it holds. Keep doing that.
Any process that can never be satisfied — even after every other process
has finished — is stuck forever: the system is deadlocked.

    Work   = Available
    Finish = [False] * n
    repeat:
        find i with Finish[i] == False and Request[i] <= Work
        if found:  Work += Allocation[i];  Finish[i] = True
    until nothing found
    deadlock  <=>  some Finish[i] is False

Works for single-instance AND multi-instance resources.
Time complexity: O(m * n^2)   (n processes, m resource types).

This is DETECTION, not avoidance: Banker's algorithm uses Need = Max - Allocation
(future demand) to decide whether to GRANT a request; we use the current Request
to decide whether the present state is already deadlocked.

Difference from the textbook (Silberschatz): the textbook initialises
Finish[i] = True for processes holding nothing. We start every process at False
so the tool can also report processes that hold nothing but are blocked BY the
deadlock. The deadlock yes/no answer is identical in both versions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from deadlock_tool.models import SystemState


def _fits(request: List[int], work: List[int]) -> bool:
    return all(request[r] <= work[r] for r in range(len(work)))


def run_detection(state: SystemState) -> Tuple[List[bool], List[str], List[int], List[Dict[str, Any]]]:
    """
    Runs the detection algorithm.

    Returns
    -------
    finish           : finish[i] is True if process i can complete
    completion_order : names of completing processes, in order
    final_work       : free units after all finishable processes finished
    trace            : list of events for step-by-step animation:
                       {"type": "check",  "pass": k, "process": P, "request": [...], "work": [...], "fits": bool}
                       {"type": "finish", "pass": k, "process": P, "released": [...], "work": [...]}
    """
    n, m = state.n, state.m
    work = state.available
    finish = [False] * n
    order: List[str] = []
    trace: List[Dict[str, Any]] = []

    progress = True
    pass_no = 0
    while progress:
        progress = False
        pass_no += 1
        for i in range(n):
            if finish[i]:
                continue
            fits = _fits(state.request[i], work)
            trace.append({
                "type": "check",
                "pass": pass_no,
                "process": state.processes[i],
                "request": list(state.request[i]),
                "work": list(work),
                "fits": fits,
            })
            if fits:
                work = [work[r] + state.allocation[i][r] for r in range(m)]
                finish[i] = True
                order.append(state.processes[i])
                progress = True
                trace.append({
                    "type": "finish",
                    "pass": pass_no,
                    "process": state.processes[i],
                    "released": list(state.allocation[i]),
                    "work": list(work),
                })

    return finish, order, work, trace
