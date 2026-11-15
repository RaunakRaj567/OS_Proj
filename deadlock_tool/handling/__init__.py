"""MODULE 3 — Resolution strategies: suggested resolutions (recovery or mitigation),
prevention protocols and starvation control."""

from deadlock_tool.handling.prevention import prevention_analysis
from deadlock_tool.handling.resolution import suggest_resolutions
from deadlock_tool.handling.starvation import simulate_starvation

__all__ = ["prevention_analysis", "suggest_resolutions", "simulate_starvation"]
