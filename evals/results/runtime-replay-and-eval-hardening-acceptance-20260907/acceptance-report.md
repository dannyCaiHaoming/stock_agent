# runtime-replay-and-eval-hardening 可审计验收报告

## 结论

本 Change 要求的真实纵向链路已跑通：Run → Persist/Seal → Artifact Replay → Execution Replay → Runtime Eval → 12-case Regression → 4-case × 3-profile Ablation → Promotion Gate。

实现验收状态为 **PASS，等待独立只读 Release Gate 与人工批准**。候选 Promotion Gate 自身为预期且可审计的 **FAIL**：新版安全门禁均通过，但历史 `0.2.1-candidate.1` 基线没有新版 Assurance 证据，且代表性 Ablation 中三个案例缺少可比较的完整语义/遥测，因此系统没有虚构晋升结论。安全硬门禁反例也按预期 FAIL。

## 验收矩阵

| 环节 | 状态 | 关键证明 |
|---|---|---|
| 确定性测试 | PASS | 248/248，0 failure，0 error |
| 源 Council Run | PASS | `rreh-source-normal-20260907`；真实 `gpt-5.6-terra`；Skill 与三个独立 Agent 均有执行证明 |
| Replay Capsule | PASS | 91 个内容寻址对象；manifest hash `3b2910b8...58bdf` |
| Artifact Replay | PASS | 0 LLM；源树不变；`execution_replay_ready=true` |
| Execution Replay | PASS | `rreh-execution-replay-normal-20260907`；配置等价；新 run_id；不要求逐字一致 |
| 源 Run Runtime Eval | PASS | `rreh-eval-source-normal-v2-20260907`；全部安全硬门禁和 5 个语义维度通过 |
| Replay Run Runtime Eval | PASS | `rreh-eval-execution-replay-normal-v2-20260907`；全部安全硬门禁和 5 个语义维度通过 |
| Grader 校准 | PASS | 两轮独立盲评，30 个观测，agreement=1.0，阈值 0.8 |
| Regression | PASS | 12/12；6 个真实 LLM 案例、6 个零 LLM 确定性案例 |
| Regression 缓存重放 | PASS | 6/6 LLM 案例命中缓存，没有新增模型运行 |
| Ablation | NOT_COMPARABLE（合规） | 4 个代表案例、A/B/C 共 12 个运行；正常案例为 `NO_MEASURABLE_GAIN`，其余三个不具备完整可比较证据 |
| Candidate Promotion | FAIL（合规） | 安全项全部 PASS；仅 `ablation_comparability` 与旧基线 `version_completeness` 阻止晋升 |
| Promotion 负向案例 | FAIL（预期） | 明确包含 `PROMOTION_HARD_GATE_FAILED:deterministic_tests` |

## 真实运行、版本与消耗

候选版本为 `0.3.0-candidate.1`，版本 manifest SHA-256 为 `61e0f7db...4404`；产品 Runtime profile 为 `fixture-council/3.0.0`，Codex Runtime 为 `codex-cli/0.153.4`，Risk Policy 为 `risk/reference/1.0.0`。真实运行与重复评分均使用 `gpt-5.6-terra`，未使用 GPT-6 Astra。

源 Run `rreh-source-normal-20260907`：19 次 LLM 调用，输入 577,175 tokens、缓存 495,104 tokens、输出 13,866 tokens、延迟 293,119 ms。Execution Replay `rreh-execution-replay-normal-20260907`：22 次调用，输入 799,817 tokens、缓存 716,288 tokens、输出 14,447 tokens、延迟 277,479 ms。

源 Run Eval：`dev_eval` / Terra，15 次调用，输入 503,985、缓存 424,192、输出 6,678 tokens、延迟 188,599 ms。Replay Run Eval：12 次调用，输入 351,186、缓存 287,744、输出 4,640 tokens、延迟 138,571 ms。两者均保存 grader execution proof、prompt/rubric/input/output hash。

