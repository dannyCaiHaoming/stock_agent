## Why

仓库已有可审计的 nested Codex launcher，但操作文档、路径假设和开发/复核权限配置没有完全收敛，容易重复排障或误把环境问题变成全产品验收。此 Change 只精简开发环境和执行契约，复用已批准能力，不重建运行框架。

## What Changes

- 根 AGENTS.md 保留原则、入口、职责、安全与完成标准，按任务条件链接少量中文专项文档；产品运行不触发开发归档和 Git 操作。
- 复用 `nested-codex-smoke`、`launch_nested_codex`、run-scoped SQLite/log/tmp、Hook、执行证明和终态判定；Smoke、Execution Replay、Regression 中需要新 LLM 执行的路径都通过同一 launcher。Artifact Replay 和纯确定性案例不启动模型。
- 明确根目录解析和固定产品 cwd，去除当前 Prompt 中个人 sessions 路径和旧管道教程；保留已密封 Replay Capsule 的合法物化机制，不允许为解决加载问题临时复制源码或凭据。
- 按人工批准分离日常功能验收与全进程隔离验收：后者保留 UNVERIFIED，排除在本 Change 完成保证之外；保留原生权限，不用 Prompt/hash 冒充隔离。
- 开发自检和独立复核默认只做确定性检查与证据读取，不隐式调用模型、doctor 或项目沙箱；保留历史专项诊断代码，区分发现、解析与实际加载证明。
- 沿用 Sol 开发、Astra 疑难分析、Terra 重复 Runtime 测试偏好；只采用本机支持的配置方式，记录请求模型与实际模型，不依赖 Prompt 自动切换。
- 以受影响范围和版本绑定决定证据复用与补测；不默认重跑 Calibration、Ablation、Promotion，不修改其安全门禁。

## Capabilities

本次用户授权补充：增加只读宿主代理检测与手动 Product Smoke 薄入口，
动态传递生效代理环境变量，仍复用统一 launcher 和 check-run。
不固化本机端口、不修改 Shadowrocket 或域名权限、不新增嵌套网络基础设施；
本轮只做零 LLM 聚焦验证，后续宿主运行不冒充独立只读复核权限证明。

### New Capabilities

- `codex-development-environment`: 统一执行路径、模式权限、版本兼容检查、实际加载证明和开发诊断入口。

### Modified Capabilities

- `three-plane-governance`: 补充按需读取开发指令、限定验收、Change 完成与候选晋升分离的要求；不删除现有三平面安全规则。

## Impact

- 预期涉及根/产品 AGENTS.md、开发 Agent 配置、现有 launcher/CLI/Prompt 中的路径与权限接口、少量开发文档、诊断 Skill、聚焦测试。详细文件清单见 Design。
- 不改变投资判断、Evidence/PIT/Risk/终态规则，不增加 runtime Agent、市场 Provider、Replay 框架或交易能力，不切换生产版本指针。
- **实施前置条件**：旧 `runtime-replay-and-eval-hardening` 已人工批准并本地归档，但 Git 发布因证据目录中的私人会话数据库暂停。旧流程须在单独明确授权下完成安全发布收尾；本提案可先评审，不能将旧敏感产物混入新提交，也不重开旧 Change、不要求旧候选 Promotion PASS。本轮不清理、上传旧证据。
- 本轮仅生成规划产物。后续实施只验证本机 macOS 与实施时明确记录的 CLI 版本；不承诺多平台权限支持。

## 已批准的范围调整

2026-09-09 用户明确批准模式分离并接受残余风险，记录见 `reviews/development/streamline-codex-development-environment-scope-approval.md`。旧 --review 明确拒绝；不修改代理配置。仅验证入口分流、无隐式启动和失败传播，复用既有 normal，不因调整关闭其他未完成任务、不启动 Replay/Regression/Gate、不归档发布。
