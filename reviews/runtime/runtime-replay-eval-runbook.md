# Runtime Replay、Eval 与 Promotion 运行手册

本文描述开发控制面的离线验证流程。所有输出仅用于研究建议验证；不得连接券商、修改账户或真实下单。

按当前任务读取所需章节，不要求每次执行完整手册。验收范围与证据复用见 [开发流程](../../docs/development/workflow.md)，权限及路径见 [开发环境](../../docs/development/environment.md)。以下模块命令从仓库根执行；正常研究由原生宿主执行，旧维护才加载明确冻结工作区；cwd、配置或文件存在不证明资源已加载。

## 1. 原生运行与持久化

正常研究/Smoke在用户所选Codex、Claude Code或OpenCode的当前原生产品会话执行。使用共享portfolio-council和四职责正文，原生主线程委派、等待并回收结果；Python不创建另一模型进程。安装、样本/阶段、实际模型、时间/调用上限和停止条件另获批准；三份薄模板、合成检查和旧Codex记录都不证明三个宿主实际通过。

Claude Code使用现有CC Switch映射时，专业角色沿inherit，native Skill不覆盖model。运行授权/记录分别说明宿主选择或别名、用户批准映射目标与主子实际可观察模型；有明确映射时不因名称不同判冲突。用户声明不等于配置读取证明，转录不等于Provider wire；未知身份不补造。无已知映射、观察到未批准目标或实际不可用仍按窗口条件停止，不读/分发CC Switch数据库、API key或完整环境，不自动换模/重派，旧评分/维护锁不变。

Claude正常入口是当前仓库 `product/`；外置目录仅存私有数据，不是另一产品项目。就地准备、同请求多任务复用、来源证据复用、连接加载条件及必要观察的取得时点统一见 [产品使用说明](../../product/hosts/INSTALL.md)，不在运行手册重复接线/诊断流程。真实Smoke仍需当前有效阶段、模型/预算/停止点授权及必要宿主能力，配置/绑定/业务/原生执行/内容分列；缺证按对应阶段阻断，不恢复旧窗口、改hash重试或另起模型后端。

### 1.1 普通股专项运行前门槛

确认PortfolioHandoff或核实的SINGLE_STOCK_RESEARCH与冻结Gate，保留完整资产覆盖。任务准备绑定请求、角色、证券、cutoff及允许对象，私有能力凭据只防误路由，不认证实际作者。Company专业范围、附件状态、查询/计算血缘、两稿上限及历史包的只读验证不放宽。旧Hook的256 KiB和run-scoped进程协议仅解释冻结旧包，正常工具不要求另一CLI或旧版本号。

资料准备与正式研究分开：只有明确获来源授权的准备任务可search/fetch，实际尝试和配置失败保留。BODY_VERIFIED正文经实际读取后由作者明确选择；目录不等于消费，超过已实现响应上限明确停止，不截断正文。同行目录只是候选，原确定性物化器验证实际选择后冻结事实。新共同cutoff须保留原准备请求和事实血缘；显式过去时点不得借新取数推进。

### 1.2 多维依赖与完整覆盖

八维及Company全部保留；RESEARCH_REPORT等待合格基本面/正文，行业消费实际已核实同行，Macro/Market各保存共享市场研究。Python只验证回执、合法依赖与覆盖，不重建原生Agent生命周期。部分失败保留成果，只阻断真实依赖，不能将定点或核心切片称为完整八维。严格复用明确冻结版本时校验完整输入、Gate、研究范围、依赖及业务资源，不派新模型、不自动选择“最新”报告、不改原cutoff或状态。

### 1.3 非持仓单股与显式综合

只提供股票代码时不伪造Handoff、数量、账户或Mandate。用户选择公司、多维、独立反证或显式综合停止点；不自动推进。独立Skeptic首轮只能接收原始允许资料和非结论性问题，不能继承正向历史或读取正向报告；宿主实际隔离不可证时阻断。

综合由当前主线程实际read获准报告、query采用事实并解释重要反证，仅输出RESEARCH_SYNTHESIS、advisory_only=true、Risk=NOT_RUN。PORTFOLIO_ADVICE在准备时拒绝，不输出动作/仓位/金额。既有fixture数据/硬Risk契约保留，真实原生fixture能力须有相应入口与实际证据，不能由研究级结果推导。

业务验证、宿主观察和内容裁定分列，UNKNOWN不补造成旧执行身份。原稿、实际读取/查询/计算收据及同源中文保存于获准仓库外目录；私人凭据、原工具转录和账户正文不进入Git。未完成、超时或失败保留剩余项，未经授权不重跑。

旧normal/stage/resume/launch模型入口及五父串联已退役，在取数、代理探测、目录写入或模型前拒绝。日常研究不得恢复旧shell命令、Codex专属Hook/状态工具或换另一宿主；冻结旧Execution Replay单独见第3节。

## 2. Artifact Replay

### 原生提交与冻结旧格式读取

