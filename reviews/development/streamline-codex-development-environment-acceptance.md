# 开发环境精简：实施与限定验收记录

**最终状态：19/19，Change 已获人工批准。** 新 normal `host-normal-9fb6a10a-66f7-4038-bb1b-b434c455ce73` 补齐实际 AGENTS 加载链；[独立补充复核](streamline-codex-development-environment-independent-review-final.md)为 PASS，R1/R2 均关闭；用户明确批准，见[批准记录](streamline-codex-development-environment-approval.md)。下列旧状态按时间保留，不代表仍有阻断。候选 NOT_PROMOTABLE、全进程隔离 UNVERIFIED；尚未归档或发布。

**本轮最新状态：R1/R2 限定修复完成，25/25 聚焦测试与 strict 校验通过，当前 15/19。** 详见 [修复证据](streamline-codex-development-environment-r1-r2-fix.md)。2.1/5.1 恢复完成；4.5/5.2 仍等待新加载逻辑的真实宿主 normal，6.2/6.3 仍未关闭。下述独立 FAIL 是修复前结论，尚未被新的独立 PASS 替代。没有自动调用模型或改写历史锁。

**最新结论：独立复核 FAIL，当前 13/19。** 见 independent-review.md。R1 为 AGENTS.md 实际加载链及完成检查缺口；R2 为手册准备入口与治理测试过时。2.1/4.5/5.1/5.2 已重新打开，历史功能成功和测试事实仍保留；5.3/5.4 的有效证据不撤销。6.2 已执行但未通过，6.3 不申请。以下17/19等计数为独立复核之前的历史状态，不代表当前。全进程隔离 UNVERIFIED，不是本次失败项。

当前收尾进度（第 9 节）：4.5、5.4 的版本绑定证据已用限定确定性测试补齐；17/19，等待独立差异复核与最终人工批准。全进程隔离 UNVERIFIED 不变。

最新状态（第 8 节）：Execution Replay 已通过并关闭 5.3，当前 15/19；4.5、5.4、6.2、6.3 仍未关闭。以下旧章节的计数仅属于当时记录。

Change：`streamline-codex-development-environment`。日期：2026-09-09。
当前状态：限定证据归集后关闭 Task 5.2，任务记录为 14/19。用户已批准开发/产品/独立复核分离；全进程源码强制只读为 UNVERIFIED，排除在本 Change 完成保证之外。最新证据映射与具体缺口见第 6 节。旧章节保留历史记录，尤其第 4.2 的 --review 建议已被取代。Change 未完成，不具备最终人工批准条件，不归档或发布。

## 1. 已满足的前置条件（Task 1.1）

- `git rev-parse HEAD origin/main`：均为 `b4d15cc138f14b4db086a93ea32a2ca483d54fc2`，此前 push 明确成功。
- 全部已跟踪文件基线 Git tree：`4576fdab68865d04e709ae452fd7f78670d5402d`，来自 `git rev-parse HEAD^{tree}`；此 tree 不包含新 Change 规划及被忽略的私密状态。
- 旧归档：`openspec/changes/archive/2026-09-09-runtime-replay-and-eval-hardening/`。
- 旧人工批准：`reviews/runtime/runtime-replay-and-eval-hardening-approval.md`，字节 SHA-256 `cb8a22b6da5564abcbc35c058205dfce0f41f8aab1171588bab9b37f7111b587`。
- 旧安全发布记录：`reviews/runtime/runtime-replay-and-eval-hardening-publication.md`，字节 SHA-256 `09e80445f69babbb13779712aa63a3117503a6b268a75c9c66622326e29f1521`。
- 私密数据库留在本地且被忽略，已完成授权范围内的安全发布，不要求删除数据库或旧候选 Promotion PASS。

## 2. 基线与证据复用映射（Task 1.2）

产品起始受保护源码快照：`24fe59edbc75db2c5d667df7e58b069f63e136aad59a0ff22782cb27e0fa74fb`。
旧 candidate lock：`618f746c35c7df17a37a64d4338bbbfc73e3a9875fe6ad9ea56f471b166ac198`。
独立复核文件：`reviews/runtime/runtime-replay-and-eval-hardening-independent-evidence-review.md`，字节 SHA-256 `0a94f3d921d4f8657ab4013fac4070123cff369bcb32119afa782646eb4f84ad`。
旧最终证据根：`evals/results/runtime-replay-and-eval-hardening-nested-diagnosis-20260909/final-lock/`。
旧 suite ID：`rrh-final-lock-regression-suite-20260909`，suite hash `179b70a83526db786357354a5bdcddcae55c06cabe05e513e81b8db3e55c7b39`。

| 本 Change 规格 / Tasks | 预期修改与受影响依赖 | 复用依据及限制 | 必须新增的证明 |
|---|---|---|---|
| 按条件读取指令 / 2.1 | 根/产品 AGENTS、两份专项文档、活跃 runbook | 旧三平面安全要求保持；旧运行不证明改后的指令已加载 | 治理测试、链接检查、原条款保留检查；新 Smoke 加载证据 |
| 版本与模型 / 2.2 | 支持的配置或显式参数、模型选择来源 | 复用 model-routing.json 的偏好，不把旧模型证据当新调用证明 | 当前 CLI 帮助/有效配置、零 LLM 选择测试及必需 Smoke 的实际模型 |
| 统一入口与路径 / 3.1–3.3 | 现有 launcher/CLI/Prompt 路径与薄入口 | 复用 launcher、Hook、执行证明算法；旧 cwd/路径不能证明新入口 | 三类路由、cwd/空格/冲突/逃逸测试；normal 与 Execution Replay 各一次 |
| 权限与诊断 / 4.1–4.4 | 有效权限、preflight、开发 Skill | 旧 source hash 未变化只证明历史观察，不证明权限边界 | 零 LLM 真实沙箱探针、后代继承、失败分类与脱敏检查 |
| 实际加载 / 4.5、5.2–5.3 | 运行时加载血缘和资源绑定 | 旧证据缺新接缝；不重写历史包 | 缺证明负向测试；当前锁 AGENTS/Skill/Agent/MCP/Hook/Risk/终态原始事件 |
| Regression / 5.4 | 入口和证据消费/缓存接缝 | typed invariant、PIT、Evidence、Risk 算法未修改时复用旧 suite 的对应能力证据 | 受影响零 LLM 子集与新 Smoke 引用，不冒充当前锁 12-case 全量 |
| 限定验收与晋升区分 / 6.1–6.3 | 当前报告、独立差异复核、人工批准 | 历史 Calibration/Ablation/Promotion 仅证明旧能力；不修改基线或生产指针 | 本次差异/完整 hash 复核与用户批准，均尚未完成 |

