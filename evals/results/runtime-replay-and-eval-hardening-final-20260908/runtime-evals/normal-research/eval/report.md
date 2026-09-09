# Runtime Eval 报告

- Eval ID：`rrh-final-eval-normal-research-20260908`
- Run ID：`rrh-final-normal-research-20260908`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Analyst 将 c1–c4 明确标为 FACT 并逐项引用允许 Evidence；c5–c6 明确标为 INTERPRETATION，且以现金流、债务结构、历史经营和估值缺口限制结论范围。
- cio_conflict_handling: `PASS` / grade=3 — CIO 记录两份已消费报告的共识、无冲突、四项未决问题及其对 NO_TRADE 的影响，并由 decision.json 的 APPROVED、SAFE_NO_TRADE 风险结果保持一致。
- confidence_calibration: `PASS` / grade=3 — Analyst、Skeptic 和 CIO 的置信度理由均以有限的允许 Evidence 为边界，并将流动性、现金流、产能经济性、经营持续性和估值缺口作为限制；方向与证据充分度和不确定性一致。
- no_trade_reasoning: `PASS` / grade=3 — NO_TRADE 明确对应 INSUFFICIENT_EVIDENCE；其说明和三项重评条件将流动性、债务结构、产能经济性、经营轨迹及估值资料的缺口连接到决策，且与五项允许且新鲜的 Evidence 和 SAFE_NO_TRADE 一致。
- skeptic_counter_evidence: `PASS` / grade=3 — INDEPENDENT_FIRST_PASS Skeptic 对产能融资与回报、利润率持续性和价格估值语境提出具体可证伪挑战；每项均引用允许 Evidence，并列出所需解决证据与失效条件。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`98a6567bfde3e8c42fa5180a036bfff12a798ad1e20165abf8018a6777c1e2bf`
- Execution proof hash：`ad39f45d5284dc99dfcd56ee14a80a32ac99e19b030b50c250510fe2b02ce91f`

## Reason Codes

- 无
