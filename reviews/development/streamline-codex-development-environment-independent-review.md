# 独立差异复核记录

Reviewer：Dalton，Agent ID `01a0862d-edd7-7961-aa65-574d99f8ea6f`。
本文件由主线程原样保存 Reviewer 回传正文；评审时快照见下文，保存该记录本身不属于被评审快照。

CHANGE_REVIEW: FAIL  
CANDIDATE_PROMOTION: NOT_PROMOTABLE  
ISOLATION: UNVERIFIED

评审对象：`streamline-codex-development-environment`，Task 6.2。  
评审日期：2026-09-09。本 Reviewer 未参与实现；仅复核当前差异与指定证据，未修改文件、执行测试或启动任何运行/诊断链路。以下记录可直接保存。

### 阻断项

**R1 — AGENTS 实际加载链尚未证明，当前完成检查也未覆盖该项。**

对应规格：[资源发现与实际加载必须分别验证，尤其“完整正常 Smoke”场景](/Users/caihaoming/Documents/stock_agent/openspec/changes/streamline-codex-development-environment/specs/codex-development-environment/spec.md:62)，涉及 Task 4.5、5.2。

- [nested_codex.py:117](/Users/caihaoming/Documents/stock_agent/product/runtime/nested_codex.py:117) 对根/产品 AGENTS 只计算文件 hash。
- [完成检查](/Users/caihaoming/Documents/stock_agent/product/runtime/nested_codex.py:167)检查 Skill、Specialist、MCP 等证明，没有检查 AGENTS 的实际读取/注入来源。
- 给定 normal 的 53 条、Replay 的 32 条原始 Codex 事件中，均没有 AGENTS 读取事件。事件中出现 `product/AGENTS.md` 的位置是读取 run manifest 后显示的完整性 hash 清单。
- 两次运行的 `preflight_binding` 均为 `null`；`specialist-execution-proof.json.resource_loads` 均只有 `agents`、`mcp`、`portfolio_council_skill`。其中 `agents` 指 Specialist 配置，不是 AGENTS.md。
- 11 项接缝证据证明了 Skill 精确读取、部分执行证明拒绝路径及 Regression 接缝，不能补足 AGENTS 加载链。

因此，现有证据不能支持验收记录将“实际加载”整体关闭。这里的结论是**未证明 AGENTS 已按该次运行加载**，不是断言 Codex 实际没有加载它。

所缺的是与对应 invocation、路径及文件 hash 绑定的真实读取或注入证据，以及缺少该证明时完成判定的处理依据。此次仅报告缺口，不执行补证；该问题与获批排除的全进程隔离保证无关。

**R2 — Execution Replay 手册与当前宿主入口不匹配，相关治理测试也未同步。**

对应规格：“执行入口必须复用统一启动契约”，Design D1/D2 及迁移说明，Task 2.1、3.1、5.1。

[运行手册第 48 行](/Users/caihaoming/Documents/stock_agent/reviews/runtime/runtime-replay-eval-runbook.md:48)仍要求：

`python3 -m product.runtime.cli prepare-execution-replay ...`

随后第 54 行要求经宿主 `--prepared-run` 执行。但 `host-replay-source.json` 只有 [council-dev.py:288](/Users/caihaoming/Documents/stock_agent/scripts/council-dev.py:288) 的准备后处理会创建；宿主转发器在缺少该文件时明确返回 `REPLAY_HOST_SOURCE_BINDING_MISSING`。因此，照当前手册执行会在模型前被拒绝。给定成功 Replay 使用了正确来源绑定，不能证明这条手册命令可用。

另外，[test_governance.py:42](/Users/caihaoming/Documents/stock_agent/tests/test_governance.py:42)仍断言手册包含：

- `python3 -m product.runtime.cli nested-codex-smoke`
- ``冻结 workspace 作为 `--repo` ``

当前手册均不包含这些字符串。这是静态源码可确认的不一致，**本次没有执行该测试**。11 项补测未包含它，历史治理测试通过记录不能直接覆盖当前文档状态。

### 已确认的有效证据

- 当前入口会拒绝旧 `--review`、`review-run`、`review-probe`、`nested-codex-probe`；自检采用确定性命令白名单。历史隔离实现保留，默认宿主路径不调用它。
- normal 与 Replay 均存在两个独立 Specialist 的 Start/Stop；两个 Start 早于任一 Stop，Stop 中的结构化输出 hash 与保存报告一致。Skill 各有一次完整内容匹配的成功读取事件；两次运行各有三条研究 MCP 调用记录。
- 两次运行均有 CIO、确定性 Risk 血缘及 `SAFE_NO_TRADE` 终态，既有 Eval、launcher 结果为 `PASSED`。normal 清单中的 83 个产品文件与当前文件无漂移。
- Replay 的 source/new manifest 绑定匹配；来源 Capsule 的 97 个对象及对应物化文件字节 hash 全部匹配。实际 transport 参数与冻结 launcher 命令相比，仅替换执行程序并增加一个 `--skip-git-repo-check`，保留 `workspace-write`、审批和 Hook 参数。
- comparison 所列九类配置 hash 一致，`result_hash` 重算一致。没有重新调用 Replay finalizer 或验证函数。
- 11 项测试的逐项 stderr 全部为 `ok`，最终 `Ran 11 tests … OK`、退出码 0。165 个源码/依赖文件的前后清单一致，也与当前文件一致。
- 当前差异未改动 Risk 判断算法、学习面写入边界或生产版本指针。研究 MCP 接口仍为 `query`/`calculate`；Risk 规则仍基于明确的会计、数学、数据质量和 mandate 约束。没有新增券商写入或自动生产晋升能力。
- 范围批准明确不构成完成批准或晋升批准；Task 6.3 仍待人工批准。本报告不授予晋升权限。