主规格核对：`three-plane-governance` 的三平面和人工晋升要求不变；`portfolio-council-orchestration` 的终态稳定性场景明确对应旧 `harden-council-terminal-contracts`，不在本次自动重开。新 Change 修改启动/加载，因此保留真实 normal 与 Execution Replay 两次运行，并执行各自原有安全/Eval 校验。后续若实际差异触及研究或安全算法，应先报告范围变化，不能沿用本表跳过必需证明。

旧私密状态不在 Git 副本中，涉及历史整目录 hash 时仅在原授权环境核验；不宣称 Git clone 是完整历史晋升包。

## 3. 本次验证

按实现进展追加真实命令和结果；未执行的项目保持未完成。任何环境失败与产品断言失败分开记录，不自动全量审计或升级权限。

### 3.1 指令与文档切片

已整理根/产品 AGENTS，新增 workflow/environment 两份专项文档，并将 runbook 的旧管道替换为既有 nested-codex-smoke。产品投资规则原文保留，仅补中文默认和开发/产品流程适用边界。差异已读取，未修改研究、Evidence、Risk、Hook 或 launcher 算法。

实际命令：创建独立临时目录后执行 `TMPDIR="$task_tmpdir" PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_governance -v`；本次 TMPDIR 为 `/tmp/stock-agent-dev-docs.qH0naS`。结果：退出码 0，8 tests，全部 OK；这是开发环境中的聚焦治理检查，不是只读运行环境的全量测试证明。`git diff --check` 退出码 0。

验证文件字节 SHA-256：

| 文件 | SHA-256 |
|---|---|
| AGENTS.md | `f06f8c98d6d63c47cb139df61c8cd1e20892e826761707da5bce9aa6de7cf81e` |
| product/AGENTS.md | `c682124bb83eec0e7f0b923b58eed3e4b6c5bc89f132467e7777815c4c2360c0` |
| docs/development/workflow.md | `3ef1afc862d831177257ec4e88b7140bb3db22fe1fd134ce00b1314064ebb0e3` |
| docs/development/environment.md | `45c9530847bf9a86d88184c233ec1599b9fffcc750bdd12cd8e3b49afe45d0ba` |
| reviews/runtime/runtime-replay-eval-runbook.md | `e4ebb9330382d069c22668609eca894a4c06f0e9e7e774b4d0d0a7260837b262` |
| tests/test_governance.py | `e7a0487c9804fccf937a01aec815ec3ba3d67764e95b188b4388caa1806826f9` |

### 3.2 沙箱可用性阻断（Task 4.1 前置检查）

本机 `codex sandbox --help` 明确支持 `--permission-profile`。在进一步落实依赖该能力的配置/入口前，实际执行：

```text
codex sandbox --permission-profile :read-only -- /usr/bin/true
```

结果：退出码 71，stderr：

```text
WARNING: proceeding, even though we could not create PATH aliases: Operation not permitted (os error 1)
sandbox-exec: sandbox_apply: Operation not permitted
```

- FIRST_DIVERGENCE：进入 macOS sandbox_apply 时失败，尚未运行 `/usr/bin/true`，更未进入 Council。
- ROOT_CAUSE：当前环境拒绝沙箱初始化；现有输出不能进一步区分外层沙箱嵌套限制与其他系统策略，不能笼统归因于 LLM 或产品断言。
- 类型：ENVIRONMENT_BLOCKED，不是产品测试 FAIL；模型调用数为 0。
- 最小后续操作：人工授权这条零 LLM、无写入的探针通过受控权限审批，或在可初始化子沙箱的本机终端执行同一命令提供结果。不会自动提权、使用 danger-full-access、扩大 CODEX_HOME 写权限或启动产品 Smoke。
- 本次只证明最小沙箱尚不可用，不代表已实现完整权限矩阵或 preflight；Task 4.1–4.5 与其他未完成项仍保留未勾选。按照 apply Skill 和本 Change 停止条件暂停后续实施，等待明确方向。

### 3.3 人工授权的单次沙箱探针

用户随后明确批准仅为上述零 LLM、无写入探针申请执行权限。保持同一 cwd、命令及 `:read-only` 子沙箱，使用工具的 `require_escalated` 单次执行审批；没有添加可复用的宽泛命令前缀授权。

- 实际命令：`codex sandbox --permission-profile :read-only -- /usr/bin/true`。
- cwd：`/Users/caihaoming/Documents/stock_agent`。
- 结果：退出码 0，stdout/stderr 均为空；工具执行记录 chunk ID `c373a8`。
- 对比结论：同一命令在默认受限执行边界内初始化失败，经批准改变外层执行边界后成功。证据支持此前问题与外层受限执行环境有关，而非 Codex 完全不支持此命令；不据此推断具体系统拒绝规则。
- 授权范围：仅此探针，不扩展到 launcher、MCP、Hook、产品 Smoke、源码写入或整个 CODEX_HOME。没有运行产品 LLM，也没有修改沙箱配置或生产实现。
- Task 4.1/4.2 仍未完成：`true` 成功仅证明该批准路径下能够初始化只读子沙箱，不能证明源码拒写、指定产物可写、越界拒写及后代进程继承的完整矩阵。

### 3.4 会话路径兼容与模型配置（本轮增量）

完成 Task 3.3：Smoke（含既有 Ablation 模板）及 Eval 不再包含个人 sessions 路径。两种 Prompt CLI 均接受显式 `--sessions-root`，默认仅解析 CODEX_HOME 或用户主目录，不扫描会话、不复制认证。正常 launcher 的 deferred 路径仍使用 run-scoped 事件。命令中的 repo/run/model/Eval 路径使用 shell 参数引用，支持空格；没有修改研究规则、Replay 算法或历史产物。

实际命令：

```text
TMPDIR=/tmp/stock-agent-path-check.8j4ptw PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_development_environment tests.test_portfolio_council_skill tests.test_runtime_assurance_cli -v
TMPDIR=/tmp/stock-agent-path-check.8j4ptw PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_development_environment tests.test_governance -v
git diff --check
```

