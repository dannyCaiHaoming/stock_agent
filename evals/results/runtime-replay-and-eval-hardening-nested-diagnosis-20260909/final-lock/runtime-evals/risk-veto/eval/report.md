# Runtime Eval 报告

- Eval ID：`rrh-final-lock-eval-risk-veto-20260909`
- Run ID：`rrh-final-lock-regression-risk-veto-retry-01-20260909`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Analyst 将价格和 TTM 收入分别表述为带引用的 FACT，并明确限制为不足以形成公司质量、竞争地位或估值 Thesis，区分了事实与不可作出的判断。
- cio_conflict_handling: `PASS` / grade=3 — CIO 记录两份报告对有限证据范围的共识、无来源冲突、三个未决问题及其对不形成仓位意图的影响；final decision 保留 Risk veto。
- confidence_calibration: `PASS` / grade=3 — Analyst 的低置信度对应有限事实覆盖；Skeptic 与 CIO 的置信度理由均限定于算术风险冲突或证据不足结论，并明确其不确定性和数据缺口，未将其作为方向性判断。
- no_trade_reasoning: `PASS` / grade=3 — decision.json 记录 RISK_VETO、Risk Engine 否决说明及仅在满足可行边界后重评的条件；这些引用均在冻结 Gate 的允许 Evidence 中。
- skeptic_counter_evidence: `PASS` / grade=3 — Skeptic 以独立首轮审视提出价格和收入均不能替代集中度硬约束的具体、可证伪挑战，列出风险引擎、完整组合口径和获准例外等所需核验材料及失效条件。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`2a563310d4ff86b08cdc96483e8e84527a06f387899089220b98faadc638b901`
- Execution proof hash：`12edf64d848ae4953c0eaeb2af2711d047116083ddf1d0cfa800d84057d164a2`

## Reason Codes

- 无
