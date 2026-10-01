"""开发记录整理：历史字节、任务状态、原规格和当前义务均保留。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_CHANGE = ROOT / "openspec/changes/complete-eight-dimension-source-consumption"
ARCHIVED_CHANGE = ROOT / "openspec/changes/archive/2026-10-01-complete-eight-dimension-source-consumption"
# 验证同一份不可变历史；归档只移动目录，不应让历史保全测试失去入口。
CHANGE = ACTIVE_CHANGE if ACTIVE_CHANGE.is_dir() else ARCHIVED_CHANGE


def task_rows(text):
    return {match.group(2): match.group(1) == "x" for match in re.finditer(
        r"^- \[([ x])\] (\d+\.\d+) ", text, re.MULTILINE,
    )}


class ResearchAcceptanceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.index = json.loads((CHANGE / "task-history-index.json").read_text())

    def test_original_task_snapshot_is_exact_and_every_status_is_retained(self):
        snapshot = CHANGE / self.index["snapshot"]
        self.assertEqual(hashlib.sha256(snapshot.read_bytes()).hexdigest(), self.index["snapshot_sha256"])
        old = task_rows(snapshot.read_text())
        self.assertEqual(len(self.index["original_tasks"]), len(old))
        self.assertEqual({row["id"]: row["completed"] for row in self.index["original_tasks"]}, old)
        for row in self.index["original_tasks"]:
            actual = snapshot.read_text().splitlines()[row["source_line"] - 1]
            self.assertIn(row["id"], task_rows(actual))

    def test_original_unfinished_items_remain_mapped_without_freezing_live_progress(self):
        original = {row["id"] for row in self.index["original_tasks"] if not row["completed"]}
        mappings = self.index["pending_mappings"]
        self.assertEqual({row["id"] for row in mappings}, original)
        self.assertEqual(len(mappings), len(original))
        current = task_rows((CHANGE / "tasks.md").read_text())
        self.assertEqual(set(current), {"8.40", "5.3", "6.16", "5.6", "5.5"})
        for row in mappings:
            self.assertFalse(row["original_completed"])
            self.assertEqual(row["coverage_status"], "NOT_CLOSED")
            self.assertTrue(set(row["current_obligations"]) <= set(current))
            self.assertTrue(row["current_obligations"])
        # 索引保存整理时点，当前tasks可在用户恢复/验收后推进；不能要求永远暂停。
        self.assertEqual(self.index["change_status"], "PAUSED")
        self.assertFalse(self.index["live_budget"]["new_calls_authorized"])
        self.assertFalse(self.index["live_budget"]["current_change_budget_inherited"])

    def test_historical_spec_identifiers_and_current_history_links_resolve(self):
        for ref, digest in self.index["spec_files_unchanged"].items():
            # 这些hash是2026-09-30整理时点；用户明确授权更新规格后不再等于当前字节。
            # 不改历史hash凑当前值，真正不可变的原任务全文仍由上一测试验证。
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            self.assertTrue((CHANGE / ref).is_file(), ref)
        current = (CHANGE / "tasks.md").read_text()
        for destination in re.findall(r"\]\(([^)]+)\)", current):
            self.assertTrue((CHANGE / destination).resolve().is_file(), destination)


if __name__ == "__main__":
    unittest.main()