- 第一条最终运行 18 tests / OK，退出码 0，工具结果 `8dfa62`。最初同组测试有两个断言失败：新测试错误地期待 macOS `/tmp` 别名，而实现按约定输出 `/private/tmp` 规范路径；测试改为对照规范路径后通过。不是环境失败，也未更改路径规则迁就测试。
- 第二条在新增模型配置测试后运行 16 tests / OK，退出码 0，工具结果 `e101d2`。两组有重叠，不累计为独立案例总数。
- `git diff --check` 无差异格式错误。临时输入由测试在独立 TMPDIR 创建并回收；未启动产品 LLM、Regression 套件或 Release Gate。CLI 测试消费的是确定性测试包，不能冒充真实 Council 验收。
- Task 2.2 部分实现：根开发配置明确 Sol，dev_eval 配置明确 Terra，并通过测试对照现有 canonical model-routing.json；Astra 缺批准仍拒绝。未声称当前 Desktop 模型已切换，也未探测账户模型可用性。
- 本机 `codex --version` 为 0.153.4，help 支持 model 配置；尝试 `codex --strict-config features list` 返回 1，明确报 `--strict-config is not supported for codex features`（工具记录 `b795fb`）。因此不能把 TOML 单元测试当 Codex 实际严格配置加载证明，Task 2.2 保持未完成；后续需使用受支持的零 LLM 配置入口核验。

本阶段字节 SHA-256（仅绑定本阶段修改，不是候选晋升锁）：

| 文件 | SHA-256 |
|---|---|
| product/runtime/smoke_prompt.py | `599f3a324be6ad8fcb405cf11fbdbdc13a7bfc2d9121ede555f7c08fd209fcc9` |
| product/runtime/runtime_eval.py | `efca41761db101a22def810c3359aac0d4a08863661afc95498c60f0dc9aa0b5` |
| product/runtime/cli.py | `829320880ff3e433a9374178f13105b0412e7c9a4553e079a1b1b208a851bba0` |
| docs/development/environment.md | `07f0d16853d9472d5c20fde004880a7a63e921bd00377c3a3ed08f2bf0439dd1` |

当前完成 4/19。尚未完成统一薄入口、实际权限矩阵和加载证明，不能提交人工完成批准。

### 3.5 统一薄入口与路径检查增量

完成 Task 3.1：新增 `scripts/council-dev.py`，直接复用 CLI parser，并在选定 repo 下调用原 CLI；无第二套 Agent、Prompt 或终态逻辑。Smoke、显式准备的新 Regression 案例、Execution Replay 均路由到原 nested-codex-smoke；Artifact Replay 和 Regression 证据消费保持原确定性命令。零 LLM 三类路由测试 mock 的仅是 launcher 调用边界，不作为真实运行证明。

Task 3.2 部分实现：launcher 启动前解析 repo/product/run/state，检查产品标识、源码与输出目录重叠、运行包内符号链接、run manifest/trace 身份、重复 invocation/state 和重放根冲突；解析记录写入原 environment-manifest。尚需补足授权产物根与祖先链接等边界及完整冻结运行证明，不勾选完成。新 environment_preflight 模块目前只有路径检查，不宣称完整诊断已实现。

实际执行：独立 `mktemp -d /tmp/council-entry-final.XXXXXX` 目录作为 TMPDIR，设置 PYTHONDONTWRITEBYTECODE=1，执行 `python3 -m unittest tests.test_development_environment tests.test_nested_codex_launcher tests.test_runtime_assurance_cli -v`。最终 30 tests / OK，退出码 0（工具记录 `2cf35e`）；此前同组 29 项通过，新增路由测试后重跑该聚焦集合，不累计为 59 个独立案例。`git diff --check` 通过。没有执行真实 Council、全套 Regression、Release Gate 或发布。

| 本阶段文件 | 字节 SHA-256 |
|---|---|
| scripts/council-dev.py | `cb152d20c23c4e070132089fc78c2afcbdd1d78dc0b2d1059c5a659fa81fc4e8` |
| product/runtime/environment_preflight.py | `fc7542efd7771b80619efac10740b4ca856afb9558c0056c62f1a9966ccca95a` |
| product/runtime/nested_codex.py | `b3fe7cd5f60c8415188ff0ce9b8311bd04df2a07186b5bdb51b095607fa7695f` |
| product/runtime/cli.py | `f6798cb30a4d47fc2aedcbafadc94cd0d8faaef8ef15814bd3e85d6e9a8133ce` |
| tests/test_development_environment.py | `7e917051217e7753e827104a94a097dacc8b1bdedbcc4b8bc931db3a806d63f6` |

补充 CLI 兼容发现：`codex --strict-config sandbox --permission-profile :read-only -- /usr/bin/true` 返回 1，`--strict-config is not supported for codex sandbox`（工具记录 `59b890`）。拒绝发生在 CLI 参数兼容检查，不是权限矩阵或产品断言；未提权。不能再把顶层 help 中出现 strict-config 推断为所有子命令支持它。Task 2.2/4.1 保持未完成，后续先选有文档/本机依据的配置解析方式，不以删除 strict 校验后命令成功代替原证明。

当前完成 5/19；权限边界未完成前不启动真实 Smoke。

### 3.6 权限矩阵、配置加载与最小例外

本机版本为 `codex-cli 0.153.4`。实际拒绝日志确认 CLI 启动阶段需要写入 `~/.codex/tmp` 与 `~/.codex/installation_id`；用户仅批准这两个精确例外。最终 filesystem profile 仍拒绝源码、项目配置、CODEX_HOME 根目录、auth、config、sessions、SQLite 与 logs 写入，run/evidence/TMPDIR 可写。profile 同时启用网络代理并仅声明 `chatgpt.com`，没有 `*` allow。

历史零 LLM 权限证据 `/private/tmp/stock-agent-streamline-network-probe-v4/evidence/permission-probe.json`：

- 字节 SHA-256：`f174c2388ccd1b953a68e0a30250aff35a1968dda28c24409ae6a9586b014d0e`
- 实际结果：filesystem 四项检查 PASS，`child_inheritance=true`，根/产品 AGENTS 与 portfolio-council Skill 配置加载为 `LOAD_VERIFIED`。
- 命令网络结果：`NETWORK_PROXY_CONNECT_REJECTED`，分类 `HTTP_CONNECT_403`，`llm_calls=0`、`credentials_sent=false`、`response_body_read=false`。该结果只属于沙箱本地命令流量；后续依据官方权限语义确认，它不能单独证明 Codex 模型服务通道不可用，原先将其作为 Change 硬阻断的解释已被 3.10 的双探针复核取代。
- 外层过程证据：`/private/tmp/stock-agent-streamline-network-probe-v4/evidence/permission-probe-process.json`，SHA-256 `f11380ac1bf44514fbd4d3b1ea5419bd81b690eae33dc84914869d76315c2218`，过程退出码 9，正确标记 BLOCKED。

