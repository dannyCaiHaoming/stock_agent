# retire-legacy-sandbox-paths 独立限定评审报告

```text
CHANGE_REVIEW: PASS
CANDIDATE_PROMOTION: NOT_PROMOTABLE
ISOLATION: UNVERIFIED
TASK_4_2_SUBMISSION: YES
```

本次源码差异与已有证据满足 Task 4.1 的限定技术复核要求，未发现阻断项。可以提交 Task 4.2 人工完成批准；本报告不构成人工批准、归档授权或候选晋升结论。

## 1. 独立身份与执行边界

- Reviewer：本次新启动的独立评审会话，未参与本 Change 的实现或修复。
- 实际会话标识：`01a086a3-7040-7c31-aa74-e66faa2ffad8`，通过 `printenv CODEX_THREAD_ID` 取得。
- 评审日期：2026-09-09。
- 仓库：`/Users/caihaoming/Documents/stock_agent`。
- 指定基线及实际 HEAD：`ed45255626df4e6a8614f2c54254c50a6cc64e40`。
- 评审对象：当前工作树中的已授权未提交修复及指定已有证据。

先读取了根 `AGENTS.md`、`docs/development/workflow.md`、本 Change 的 `proposal.md`、`design.md`、`tasks.md` 和两个 delta specs，再开展差异与证据核对。

本会话仅执行文件读取、Git 只读查询、已有 JSON/JSONL 解析及 hash 重算。没有修改文件，没有运行测试、产品 LLM、Smoke、Replay、Regression、Calibration、Ablation、Promotion 或完整 Gate；没有新增探针、项目沙箱、修改配置、归档、commit/push。未读取认证文件、私人全局会话或 run 下的 `.codex-runtime` 原始状态内容，未查询官方网络或运行 CLI 探针。

本报告直接返回主线程保存；Reviewer 未写入报告文件，也未勾选 Tasks。

## 2. 基线、差异与源码快照

相对基线，已跟踪差异共 11 个文件，225 行新增、993 行删除：

| 类别 | 文件 |
| --- | --- |
| 根指令及配置 | `AGENTS.md`、`.codex/config.toml` |
| 对应入口说明 | `docs/development/environment.md` |
| 启动及退役处理 | `product/runtime/nested_codex.py`、`product/runtime/cli.py`、`product/runtime/environment_preflight.py`、`scripts/council-dev.py` |
| 接缝与治理测试 | `tests/test_nested_codex_launcher.py`、`tests/test_development_environment.py`、`tests/test_host_proxy_scripts.py`、`tests/test_governance.py` |

未跟踪内容为本 Change 规划、两份验证报告和证据目录。没有发现上述源码快照范围内的未跟踪新实现文件。

完整源码清单：

`reviews/development/retire-legacy-sandbox-paths/source-sha256.txt`

清单完整字节 SHA-256：

```text
dd57caa2eb1eb162d7004640f745aab554bc8626080d416d9437ccdfcf2b8d3d
```

独立逐文件重算结果：**177/177 匹配，0 个不匹配**。另从当前 Git 跟踪路径重新生成同范围清单并排序，其 SHA-256 也等于上述值。

清单范围为 Git 跟踪的 `AGENTS.md`、`.codex/`、`.agents/`、`product/`、`scripts/`、`tests/`、`evals/fixtures/`、`docs/development/`、`pyproject.toml` 当前工作树字节。它覆盖本次全部实现、配置、测试及环境文档，不包含 OpenSpec 规划、报告自身、历史运行结果、临时产物或用户级配置。该标识不是整仓库快照、Git commit 或生产候选版本锁。

本次读取的规划文件另行绑定如下：

| 文件，相对本 Change 目录 | SHA-256 |
| --- | --- |
| `proposal.md` | `877211140a96c2c9cedac69e482b5f8da4af443f457b75c7c349f8e436e26e7d` |
| `design.md` | `ac10a104db1148648a634391bce38cf0d330b7f6949b020d340158da5bfd37e0` |
| `tasks.md` | `e0219b9432f85c8c576b1a6a25f45587586959006492b76fe628b9e725643a19` |
| `specs/codex-development-environment/spec.md` | `59a2a73c676be849b057184944c05b41d1f9feefdc4c3e60b04fd098c67024ee` |
| `specs/three-plane-governance/spec.md` | `b90549af406c91bb37865566e43bbe78e95b351220ef57f98fa674162b86885f` |

