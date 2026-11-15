"""
validation.py — MODULE 1: the gatekeeper.

The detection engine assumes a consistent state. This module checks every
rule and returns human-readable error messages. An empty list means valid.

Rules
-----
1. Names are non-empty and unique (process and resource names must not clash,
   because both become node IDs in the graph).
2. Matrix shapes match: n rows, m columns.
3. All numbers are non-negative integers.
4. A resource is never over-allocated:  sum_i Allocation[i][r] <= Total[r]
5. Every request is satisfiable in principle:  Allocation[i][r] + Request[i][r] <= Total[r]
   (otherwise the process could never run even if everyone else finished —
    that is an invalid request, NOT a deadlock).
6. Max claim (only if declared, used by Banker's avoidance):
   Max[i][r] <= Total[r]                 a process can't claim more than exists
   Allocation[i][r] + Request[i][r] <= Max[i][r]
                                         a process can't exceed its declared maximum claim
"""

from __future__ import annotations

from typing import Any, List

from deadlock_tool.models import SystemState

MAX_PROCESSES = 20
MAX_RESOURCES = 12
MAX_INSTANCES = 99


def _is_count(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def validate(state: SystemState) -> List[str]:
    errors: List[str] = []
    n, m = state.n, state.m

    # ---- 1. names ---------------------------------------------------------
    if n > MAX_PROCESSES:
        errors.append(f"Too many processes ({n}); the limit is {MAX_PROCESSES}.")
    if m > MAX_RESOURCES:
        errors.append(f"Too many resource types ({m}); the limit is {MAX_RESOURCES}.")

    for kind, names in (("Process", state.processes), ("Resource", state.resources)):
        seen = set()
        for name in names:
            if not name.strip():
                errors.append(f"{kind} names cannot be empty.")
            elif name in seen:
                errors.append(f"{kind} name '{name}' is used more than once.")
            seen.add(name)

    clash = set(state.processes) & set(state.resources)
    for name in sorted(clash):
        errors.append(f"'{name}' is used as both a process and a resource name.")

    # ---- 2. shapes --------------------------------------------------------
    if len(state.total) != m:
        errors.append(f"Total instances must list {m} values (one per resource).")
        return errors
    matrices = [("Allocation", state.allocation), ("Request", state.request)]
    if state.max:
        matrices.append(("Max", state.max))
    for label, matrix in matrices:
        if len(matrix) != n or any(len(row) != m for row in matrix):
            errors.append(f"{label} matrix must be {n} x {m} (processes x resources).")
            return errors

    # ---- 3. non-negative integers ----------------------------------------
    for r, t in enumerate(state.total):
        if not _is_count(t):
            errors.append(f"Total instances of {state.resources[r]} must be a whole number >= 0.")
        elif t > MAX_INSTANCES:
            errors.append(f"{state.resources[r]} has {t} instances; the limit is {MAX_INSTANCES}.")
    for label, matrix in matrices:
        for i in range(n):
            for r in range(m):
                if not _is_count(matrix[i][r]):
                    errors.append(
                        f"{label}[{state.processes[i]}][{state.resources[r]}] must be a whole number >= 0."
                    )
    if errors:
        return errors

    # ---- 4. over-allocation ----------------------------------------------
    for r in range(m):
        allocated = sum(state.allocation[i][r] for i in range(n))
        if allocated > state.total[r]:
            errors.append(
                f"{state.resources[r]} is over-allocated: {allocated} units held "
                f"but only {state.total[r]} exist."
            )

    # ---- 5. impossible requests ------------------------------------------
    for i in range(n):
        for r in range(m):
            need = state.allocation[i][r] + state.request[i][r]
            if state.request[i][r] > 0 and need > state.total[r]:
                errors.append(
                    f"{state.processes[i]} holds {state.allocation[i][r]} and requests "
                    f"{state.request[i][r]} more {state.resources[r]}, but only "
                    f"{state.total[r]} exist — this request can never be granted "
                    f"(invalid input, not a deadlock)."
                )

    # ---- 6. max claim (Banker's) -----------------------------------------
    if state.max and not errors:
        for i in range(n):
            for r in range(m):
                p, res, mx = state.processes[i], state.resources[r], state.max[i][r]
                if mx > state.total[r]:
                    errors.append(
                        f"Max[{p}][{res}] = {mx} but only {state.total[r]} {res} exist — "
                        f"a process cannot claim more than the system has."
                    )
                elif state.allocation[i][r] + state.request[i][r] > mx:
                    errors.append(
                        f"{p} holds {state.allocation[i][r]} + requests {state.request[i][r]} {res}, "
                        f"which exceeds its declared maximum claim of {mx}."
                    )

    return errors
