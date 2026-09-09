# Runtime Eval 报告

- Eval ID：`rreh-hardening-ablation-eval-conflict-full-council-v3-20260908`
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

- analyst_thesis_grounding: `PASS` / grade=3 — runtime_company_analyst 将收入、利润率和价格陈述分别标为 FACT 并引用 Gate 允许的证据；claim c5 明确标为 INTERPRETATION，且将商业与估值判断限制在同一 as_of 两项收入冲突和已列数据缺口之内。
- cio_conflict_handling: `PASS` / grade=3 — runtime_cio 明确记录 Analyst 与 Skeptic 对收入冲突及数据缺口的共识，将未解决冲突、其置信度影响和不形成仓位变更意图逐项关联，并列出未决问题；decision.json 同时记录 Risk APPROVED 和 SAFE_NO_TRADE，均与冻结产物一致。
- confidence_calibration: `PASS` / grade=3 — Analyst 0.24、Skeptic 0.32 与 CIO 0.2 的理由均把置信度限制在已确认的收入冲突及有限事实范围内，而非对收入规模、经营质量或估值作高置信结论；数值方向与未解决冲突、不可比性和数据缺口一致。
- no_trade_reasoning: `PASS` / grade=3 — runtime_cio 与 decision.json 均将 Gate 标记为 INCOMPATIBLE_NORMALIZED_VALUES 的同一 as_of 收入冲突作为 MATERIAL_SOURCE_CONFLICT，说明该冲突阻止可核验的收入、估值或仓位解释，并列出取得可追溯口径与同边界财务资料后的重评条件。
- skeptic_counter_evidence: `PASS` / grade=3 — runtime_skeptic 以 INDEPENDENT_FIRST_PASS 提出两个具体挑战：收入来源或定义冲突，以及利润率与收入规模的配对未获证明；两项挑战均引用冻结证据、列出所需裁决材料，并给出可证伪的失效条件。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`59c5a00216dec17b6c0529370cebed843a88a65a745c9feb33b0031632da55eb`
- Execution proof hash：`8c896a4f14a62f18b9e55c21997f68749573081f74d5306a47c51a4ec3278cda`

## Reason Codes

- 无
