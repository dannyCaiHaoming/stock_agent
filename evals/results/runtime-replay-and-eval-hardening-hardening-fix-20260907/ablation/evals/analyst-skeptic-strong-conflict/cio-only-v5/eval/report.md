# Runtime Eval 报告

- Eval ID：`rreh-hardening-ablation-eval-conflict-cio-only-v5-20260908`
- Run ID：`rreh-hardening-ablation-conflict-cio-only-v5-20260908`
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

- analyst_thesis_grounding: `NOT_APPLICABLE` / grade=None — 冻结输入未提供 Analyst 报告或 Analyst Thesis；runtime_cio 明确记录本 cio-only 评估不存在已验证的 Specialist 报告，因此无法评估该维度。
- cio_conflict_handling: `PASS` / grade=3 — runtime_cio 明确记录两项收入观测的冲突、未解决状态、对研究判断的影响、两项未决问题及不可用 Specialist 共识；其 NO_TRADE 与 decision.json 的 SAFE_NO_TRADE 一致。
- confidence_calibration: `PASS` / grade=3 — CIO 的 0.15 置信度理由将低置信度归因于未解决的收入冲突、缺少已验证 Specialist 报告及缺乏可裁决证据，方向上与证据不确定性一致。
- no_trade_reasoning: `PASS` / grade=3 — runtime_cio 与 decision.json 均将同一期间 revenue_ttm 的未解决冲突识别为 EVIDENCE_CONFLICT；NO_TRADE 解释及取得可核验调节或权威可比值后的重评条件与该冲突一致。
- skeptic_counter_evidence: `NOT_APPLICABLE` / grade=None — 冻结输入未提供 Skeptic 报告或独立反证；runtime_cio 明确记录本 cio-only 评估不存在已验证的 Specialist 报告，因此无法评估该维度。

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`bbfaadc261bc0ca7a7ace0037d8b14d1845075fef05ff566e4d3756415113df0`
- Execution proof hash：`54d7d3b52d64509ec2b8103f7b2e9dab43347f9ffde462912c02a98e666cdd39`

## Reason Codes

- 无
