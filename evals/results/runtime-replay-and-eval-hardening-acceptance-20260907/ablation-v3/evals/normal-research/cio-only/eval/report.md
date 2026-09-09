# Runtime Eval 报告

- Eval ID：`rreh-ablation-v3-eval-normal-cio-only-20260907`
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

- analyst_thesis_grounding: `NOT_APPLICABLE` / grade=None — cio-only 输入没有 Analyst Specialist 报告，且 runtime_cio.consumed_reports 为空；没有可评分的 Analyst Thesis 或其证据引用。
- cio_conflict_handling: `PASS` / grade=3 — CIO 明确记录无已验证 Specialist 报告、空共识和空冲突，并以未决的估值、产能执行和竞争问题说明 NO_TRADE 的影响；引用的允许证据与其基础事实陈述一致。
- confidence_calibration: `PASS` / grade=3 — 0.35 置信度的理由区分了新鲜且允许的基础事实与缺失的关键验证维度，并将不确定性限定为不形成调整建议；方向上与证据不足一致。
- no_trade_reasoning: `PASS` / grade=3 — NO_TRADE 明确归因于已允许证据未覆盖估值、现金流、竞争和产能执行验证，且给出获得 Gate-allowed 证据和经验证独立报告后的重评条件；该范围与所列五项允许证据一致。
- skeptic_counter_evidence: `NOT_APPLICABLE` / grade=None — cio-only 输入没有 Skeptic Specialist 报告，且 runtime_cio.consumed_reports 为空；没有可评分的独立反证产物。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`17367dd1c92cc9b1e94049896fd2310aac19b298270993773416fafd3f4bdc2f`
- Execution proof hash：`6e60dfa1b496fe137e1f4456051f6f46d7fdf8db66481d8110c29140beb517e7`

## Reason Codes

- 无