环境预检曾在同一文件权限锁下输出 READY，并确认 CLI、doctor、路径、模型路由、AGENTS 与 Skill 广告；随后新增网络 HEAD 探针，把同一网络问题提前为零 LLM 阻断。Task 2.2、3.2、4.1–4.4 因此有实现、测试和真实探针证据；Task 4.5 仍需成功 Runtime 的 Agent/MCP/Hook 实际执行事件。

### 3.7 受影响的确定性验证

使用独立 `TMPDIR=/private/tmp/stock-agent-streamline-focused.mesW0x`，执行：

`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_development_environment tests.test_governance tests.test_native_execution_proof tests.test_nested_codex_launcher tests.test_portfolio_council_skill tests.test_product_config tests.test_native_run_package tests.test_eval_execution_proof tests.test_runtime_eval_job tests.test_runtime_regression tests.test_native_replay tests.test_runtime_assurance_cli`

结果：退出码 0，118 tests，全部 OK。负向 fixture 按预期打印 `NATIVE_EXECUTION_PROOF_FAILED`，不影响测试结论。执行 `openspec validate streamline-codex-development-environment --strict` 退出码 0。未执行 Calibration、Ablation、Promotion 或完整 Release Gate。Task 5.1 完成。

### 3.8 真实 normal Smoke 的阻断证据

本 Change 共发生两次 normal Council 启动尝试，没有执行 Execution Replay：

1. `streamline-normal-20260909-c` 在最初的 filesystem-only profile 下进入 Codex 事件流，但模型端点 DNS 被外层网络默认拒绝。事件 SHA-256 为 `6209788468532f1bb05429c252372a1ee96a1b01057c54411813efecc22dcfdf`，stderr SHA-256 为 `b97b44c5cc9eafd6c9f45530eb960f1e3139d205ba16156939486ae003013b7e`。保留原始证据后停止运行。
2. 根据第一处分歧增加 `chatgpt.com` 最小代理 allowlist，并创建全新运行包 `streamline-normal-20260909-d`。该次 DNS 已恢复，但 managed proxy 对 CONNECT 返回 403；再次停止，没有继续重试或执行 Replay。

运行 `streamline-normal-20260909-d` 使用 Terra、全新 run_id、统一受限入口及当前运行时 Capsule。输入 fixture 为 `evals/fixtures/codex-native/normal-research.json`。关键证据：

| 产物 | SHA-256 |
|---|---|
| run_manifest.json | `ab716b369393553c0a726aad6ef1c28cf9336c4baa05f697dbacf1bef61b94ef` |
| replay_capsule/manifest.json | `8f3db6c3d1b73e3b4aac91f62b67ffc6bac22199b27f2bd96d832ecc48c40cb4` |
| invocation/prompt.txt | `769b2cc4d718f4fc637df8abd8fb1785c31de7a98517b3777d94e910bf0b3f78` |
| invocation/environment-manifest.json | `12d469abb3dc8d42bd61e506a26310b731dd316e65d2d426a5ba725484493ad6` |
| invocation/codex-events.jsonl | `2ff14dda473c60f663932c20e15b8433f09a87bca622c9421147003baa8` |
| invocation/codex-stderr.log | `dbe8705c9fdc60c69e52ff412b0d6985552af36f12dbc173bc60dd1590903bad` |

`codex-events.jsonl` 可解析，但在模型响应前连续收到 `Proxy connection failed: HTTP CONNECT failed with status 403`；stderr 首个关键分歧为 `wss://chatgpt.com/backend-api/codex/responses` 被代理拒绝。固定、无凭据 HEAD 只作为 command-network 对照，不再用来判定 Codex service/model request；3.10 使用独立最小 `NESTED_CODEX_PROBE` 重现了同一模型端点的真实 403。

FIRST_DIVERGENCE：外层 managed network proxy 的 CONNECT allowlist。

ROOT_CAUSE：当前宿主的 managed proxy 没有接受运行时 profile 声明的 Codex 服务域名；不是 LLM 非确定性，也不是 Specialist/CIO/Risk 产品断言失败。

运行已人工终止以停止无意义重连。没有 Specialist 输出、CIO、Risk 或合法终态，故 Task 5.2 FAIL 且保持未完成；按停止条件未执行 Execution Replay，Task 5.3 未完成。Task 5.4 因缺少可引用的新 Smoke 也保持未完成。

### 3.9 当前结论与停止条件

- 已完成：1.1–1.2、2.1–2.2、3.1–3.3、4.1–4.4、5.1、6.1，共 13/19。
- 真正阻断：宿主 managed network proxy 必须允许 nested Codex 到 `chatgpt.com`，且仍需保持源码只读与后代权限继承。当前仓库不能自行修改该外部策略。
- 禁止的替代：不得将 `features.network_proxy=false` 作为默认修复；它会给所有后代进程开放无域名约束的公网访问，违反 D4 的最小权限边界。
- 后续仅在外部 allowlist 已修复并由零 LLM 探针返回 PASS 后，才可使用新 run_id 重做一次 normal Smoke；成功后再做唯一一次 Execution Replay、受影响 Regression 子集、独立 Reviewer 与人工批准。
- 当前不具备人工完成批准条件；`CHANGE_REVIEW=BLOCKED`，`CANDIDATE_PROMOTION=NOT_PROMOTABLE`。

### 3.10 COMMAND_NETWORK_PROBE 与 NESTED_CODEX_PROBE 分离复核

依据官方 Codex 权限文档，permission profile 的 network proxy 约束沙箱本地命令流量，Codex 的模型、认证及其他客户端服务请求应以实际 Codex exec 证据独立判断。本轮没有修改 allowlist，没有使用 `*`、`**.com` 或关闭 `network_proxy`。

实现将零 LLM 权限探针的网络结果改为非阻断 `COMMAND_NETWORK_STATUS`，并新增最小 `NESTED_CODEX_PROBE`：沿用现有受限外层、run-scoped SQLite/log/tmp 和 canonical `codex exec --ephemeral --json` 参数，只允许固定响应 `NESTED_CODEX_PROBE_OK`，不启动 portfolio-council、Specialist、CIO、Risk 或工具。