`tasks.md` 的 hash 对应 Task 4.1、4.2 尚未勾选的本次评审版本。

## 3. 三项差异的逐项结论

| 验收项与对应规格 | 独立核对依据 | 结论 |
| --- | --- | --- |
| 删除底层自动绕过；“执行模式必须分离且不隐式启动” | `nested_codex.py:287` 在构造命令前拒绝 `externally_sandboxed=True`；正常分支固定保留 `--sandbox workspace-write` 和 `--ask-for-approval never`。原自动添加 approvals/sandbox 绕过参数的分支已删除。 | PASS |
| 历史 preflight 不再授权启动；“历史沙箱参数不能触发降级” | `nested_codex.py:361` 在 `resolve_run_paths`、manifest/report 读取及目录创建前拒绝非 `None` 的 `preflight_report`。历史 binding 校验和据此选择外部沙箱的代码已删除。 | PASS |
| 薄入口、底层 CLI、直接 API 前置拒绝；“绕过薄入口调用历史流程” | 共用 `environment_preflight.py:28` 的退役检查。底层 CLI 在参数解析及业务分发前调用；薄入口 `main` 和 `forwarded_command` 均先调用。覆盖五个旧命令、`--review` 及等号形式、`--preflight-report` 分离值和等号值形式。CLI 返回非零及明确 failure code。 | PASS |
| 旧直接启动实现不可恢复 | `restricted_main`、`run_nested_codex_connectivity_probe`、`run_environment_preflight`、`run_permission_probe_with_child` 均为立即抛出 `PROJECT_SANDBOX_ENTRY_RETIRED` 的 stub。构造器及 launcher 另以 `LEGACY_SANDBOX_MODE_RETIRED` 拒绝旧模式。 | PASS |
| 正常宿主路径和现用 helper 保留 | `resolve_run_paths` 的身份、路径和重复运行检查仍被正常 launcher 使用；正常转发与退出码传播保留。未发现当前受支持入口能够重新接通旧沙箱启动绕过。 | PASS |
| 根指令三类入口分离；“开发指令必须按任务条件读取” | 根指令明确当前环境确定性自检、宿主 launcher 执行 Smoke/Execution Replay、独立只读证据复核；底层 CLI 被说明为内部实现及确定性工具入口。开发/产品角色、学习面和发布边界保留。 | PASS |
| 配置最小清理；“项目权限残留清理不得改变现用权限边界” | 实际 diff 仅删除 `[permissions.project-edit.network.domains]` 及两个域名项，共四行。独立 TOML 解析对照表明：从基线移除该唯一废弃 permissions 内容后，与当前配置完全相等。 | PASS |

根配置继续保留 `model="gpt-5.6-sol"`、`sandbox_mode="workspace-write"`、`network_access=true`、`max_threads=4` 及四个开发 Agent 的完整注册内容。没有迁移新权限框架或修改宿主代理配置。

本评审没有把普通宿主路径描述为原本全部不安全：基线普通分支本来就使用 `workspace-write`，本 Change 关闭的是旧 external/preflight 自动绕过链。`--dangerously-bypass-hook-trust` 属于明确保留的不同契约。

历史低层 helper 的存在不等于退役启动链仍可达。源码仍有权限表构造和低层诊断 helper；它们不能统称为纯只读函数，但未发现其重新接入当前退役 CLI/API 启动路由。本结论不要求删除所有历史 helper，也不要求重写冻结包。

## 4. 确定性接缝证据复核

本轮没有执行测试；以下结果来自读取原始日志，并对照当前测试源码中的实际断言。

