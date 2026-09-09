# Runtime Eval 报告

- Eval ID：`rreh-hardening-ablation-eval-conflict-analyst-cio-v4-20260908`
- Run ID：`rreh-hardening-ablation-conflict-analyst-cio-v4-20260908`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Analyst 区分收入事实与冲突解释；两项互斥收入支持冲突结论，并明确利润率和价格不足以解决该冲突。
- cio_conflict_handling: `PASS` / grade=3 — CIO 明确记录共识、未解决冲突、两个未决问题及其对商业质量、估值和方向性结论的阻断影响。
- confidence_calibration: `PASS` / grade=3 — Analyst 与 CIO 均将信心限制在冲突识别，而未延展至商业、估值或方向性结论，符合冲突和数据缺口。
- no_trade_reasoning: `PASS` / grade=3 — NO_TRADE 明确归因于同一 as_of 的未解决收入冲突，并给出在获得来源优先级、口径及修订信息后重评的条件。
- skeptic_counter_evidence: `NOT_APPLICABLE` / grade=None — 该 ablation 仅含 runtime_company_analyst；冻结输入没有 Skeptic 报告，无法评分。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`5b87faa9626aeebd0b896d5f66d0aa3de6aece156eaf6e0be50e2105f88a839d`
- Execution proof hash：`89d8d47483ad759176159e8af1d916cbda31ceb4624d00467e5b96935715a076`

## Reason Codes

- 无