- 聚焦测试：`TMPDIR=/private/tmp/stock-agent-streamline-probe-focused PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_development_environment tests.test_nested_codex_launcher tests.test_runtime_assurance_cli -v`，42 tests / OK。首次因未预建 TMPDIR 回退到 `/tmp` 符号链接而发生环境错误；创建独立目录后原样重跑通过，没有修改路径保护规则。
- `openspec validate streamline-codex-development-environment --strict`：PASS；`git diff --check`：PASS。
- 零 LLM 权限/命令网络证据：`/private/tmp/stock-agent-streamline-probe-v7/evidence/permission-probe.json`，SHA-256 `8a8bc884a1b2938869d7a8e024aa896fb029a2f0fa96d579db302a42b11bd342`。结果：权限与配置加载 PASS，`COMMAND_NETWORK_STATUS=BLOCKED`、`NESTED_CODEX_STATUS=NOT_EXECUTED`、`FIRST_DIVERGENCE=null`、`blocks_change=false`、`llm_calls=0`。
- 最小 nested Codex invocation：`/private/tmp/stock-agent-streamline-probe-v7/evidence/nested-codex-probe/invocation/invocation-manifest.json`，SHA-256 `01fa4138f419c0eff50e93c63c8d41a06d0bae11d9031be0d352131c3bc1a552`，invocation hash `fd407635a1db56e0c1c0e9d3ebcdf602a747fa14fb528d2fd55c0f1c68c86361`，模型 `gpt-5.6-terra`。
- 原始事件：`codex-events.jsonl`，SHA-256 `def706ed8a256d759f6acf9dc0b5c409ae54fea0b1a16270d69d8c8c766687be`；15 条 JSON 事件可解析，模型响应前明确记录 `wss://chatgpt.com/backend-api/codex/responses` 的 `HTTP CONNECT failed with status 403`，随后 fallback 到 HTTP 并持续连接失败。
- 原始 stderr：`codex-stderr.log`，SHA-256 `89c2c540959573f39d09531ef7d0b56a8a07b50bdcf603c73e88330cada9ae4c`；包含 `codex_api::endpoint::responses_websocket` 的实际服务请求 403。最终在 180 秒上限超时；分类器已修正为优先保存首因 `NESTED_CODEX_PROXY_CONNECT_REJECTED`，不让后续超时覆盖 403。没有再次调用模型重写历史产物。

最终状态：`COMMAND_NETWORK_STATUS=BLOCKED`（非阻断、供未来 MCP/Provider 最小域名授权时参考）；`NESTED_CODEX_STATUS=BLOCKED`；`FIRST_DIVERGENCE=NESTED_CODEX_MODEL_TRANSPORT`。本 Change 当前确实被实际 nested Codex service request 阻断，而不是被 curl/HEAD 推断阻断。按约定，下一步仅调查实际生效的 `requirements.toml`、MDM 或托管策略，不扩大网络授权。

### 3.11 授权的最小配置修复与单次 normal Smoke

launcher 动态配置增加 `default_permissions="council_review"`，同时保留显式 `--permission-profile council_review`、`features.network_proxy=true`、`network.enabled=true` 和唯一 `chatgpt.com` allow。文件权限表未修改。实际外层命令无 `--sandbox`，内层沿用既有 externally-sandboxed 模式，由外层施加文件权限；未修改用户全局或项目的旧 sandbox 配置，不能宣称已完成所有配置层的迁移。

`review-run` 在缺少当前路径权限证据时自动复用既有零 LLM 权限准备，避免要求用户另跑检查命令。新 run_id 为 `streamline-normal-final-20260909`，产物根 `/private/tmp/stock-agent-streamline-normal-final-20260909`。

实际启动命令：`python3 scripts/council-dev.py review-run --repo /Users/caihaoming/Documents/stock_agent --run-dir /private/tmp/stock-agent-streamline-normal-final-20260909/run --evidence-dir /private/tmp/stock-agent-streamline-normal-final-20260909/evidence --tmpdir /private/tmp/stock-agent-streamline-normal-final-20260909/tmp --timeout-seconds 600`。已通过本轮 require_escalated 执行审批。外层新 sandbox/proxy PID 为 91522；profile hash `8eb380853f245b626bf1145def5fe6e30abad41661dda4b70f36d955fdc3e5d7`。

权限准备 PASS，preflight READY；真实模型请求仍在 2026-09-09T08:09:42.870095Z 对 `wss://chatgpt.com/backend-api/codex/responses` 返回 HTTP CONNECT 403。为停止重复重连，针对内层 Codex PID 91532 发送 TERM，外层正常保存失败记录并返回 7。原始事件、stderr、调用环境和 process-result 位于 `run/invocation/`，权限及外层命令记录位于 `evidence/`。本轮只启动一次 normal Smoke，未启动 Regression 或全量 Gate。

结论：最小配置变更未解决实际连接拒绝，Task 5.2 仍未通过；此次证据不能进一步确定拒绝来自哪一层代理，也不能宣称配置层迁移已经完成。保持未完成，不扩大授权、不提交或推送。

## 4. 当前收尾状态：宿主成功与受限验收分开（2026-09-09）

本节覆盖历史状态摘要，但不改写历史产物。用户已从 Terminal 执行真实 normal：
`bash scripts/run-product-smoke.sh`（脚本绝对路径由用户实际调用，内层完整参数保存在 invocation manifest）。

- run_id：`host-normal-e4e41ded-0e3e-4b25-a026-6249d9d76413`。
- 原始运行根：`/private/var/folders/tn/x1hbkfy17sx0w1lb8kjzzr340000gn/T/stock-agent-product-smoke.ZFpS6a/run`。
- 产品源码快照：`f425ff5f6a3412ee4793224b6dc89869a08956e49a17b08d4e1218fb4d0c295f`（历史运行记录值，不冒充本次文档/脚本编辑后的全仓库快照）。
- 实际模型：`gpt-5.6-terra`；process-result 为 PASSED、failure_code=null、timed_out=false、source_integrity_unchanged=true。
- Runtime Eval 为 PASSED / SAFE_NO_TRADE，检查含 normal_full_chain、actual_council_risk_passage、native_agent_skill_mcp_authenticity、trace_lineage、artifact_replay；本轮读取现有结果，没有重跑 Eval。
- 模型列表刷新超时是该次 stderr 中保留的异常，未阻断该次终态；不据此补跑。

### 4.1 原始产物字节 SHA-256

以下路径相对于上述运行根；字节 hash 与工具内部 canonical JSON hash 是不同口径，不混用。

| 产物 | SHA-256 |
|---|---|
| decision.json | `4331c92985b9d4d4f80789817090e1fad30f888c9e4720e227aa20d0ad50a2fd` |
| report.md | `5bede7845b73f3c633f7ebd38e7edd7b536e95a0985859c2ba39f218c01fd825` |
| decision_trace.json | `7555cab1bbf4b73655c8f7e1d40c40042c2939d1023c739108b434f47e27508d` |
| eval/result.json | `c333240be6efce9c52b43594148769355ef97ba25c5f960f3f2bdbe0459e8371` |
| invocation/process-result.json | `202af361019db626410aabb9030e3ea4f200f64e92a84c3dc6fcb2f76b29bfbd` |
| invocation/codex-events.jsonl | `9d64478a693299c1ef4e9fd34469833e3e608e670e3acb5bf43851226d97cc58` |
| invocation/environment-manifest.json | `c06b16c9f336a9a6bbe1a0d126716b81fde3ece4f9d838591181c13305682062` |