| 覆盖组 | 日志中测试方法数 | 核对到的实际断言 |
| --- | ---: | --- |
| Launcher | 3 | 默认与显式 False 命令等价；原生参数及 Hook 保留；True 明确拒绝；已有和不存在 report 均在路径解析、读取、目录创建及子进程前拒绝。 |
| RetiredSandboxEntryTests | 5 | 五个旧命令在两层 CLI 和直接转发调用中拒绝；旧参数两种形式、`sys.argv`、直接启动 stub、旧命令不再展示。 |
| EntryPathTests | 9 | 普通路径、相对路径与等号参数、身份/目录冲突、冻结根选择及原有失败传播。 |
| EntrySeparationTests | 4 | 宿主 `--review` 前置拒绝；自检白名单及非法请求拒绝；`check-run`/`trace-check` 转发并保留退出码。 |
| HostProxyTests 选定方法 | 1 | 用假的系统命令与 Python 入口验证 prepare → launcher → check-run 路由及 0/9/7 状态传播。 |
| 根治理、配置及模型一致性 | 6 | 三类根入口、角色边界、条件读取、Agent 注册、TOML 全字典及模型策略一致性。 |

`assert_no_effect` 不只匹配错误文字：还检查 `subprocess.run`、`subprocess.Popen`、`urllib.request.urlopen`、`Path.read_text`、`Path.mkdir` 未被调用，以及临时目录保持为空。

原始结果为：

- `task-1.1.log`：3 项通过。
- `task-1.2.log`：2 个导入错误、4 项通过；错误为误删 `network_access_probe` 兼容别名。
- `task-1.2-corrected.log`：恢复别名后，18 项通过。
- `task-2.log`：6 项通过。
- `focused-final.log`：`Ran 28 tests in 3.145s`，`OK`。
- `openspec-validate.log`：`Change 'retire-legacy-sandbox-paths' is valid`。

首次失败被完整保留，属于实施编辑错误，不是环境错误。当前源码中别名已恢复，最终日志没有遗留失败。阶段日志是过程证据，当前限定接缝结论以最终日志及匹配的源码快照为准。

仓库证据目录相对路径：

`reviews/development/retire-legacy-sandbox-paths/`

| 文件 | SHA-256 |
| --- | --- |
| `focused-final.log` | `bd3b14527ac859ec9cc0c27943716a242fe9f911d21537082169ec7d4bac50e4` |
| `openspec-validate.log` | `3ac7750df0e9a3709eee26e6c02b5309c6d01fe5087fc66e3b5f3e53721e03cd` |
| `task-1.1.log` | `1d8d38bcee6b258b3f17bb4a3f4d295f2ecb13347d74e1ebb630d51cac949f87` |
| `task-1.2.log` | `fa2bc924f26ef430750a3c1bdbb720d59d9c5dc1a79a5d9b53213a8c23a38d63` |
| `task-1.2-corrected.log` | `6ea78d39daf3bfc38fa6f9cbaa0a9f3d3bf5ee82c99b17f409a3821fa32ef61e` |
| `task-2.log` | `705c3331210dd35ac009f8e12af54b7535d09d1c3dd43f0408824806c981f6cf` |

上述六份日志及源码清单，与 `/private/tmp/stock-agent-retire-legacy.eeXNmb/` 下对应原件的字节 hash 全部一致。

## 5. 修复后 normal Smoke 原始证据链

运行目录：

`/private/tmp/stock-agent-retire-normal.lar8XL/run`

运行标识：

`host-normal-5f21e995-d4cb-426f-b3d3-488b161c455b`

已有 manifest 记录模型为 `gpt-5.6-terra`、运行时为 `codex-cli/0.153.4`、候选标签为 `0.3.0-candidate.1`。本轮没有另行查询其可用性或启动它们。

### 5.1 启动、源码与实际加载

- invocation 与 environment manifest 的实际 argv 保留 `--sandbox workspace-write`、`--ask-for-approval never`、`--strict-config`、`--ephemeral`，cwd 为本仓库 `product/`；`preflight_binding=null`。
- 源码完整性 before/after 各列出 83 个产品文件。逐文件与当前工作树核对全部一致，两份映射相同，映射 canonical hash 均为：

```text
f836d67fe2a75a9b6e2e0fa23a969c6c052f19839f19be15b69583137fdcefcd
```

其中当前 launcher `product/runtime/nested_codex.py` 的完整文件 hash 为：

```text
685ea75b5290164d356e997616497ba0ef702c05c7c95418b174e7d6ff582bf2
```

该 83 文件产品快照与前述 177 文件源码清单范围不同。

JSONL 共 36 条记录。以下成功命令事件的完整输出字节，与当前文件逐字节 hash 匹配，且 proof 中相应事件 canonical hash 也匹配：

