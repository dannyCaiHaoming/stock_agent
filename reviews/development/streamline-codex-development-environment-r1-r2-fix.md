# R1/R2 限定修复与证据边界

最终补充：用户已完成所需新 normal，独立 Reviewer 确认 R1/R2 关闭并返回 PASS；后续用户明确批准 Change。见[独立补充复核](streamline-codex-development-environment-independent-review-final.md)与[人工批准](streamline-codex-development-environment-approval.md)。下文“缺证/停止状态”为补跑前历史记录，保留原判断，不再表示当前任务未完成。

日期：2026-09-09。Change：`streamline-codex-development-environment`。
依据：独立复核记录及用户“好，继续”的限定修复授权。
本记录不是独立 Reviewer 的 PASS，也不是最终人工批准。

## 修复映射

| 问题 / 规格 / Task | 根因与本次修改 | 证据与状态 |
|---|---|---|
| R1；资源发现与实际加载必须分别验证；4.5/5.2 | 原环境记录只 hash AGENTS，完成检查仅要求 Skill/Agent/MCP。现在 normal Prompt 明确要求逐文件完整读取根与产品 AGENTS，再读 Skill；复用既有成功命令输出校验，将内容 hash、顺序、原始事件 hash、session、run、Prompt 和 invocation 绑定。执行证明保存 `resource_loads.agents_md`；完成检查重新读取底层事件/manifest，不信任自报状态 | 新的正负事件及完成判定测试 PASS；真实新运行尚缺，4.5/5.2 不勾选 |
| R1 合法前置终止 / 冻结资源边界 | PIT 前置安全终止显式记 `NOT_APPLICABLE_PRE_AGENT_SAFE_TERMINATION`，不造读文件事件；冻结 workspace 不借用宿主根指令 | 合成测试 PASS；未改历史 Artifact Replay 规则、密封 Capsule 或旧运行 |
| R2；执行入口必须复用统一启动契约、按条件读取指令；2.1/5.1 | 手册仍直接调用底层 prepare，缺少宿主所需来源绑定；治理测试仍断言旧文案。改为安装仓库 `scripts/council-dev.py prepare-execution-replay`，明确 `host-replay-source.json` 由新 prepare 生成；治理测试检查宿主 --prepared-run 和冻结根选择，不再要求旧入口 | 治理及既有 transport 接缝通过；2.1/5.1 恢复完成，独立复核仍属于 6.2 |

未修改金融业务、安全决策算法、代理配置、Hook 分派、原生权限或冻结 transport。
没有新 launcher、探针或 Change；不存在自动截断、静默降级或旧证据补写。

## 实际验证

唯一执行驱动：`python3 /private/tmp/stock-agent-r1-r2-focused.py`。
证据目录：`/private/tmp/stock-agent-r1-r2-dfvu_2gk`。
独立临时目录：`/private/tmp/stock-agent-r1-r2-dfvu_2gk/tmp`。

驱动实际执行 `python3 -m unittest -v`，选择如下接缝（完整解释器路径、参数、时间及文件 hash 见 execution.json）：

- `tests.test_agents_instruction_proof`：6 项，包括顺序与绑定、缺失/失败/截断/错误路径/重复事件、hash-only 拒绝、版本漂移、Prompt/manifest 漂移、冻结根。
- `tests.test_governance`：8 项，包括修正后的运行手册入口与开发/产品职责边界。
- `tests.test_native_execution_proof.NativeExecutionProofTests` 的 `test_skill_load_requires_exact_successful_runtime_event`、`test_ephemeral_hook_proof_uses_public_events_and_distinct_children`：2 项。
- `tests.test_nested_codex_launcher.NestedCodexLauncherTests` 的 prepare-only、canonical trace agent、合法前置终止、退出码零不能掩盖缺产物：4 项。成功完成检查后删除合成读取事件，仍保留正面 proof 摘要，必须变为 `AGENTS_LOAD_PROOF_MISSING`。
- `tests.test_development_environment.SessionPathTests.test_smoke_modes_quote_paths_and_keep_deferred_proof_run_scoped`：1 项。
- `tests.test_replay_transport`：4 项；只用合成/替身验证既有 transport，不执行真实重放。

