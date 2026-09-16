from __future__ import annotations

import unittest

from product.council.research_schedule import (
    DependencyResearchScheduler,
    ResearchScheduleError,
)


def tasks():
    return [
        {"task_id": "technical-a", "capability": "TECHNICAL_STRUCTURE", "security_ids": ["US:A"], "depends_on": []},
        {"task_id": "fundamental-a", "capability": "FUNDAMENTAL_EVENT", "security_ids": ["US:A"], "depends_on": []},
        {"task_id": "macro-shared", "capability": "MACRO_MARKET", "security_ids": ["US:A", "US:B"], "depends_on": []},
        {"task_id": "report-update-a", "capability": "FUNDAMENTAL_EVENT", "security_ids": ["US:A"], "depends_on": ["fundamental-a"]},
        {"task_id": "industry-a", "capability": "INDUSTRY_COMPARISON", "security_ids": ["US:A"], "depends_on": ["peer-data-a"]},
        {"task_id": "peer-data-a", "capability": "INDUSTRY_COMPARISON", "security_ids": ["US:A"], "depends_on": []},
    ]


class MultidimensionalScheduleTests(unittest.TestCase):
    def test_independent_tasks_fill_slots_and_dependencies_wait(self) -> None:
        scheduler = DependencyResearchScheduler(tasks(), max_concurrency=3)
        initial = [item["task_id"] for item in scheduler.ready_tasks()]
        self.assertEqual(initial, ["technical-a", "fundamental-a", "macro-shared"])
        for index, task_id in enumerate(initial):
            scheduler.record_started(task_id, invocation_id=f"inv-{index}")
        self.assertEqual(scheduler.ready_tasks(), [])
        scheduler.record_completed("fundamental-a", report_ref="reports/fundamental-a.json")
        self.assertEqual(
            [item["task_id"] for item in scheduler.ready_tasks()],
            ["report-update-a"],
        )
        self.assertEqual(scheduler.progress()["reports_available"], ["reports/fundamental-a.json"])

    def test_out_of_order_completion_and_single_failure_are_isolated(self) -> None:
        scheduler = DependencyResearchScheduler(tasks(), max_concurrency=3)
        for index, task in enumerate(scheduler.ready_tasks()):
            scheduler.record_started(task["task_id"], invocation_id=f"inv-{index}")
        scheduler.record_completed("macro-shared", report_ref="reports/macro.json")
        scheduler.record_failed("fundamental-a", failure_code="SOURCE_FAILED")
        self.assertEqual(scheduler._task("report-update-a")["status"], "BLOCKED")
        self.assertEqual(scheduler._task("technical-a")["status"], "RUNNING")
        self.assertIn("reports/macro.json", scheduler.progress()["reports_available"])

    def test_shared_task_is_one_invocation_for_multiple_holdings(self) -> None:
        scheduler = DependencyResearchScheduler(tasks(), max_concurrency=6)
        shared = [item for item in scheduler.ready_tasks() if item["task_id"] == "macro-shared"]
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0]["security_ids"], ["US:A", "US:B"])

    def test_cycle_and_unknown_dependency_fail_closed(self) -> None:
        for invalid in (
            [{"task_id": "a", "security_ids": [], "depends_on": ["missing"]}],
            [{"task_id": "a", "security_ids": [], "depends_on": ["b"]},
             {"task_id": "b", "security_ids": [], "depends_on": ["a"]}],
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ResearchScheduleError):
                DependencyResearchScheduler(invalid)


if __name__ == "__main__":
    unittest.main()