| JSONL 序号，从 0 开始 | 实际读取对象 | 输出字节 SHA-256 |
| --- | --- | --- |
| 6 / `item_3` | 根 `AGENTS.md` | `6e25a68e1a16b87641ba1af1eb753ed46917d0fe2474627fb7ea3c37bcd695a9` |
| 8 / `item_4` | `product/AGENTS.md` | `c682124bb83eec0e7f0b923b58eed3e4b6c5bc89f132467e7777815c4c2360c0` |
| 10 / `item_5` | `product/skills/portfolio-council/SKILL.md` | `74f8cd9e37862cb43e207dd9fadcf7b411f93949d59770e711bf7011814a369c` |

这提供了本次根指令和 Skill 实际读取依据，而非仅以配置存在或模型自述认定加载成功。

### 5.2 独立 Specialist、CIO 与 MCP

父会话：

`01a08694-c2bc-77e3-9c56-5d368745580a`

| 角色 | 实际子会话 | 生命周期 |
| --- | --- | --- |
| Company Analyst | `01a08695-e6ba-70c3-ad23-d1efcc006e26` | Start `14:32:51.667491Z`；Stop `14:33:42.983932Z` |
| Independent Skeptic | `01a08696-5faf-7a13-b890-9863475e572e` | Start `14:33:24.490189Z`；Stop `14:39:08.531989Z` |

两条 PreToolUse dispatch 均为 `ALLOW`、`fork_turns=none`；两次 Start 均发生在第一次 Stop 前。四条生命周期事件和两条 dispatch 的内部 `event_hash` 重算全部匹配。Skeptic 输入为 `INDEPENDENT_FIRST_PASS`，只包含研究范围、证券、组合摘要、截止时间及允许 Evidence IDs，没有 Analyst/CIO 输出或派生结论。

两份 Specialist 结构化输出的 canonical hash 与 Stop、proof、Trace 及 CIO 的 `consumed_reports` 一致。三个角色的 input、invocation manifest、prompt、output、Agent 配置、Schema 和绑定 Skill hash 均逐项匹配。

CIO 在父会话内执行；事件显示先完成 Specialist 产物和 `prepare-cio`，再成功读取 CIO input/invocation/prompt/schema，并写入 `cio/runtime_cio.json`。Trace 中 `runtime_cio` 为 `COMPLETED`，具有独立 invocation/input/output hash。

MCP 原始日志有三条结果：Analyst 的 Evidence query 和 math calculation，以及 Skeptic 的 Evidence query；均为 `access_mode=read`，与 Trace 完全一致。现有 MCP 配置只启用 `query`、`calculate`，实现按 run、invocation、工具白名单和 Gate Evidence IDs 约束调用。本 Change 没有增加业务写入或券商能力。运行产物和审计日志的持久化不能解释为全进程零文件写入。

这是**一次 normal Smoke，三个逻辑 LLM 角色执行**。proof 的 `llm_calls=3` 按角色统计，不应解释为只有三次底层模型请求，也不是运行了三次 Smoke。

### 5.3 Risk、Eval 与合法终态

- Gate 截止时间为 `2026-01-31T23:59:59Z`，允许五个 Evidence IDs。
- CIO 明确消费两份 Specialist 输出，产生 `LOW_CONFIDENCE`、`NO_TRADE` 草稿。
- `risk/check-1.json` 记录 producer 为 `deterministic_risk_engine`、stage 为 `FINAL`、状态为 `APPROVED`。
- Risk `draft_hash` 与 CIO 输出、Trace risk input hash 一致；Risk 文件 canonical hash 与 Trace `result_hash` 一致，结果对象也完全相同。
- Risk 原动作及最终动作均为 `NO_TRADE`，不是跳过 Risk。此次 normal 样本不证明 veto 或全部风险边界场景。
- 决策为 `advisory_only=true`、终态 `SAFE_NO_TRADE`，report 与 decision 一致。
- Eval 原始结果为 `PASSED`，九项已有检查均通过。独立重算其内部 hash，并核对 decision source hash；按 `persist_eval_result` 的写入顺序，在内存中去除 Eval 后附加的 Trace 事件及 artifact 项后，得到的 Trace source hash 与 Eval 记录一致。没有执行 Eval。
- Trace 引用的 **121 个产物文件 hash 全部匹配**。
- process-result 记录 `codex_exit_code=0`、`failure_code=null`、`first_missing_stage=null`、耗时 `592.297` 秒，内置单运行检查 exit code 为 0。宿主脚本最终退出码 0 来自已有 Smoke 记录，本轮直接核验的是上述底层产物。

