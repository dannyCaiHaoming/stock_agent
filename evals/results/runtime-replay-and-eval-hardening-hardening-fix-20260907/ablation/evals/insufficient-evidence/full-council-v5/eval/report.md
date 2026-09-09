# Runtime Eval 报告

- Eval ID：`rreh-hardening-ablation-eval-insufficient-full-council-v5-20260908`
- Run ID：`rreh-hardening-ablation-insufficient-full-council-v5-20260908`
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

- analyst_thesis_grounding: `PASS` / grade=3 — runtime_company_analyst 将唯一价格陈述标记为 FACT 并引用 ev-insufficient-price，同时明确区分该已支持事实与无法由该证据形成的公司质量、估值或趋势判断，并列出相应数据缺口与重新评估条件。
- cio_conflict_handling: `PASS` / grade=3 — runtime_cio 记录两份 Specialist 对证据不足的共识、无机械来源冲突、两项未决问题及其不形成持仓判断的影响；decision.json 同时记录 Risk Engine APPROVED 与 SAFE_NO_TRADE 终态，处理与冻结产物一致。
- confidence_calibration: `PASS` / grade=3 — Analyst 的 0.08 与 CIO 的 0.05 均明确受限于唯一单点事实和关键数据缺口；Skeptic 的 0.93 明确限于证据不足结论而非证券方向判断，三者均与证据充分度和不确定性的方向一致。
- no_trade_reasoning: `PASS` / grade=3 — runtime_cio 与 decision.json 均将唯一允许的单点收盘价判为不足以支持公司质量、估值、催化剂、流动性或风险回报判断；INSUFFICIENT_EVIDENCE 的 NO_TRADE 理由、说明及取得 Gate 授权且不晚于 decision_cutoff 的补充证据后重评的条件一致。
- skeptic_counter_evidence: `PASS` / grade=3 — runtime_skeptic 以 INDEPENDENT_FIRST_PASS 对价格充分性、价格稳定性和下行风险假设提出两项具体挑战，说明单一价格不能支持的判断范围，逐项列出所需核验材料和可证伪的失效条件。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`931a50fd8f66ee6899bd03cf18cddebfb8202fc7d83dffbe5fab59958e1c6136`
- Execution proof hash：`5eba7b20ad7a0fa2f74fa81ff13ade7c6372d3c3ca50b82bfe6ebf01ae6e73fc`

## Reason Codes

- 无
