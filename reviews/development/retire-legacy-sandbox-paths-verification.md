# retire-legacy-sandbox-paths：限定接缝验证记录

后续更新：用户另行授权的一次宿主 normal Smoke 已通过，Task 3.2 的新增证据见 [宿主 Smoke 记录](retire-legacy-sandbox-paths-normal-smoke.md)。下文保留接缝测试结束时的历史状态，不将后续运行冒充当时已完成。

## 结论与适用范围

- 日期：2026-09-09；执行环境：当前 Codex 开发环境，未额外创建项目沙箱。
- 最终确定性接缝：**28/28 PASS**；OpenSpec strict validate：**PASS**；`git diff --check`：**PASS**。
- 本记录为实施者的接缝证据，不是独立评审、完整 Release Gate 或生产晋升结果。
- Task 1.1、1.2、2.1、2.2、3.1 有证据；Task 3.2 等待修复后的一次宿主 normal Smoke，4.1 等待独立差异复核，4.2 等待最终人工批准。
- 全进程源码强制只读仍为 **UNVERIFIED**；不修改生产版本指针。

本轮仅修改退役启动路径、根指令、无消费者的项目权限配置以及相应确定性测试。未修改 Shadowrocket、宿主代理适配、金融业务、Agent/Skill/Schema/Risk 契约、历史运行包或版本锁。旧 preflight 与 probe 的执行测试改为明确拒绝测试，不将已退役功能继续执行成功作为验收要求；未删除正常路径与业务安全的有效断言。

## 版本与证据标识

- Git 基线：`ed45255626df4e6a8614f2c54254c50a6cc64e40`；本轮尚未提交。
- 本地原始证据目录：`/private/tmp/stock-agent-retire-legacy.eeXNmb`。
- 仓库证据包：[retire-legacy-sandbox-paths](retire-legacy-sandbox-paths/)。日志副本与本地原件 SHA-256 相同。
- 源码/配置清单：[source-sha256.txt](retire-legacy-sandbox-paths/source-sha256.txt)，177 个文件。
- 快照标识：`dd57caa2eb1eb162d7004640f745aab554bc8626080d416d9437ccdfcf2b8d3d`，为该清单完整字节的 SHA-256，不是 Git commit 或候选晋升锁。

清单范围是 Git 跟踪的 `AGENTS.md`、`.codex/`、`.agents/`、`product/`、`scripts/`、`tests/`、`evals/fixtures/`、`docs/development/`、`pyproject.toml` 的当前工作树字节。包括本次全部实现、配置、测试及环境文档；不包括验收报告自身、OpenSpec 规划、历史结果、临时产物或用户级配置。这是明确范围的源码快照，不称为包含所有历史产物的整仓库快照。当前这些源码范围没有未跟踪新实现文件。

清单实际生成命令（从仓库根执行）：

```sh
git ls-files -z AGENTS.md .codex .agents product scripts tests evals/fixtures docs/development pyproject.toml | xargs -0 shasum -a 256 | LC_ALL=C sort -k2 | tee /private/tmp/stock-agent-retire-legacy.eeXNmb/source-sha256.txt
```

| 证据 | 完整 SHA-256 |
| --- | --- |
| focused-final.log | `bd3b14527ac859ec9cc0c27943716a242fe9f911d21537082169ec7d4bac50e4` |
| openspec-validate.log | `3ac7750df0e9a3709eee26e6c02b5309c6d01fe5087fc66e3b5f3e53721e03cd` |
| task-1.1.log | `1d8d38bcee6b258b3f17bb4a3f4d295f2ecb13347d74e1ebb630d51cac949f87` |
| task-1.2.log（首次失败） | `fa2bc924f26ef430750a3c1bdbb720d59d9c5dc1a79a5d9b53213a8c23a38d63` |
| task-1.2-corrected.log | `6ea78d39daf3bfc38fa6f9cbaa0a9f3d3bf5ee82c99b17f409a3821fa32ef61e` |
| task-2.log | `705c3331210dd35ac009f8e12af54b7535d09d1c3dd43f0408824806c981f6cf` |

## 修复与规格映射