重算匹配的内部 canonical 标识：

| 标识 | 完整 hash |
| --- | --- |
| invocation_hash | `5ed27e4e4c88943421845466d011581101574140914cba5957adc16ba5dc73eb` |
| proof_hash | `a14937edf64b378b24103b051ad6174b3b98781d7159be5c1c08ab2d20e027d0` |
| process_result_hash | `b446334cb146960989a767d0aec2dc4974ad07e1e5183ce4c7b36487556490b4` |
| eval_hash | `6ee3a513233d35dfe383ff0a856c2001ea056c5b6e3208dd7db29a4ac89e8254` |

### 5.4 原始产物文件 hash

以下路径均相对上述 Run；这里是文件字节 hash，不与内部 canonical hash 混用。

| 文件 | SHA-256 |
| --- | --- |
| `run_manifest.json` | `3ba4a9e24e800b1a23e49f577df76c1cb7693572787ff572fc8a87808e5c0392` |
| `invocation/invocation-manifest.json` | `62542fb4958af548483df3bd3bb439025993b155f903f3b344e7447ca5838e08` |
| `invocation/environment-manifest.json` | `ed1026186f7db4eaf31b3fef906215a05c24f5693bf3dde7fe28a4d1aad1d313` |
| `invocation/process-result.json` | `58570db93314f6a8a3e77f8a1b68a9c0121198ae68203898290ddd293989de9b` |
| `invocation/codex-events.jsonl` | `9ce02891165aa1be5008198afe88f339b7836c2e92d292b6345a238117b4d5e7` |
| `invocation/subagent-events.jsonl` | `0bc5bbd2ae4b18b0dce8c09fb5f2615988a3c131ee1b0ef87fb4197622ddd150` |
| `invocation/subagent-dispatches.jsonl` | `4dd4d2bae7c8139dd1189bb4ba137ee8bff4275f7ef9f4ccde2b0b9570d94ba6` |
| `events/codex/specialist-execution-proof.json` | `2b7d9d80e2cbbf4195d44ac88d69135f2591a9b952ef0712a8cce6d8e4256560` |
| `events/mcp/events.jsonl` | `9424c78a532bfc0c3722b2119282cfe511f63f6afb7a51f8a1aaccfdbc23024e` |
| `evidence/gate.json` | `cc7085873ac6bdfec2836a4e02dc2b43ceb9a079bf120fbb2c4fb192246ea6ad` |
| `cio/runtime_cio.json` | `2ccd4314f748deb92b883e9dfc23bd464cda761f52e795bbfdf0cf3f020d88c6` |
| `risk/check-1.json` | `85785fd70a056573be1bc7621a2521850e483fcf981b7b6b13a34439a35ede13` |
| `decision.json` | `c6036cef39d1c709ebd75fb3aad8cf475b4155a16b69d8ac1f8b7fb4f29fdab5` |
| `report.md` | `252d32e13480f849c02e5b59ea4db61444e69951f528a824d43c4bcf58adb25e` |
| `decision_trace.json` | `58a11e031d4e4d6c4f0fa72bf9053f5026dd55bd8cffeb5453beff4dc186e627` |
| `eval/result.json` | `8ca1b97950ba0c5e51ceedd4c4dc3d703336c984c7a43533cb9ad581cc7d4de6` |

两份实施报告的独立文件 hash：

| 报告，相对 `reviews/development/` | SHA-256 |
| --- | --- |
| `retire-legacy-sandbox-paths-verification.md` | `e7a63c635e2ec09c21670e625c172116a2f621536a30995ae6059f439c0f89cf` |
| `retire-legacy-sandbox-paths-normal-smoke.md` | `53427c1dea8b5e4bc8c2611cb398589bb0865f16fc78f448bae34932f1a64d5e` |

## 6. 实际执行的只读核对命令

工作目录为仓库根。主要命令如下，未执行报告中记载的测试或运行命令：

```sh
pwd
git status --short
printenv CODEX_THREAD_ID
git rev-parse HEAD
git diff ed45255626df4e6a8614f2c54254c50a6cc64e40 --stat
git show ed45255626df4e6a8614f2c54254c50a6cc64e40:.codex/config.toml
```

