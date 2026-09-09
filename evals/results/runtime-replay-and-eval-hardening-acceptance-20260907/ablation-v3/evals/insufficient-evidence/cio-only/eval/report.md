# Runtime Eval 报告

- Eval ID：`rreh-ablation-v3-eval-insufficient-cio-only-20260907`
- Run ID：`rreh-ablation-v3-insufficient-cio-only-20260907`
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
- cio_conflict_handling: `PASS` / grade=3 — CIO 明确记录没有已验证 Specialist 报告、空冲突和具体未决问题，并说明单项允许价格事实不足以支持方向性判断，因而形成 NO_TRADE；该处理与冻结输入一致。
- confidence_calibration: `PASS` / grade=3 — 0.05 置信度的理由将结论严格限定为对不采取行动和证据不足的判断，并明确唯一允许价格事实不能支持方向性判断；方向上与证据充分度和不确定性一致。
- no_trade_reasoning: `PASS` / grade=3 — NO_TRADE 明确归因于唯一允许的价格事实不足以形成或检验 Thesis，并列出获得 Gate-allowed、可核验且时点合格的基本面、估值、催化剂、风险和独立反证材料后的重评条件；与 gate.json 的单项允许证据及 decision.json 的 APPROVED SAFE_NO_TRADE 一致。
- skeptic_counter_evidence: `NOT_APPLICABLE` / grade=None — cio-only 输入没有 Skeptic Specialist 报告，且 runtime_cio.consumed_reports 为空；没有可评分的独立反证产物。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`489f98f5d96a91c2ef5a1c29dfa8b4e6e727ce06092f3d4085d822e918658b23`
- Execution proof hash：`4b52a9bb626b830e8f91a98c8cfcc60a959dbb08f9767679ff744c68bc6e35ea`

## Reason Codes

- 无
