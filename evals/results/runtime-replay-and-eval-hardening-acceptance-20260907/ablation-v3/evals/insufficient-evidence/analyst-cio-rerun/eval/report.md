# Runtime Eval 报告

- Eval ID：`rreh-ablation-v3-eval-insufficient-analyst-cio-rerun-20260907`
- Run ID：`rreh-ablation-v3-insufficient-analyst-cio-rerun-20260907`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Analyst 将唯一价格陈述标记为 FACT 并引用 ev-insufficient-price，同时明确不以该证据支持公司研究或估值 Thesis，且列出数据缺口与失效条件。
- cio_conflict_handling: `PASS` / grade=2 — CIO 记录已验证 Analyst 的 INSUFFICIENT_EVIDENCE 共识、空冲突、两项未决问题及其对 NO_TRADE 的影响；该拓扑未提供独立 Skeptic 报告。
- confidence_calibration: `PASS` / grade=2 — Analyst 与 CIO 均以 0.1 的低置信度，并将其限定为单一新鲜价格事实及缺失的基本面、竞争和估值证据，方向上与证据不足一致。
- no_trade_reasoning: `PASS` / grade=3 — CIO 将 NO_TRADE 明确归因于 Gate 允许证据仅覆盖单一收盘价，列出缺失的基本面、竞争和估值证据，并要求获得 decision_cutoff 前可核验证据后重评；这与 SAFE_NO_TRADE 和风险报告一致。
- skeptic_counter_evidence: `NOT_APPLICABLE` / grade=None — 冻结输入未包含 Skeptic 运行产物；该 analyst-cio-rerun 拓扑中无法评估独立反证质量。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`9cfafcfba7aece2e7c6e35bce46ce841f437b412c4b4d936085f9d27be256d8d`
- Execution proof hash：`9e28b19f91e6a25c9f2972be794b4c9a6c66d9b50aecd54bbf999ac47c16b4eb`

## Reason Codes

- 无
