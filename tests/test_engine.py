"""
Tests. Core: automatic detection of actual and POTENTIAL deadlocks (circular
wait, unsafe state, lock-order inversion), process-trace monitoring and verified
resolution strategies. Supporting syllabus topics: characterization,
prevention, avoidance, recovery and starvation. Run with either:
    python -m pytest -v
    python -m unittest discover tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deadlock_tool.models import SystemState
from deadlock_tool.state import validate, list_scenarios, load_scenario, random_scenario
from deadlock_tool.engine import analyze
from deadlock_tool.engine.cycles import build_adjacency, find_cycle_in, strongly_connected_components
from deadlock_tool.engine import assess_risk, request_resources, safety_check
from deadlock_tool.engine.potential import risk_of
from deadlock_tool.handling import prevention_analysis, simulate_starvation, suggest_resolutions
from deadlock_tool.state import TRACE_EXAMPLE, replay_trace
from deadlock_tool.output import suggest_recoveries, build_report

try:
    import networkx as nx
except ImportError:  # optional cross-check
    nx = None


def state_of(sc):
    return SystemState.from_dict(sc)


class TestPresetScenarios(unittest.TestCase):
    """Every preset JSON carries its expected result — the demo and the tests can't drift apart."""

    def test_all_presets_match_expected(self):
        scenarios = list_scenarios()
        self.assertGreaterEqual(len(scenarios), 16)
        for meta in scenarios:
            sc = load_scenario(meta["id"])
            exp = sc["expected"]
            with self.subTest(scenario=meta["id"]):
                errors = validate(state_of(sc))
                if not exp["valid"]:
                    self.assertTrue(errors, "invalid scenario must be rejected")
                    continue
                self.assertEqual(errors, [])
                res = analyze(state_of(sc))
                self.assertEqual(res.deadlocked, exp["deadlocked"])
                self.assertEqual(res.blocked, exp["blocked"])
                self.assertEqual(res.completion_order, exp["completion_order"])
                self.assertEqual(res.is_deadlocked, bool(exp["deadlocked"] or exp["blocked"]))
                if "risk" in exp:
                    self.assertEqual(risk_of(state_of(sc))["level"], exp["risk"])
                if "safe" in exp:
                    sf = safety_check(state_of(sc))
                    self.assertEqual(sf["safe"], exp["safe"])
                    if exp["safe"]:
                        self.assertEqual(sf["sequence"], exp["safe_sequence"])


class TestDetectionDetails(unittest.TestCase):
    def test_cycle_without_deadlock_flag(self):
        res = analyze(state_of(load_scenario("t04_cycle_no_deadlock")))
        self.assertFalse(res.is_deadlocked)
        self.assertTrue(res.cycle_without_deadlock)

    def test_cycles_and_deadlock_edges(self):
        res = analyze(state_of(load_scenario("t03_three_cycle")))
        self.assertEqual(len(res.cycles), 1)
        cyc = res.cycles[0]
        self.assertEqual(cyc[0], cyc[-1])
        self.assertEqual(sorted(cyc[:-1]), ["P1", "P2", "P3"])
        self.assertEqual(len(res.deadlock_edges), 3)

    def test_two_independent_groups(self):
        res = analyze(state_of(load_scenario("t10_db_transactions")))
        self.assertEqual(res.groups, [["T1", "T2"], ["T3", "T4"]])
        self.assertEqual(len(res.cycles), 2)

    def test_blocked_process_not_in_deadlock_edges(self):
        res = analyze(state_of(load_scenario("t07_printer_scanner")))
        self.assertNotIn("P4", {e["from"] for e in res.deadlock_edges})
        self.assertEqual(res.status, {"P1": "deadlocked", "P2": "deadlocked",
                                      "P3": "completes", "P4": "blocked"})

    def test_trace_records_checks_and_finishes(self):
        res = analyze(state_of(load_scenario("t01_no_deadlock")))
        types = [e["type"] for e in res.trace]
        self.assertEqual(types.count("finish"), 2)
        self.assertEqual(res.final_work, [1, 1])

    def test_empty_system(self):
        s = SystemState()
        self.assertEqual(validate(s), [])
        res = analyze(s)
        self.assertFalse(res.is_deadlocked)

    def test_single_instance_cycle_equals_deadlock_on_random_states(self):
        """Theory check: with single-instance resources, WFG cycle <=> deadlock."""
        for seed in range(300):
            s = random_scenario(seed=seed)
            s.total = [1] * s.m
            s.allocation = [[min(v, 1) for v in row] for row in s.allocation]
            for r in range(s.m):  # keep at most one holder per resource
                holders = [i for i in range(s.n) if s.allocation[i][r]]
                for i in holders[1:]:
                    s.allocation[i][r] = 0
            s.request = [[1 if (s.request[i][r] and not s.allocation[i][r]) else 0
                          for r in range(s.m)] for i in range(s.n)]
            s.max = []          # Max no longer matches; fall back to Allocation + Request
            self.assertEqual(validate(s), [], msg="seed %d" % seed)
            res = analyze(s)
            wfg = build_adjacency(s.processes, [(e["from"], e["to"]) for e in res.wait_for_edges])
            self.assertEqual(find_cycle_in(wfg) is not None, res.is_deadlocked, msg="seed %d" % seed)