原生作者使用research_submit提交研究字段与精确选择，首稿加最多一次原作者定位修订；服务端从可信任务和实际工具记录装配技术元数据并返回唯一不可变回执。读取使用research_read_submission，不解析Codex Stop、不抄hash、不猜最后一稿。权限/完整性错误不能借宽松纠正绕过。旧research-object-submission等协议及Hook材料按冻结版本读取，不为新原生运行开放旧写入或改写原事件。

```text
python3 -m product.runtime.cli artifact-replay \
  --repo <repository-root> \
  --run-dir <source-run-dir> \
  --output <external-replay-result.json>
```

该命令只读验证历史运行包和 Replay Capsule，LLM 调用数必须为 0，输出必须位于源 Run 目录之外。缺失对象、hash 漂移或路径逃逸均 fail closed。

统一 Trace 报告可用以下命令生成，供 Promotion 证据图引用：

```text
python3 -m product.runtime.cli trace-check \
  --run-dir <run-dir> \
  --output <external-trace-integrity.json>
```

## 3. Execution Replay

本节仅适用于另获源包、冻结版本、模型/调用预算及停止条件授权的旧维护。宿主执行命令为：

```bash
bash <repository-root>/scripts/run-product-smoke.sh --prepared-run <run-dir> <new-invocation-output-dir>
```

正常原生研究不使用此入口，旧维护也不能只看 shell exit code；必须重验冻结版本要求的实际运行/资源证据与终态。

先通过安装仓库的薄入口物化密封工作区并准备新的 Run（不是额外创建项目沙箱）：

```text
python3 <repository-root>/scripts/council-dev.py prepare-execution-replay \
  --source-run-dir <source-run-dir> \
  --run-dir <new-run-dir> \
  --run-id <new-run-id>
```

该薄入口在新 Run 保存 `host-replay-source.json`，供宿主 transport 校验来源 Capsule；直接使用底层 prepare 命令不会创建此绑定，不能用于随后宿主执行，也不得手工向旧 Run 补写。随后在宿主 Terminal 使用上述 --prepared-run 入口，既有转发器按 manifest 选择冻结 workspace，先经当前check-frozen-replay验证源manifest/封闭快照，再由execute-frozen-replay转发冻结旧版本自己的nested-codex-smoke；当前工作树的该模型命令仍明确退役；不要手动传当前仓库的 --repo，不要使用当前工作树替换冻结资源或临时复制缺失文件。独立 Reviewer 只提出补跑缺口，不自动执行。完成后运行：

```text
python3 -m product.runtime.cli finalize-execution-replay \
  --source-run-dir <source-run-dir> \
  --run-dir <new-run-dir> \
  --output-dir <comparison-dir>
```

Execution Replay 要求 Portfolio、PIT Evidence、Agent、Skill、Prompt、Schema、Model 和 Risk Policy 等可观察配置一致，但不要求自然语言、合法动作、Confidence、token 或延迟逐字一致。

## 4. Runtime Eval

先创建外置 Eval Job：

```text
python3 -m product.runtime.cli eval-prepare \
  --repo <repository-root> \
  --run-dir <run-dir> \
  --eval-dir <new-eval-dir> \
  --eval-id <eval-id>
```

显式 Eval Job 准备后保留完整校验输入 `grader-input.json`，并生成移除外围重复技术包装的 `grader-model-input.json`、`grader-prompt.txt` 和权威 `semantic-output-schema.json`。独立 `dev_eval` 使用 `runtime-eval-grading`，在自己的子会话完整读取冻结 manifest 和模型视图，输出 native 语义草稿；不抄写 hash，也不自行写正式结果。视图不递归删除事实字段，读取证明、等价性及文件字节统计由程序核验，不把字节当 token。协调线程沿原收集入口读取真实 rollout：

```text
python3 -m product.runtime.cli eval-execution-proof \
  --repo <repository-root> --eval-dir <eval-dir> \
  --semantic-result <eval-dir>/semantic-result.json --sessions-root <codex-sessions-root> \
  --collect-native-output

python3 -m product.runtime.cli eval-finalize \
  --repo <repository-root> \
  --eval-dir <eval-dir> \
  --semantic-result <semantic-result.json>
```

权威产物为 `eval/result.json`，`eval/report.md` 由同一结果确定性渲染。带语义评分的真实 Eval 必须先通过 `eval-execution-proof`，静态 JSON 不能代替真实 `dev_eval` 会话。Eval 不回写源 Run。预期 `FAILED_VALIDATION` 案例可通过重复的 `--expected-terminal-state FAILED_VALIDATION` 进行诊断。

