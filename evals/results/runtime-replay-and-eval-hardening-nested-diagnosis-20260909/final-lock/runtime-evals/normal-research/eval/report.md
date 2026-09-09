# Runtime Eval 报告

- Eval ID：`rrh-final-lock-eval-normal-research-20260909`
- Run ID：`rrh-final-lock-regression-normal-research-20260909`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Analyst 将可追溯事实与有限解释分开；解释引用收入、利润率、债务和公司更新，并明确未能支持持续性、竞争壁垒或未来回报的部分。
- cio_conflict_handling: `PASS` / grade=3 — CIO 明确记录 Specialist 共识及无机械冲突，并把未决的估值、现金流、债务、经营趋势和产能问题与 NO_TRADE 结论及重评条件相连。
- confidence_calibration: `PASS` / grade=3 — 各报告的置信度理由区分已支持的点时事实与未解决的数据缺口；CIO 的低置信度与有限证据、无估值基础和不确定性方向一致。
- no_trade_reasoning: `PASS` / grade=3 — NO_TRADE 将估值、现金流、债务期限、经营趋势与产能执行信息缺口明确关联到无法形成风险回报判断，并列出可核验的重评条件。
- skeptic_counter_evidence: `PASS` / grade=3 — Skeptic 独立地针对利润率持续性、产能执行与融资、以及价格解释提出具体可证伪的限制，并为每项说明所需的解决证据。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`70716c462b0e6175672a91c47ba3cacea2e21c3dea79e2af0235043ac8a7a9b1`
- Execution proof hash：`8936a981083d3427f569f857b59e0a5c11bbb00077f5011cbb0fbf32551d76a2`

## Reason Codes

- 无