### 快照与证据标识

基准 HEAD：`b4d15cc138f14b4db086a93ea32a2ca483d54fc2`。

全仓库清单：`/private/tmp/stock-agent-close-seams-i98ft6pp/reviewer-source-snapshot.json`

- 文件数：17,842，口径为 Git tracked + nonignored untracked regular files，包含历史非忽略证据文件。
- 清单文件字节 SHA-256：`15cbc65b642e541519f79dfade6514a2d78ec5c9d970ae6dbaf1041247be0135`
- 清单 `snapshot_hash`：`9da44e761ad2cc743ace125e574daca6e50c2f555f1d3d7d1c771351158220ae`
- 重算口径：`files` 映射使用 `sort_keys=True, ensure_ascii=True, separators=(',', ':')` 序列化后计算 SHA-256。
- 清单与当前文件集合一致；复核开始和结束均未发现文件字节漂移。未逐一阅读全部历史文件正文。

以下均为文件字节 SHA-256；源码与规划的逐文件标识同时保存在上述完整清单中。

| 当前评审依据 | SHA-256 |
|---|---|
| scope-approval.md | `8b1194f130c6c53be475e41e6850acd73ca784ca04012f3cb65a86bc34a9c169` |
| acceptance.md | `04ddadd91414ce69eb73382b96756347776c76699435994bddb98250a66a9636` |
| scripts/council-dev.py | `8cbbd1abfae9b5ab89f465e973c2a4dcc1d865af83f921b9dd9d7fdb82a5db4c` |
| scripts/run-product-smoke.sh | `6fdc5bcc36d9a716252c584a0b537f17390059dab2bd1c3e6e322029e53d665f` |
| scripts/replay-codex-transport.py | `876e38211557823d7837757ff5f5e54c7fc52c56a70e5a686042d5b18df5d975` |
| product/runtime/nested_codex.py | `506db07f9c06a377a07b7ebe1738a3b906e02d9c9d521d92b381d0a0f245609e` |
| product/runtime/execution_proof.py | `c2f9a5845c25354f0c2a76dc7b9b69c598a963255a24f781c4a44d4f445b3928` |
| reviews/runtime/runtime-replay-eval-runbook.md | `ce72ad7100aef119e7696f98318b3b2c9b4533f92a73910cb69b1533ebd67495` |
| tests/test_governance.py | `e7a0487c9804fccf937a01aec815ec3ba3d67764e95b188b4388caa1806826f9` |

11 项接缝证据根：`/private/tmp/stock-agent-close-seams-i98ft6pp`

| 证据 | SHA-256 |
|---|---|
| execution.json | `c86db511e1536a9a8cc7270662fbc1a74e3512b5acd8e0f633be635d5d25f3b6` |
| stderr.log | `8cf536f19afc128b6172c13c19b6dca31b7210ba809f32e4ce6d92f7912493cd` |
| stdout.log | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| 外置执行驱动 stock-agent-close-seams-20260909.py | `7f59a3bde4c1c673068ce8c38d8b3ad52fa3f71ca1584f1027a312b6049fb686` |

接缝源码/依赖快照：`0f397f52a9e82228f83a7a534e128dc82d1c4a305adc956a428213fe8f950375`，165 文件，非全仓库或生产候选锁。

运行证据路径：

- N：`/private/var/folders/tn/x1hbkfy17sx0w1lb8kjzzr340000gn/T/stock-agent-product-smoke.ZFpS6a/run`
- R：`/private/tmp/stock-agent-execution-replay.diDwuI/run`

