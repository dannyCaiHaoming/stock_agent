# Runtime Eval 报告

- Eval ID：`rreh-hardening-ablation-eval-insufficient-cio-only-v3-20260908`
- Run ID：`rreh-hardening-ablation-insufficient-cio-only-v2-20260908`
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

- analyst_thesis_grounding: `NOT_APPLICABLE` / grade=None — No analyst report is present in the frozen CIO-only artifacts.
- cio_conflict_handling: `PASS` / grade=3 — CIO records no specialist consensus or conflicts, identifies missing specialist reports and unresolved questions, and reflects that limitation in NO_TRADE.
- confidence_calibration: `PASS` / grade=3 — Confidence 0.1 is explicitly tied to the single permitted observation and absence of validated specialist reports.
- no_trade_reasoning: `PASS` / grade=3 — The sole permitted price observation and absent validated specialist reports support INSUFFICIENT_EVIDENCE; concrete re-evaluation conditions are stated.
- skeptic_counter_evidence: `NOT_APPLICABLE` / grade=None — No skeptic report is present in the frozen CIO-only artifacts.

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`c1ef17eacccc5c7f9c4b8f488870637c34c276456ddd0004fbd77a587440862b`
- Execution proof hash：`67ba58135d7c4f8acc498e05313937122e2cff266271b204c8d147c0da4a153b`

## Reason Codes

- 无
