# Runtime Eval 报告

- Eval ID：`rreh-hardening-ablation-regrade-normal-research-cio-only-20260908`
- Run ID：`rreh-ablation-v3-normal-cio-only-20260907`
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

- analyst_thesis_grounding: `NOT_APPLICABLE` / grade=None — cio-only 拓扑未提供已验证的 Analyst 报告或可评分的 Analyst Thesis。
- cio_conflict_handling: `PASS` / grade=3 — CIO 明确记录没有已验证 Specialist 报告，consensus/conflicts 均为空，并列出估值、产能执行与竞争影响三个未决问题；因此将决策影响限定为不形成调整建议。
- confidence_calibration: `PASS` / grade=3 — 0.35 置信度明确仅针对不形成调整建议，并由缺少已验证 Specialist 报告及关键估值、现金流、竞争和产能执行证据所约束，方向与不确定性一致。
- no_trade_reasoning: `PASS` / grade=3 — NO_TRADE 因关键估值、现金流、竞争状况及产能执行证据缺失；说明和两项重评条件均要求 Gate-allowed 的补充证据或经本次 Invocation 验证的独立报告，且与全部允许 Evidence 的有限覆盖一致。
- skeptic_counter_evidence: `NOT_APPLICABLE` / grade=None — cio-only 拓扑未提供已验证的 Skeptic 报告或可评分的独立反证。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`17367dd1c92cc9b1e94049896fd2310aac19b298270993773416fafd3f4bdc2f`
- Execution proof hash：`db93cec3f4509c17e191e0078f9a40c93fe4879c7b0cc40a79ad87bd16637e91`

## Reason Codes

- 无
