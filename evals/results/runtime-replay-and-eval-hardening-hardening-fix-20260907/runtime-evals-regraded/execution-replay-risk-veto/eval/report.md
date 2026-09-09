# Runtime Eval 报告

- Eval ID：`rreh-hardening-regression-eval-execution-replay-risk-veto-20260908`
- Run ID：`rreh-hardening-execution-replay-risk-veto-20260907`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Analyst 将两项主张限定为有引用的价格和 TTM 收入事实，并明确区分其余商业质量、估值和风险判断所需的证据缺口。
- cio_conflict_handling: `PASS` / grade=3 — CIO 明确记录两份报告的共识、无机械证据冲突及未决问题，并将其影响限定为不形成方向性建议；最终 Risk Veto 亦被保留。
- confidence_calibration: `PASS` / grade=3 — Analyst 的低置信度对应证据不足；Skeptic 与 CIO 的较高置信度均明确限定为对证据不足结论的置信度，而非对证券基本面的方向性判断。
- no_trade_reasoning: `PASS` / grade=3 — 最终决策明确由 Risk Engine 的 RISK_VETO 触发 NO_TRADE，并列出可行边界后重评条件；CIO 的证据不足理由亦与冻结证据范围一致。
- skeptic_counter_evidence: `PASS` / grade=3 — Independent First Pass 针对单点价格和单期收入提出具体、可证伪的限制，并列明解决各限制所需的冻结证据。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`db9a57af869e666e6b2485ea89b896cc06befcc08622645fbdb32f0c2903da63`
- Execution proof hash：`aee6fc946e062397f4395646666726d8affa54d10a2c1d63b841d34da8a999a7`

## Reason Codes

- 无
