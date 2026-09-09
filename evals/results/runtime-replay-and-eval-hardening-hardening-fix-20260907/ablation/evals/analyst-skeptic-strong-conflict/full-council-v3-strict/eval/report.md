# Runtime Eval 报告

- Eval ID：`rreh-hardening-ablation-eval-conflict-full-council-v3-strict-20260908`
- Run ID：`rreh-hardening-ablation-conflict-full-council-v3-20260908`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Analyst 将四项可追溯事实与解释性限制分开；两项收入的同日冲突直接支持其不形成收入规模、商业判断或估值结论的 Thesis。
- cio_conflict_handling: `PASS` / grade=3 — CIO 记录 Analyst 与 Skeptic 的共识，明确未决收入冲突、对置信度和结论边界的影响，以及尚待回答的问题；未以孤立价格或利润率覆盖冲突。
- confidence_calibration: `PASS` / grade=3 — Analyst、Skeptic 与 CIO 的低置信度均明确归因于同日收入冲突、口径不可比性和关键数据缺口，与可追溯但不足的证据范围方向一致。
- no_trade_reasoning: `PASS` / grade=3 — NO_TRADE 明确锚定同一 as_of 的两项未解 revenue_ttm 冲突及利润率配对未证实，并给出可核验的来源调节、同口径利润表和补充证据重评条件。
- skeptic_counter_evidence: `PASS` / grade=3 — Skeptic 独立提出收入定义/来源冲突及利润率与收入边界未证实两项具体、可证伪挑战，并列出解决各挑战所需的可核验证据。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`59c5a00216dec17b6c0529370cebed843a88a65a745c9feb33b0031632da55eb`
- Execution proof hash：`8597e6726e161799c9b35a7ff716665c2afdbc3d3d406e9fec19689d254f0083`

## Reason Codes

- 无
