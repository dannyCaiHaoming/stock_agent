# Runtime Eval 报告

- Eval ID：`rreh-eval-candidate-risk-veto-current-20260907`
- Run ID：`rreh-candidate-risk-veto-current-20260907`
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

- analyst_thesis_grounding: `PASS` / grade=3 — runtime_company_analyst 将两项主张标记为 FACT 并分别引用允许 Evidence；其余结论限于这些事实不足以支持商业质量、竞争或估值，且明确列出数据缺口与失效条件。
- cio_conflict_handling: `PASS` / grade=3 — runtime_cio 记录两份报告关于证据覆盖限制的共识、无来源冲突和三项未决问题，并据此说明不形成行动建议；decision.json 另明确记录 Risk Engine 对该草案的 RISK_VETO。
- confidence_calibration: `PASS` / grade=3 — Analyst 的 0.25 受限于仅两项单点事实；Skeptic 的 0.92 明确限于证据不足结论；CIO 的 0.88 明确限于不形成行动建议，三者均以数据缺口和不确定性校准其结论方向。
- no_trade_reasoning: `PASS` / grade=3 — decision.json 将终态记录为 SAFE_NO_TRADE，Risk Report 明确为 RISK_VETO 并列出三项违反；CIO 的证据不足说明及最终仅在满足 Risk Engine 可行边界后重评的条件，均与冻结产物一致。
- skeptic_counter_evidence: `PASS` / grade=3 — runtime_skeptic 以 INDEPENDENT_FIRST_PASS 提出价格非估值、收入规模非经营质量及时点联结缺口三项具体挑战，逐项给出所需核验材料和可证伪的失效条件。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`89a1ce9e6f10b8cdecb12f6af0e98eea26bb65211eefc137b989340eaea15e90`
- Execution proof hash：`4076fbb6da9f7f69eeaeae7d5e3bf92993639d58d8166816b59dd5e6753ac46a`

## Reason Codes

- 无