| Task / 规格 | 实现及实际证明 | 状态 |
| --- | --- | --- |
| 1.1 / 执行模式必须分离且不隐式启动 | 删除 launcher 自动绕过分支；旧 True/非空 preflight 直接拒绝。默认/False 相同且保留 workspace-write；已有/缺失 report 均在读取与目录创建前拒绝。3 项 launcher 测试。 | PASS |
| 1.2 / 同上；开发诊断必须最小化且不自带修复权限 | 薄入口、底层 CLI、直接函数均封闭旧路由；退役函数只保留失败 stub；CLI 不再展示旧命令。测试覆盖两种旧参数拼写、sys.argv、零子进程/网络调用、零输入读取/目录创建及当前自检白名单。 | PASS |
| 1.2 / 执行路径必须明确且可移植（回归保护） | 9 项 EntryPath 与 4 项 EntrySeparation 测试，使用临时 fixture 和 mock，保留正常解析、冻结根转发和失败码。不是 Execution Replay 真实运行。 | PASS |
| 2.1 / 开发指令必须按任务条件读取 | 根指令明确当前环境自检、宿主运行、独立证据复核；同步环境文档退役说明。角色安全与条件读取断言保留。诊断 Skill 已符合原则，未改动。 | PASS |
| 2.2 / 项目权限残留清理不得改变现用权限边界 | 只删除 project-edit 域名表。TOML 全字典对照有效基线，保留 native workspace-write、network_access、模型、4 个 Agent 注册及描述。 | PASS |
| 3.1 / 限定差异验收 | 28 项聚焦测试、strict validate、本文及原始日志/hash。没有运行全量测试或 Gate。 | PASS |
| 3.2 / 资源发现与实际加载必须分别验证；既有启动/加载 Smoke 要求 | 尚未运行修复后真实模型。旧 normal 仅为历史基线，不证明新根指令或新 launcher 的实际加载。 | PENDING |
| 4.1、4.2 / 独立复核与人工批准 | 未启动 Reviewer，未保存最终人工批准。 | PENDING |

`HostProxyTests.test_host_routes_and_preserves_failure` 使用假的本地系统命令和假的 Python 入口，验证宿主脚本按 prepare → launcher → check-run 路由并传播 0/9/7 状态；未检测真实代理、没有真实 Codex 模型调用。

## 实际执行与错误分类

所有测试设置独立 `TMPDIR=/private/tmp/stock-agent-retire-legacy.eeXNmb` 及 `PYTHONDONTWRITEBYTECODE=1`。未调用 `codex sandbox`、产品 LLM、Replay、完整 Regression、Calibration、Ablation 或 Gate。

分阶段结果：

- Task 1.1：3 个 launcher 测试通过。
- Task 1.2 首次：2 个模块导入错误、4 个测试通过；原因是删除旧函数区块时误删未变辅助函数的兼容别名 `network_access_probe`。这是实现编辑错误，不是沙箱环境错误，也不是产品断言失败。已恢复原别名，保留首次失败日志。
- Task 1.2 修复后：相同目标的 18 项测试通过。
- Task 2：6 项根指令、配置及模型路由一致性测试通过。
- 补齐自检两项白名单（check-run/trace-check）与宿主失败传播覆盖后，最终同一快照下选定 28 项接缝全部通过；无环境错误、导入错误或断言失败。

最终完整实际命令如下；日志列出全部展开的测试名称。此前分阶段命令分别选择此列表的 3 个 launcher 方法、RetiredSandboxEntryTests + EntryPathTests + EntrySeparationTests、以及末尾 6 个根指令/配置方法。

```sh
set -o pipefail
TMPDIR=/private/tmp/stock-agent-retire-legacy.eeXNmb PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_nested_codex_launcher.NestedCodexLauncherTests.test_command_is_ephemeral_isolated_and_keeps_user_config tests.test_nested_codex_launcher.NestedCodexLauncherTests.test_command_default_and_explicit_false_preserve_native_sandbox tests.test_nested_codex_launcher.NestedCodexLauncherTests.test_preflight_is_rejected_before_run_or_report_is_read tests.test_development_environment.RetiredSandboxEntryTests tests.test_development_environment.EntryPathTests tests.test_host_proxy_scripts.EntrySeparationTests tests.test_host_proxy_scripts.HostProxyTests.test_host_routes_and_preserves_failure tests.test_governance.GovernanceTests.test_root_instructions_separate_checks_host_execution_and_review tests.test_governance.GovernanceTests.test_project_config_retains_native_settings_without_unused_profile tests.test_governance.GovernanceTests.test_development_control_plane_has_no_runtime_authority tests.test_governance.GovernanceTests.test_development_documents_are_conditional_and_roles_do_not_leak tests.test_governance.GovernanceTests.test_development_agents_are_registered_for_codex_native_delegation tests.test_development_environment.ModelConfigurationTests.test_effective_development_defaults_match_canonical_policy 2>&1 | tee /private/tmp/stock-agent-retire-legacy.eeXNmb/focused-final.log
openspec validate retire-legacy-sandbox-paths --strict 2>&1 | tee /private/tmp/stock-agent-retire-legacy.eeXNmb/openspec-validate.log
git diff --check
```

## 停止位置与下一步

依据 apply Skill 与 Task 3.2 的停止条件，当前停止自动执行。需要用户在宿主 Terminal 手动执行一次：

```sh
bash /Users/caihaoming/Documents/stock_agent/scripts/run-product-smoke.sh
```

沿用现有脚本生成新的外置产物目录及 run_id；不要复用历史失败运行。该命令未在本轮执行。完成后提供终态输出和产物路径，才能核对实际命令、原生权限、加载事件与完整终态，再做一次限定独立差异复核。测试或手动 Smoke 都不等于全进程隔离 PASS 或候选 Promotion PASS。

未归档、未提交、未推送；旧 Change 不重开。
