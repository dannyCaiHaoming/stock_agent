## Why

当前 Codex-native Investment Council 已能保存结构化运行包、执行确定性 Artifact Replay 和单次 fixture Eval，但历史重放仍依赖当前工作区资源，现有 Ablation、Regression 与 Promotion 主要停留在数据结构或人工候选报告层，无法证明候选版本在真实 Runtime 产物上的可复现性、质量增益和安全性。现在需要建立从冻结运行、Execution Replay、真实 Eval、固定回归、Ablation 到人工晋升门禁的完整可审计闭环，为后续版本迭代提供可信基础。

## What Changes

- 为每次可重放运行保存内容寻址的 Replay Capsule，冻结 Portfolio、PIT Gate 后 Evidence、Agent、Skill、Prompt、Schema、Model、MCP Adapter、Risk Policy、数据和运行时版本；缺失、哈希漂移或模型不可用时 fail closed。
- 明确区分只读、无 LLM 的 Artifact Replay 与使用全新 `run_id`、全新目录重新调用 Codex Agent 的 Execution Replay；重放不得覆盖或补写历史运行包，也不要求自然语言输出逐字一致。
- 建立统一、终态感知的 Runtime Trace Integrity Validator，覆盖输入、Evidence/PIT、Agent/Skill/Prompt/Schema/Model、输入输出哈希、Risk lineage、`terminal_state` 和 `failed_stage`，并保持 Risk 前失败可无 Risk lineage 的既有契约。
- 将 Eval Runner 升级为直接消费真实 Runtime 产物、Trace 和 Replay 结果的自动评估，输出 `eval/result.json` 与 `eval/report.md`；Evidence、PIT、Risk、Schema 和 Trace 使用确定性硬门禁，Thesis、反证、冲突处理、NO_TRADE 解释与 Confidence 校准使用版本化、可审计的结构化 rubric。
- 建立 12 个固定 Regression 案例，每个案例只声明 `expected_invariants`、适用 Eval 维度、数据/版本锁和是否需要真实 LLM，不硬编码具体股票结论或固定 Confidence 数值。
- 在完全相同的 Portfolio 与 PIT Evidence 上运行隔离的三组 Ablation：CIO only、Company Analyst + CIO、Company Analyst + Independent Skeptic + CIO；比较质量、安全、Schema、token 和延迟，并如实报告无增益或负增益。
- 建立机器可读 Promotion Gate，直接聚合确定性测试、真实 Runtime Regression、Ablation、Trace 完整性和成本结果；Evidence Closure、PIT Leakage、Risk Bypass、Schema 与必要 NO_TRADE 场景为不可被平均分抵消的硬门禁。
- Promotion Gate 只输出候选建议 `promotion/PASS` 或 `promotion/FAIL + reasons`；`PASS` 不自动修改生产版本指针，仍需开发控制面人工批准和既有 Promotion Record。
- 固定模型路由：普通开发使用 GPT-5.6 Sol，重复 Runtime Regression/Ablation 使用 GPT-5.6 Terra；只有架构或 Eval 方法存在记录在案的重大争议时，才允许人工批准升级 GPT-6 Astra。Regression 根据案例标签、版本变化和缓存策略避免无意义重复 LLM 调用。
- 保持现有动作契约不变；需求中的“REDUCE 类”使用现有 `TRIM` 或 `EXIT` 场景表达，不引入新的 `REDUCE` 枚举。
- 明确不增加真实行情 Provider、SEC/FRED、Market/Sector/Options Agent、社区或政客数据、Reflection Agent、Skill 自动修改、券商接入或真实下单能力。

## Capabilities

### New Capabilities

- 无。该 Change 加固现有 Trace、Replay、Eval、Council 编排和受控晋升能力，不创建新的产品能力域。

### Modified Capabilities

- `decision-trace-evaluation`: 增加冻结 Replay Capsule、统一 Trace Integrity Validator、Artifact/Execution Replay、真实产物 Eval、固定 Regression Set 与三组 Ablation 的行为契约。
- `portfolio-council-orchestration`: 增加 Execution Replay 与隔离 Ablation Profile 的 Codex-native 执行约束，确保重放使用新运行身份且不削弱默认 Council 链路。
- `controlled-learning-loop`: 将 Promotion Gate 绑定到真实 Regression/Ablation/Trace 产物和安全硬门禁，同时保留人工批准、不可自动修改生产系统与可回滚要求。

## Impact

- 主要影响 `product/runtime/` 的 Replay、Trace、Eval、运行包与 CLI 边界，以及相应版本化 JSON Schema 和产品版本清单。
- `evals/` 将增加固定 Regression 数据集、真实运行索引、Ablation 运行与比较产物、Promotion Gate 结果和人类可读报告；现有人工静态 `candidate-*.json` 不再能单独满足晋升证据要求。
- `tests/` 将增加 Replay Capsule 漂移、终态矩阵、真实产物 Eval、Regression invariants、Ablation 可比性、模型路由、成本预算和 Promotion 硬门禁测试。
- 不引入独立 Python LLM 编排后端；Python 仅负责冻结、校验、编排准备、数学/风控、聚合评分和存储，实际 Investment Council 与需要语义判断的 Eval 仍由 Codex-native Skill/Agent 运行。
- 本 Change 只生成研究建议与离线评估产物，不增加外部市场数据或任何交易执行权限。
