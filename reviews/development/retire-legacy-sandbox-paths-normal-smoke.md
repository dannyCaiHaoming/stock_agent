# retire-legacy-sandbox-paths：授权宿主 normal Smoke

## 结果

- 2026-09-09，依据用户“允许通过现有宿主 launcher 执行一次 normal Smoke；如需宿主执行权限，发起授权请求”的明确授权执行。
- 宿主执行权限请求获准；只启动一次既有脚本，没有重试、改配置、增加沙箱或新增探针。
- 结果 **PASS**，终态 `SAFE_NO_TRADE`，`failed_stage=null`、`failure_code=null`。
- 内层执行耗时 `592.297` 秒，launcher 与宿主脚本退出码均为 0；通过依据包括底层事件、Trace、Risk、Eval 和完整产物，不仅是退出码。
- Task 3.2 完成。独立 Reviewer 和最终人工批准仍待完成；未归档、提交或推送。

实际命令：

```sh
bash /Users/caihaoming/Documents/stock_agent/scripts/run-product-smoke.sh /private/tmp/stock-agent-retire-normal.lar8XL
```

执行时工作目录为仓库根；内层 cwd 为 `product/`。代理适配仅由现有脚本执行，代理查询和本机状态留在外置目录，不复制到仓库。

## 运行与源码绑定

- run_id：`host-normal-5f21e995-d4cb-426f-b3d3-488b161c455b`。
- Run 目录：`/private/tmp/stock-agent-retire-normal.lar8XL/run`。
- 模型：`gpt-5.6-terra`；Trace 记录 CIO 主会话与两个独立 Specialist 会话，共 3 个逻辑 LLM 角色执行；“一次 Smoke”不等于只有一次模型请求。
- 完整执行证明：`events/codex/specialist-execution-proof.json`，proof_hash 为 `a14937edf64b378b24103b051ad6174b3b98781d7159be5c1c08ab2d20e027d0`。
- 既有源码清单 `reviews/development/retire-legacy-sandbox-paths/source-sha256.txt` 的 177 个文件重验全部匹配；清单 hash 保持 `dd57caa2eb1eb162d7004640f745aab554bc8626080d416d9437ccdfcf2b8d3d`，范围定义见接缝验证记录。
- launcher 的产品完整性前后检查同样为 unchanged，产品快照为 `f836d67fe2a75a9b6e2e0fa23a969c6c052f19839f19be15b69583137fdcefcd`；它与上述较广源码清单范围不同，不能混为同一个 hash。

## 底层证据核对

| 检查 | 实际证据 | 结果 |
| --- | --- | --- |
| 原生沙箱 | environment-manifest 的实际 argv 包含 `--sandbox workspace-write`、`--ask-for-approval never`；没有 `--dangerously-bypass-approvals-and-sandbox` 或旧 preflight 模式 | PASS |
| 根指令实际读取 | JSONL `item_3` 的成功命令输出字节 SHA-256 为 `6e25a68e1a16b87641ba1af1eb753ed46917d0fe2474627fb7ea3c37bcd695a9`，与当前根 AGENTS.md 相同 | PASS |
| 产品规则与 Skill | `item_4` 成功读取产品规则；`item_5` 的 Skill 输出字节 hash 为 `74f8cd9e37862cb43e207dd9fadcf7b411f93949d59770e711bf7011814a369c`，与当前 portfolio-council Skill 相同 | PASS |
| 独立 Specialist / Hook | Start/Stop Hook 事件齐全，Analyst session `01a08695-e6ba-70c3-ad23-d1efcc006e26`，Skeptic session `01a08696-5faf-7a13-b890-9863475e572e`；两次 Start 均先于完成事件，dispatch 证明保留 | PASS |
| CIO | 父 session `01a08694-c2bc-77e3-9c56-5d368745580a`；结构化报告之后读取 CIO input/prompt/schema，Trace 的 runtime_cio 状态 COMPLETED 且有独立 invocation/input/output hash | PASS |
| MCP | Trace 有 Analyst Evidence query、math calculation、Skeptic Evidence query 三条只读工具结果与输入输出 hash | PASS |
| PIT / Evidence | Gate 截止 `2026-01-31T23:59:59Z`，5 个允许 Evidence ID；报告/决策引用经既有完成校验，未发现悬空引用；本次不替代 future fixture 测试 | PASS |
| Risk | risk_lineage attempt 1，`deterministic_risk_engine` 实际执行 FINAL 校验，APPROVED，原始和最终 action 均为 NO_TRADE；不是跳过 Risk，也不是本次验证了 veto 场景 | PASS |
| 完整终态 | decision.json、report.md、decision_trace.json、eval/result.json 均生成，terminal_state=SAFE_NO_TRADE | PASS |
| Eval | eval/result.json PASSED，normal_full_chain、actual_council_risk_passage、trace_lineage 等现有检查通过；eval_hash=`6ee3a513233d35dfe383ff0a856c2001ea056c5b6e3208dd7db29a4ac89e8254` | PASS |

## 原始文件 SHA-256

以下路径均相对上述 Run 目录；SHA-256 为文件字节 hash，与 JSON 内部 canonical hash 不混用。

| 文件 | SHA-256 |
| --- | --- |
| decision.json | `c6036cef39d1c709ebd75fb3aad8cf475b4155a16b69d8ac1f8b7fb4f29fdab5` |
| report.md | `252d32e13480f849c02e5b59ea4db61444e69951f528a824d43c4bcf58adb25e` |
| decision_trace.json | `58a11e031d4e4d6c4f0fa72bf9053f5026dd55bd8cffeb5453beff4dc186e627` |
| eval/result.json | `8ca1b97950ba0c5e51ceedd4c4dc3d703336c984c7a43533cb9ad581cc7d4de6` |
| invocation/process-result.json | `58570db93314f6a8a3e77f8a1b68a9c0121198ae68203898290ddd293989de9b` |
| invocation/environment-manifest.json | `ed1026186f7db4eaf31b3fef906215a05c24f5693bf3dde7fe28a4d1aad1d313` |
| invocation/codex-events.jsonl | `9ce02891165aa1be5008198afe88f339b7836c2e92d292b6345a238117b4d5e7` |
| invocation/subagent-events.jsonl | `0bc5bbd2ae4b18b0dce8c09fb5f2615988a3c131ee1b0ef87fb4197622ddd150` |
| invocation/subagent-dispatches.jsonl | `4dd4d2bae7c8139dd1189bb4ba137ee8bff4275f7ef9f4ccde2b0b9570d94ba6` |

## 非阻断日志与保证边界

原始 stderr 保留模型列表刷新超时、插件图标路径警告、ephemeral 父 transcript 路径警告。它们没有阻止本次完整终态，不据此扩展诊断或修改配置。既有 Hook trust 参数保留，与已移除的 approvals/sandbox 绕过参数不同。

本次只调用宿主脚本；其中既有 launcher continuation 执行 execution-proof、Risk finalization、Runtime Eval，脚本也按既有设计调用 check-run（含单运行产物检查）。这是 normal Smoke 的组成部分，不是另外启动完整 Release Gate，也未启动第二个 Council、Execution Replay、Regression、Calibration、Ablation 或 Promotion。

`RELEASE_READY` 是本次 check-run 对单运行包的分类，不代表 Change 已获独立评审、候选 Promotion PASS 或全进程隔离已验证。**全进程源码强制只读继续 UNVERIFIED**；事后 hash 一致不能代替预防性权限保证。
