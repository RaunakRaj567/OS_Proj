"""
analyzer.py — MODULE 2 entry point:  analyze(SystemState) -> DetectionResult

Pipeline
--------
1. run_detection()            decides: which processes can finish, which are stuck
2. stuck_wait_for_edges()     who-waits-for-whom among the stuck processes
3. strongly_connected_components()
                              groups of stuck processes in a circular wait
                              -> members are DEADLOCKED, other stuck ones are BLOCKED
4. find_cycle_in()            one readable example cycle per group
5. evaluate_conditions()      DEADLOCK CHARACTERIZATION: the four necessary conditions
6. explanations               plain-English sentences for the UI and report

The caller must validate the state first (Module 1). analyze() assumes it is valid.
"""

from __future__ import annotations

from typing import Dict, List

from deadlock_tool.models import DetectionResult, SystemState
from deadlock_tool.engine.detection import run_detection
from deadlock_tool.engine.wait_for_graph import current_wait_for_edges, stuck_wait_for_edges
from deadlock_tool.engine.cycles import build_adjacency, find_cycle_in, strongly_connected_components
from deadlock_tool.engine.characterization import characterization_summary, evaluate_conditions


def _units(state: SystemState, row: List[int]) -> str:
    parts = ["%s×%d" % (state.resources[r], row[r]) for r in range(state.m) if row[r] > 0]
    return ", ".join(parts) if parts else "nothing"


def _holders(state: SystemState, r: int, exclude: int, among: List[int]) -> List[str]:
    return [state.processes[j] for j in among if j != exclude and state.allocation[j][r] > 0]


def analyze(state: SystemState) -> DetectionResult:
    n = state.n
    idx = {p: i for i, p in enumerate(state.processes)}

    # 1. detection algorithm -------------------------------------------------
    finish, order, final_work, trace = run_detection(state)
    stuck = [i for i in range(n) if not finish[i]]

    # 2-3. who is in the circular wait? -------------------------------------
    stuck_edges = stuck_wait_for_edges(state, finish, final_work)
    stuck_names = [state.processes[i] for i in stuck]
    graph = build_adjacency(stuck_names, [(e["from"], e["to"]) for e in stuck_edges])

    groups = [c for c in strongly_connected_components(graph) if len(c) >= 2]
    groups = [sorted(g, key=idx.get) for g in groups]
    groups.sort(key=lambda g: idx[g[0]])
    group_of: Dict[str, int] = {p: k for k, g in enumerate(groups) for p in g}

    deadlocked = sorted(group_of, key=idx.get)
    blocked = [p for p in stuck_names if p not in group_of]
    deadlock_edges = [
        e for e in stuck_edges
        if e["from"] in group_of and group_of.get(e["to"]) == group_of[e["from"]]
    ]

    # 4. one example cycle per group -----------------------------------------
    cycles = []
    for g in groups:
        cyc = find_cycle_in(graph, allowed=set(g))
        if cyc:
            cycles.append(cyc)

    # Current-state wait-for graph (for the WFG view) ------------------------
    wfg_edges = current_wait_for_edges(state)
    wfg = build_adjacency(state.processes, [(e["from"], e["to"]) for e in wfg_edges])
    wfg_cycle = find_cycle_in(wfg)
    is_deadlocked = len(stuck) > 0
    cycle_without_deadlock = (wfg_cycle is not None) and not is_deadlocked

    status = {}
    for p in state.processes:
        if p in group_of:
            status[p] = "deadlocked"
        elif p in blocked:
            status[p] = "blocked"
        else:
            status[p] = "completes"

    # 5. characterization --------------------------------------------------
    conditions = evaluate_conditions(state, wfg_cycle)

    # 6. explanations -------------------------------------------------------
    exp: List[str] = []
    available = state.available
    if n == 0:
        exp.append("The system is empty — add processes and resources to analyse it.")
    elif not is_deadlocked:
        exp.append(
            "No deadlock. All %d processes can finish, in the order %s."
            % (n, " → ".join(order))
        )
        for i in range(n):
            waiting = [r for r in range(state.m) if state.request[i][r] > available[r]]
            if waiting:
                r = waiting[0]
                exp.append(
                    "%s is only waiting temporarily: it needs %s×%d (%d free now) "
                    "but will get it once earlier processes release their resources."
                    % (state.processes[i], state.resources[r], state.request[i][r], available[r])
                )
        if cycle_without_deadlock:
            exp.append(
                "The wait-for graph contains a cycle (%s), but this is NOT a deadlock: "
                "a resource on that cycle has multiple instances and processes outside "
                "the cycle will release them. With multi-instance resources a cycle is "
                "necessary but not sufficient for deadlock."
                % " → ".join(wfg_cycle)
            )
    else:
        exp.append(
            "DEADLOCK DETECTED: %d process%s in circular wait (%s)."
            % (len(deadlocked), "" if len(deadlocked) == 1 else "es",
               "; ".join(" → ".join(c) for c in cycles))
        )
        for p in deadlocked:
            i = idx[p]
            reasons = []
            for r in range(state.m):
                if state.request[i][r] > final_work[r]:
                    holders = _holders(state, r, i, stuck)
                    reasons.append(
                        "%s×%d (held by %s)"
                        % (state.resources[r], state.request[i][r], ", ".join(holders) or "nobody")
                    )
            exp.append(
                "%s holds %s and waits for %s."
                % (p, _units(state, state.allocation[i]), "; ".join(reasons))
            )
        for p in blocked:
            i = idx[p]
            reasons = []
            for r in range(state.m):
                if state.request[i][r] > final_work[r]:
                    holders = _holders(state, r, i, stuck)
                    reasons.append("%s held by %s" % (state.resources[r], ", ".join(holders)))
            exp.append(
                "%s is not part of the cycle but is BLOCKED by it: it waits for %s, "
                "which will never be released." % (p, "; ".join(reasons))
            )
        if order:
            exp.append("%s can still finish normally." % ", ".join(order))
    if n > 0:
        exp.append(characterization_summary(state, conditions, is_deadlocked))

    return DetectionResult(
        is_deadlocked=is_deadlocked,
        status=status,
        completion_order=order,
        deadlocked=deadlocked,
        blocked=blocked,
        groups=groups,
        cycles=cycles,
        wait_for_edges=wfg_edges,
        deadlock_edges=deadlock_edges,
        cycle_without_deadlock=cycle_without_deadlock,
        available=available,
        final_work=final_work,
        trace=trace,
        explanations=exp,
        conditions=conditions,
    )
