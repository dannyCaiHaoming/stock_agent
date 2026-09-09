# Runtime Eval 报告

- Eval ID：`rreh-hardening-ablation-regrade-normal-research-full-council-20260908`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Analyst 将基础数值主张标为 FACT 并引用允许 Evidence；解释性主张披露假设且限定结论，未将有限事实延伸为估值或持续性结论。
- cio_conflict_handling: `PASS` / grade=3 — CIO 记录两份专业报告的共识、与 Gate 一致的无机械冲突状态及四项未决问题，并将这些缺口明确连接到 NO_TRADE 和重评条件。
- confidence_calibration: `PASS` / grade=3 — Analyst、Skeptic 与 CIO 的置信度理由均将有限证据覆盖、缺口和不确定性与其结论方向相连；CIO 的低置信度未把有限事实转化为方向性结论。
- no_trade_reasoning: `PASS` / grade=3 — NO_TRADE 与五项允许且新鲜的证据范围一致，明确将现金流、债务结构、需求兑现和估值资料缺失作为原因，并列出对应的可核验重评条件。
- skeptic_counter_evidence: `PASS` / grade=3 — 独立第一轮 Skeptic 对偿债能力、利润率质量、产能需求验证和价格估值分别提出具体、可证伪的挑战，并逐项给出所需解决证据。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`4cf60382a1e404f7edfb04a0dd82db5137459e320f490062815e449600e468a3`
- Execution proof hash：`8682a89ad67e0b6006fc10afd1688dbd49dcc155bf1a0ceef7607e88f085d711`

## Reason Codes

- 无
