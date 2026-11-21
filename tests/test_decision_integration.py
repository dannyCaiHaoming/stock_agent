"""P1 integration: server-side event-group re-check on save, get_prior_trade_decision, MCP tool list.

Offline: classify_decision_event is mocked; STOCK_AGENT_DATA_DIR points at a temp dir.
"""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from mcp.server.mcpserver.exceptions import ToolError

from product.mcp import decision_ledger, server
from tests.test_decision_ledger import base


def classified(**over):
    out = {"group": "E2", "event_date": "2026-03-05", "benchmark": "IGV", "horizon_days": 60,
           "e2": {"moment": "platform_breakdown", "date": "2026-03-05", "deviation_z": -2.4, "direction": "down"},
           "e1": None}
    out.update(over)
    if "event_date" in over and out.get("e2"):
        out["e2"] = dict(out["e2"], date=over["event_date"])
    return out


class IntegrationCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"STOCK_AGENT_DATA_DIR": self.tmp.name}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("STOCK_AGENT_REPLAY_AS_OF", None)

    def save(self, classify_result, **over):
        with mock.patch.object(server.decision_tools, "classify_decision_event", return_value=classify_result) as m:
            out = server.save_trade_decision(**base(**over))
        return out, m

    def test_save_rechecks_group_event_date_and_benchmark(self):
        out, m = self.save(classified())
        self.assertTrue(out["saved"])
        self.assertEqual(out["horizon_days"], 60)
        m.assert_called_once()
        for wrong in (classified(group="E0"), classified(event_date="2026-03-04"), classified(benchmark="XLK")):
            with self.subTest(wrong=wrong), self.assertRaises(ToolError) as caught:
                self.save(wrong)
            self.assertIn("EVENT_GROUP_MISMATCH", str(caught.exception))

    def test_event_details_come_from_the_classifier_not_the_caller(self):
        # the caller flips the deviation sign (which would turn B1 from REDUCE into HOLD) and adds an overlap
        self.save(classified(), event={"event_date": "2026-03-05", "moment": "x", "deviation_z": 2.4,
                                       "d0": "2026-03-05", "accession": "0000-fake"})
        row = json.loads((Path(self.tmp.name) / "trade_decisions.jsonl").read_text().splitlines()[0])
        self.assertEqual(row["event"], {"event_date": "2026-03-05", "moment": "platform_breakdown",
                                        "deviation_z": -2.4})
        e1 = classified(group="E1", e2=None, e1={"d0": "2026-03-05", "accession": "0001-23", "reaction_excess": -0.08})
        self.save(e1, group="E1", event={"event_date": "2026-03-05"})
        row = json.loads((Path(self.tmp.name) / "trade_decisions.jsonl").read_text().splitlines()[1])
        self.assertEqual(row["event"], {"event_date": "2026-03-05", "d0": "2026-03-05", "accession": "0001-23"})

    def test_save_rechecks_as_of_the_replay_date(self):
        with mock.patch.dict(os.environ, {"STOCK_AGENT_REPLAY_AS_OF": "2026-03-06"}):
            _, m = self.save(classified())
        self.assertEqual(m.call_args.kwargs["as_of"], "2026-03-06")

    def test_prior_decision_is_latest_strictly_before(self):
        with mock.patch.dict(os.environ, {"STOCK_AGENT_REPLAY_AS_OF": "2026-03-06"}):
            first, _ = self.save(classified())
        with mock.patch.dict(os.environ, {"STOCK_AGENT_REPLAY_AS_OF": "2026-03-10"}):
            second, _ = self.save(classified(event_date="2026-03-10"), event={"event_date": "2026-03-10",
                                                                             "deviation_z": -2.1},
                                  prior_decision_id=first["decision_id"])
        with mock.patch.dict(os.environ, {"STOCK_AGENT_REPLAY_AS_OF": "2026-03-20"}):
            self.assertFalse(decision_ledger.get_prior_trade_decision("INTU", before="2026-03-05")["found"])
            mid = decision_ledger.get_prior_trade_decision("intu", before="2026-03-09")
            self.assertEqual(mid["decision_id"], first["decision_id"])
            self.assertIn("## 复核条件", mid["report_markdown"])
            self.assertEqual(decision_ledger.get_prior_trade_decision("INTU")["decision_id"], second["decision_id"])
            # the same-day card is not "prior" to itself
            self.assertFalse(decision_ledger.get_prior_trade_decision("INTU", before="2026-03-06")["found"])
        # a live session never sees replay cards
        self.assertFalse(decision_ledger.get_prior_trade_decision("INTU")["found"])

    def test_prior_id_must_be_same_ticker_earlier_and_same_kind(self):
        with mock.patch.dict(os.environ, {"STOCK_AGENT_REPLAY_AS_OF": "2026-03-10"}):
            later, _ = self.save(classified(event_date="2026-03-10"), event={"event_date": "2026-03-10",
                                                                            "deviation_z": -2.1})
        with mock.patch.dict(os.environ, {"STOCK_AGENT_REPLAY_AS_OF": "2026-03-06"}):
            with self.assertRaises(ToolError) as caught:  # prior decided after this card
                self.save(classified(), prior_decision_id=later["decision_id"])
            self.assertIn("PRIOR_DECISION_INVALID", str(caught.exception))
        with self.assertRaises(ToolError) as caught:  # live card pointing at a replay card
            self.save(classified(event_date="2026-03-05"), prior_decision_id=later["decision_id"])
        self.assertIn("PRIOR_DECISION_INVALID", str(caught.exception))

    def test_prior_decision_is_capped_by_replay_date(self):
        with mock.patch.dict(os.environ, {"STOCK_AGENT_REPLAY_AS_OF": "2026-03-10"}):
            self.save(classified(event_date="2026-03-10"), event={"event_date": "2026-03-10", "deviation_z": -2.1})
        with mock.patch.dict(os.environ, {"STOCK_AGENT_REPLAY_AS_OF": "2026-03-09"}):
            self.assertFalse(decision_ledger.get_prior_trade_decision("INTU")["found"])
            self.assertFalse(decision_ledger.get_prior_trade_decision("INTU", before="2026-12-31")["found"])

    def test_tools_are_registered(self):
        names = {t.name for t in asyncio.run(server.server.list_tools())}
        self.assertLessEqual({"classify_decision_event", "get_prior_trade_decision", "save_trade_decision"}, names)


if __name__ == "__main__":
    unittest.main()