结果：**25/25 PASS**，退出码 0，0.148 秒，无环境错误、无断言失败，真实 LLM 调用数 0。
随后实际执行 `openspec validate streamline-codex-development-environment --strict`：退出码 0。
本次相关已跟踪差异的 `git diff --check`：退出码 0。

| 标识 | 完整 SHA-256 |
|---|---|
| execution.json 字节 | `ccdb0dcf4a867d815d10f2d077c401a47dd71470ea61a94cd86851dfacc3259f` |
| 验证前后文件映射 canonical hash | `e5d24cc40c44fdf74dbbb7f15eb76d860a94307dcd12aa8d448665bd495c0f9f` |
| product/runtime/execution_proof.py | `60f4606c710275ef430aa9fcb74cb8667248fbbd04ce4412eb639ebf0f7b9833` |
| product/runtime/nested_codex.py | `630eeae27bb509e862872008f185c5f7248d1450d9a0ac769ae9fa54c7f77dfd` |
| product/runtime/smoke_prompt.py | `d10ec2534eae7a23565f652d57427a5fb18c8eff6b3c2cb336395fcca590327d` |
| tests/test_agents_instruction_proof.py | `9236e35c433dde2335324d614be3c65c9a4dc712a4229d8c7a970a6b1e0cb5c5` |
| reviews/runtime/runtime-replay-eval-runbook.md | `e0fd5411c693fbf6dd340f7395582879383f95a1e650301e4856d372b9fe7a3a` |

execution.json 保留逐文件完整 hash，以及 stdout/stderr 路径和 hash。快照范围为 product/tests/scripts/docs/当前 Change，以及根 AGENTS、项目配置和 runbook；**不是全仓库完整快照**。测试前后该范围一致；测试后仅更新收尾文档和任务状态，不将测试时快照称为此后整个工作区的快照。独立最终源码快照由后续 Reviewer 记录。

## 旧证据复用与唯一补证请求

- 旧 normal `host-normal-e4e41ded-0e3e-4b25-a026-6249d9d76413` 仍证明旧锁下 Council、Risk、Eval 功能成功，不证明本次新增 AGENTS 读取链。
- 旧真实 replay `host-replay-96dba124-e4d4-402d-bf5e-4ec360ea20db` 的比较结果 canonical hash `02ea4793107b9f65609241e8296d0e8646063e8a976e62ad3657951925c65aba`、结果文件字节 hash `4a11e0758081237c8271784baf309f9728667a6d079647ffbba3ce7f91b56ef1` 不变；仅复用冻结根、宿主 transport 和旧配置等价性，保留 Task 5.3。不包装成当前候选晋升证明。
- 历史 Regression 接缝仅用于未变化的路由/缓存/证据消费，不代替新读取链的实际执行。
- **真正缺少：当前实现一次宿主 normal 的真实 AGENTS 读取事件及全链终态。** 旧事件没有该读取内容，合成测试也不能证明 LLM 实际遵守新 Prompt。按当前规格仍须补这一项，不触发 Replay、Regression 或全量 Gate 重跑。

由用户决定并在宿主 macOS Terminal 执行一次（本轮没有执行）：

```bash
bash /Users/caihaoming/Documents/stock_agent/scripts/run-product-smoke.sh
```

入口自动生成新的外置目录和 run_id，保存实际 Prompt、manifest、JSONL、Hook 和执行证明。预期除原完整终态外，`invocation/process-result.json` 的 `completion_checks.agents_md_loaded` 为 true，且执行证明包含与底层文件、事件一致的 `resource_loads.agents_md`；任何失败立即保留证据，不自动重试。

## 停止状态

当前 15/19。剩余 4.5/5.2（真实加载证据）、6.2（对修复差异及完整证据的独立复核）、6.3（最终人工批准）。暂不具备最终人工批准条件。没有自动调用模型、归档、提交或推送。

`CANDIDATE_PROMOTION: NOT_PROMOTABLE`；全进程源码强制只读：`UNVERIFIED`。两者不是本次补证以外的新阻断。
