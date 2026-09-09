# Runtime Eval 报告

- Eval ID：`rreh-ablation-v3-eval-normal-analyst-cio-20260907`
- Run ID：`rreh-ablation-v3-normal-analyst-cio-20260907`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Analyst 将收入、利润率、债务和管理层更新作为带引用的事实；解释性结论显式受 a1 假设及现金流、需求和估值缺口限制。
- cio_conflict_handling: `PASS` / grade=2 — CIO 记录已验证 Analyst 报告的一致点、无冲突、具体未决问题及其对 NO_TRADE 的影响；该拓扑未提供独立 Skeptic 报告。
- confidence_calibration: `PASS` / grade=2 — Analyst 与 CIO 均将置信度限定于已核验的经营和杠杆观察，并将流动性、现金流、需求、执行和估值缺口作为不确定性限制。
- no_trade_reasoning: `PASS` / grade=3 — NO_TRADE 明确对应已核验事实的有限覆盖及流动性、现金流、趋势、需求、产能回报和估值缺口，并列出可核验的重评条件。
- skeptic_counter_evidence: `NOT_APPLICABLE` / grade=None — 冻结输入未包含 Skeptic 运行产物；该 ablation 拓扑中无法评估独立反证质量。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`b8aa99ac9162952b7180df6f710de1918e555681af5d3a6b4f757900fcb637ac`
- Execution proof hash：`7195477cf7f9697f610539622f5c0b5e2921beb180f74261b22e95ddac0c4ca1`

## Reason Codes

- 无
