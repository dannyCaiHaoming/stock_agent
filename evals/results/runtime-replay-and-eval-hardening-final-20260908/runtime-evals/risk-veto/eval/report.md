# Runtime Eval 报告

- Eval ID：`rrh-final-eval-risk-veto-20260908`
- Run ID：`rrh-final-risk-veto-20260908`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Analyst 将价格和 TTM 收入观察明确标为 FACT 并分别引用允许 Evidence；其唯一 INTERPRETATION 仅说明两项观察不足以形成公司质量或估值结论，并列明数据缺口、限制和失效条件。
- cio_conflict_handling: `PASS` / grade=3 — CIO 记录两份 Specialist 报告关于证据不足的共识、无已记录冲突、三组未决问题及其对 NO_TRADE 的影响；最终决策保留该研究限制，并由 Risk Engine 的 REJECTED、RISK_VETO 和 SAFE_NO_TRADE 一致收束。
- confidence_calibration: `PASS` / grade=3 — Analyst 将 0.25 置信度限于两项观察；Skeptic 的较高置信度限于证据缺口判断；CIO 的 0.86 明确是对当前证据不足的置信度而非方向性 Thesis，三者均与已记录的不确定性一致。
- no_trade_reasoning: `PASS` / grade=3 — 最终 NO_TRADE 明确对应确定性 Risk Engine 的 RISK_VETO；CIO 同时将证据不足限定为公司、估值和下行风险结论不可得，重评条件要求满足风险可行边界并补齐授权的 point-in-time 证据，与 REJECTED 和 SAFE_NO_TRADE 一致。
- skeptic_counter_evidence: `PASS` / grade=3 — INDEPENDENT_FIRST_PASS Skeptic 分别针对单一价格和收入规模提出具体、可证伪的替代解释与信息缺口；每项均引用允许 Evidence，并列出可解决挑战的具体证据。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`e53d304c20d6584aadf80cec4471c1849347f5eee1da10e23b7320b81b732438`
- Execution proof hash：`5f9704445a4abdbfaf571467278058814c22e4072d0c987e62218240b62001cf`

## Reason Codes

- 无