取证命令：`shasum -a 256 <run>/<上述文件>`；使用 jq 读取 process-result、environment-manifest、eval/result；没有复制 SQLite、认证或全局会话。原包位于系统临时目录，长期保留与发布前须按既有敏感信息规则处理，不能整体提交。

### 4.2 权限差异与最小接缝修复

FIRST_DIVERGENCE：最新宿主调用为 `--sandbox workspace-write -C <repo>/product`，environment-manifest 的 `preflight_binding=null`。它没有绑定 review-run 的全进程权限证明。

ROOT_CAUSE：宿主脚本直接转发 nested-codex-smoke，功能执行与受限复核是不同分支。源码 hash 未变化只是观察结果，不能替代 D4 进程边界。此差异不是需要用户修改 Shadowrocket 的证据。

本轮最小修改：`run-product-smoke.sh --review` 显式复用已有 `council-dev.py review-run`，传入本次 run/evidence/tmp 目录并继承已检测代理。其后仍执行 check-run；失败不退回普通模式。未修改 council_review 文件权限、域名、代理开关、业务实现或全局配置；没有新建运行框架。

本轮限定验证：

- `python3 -m unittest tests.test_host_proxy_scripts`：9 tests，OK；含受限路由成功/失败两种合成结果、四个代理变量继承、失败不回退。零真实模型调用；不充当真实沙箱或网络证明。
- `bash -n scripts/run-product-smoke.sh`：退出码 0。
- `openspec validate streamline-codex-development-environment --strict`：有效，退出码 0。
- 修改后脚本 SHA-256：`a375b353ff1ceac54e5343b7227f19f1d8527482405a45c28b590bb86b7423c7`。
- 未修改底层入口 SHA-256：`scripts/council-dev.py` = `a4d58ecf996a42bea35a27a151e0f1243973670a1e2d5259a0b071c0b11c2ce8`；`product/runtime/environment_preflight.py` = `2b1cae0459303538db719e7ac66a55b2baa35e7fd3a958cf35399e086df6cf1c`。
- 测试文件 SHA-256：`a5c9900db88b5e58b43327263d605cf9bc87da9626c24abee3f59ce3ea6a06da`。

### 4.3 六个未关闭任务的明确处置

| Task | 可以复用 | 剩余缺口 / 停止条件 |
|---|---|---|
| 4.5 | 当前 normal 的真实执行事件与资源血缘；原有正负测试 | 仍需逐项核对 Hook 信任、资源加载及权限模式适用范围，不将宿主成功改写成旧受限 probe PASS |
| 5.2 | 当前 normal 功能与完整终态证据 | 原任务的受限入口条件尚未由本次宿主运行证明；新增 --review 仅有零 LLM 路由测试。若安排受限真实运行，应明确仅补这个差异，不否定旧功能成功 |
| 5.3 | 现有 Capsule 和 Artifact Replay | 缺该来源的 Execution Replay；不得用 Artifact Replay 代替，待执行方式确认后再执行 |
| 5.4 | 历史 Regression 能力与接缝测试 | 仍需完成当前依赖/版本映射及零 LLM 子集的正式关闭证明；本轮 9 项脚本测试不冒充 Regression 子集 |
| 6.2 | 本节索引与历史记录 | 未实施本次差异的独立 Reviewer 尚未出具最终复核 |
| 6.3 | 无 | 等待上述关闭后申请人工批准，不能预先勾选 |

本轮不重跑 normal、Replay、产品 LLM、Regression 或完整 Gate，不归档/提交/推送。没有证据要求用户现在修改代理配置。下一项真实补证只应是已存在受限入口的权限与功能绑定；若与此前禁止额外嵌套运行的限制冲突，先取得明确执行授权，不自动重试或放宽安全条件。

## 5. 已批准模式分离与本轮限定结果

批准记录：`streamline-codex-development-environment-scope-approval.md`，
字节 SHA-256 `8b1194f130c6c53be475e41e6850acd73ca784ca04012f3cb65a86bc34a9c169`。
该批准仅调整范围，接受已列明残余风险；不代表 Change 完成或生产晋升。

### 修改与证明边界

- Proposal、Specs、Design、Tasks 同步模式分离；4.1–4.4 的既有勾选是历史记录，不构成当前全进程隔离通过。全进程源码强制只读独立状态 **UNVERIFIED**，明确排除在完成保证之外。
- 宿主脚本 --review 在任何外部命令或产物创建前拒绝；不回退普通运行。开发薄入口的旧项目沙箱命令同样拒绝，保留历史实现但不再路由进入。
- self-check 仅白名单转发 check-run / trace-check；不启动 Council、沙箱、网络探针。测试可直接在当前环境按授权范围执行。
- 普通宿主模式保留既有代理检测和 native launcher。--prepared-run 只转发已准备运行，不重复 prepare；Smoke 与 Execution Replay 使用同一入口，冻结根由既有 manifest 路由选择。后续仍需原 finalizer，check-run 不代替执行重放比较。
- 诊断 Skill 与活跃环境/运行手册已同步：Reviewer 默认只读，补跑只提出缺口，不要求先创建沙箱或准备新 run。

### 本轮实际限定测试

命令（仓库根）：
```text
python3 -m unittest tests.test_host_proxy_scripts.EntrySeparationTests tests.test_host_proxy_scripts.HostProxyTests.test_host_routes_and_preserves_failure tests.test_host_proxy_scripts.HostProxyTests.test_entry_reuses_launcher_and_terminal_check
```

首轮 6 项中 1 项失败：测试将 /var 与规范化 /private/var 当成不同冻结根；修正测试期望为 resolve() 后，同一命令 **6 tests，OK，退出码 0**。产品代码未因该断言失败改变路径安全逻辑。

覆盖：旧 --review 各参数位置拒绝且无外部调用；自检禁止隐式启动；确定性命令退出码传播；宿主 prepare/launcher/check-run 顺序及失败传播；冻结根路由。子进程和系统查询均使用测试替身，不调用真实模型、沙箱、Replay 或 Regression。
另执行 bash -n scripts/run-product-smoke.sh 与 git diff --check，均退出码 0；本轮未执行全量测试或完整 Gate。

