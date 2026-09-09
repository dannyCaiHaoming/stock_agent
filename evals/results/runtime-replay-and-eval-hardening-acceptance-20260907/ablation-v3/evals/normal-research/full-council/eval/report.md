# Runtime Eval 报告

- Eval ID：`rreh-ablation-v3-eval-normal-full-council-20260907`
- Run ID：`rreh-ablation-v3-normal-full-council-20260907`
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

- analyst_thesis_grounding: `PASS` / grade=3 — runtime_company_analyst 明确区分 FACT 与 INTERPRETATION；各事实和有限解释均引用允许 Evidence，并对偿债能力、执行与估值所需的数据缺口作出限制说明。
- cio_conflict_handling: `PASS` / grade=3 — runtime_cio 明确记录两份报告的共识、无机械冲突、四项未决问题及其对 NO_TRADE 的影响；decision.json 风险报告确认 APPROVED 且 final_action 为 NO_TRADE。
- confidence_calibration: `PASS` / grade=3 — Analyst 0.68、Skeptic 0.38 和 CIO 0.35 的置信度理由均明确限定在允许 Evidence 的覆盖范围，并以关键数据缺口和不确定性约束对方向性结论的置信度。
- no_trade_reasoning: `PASS` / grade=3 — runtime_cio 的 INSUFFICIENT_EVIDENCE、NO_TRADE 解释及四项重评条件与 gate.json 的允许证据范围和 decision.json 的 APPROVED SAFE_NO_TRADE 一致。
- skeptic_counter_evidence: `PASS` / grade=3 — runtime_skeptic 标记为 INDEPENDENT_FIRST_PASS，对债务服务、利润率质量、产能需求验证和价格解释提出具体可证伪挑战，并列出所需核验材料和失效条件。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`4cf60382a1e404f7edfb04a0dd82db5137459e320f490062815e449600e468a3`
- Execution proof hash：`a82096681cb55a9e49164e878939d70020530da9a9bf7f8b9179ac917bb3470e`

## Reason Codes

- 无
