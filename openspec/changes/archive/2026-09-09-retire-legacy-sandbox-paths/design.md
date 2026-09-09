## Context

动机见 `proposal.md`。本地检查基线为 `ed45255626df4e6a8614f2c54254c50a6cc64e40`，新 Change 创建前工作区干净。以下是源码事实，不是新运行结果：

| 位置 | 已确认问题 / 保留行为 |
| --- | --- |
| `product/runtime/nested_codex.py` | 命令构造器在 `externally_sandboxed=True` 时添加沙箱绕过参数；connectivity probe 固定传 True；launcher 以 preflight binding 是否存在选择该模式。默认 False 仍使用 `workspace-write`。 |
| `product/runtime/cli.py` | `environment-preflight`、`permission-probe`、`nested-codex-probe` 和 `nested-codex-smoke --preflight-report` 仍可执行。 |
| `scripts/council-dev.py` | 常规入口已拒绝三个 review/probe 名称，但另有旧 `restricted_main` 启动实现；其他底层旧命令仍可转发。 |
| `tests/test_nested_codex_launcher.py` | 旧 external-profile 测试要求生成危险绕过参数，需改成拒绝测试。 |
| 根指令与配置 | 根指令未完整说明三类入口；配置中的原生 workspace-write 仍有效，`project-edit` 域名表没有现用入口消费者。 |

