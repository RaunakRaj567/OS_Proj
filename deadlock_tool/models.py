"""
models.py — the shared data contract between the three modules.

    Module 1 (state)     builds a SystemState
    Module 2 (engine)    characterization, detection and avoidance (Banker's)
    Module 3 (handling)  prevention, recovery and starvation control, plus the visual side

Everything here is plain Python data so it can be converted to/from JSON
for the web frontend and for the scenario files.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List


@dataclass
class SystemState:
    """
    A snapshot of the simulated system.

    processes  : process names, e.g. ["P1", "P2"]
    resources  : resource type names, e.g. ["Printer", "Disk"]
    total      : total instances of each resource type     (length m)
    allocation : allocation[i][r] = units of r HELD by process i   (n x m)
    request    : request[i][r]    = units of r process i is WAITING for (n x m)
    max        : max[i][r]        = MAXIMUM units of r process i may ever claim (n x m),
                 used only by deadlock AVOIDANCE (Banker's algorithm).
                 Optional: if empty, the claim defaults to Allocation + Request.

    `request` is what a process is blocked on *right now* (used by DETECTION);
    `max` is its declared future demand (used by AVOIDANCE: Need = Max - Allocation).
    """

    processes: List[str] = field(default_factory=list)
    resources: List[str] = field(default_factory=list)
    total: List[int] = field(default_factory=list)
    allocation: List[List[int]] = field(default_factory=list)
    request: List[List[int]] = field(default_factory=list)
    max: List[List[int]] = field(default_factory=list)

    # ---- derived values -------------------------------------------------
    @property
    def n(self) -> int:
        return len(self.processes)

    @property
    def m(self) -> int:
        return len(self.resources)

    @property
    def available(self) -> List[int]:
        """Available[r] = Total[r] - sum of Allocation[i][r] over all processes."""
        return [
            self.total[r] - sum(self.allocation[i][r] for i in range(self.n))
            for r in range(self.m)
        ]

    @property
    def claim(self) -> List[List[int]]:
        """Max claim matrix; defaults to Allocation + Request when no Max was declared."""
        if self.max:
            return self.max
        return [[self.allocation[i][r] + self.request[i][r] for r in range(self.m)] for i in range(self.n)]

    @property
    def need(self) -> List[List[int]]:
        """Banker's Need[i][r] = Max[i][r] - Allocation[i][r]."""
        mx = self.claim
        return [[mx[i][r] - self.allocation[i][r] for r in range(self.m)] for i in range(self.n)]

    # ---- helpers used by the recovery simulator ------------------------
    def clone(self) -> "SystemState":
        return copy.deepcopy(self)

    def without_process(self, name: str) -> "SystemState":
        """Returns a copy with process `name` terminated (its resources are released)."""
        s = self.clone()
        i = s.processes.index(name)
        del s.processes[i]
        del s.allocation[i]
        del s.request[i]
        if s.max:
            del s.max[i]
        return s

    # ---- JSON conversion ------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "processes": list(self.processes),
            "resources": list(self.resources),
            "total": list(self.total),
            "allocation": [list(row) for row in self.allocation],
            "request": [list(row) for row in self.request],
            "max": [list(row) for row in self.claim],
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "SystemState":
        """Builds a SystemState from a dict. Shape/type problems are reported by validation."""
        return SystemState(
            processes=[str(p) for p in data.get("processes", [])],
            resources=[str(r) for r in data.get("resources", [])],
            total=list(data.get("total", [])),
            allocation=[list(row) for row in data.get("allocation", [])],
            request=[list(row) for row in data.get("request", [])],
            max=[list(row) for row in (data.get("max") or [])],
        )


@dataclass
class DetectionResult:
    """
    Output of the characterization + detection engine (Module 2).

    is_deadlocked     : True if at least one process can never proceed
    status            : process -> "completes" | "deadlocked" | "blocked"
    completion_order  : processes that can finish, in the order the algorithm finished them
    deadlocked        : processes ON a circular wait (members of a deadlock group)
    blocked           : stuck processes NOT on a cycle (waiting on a deadlocked holder)
    groups            : each deadlock group (strongly connected set of stuck processes)
    cycles            : one example cycle per group, e.g. ["P1", "P2", "P1"]
    wait_for_edges    : current-state wait-for graph [{"from","to","resource"}]
    deadlock_edges    : wait-for edges that lie on a deadlock cycle
    cycle_without_deadlock : the wait-for graph has a cycle but the system is NOT
                             deadlocked (only possible with multi-instance resources)
    available         : free units before the algorithm runs
    final_work        : free units after every finishable process has finished
    trace             : step-by-step events of the detection algorithm (for animation)
    explanations      : plain-English sentences
    conditions        : the four necessary (Coffman) conditions, evaluated on this state
    """

    is_deadlocked: bool
    status: Dict[str, str]
    completion_order: List[str]
    deadlocked: List[str]
    blocked: List[str]
    groups: List[List[str]]
    cycles: List[List[str]]
    wait_for_edges: List[Dict[str, str]]
    deadlock_edges: List[Dict[str, str]]
    cycle_without_deadlock: bool
    available: List[int]
    final_work: List[int]
    trace: List[Dict[str, Any]]
    explanations: List[str]
    conditions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
