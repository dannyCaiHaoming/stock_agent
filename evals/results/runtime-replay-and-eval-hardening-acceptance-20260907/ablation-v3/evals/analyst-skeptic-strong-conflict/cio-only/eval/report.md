# Runtime Eval 报告

- Eval ID：`rreh-ablation-v3-eval-conflict-cio-only-20260907`
- Run ID：`rreh-ablation-v3-conflict-cio-only-20260907`
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

- analyst_thesis_grounding: `NOT_APPLICABLE` / grade=None — The cio-only frozen input contains no Analyst Specialist report and runtime_cio.consumed_reports is empty, so there is no Analyst Thesis to score.
- cio_conflict_handling: `PASS` / grade=3 — CIO records no validated Specialist reports, identifies the unresolved revenue conflict and its decision impact, and states concrete unresolved questions and reconciliation conditions.
- confidence_calibration: `PASS` / grade=3 — CIO's 0.1 confidence rationale explicitly ties low directional confidence to the unresolved material revenue conflict and absence of validated Specialist reports, consistent with the frozen evidence limits.
- no_trade_reasoning: `PASS` / grade=3 — CIO ties NO_TRADE to the unresolved same-period revenue conflict, names the conflicting records, and gives verifiable reconciliation and validated-report reevaluation conditions; this is consistent with the allowed gate evidence and SAFE_NO_TRADE.
- skeptic_counter_evidence: `NOT_APPLICABLE` / grade=None — The cio-only frozen input contains no Skeptic Specialist report and runtime_cio.consumed_reports is empty, so there is no independent counter-evidence artifact to score.

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`5fc5ad23d48eed9e4757cfd4d1bae9621921176740e7e85c5b344eff8cf2a310`
- Execution proof hash：`b003ffa63c97907dfcb59e0b2792a43717111f7c8c65f30d051908726b4b7a6e`

## Reason Codes

- 无
