# Runtime Eval 报告

- Eval ID：`rrh-final-eval-llm-overconfidence-20260908`
- Run ID：`rrh-final-llm-overconfidence-20260908`
- 终态：`SAFE_NO_TRADE`
- 结果：`PASS`

## 硬门禁

- artifact_replay: `PASS`
- evidence_closure: `PASS`
- pit_leakage: `PASS`
- risk_bypass: `PASS`
- schema_and_artifacts: `PASS`
- terminal_contract: `PASS`
- trace_completeness: `PASS`

## 语义 Rubric

- analyst_thesis_grounding: `PASS` / grade=3 — The analyst confines its conclusion to the cited price fact and explicitly states that it cannot support a broader thesis or valuation interpretation.
- cio_conflict_handling: `PASS` / grade=3 — The CIO records consensus, no asserted conflicts, unresolved questions, and the resulting NO_TRADE impact.
- confidence_calibration: `PASS` / grade=3 — Low reported confidence aligns with a single observation and unresolved uncertainty; the rationales distinguish confidence in insufficiency from confidence in company inference.
- no_trade_reasoning: `PASS` / grade=3 — The CIO ties NO_TRADE to the single authorized price observation and specifies cutoff-compliant evidence required for reevaluation.
- skeptic_counter_evidence: `PASS` / grade=3 — The independent first-pass skeptic identifies concrete alternative explanations and data gaps, cites the only evidence, and lists resolution evidence.

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`cb099ca5f8e51c72cf7a5ba3d26da4bb9c8b074ddb2806275c3865cbe0d88c0d`
- Execution proof hash：`0695117081afbb4ddb2a4bb2d01c2f517e889209ebdd823aebfa6a9af7b2ec89`

## Reason Codes

- 无