class TestCycleUtilities(unittest.TestCase):
    def test_dfs_cycle_and_none(self):
        g = build_adjacency("ABCD", [("A", "B"), ("B", "C"), ("C", "A"), ("C", "D")])
        cyc = find_cycle_in(g)
        self.assertEqual(cyc[0], cyc[-1])
        self.assertEqual(sorted(cyc[:-1]), ["A", "B", "C"])
        self.assertIsNone(find_cycle_in(build_adjacency("AB", [("A", "B")])))

    @unittest.skipIf(nx is None, "networkx not installed")
    def test_scc_matches_networkx(self):
        for seed in range(100):
            s = random_scenario(n_processes=8, n_resources=4, seed=seed)
            res = analyze(s)
            edges = [(e["from"], e["to"]) for e in res.wait_for_edges]
            ours = {frozenset(c) for c in strongly_connected_components(build_adjacency(s.processes, edges))}
            G = nx.DiGraph()
            G.add_nodes_from(s.processes)
            G.add_edges_from(edges)
            theirs = {frozenset(c) for c in nx.strongly_connected_components(G)}
            self.assertEqual(ours, theirs, msg="seed %d" % seed)


class TestValidation(unittest.TestCase):
    def test_overallocation_message(self):
        errs = validate(state_of(load_scenario("t11_invalid_overalloc")))
        self.assertTrue(any("over-allocated" in e for e in errs))

    def test_impossible_request_message(self):
        errs = validate(state_of(load_scenario("t12_invalid_request")))
        self.assertTrue(any("can never be granted" in e for e in errs))

    def test_shape_negative_and_duplicates(self):
        s = SystemState(["P1", "P1"], ["R1"], [1], [[0], [0]], [[0], [-1]])
        errs = validate(s)
        self.assertTrue(any("more than once" in e for e in errs))
        self.assertTrue(any(">= 0" in e for e in errs))
        bad_shape = SystemState(["P1"], ["R1"], [1], [[0, 0]], [[0]])
        self.assertTrue(any("matrix must be" in e for e in validate(bad_shape)))

    def test_random_states_are_valid(self):
        for seed in range(200):
            self.assertEqual(validate(random_scenario(seed=seed)), [])


