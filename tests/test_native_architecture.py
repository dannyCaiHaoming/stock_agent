import tempfile
import unittest
from pathlib import Path

from product.runtime.architecture_guard import (
    inspect_product_python,
    inspect_python_source,
)


ROOT = Path(__file__).resolve().parents[1]


class NativeArchitectureGuardTests(unittest.TestCase):
    def test_current_product_has_no_python_llm_backend_or_fixed_conclusion(self):
        self.assertEqual(inspect_product_python(ROOT / "product"), [])

    def test_model_sdk_import_is_rejected(self):
        findings = inspect_python_source("from openai import OpenAI\n", path="bad.py")
        self.assertEqual([finding.code for finding in findings], ["PYTHON_MODEL_SDK"])

    def test_multi_role_callback_simulation_is_rejected(self):
        source = "def run(research_agent, skeptic_callback, synthesis):\n    pass\n"
        codes = {finding.code for finding in inspect_python_source(source)}
        self.assertIn("MULTI_ROLE_CALLBACK_ORCHESTRATION", codes)

    def test_literal_thesis_action_confidence_bundle_is_rejected(self):
        source = "result = {'thesis': 'fixed', 'action': 'BUY', 'confidence': 0.9}\n"
        codes = {finding.code for finding in inspect_python_source(source)}
        self.assertIn("HARDCODED_INVESTMENT_CONCLUSION", codes)

    def test_unmarked_reference_callback_is_not_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "council" / "orchestrator.py"
            target.parent.mkdir()
            target.write_text(
                "def run(research_agent, skeptic_callback, synthesis):\n    pass\n",
                encoding="utf-8",
            )
            codes = {finding.code for finding in inspect_product_python(root)}
            self.assertIn("MULTI_ROLE_CALLBACK_ORCHESTRATION", codes)


if __name__ == "__main__":
    unittest.main()
