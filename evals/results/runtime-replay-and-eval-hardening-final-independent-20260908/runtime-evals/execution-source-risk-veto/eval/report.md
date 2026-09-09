# Runtime Eval 报告

- Eval ID：`rreh-hardening-regression-eval-risk-veto-current-20260908`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Analyst 仅将价格和 TTM 收入表述为带引用的 FACT，并明确说明这些单点事实不足以支撑商业质量或估值结论。
- cio_conflict_handling: `PASS` / grade=3 — CIO 明确区分无来源冲突与证据覆盖不足，记录两份报告的共识、未决问题和重评所需信息；最终 Risk veto 亦被保留在 final decision。
- confidence_calibration: `PASS` / grade=3 — Analyst 的低置信度对应有限事实覆盖；Skeptic 与 CIO 的较高置信度限定为证据不足和不形成行动建议的结论，未把它们表述为方向性判断。
- no_trade_reasoning: `PASS` / grade=3 — final decision 明确记录 RISK_VETO、Risk Engine 否决说明及满足可行边界后重评条件；其证据引用与冻结 Gate 的允许 Evidence ID 一致。
- skeptic_counter_evidence: `PASS` / grade=3 — Skeptic 独立提出价格非估值、收入规模非经营质量及时点联结缺口三项具体、可证伪挑战，并列出所需核验材料。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`89a1ce9e6f10b8cdecb12f6af0e98eea26bb65211eefc137b989340eaea15e90`
- Execution proof hash：`7432c4710e2d4587a1c5c9b6c68956319a6094a4f2df16f04f17f75af9e4dd1e`

## Reason Codes

- 无