| 相对路径 | N：SHA-256 | R：SHA-256 |
|---|---|---|
| run_manifest.json | `25456c81d602b740dc8fd9689773106ec620f44efff8b12d8da794fad9519a64` | `0c1603f76850e541d341b08c7458c06e34020cf0c433707d3ef2c5f7c6601492` |
| invocation/environment-manifest.json | `c06b16c9f336a9a6bbe1a0d126716b81fde3ece4f9d838591181c13305682062` | `d30a7e6c6178b633752f8c775b2f2e59340d57188c9ab66d4f542c2c23794d36` |
| invocation/invocation-manifest.json | `95b503cd08810813f8b1e5073d05939b94ca6d0671be49c5aa9fe8e1a918232d` | `34bc559ed9e547a2a2f0fa5e2841ac2ddd59bd6ff55e6a25def7baab338f9e6f` |
| invocation/process-result.json | `202af361019db626410aabb9030e3ea4f200f64e92a84c3dc6fcb2f76b29bfbd` | `ce3c89f9b0e9be24e17dc66c1f44b7e2092d5824d9c935659d630f9ce4f6aa7c` |
| invocation/codex-events.jsonl | `9d64478a693299c1ef4e9fd34469833e3e608e670e3acb5bf43851226d97cc58` | `361b1d539eed1831887c323bf3fc655352fdb300af1a1a625803f26a4160005a` |
| invocation/subagent-events.jsonl | `a9d13023c2fa7b2d398b6d0ae82646553f88fe8360877c8c6ae967dd8f7b30ae` | `534c8e4e409d416a62784566d67c171fa6675fc33ad59881554215b654c316cc` |
| invocation/subagent-dispatches.jsonl | `40fa1751df606d728a87301675572c3c0b99442cee614164ea1d31edbe437e16` | `2678a1cd39e201e6c39d775a8734100f663bb1e0c6609345588a41c8103199a3` |
| events/mcp/events.jsonl | `cfea64c2f3a2c9949fb4c462c5a97140cab45213049734905b9de8cca501708c` | `f772baa380b2e62e08a7efd6f94223f37b6e71033f4c8ed53401b9cdc6964961` |
| events/codex/specialist-execution-proof.json | `390e686322c762776a3b545bb97be23e59a59061ab62d52839147c2cc8fe0d20` | `f60e8fe6ab17bcf412fdeb0762a9e859c947c93ecc9b6d56c2578dc20f0bc56e` |
| invocation/prompt.txt | `7d04dc595f01be00b836ba310475a999fd88d475ce1270f64e0b57053734eb79` | `cfeaddc6a11d4ff702a7f45b6ea4260ecd3208ab6bf5a3dc8e6bcc189e7d65df` |
| invocation/final-message.json | `21a1cab9d73e30fea4dc43cbde1c53d888b9ee490114454a03c48d17ad11683f` | `024c70cb7413f1af22f6a140559ad8c1ab07f527d49553838fa2f02b733df4df` |
| invocation/codex-stderr.log | `bc84624917642bb5cbc6b23ab822fc09e0f73e91ccd21f7c77ca1800e29bd6a2` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| decision.json | `4331c92985b9d4d4f80789817090e1fad30f888c9e4720e227aa20d0ad50a2fd` | `926476fe69acdeff673a1e1cddaeda8e898fbe22774d3623d820b3bb8c92a8db` |
| report.md | `5bede7845b73f3c633f7ebd38e7edd7b536e95a0985859c2ba39f218c01fd825` | `4410d9e63e67ef2fe72c6228ea050d68c168786824cc148fdbca579460416a5b` |
| decision_trace.json | `7555cab1bbf4b73655c8f7e1d40c40042c2939d1023c739108b434f47e27508d` | `22a94b13c77d6539f3a6003f05b2851c93f1414f41bfd9b7a7823a4ff03b8a39` |
| eval/result.json | `c333240be6efce9c52b43594148769355ef97ba25c5f960f3f2bdbe0459e8371` | `019a14e69cd5a522d65664d54e91c8395927580022f8debff1b6d07ff2f09618` |

| 重放来源及比较证据 | SHA-256 |
|---|---|
| N/replay_capsule/manifest.json | `0907c457a9d03e7a4ce9f5ff17f7e1cba9f72d09968a04a22881c002354ebbab` |
| R/execution-replay.json | `81bbc604b126407cc8e425fab1484d5e890eda97611fd17e061610d7329d86e7` |
| R/host-replay-source.json | `0a820aeb17c805576a50048b435ebbe48fdb8e46f71e7081700516aa793a305b` |
| R/invocation/host-transport.json | `db0f7de51c046d4a4c8757e0720783f75c4376540079c06d700e7c9dba17ca94` |
| R/../comparison/result.json | `4a11e0758081237c8271784baf309f9728667a6d079647ffbba3ce7f91b56ef1` |
| R/../comparison/report.md | `d45401ac0b97b7d8adeb9347ea32b96da540322474299c3298d9527dfa4f365c` |

### 适用限制与停止位置

本结论仅适用于上述快照及当前 Change。历史运行的功能证据仍然有效，但不自动证明全部新增规格已满足，也不构成新候选完整晋升证据。

全进程源码强制只读按人工批准保留 **UNVERIFIED**，不作为本次失败项，不要求额外沙箱。文件 hash 一致仅证明取证时字节一致。

评审已完成并停止。R1、R2 尚未消除，当前不能给出 `CHANGE_REVIEW PASS`；未补跑、未修复、未写报告文件、未归档提交推送。
