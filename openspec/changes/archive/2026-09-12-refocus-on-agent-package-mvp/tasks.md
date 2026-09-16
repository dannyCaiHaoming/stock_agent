## 1. Demo Profile 与数据契约

- [x] 1.1 增加独立 `DEMO_SCAFFOLD` Profile 和版本化 Demo 输入契约，接受任意合法 Portfolio/Evidence 文件并包含研究问题、`decision_cutoff`、synthetic/advisory/llm 标识；用合法输入、缺字段、未来 Evidence 和伪装真实 Profile 的正负测试验证。
- [x] 1.2 增加最小 `AgentPackageTopology`，从仓库实际 Plugin manifest 绑定 `portfolio-council`、CIO Role Policy、两个 Specialist Agent definitions、Skills、Tool/MCP 契约、输出 Schema、Risk 和 Final Output；为各节点记录 Input → Tool/Data → Skill/Reasoning → Structured Output → MVP Check，并验证缺失/漂移绑定失败、Market/Catalyst 仅以 excluded reason 留存。
- [x] 1.3 增加统一 Agent Request/Response Envelope、角色输出子契约和编排 Dispatch Record；从 Agent Response 移除路由决定，验证三个角色可使用同一外层协议，错误 `run_id`、Agent、发送者、接收者或 Artifact Reference 被拒绝。
- [x] 1.4 增加一个最小合成 fixture，提供各角色明确标记的 Demo 内容、领域状态样例和可触发 deterministic Risk 的数据；检查所有事实携带 `evidence_id`、`source_id`、`as_of`、`retrieved_at`，且主观示例不被编码为 Python 投资规则。

## 2. 可替换 Agent Port 与完整数据流

- [x] 2.1 实现与现有 MCP Query/Calculate 参数语义兼容的只读 `EvidenceQueryPort` 和 `DeterministicMathPort` Demo Adapter；验证只能查询当前 Gate 允许 ID、不能读取原始 fixture/Evidence 文件、未知/排除/跨 run 引用失败。
- [x] 2.2 实现三个相互独立的 Demo Agent Adapter，并验证每个角色都能从合法请求单独返回响应；确认 `producer_type=deterministic_demo`、`llm_used=false`、`skill_reasoning_executed=false`，且不能用同一个回调替换名字冒充多个角色。
- [x] 2.3 实现 Analyst 与 Skeptic 的逻辑 fan-out、隔离 Tool 查询、独立响应和 fan-in；验证两者输入不含对方结论、输出分别保留独立 invocation，非法或悬空 Evidence 在进入 CIO 前停止，同时不把逻辑隔离声称为真实 Subagent 上下文证明。
- [x] 2.4 实现 CIO Demo Adapter 消费两份已验证 Specialist Response Envelope，并由 Dispatch Record 把原始结构化草案传给现有 Risk Engine；验证跨 run 响应、缺失角色、Agent 自行选路和同一组件冒充多个角色均失败，且明确 CIO Demo 不等于 Codex 主线程 CIO。
- [x] 2.5 实现 `COMPLETE`、`INSUFFICIENT_EVIDENCE`、`LOW_CONFIDENCE`、`TIMEOUT` 的领域状态传递，以及 `DEMO_COMPLETED`、`DEMO_SAFE_NO_TRADE`、`DEMO_FAILED_VALIDATION` 终态；验证全 Evidence 排除时 Agent 前安全终止、合法降级仍进入 CIO、非法输出不能伪装 NO_TRADE。
- [x] 2.6 实现最终 Demo 产物生成：输入、Package 拓扑、PIT Gate、到达阶段的 Agent 响应、Dispatch、Risk、`decision.json`、中文 `report.md` 和轻量运行清单；`decision.json` 使用外层 Demo 元数据加内层 canonical Decision，验证报告展示 Portfolio、角色状态、Thesis/反证、共识/冲突、Evidence、数据缺口、失效条件、Action、Confidence 和 Risk，同时醒目标明 synthetic/非 LLM/非投资建议。
- [x] 2.7 提供一个本地零 LLM Demo 命令和三个单 Agent 调用方式；验证命令不访问网络、不启动 nested Codex、不执行真实 Skill/Subagent/CIO 主线程、不调用高级 Gate，并以拓扑和产物完整性而非占位文本判断成功。

## 3. 默认流程收敛与暂停隔离

- [x] 3.1 更新根 `AGENTS.md`、`PRODUCT.md`、开发流程和最小运行说明，将 Agent Package Demo 设为 Milestone 0 装配目标；明确完成后产品优先级回到真实单股研究，验证普通开发文档不再引导自动执行 Runtime Eval、Execution Replay、Regression、Calibration、Ablation、Promotion 或重复真实 LLM。
- [x] 3.2 调整常用开发/验收入口，使高级验证只能通过现有显式子命令按需启动，Demo 与默认自检不会隐式触发；保留高级模块、Schema、测试和历史命令，并以入口路由测试验证未删除也未伪造 PASS。
- [x] 3.3 同步批准边界：apply 后范围内连续实施，只有权限、破坏性动作、外部付费/凭证、范围/安全契约变化或真实阻断才暂停；最终归档和推送保留一次人工批准。用文档/配置一致性测试确认未要求逐步骤批准，也未删除最终批准边界。
- [x] 3.4 只在 Change 规划/暂停记录中为 `us-equity-live-advisory-slice` 保存明确的暂停参考标识并从当前默认 MVP 入口隔离，不把该临时状态写入永久产品规格；核对其 5.3–5.5 仍未完成、历史证据未改写、现有 live 代码和未提交修改未被删除或归档。

## 4. 限定验收与收尾

- [x] 4.1 运行 Package 拓扑、Capability 五段映射、Schema、Tool Port、角色独立性、Dispatch、PIT、Evidence Closure、三类终态、Risk、失败传播和默认入口的聚焦确定性测试；记录实际命令与结果，不运行真实 LLM 或任何高级 Gate。
- [x] 4.2 使用全新输出目录和非内置路径显式传入 Demo fixture，运行一次完整零 LLM Demo，逐项检查 Input → Evidence Store/Gate → Tool Queries → Analyst/Skeptic → Dispatch → CIO → Risk → Decision/Report；确认每个到达的 Agent 均有响应对象且输出无需人工改写即可成为下一节点输入。
- [x] 4.3 执行 OpenSpec strict validate，并核对本 Change 只证明 Agent Package 静态绑定、Demo Adapter 与数据流，不声明真实研究、Skill 推理、主线程 CIO、Subagent、live 能力或 Promotion PASS。
- [x] 4.4 向用户提交 Demo 命令、产物路径、完成范围和保留限制，取得一次明确人工完成批准后再标记完成；未获批准不归档、不提交、不推送。
