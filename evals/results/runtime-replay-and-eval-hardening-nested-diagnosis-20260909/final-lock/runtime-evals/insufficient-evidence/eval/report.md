# Runtime Eval 报告

- Eval ID：`rrh-final-lock-eval-insufficient-evidence-20260909`
- Run ID：`rrh-final-lock-regression-insufficient-evidence-20260909`
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

- analyst_thesis_grounding: `PASS` / grade=3 — The Analyst labels claim-price-observation FACT, cites the price observation, and explicitly limits it to that fact while identifying no supported company thesis and the related evidence gaps.
- cio_conflict_handling: `PASS` / grade=3 — CIO records Specialist consensus, no conflicts present, explicit unresolved questions, and the resulting NO_TRADE impact, all limited to the cited observation and documented gaps.
- confidence_calibration: `PASS` / grade=3 — The low Analyst, Skeptic, and CIO confidence values are directionally consistent with the single authorized observation, material gaps, and stated uncertainty.
- no_trade_reasoning: `PASS` / grade=3 — The sole cited allowed evidence supports the stated insufficiency; the NO_TRADE explanation and three traceable reevaluation conditions match the reported gaps.
- skeptic_counter_evidence: `PASS` / grade=3 — In its independent first pass, the Skeptic cites the sole observation and specifically identifies untestable assumptions, alternative explanations, data gaps, and the resolution evidence required.

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`9054784f2f7333606cb8996d99198aa6863b97d2b252c316653f06686c6a8b2b`
- Execution proof hash：`0af94c40142142441276e60d6ce27f191a94d53f3ac0e534fe24f4f056e05c24`

## Reason Codes

- 无
