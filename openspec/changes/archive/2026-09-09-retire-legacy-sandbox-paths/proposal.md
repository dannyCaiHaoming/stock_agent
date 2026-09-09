## Why

当前普通宿主路径默认使用 `workspace-write`，但底层 launcher 仍可通过 `externally_sandboxed` 自动关闭原生沙箱，退役的 probe/preflight 入口也仍可到达该分支。根指令与未使用的权限配置残留进一步增加误用风险，需要以小范围修复收敛到已经跑通的宿主入口，而非再建立权限框架。

## What Changes

- **BREAKING**：删除自动生成 `--dangerously-bypass-approvals-and-sandbox` 的分支；旧外部沙箱模式及携带 `--preflight-report` 的启动请求明确失败，不静默降级。
- **BREAKING**：在薄入口和底层入口一致拒绝旧 `environment-preflight`、`permission-probe`、`nested-codex-probe` 及原有 review 入口；直接调用旧启动函数也不得绕过拒绝。保留历史产物可读性及仍被宿主路径使用的纯路径解析能力。
- 根 `AGENTS.md` 明确三类入口：开发自检不启动产品；真实 Smoke/Execution Replay 走宿主 launcher；独立复核默认读差异、规格与证据。底层模块命令不再作为真实产品运行的默认建议。
- 清理根 `.codex/config.toml` 中未使用的 `permissions.project-edit.network.domains`；保留现用 `sandbox_mode = "workspace-write"`、对应原生配置、模型和开发 Agent 注册，不迁移新权限框架。
- 补与上述差异直接相关的确定性接缝测试，验证拒绝发生在子进程及运行副作用之前、正常入口参数未扩大权限。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `codex-development-environment`：封闭旧沙箱启动路径、保持原生权限并清理无消费者的项目权限配置；将历史 preflight 的保留范围限定为证据读取。
- `three-plane-governance`：在根指令中明确开发自检、宿主产品执行、独立证据复核的入口边界。

## Impact

- 预期实现文件：`product/runtime/nested_codex.py`、`product/runtime/cli.py`、`product/runtime/environment_preflight.py`、`scripts/council-dev.py`、根 `AGENTS.md`、根 `.codex/config.toml`。
- 预期测试文件：`tests/test_nested_codex_launcher.py`、`tests/test_development_environment.py`、`tests/test_host_proxy_scripts.py`、`tests/test_governance.py` 中受影响的测试；按实际断言归属最小修改，不要求整个文件重写。
- 若环境文档或诊断 Skill 仍推荐这些退役入口，仅同步对应的入口说明，不增加检查能力。
- 不修改金融业务、Shadowrocket、宿主代理适配、用户配置、生产版本指针、历史 Replay 锁或归档内容；不增加探针、Agent、沙箱层或依赖。不重跑全套 Regression/Gate，不补做全进程隔离；该保证保持 `UNVERIFIED`。
- 验收边界：实施阶段先仅运行确定性接缝测试。现有 `three-plane-governance` 与开发流程仍要求启动/加载变更提供受影响的真实 Smoke，因此完成条件保留一次修复后宿主 normal Smoke，由用户执行或另行授权，不在当前 Codex 中自动启动。它不是全量 Gate；旧运行只作历史基线。若要求最终验收也完全零 LLM，须先明确批准有限验收调整，不能静默豁免原规格。
- 本次只生成规划，得到显式 apply 授权后再修改实现。
