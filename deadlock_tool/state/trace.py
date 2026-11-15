"""
trace.py — MODULE 1: build the system state from a PROCESS ACTIVITY TRACE and
monitor it automatically, event by event.

Instead of typing matrices, describe what the processes do — the kind of log a
lock manager, a database or an instrumented program produces:

    # comments start with '#'
    resource Printer 1          declare a resource type with 1 instance
    resource Disk 2
    P1 claims Printer 1         (optional) declare a maximum claim for avoidance
    P1 acquire Printer          ask for 1 unit; granted if free, otherwise P1 WAITS
    P2 acquire Disk 2           ask for 2 units
    P1 release Printer          give units back; waiting processes are served (FIFO)

Synonyms: acquire / request / lock / wait / wants;  release / free / unlock;
          claims / max.  Undeclared resources are created with 1 instance.

After EVERY event the full analysis runs (detection + Banker's safety +
lock-order analysis). The timeline reports the first event at which a
POTENTIAL deadlock appears and the first event at which a DEADLOCK occurs —
i.e. it pinpoints which request closed the circular wait.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from deadlock_tool.models import SystemState

ACQUIRE = {"acquire", "request", "requests", "lock", "locks", "wait", "waits", "wants", "acquires"}
RELEASE = {"release", "releases", "free", "frees", "unlock", "unlocks"}
CLAIM = {"claims", "claim", "max"}
NAME = re.compile(r"^[A-Za-z_][\w.\-]{0,13}$")

EXAMPLE = """# Two jobs share a printer and a scanner, but lock them in OPPOSITE orders.
resource Printer 1
resource Scanner 1
resource Disk 1
# Declared needs (optional) let the tool warn BEFORE the deadlock happens.
P1 claims Printer
P1 claims Scanner
P2 claims Scanner
P2 claims Printer
P1 acquire Printer
P2 acquire Scanner     # potential deadlock: P1 and P2 now hold what the other needs
P3 acquire Disk
P3 release Disk
P4 acquire Disk
P1 acquire Scanner     # P1 waits for P2
P2 acquire Printer     # ...and P2 waits for P1: circular wait!
P4 acquire Printer     # P4 gets stuck behind the deadlock
"""


class TraceError(ValueError):
    pass


def _ensure_resource(s: SystemState, name: str, total: int = 1) -> int:
    if name not in s.resources:
        if name in s.processes:
            raise TraceError("'%s' is already a process name" % name)
        s.resources.append(name)
        s.total.append(total)
        for rows in (s.allocation, s.request, s.max):
            for row in rows:
                row.append(0)
    return s.resources.index(name)


def _ensure_process(s: SystemState, name: str) -> int:
    if name not in s.processes:
        if name in s.resources:
            raise TraceError("'%s' is already a resource name" % name)
        s.processes.append(name)
        s.allocation.append([0] * s.m)
        s.request.append([0] * s.m)
        s.max.append([0] * s.m)
    return s.processes.index(name)


def _grant_waiters(s: SystemState, r: int) -> List[str]:
    """After a release, serve waiting processes in order (all-or-nothing per request)."""
    granted = []
    for i, p in enumerate(s.processes):
        q = s.request[i][r]
        if q > 0 and q <= s.available[r]:
            s.allocation[i][r] += q
            s.request[i][r] = 0
            granted.append("%s gets %s×%d" % (p, s.resources[r], q))
    return granted


def _parse_count(tok: Optional[str], line_no: int) -> int:
    if tok is None:
        return 1
    if not tok.isdigit() or int(tok) < 1 or int(tok) > 99:
        raise TraceError("line %d: count must be a whole number 1–99, got '%s'" % (line_no, tok))
    return int(tok)


def apply_event(s: SystemState, words: List[str], line_no: int) -> str:
    """Applies one parsed event to `s` in place and returns a human description."""
    if words[0].lower() == "resource":
        if len(words) not in (2, 3):
            raise TraceError("line %d: use 'resource <name> [instances]'" % line_no)
        name, total = words[1], _parse_count(words[2] if len(words) == 3 else None, line_no)
        if not NAME.match(name):
            raise TraceError("line %d: invalid resource name '%s'" % (line_no, name))
        if name in s.resources:
            r = s.resources.index(name)
            held = sum(row[r] for row in s.allocation)
            if total < held:
                raise TraceError("line %d: %s already has %d units allocated" % (line_no, name, held))
            s.total[r] = total
        else:
            _ensure_resource(s, name, total)
        return "Resource %s has %d instance%s" % (name, total, "" if total == 1 else "s")

    if len(words) not in (3, 4):
        raise TraceError("line %d: use '<process> acquire|release|claims <resource> [count]'" % line_no)
    proc, verb, res = words[0], words[1].lower(), words[2]
    count = _parse_count(words[3] if len(words) == 4 else None, line_no)
    for nm in (proc, res):
        if not NAME.match(nm):
            raise TraceError("line %d: invalid name '%s'" % (line_no, nm))
    if verb not in ACQUIRE | RELEASE | CLAIM:
        raise TraceError("line %d: unknown action '%s' (use acquire, release or claims)" % (line_no, words[1]))

    r = _ensure_resource(s, res)
    i = _ensure_process(s, proc)

    if verb in CLAIM:
        if count > s.total[r]:
            raise TraceError("line %d: %s claims %d %s but only %d exist" % (line_no, proc, count, res, s.total[r]))
        s.max[i][r] = count
        return "%s declares a maximum claim of %d %s" % (proc, count, res)

    if verb in ACQUIRE:
        if any(s.request[i]):
            waiting = [s.resources[k] for k in range(s.m) if s.request[i][k]]
            raise TraceError("line %d: %s is blocked waiting for %s and cannot issue another request"
                             % (line_no, proc, ", ".join(waiting)))
        if s.allocation[i][r] + count > s.total[r]:
            raise TraceError("line %d: %s asks for %d %s but only %d exist in total"
                             % (line_no, proc, count, res, s.total[r]))
        if count <= s.available[r]:
            s.allocation[i][r] += count
            return "%s acquires %s×%d (granted immediately)" % (proc, res, count)
        s.request[i][r] += count
        holders = [s.processes[j] for j in range(s.n) if j != i and s.allocation[j][r] > 0]
        return "%s requests %s×%d — not free, WAITS (held by %s)" % (proc, res, count, ", ".join(holders) or "nobody")

    # release
    if s.allocation[i][r] < count:
        raise TraceError("line %d: %s holds only %d %s, cannot release %d"
                         % (line_no, proc, s.allocation[i][r], res, count))
    s.allocation[i][r] -= count
    granted = _grant_waiters(s, r)
    return "%s releases %s×%d%s" % (proc, res, count, ("; " + "; ".join(granted)) if granted else "")


def _finalize_max(s: SystemState) -> SystemState:
    """Max claim = max(declared claim, what is held + waited for)."""
    out = s.clone()
    out.max = [[max(out.max[i][r], out.allocation[i][r] + out.request[i][r]) for r in range(out.m)]
               for i in range(out.n)]
    return out


def parse_events(text: str) -> List[Tuple[int, List[str]]]:
    events = []
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if line:
            events.append((no, line.split()))
    return events


def replay_trace(text: str, analyze_fn) -> Dict[str, Any]:
    """
    Replays the trace. `analyze_fn(state) -> (result, risk)` is injected by the
    caller so this module stays independent of the engine (Module 2).
    """
    if len(text) > 20000:
        return {"ok": False, "errors": ["Trace is too long (limit 20 000 characters)."]}
    events = parse_events(text)
    if not events:
        return {"ok": False, "errors": ["The trace is empty. Try the example."]}
    if len(events) > 300:
        return {"ok": False, "errors": ["Too many events (limit 300)."]}

    s = SystemState()
    timeline: List[Dict[str, Any]] = []
    first_risk = first_deadlock = None
    for no, words in events:
        try:
            desc = apply_event(s, words, no)
        except TraceError as e:
            return {"ok": False, "errors": [str(e)], "timeline": timeline}
        if s.n > 20 or s.m > 12:
            return {"ok": False, "errors": ["line %d: limit is 20 processes and 12 resources." % no], "timeline": timeline}
        snap = _finalize_max(s)
        result, risk = analyze_fn(snap)
        step = len(timeline) + 1
        if risk["level"] in ("high", "medium") and first_risk is None and first_deadlock is None:
            first_risk = step
        if result.is_deadlocked and first_deadlock is None:
            first_deadlock = step
        timeline.append({
            "step": step, "line": no, "event": " ".join(words), "description": desc,
            "level": risk["level"], "deadlocked": list(result.deadlocked), "blocked": list(result.blocked),
            "cycles": result.cycles, "state": snap.to_dict(),
        })

    final = timeline[-1]
    if first_deadlock:
        ev = timeline[first_deadlock - 1]
        summary = ("DEADLOCK at event #%d (%s): this request closed the circular wait %s."
                   % (first_deadlock, ev["event"], "; ".join(" → ".join(c) for c in ev["cycles"])))
        if first_risk:
            summary = ("Potential deadlock first flagged at event #%d (%s). " % (first_risk, timeline[first_risk - 1]["event"])
                       + summary)
    elif first_risk:
        summary = ("No deadlock occurred, but a POTENTIAL deadlock was flagged from event #%d (%s)."
                   % (first_risk, timeline[first_risk - 1]["event"]))
    else:
        summary = "No deadlock and no deadlock risk during the whole trace (%d events)." % len(timeline)
    return {
        "ok": True, "errors": [], "timeline": timeline, "summary": summary,
        "first_risk": first_risk, "first_deadlock": first_deadlock,
        "final_state": final["state"],
    }
