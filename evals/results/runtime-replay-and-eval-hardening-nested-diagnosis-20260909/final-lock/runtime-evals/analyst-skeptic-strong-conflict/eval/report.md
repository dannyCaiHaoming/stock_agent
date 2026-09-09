# Runtime Eval 报告

- Eval ID：`rrh-final-lock-eval-analyst-skeptic-strong-conflict-20260909`
- Run ID：`rrh-final-lock-regression-analyst-skeptic-strong-conflict-20260909`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Analyst 将利润率、价格和两项收入观察分别标注为 FACT 并引用允许证据；其 INTERPRETATION 明确受同期间收入冲突和数据缺口限制，未将未证实的收入规模、增长或估值判断表述为事实。
- cio_conflict_handling: `PASS` / grade=3 — CIO 明确记录 Specialist 对收入冲突和证据边界的共识，保留未解决冲突、未决问题及其对收入、盈利和估值推导的影响，并在 decision.json 中保持与 Risk APPROVED 和 SAFE_NO_TRADE 一致的结论。
- confidence_calibration: `PASS` / grade=3 — Analyst、Skeptic 和 CIO 的置信度理由均将判断范围限定为已验证冲突或有限事实，并随未解决收入冲突、口径不明及经营和估值数据缺口保持审慎；未以固定数值或市场结果作为正确性依据。
- no_trade_reasoning: `PASS` / grade=3 — CIO 与 decision.json 均将同一报告期的未解决收入冲突及补充经营和估值数据缺口列为 NO_TRADE 原因，并给出取得统一可追溯收入口径和补充同口径证据后的重评条件；与 Evidence Gate 的冲突记录和 SAFE_NO_TRADE 一致。
- skeptic_counter_evidence: `PASS` / grade=3 — Skeptic 以 INDEPENDENT_FIRST_PASS 提出具体的收入口径、利润率可比性和价格语境挑战，逐项引用授权证据，列明可证伪的替代解释、所需解决证据和失效条件。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`1f64bb326436ba6ad378ecf2ab1adc0f4d3ecfc322dc2ea7073bbd63722ec965`
- Execution proof hash：`cde173b965a86e5d4161223ddafeb85187d3b532342e60ff7aaf720006aea695`

## Reason Codes

- 无