class TestRecovery(unittest.TestCase):
    def test_no_options_without_deadlock(self):
        self.assertEqual(suggest_recoveries(state_of(load_scenario("t01_no_deadlock"))), [])

    def test_terminate_p1_matches_t9(self):
        s = state_of(load_scenario("t03_three_cycle"))
        opts = suggest_recoveries(s)
        term = [o for o in opts if o["title"] == "Terminate P1"][0]
        self.assertTrue(term["resolved"])
        self.assertEqual(term["after_result"]["completion_order"], ["P3", "P2"])

    def test_every_option_is_verified_and_recommended_first(self):
        for sid in ["t02_two_process", "t05_multi_deadlock", "t07_printer_scanner",
                    "t08_multi_holder", "t10_db_transactions"]:
            s = state_of(load_scenario(sid))
            opts = suggest_recoveries(s)
            with self.subTest(scenario=sid):
                self.assertTrue(opts)
                self.assertTrue(opts[0]["recommended"])
                self.assertTrue(opts[0]["resolved"])
                for o in opts:
                    after = SystemState.from_dict(o["after_state"])
                    self.assertEqual(validate(after), [])
                    self.assertEqual(o["resolved"], not analyze(after).is_deadlocked)

    def test_recovery_does_not_mutate_input(self):
        s = state_of(load_scenario("t07_printer_scanner"))
        snapshot = s.to_dict()
        suggest_recoveries(s)
        self.assertEqual(s.to_dict(), snapshot)

    def test_no_capacity_advice(self):
        opts = suggest_recoveries(state_of(load_scenario("t05_multi_deadlock")))
        self.assertTrue(opts)
        self.assertEqual({o["strategy"] for o in opts} - {"terminate", "terminate_all", "preempt", "rollback"}, set())

    def test_report_contains_sections(self):
        s = state_of(load_scenario("t07_printer_scanner"))
        md = build_report(s, analyze(s), suggest_recoveries(s), "T7",
                          safety=safety_check(s), prevention=prevention_analysis(s),
                          risk=risk_of(s), resolution=suggest_resolutions(s))
        for heading in ["# Deadlock Detection Report", "## Summary: Detection Findings",
                        "## Summary: Suggested Resolution Strategies", "## 1. System State", "## 2. Deadlock Characterization",
                        "## 3. Deadlock Prevention", "## 4. Deadlock Avoidance", "## 5. Deadlock Detection",
                        "## 6. Deadlock Recovery", "## 7. Starvation"]:
            self.assertIn(heading, md)


class TestCharacterization(unittest.TestCase):
    def conds(self, sid):
        return {c["key"]: c["holds"] for c in analyze(state_of(load_scenario(sid))).conditions}

    def test_all_four_hold_in_deadlock(self):
        for sid in ["t02_two_process", "t03_three_cycle", "t07_printer_scanner", "t10_db_transactions"]:
            self.assertTrue(all(self.conds(sid).values()), sid)

    def test_chain_has_no_circular_wait(self):
        self.assertFalse(self.conds("t06_wait_chain")["circular_wait"])

    def test_deadlock_implies_all_conditions_on_random_states(self):
        """Theory check: the four conditions are NECESSARY for deadlock."""
        for seed in range(300):
            res = analyze(random_scenario(seed=seed))
            if res.is_deadlocked:
                self.assertTrue(all(c["holds"] for c in res.conditions), "seed %d" % seed)

    def test_multi_instance_all_hold_without_deadlock(self):
        res = analyze(state_of(load_scenario("t04_cycle_no_deadlock")))
        self.assertTrue(all(c["holds"] for c in res.conditions))
        self.assertFalse(res.is_deadlocked)


class TestPrevention(unittest.TestCase):
    def test_every_protocol_is_verified_on_deadlocks(self):
        for sid in ["t02_two_process", "t03_three_cycle", "t05_multi_deadlock", "t07_printer_scanner",
                    "t08_multi_holder", "t10_db_transactions"]:
            s = state_of(load_scenario(sid))
            for p in prevention_analysis(s):
                with self.subTest(scenario=sid, protocol=p["key"]):
                    if not p["simulated"]:
                        continue
                    after = SystemState.from_dict(p["after_state"])
                    self.assertEqual(validate(after), [])
                    self.assertTrue(p["resolved"])
                    self.assertTrue(p["condition_broken"])

    def test_protocols_always_prevent_deadlock_on_random_states(self):
        for seed in range(200):
            s = random_scenario(seed=seed)
            for p in prevention_analysis(s):
                if p["simulated"]:
                    self.assertTrue(p["resolved"], "seed %d %s" % (seed, p["key"]))
                    self.assertTrue(p["condition_broken"], "seed %d %s" % (seed, p["key"]))
                    if p["key"] == "circular_wait":
                        self.assertIsNone(p["cycle_after"], "seed %d" % seed)

    def test_ordered_scenario_has_no_violators(self):
        p = prevention_analysis(state_of(load_scenario("t15_ordered_requests")))
        self.assertEqual([x for x in p if x["key"] == "circular_wait"][0]["violators"], [])

    def test_mutual_exclusion_is_not_simulated(self):
        p = prevention_analysis(state_of(load_scenario("t02_two_process")))
        self.assertFalse(p[0]["simulated"])


