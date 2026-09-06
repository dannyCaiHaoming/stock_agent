from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.run_package import finalize_cio, prepare_cio, prepare_run
from product.runtime.trace_validation import TraceValidationError, validate_decision_trace
from tests.test_native_run_package import FIXTURES, ROOT, cio_output, specialist_outputs, write_json


class NativeDecisionTraceTests(unittest.TestCase):
    def test_trace_traverses_versions_agents_evidence_risk_and_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "trace"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="trace-chain",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            specialist_outputs(run_dir)
            prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            write_json(run_dir / "cio" / "runtime_cio.json", cio_output(run_dir))
            finalize_cio(ROOT, run_dir=run_dir)
            trace = json.loads((run_dir / "decision_trace.json").read_text())
            validate_decision_trace(trace, run_dir=run_dir)
            self.assertEqual(
                {item["name"] for item in trace["agents"]},
                {"runtime_company_analyst", "runtime_skeptic", "runtime_cio"},
            )
            self.assertTrue(trace["risk_lineage"])
            self.assertIn("evidence/gate.json", trace["artifacts"])

    def test_trace_missing_agent_input_hash_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "trace"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="trace-invalid",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            specialist_outputs(run_dir)
            prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            write_json(run_dir / "cio" / "runtime_cio.json", cio_output(run_dir))
            finalize_cio(ROOT, run_dir=run_dir)
            trace = json.loads((run_dir / "decision_trace.json").read_text())
            del trace["agents"][0]["input_hash"]
            with self.assertRaisesRegex(TraceValidationError, "AGENT_LINEAGE_INCOMPLETE"):
                validate_decision_trace(trace, run_dir=run_dir)


if __name__ == "__main__":
    unittest.main()
