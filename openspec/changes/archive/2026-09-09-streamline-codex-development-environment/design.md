## Context

动机见 Proposal。以下为 2026-09-09 的只读源码/配置盘点，未在规划阶段运行测试或产品 LLM；“已有”不等于本轮重新验收通过。

| 分类 | 实际位置与发现 | 本次处理 |
|---|---|---|
| 已完成，复用 | `product/runtime/nested_codex.py` 已固定 product cwd、写 prompt 文件、保存 invocation/environment/events/stderr/process-result，复用执行证明与终态检查 | 保留单一启动器与输出，补路径和权限接缝 |
| 已完成，复用 | 同文件已按 run 建立 `.codex-runtime/sqlite`、`logs`、`tmp` 并设置 TMPDIR；`codex_hook_recorder.py` 已限制分派和记录 Specialist 事件 | 不再设计状态目录或 Hook 框架；隔离目录存在不代表没有历史数据导入 |
| 已完成，复用 | `execution_replay.py`、`replay_capsule.py` 已物化冻结内容、密封并重算等价性；`evals/regression/runner.py` 已验证 run index、缓存和底层执行链 | 仅统一新 LLM 执行的入口；不改 Replay/Eval 判定算法 |
| 需整理 | 根 AGENTS.md 已很短，但缺少按需入口；产品规则已禁止修改生产文件；`dev_reviewer` 是全局 read-only，`dev_eval` 是 workspace-write 却靠指令禁止产品修改 | 保留安全含义，区分开发、复核和产品的适用条件与产物写权限 |
| 需整理 | `reviews/runtime/runtime-replay-eval-runbook.md` 仍示范管道执行；`smoke_prompt.py`、`runtime_eval.py` 含个人 sessions 绝对路径 | 更新入口示例和路径来源，不重写历史报告/证据 |
| 需整理 | `.codex/config.toml` 未显式设置开发模型，`product/model-routing.json` 已有 Sol/Terra/Astra 策略 | 复用权威模型策略，落实本机支持的调用配置；不创建第二份策略 |
| 确实缺失 | 检索 CLI 与 runtime 未找到仓库级 doctor/preflight 命令；已有 `_writable_probe` 可复用，本机有 `codex doctor --json` | 增加最小开发 preflight 薄层，不重复实现认证诊断 |
| 确实缺失 | 当前 `workspace-write + product cwd + --add-dir run_dir` 与事后 source hash 不能证明源码禁止写；未见覆盖外层 launcher/MCP/Hook 的受限执行证明 | 定向配置实际权限并做零 LLM 探针，不把 Prompt 当沙箱 |

本机 `codex-cli 0.153.4` 的 `--help` 确认 `exec --ephemeral/--json/-C/--add-dir/--strict-config`、顶层 `--ask-for-approval`、`sandbox --permission-profile/--sandbox-state-json`、`doctor --json` 存在。帮助输出同时出现 PATH aliases 写入警告；本轮未运行 doctor 正式诊断，也未验证权限 profile 的具体配置键或模型账户权限。

