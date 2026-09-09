# 独立差异复核补充记录（R1/R2 关闭）

Reviewer：Dalton，Agent ID `01a0862d-edd7-7961-aa65-574d99f8ea6f`。
以下正文由主线程原样保存 Reviewer 回传结论。此前 FAIL 记录保留，不覆盖历史判断；保存本文件及批准记录不属于下述评审快照。

CHANGE_REVIEW: PASS  
CANDIDATE_PROMOTION: NOT_PROMOTABLE  
ISOLATION: UNVERIFIED

本次仅复核此前 R1/R2 的关闭，两个阻断均已消除；其他已确认项目沿用原评审结论。未执行测试、模型、Replay、Regression、Gate、沙箱或探针，未编辑任何文件。

### R1：关闭

对应“资源发现与实际加载必须分别验证”及 Task 4.5、5.2。

新 normal：`host-normal-9fb6a10a-66f7-4038-bb1b-b434c455ce73`，模型 `gpt-5.6-terra`。

独立读取原始 JSONL，确认以下事件序号为**零基索引**：

| 序号 | 实际读取 | 核对结果 |
|---|---|---|
| 6 | 根 `AGENTS.md` | 独立 `cat`，退出码 0，完整输出与当前文件一致 |
| 8 | `product/AGENTS.md` | 独立 `cat`，退出码 0，完整输出与当前文件一致 |
| 10 | `portfolio-council/SKILL.md` | 独立 `cat`，退出码 0，完整输出与当前文件一致 |

三个事件的 canonical hash 分别为：

```text
6  ef5b88c52c20be0ee489c12c8cc737d3960801f4a77a7938489db1b2075b4069
8  789586dbc182a9749ee886ebbbdd90642b947711cbbf13a63df183fa98e756c3
10 89c8d012d1ecd3e8677349f4e64c97846aaf2be461053c7bed6216ec16febd7e
```

已核对 invocation 自身 hash、environment 文件 hash、Prompt hash、完整事件流 hash、run_id、session、命令、cwd、路径及 AGENTS 版本绑定，均一致。保存的 `resource_loads.agents_md` 与原始读取事件对应。

源码差异确认：`_completion_checks` 现在重新读取底层事件和 invocation，重建 AGENTS 加载证明，再与保存证明比较。既有测试原始记录确认：删除读取事件、保留正面证明摘要后，完成检查返回 `AGENTS_LOAD_PROOF_MISSING`；缺失、失败、截断、错误路径、重复、顺序及版本/调用绑定漂移均有负向覆盖。此次未重新调用完成检查或测试函数。

新运行 `completion_checks.agents_md_loaded=true`，launcher 为 `PASSED`、`failure_code=null`；存在 Specialist、CIO、确定性 Risk 血缘及 `SAFE_NO_TRADE` 终态，既有 Eval 为 `PASSED`。运行产品源码清单与当前文件无漂移。

### R2：关闭

对应统一启动契约、运行手册及 Task 2.1、5.1。

手册现在明确使用：

```text
python3 <repository-root>/scripts/council-dev.py prepare-execution-replay
```

并说明该入口创建 `host-replay-source.json`，随后由宿主 `--prepared-run` 按 manifest 选择冻结 workspace。与已确认的 `council-dev.py` 准备后处理一致。

治理测试已删除两个过时文本断言，改查上述准备入口、来源绑定和宿主执行方式。原始 stderr 确认该测试通过；整个限定集合为 **25 tests / OK**，退出码 0；OpenSpec strict 原始输出为 valid，退出码 0。

测试前后 162 文件映射一致，hash 为：

`e5d24cc40c44fdf74dbbb7f15eb76d860a94307dcd12aa8d448665bd495c0f9f`

与本次取证状态比较，测试快照覆盖范围内仅 `tasks.md` 变化；报告属于后续整理。未发现实现、测试或配置在该测试快照后变化，不将测试快照当作后续全工作区快照。

### 完整源码快照标识

取证时间：`2026-09-09T13:10:59.679713+00:00`。

- HEAD：`b4d15cc138f14b4db086a93ea32a2ca483d54fc2`
- 文件数：**17,845**
- 完整清单 hash：`a5d6295eaf570902349e7b79070827f5eb0c34af0c3ed9f26c48ac7f8911f9cf`
- 口径：Git tracked + nonignored untracked regular files；相对路径映射到文件字节 SHA-256，再以 `sort_keys=True, ensure_ascii=True, separators=(',', ':')` 序列化计算 SHA-256。
- 快照仅在内存计算，未写文件。包含历史非忽略证据文件，但未阅读其全部正文；主线程此后保存报告或更新任务会改变该清单 hash。

新 normal 的产品完整性快照为：

`116d3c21bc4e1f6bde19b02ce59152700549344872489587c5b750ba80bb473a`

其 invocation canonical hash 为：

`7b702e266a54e864a591e7cad34bc9d64d8eb0bec4d2a4cc27bce4beab6ce1d1`

### 已读取证据及完整 hash

以下均为**文件字节 SHA-256**。

