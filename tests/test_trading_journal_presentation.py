from __future__ import annotations

from copy import deepcopy
import json
import shutil
import subprocess
import unittest

from product.trading_journal.presentation import build_reader_labels, readable_text, reader_script
from product.trading_journal.reflection import render_markdown
from tests.test_trading_journal_reflection import WIN_ID, packet, report, evidence


class TradingJournalPresentationTests(unittest.TestCase):
    def test_known_reference_mapping_keeps_financial_values_and_public_links(self):
        values = packet()
        result = report(values)
        labels = build_reader_labels(values, result)
        body = f"{WIN_ID}与episode:{WIN_ID}；net_pnl=8 USD；120.45；事实deadbeef；https://example.invalid/{WIN_ID}?price=120.45"
        displayed = readable_text(body, labels)
        self.assertNotIn(WIN_ID, displayed.split("https://", 1)[0])
        self.assertIn("AAPL", displayed)
        self.assertIn("净盈亏=8 USD", displayed)
        self.assertIn("120.45；事实deadbeef", displayed)
        self.assertIn(f"https://example.invalid/{WIN_ID}?price=120.45", displayed)
        # A numeric reference cannot silently rewrite a research number.
        self.assertEqual(readable_text("费用1，成交价1.25", {"1": "某笔成交"}), "费用1，成交价1.25")
        self.assertEqual(readable_text("来源 evidence-example", {"evidence-example": "https://example.org/Users/public"}), "来源 https://example.org/Users/public")

    def test_unknown_internal_reference_and_path_have_explicit_reader_limits(self):
        shown = readable_text("episode:episode-unresolved；/Users/example/private/input.json；file:///tmp/secret；NEW_GAP_REASON；UNKNOWN.")
        for hidden in ("episode-unresolved", "/Users/", "input.json", "file://", "NEW_GAP_REASON", "UNKNOWN"):
            self.assertNotIn(hidden, shown)
        self.assertIn("引用资料暂不可展示", shown)
        self.assertIn("未知.", shown)

    def test_structured_gap_projects_to_natural_language_without_metadata(self):
        original = {"code": "FEES_INCOMPLETE", "asset_type": "OPTION", "start": "2026-01-05", "message": "费用仍待核对", "input_hash": "a" * 64, "source_id": "source-secret", "source_path": "/Users/example/source.csv", "schema_version": "1.0.0"}
        frozen = deepcopy(original)
        text = readable_text(original)
        self.assertIn("费用不完整", text)
        self.assertIn("期权", text)
        self.assertIn("2026-01-05", text)
        self.assertIn("费用仍待核对", text)
        for hidden in ("source-secret", "/Users/", "1.0.0", "a" * 64, "{", "}"):
            self.assertNotIn(hidden, text)
        self.assertEqual(original, frozen)
        self.assertEqual(readable_text({"reason": "ACCOUNT_START_UNKNOWN"}), "原因：开户起点尚未核实")

    def test_markdown_keeps_semantics_and_eliminates_reader_technical_identity(self):
        material = evidence("evidence-visible-sentinel", "2026-01-01T14:00:00Z", title="官方发布日期待核验", source_url="https://example.invalid/release", availability_basis="ORIGINAL_PUBLICATION_TIME_UNKNOWN", publication_precision="DATE")
        value = packet(evidence=[material])
        result = report(value)
        finding = result["findings"][0]
        finding["uncertain_evidence_refs"] = [material["evidence_id"]]
        finding["process_observation"] = f"原始记录为buy-win，计算采用episode:{WIN_ID}。net_pnl=8，但不能反推原始动机。"
        before = deepcopy((result, value))
        text = render_markdown(result, value)
        for hidden in (result["report_id"], result["snapshot_id"], result["input_hash"], result["packet_hash"], result["model_version"], "buy-win", WIN_ID, material["evidence_id"], "source_id", "DATA_LIMITED", "SNAPSHOT_WINDOW", "PROPOSED", "net_pnl", "{", "}"):
            self.assertNotIn(hidden, text)
        for retained in ("净盈亏=8", "不能反推原始动机", "原始发布时刻未知", "https://example.invalid/release", "官方发布日期待核验", finding["interpretation"], finding["confidence_limits"]):
            self.assertIn(retained, text)
        self.assertEqual((result, value), before)

    def test_minimal_review_labels_only_refer_to_projected_selection(self):
        selected = {"findings": [{"finding_id": "finding-picked", "pattern": "当前案例", "record_refs": ["buy-win"], "episode_refs": ["episode-picked"], "chart_refs": ["chart:picked"], "alternative_explanations": [{"record_refs": ["sell-loss"], "episode_refs": ["episode-counter"]}]}], "calculations": {}, "evidence": []}
        chosen = [row for row in packet()["snapshot"]["records"] if row["record_id"] in {"buy-win", "sell-loss"}]
        labels = build_reader_labels(packet=selected, report=selected, records=chosen)
        self.assertIn("2026-01-05", labels["episode-picked"])
        self.assertIn("2026-01-08", labels["episode-counter"])
        self.assertNotIn("buy-loss", labels)
        self.assertNotIn("sell-win", labels)
        self.assertEqual(labels["chart:picked"], "本案交易图表")

    @unittest.skipUnless(shutil.which("node"), "需要本地 Node 验证共用 JavaScript 阅读投影")
    def test_python_javascript_projection_agree_for_business_and_limit_text(self):
        labels = {"record-sentinel": "AAPL · 2026-01-05 · 买入 · 1份", "episode:episode-sentinel": "AAPL交易片段", "0": "不能替换金融数值", "evidence-example": "https://example.org/Users/public"}
        values = [None, True, [], ["BUY", "DATE"], {"status": "UNAVAILABLE", "reason": "OPENING_POSITION_UNKNOWN", "net_pnl": None, "source_id": "hidden", "input_hash": "f" * 64}, "record-sentinel与episode:episode-sentinel；net_pnl=120.45 USD；https://example.invalid/episode-sentinel/0；deadbeef", "episode:episode-missing；UNKNOWN.；NEW_LIMIT_CODE", "constructor", "CURRENT_OFFICIAL_CALENDAR_EVENT_TIME_IS_NOT_PUBLICATION_TIME", "来源 evidence-example"]
        code = reader_script(labels) + "\nconst values=" + json.dumps(values) + ";process.stdout.write(JSON.stringify(values.map(jrReadable)));"
        output = subprocess.run([shutil.which("node"), "-"], input=code, text=True, capture_output=True, check=True, timeout=15)
        self.assertEqual(json.loads(output.stdout), [readable_text(value, labels) for value in values])

    @unittest.skipUnless(shutil.which("node"), "需要本地 Node 验证标签注册")
    def test_runtime_registration_and_script_encoding_do_not_execute_labels(self):
        label = "研究文本 </script><script>bad()</script>"
        script = reader_script({"finding-x": label})
        self.assertNotIn("</script>", script)
        code = script + '\njrRegisterLabel("__proto__","安全的已声明引用"); process.stdout.write(JSON.stringify([jrRefLabel("finding-x"),jrRefLabel("__proto__"),jrRefLabel("missing")]));'
        output = subprocess.run([shutil.which("node"), "-"], input=code, text=True, capture_output=True, check=True, timeout=15)
        self.assertEqual(json.loads(output.stdout), [label, "安全的已声明引用", "引用资料暂不可展示"])


if __name__ == "__main__":
    unittest.main()
