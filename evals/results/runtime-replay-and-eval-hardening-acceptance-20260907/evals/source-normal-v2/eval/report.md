# Runtime Eval 报告

- Eval ID：`rreh-eval-source-normal-v2-20260907`
- Run ID：`rreh-source-normal-20260907`
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

- analyst_thesis_grounding: `PASS` / grade=3 — runtime_company_analyst 明确区分 FACT 与 INTERPRETATION；每项事实和有限解释均引用允许 Evidence，并对持续性、偿债能力和估值所需数据缺口作出限制说明。
- cio_conflict_handling: `PASS` / grade=3 — runtime_cio 明确记录两份报告的共识、无机械冲突、四项未决问题及其对 NO_TRADE 的影响；decision.json 风险报告也确认 APPROVED 且 final_action 为 NO_TRADE。
- confidence_calibration: `PASS` / grade=3 — Analyst 0.38、Skeptic 0.40 和 CIO 0.35 的低置信度均由已列明的关键数据缺口和不确定性解释，方向上与允许 Evidence 的有限覆盖一致。
- no_trade_reasoning: `PASS` / grade=3 — cio/runtime_cio.json 的 INSUFFICIENT_EVIDENCE、NO_TRADE 解释及四项重评条件与 gate.json 的允许证据范围和 decision.json 的 APPROVED SAFE_NO_TRADE 一致。
- skeptic_counter_evidence: `PASS` / grade=3 — runtime_skeptic 标记为 INDEPENDENT_FIRST_PASS，对债务、利润率、产能和价格提出具体可证伪挑战，并列出各挑战所需的核验材料和失效条件。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`b26947a809072410476273a0ea78a4a0325e1e6449af80f8b992e73357355aed`
- Execution proof hash：`46a71eeed46f65e6a2903503e02bdb27e6ed9e2aa805e6cf8b14c0df8acd605e`

## Reason Codes

- 无