官方参考：[配置说明](https://learn.chatgpt.com/docs/config-file/config-reference)、[安全说明](https://learn.chatgpt.com/docs/security)。本机帮助与有效配置优先决定落地语法；不照抄官网或历史版本的命令层级。现有 launcher 使用 `--dangerously-bypass-hook-trust`，本 Change 不把它视为普遍安全默认值，更不自动扩大该豁免。

## Goals / Non-Goals

**Goals:** 单一执行路径；确定的根目录来源；模式明确分离及保证边界声明；按需中文文档；最小诊断和按差异验收。

**Non-Goals:** 不新增编排服务、容器平台、依赖管理系统或 runtime Agent；不更改投资逻辑、终态、19 类 invariant、完整 Replay/Eval/Promotion 算法；不清理旧私密数据库、不重开旧 Change；不自动迁移全局配置、安装插件或切换生产版本。

## Decisions

### D1. 指令短入口，最多三份专项文档

根 `AGENTS.md` 保留原则、命令入口、角色边界、完成标准、安全以及条件链接，不以字数指标删安全规则。

- `docs/development/workflow.md`：OpenSpec 实施、差异驱动验收、独立评审、人工批准、归档/提交规则；仅变更/验收/归档时读取。
- `docs/development/environment.md`：路径、权限、CLI 兼容性、模型选择、最小授权请求；配置/启动/环境问题时读取。模型 ID 引用现有 `product/model-routing.json`，不重复维护策略。
- 复用 `reviews/runtime/runtime-replay-eval-runbook.md`：操作入口与产物定位；实际执行对应运行/重放时读取相关章节，不另写一套全量运行手册。

根规则明确开发流程条款只适用于开发任务，即使产品会话读取到了祖先 AGENTS 也不触发归档/Git；`product/AGENTS.md` 保持产品权威边界。不假设 cwd 可以屏蔽祖先指令。

替代方案：把所有经验放进 AGENTS 会增加冲突和上下文消耗；拆成大量文档会增加查找成本，均不采用。

### D2. 薄入口复用，不改执行职责

保留 `product.runtime.cli` 命令和 `nested-codex-smoke`，新建必要的开发薄入口 `scripts/council-dev.py`，仅提供路径无关的命令转发、preflight 和受限执行接入，不包含 Agent 调度、Prompt 构造或终态判断副本。脚本位置用自身路径定位安装仓库；显式 `--repo` 指向目标仓库，模块加载不依赖偶然 cwd。既有 CLI 保持兼容。

Smoke：prepare 后调用现有 launcher。Execution Replay：由现有 prepare 返回冻结 workspace，将其作为运行根调用同一 launcher，再使用原 finalizer。Regression：保留现有 run-index/缓存消费语义；缺失运行需要显式授权和选定案例才启动同一 launcher，不让验证命令默默发起 LLM。Artifact Replay/确定性 Eval/Regression 直接复用原确定性实现，不启动模型。

不以新命令名称取代已有底层职责，不在 `evals/regression/runner.py` 增加第二个 subprocess Codex 构造器。

### D3. 四个路径与优先级

| 字段 | 权威来源 | 约束 |
|---|---|---|
| repo_root | 普通运行显式 `--repo`，薄入口缺省时从自身位置确定；重放由冻结 workspace manifest 确定 | 显式值与重放 manifest 冲突即失败，不退回 cwd |
| product_root | 所选 repo_root 下的 product，经解析和包标识验证 | 作为 Codex/MCP 的实际工作目录；不取任意缓存副本 |
| run_dir | 显式参数，规范化后与 run manifest 的 output_dir/run_id 核对 | 拒绝重复 invocation、身份冲突和越界链接；必须在授权产物根内，不能把源码根当产物目录 |
| state_dir | run_dir 下 `.codex-runtime` | sqlite/logs/tmp 沿用既有布局，不与另一 run 共用 |

相对用户参数只在入口按原始调用 cwd 解析一次，后续传绝对规范路径并记录来源；不是把所有 CLI 参数默认当 repo-relative。源码/模板禁止个人绝对路径，机器生成的本地 manifest 必须保留实际绝对路径用于审计。

旧 sessions 模式确有需要时使用显式 sessions-root 或从现有 CODEX_HOME 推导；新 launcher 优先使用现有 run-scoped 事件证明。保留读取认证所需的既有 CODEX_HOME，不复制 auth.json，不新增全局 sessions 扫描。合法 Capsule 物化继续走原内容寻址校验，不手工补拷历史缺文件。

### D4. 已批准的模式分离与隔离保证边界

批准依据：reviews/development/streamline-codex-development-environment-scope-approval.md。

- 开发自检在当前 Codex 环境检查代码、执行明确授权的确定性测试和读取产物；不得隐式启动 Council、codex sandbox 或模型探针。
- 产品 Smoke 与 Execution Replay 仅通过宿主 Terminal 的现有 launcher 和代理适配启动，保留 Codex 原生权限、Hook、run-scoped 状态和完成判定，不额外套项目沙箱。
- 独立 Reviewer 默认读取差异、规格和历史运行证据；独立性来自未参与实现的上下文与证据判断，而非额外沙箱。需要补跑只报告缺口，由获授权的宿主入口执行。
- 全进程源码强制只读保留为 UNVERIFIED，明确排除在本 Change 完成保证之外。历史权限探针仅证明其当时配置，不证明当前产品运行的全进程隔离。
- 保留历史隔离实现及证据，不关闭原生保护；旧 --review 与开发薄入口的 review-run/review-probe/nested-codex-probe 明确拒绝，不静默降级。
- 残余风险：launcher、Hook、MCP 等进程未证明全部禁止源码写入；错误调用可能修改既有权限允许的文件；前后 hash 只能事后检测部分改动，不能证明运行期间无写入。用户已接受该边界，但不代表生产晋升批准。
- 不修改 Shadowrocket、域名 allowlist 或系统配置；不重新排查网络，不新建网络基础设施。

### D5. preflight 静态检查与运行时加载证明分层

preflight 保留为历史专项诊断，不作为开发自检或 Reviewer 默认前置条件。日常检查读取路径、配置和已有产物，不启动 doctor、网络探针或项目沙箱。复用本机 doctor 的脱敏结果（实施前确认其状态访问范围），不复制完整用户配置。若 doctor 本身需要额外状态写权限，返回最小权限缺口，不自行修复。

新开发 Skill `.agents/skills/codex-development-diagnostics/SKILL.md` 仅串联 preflight、指定运行包读取和首处分歧定位，不含自动重跑/修复/归档/推送指令，不装进 product 包。其能力链为：环境或失败 run 输入 → 确定性检查器及指定事件 → 诊断 Skill 解释 → 结构化诊断/中文说明 → 零 LLM 错误分类测试及独立复核。

输出放在显式外置 `output_dir`：`preflight.json`、`preflight.md`，含 schema_version、mode、路径来源、CLI/version、请求/实际模型（未知为 null）、effective permission 依据、checks、failure_code、minimal_authorization、llm_calls。资源分别标记 DISCOVERED、CONFIG_VALIDATED、LOAD_VERIFIED；静态阶段不得填写 LOAD_VERIFIED。缺失加载来源时标 UNKNOWN 并阻断依赖该证明的成功结论。

实际 Smoke 继续使用原 invocation/events/execution-proof，补充缺少的 AGENTS 读取链和配置来源绑定，而不是复制完整 Prompt/消息到诊断报告。现有 Schema/终态校验器保持权威；合法前置终止标阶段不适用，不伪造执行。完成条件继续检查 decision/report/trace/eval 及 Risk，绝不退回 shell exit code。

### D6. 模型偏好落实到配置，不靠指令切换

保留现有策略文件。开发调用可在本机支持的项目配置/Agent 配置或显式参数设置 Sol；重复 Runtime 使用锁定 Terra。Astra 仍遵循现有重大争议和人工批准约束。Desktop 无法由仓库配置改变当前模型时明确提示用户选择，不声称已自动切换。只读可用性信息不足时记待确认，借必需 Smoke 确認实际模型，不另启动三种模型探测。

### D7. 限定验收与交付

先创建一份证据映射：要求 → 本次 diff → 受影响依赖 → 可复用证据完整标识/理由 → 需新增证明。旧 Change 独立复核/批准仅作为基线来源，不把它提升成新候选晋升依据。

| 受影响面 | 本 Change 的验收 | 不触发 |
|---|---|---|
| AGENTS/文档/模型配置 | 规则无冲突、条件链接、配置解析、请求与实际模型来源检查 | 模型对比实验 |
| 路径与路由 | 零 LLM 测试覆盖 root/product/外部 cwd、空格、显式根、冻结根、路径冲突及 run 重复；三类新 LLM 入口只调用既有 launcher | 12-case 全量 LLM 重跑 |
| 权限与诊断 | 仅测试入口分流、禁止隐式启动及失败传播；全进程隔离 UNVERIFIED | 新沙箱探针、网络排障 |
| 真实启动/加载 | 零 LLM 检查通过后，当前锁一次 normal Smoke；本计划包含 Replay 入口统一，因此再做一次同一来源 Capsule 的 Execution Replay Smoke，均使用 Terra 和新 run_id | conflict 三连、Calibration、Ablation、Promotion 全套 |
| Regression 接缝 | 受影响的 runner 路由/证据消费/缓存测试，读取新 Smoke 证明完成新执行路径绑定；其余案例按依赖复用 | 宣称仅凭旧证据获得新候选 Promotion PASS |
| 独立复核 | 一名未参与实施的 Reviewer 读取本次 diff、有效权限、原始事件及完整 hash，确认上述覆盖 | 默认为独立 Reviewer 重跑全部执行链 |

真实运行预算为上述两次 Council，不另增加稳定性重复。若其中一次失败，先保留首处分歧并停止真实运行；只有明确缺口、旧证据为何不可复用和所需次数获批准后补跑。正常运行保留现有必需 Eval；不将“非全套验收”误解为省略每次运行的安全校验。

现有 `three-plane-governance` 的生产晋升要求不变；旧 Council 加固的稳定性要求不是本次自动重验触发器。本次变更加载行为，故满足既有真实执行证据要求，不能纯文档宣称通过。若实际差异触及投资/安全算法或某条现有规格确实要求更大范围，先透明提出调整再停止，不暗中豁免。

预期交付文件清单（不是本轮修改授权）：

- 整理：`AGENTS.md`、`product/AGENTS.md`、`.codex/config.toml`、受影响的 `.codex/agents/dev_*.toml`、现有运行手册。
- 新增：上述两份 `docs/development/` 文档、一个诊断 Skill、`scripts/council-dev.py`、最小 `product/runtime/environment_preflight.py`。
- 定向修改：`product/runtime/nested_codex.py`、`cli.py`、`smoke_prompt.py`、`runtime_eval.py`；`execution_proof.py` 和 `product/.mcp.json`/`product/.codex/config.toml` 仅在证明路径/加载接缝确需调整时涉及，并明确补测映射。不修改研究 Prompt 内容或 Hook 分派算法。
- 验证：复用并补 `tests/test_nested_codex_launcher.py`、`test_runtime_assurance_cli.py`、`test_governance.py`、`test_product_config.py`；新增 `tests/test_development_environment.py` 覆盖零 LLM 路径/权限/preflight。其他既有测试仅在映射表证明受影响时运行。
- 报告：`reviews/development/streamline-codex-development-environment-acceptance.md` 与独立复核记录；命令/原始产物放指定外置证据目录，报告保存可共享索引及完整 hash，不提交 SQLite、凭据或用户会话。

## Risks / Trade-offs

### 已授权修复：冻结目录非 Git 启动

用户针对 host-replay-80479d80-fdfe-4bdf-8a1d-70980a414996 的实际启动拒绝批准最小修复。
宿主 prepare 薄入口在新 run 保存 host-replay-source.json（不进入历史 manifest/版本锁）；
只在 EXECUTION_REPLAY 分支将既有 launcher 的 codex-binary 指向宿主 scripts/replay-codex-transport.py。
该适配器重新校验 source/new manifest、run 身份、来源 Capsule、密封目录内容与 cwd，
仅添加本机 help 确认支持的 --skip-git-repo-check，保留 workspace-write、审批和 Hook 参数。
不复制或修改冻结 launcher，不创建 .git，不放宽沙箱。实际命令与适配器 hash 保存到 invocation/host-transport.json。
缺少来源绑定时 fail-closed；必须从原来源重新 prepare 新 run，不向历史失败包补写字段。
此适配不代表 execution replay PASS，仍需既有 finalizer 重新验证配置等价性。

- [旧 Change 尚未安全发布] → 规划可评审，实施保持 BLOCKED；另行获授权收尾，不将数据库混入提交。
- [CLI 键或沙箱受上层约束] → 使用本机帮助和实际解析/零 LLM 探针；不支持即报告最小需求，不建立备用平台。
- [AGENTS 或 Prompt 路径变化影响版本锁] → 不补写旧快照；记录新锁，重跑上述受影响 Smoke，其他证据明确限定适用范围。
- [run-scoped 数据库仍可能含无关私密历史] → 状态目录与可共享证明分开，禁止整体打包；记录问题，不在本 Change 清理或改写旧数据。
- [历史包不能提供新加载证明] → 允许按原契约验证历史自洽，不认作本次启动验证；缺关键锁时保持原 fail-closed。

## Migration Plan

### 本次授权补充：宿主代理适配

新增 `scripts/detect-host-proxy.sh` 与 `scripts/run-product-smoke.sh` 两个薄脚本，
复用既有 launcher，不改产品算法。生效系统代理从只读 `scutil` 查询取得，
`networksetup` 与监听查询留作原始证据；禁用端口不采用，不凭进程名猜端口。
仅 SOCKS 时先使用已有 doctor 的 transport 检查；失败停止，不转换端口或协议。
已连接 VPN/隧道路由且无显式代理时不生成代理变量，UNKNOWN 不启动模型。

用户授权宿主 Terminal 直接启动 Product Smoke，继承宿主代理/TUN，
不要求该启动方式在外层 Codex 沙箱内重复成功，不再增加网络基础设施。
保留 launcher 既有原生权限设置；此模式不宣称具备 D4 的外层全进程只读边界，
不能代替独立复核权限证明或自动完成有限集成验收任务。
本次交付以零 LLM 脚本测试与实际系统状态检测验证；真实 Smoke 由用户后续手动启动。
系统代理地址仅进入外置本地证据，不固化进源码、业务配置或 Git。

收尾接缝已由人工批准调整：旧 --review 明确拒绝，不调用 review-run。开发自检与宿主产品执行分流；全进程隔离不纳入当前功能验收保证。

当前迁移：同步批准 → 入口分流 → 限定确定性测试 → 复用已有 normal → 列出未完成 Replay/接缝与独立复核 → 后续人工收尾。本轮不得自动执行剩余真实运行或 Gate。

旧 CLI 子命令保持可用，旧文档入口给出统一替代方式。只更新活跃文档，不修改归档 Change 或历史产物。回退只撤销本 Change 的明确修改，不回退旧已批准能力、不解除权限保护，不改生产默认版本指针。
