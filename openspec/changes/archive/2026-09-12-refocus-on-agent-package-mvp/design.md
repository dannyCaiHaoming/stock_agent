## Context

参见 [proposal.md](proposal.md)。仓库现有产品包已经包含 `portfolio-council` Skill、三个 runtime Agent 定义、Evidence/PIT、Risk、产物契约和大量发布级验证模块。当前真实产品入口要求 LLM、完整执行证明和 Eval；另有 `product/council/orchestrator.py` 作为测试专用 callback 状态机，明确不能证明 Codex Agent 参与。新的 MVP 不能把该测试状态机重新包装成真实运行，也不应为了演示数据流启动 nested Codex 或继续扩展验证平台。

工作区同时保留暂停中的 `us-equity-live-advisory-slice` 及其未提交修改。实现时必须按文件与实际 diff 保护这些工作，不使用 stash、回退或整文件覆盖清理现场。

## Goals / Non-Goals

**Goals:**

- 让开发者用一个本地确定性命令看见 Portfolio 到最终报告的完整多 Agent 数据流。
- 验证实际 Plugin、入口 Skill、Agent definitions、Skills、Tool/MCP 契约和输出 Schema 形成一张可检查的 Agent Package 拓扑，而不是只创建同名 Python 对象。
- 让 Company Analyst、Independent Skeptic 和 CIO 都能使用同一套明确契约单独响应，并能无人工改写地接入下一节点。
- 让 Demo Adapter 与未来 Codex/MCP Adapter 共享稳定 Port，后续可以逐个替换 Agent，而不用重写全链路。
- 保留 PIT、Evidence Closure、Schema、Risk、只读与禁止真实交易等产品安全边界。
- 把高级验证从默认开发主路径移走，同时保留实现和显式入口供未来按需使用。
- 用最少的聚焦测试证明装配、传递、失败传播和默认入口没有隐式启动重型能力。

**Non-Goals:**

- 不证明真实 LLM、Agent Skill 推理质量、真实数据质量或真实投资建议能力。
- 不恢复或完成 `us-equity-live-advisory-slice`，不修改其 21/24 状态。
- 不删除 Replay、Regression、Calibration、Ablation、Promotion 或历史证据。
- 不新增 Agent、真实 Provider、网络、代理、沙箱、券商或下单功能。
- 不把 Demo 示例内容演化成 Python 投资判断规则。

## Decisions

### 1. 新增隔离的 `DEMO_SCAFFOLD`，不放宽真实产品 Profile

Demo 使用独立 profile、入口和产物身份。真实 fixture/live `portfolio-council` 继续遵守现有真实 LLM 与 Skill 约束；真实调用失败时不能回退到 Demo。

选择该方案是为了让“架子可运行”和“真实研究可验收”成为两个清晰里程碑。备选方案是在现有产品 Profile 中增加 `--fake`，但这会让 synthetic 产物更容易被误当作真实建议，因此不采用。

### 2. 用 `AgentPackageTopology` 证明实际 Package 接缝

Demo 启动前解析一份最小拓扑清单，逐项绑定仓库中的实际资源：

```text
product plugin
  -> portfolio-council Skill
  -> CIO role policy
  -> runtime_company_analyst
       -> evidence-grounding / company-research / valuation
       -> evidence.query / math.calculate
       -> AgentResearchReport
  -> runtime_skeptic
       -> evidence-grounding / counter-thesis
       -> evidence.query
       -> CounterThesisReport
  -> deterministic Risk Engine
  -> Final Decision / Report
```

拓扑同时列出 `runtime_market_catalyst` 为 `excluded_from_demo` 及原因，保留未来扩展槽但不实例化空 Agent。每个节点记录 Capability-first 五段映射：Input、Tool/Data、Skill/Reasoning、Structured Output、MVP Check。Demo 对 Skill 使用 `binding_verified=true`、`reasoning_executed=false`；不能把文件存在写成实际推理证明。

备选方案只注册三个 Python Responder 名称。它能证明函数串联，却不能证明 Codex Agent Package 的资源关系，因此不采用。

### 3. 使用稳定的 AgentPort、ToolPort 和独立 Dispatch Record

Demo 定义两个最小版本化信封：