class TestAvoidance(unittest.TestCase):
    def test_textbook_request_granted(self):
        s = state_of(load_scenario("t13_bankers_safe"))
        out = request_resources(s, "P1", [1, 0, 2])
        self.assertEqual(out["decision"], "grant")
        self.assertEqual(out["safety"]["sequence"], ["P1", "P3", "P4", "P0", "P2"])

    def test_textbook_requests_denied(self):
        s = state_of(load_scenario("t13_bankers_safe"))
        after = SystemState.from_dict(request_resources(s, "P1", [1, 0, 2])["after_state"])
        self.assertEqual(request_resources(after, "P4", [3, 3, 0])["decision"], "wait")   # not available
        self.assertEqual(request_resources(after, "P0", [0, 2, 0])["decision"], "wait")   # unsafe
        self.assertEqual(request_resources(after, "P3", [5, 0, 0])["decision"], "error")  # exceeds need

    def test_unsafe_is_not_deadlock(self):
        s = state_of(load_scenario("t14_unsafe_state"))
        self.assertFalse(safety_check(s)["safe"])
        self.assertFalse(analyze(s).is_deadlocked)

    def test_safe_implies_no_deadlock_on_random_states(self):
        """Theory check: deadlocked states are a subset of unsafe states."""
        for seed in range(300):
            s = random_scenario(seed=seed)
            self.assertEqual(validate(s), [])
            if safety_check(s)["safe"]:
                self.assertFalse(analyze(s).is_deadlocked, "seed %d" % seed)

    def test_max_validation(self):
        s = state_of(load_scenario("t13_bankers_safe"))
        s.max[0][0] = 11
        self.assertTrue(any("cannot claim more" in e for e in validate(s)))
        s = state_of(load_scenario("t02_two_process"))
        s.max = [[1, 0], [0, 1]]
        self.assertTrue(any("maximum claim" in e for e in validate(s)))


class TestStarvation(unittest.TestCase):
    def test_without_aging_same_victim_starves(self):
        out = simulate_starvation(state_of(load_scenario("t02_two_process")), rounds=6)
        self.assertEqual(out["without_aging"]["starved"], ["P1"])
        self.assertEqual(out["without_aging"]["counts"]["P1"], 6)

    def test_aging_bounds_victim_count(self):
        for sid in ["t02_two_process", "t03_three_cycle", "t07_printer_scanner", "t10_db_transactions"]:
            out = simulate_starvation(state_of(load_scenario(sid)), rounds=6)
            with self.subTest(scenario=sid):
                self.assertEqual(out["with_aging"]["starved"], [])
                self.assertLessEqual(out["with_aging"]["max_count"], 3)

    def test_history_raises_cost_and_protects(self):
        s = state_of(load_scenario("t02_two_process"))
        base = {o["title"]: o["cost"] for o in suggest_recoveries(s)}
        aged = suggest_recoveries(s, {"P1": 3})
        for o in aged:
            if "P1" in o["victims"]:
                self.assertEqual(o["cost"], base[o["title"]] + 180)
                self.assertIn("P1", o["protected"])
        rec = [o for o in aged if o["recommended"]][0]
        self.assertNotIn("P1", rec["victims"])


if __name__ == "__main__":
    unittest.main()


