# Runtime Eval 报告

- Eval ID：`rrh-final-eval-high-concentration-portfolio-20260908`
- Run ID：`rrh-final-high-concentration-portfolio-20260908`
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

- analyst_thesis_grounding: `PASS` / grade=3 — 报告将价格和 TTM 收入明确列为带引用的事实，并明确区分这些事实与因估值、财务和业务证据缺失而不能形成的 Thesis。
- cio_conflict_handling: `PASS` / grade=3 — CIO 明确记录专业报告共识、无机械证据冲突、未决问题及其对不形成方向性行动的影响，并在最终风险否决前保持该限制。
- confidence_calibration: `PASS` / grade=3 — Analyst、Skeptic 和 CIO 的低置信度均直接与授权证据狭窄、关键数据缺口及未量化集中风险相匹配，未依赖固定置信度或市场结果。
- no_trade_reasoning: `PASS` / grade=3 — 最终 NO_TRADE 明确归因于 Risk Engine veto，并保留可行边界、具体违规及仅在满足该边界后重评的条件；其事实输入均可追溯。
- skeptic_counter_evidence: `PASS` / grade=3 — 独立首轮提出了可证伪的估值基础和集中风险挑战，逐项说明缺口、所需验证证据及失效条件。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`60fa28bb14e61cb6d5889e6bbd9cadb8e14c59d1e56d623d6c24a9d6164f8aae`
- Execution proof hash：`d54631f4b5037e8bca0ce3d351f1598fd47ed0a34eec1c47a4c90b19172702e0`

## Reason Codes

- 无
