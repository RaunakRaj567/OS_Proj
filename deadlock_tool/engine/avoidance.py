"""
avoidance.py — MODULE 2: DEADLOCK AVOIDANCE with the Banker's algorithm.

Avoidance needs a-priori information: every process declares its MAXIMUM
claim (Max). The system then grants a request only if the resulting state is
SAFE.

    Need[i] = Max[i] - Allocation[i]

Safe state: there is a sequence <P_a, P_b, ...> (a SAFE SEQUENCE) such that
each process's remaining Need can be satisfied by the currently available
resources plus everything held by the processes before it in the sequence.

    safe state      =>  no deadlock
    unsafe state    =>  deadlock is POSSIBLE (not certain)
    deadlocked      =>  unsafe          (deadlocked states ⊂ unsafe states)

1. Safety algorithm                                   O(m · n²)
       Work = Available ; Finish[i] = False
       repeat: find i with !Finish[i] and Need[i] <= Work
               Work += Allocation[i] ; Finish[i] = True
       safe  <=>  all Finish[i] are True

2. Resource-request algorithm (process Pi asks for vector Req)
       a. Req <= Need[i]      else ERROR: exceeds maximum claim
       b. Req <= Available    else Pi must WAIT (resources not free)
       c. Pretend to allocate:  Available -= Req; Allocation[i] += Req; Need[i] -= Req
          run the safety algorithm on the new state:
            safe   -> GRANT the request
            unsafe -> Pi must WAIT; the old state is restored

Note how the safety algorithm is the detection algorithm with Request replaced
by Need: detection asks "can everybody finish given what they wait for NOW?",
avoidance asks "can everybody finish even if they claim their MAXIMUM?".
"""

from __future__ import annotations

from typing import Any, Dict, List

from deadlock_tool.models import SystemState


def _le(a: List[int], b: List[int]) -> bool:
    return all(x <= y for x, y in zip(a, b))


def safety_check(state: SystemState) -> Dict[str, Any]:
    """Runs the Banker's safety algorithm. Returns safe flag, safe sequence and a step trace."""
    n, m = state.n, state.m
    need = state.need
    work = state.available
    finish = [False] * n
    sequence: List[str] = []
    trace: List[Dict[str, Any]] = []

    progress, pass_no = True, 0
    while progress:
        progress = False
        pass_no += 1
        for i in range(n):
            if finish[i]:
                continue
            fits = _le(need[i], work)
            trace.append({"type": "check", "pass": pass_no, "process": state.processes[i],
                          "need": list(need[i]), "work": list(work), "fits": fits})
            if fits:
                work = [work[r] + state.allocation[i][r] for r in range(m)]
                finish[i] = True
                sequence.append(state.processes[i])
                progress = True
                trace.append({"type": "finish", "pass": pass_no, "process": state.processes[i],
                              "released": list(state.allocation[i]), "work": list(work)})

    safe = all(finish)
    unsafe_procs = [state.processes[i] for i in range(n) if not finish[i]]
    if n == 0:
        msg = "No processes: the empty state is trivially safe."
    elif safe:
        msg = ("SAFE STATE. Safe sequence ⟨%s⟩: even if every process claims its maximum, "
               "each one can finish in this order. A safe state can never deadlock." % ", ".join(sequence))
    else:
        msg = ("UNSAFE STATE. No safe sequence exists: %s could not be guaranteed to finish if they "
               "claim their maximum. Deadlock is possible (not certain) — the Banker's algorithm would "
               "never have entered this state." % ", ".join(unsafe_procs))
    return {
        "safe": safe,
        "sequence": sequence,
        "unsafe": unsafe_procs,
        "need": need,
        "max": [list(r) for r in state.claim],
        "available": state.available,
        "trace": trace,
        "message": msg,
    }


def request_resources(state: SystemState, process: str, req: List[int]) -> Dict[str, Any]:
    """
    Banker's resource-request algorithm. Never mutates `state`.
    Returns {decision: "grant" | "wait" | "error", steps: [...], after_state?, safety?}.
    """
    if process not in state.processes:
        return {"decision": "error", "steps": [{"ok": False, "text": "Unknown process %s." % process}]}
    if len(req) != state.m or any((not isinstance(x, int)) or isinstance(x, bool) or x < 0 for x in req):
        return {"decision": "error", "steps": [{"ok": False, "text": "The request must be %d whole numbers ≥ 0." % state.m}]}

    i = state.processes.index(process)
    need, avail = state.need[i], state.available
    steps: List[Dict[str, Any]] = []
    vec = lambda v: "[" + ", ".join(str(x) for x in v) + "]"

    if not any(req):
        return {"decision": "error", "steps": [{"ok": False, "text": "Empty request — ask for at least one unit."}]}

    ok1 = _le(req, need)
    steps.append({"ok": ok1, "text": "Step 1 · Request %s ≤ Need %s ?" % (vec(req), vec(need))
                  + ("  ✓" if ok1 else "  ✗ — ERROR: the process has exceeded its maximum claim.")})
    if not ok1:
        return {"decision": "error", "steps": steps}

    ok2 = _le(req, avail)
    steps.append({"ok": ok2, "text": "Step 2 · Request %s ≤ Available %s ?" % (vec(req), vec(avail))
                  + ("  ✓" if ok2 else "  ✗ — resources are not free: %s must WAIT." % process)})
    if not ok2:
        return {"decision": "wait", "steps": steps}

    after = state.clone()
    if not after.max:
        after.max = [list(r) for r in state.claim]
    after.allocation[i] = [after.allocation[i][r] + req[r] for r in range(state.m)]
    after.request[i] = [max(0, after.request[i][r] - req[r]) for r in range(state.m)]
    safety = safety_check(after)
    steps.append({"ok": True, "text": "Step 3 · Pretend to allocate: Available = %s, Allocation[%s] = %s, Need[%s] = %s"
                  % (vec(after.available), process, vec(after.allocation[i]), process, vec(after.need[i]))})
    steps.append({"ok": safety["safe"], "text": "Safety algorithm on the new state → " + (
        "SAFE, sequence ⟨%s⟩. Request GRANTED." % ", ".join(safety["sequence"]) if safety["safe"]
        else "UNSAFE. Request DENIED: %s must wait and the old state is restored." % process)})
    return {
        "decision": "grant" if safety["safe"] else "wait",
        "steps": steps,
        "after_state": after.to_dict(),
        "safety": safety,
    }
