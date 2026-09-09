# Runtime Eval 报告

- Eval ID：`rreh-hardening-ablation-regrade-normal-research-analyst-cio-20260908`
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

- analyst_thesis_grounding: `PASS` / grade=3 — c1–c4 将收入、利润率、债务及管理层更新分别锚定到允许 Evidence；c5 明确标为 INTERPRETATION 并以 a1 和数据缺口限制其范围。
- cio_conflict_handling: `PASS` / grade=3 — CIO 说明与唯一已验证 Analyst 报告的共识，记录无冲突，并列出流动性、现金流、需求、执行和估值等未决问题及其对 NO_TRADE 的影响。
- confidence_calibration: `PASS` / grade=3 — Analyst 与 CIO 的置信度理由均以允许的核心事实为边界，并因流动性、现金流、趋势、需求与估值缺口而限制结论；方向与证据充分度和不确定性一致。
- no_trade_reasoning: `PASS` / grade=3 — NO_TRADE 明确对应 INSUFFICIENT_EVIDENCE：已引用事实仅支持初步经营和杠杆观察，且重评条件具体要求补足流动性、历史趋势、需求、产能经济性与估值证据。
- skeptic_counter_evidence: `NOT_APPLICABLE` / grade=None — 冻结输入未包含 runtime_skeptic 报告或 Skeptic Claim，无法对独立反证维度评分。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`b8aa99ac9162952b7180df6f710de1918e555681af5d3a6b4f757900fcb637ac`
- Execution proof hash：`a82474449ee016cfd145f4483de7bd5f01c40e5ec2244f0c40e4f0bbf75465e9`

## Reason Codes

- 无