官方参数说明区分关闭审批/沙箱的 `--dangerously-bypass-approvals-and-sandbox` 与 Hook 信任参数；本次只处理前者，不按名称相似误删 Hook 契约。[Codex CLI 参数说明](https://learn.chatgpt.com/docs/developer-commands?surface=cli)

## Goals / Non-Goals

**Goals:**

- 当前源码的受支持入口无法再经旧模式自动关闭原生沙箱。
- 拒绝旧入口发生在读取 preflight 内容、创建运行状态目录、探测网络或启动子进程之前。
- 正常宿主入口、代理适配、run-scoped 状态、Hook 和终态校验保持既有行为。

**Non-Goals:**

- 不建立新权限模型、诊断/探针框架或隔离层；不修改 Shadowrocket、代理检测、域名授权策略或金融业务。
- 不修补历史密封 Capsule、改写旧版本锁或生产指针；历史文件里的旧文本不是当前可执行入口。
- 不证明全进程源码只读，继续 `UNVERIFIED`；不做候选晋升或全套 Gate。

## Decisions

### 1. 删除绕过行为，旧调用显式失败

命令构造器只生成现用 `--sandbox workspace-write` 和 `--ask-for-approval never`。允许短期保留 `externally_sandboxed` 参数用于兼容错误诊断，但 True 必须立即抛出带稳定错误码的异常，不能转成普通启动。`launch_nested_codex(preflight_report=...)` 在读取 run manifest/preflight 或创建目录之前拒绝，文件真伪、是否存在均不能影响拒绝结果。

不采用“只删 CLI 参数”方案：这不能关闭 Python 直接调用路径。也不采用“忽略 True/旧参数”方案：调用者会误以为旧隔离契约仍生效。

`--dangerously-bypass-hook-trust` 是现有独立契约，本次保持；不添加 `--yolo`、`danger-full-access` 或其他等效自动降级。

### 2. 旧入口统一退役，不影响现用纯工具

| 旧请求 | 拒绝层与结果 |
| --- | --- |
| `review-run`、`review-probe`、`nested-codex-probe` | 薄入口保持显式拒绝；底层对应请求不能重新启动旧流程。 |
| `environment-preflight`、`permission-probe` | 薄入口转发前及底层 CLI 分发前拒绝，即使参数缺失也不能进入原启动逻辑。 |
| `nested-codex-smoke --preflight-report` | 包括分离值和 `--preflight-report=...`，均明确拒绝，不能先读取该文件。 |
| `externally_sandboxed=True` / `preflight_report` 非空的 Python 调用 | 构造器 / launcher 自身拒绝，不能仅依靠外层参数过滤。 |
| `restricted_main`、旧 probe/preflight 执行函数 | 删除可执行旧实现或保留明确拒绝的兼容 stub；保留 stub 时使用同一退役错误语义。 |

CLI 使用既有 `BLOCKED`/`failure_code` 风格和非零退出码；旧项目入口复用 `PROJECT_SANDBOX_ENTRY_RETIRED`，旧启动模式使用明确的 `LEGACY_SANDBOX_MODE_RETIRED`。直接函数调用可抛出相同错误码的异常，不伪造执行报告。

`environment_preflight.py` 的 `resolve_run_paths` 等现用纯函数仍被 launcher 消费，不能整文件误删。只处理旧执行链及其独占依赖；不借此整理无关诊断实现。历史 preflight JSON 可供证据复核，但不再授权当前启动。

### 3. 根入口说明与配置最小清理

根 `AGENTS.md` 指向：

- 当前环境内的授权确定性测试、自检 `scripts/council-dev.py self-check`；不启动产品或沙箱。
- 宿主 Terminal 的 `scripts/run-product-smoke.sh`；Execution Replay 使用同一脚本的 `--prepared-run`，准备/finalize 仍按既有运行手册。
- 独立复核默认读取差异、规格、已有证据；缺证据只提出具体宿主补跑需求。

低层 `python3 -m product.runtime.cli` 仍是内部实现和确定性工具入口，不删除它，但不再把它直接推荐为真实模型运行入口。业务安全、角色边界及开发发布流程不改。

根 `.codex/config.toml` 仅删除 `[permissions.project-edit.network.domains]` 及其未使用的域名项。保留 `model`、`agents`、`sandbox_mode="workspace-write"` 和 `[sandbox_workspace_write]` 当前值。删除有效原生配置会改变权限边界，不属于“清理残留”。不迁移命名权限框架，不改用户配置或 network proxy。

环境文档如仍描述旧入口可用，只更正对应行。现有诊断 Skill 已禁止自动 preflight/模型/沙箱；不因本 Change 重写或增加该 Skill 的能力。

### 4. 限定验证与证据范围

首先运行受影响测试方法，不运行全套产品测试。测试以 mock 子进程/文件读取/网络调用和临时目录证明：

1. 默认命令保留原生参数，省略旧模式与显式 False 等价；True 确定性拒绝。
2. 全部旧 CLI 路由、旧参数两种拼写、直接 API 都拒绝；外部子进程调用数为零、无运行目录、无 preflight 文件读取。不能只匹配一段错误文本。
3. 自检只允许原白名单，正常宿主转发仍可构造命令，现有失败码如实传播；测试不启动真实 Codex。
4. TOML 解析验证原生设置/模型/Agent 注册不变且废弃表已删除；根指令包含三类入口，无直接启动误导。

接缝报告记录实际命令、选中测试、结果、源码快照和涉及文件完整 hash。旧 normal 仅是旧宿主路径的功能基线，不证明新 AGENTS hash 实际加载。

**沿用既有完成门槛，而不自行扩展 Gate：** 由于改动 launcher 和根加载内容，主规格要求一次受影响的真实 Smoke。确定性测试通过后停下，提供现有宿主 normal 命令，由用户执行或另行授权；只核对该次原始 invocation、命令参数、加载事件、终态和既有完成产物。不重跑 Replay、Regression、Calibration、Ablation 或 Promotion。若用户要求完全零 LLM 验收，先申请明确范围调整，批准前保留该任务未完成，不能以本提案视为已获豁免。

最后独立 Reviewer 只读本次差异和上述证据；不自行补跑。归档和发布须另有最终人工批准。

## Risks / Trade-offs

- [调用旧入口的自动化会失败] → 返回稳定退役错误并指向现用宿主方式，不做不透明回退。
- [错误删除有效原生配置] → 对配置语义做前后对照；本次只移除无消费者的 project-edit 表。
- [仍有历史冻结代码含旧实现] → 不改历史包或版本锁，不将历史包等同于当前修复后的入口保证；当前入口不得据历史 preflight 自动授权绕过。
- [只用参数断言不足以证明模型加载] → 确定性测试只证明接缝安全；按既有规格把修复后的一次宿主 Smoke 与历史证据明确区分。
- [workspace-write 不等于全进程源码只读] → 原生权限继续保留，但全进程隔离为 `UNVERIFIED`；本次修复不扩大保证。

## Migration Plan

先封闭底层分支及旧分发，再同步根入口/配置，替换旧的“应生成绕过参数”断言并跑聚焦测试。已退役脚本应改由现用宿主入口执行，不能把旧 preflight 作为授权材料。

若正常路径受到影响，停止发布并报告具体差异；不以恢复危险分支、关闭沙箱、修改代理或重写历史锁作为自动回退。当前阶段仅生成规划，不执行迁移。