- Request：运行身份、调用身份、发送者、接收 Agent、Portfolio/Evidence 或上游 Artifact References。
- Response：运行身份、调用身份、Agent 身份、领域状态、输入引用、角色输出、`producer_type` 和 `llm_used`。

Agent Response 不包含 `next_recipient`，因为专业 Agent 不负责决定流程拓扑。编排层单独写 Dispatch Record，记录 `from`、`to`、`artifact_ref` 和校验结果。三个角色共享外层 Envelope，`output` 使用各角色明确的子 Schema；编排器传递原始已验证对象，不把 JSON 重新转写成自然语言后再解析。

Responder 只能通过 `EvidenceQueryPort` 按 `allowed_evidence_ids` 获取 Gate 合格事实；Company Analyst 可再使用 `DeterministicMathPort`。首版 Adapter 可以进程内实现，但请求/响应与现有只读 MCP Tool 契约兼容，禁止读取原始 fixture、Evidence 文件或隐式全局状态。后续替换为 MCP 或 Codex Adapter 时，Port 与上下游 Schema 不变。

### 4. 每个角色使用独立 Demo Adapter，示例内容来自 fixture

Company Analyst、Independent Skeptic 和 CIO 分别注册为独立组件和独立 `invocation_id`，不能由同一个通用回调仅替换角色名。Adapter 只读取本角色可见的合成 fixture 段、ToolPort 结果和合法上游对象，完成结构封装与少量机械投影；示例 Thesis、反证和动作写在明确的 synthetic fixture 中，不编码为股票判断 if/else。

角色定义和预期 Skill 绑定来自 `AgentPackageTopology`，但 Demo 响应必须记录 `producer_type=deterministic_demo`、`llm_used=false`、`skill_reasoning_executed=false`。后续开发真实 Agent 时，按节点切换到 Codex Adapter 并单独验收真实 Skill/LLM。

`CIO Demo Adapter` 只实现 CIO Request/Response Contract，不是第三个被委派的 Codex Subagent，也不证明当前主线程已担任 CIO。真实 Profile 中仍由 `portfolio-council` Skill 把 CIO Role Policy 加载到当前 Codex 主线程。

### 5. 使用固定 fan-out/fan-in 和显式终态

首版只实现：

```text
DemoInput -> Evidence Store/PIT Gate -> logical fan-out
                                      -> Analyst Adapter --+
                                      -> Skeptic Adapter --+-> CIO Adapter -> Risk -> Report
```

Demo 必须证明两个 Specialist 接收独立输入并在 CIO 前汇合；不要求线程级并发，因为本阶段不声称验证 Codex Subagent 生命周期。两个输入均来自同一 Gate 结果，并且不含对方输出。CIO 只有在取得两份 Schema 合法的 Response Envelope 后才接收它们。

Agent 领域状态沿用 `COMPLETE`、`INSUFFICIENT_EVIDENCE`、`LOW_CONFIDENCE`、`TIMEOUT`。后面三种是可传递的合法响应，由 CIO 形成保守草案或 `NO_TRADE`；非法 Schema、身份、跨 run 或 Evidence Reference 进入失败终态。Demo 终态固定为：

- `DEMO_COMPLETED`：双 Specialist、CIO 与 Risk 均完成。
- `DEMO_SAFE_NO_TRADE`：Gate 后无可用 Evidence，或 CIO/Risk 形成合法 `NO_TRADE`；Gate 前终止时不伪造 Agent 响应。
- `DEMO_FAILED_VALIDATION`：输入、角色输出、引用、传递或产物校验失败。

动态 Agent 选择、自动重试、真实超时控制、定向第二轮反证和更多专业角色推迟到相应真实 Agent 开发。

### 6. 复用现有确定性安全组件，只新增最小 Demo 封装

Demo 复用现有 Portfolio、Evidence Store/Bundle、Evidence Gate、Evidence Closure、canonical decision contract 和 Risk Engine。新增逻辑只负责 profile 识别、Package 拓扑校验、Port/Envelope 校验、独立 Adapter 调用、Dispatch Record 和 Demo 产物编排。

`decision.json` 使用独立的 `DemoDecisionEnvelope`：外层保存 Demo Profile、synthetic/llm/terminal 标识，内层 `decision` 继续通过 canonical decision contract。这样不向真实产品 Decision Schema 塞入 Demo 字段，也不会让 Demo 文件被真实产品读取。中文报告只从该 Envelope、Agent 响应、Dispatch 和 Risk 结果渲染。