实现/测试字节 SHA-256：
- scripts/run-product-smoke.sh：`6fdc5bcc36d9a716252c584a0b537f17390059dab2bd1c3e6e322029e53d665f`。
- scripts/council-dev.py：`eb596bce837f6c4f640159a36727e0fc8fe46c0b1032676f114281b4dbae7121`。
- tests/test_host_proxy_scripts.py：`66faff80513bf5afce67778ded5528f5773f479b28ec77d092bafc23872c5fdc`。

### 证据复用与剩余事项

第 4.1 的 normal 运行及 hash 原样保留，仅复用原功能成功；不将它当成本轮新增入口、Execution Replay 或全进程隔离的真实执行证据。
本轮未勾选 4.5、5.2、5.3、5.4、6.2、6.3；仍需按调整后契约完成加载证据归集、normal 证据正式映射、Execution Replay、原定接缝证据、独立复核和最终人工批准。
不再为旧隔离入口补跑 normal，不因隔离 UNVERIFIED 阻断日常功能证据审查，也不把该隔离要求标为完成。
未修改 Shadowrocket、原生权限、网络 allowlist、金融业务实现或生产指针；未运行模型/Replay/Regression/Gate，未归档、提交或推送。

## 6. 限定收尾：证据映射与 Task 5.2 关闭

本轮只读归集，并更新任务/报告；没有执行测试或模型。以第 4 节原始 normal 为来源，逐项计算当前产品文件 SHA-256，与 run_manifest.integrity_before.files 比较：差异列表为空。候选标签为 0.3.0-candidate.1；实际版本依据为完整文件 hash，而非标签本身。历史源码快照仍为 f425ff5f6a3412ee4793224b6dc89869a08956e49a17b08d4e1218fb4d0c295f。

### 原始运行证明补充（字节 SHA-256）

- run_manifest.json：`25456c81d602b740dc8fd9689773106ec620f44efff8b12d8da794fad9519a64`。
- invocation/subagent-events.jsonl：`a9d13023c2fa7b2d398b6d0ae82646553f88fe8360877c8c6ae967dd8f7b30ae`。
- events/codex/specialist-execution-proof.json：`390e686322c762776a3b545bb97be23e59a59061ab62d52839147c2cc8fe0d20`。
- events/mcp/events.jsonl：`cfea64c2f3a2c9949fb4c462c5a97140cab45213049734905b9de8cca501708c`。

读取实际 proof 的 capture_sources 与 JSONL hash 对应；两个不同 Specialist session 各有 Start/Stop 与结构化 output hash，proof 绑定 Agent 配置、Skill 和任务；MCP 有对应调用。Trace 含三角色及版本/input/output/prompt/schema 血缘，并存在 deterministic_risk_engine 的 APPROVED 记录；合法 NO_TRADE 未绕过 Risk。不是仅引用报告 PASS。

| Task | 已有证据 / 版本与适用范围 | 本轮判定 |
|---|---|---|
| 4.5 | 上述 normal 原始加载与执行证明；第 3.7 的 118 项历史执行包含 test_native_execution_proof。当前测试文件 hash 为 `2c037cef1405f75d58c6a64c7bc53a32f2172e36d6ef513d87e4efb27dff0065` | 正向加载充分；历史负向测试的运行时测试源码绑定尚未由底层记录完整证明，不能仅凭当前测试内容倒推旧执行。保留未完成，不重跑 |
| 5.2 | 第 4.1 终态产物、原始 JSONL/Hook/MCP、Trace/Risk；当前产品文件与该运行快照无漂移 | 完成，仅覆盖该 normal 功能链；不覆盖后续宿主脚本修改或全进程隔离 |
| 5.3 | normal 有 Capsule 与 Artifact Replay；在 /private/tmp、系统 TMPDIR、evals/results 深度不超过 5 的指定 result/execution-replay JSON 中读取 163 个结果，没有匹配此 source_run_id 的执行重放结果 | 缺一次本来源的 Execution Replay，不以旧不同来源或 Artifact Replay 替代；提供宿主命令，不在本任务执行 |
| 5.4 | 历史测试包括 test_regression_only_forwards_existing_index_consumer、test_three_new_execution_sources_use_the_same_cli_launcher、test_cache_key_changes_with_any_versioned_input、test_verified_cache_hit_reuses_hash_bound_runtime_artifacts、test_runtime_artifact_must_match_declared_candidate_manifest。第 5 节 6 项测试补充入口分流/拒绝隐式启动/冻结根/失败传播 | 原定行为在测试代码中有覆盖；历史运行源码版本证据不足，保留未完成。缺的是测试执行与当时版本的绑定，不是新增功能或新测试标准 |
| 6.2 | 本报告和既有证据索引 | 待必需产物齐全再做一次独立差异复核，本轮不提前分派 |
| 6.3 | 范围批准不等于最终批准 | 未完成 |

接缝测试当前文件 hash：test_development_environment.py = `e5feee5dff20f86350d0a05554664621d909e8e01fc4b2a823fe6be2a9647e13`；test_runtime_regression.py = `e6ce103715b1e9ce6462bdedebdb99ae86e8f5419c02e6a89a525c7bb5faed9e`；runner.py = `69ff1a046390fd65daff82502c51d40732865060d96598b220a3cc76e2ac1441`。这些是本轮读取值，不伪称历史执行锁。第 5 节的 6 项测试及当时文件 hash 直接复用，不重新执行。

一次宿主执行命令在本任务回复中提供，包含 prepare-execution-replay、已有 --prepared-run 宿主入口和原 finalize-execution-replay；新 bundle 保存各阶段日志与入口 hash。失败即停止，不修改源运行/Capsule/锁。该命令尚未执行，未形成新运行证据。

## 7. Execution Replay 首次执行失败与专项修复

实际 run：host-replay-80479d80-fdfe-4bdf-8a1d-70980a414996，产物 /private/tmp/stock-agent-execution-replay.UZXy87。
prepare 成功；Codex 退出码 1，JSONL 事件为 0，stderr 为 `Not inside a trusted directory and --skip-git-repo-check was not specified.`。没有执行 Agent 或 finalizer，5.3 保持未完成。失败不是代理/沙箱网络问题。

用户批准最小修复；本机 codex exec --help 明确支持 --skip-git-repo-check。
修复仅宿主侧：prepare 写外置 source 指针，重放启动选择 replay-codex-transport.py，校验来源/目标 manifest、run_id、Capsule 和密封内容后补参数，保存实际命令/adapter hash。没有改写旧快照、版本锁或运行产物。