收集返回 `EVAL_LOCAL_REVISION_REQUIRED` 时只是待修订，不是 PASS：协调线程仅向返回的原 `child_session_id` 使用一次原生 `send_input`，消息为完整 `feedback`；等待同一子会话完成后再次收集。局部补丁只改允许路径，保留两版原文并完整再验；第二次失败、其它字段漂移或基础稿损坏均终止，禁止另派 grader 或重置额度。只有 `EVAL_EXECUTION_PROOF_VERIFIED` 才进入 `eval-finalize`。合法的低分或 FAIL 不触发重评。当前带局部修订标记的执行证明会重读原 rollout/原稿；不回填历史结果或扩大旧证据的适用范围。上述命令属于显式维护任务，不是普通开发自检的自动步骤。

Rubric 校准使用人工标注的固定样本，并至少进行两次相互独立的 `dev_eval` 盲评。若同一维度的状态不一致或 grade 差值超过门槛，校准必须 FAIL；不得修改原始评分来追求通过。

## 5. Regression 与 Ablation

Regression Set 位于 `evals/regression/v1/`。需要 LLM 的案例必须在 run index 中引用真实冻结 Run 和外置 Eval（新默认 Luna，历史 Terra 保留原锁）；确定性反例不得调用 LLM。无变化时按 case、候选、模型、Profile、Evidence、Rubric 和 Grader hash 复用已验证缓存。

```text
python3 -m product.runtime.cli regression --repo <repository-root> \
  --output-dir <suite-dir> --suite-id <suite-id> \
  --candidate-hash <sha256> --run-index <run-index.json> \
  --cache-dir <verified-cache-dir>
```

缓存记录必须反向引用仍可验证的 Run、Eval 与来源 hash；命中时报告 `reused_from`。仅在人工明确要求重新调用模型时使用 `--force`。

Ablation 使用相同输入分别运行 `cio-only`、`analyst-cio` 和 `full-council`。三个 Variant 都必须经过同一 Risk Engine，并锁定相同的 Portfolio、PIT Evidence、Model、完整 version lock、Risk Policy 与 Rubric。缺少语义质量时结论为 `NOT_COMPARABLE`；缺少 token 或延迟时显示 `MISSING_TELEMETRY`，不得记为 0。

```text
python3 -m product.runtime.cli ablation --repo <repository-root> \
  --output-dir <ablation-dir> --ablation-id <id> \
  --variants <variants.json>
```

`variants.json` 可包含一个三 Profile 案例，也可使用 `{"cases": {...}}` 聚合版本化代表案例集。任一代表案例不可比较时，整体不得宣称有增益或无增益。

## 6. Promotion Gate

Promotion 输入必须是 hash-bound 证据图，引用确定性测试、Regression、Execution Replay、候选与基线 Runtime Eval、候选与基线 Ablation、Trace、模型政策、候选与基线版本。静态 candidate 摘要不能代替这些产物。

确定性测试证据必须由独立子进程实际生成，保存命令参数、独立且可写的 `TMPDIR`、起止时间、进程 ID、退出码、测试计数，以及 stdout/stderr 原文与哈希：

```text
python3 -m product.runtime.cli test-evidence --repo <repository-root> \
  --output-dir <test-evidence-dir> --tmpdir <empty-writable-tmpdir>
```

Promotion 不接受手工填写的 PASS 摘要作为测试证明。测试事件中的计数、退出码或 transcript 不一致时必须 fail closed。

```text
python3 -m product.runtime.cli promotion --repo <repository-root> \
  --input-manifest <promotion-input.json> \
  --output-dir <promotion-dir>
```

结果目录只会包含 `PASS` 或 `FAIL` 其中一个 sentinel，并同时生成 `result.json`、`report.md` 和 `input-manifest.json`。Evidence Closure、PIT、Risk bypass、Schema、Trace 和必须 NO_TRADE 案例是硬门禁。PASS 仍不修改生产版本，必须等待人工批准。

每次 Gate 必须使用新的 `gate_id`；重复检查相同证据时只要求硬门禁和 reason codes 保持一致，必须写入新的历史记录。候选 Eval/Ablation、基线 Eval/Ablation 必须分别从各自版本的 Runtime Trace 解析，路径或内容哈希复用会被视为自我比较并拒绝。

旧 baseline 若缺少当前 Assurance 字段，可以作为带 hash 的诊断输入，但 `version_completeness` 必须 FAIL；Gate 应输出可审计原因，而不是异常退出或静默借用候选版本资源。

## 7. 模型与消耗

- 普通开发：`gpt-5.6-sol`。
- 新产品、重复 Regression/Ablation 与语义评分默认：`gpt-6-luna`；Execution Replay 使用来源密封模型，历史 Terra 不重标。
- `gpt-6-astra`：仅限记录在案的重大架构或 Eval 方法争议，并要求 dispute ID 与人工批准产物。

每次真实 LLM 执行从 Codex rollout 的 `token_count` 与时间戳生成最小化遥测，记录模型、输入/输出 token、可用的 cache token、延迟、调用数、触发原因和 cache provenance。原始 Prompt 与隐藏推理不会复制进证明。缺失遥测标记为 `MISSING_TELEMETRY`，不能当作零成本。
