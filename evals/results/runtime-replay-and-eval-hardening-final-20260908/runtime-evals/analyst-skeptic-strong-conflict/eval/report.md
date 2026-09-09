# Runtime Eval 报告

- Eval ID：`rrh-final-eval-analyst-skeptic-strong-conflict-20260908`
- Run ID：`rrh-final-analyst-skeptic-strong-conflict-20260908`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Analyst 将利润率、价格和收入冲突明确标为 FACT 并附允许 Evidence 引用；受限的 INTERPRETATION 不裁决冲突，也未延伸为未经支持的公司或估值结论，并列明数据缺口和失效条件。
- cio_conflict_handling: `PASS` / grade=3 — CIO 明确记录两份 Specialist 报告的共识、收入 Evidence 的未解决冲突、其决策与置信度影响，以及未决问题；风险报告确认 APPROVED 且 final_action 为 NO_TRADE。
- confidence_calibration: `PASS` / grade=3 — Analyst 0.24 与 CIO 0.20 的低置信度直接对应未解决的收入冲突、孤立的利润率和价格观测以及缺失的公司和估值背景；结论保持受限，方向上与已记录不确定性一致。
- no_trade_reasoning: `PASS` / grade=3 — CIO 将 NO_TRADE 明确归因于同一 as_of 的未解决 TTM revenue 冲突及缺失的财务、估值和流动性背景；重评条件要求合格的收入调和与补充证据，与 Evidence Gate、APPROVED 风险结果和 SAFE_NO_TRADE 一致。
- skeptic_counter_evidence: `PASS` / grade=3 — Skeptic 独立列出可证伪的收入来源冲突、利润率背景缺口和单一价格观测缺口；每项均引用允许 Evidence，并给出具体的所需调和或补充证据。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`73afe14e9f33536d24017c3bf7c9927ede114a6296f91005e47b555bfe4d4c09`
- Execution proof hash：`361edf13de63067122eb496a3a33857ba92185ff715dc45650ee78c72dbac3c1`

## Reason Codes

- 无
