"""
prevention.py — MODULE 3: DEADLOCK PREVENTION.

Prevention makes deadlock structurally impossible by guaranteeing that at
least ONE of the four necessary conditions can never hold. For each condition
this module

  * finds the processes that currently violate the prevention protocol, and
  * simulates what the state looks like when the protocol is enforced,
    then re-checks it with the detection engine (verified, like recovery).

Mutual exclusion   cannot be denied for non-sharable resources -> explained only
Hold and wait      protocol: "all-or-nothing" — a process must request every
                   resource it needs at once and may not hold anything while
                   waiting. Violators release what they hold and re-request it
                   together with their pending request.
No preemption      protocol: if a process that holds resources requests one that
                   cannot be granted immediately, all its resources are
                   preempted (implicitly released) and added to its request list.
Circular wait      protocol: total ordering F(R1) < F(R2) < ... ; a process may
                   only request Rj if F(Rj) > F(Ri) for every Ri it holds.
                   Violators release the higher-ordered resources and re-request
                   them, so all requests go in increasing order.
                   (Proof that it works: along any wait-for cycle the order of the
                   resources would have to strictly increase forever.)

Nothing here touches real processes; the input state is never mutated.
"""

from __future__ import annotations

from typing import Any, Dict, List

from deadlock_tool.models import SystemState
from deadlock_tool.engine import analyze
from deadlock_tool.engine.cycles import build_adjacency, find_cycle_in


def _release_and_rerequest(state: SystemState, i: int, resources: List[int]) -> None:
    """In place: process i gives back `resources` and adds them to its pending request."""
    for r in resources:
        state.request[i][r] += state.allocation[i][r]
        state.allocation[i][r] = 0


def _hold_wait_violators(state: SystemState) -> List[int]:
    return [i for i in range(state.n) if any(state.allocation[i]) and any(state.request[i])]


def _no_preemption_violators(state: SystemState) -> List[int]:
    avail = state.available
    return [i for i in range(state.n)
            if any(state.allocation[i]) and any(state.request[i][r] > avail[r] for r in range(state.m))]


def _ordering_violations(state: SystemState) -> Dict[int, List[int]]:
    """process index -> held resources whose order F >= F(lowest requested resource)."""
    out: Dict[int, List[int]] = {}
    for i in range(state.n):
        wanted = [r for r in range(state.m) if state.request[i][r] > 0]
        if wanted:
            lowest = min(wanted)                     # F(Rj) = j + 1  (listed order)
            bad = [r for r in range(state.m) if state.allocation[i][r] > 0 and r >= lowest]
            if bad:
                out[i] = bad
    return out


_CHECKS = {
    "hold_and_wait": lambda s: bool(_hold_wait_violators(s)),
    "no_preemption": lambda s: bool(_no_preemption_violators(s)),
    "circular_wait": lambda s: bool(_ordering_violations(s)),
}


def _verify(after: SystemState, condition_key: str) -> Dict[str, Any]:
    res = analyze(after)
    wfg = build_adjacency(after.processes, [(e["from"], e["to"]) for e in res.wait_for_edges])
    return {
        "resolved": not res.is_deadlocked,
        "condition_broken": not _CHECKS[condition_key](after),
        "cycle_after": find_cycle_in(wfg),
        "after_state": after.to_dict(),
        "after_result": res.to_dict(),
    }


def _units(state: SystemState, i: int, rs: List[int]) -> str:
    return ", ".join("%s×%d" % (state.resources[r], state.allocation[i][r]) for r in rs if state.allocation[i][r])


