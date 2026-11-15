"""
potential.py — MODULE 2: POTENTIAL deadlock detection (risk assessment).

The detection algorithm (detection.py) answers "is the system deadlocked NOW?".
This module answers the harder, more useful question: "COULD these processes
deadlock, given how they depend on each other and on the resources?"

Three findings, from most to least severe
-----------------------------------------
1. DEADLOCK (actual)        the detection algorithm found a circular wait.

2. UNSAFE STATE (high)      Banker's safety algorithm (avoidance.py) finds no
                            safe sequence: if the processes claim their declared
                            maximum, the system cannot guarantee that everybody
                            finishes. Deadlock is possible but has not happened.
                            (Needs declared Max claims; without them Need = Request.)

3. LOCK-ORDER INVERSION     Resource-acquisition graph (the idea behind Linux
   (medium)                 "lockdep"): edge  Ra -> Rb  when some process HOLDS Ra
                            and still NEEDS Rb, i.e. it acquires Ra before Rb.
                            A cycle  Ra -> Rb -> Ra  means two (or more) processes
                            acquire the same resources in OPPOSITE orders. Today
                            they may get lucky, but a different interleaving
                            produces a circular wait. A global acquisition order
                            makes this cycle — and therefore circular wait —
                            impossible.

The process-dependency graph used for the explanation is the "potential
wait-for graph": Pi -> Pj (on r) when Pi still NEEDS r and Pj holds r.
"""

from __future__ import annotations

from typing import Any, Dict, List

from deadlock_tool.models import DetectionResult, SystemState
from deadlock_tool.engine.cycles import build_adjacency, find_cycle_in, strongly_connected_components


def lock_order_edges(state: SystemState) -> List[Dict[str, str]]:
    """Resource-acquisition edges: holder of `from` still needs `to`."""
    need = state.need
    edges: List[Dict[str, str]] = []
    for i, p in enumerate(state.processes):
        for a in range(state.m):
            if state.allocation[i][a] <= 0:
                continue
            for b in range(state.m):
                if b != a and need[i][b] > 0:
                    edges.append({"from": state.resources[a], "to": state.resources[b], "process": p})
    return edges


def lock_order_cycles(state: SystemState) -> List[Dict[str, Any]]:
    """Cycles in the resource-acquisition graph, each with the processes that create it."""
    edges = lock_order_edges(state)
    graph = build_adjacency(state.resources, [(e["from"], e["to"]) for e in edges])
    out = []
    for comp in strongly_connected_components(graph):
        if len(comp) < 2:
            continue
        cyc = find_cycle_in(graph, allowed=set(comp))
        if not cyc:
            continue
        hops = []
        for k in range(len(cyc) - 1):
            procs = sorted({e["process"] for e in edges if e["from"] == cyc[k] and e["to"] == cyc[k + 1]},
                           key=state.processes.index)
            hops.append({"from": cyc[k], "to": cyc[k + 1], "processes": procs})
        involved = sorted({p for h in hops for p in h["processes"]}, key=state.processes.index)
        if len(involved) < 2:          # one process alone cannot deadlock with itself
            continue
        out.append({"cycle": cyc, "hops": hops, "processes": involved})
    return out


def potential_wait_for_edges(state: SystemState) -> List[Dict[str, str]]:
    """Pi -> Pj on r: Pi still needs r (beyond what is free) and Pj holds some r."""
    need, avail = state.need, state.available
    edges = []
    for i in range(state.n):
        for r in range(state.m):
            if need[i][r] > 0 and need[i][r] > avail[r]:
                for j in range(state.n):
                    if j != i and state.allocation[j][r] > 0:
                        edges.append({"from": state.processes[i], "to": state.processes[j],
                                      "resource": state.resources[r]})
    return edges


def assess_risk(state: SystemState, result: DetectionResult, safety: Dict[str, Any]) -> Dict[str, Any]:
    """Combines actual detection, Banker's safety and lock-order analysis into one risk report."""
    findings: List[Dict[str, Any]] = []
    lo = lock_order_cycles(state)

    if result.is_deadlocked:
        for cyc in result.cycles:
            findings.append({
                "severity": "deadlock", "kind": "circular_wait",
                "title": "Circular wait: " + " → ".join(cyc),
                "detail": "These processes are blocked on each other right now and none can ever proceed.",
                "processes": cyc[:-1],
            })
        if result.blocked:
            findings.append({
                "severity": "deadlock", "kind": "blocked",
                "title": "Blocked by the deadlock: " + ", ".join(result.blocked),
                "detail": "Not on the cycle, but waiting for resources held by deadlocked processes.",
                "processes": list(result.blocked),
            })

    if not safety["safe"] and not result.is_deadlocked:
        findings.append({
            "severity": "high", "kind": "unsafe",
            "title": "Unsafe state: no safe sequence for " + ", ".join(safety["unsafe"]),
            "detail": "If these processes request their declared maximum, the free resources cannot satisfy them "
                      "in any order. The system is not deadlocked yet, but a deadlock can now occur.",
            "processes": list(safety["unsafe"]),
        })

    for c in lo:
        order_txt = "; ".join("%s take%s %s before %s" % (", ".join(h["processes"]),
                                                          "s" if len(h["processes"]) == 1 else "",
                                                          h["from"], h["to"]) for h in c["hops"])
        findings.append({
            "severity": "deadlock" if result.is_deadlocked else "medium", "kind": "lock_order",
            "title": "Lock-order inversion: " + " → ".join(c["cycle"]),
            "detail": "Processes acquire the same resources in opposite orders (%s). A different interleaving "
                      "produces a circular wait." % order_txt,
            "processes": c["processes"],
            "resources": c["cycle"][:-1],
        })

    if result.is_deadlocked:
        level = "deadlock"
    elif not safety["safe"]:
        level = "high"
    elif lo:
        level = "medium"
    else:
        level = "none"

    at_risk = sorted({p for f in findings for p in f["processes"]}, key=state.processes.index)
    headline = {
        "deadlock": "Deadlock detected: %d process(es) in circular wait." % len(result.deadlocked),
        "high": "Potential deadlock: the state is UNSAFE. A deadlock can occur if the processes claim their maximum.",
        "medium": "Potential deadlock: processes acquire resources in conflicting orders (lock-order inversion).",
        "none": "No deadlock and no deadlock risk: the state is safe and resources are acquired in a consistent order.",
    }[level]
    if state.n == 0:
        headline = "The system is empty."
    return {
        "level": level,
        "headline": headline,
        "findings": findings,
        "at_risk": at_risk,
        "lock_order_edges": lock_order_edges(state),
        "lock_order_cycles": lo,
        "potential_wait_for_edges": potential_wait_for_edges(state),
    }


def risk_of(state: SystemState) -> Dict[str, Any]:
    """Convenience: full risk report for a state."""
    from deadlock_tool.engine.analyzer import analyze
    from deadlock_tool.engine.avoidance import safety_check
    return assess_risk(state, analyze(state), safety_check(state))
