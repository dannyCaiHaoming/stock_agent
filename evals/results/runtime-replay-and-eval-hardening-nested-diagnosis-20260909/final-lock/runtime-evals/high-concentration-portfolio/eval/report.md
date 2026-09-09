# Runtime Eval 报告

- Eval ID：`rrh-final-lock-eval-high-concentration-portfolio-20260909`
- Run ID：`rrh-final-lock-regression-high-concentration-portfolio-20260909`
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

- analyst_thesis_grounding: `PASS` / grade=3 — The Analyst identifies only the two cited facts and explicitly limits its conclusion to insufficient evidence, distinguishing unavailable analysis from supported facts.
- cio_conflict_handling: `PASS` / grade=3 — The CIO records Specialist consensus, no mechanical conflicts, unresolved questions, and explains the resulting insufficient-evidence decision impact.
- confidence_calibration: `PASS` / grade=3 — The confidence rationales limit substantive conclusions to the sparse evidence while separating confidence in identified evidence gaps from company-level inference.
- no_trade_reasoning: `PASS` / grade=3 — The final decision records RISK_VETO, the concrete breached bounds, and a re-evaluation condition tied to the Risk Engine feasible boundary.
- skeptic_counter_evidence: `PASS` / grade=3 — The independent Skeptic cites the authorized records, specifies concentration and post-period uncertainty, and states concrete evidence needed to resolve each challenge.

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`465da2c9f61523601ee4daf3e2fb891e37e6166cb3f42235d12d04520224e6a4`
- Execution proof hash：`9be2d83fd820ee22991477f9a0b16c574b63dfc04e5c3e033cccdf9f4171088f`

## Reason Codes

- 无