def prevention_analysis(state: SystemState) -> List[Dict[str, Any]]:
    """Returns one entry per necessary condition with violators and a verified simulation."""
    before = analyze(state)
    cond = {c["key"]: c for c in before.conditions}
    n, m = state.n, state.m
    out: List[Dict[str, Any]] = []

    # ---- 1. Mutual exclusion ----------------------------------------------
    used = [state.resources[r] for r in range(m) if any(state.allocation[i][r] for i in range(n))]
    out.append({
        "key": "mutual_exclusion",
        "condition": "Mutual exclusion",
        "holds": cond["mutual_exclusion"]["holds"],
        "technique": "Make resources sharable",
        "rule": "Sharable resources (e.g. read-only files) never need exclusive access, so they cannot deadlock.",
        "violators": [],
        "actions": [],
        "simulated": False,
        "verdict": ("Cannot be prevented here: %s %s intrinsically non-sharable (a printer cannot print two jobs at once)."
                    % (", ".join(used), "is" if len(used) == 1 else "are")) if used
                   else "Nothing is allocated, so exclusive use is not an issue right now.",
        "drawbacks": ["In general we cannot deny mutual exclusion — some resources are non-sharable by nature."],
    })

    # ---- 2. Hold and wait -------------------------------------------------
    after = state.clone()
    violators, actions = [], []
    for i in _hold_wait_violators(state):
        violators.append(state.processes[i])
        actions.append("%s releases %s and re-requests everything at once"
                       % (state.processes[i], _units(state, i, list(range(m)))))
        _release_and_rerequest(after, i, list(range(m)))
    entry = {
        "key": "hold_and_wait",
        "condition": "Hold and wait",
        "holds": cond["hold_and_wait"]["holds"],
        "technique": "All-or-nothing allocation",
        "rule": "A process must request (and be allocated) ALL its resources before it starts, "
                "or release everything it holds before requesting more.",
        "violators": violators,
        "actions": actions,
        "simulated": bool(violators),
        "drawbacks": ["Low resource utilization: resources sit allocated but unused for a long time.",
                      "Starvation: a process needing several popular resources may wait indefinitely."],
    }
    if violators:
        entry.update(_verify(after, "hold_and_wait"))
    out.append(entry)

    # ---- 3. No preemption -------------------------------------------------
    after = state.clone()
    violators, actions = [], []
    for i in _no_preemption_violators(state):
        violators.append(state.processes[i])
        actions.append("%s cannot be served now → preempt %s; it restarts when it can regain them"
                       % (state.processes[i], _units(state, i, list(range(m)))))
        _release_and_rerequest(after, i, list(range(m)))
    entry = {
        "key": "no_preemption",
        "condition": "No preemption",
        "holds": cond["no_preemption"]["holds"],
        "technique": "Preempt on blocked request",
        "rule": "If a process holding resources requests one that cannot be granted immediately, "
                "all resources it holds are preempted and added to the list it is waiting for.",
        "violators": violators,
        "actions": actions,
        "simulated": bool(violators),
        "drawbacks": ["Only works for resources whose state can be saved and restored (CPU registers, memory) — "
                      "not for printers or tape drives.",
                      "Repeated preemption of the same process can lead to starvation."],
    }
    if violators:
        entry.update(_verify(after, "no_preemption"))
    out.append(entry)

    # ---- 4. Circular wait -------------------------------------------------
    after = state.clone()
    violators, actions = [], []
    for i, bad in _ordering_violations(state).items():
        lowest = min(r for r in range(m) if state.request[i][r] > 0)
        violators.append(state.processes[i])
        actions.append("%s holds %s but requests %s (F=%d) — releases %s and re-requests in increasing order"
                       % (state.processes[i], _units(state, i, bad), state.resources[lowest], lowest + 1,
                          _units(state, i, bad)))
        _release_and_rerequest(after, i, bad)
    entry = {
        "key": "circular_wait",
        "condition": "Circular wait",
        "holds": cond["circular_wait"]["holds"],
        "technique": "Resource ordering",
        "rule": "Number the resource types F(R) and request them only in strictly increasing order: "
                "a process holding Ri may request Rj only if F(Rj) > F(Ri).",
        "ordering": [{"resource": r, "order": k + 1} for k, r in enumerate(state.resources)],
        "violators": violators,
        "actions": actions,
        "simulated": bool(violators),
        "drawbacks": ["Programmers must follow the order; the ordering may not match the natural order of use.",
                      "Processes may have to acquire resources earlier than needed."],
    }
    if violators:
        entry.update(_verify(after, "circular_wait"))
    out.append(entry)

    for e in out:
        if e["key"] != "mutual_exclusion" and "verdict" not in e:
            if not e["violators"]:
                e["verdict"] = "No process violates this protocol — the condition is already denied."
            elif e.get("resolved"):
                e["verdict"] = "Verified: enforcing this protocol leaves the system deadlock-free."
            else:
                e["verdict"] = "Enforcing this protocol alone does not clear the deadlock."
    return out