Demo Trace 只需一份轻量 `demo_run.json` 或等价运行清单，记录节点顺序、Dispatch、输入输出文件和终态；不生成或要求 Replay Capsule、完整版本锁、模型事件、token、语义评分和 Promotion 证据。

### 7. 高级验证“停用默认路径”，不做源码注释或删除

用户所说“注释掉”落实为：

- 根文档和常用入口不再把 Runtime Eval、Replay、Regression、Calibration、Ablation、Promotion 列为普通开发的后续步骤。
- Demo 命令和默认自检不会调用上述能力。
- 现有模块、Schema、测试和显式子命令原样留存；只有用户明确维护该能力或申请候选晋升时才执行。
- 不通过大段代码注释制造无法测试的死代码，也不删除历史能力导致未来无法参考。

这比直接删除更符合“后续看看有没有参考价值”，同时避免本 Change 演变成验证平台拆除项目。

### 8. 将批准点收敛为实施授权与最终发布授权

apply 获批后，范围内文件编辑、普通修复和聚焦测试连续执行。只有新增权限、破坏性动作、外部付费/凭证、范围或安全契约变化、无法自行解除的阻断才中途暂停。最终归档与 Git 推送仍需要一次明确人工完成批准。

独立 Reviewer 不作为本 Demo Change 的默认完成条件；若用户明确要求，只读复核可以执行，但不能自动升级成完整 Release Gate。

### 9. 暂停 live Change 采用标记与入口隔离，不改写历史

实施时为 `us-equity-live-advisory-slice` 增加清晰的暂停说明或等价状态记录，说明它不属于当前默认 MVP；不勾选 5.3–5.5、不归档、不删除代码和证据。若某个文件与本 Change 必须重叠，只编辑可明确归属的行并在完成摘要中列出。

## Risks / Trade-offs

- [Demo 运行成功可能被误解为真实 Agent 已可用] → 所有入口和产物强制 synthetic/demo/llm_used=false 标识，真实验收明确拒绝 Demo。
- [Demo 退化为普通 Python 编排] → 以实际 Package 拓扑、稳定 AgentPort、MCP-compatible ToolPort 和逐节点可替换 Adapter 作为完成条件；Demo 编排不得进入真实产品 Profile。
- [确定性示例掩盖真实 LLM 集成问题] → 将“数据流完成”和“真实 Agent 完成”作为不同 Capability；后续每开发一个真实 Agent，再对该节点做切面 Smoke。
- [保留高级验证源码仍带来目录复杂度] → 默认文档和入口隐藏它们，但不在本 Change 中删除；未来确认无参考价值后再单独清理。
- [工作区 live 修改与本 Change 文件重叠] → 使用文件级和 hunk 级差异核对；无法安全分离时只报告具体重叠，不回退用户工作。
- [Demo fixture 出现硬编码投资结论] → 示例内容必须标记 synthetic 并存放在 fixture，不在 Python 中根据证券或指标生成主观判断。
- [简化验收降低缺陷发现率] → PIT、Evidence、Schema、Risk 和禁止交易仍是硬门禁；降低的只是与当前 Demo 目标无关的运行次数和发布级证明。

## Migration Plan

1. 增加 Demo Profile、`AgentPackageTopology`、Capability 五段映射、Port/Envelope/Dispatch Schema 和合成 fixture。
2. 增加只读 ToolPort、独立角色 Demo Adapter、单 Agent 调用与完整 fan-out/fan-in Demo 入口，生成最小可审阅产物。
3. 更新默认开发说明和常用入口，移除隐式高级验证；保留显式命令及源码。
4. 标记 `us-equity-live-advisory-slice` 为暂停参考，不改变任务完成状态。
5. 运行受影响的 Schema、隔离、传递、失败传播、Risk 和入口聚焦测试，再运行一次零 LLM Demo。
6. 提交用户审阅；未获最终批准不归档、不提交、不推送。

回滚时删除 Demo Profile/入口及其新契约，恢复默认文档入口即可。现有真实产品、live 工作、发布验证源码和历史证据未被迁移，因此无需数据回写。