使用 `git diff <基线> -- <文件列表>` 分批读取上述 11 个变更文件；使用 `cat`、`sed -n` 读取必读规划、规格、测试断言和指定证据。使用 `rg -n` 检索当前 `product/`、`scripts/`、`.codex/`、`.agents/` 内的旧绕过参数、旧函数及调用点。

实际执行的清单核对命令包括：

```sh
shasum -a 256 reviews/development/retire-legacy-sandbox-paths/*
shasum -a 256 -c reviews/development/retire-legacy-sandbox-paths/source-sha256.txt | tail -5
git ls-files -z AGENTS.md .codex .agents product scripts tests evals/fixtures docs/development pyproject.toml | xargs -0 shasum -a 256 | LC_ALL=C sort -k2 | shasum -a 256
```

另执行多段 `python3 -B - <<'PY'` 内存解析命令，仅使用标准库 `json`、`hashlib`、`pathlib`、`shlex`、`tomllib`；其中一次 `subprocess.check_output` 仅调用上述 `git show`。这些命令没有导入或执行项目模块，没有写文件，完成了：

- 177 文件逐项 hash 比较及 83 文件 before/after 比较；
- Trace 的 121 个已列明产物 hash 比较；
- invocation、process-result、proof、Eval 和 Hook/dispatch 内部 hash 重算；
- 三个角色的 input、prompt、manifest、output、Agent、Schema、Skill 绑定比较；
- 原始事件成功读取输出与文件内容比较；
- CIO → Risk、Specialist → CIO、MCP → Trace、decision/Trace → Eval 的已有 hash 衔接比较；
- 仓库日志与指定临时目录原件比较，以及根 TOML 基线语义对照。

canonical hash 使用当前 `hashing.py` 声明的规则：UTF-8、`ensure_ascii=False`、键排序、紧凑 JSON 分隔符。全程未调用项目校验器、测试入口或 Gate。

## 7. 阻断项、非阻断项与提交建议

**阻断项：无。无需新增运行或补测。**

非阻断项及保证边界：

1. 全进程源码强制只读仍为 `UNVERIFIED`。原生 argv、Agent 配置和前后 hash 均不能替代操作系统层的写入阻止证明。Hook 事件的 `permission_mode="bypassPermissions"` 也不单独用于推断原生沙箱已关闭或隔离已验证。
2. 原始 JSONL 的两个 `error` 类型记录内容是保留的 Hook trust 提示；本次仍有完整生命周期及合法终态，不能只按事件类型将其判为运行失败。
3. proof 采用 `ephemeral_lifecycle_hooks`，没有独立原始 transcript；Specialist 的 Agent/Skill 绑定依赖已锁定配置、生命周期及 MCP 血缘。本报告没有扩大为逐条隐藏工具行为或全进程隔离证明。
4. 接缝报告正文保留 Smoke 前的 `PENDING` 历史状态，页首已指向后续 Smoke 记录。当前 Task 3.2 的依据是本次新 run 的原始证据，不能把旧正文时间点与当前状态混同。
5. 原有 Risk 硬约束、研究工具只读业务边界、学习面仅产出提案及人工晋升要求未被本次差异修改。本次没有增加主观投资规则、生产写入接口或券商能力，也未执行投资决策或晋升操作。
6. 当前没有本 Change 的最终人工完成批准；这是 Task 4.2 待办，不是 Task 4.1 技术失败。单运行 `RELEASE_READY` 不代表候选晋升成功。

旧 normal、历史 preflight、Replay 和 Ablation 只能证明其各自旧版本与场景。本评审没有使用它们证明新 launcher/根指令实际加载，也没有把它们重新认证为当前候选晋升证据。此次启动及加载验收以本报告绑定的新 normal run 为依据；现有聚焦日志只证明所列接缝，不替代全套确定性测试或新 Gate。

**可以提交 Task 4.2 人工完成批准。** 主线程可保存本报告并重算其文件 hash，将其与源码清单及两份实施报告关联，等待明确人工批准。批准前不勾选 Task 4.2、不归档、不提交或推送；候选继续 `NOT_PROMOTABLE`，隔离继续 `UNVERIFIED`。