测试证据根：`/private/tmp/stock-agent-r1-r2-dfvu_2gk`

| 相对路径 | SHA-256 |
|---|---|
| execution.json | `ccdb0dcf4a867d815d10f2d077c401a47dd71470ea61a94cd86851dfacc3259f` |
| 0-stderr.log | `0dec70df2bc5eb73ea63c59dfacb9046f18239c658dc0720ec2e14fac89597ec` |
| 1-stdout.log | `2b735a5260fec7aa1f942afb9b53ac54304545152f029893dd23a31bba670e61` |
| 0-stdout.log、1-stderr.log（均为空） | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

新运行证据根：

`/private/var/folders/tn/x1hbkfy17sx0w1lb8kjzzr340000gn/T/stock-agent-product-smoke.uGjvNB/run`

| 相对路径 | SHA-256 |
|---|---|
| run_manifest.json | `ba56dc8e20ffb53d0e6cbb8b76ff0779f0a4d73a6273cbb703c0a2d87bab7d03` |
| invocation/invocation-manifest.json | `54933751e5ee0ecf8f0a6bb9814547530737ffa13b90726a3ea3880eda04d9a5` |
| invocation/environment-manifest.json | `8cff46eb4b6cacaefd2be6fc445d7cf9eecb68d7ab8239975cc947d990411640` |
| invocation/prompt.txt | `840224893348d1cf96222c198fd7babf142709936487ff2887bfac50e0d57095` |
| invocation/codex-events.jsonl | `d0edaa4c13f9987c676528772dfc93cc937bf5d3ee108e697723e25e7a3a45c7` |
| invocation/process-result.json | `4c25165b4023a5e4aca6fd862156bb96c3ab889d346b0a3d9b87aa0d58db158b` |
| events/codex/specialist-execution-proof.json | `35155c73e3db948b7ecdda8a0998d134e80f6ec0f5e4227c251225deecd42614` |
| invocation/subagent-events.jsonl | `23420ea7a71b767c216a9e8b4b515994dee02601eac9e45379fc0dd7d7beb461` |
| invocation/subagent-dispatches.jsonl | `2d078cf012fb079e7ac710f2a8528b1b7ca4b5ce83aa4015ab127d7150c69d3d` |
| events/mcp/events.jsonl | `5c4f57f65ab949e4a8388f9060fb6d731e8b204009d9cbb0c7daf94f9bf80b5a` |
| decision.json | `2fb832510725fd0f15cb9fd5effea529632c49d0e074f75010b33b86c5cfa2d6` |
| report.md | `d5782dcb82d6b2340daea8f082bb5f7b5bd3ecf16ca7554ed2d90dd9562e248f` |
| decision_trace.json | `bddcfdb8c34f98785de0b9f903ad3ca7a87025c5c3c2076008f1f4105815842f` |
| eval/result.json | `9ebee9175bd897176ea1fcd8b8a865be3318813889ca0cf5c99a53b56364a381` |

仓库内本次修复依据：

| 路径 | SHA-256 |
|---|---|
| reviews/development/streamline-codex-development-environment-independent-review.md | `7c359578637fa18eadd4c4fbea3bc9facba131cf30a88eb69f8971544b9e7880` |
| reviews/development/streamline-codex-development-environment-r1-r2-fix.md | `a4ac86da1b1c4221accd10167c49cb68757f5cb7949f648f6a556219a6159830` |
| product/runtime/execution_proof.py | `60f4606c710275ef430aa9fcb74cb8667248fbbd04ce4412eb639ebf0f7b9833` |
| product/runtime/nested_codex.py | `630eeae27bb509e862872008f185c5f7248d1450d9a0ac769ae9fa54c7f77dfd` |
| product/runtime/smoke_prompt.py | `d10ec2534eae7a23565f652d57427a5fb18c8eff6b3c2cb336395fcca590327d` |
| reviews/runtime/runtime-replay-eval-runbook.md | `e0fd5411c693fbf6dd340f7395582879383f95a1e650301e4856d372b9fe7a3a` |
| tests/test_agents_instruction_proof.py | `9236e35c433dde2335324d614be3c65c9a4dc712a4229d8c7a970a6b1e0cb5c5` |
| tests/test_governance.py | `386f7b3b919b26e2ab6864671b42aaa6e1ebb3a76215522c93a87499b50addee` |
| tests/test_nested_codex_launcher.py | `d7e6dca1e5d3a70cb0a0a9031fbabe8aacf28e92df5b91fd9d9fc982424fe983` |

### 适用限制

旧 Replay/Regression 接缝继续按原证据范围复用：相关宿主脚本、transport、Replay/Capsule 实现及 Regression runner 与此前快照一致。本次没有重新评审其全部功能，也没有将旧配置等价性或缓存证据提升为新候选晋升证明。

本补充记录关闭 R1/R2，并将限定 Change 评审结论更新为 **PASS**。Task 6.3 的最终人工批准仍是独立步骤。全进程源码强制只读继续 **UNVERIFIED**，不作为本次失败项；本报告不授权归档、提交、推送或生产晋升。