实际确定性测试命令：
`python3 -m unittest tests.test_replay_transport tests.test_host_proxy_scripts.EntrySeparationTests tests.test_development_environment.EntryPathTests.test_three_new_execution_sources_use_the_same_cli_launcher`

结果：9 tests，OK，退出码 0；git diff --check 通过。测试使用替身，不运行 Codex 模型，不将此结果视为 Execution Replay 成功。
适配器字节 SHA-256：876e38211557823d7837757ff5f5e54c7fc52c56a70e5a686042d5b18df5d975。
宿主薄入口字节 SHA-256：8cbbd1abfae9b5ab89f465e973c2a4dcc1d865af83f921b9dd9d7fdb82a5db4c。

后续由用户使用原 source_run 和新的 bundle/run_id 重新执行既有宿主命令；旧失败目录不可复用或补写。新 invocation/host-transport.json 必须纳入复核；原 finalizer 仍决定配置等价性。全进程隔离 UNVERIFIED，未归档/提交/推送。

## 8. 宿主 Execution Replay 成功与 Task 5.3 关闭

运行根：`/private/tmp/stock-agent-execution-replay.diDwuI`；run_id：`host-replay-96dba124-e4d4-402d-bf5e-4ec360ea20db`；来源为第 4 节 normal。
用户实际执行先前提供的 prepare → 宿主 --prepared-run → check-run → finalize-execution-replay 命令；日志位于 prepare.log、execute.log、finalize.log。

真实执行耗时 287.778 秒，32 个 JSONL 事件，合法 SAFE_NO_TRADE，Specialist/CIO/Risk/Eval 产物齐全。comparison/result.json 为 PASS，九类 source/replay configuration hashes 一致。宿主适配器 hash 与当前文件一致，实际命令仅补一个 --skip-git-repo-check，保留 workspace-write；冻结版本锁未改写。

本轮额外核验仅调用现有只读 `verify_execution_replay_result(Path('<bundle>/comparison/result.json'))`，从底层包重新计算而非只读摘要；结果 PASS、configuration_equivalent=true，canonical result_hash：`02ea4793107b9f65609241e8296d0e8646063e8a976e62ad3657951925c65aba`。没有新建运行或重新执行 Agent。

字节 SHA-256：

| 相对路径 | hash |
|---|---|
| comparison/result.json | `4a11e0758081237c8271784baf309f9728667a6d079647ffbba3ce7f91b56ef1` |
| comparison/report.md | `d45401ac0b97b7d8adeb9347ea32b96da540322474299c3298d9527dfa4f365c` |
| run/invocation/host-transport.json | `db0f7de51c046d4a4c8757e0720783f75c4376540079c06d700e7c9dba17ca94` |
| run/invocation/codex-events.jsonl | `361b1d539eed1831887c323bf3fc655352fdb300af1a1a625803f26a4160005a` |
| run/invocation/subagent-events.jsonl | `534c8e4e409d416a62784566d67c171fa6675fc33ad59881554215b654c316cc` |
| run/decision.json | `926476fe69acdeff673a1e1cddaeda8e898fbe22774d3623d820b3bb8c92a8db` |
| run/report.md | `4410d9e63e67ef2fe72c6228ea050d68c168786824cc148fdbca579460416a5b` |
| run/decision_trace.json | `22a94b13c77d6539f3a6003f05b2851c93f1414f41bfd9b7a7823a4ff03b8a39` |
| run/eval/result.json | `019a14e69cd5a522d65664d54e91c8395927580022f8debff1b6d07ff2f09618` |

关闭 5.3；当前 15/19。第 6 节的 4.5/5.4 历史测试执行版本绑定缺口不因本次重放成功自动消失，未补测；因此未启动最终独立复核。6.2、6.3 保持未完成，尚不具备最终人工批准条件。全进程隔离继续 UNVERIFIED，不归档、提交、推送。

## 9. 4.5 / 5.4 限定关闭证明

用户要求继续完成剩余任务后，本轮只补 11 项已有确定性测试以修复已列明的历史版本绑定缺口，不新增验收标准。没有重跑 normal、真实 Replay、完整 Regression、Calibration、Ablation 或 Gate。

执行证据：`/private/tmp/stock-agent-close-seams-i98ft6pp/execution.json`；逐项输出在同目录 stderr.log/stdout.log。
执行驱动：`python3 /private/tmp/stock-agent-close-seams-20260909.py`。execution.json 完整保存实际 `python3 -m unittest -v <11个test_id>` 参数、cwd、独立 TMPDIR、开始/结束时间、退出码和运行前后文件 hash 清单。
结果：11 tests，OK，退出码 0；source_before 与 source_after 完全一致。
源码/依赖快照（product、tests、scripts、evals/regression 所有非 pycache 文件）：`0f397f52a9e82228f83a7a534e128dc82d1c4a305adc956a428213fe8f950375`。不将该限定快照称为全仓库或生产 candidate lock。

| Task | 本轮 test_id 末段与原要求映射 | 真实证据复用 |
|---|---|---|
| 4.5 | test_skill_load_requires_exact_successful_runtime_event（成功/缺失/失败/重复/hash漂移）；test_self_report_without_codex_skill_or_mcp_proof_fails；test_saved_report_must_equal_child_final_structured_output；test_future_or_stale_fixture_safely_stops_before_agents；test_zero_codex_exit_cannot_mask_incomplete_council | 第 6/8 节真实 normal/Replay 原始加载、Hook、MCP、Trace 和终态；原 Hook 信任调用未扩大，宿主运行授权不等于全进程隔离 |
| 5.4 | test_regression_only_forwards_existing_index_consumer；test_three_new_execution_sources_use_the_same_cli_launcher；test_cache_key_changes_with_any_versioned_input；test_verified_cache_hit_reuses_hash_bound_runtime_artifacts；test_runtime_artifact_must_match_declared_candidate_manifest；test_duplicate_runtime_run_id_is_rejected_before_suite_execution | 第 5 节入口分流/失败传播测试；第 8 节宿主真实重放证明当前适配入口可调用冻结 launcher。其余产品能力沿用旧版本证据，不宣称当前 candidate 完整 12-case 晋升 |

测试涉及的 Runtime 产物由既有测试替身生成；缓存/候选检查会运行测试内部确定性消费者，不调用真实模型，不等于启动一次完整产品 Regression。原始错误输出按测试期望保留，最终 unittest 为 OK。
据此关闭 4.5、5.4；6.2 待未参与实施的独立 Reviewer 读取本次差异及上述底层证据，6.3 待用户最终批准。未修改产品代码、原生权限、业务安全或历史运行包。