首次 Regression：12/12 PASS；6 个 LLM 案例共引用 102 次调用、输入 3,626,582、缓存 3,177,984、输出 63,526 tokens、累计延迟 1,423,391 ms；另 6 个故障注入/契约案例为零 LLM。第二次执行中 6 个 LLM 案例全部 HIT，复用同一可信产物，没有新增 LLM 消耗；报告中的历史 telemetry 用于说明复用来源，不表示再次调用。

## Agent、Skill 与 Trace 证明

源 Run 和 Execution Replay 均记录：

- `runtime_company_analyst/2.1.0`，绑定 `evidence-grounding/2.0.0`、`company-research/2.0.0`、`valuation/2.0.0`；
- `runtime_skeptic/2.0.0`，绑定 `evidence-grounding/2.0.0`、`counter-thesis/2.0.0`；
- `runtime_cio/3.0.0`，绑定 `portfolio-council/3.0.0`；
- 独立子会话、并行 Specialist dispatch、父 CIO 会话、模型、Agent/Skill/Prompt/Schema hash、输入输出 hash、Evidence closure、PIT cutoff、Risk lineage、Capsule hash 与重放来源。

源 Run 的 Company Analyst 和 Skeptic 使用不同子会话，`independent_sessions_proven=true`、`parallel_dispatch_proven=true`、`portfolio_council_skill_bound=true`。Artifact Replay 明确记录 `llm_calls=0`。

## 实际命令与退出状态

以下命令均在仓库根目录执行；重复的 Ablation/Grader 运行使用相同命令形态，仅替换 case/profile/run/eval ID。

```text
python3 -m product.runtime.cli prepare --repo /Users/caihaoming/Documents/stock_agent --fixture /Users/caihaoming/Documents/stock_agent/evals/fixtures/codex-native/normal-research.json --run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/runs/source-normal --run-id rreh-source-normal-20260907 --model gpt-5.6-terra --question "基于冻结 fixture 执行只读投资委员会研究，并输出结构化建议。" --trigger-reason acceptance:source-normal
python3 -m product.runtime.cli smoke-prompt --repo /Users/caihaoming/Documents/stock_agent --run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/runs/source-normal | codex exec -C /Users/caihaoming/Documents/stock_agent/product --add-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/runs/source-normal --strict-config --json -m gpt-5.6-terra -
python3 -m product.runtime.cli artifact-replay --repo /Users/caihaoming/Documents/stock_agent --run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/runs/source-normal --output /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/replay/source-normal-artifact.json
python3 -m product.runtime.cli prepare-execution-replay --source-run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/runs/source-normal --run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/runs/execution-replay-normal --run-id rreh-execution-replay-normal-20260907 --workspace /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/workspaces/execution-replay-normal
python3 -m product.runtime.cli finalize-execution-replay --source-run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/runs/source-normal --run-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/runs/execution-replay-normal --output-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/replay/execution-normal
python3 -m product.runtime.cli trace-check --run-dir <source-or-replay-run-dir> --output <external-trace-result.json>
python3 -m product.runtime.cli eval-prepare --repo /Users/caihaoming/Documents/stock_agent --run-dir <run-dir> --eval-dir <eval-dir> --eval-id <eval-id>
python3 -m product.runtime.cli eval-execution-proof --repo /Users/caihaoming/Documents/stock_agent --eval-dir <eval-dir> --semantic-result <semantic-result.json> --sessions-root /Users/caihaoming/.codex/sessions
python3 -m product.runtime.cli eval-finalize --repo /Users/caihaoming/Documents/stock_agent --eval-dir <eval-dir> --semantic-result <semantic-result.json>
python3 -m product.runtime.cli eval-calibration --repo /Users/caihaoming/Documents/stock_agent --labels /Users/caihaoming/Documents/stock_agent/evals/grading/calibration/v1/labels.json --grader-index /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/calibration/v2/index.json --output-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/calibration/v2/result
python3 -m product.runtime.cli regression --repo /Users/caihaoming/Documents/stock_agent --output-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/regression/first --suite-id runtime-regression-v1 --candidate-hash ae13c85f3189025de2ea9dcdd3156b3d25c15544802950f9a86e95cf4ad1edb4 --run-index /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/regression/run-index.json --cache-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/regression/cache
python3 -m product.runtime.cli regression --repo /Users/caihaoming/Documents/stock_agent --output-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/regression/cache-replay --suite-id runtime-regression-v1-cache-replay --candidate-hash ae13c85f3189025de2ea9dcdd3156b3d25c15544802950f9a86e95cf4ad1edb4 --run-index /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/regression/run-index.json --cache-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/regression/cache
python3 -m product.runtime.cli ablation --repo /Users/caihaoming/Documents/stock_agent --output-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/ablation-v3/comparison-v2 --ablation-id rreh-ablation-v3-final-20260907 --variants /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/ablation-v3/variants.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
python3 -m product.runtime.cli promotion --repo /Users/caihaoming/Documents/stock_agent --input-manifest /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/promotion/input.json --output-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/promotion/candidate
python3 -m product.runtime.cli promotion --repo /Users/caihaoming/Documents/stock_agent --input-manifest /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/promotion/input-negative-hard-gate.json --output-dir /Users/caihaoming/Documents/stock_agent/evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/promotion/negative-hard-gate
```

