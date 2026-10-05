## Why

当前开发会话会自动发现并启动产品研究 MCP，其中 `fixture_runtime` 已出现握手失败；安装包沿用交易记录功能发布时保留的旧投研基线，与仓库当前研究指令存在差异。开发/产品 AGENTS 的阶段描述、解释器使用及部分旧配置也未完全对齐，导致入口误解与重复排障。

## What Changes

- **BREAKING**：按用户选择 A，普通开发会话保留产品 Skills，但不自动启动插件中的 `fixture_runtime`、`live_runtime`；需要研究时只由既有宿主 launcher 按运行绑定解释器、产品根、run 和阶段工具权限。普通会话直接使用这两个研究 MCP 的方式不再支持。
- 统一根 AGENTS、产品 AGENTS、CIO 兼容角色与插件介绍：独立 Intake/交易记录/复盘不自动启动 Council；单股与阶段研究不继承完整 fixture Council 的动作、Risk 和重试政策。
- 对照已批准来源和依赖闭包准备新的洁净产品包，保留交易记录功能、私密目录排除和可恢复安装基线；验证实际注册与缓存后才确认更新成功。版本差异不自动等于漏发，也不把工作树整体打包。
- 使用项目 `.venv` 和已有基础依赖声明，明确开发检查及宿主启动时的解释器选择；清理长期文档中的历史任务状态。
- 将新产品运行（完整 fixture、研究阶段、重复 Runtime）及新语义评分/Calibration 的默认模型统一为 `gpt-6-luna`；冻结评分模型并核对实际执行身份。历史包、旧候选与 Replay 锁保留原字节。
- 将用户级已移除 `js_repl` 开关清理列为独立本机维护；当前不存在的 Guardian `thread_context` 不作虚构修复。

- 用户确认纳入旧 Regression 交接修复：零 LLM 合成 CIO 使用当前冻结目录、实际报告读取与 native 草稿装配；契约夹具的评分明确不适用，不伪造 Luna 评分。

- 用户确认纳入 Promotion 评分证明拒绝的异常处理：保留底层拒绝，输出含错误原因的可审计 FAIL，正常通过路径不变。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `codex-development-environment`：研究 MCP 按运行启用、项目解释器可复现、洁净分发与实际安装核对，以及新运行/评分的 Luna 默认模型。
- `three-plane-governance`：产品指令按入口与阶段适用，配置维护与用户级规则变更保持明确范围。

## Impact

- 预期涉及 `product/.mcp.json`、`product/runtime/nested_codex.py` 及受影响的宿主命令生成路径；`AGENTS.md`、`product/AGENTS.md`、产品 CIO 配置、插件介绍、`README.md`、`docs/development/environment.md`；产品模型路由与当前 manifest、`dev_eval`、评分装配/证明、Calibration 以及已有 Regression/Promotion 消费者中的模型版本校验；受影响配置/启动/安装测试及版本镜像。
- 复用 `product/trading_journal/packaging.py` 的批准基线、overlay、注册与隔离验证，不放宽其交易记录发布白名单；必要的研究包准备逻辑归开发工具，不新增产品 Agent 或编排器。
- `.codex-local/product-plugin` 与安装缓存属于本机发布产物；用户级配置只作限定键维护，不进入项目提交。
- 已获 apply 与模型方案 B 授权，范围内实施、安装切换、依赖安装及确定性验证持续进行；真实产品 Smoke 另需明确场景、模型预算及宿主执行授权。

## Non-goals

不修改全局 Git 免审批规则、当前开发模型/沙箱、手动模型选择的既有约束、历史运行锁或生产晋升指针；不更新其他全局插件或 CLI，不读取连接器凭据，不执行券商同步、私人交易写入、全量研究、Replay/Eval/Promotion，不修改并行 Change。

- 2026-10-05 用户选择更新后续候选 CLI 锁为 0.160.0，并补宿主模型前实际版本核验；原 Smoke 保留差异，新增模型调用为 0。
