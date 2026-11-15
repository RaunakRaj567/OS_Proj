"""MODULE 1 — Input & State Management (validation, presets, random generator, process-trace replay)."""

from deadlock_tool.state.validation import validate
from deadlock_tool.state.scenarios import list_scenarios, load_scenario, random_scenario
from deadlock_tool.state.trace import EXAMPLE as TRACE_EXAMPLE, replay_trace

__all__ = ["validate", "list_scenarios", "load_scenario", "random_scenario", "replay_trace", "TRACE_EXAMPLE"]