成功链路与测试命令退出码为 0。Ablation 因整体 `NOT_COMPARABLE` 返回 5；Candidate Promotion 和负向 Promotion 均按策略返回 5。非零状态与各自的 `result.json` 一致，不是执行异常。

## 关键产物

- 源 Run：`runs/source-normal/decision.json`、`report.md`、`decision_trace.json`、`replay_capsule/manifest.json`
- Artifact Replay：`replay/source-normal-artifact.json`
- Execution Replay：`runs/execution-replay-normal/` 与 `replay/execution-normal/result.json`
- Runtime Eval：`evals/source-normal-v2/eval/`、`evals/execution-replay-normal-v2/eval/`
- Trace：`traces/source-normal.json`、`traces/execution-replay-normal.json`
- Regression：`regression/first/`、`regression/cache-replay/`、`regression/cache-index.json`
- Ablation：`ablation-v3/variants.json`、`ablation-v3/comparison-v2/`
- Promotion：`promotion/candidate/`、`promotion/negative-hard-gate/`
- 完整路径和文件 SHA-256：`acceptance-manifest.json`

## 已知限制与诚实结论

1. 历史基线 `0.2.1-candidate.1` 没有本 Change 新增的 Assurance 字段、baseline Runtime Eval 和 baseline Ablation，因此只能作为 hash-bound legacy diagnostic，不能被宣称为 promotion-ready。
2. Ablation 的正常研究案例显示多 Agent 相对 A/B 没有可测增益；不能由该单一案例证明多 Agent 更优。
3. `insufficient-evidence` 与 `analyst-skeptic-strong-conflict` 的 full-council 运行因 Skeptic 生成未落到 Evidence 或 assumption 的 challenge 而 fail-closed；`mandatory-no-trade` 在 Agent 前安全终止。三者缺少完整语义或遥测，所以整体只能是 `NOT_COMPARABLE`，不能静默记 0 或虚构增益。
4. 上述 Specialist 偶发非法输出暴露的是现有产品约束边界；本 Change 保持 Validator 严格，没有加入静默修复或投资判断规则。
5. 旧的首次校准失败和早期诊断运行被保留用于审计；权威校准为 `calibration/v2/result/result.json`，权威 Ablation 为 `ablation-v3/comparison-v2/result.json`。
6. 本 Change 不接真实行情、SEC/FRED、新投资 Agent、Reflection Agent 或自动交易，也不自动修改 Skill 或版本指针。

## 待办边界

Task 11.10 尚未执行：需要独立、只读 Release Gate 和人工批准。完成该门禁前，不得标记 Change 完成，不得归档或晋升版本。