class TestPotentialDeadlock(unittest.TestCase):
    def level(self, sid):
        return risk_of(state_of(load_scenario(sid)))["level"]

    def test_levels(self):
        self.assertEqual(self.level("t02_two_process"), "deadlock")
        self.assertEqual(self.level("t16_potential_deadlock"), "high")      # unsafe, opposite lock order
        self.assertEqual(self.level("t14_unsafe_state"), "high")
        self.assertEqual(self.level("t04_cycle_no_deadlock"), "medium")     # lock-order inversion only
        for sid in ["t01_no_deadlock", "t06_wait_chain", "t15_ordered_requests"]:
            self.assertEqual(self.level(sid), "none", sid)

    def test_potential_is_not_actual(self):
        s = state_of(load_scenario("t16_potential_deadlock"))
        self.assertFalse(analyze(s).is_deadlocked)
        risk = risk_of(s)
        kinds = {f["kind"] for f in risk["findings"]}
        self.assertEqual(kinds, {"unsafe", "lock_order"})
        self.assertEqual(risk["lock_order_cycles"][0]["processes"], ["P1", "P2"])

    def test_every_deadlock_is_flagged_on_random_states(self):
        for seed in range(300):
            s = random_scenario(seed=seed)
            self.assertEqual(risk_of(s)["level"] == "deadlock", analyze(s).is_deadlocked, "seed %d" % seed)

    def test_lock_order_cycle_always_precedes_deadlock(self):
        """With single-instance resources a deadlock implies a lock-order cycle."""
        for seed in range(300):
            s = random_scenario(seed=seed)
            if all(t == 1 for t in s.total) and analyze(s).is_deadlocked:
                self.assertTrue(risk_of(s)["lock_order_cycles"], "seed %d" % seed)


class TestResolution(unittest.TestCase):
    def test_modes(self):
        self.assertEqual(suggest_resolutions(state_of(load_scenario("t02_two_process")))["mode"], "recover")
        self.assertEqual(suggest_resolutions(state_of(load_scenario("t16_potential_deadlock")))["mode"], "mitigate")
        self.assertEqual(suggest_resolutions(state_of(load_scenario("t01_no_deadlock")))["mode"], "none")

    def test_recommended_mitigation_removes_risk(self):
        for sid in ["t16_potential_deadlock", "t14_unsafe_state", "t04_cycle_no_deadlock", "t13_bankers_safe"]:
            out = suggest_resolutions(state_of(load_scenario(sid)))
            rec = [o for o in out["strategies"] if o["recommended"]]
            with self.subTest(scenario=sid):
                self.assertEqual(len(rec), 1)
                after = SystemState.from_dict(rec[0]["after_state"])
                self.assertEqual(validate(after), [])
                self.assertEqual(risk_of(after)["level"], "none")

    def test_lock_order_fix_on_random_states(self):
        for seed in range(200):
            s = random_scenario(seed=seed)
            for o in suggest_resolutions(s)["strategies"]:
                if o["strategy"] == "lock_order":
                    after = SystemState.from_dict(o["after_state"])
                    self.assertEqual(validate(after), [], "seed %d" % seed)
                    self.assertFalse(risk_of(after)["lock_order_cycles"], "seed %d" % seed)


def _fa(state):
    res = analyze(state)
    return res, assess_risk(state, res, safety_check(state))


class TestTraceMonitoring(unittest.TestCase):
    def test_example_flags_risk_before_deadlock(self):
        out = replay_trace(TRACE_EXAMPLE, _fa)
        self.assertTrue(out["ok"], out["errors"])
        self.assertIsNotNone(out["first_risk"])
        self.assertGreater(out["first_deadlock"], out["first_risk"])
        dead = out["timeline"][out["first_deadlock"] - 1]
        self.assertEqual(dead["event"], "P2 acquire Printer")
        final = analyze(SystemState.from_dict(out["final_state"]))
        self.assertEqual(final.deadlocked, ["P1", "P2"])
        self.assertEqual(final.blocked, ["P4"])

    def test_release_wakes_waiter(self):
        out = replay_trace("P1 acquire R1\nP2 acquire R1\nP1 release R1", _fa)
        self.assertTrue(out["ok"])
        st = out["final_state"]
        self.assertEqual(st["allocation"], [[0], [1]])
        self.assertEqual(st["request"], [[0], [0]])
        self.assertIsNone(out["first_deadlock"])

    def test_errors(self):
        self.assertIn("unknown action", replay_trace("P1 grab R1", _fa)["errors"][0])
        self.assertIn("cannot release", replay_trace("P1 release R1", _fa)["errors"][0])
        self.assertIn("blocked", replay_trace("P1 acquire R1\nP2 acquire R1\nP2 acquire R2", _fa)["errors"][0])
        self.assertFalse(replay_trace("   # nothing", _fa)["ok"])
