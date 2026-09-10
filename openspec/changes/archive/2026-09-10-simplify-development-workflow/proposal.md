## Why

当前开发流程虽已区分 Change 完成与晋升，但未明确授权内持续推进，Reviewer 的通用指令仍要求晋升批准，开发模型又被环境文档和测试绑定到产品路由。这些混用容易将阶段汇报、普通错误或发布级证明缺失变成开发停点，妨碍已授权股票需求推进。

## What Changes

- 精简根 AGENTS.md 和开发流程：显式 apply 后持续完成授权范围，阶段汇报使用进度消息，不要求用户反复回复“继续”；普通实现错误自行诊断、修复和聚焦验证，真实阻断才暂停受影响工作。
- 明确三层检查：日常开发做受影响聚焦验证；Change 按其既定 Specs/Tasks 验收、独立复核和人工批准；版本晋升另遵循完整发布门禁。不得拿后两者作为每一步开发的默认前置。
- Reviewer 按本次评审类型与差异确定检查范围，保留只读权限和安全职责，不将生产晋升批准强加到普通开发复核；同步注册描述与实际角色说明。
- 保留 Sol 常规开发、Astra 复杂分析、Terra 产品开发期 LLM 测试分工及成本控制；尊重用户明确的主会话选择，开发子 Agent 按职责与已有配置选模，Reviewer 使用实际生效配置，不承诺自动跟随主会话。仅移除手动开发选模的产品 dispute_id/批准凭证前置，以及根开发默认值必须等于产品 development_default 的断言；不删除既有模型配置，不修改产品路由、预算、权限或锁。
- 暂停并保留 `us-equity-live-advisory-slice` 的当前 19/24 进度及全部未提交修改。小 Change 按现有人工批准规则收尾、仅提交自身差异后，重新读取开发规则并恢复原股票任务；不将暂停当作完成或归档。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `three-plane-governance`：授权范围持续实施、开发/验收/晋升分层、Reviewer 的范围化复核，以及并行未完成 Change 的保留与限定提交。
- `codex-development-environment`：开发模型手动选择与产品路由隔离，保留实际配置能力与模型不可用时的诚实报告。

## Impact

限定交付：`AGENTS.md`、`docs/development/workflow.md`、`docs/development/environment.md` 的模型/诊断适用说明、`.codex/agents/dev_reviewer.toml` 指令、根 `.codex/config.toml` 中仅 Reviewer 注册描述，以及对应开发规则测试与本 Change 的规划/评审/批准记录。`tests/test_development_environment.py` 已有股票未提交差异，只允许隔离本次模型绑定测试的改动，不能整文件夹带提交。

不改金融业务、Provider、launcher、产品 Agent/Skill/MCP、Risk/PIT、历史运行/评审证据、模型路由文件或任何版本锁；不降低股票 Change 的单股/三股真实研究、Eval、独立评审及人工批准标准。不启动产品 LLM、网络探针或完整 Gate，不安装依赖、不修改用户所选模型。

仅做文档/配置一致性、必要聚焦测试、OpenSpec strict validate 和一次本次差异的独立只读复核。保留敏感信息检查、明确人工完成批准、主规格同步及 scoped commit/push；这些仅在相应收尾阶段触发。规划已获用户明确 apply 授权；该授权不是最终完成批准。
