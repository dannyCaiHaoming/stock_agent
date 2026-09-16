# expand-free-data-holding-research 独立复核记录

## 结论

`CHANGE_REVIEW: PASS`

Task 8.4 通过。此前唯一审计缺口——当前源码快照标识缺失——已经补齐；本复核绑定到下述源码快照与证据包。该结论不代表 Promotion PASS、完整 Portfolio Council、生产批准或投资建议通过。

## 源码快照绑定

- Git HEAD：`d738110e712ee94de38488478556e7400453a948`
- 完整 `git status --porcelain=v1 -z --untracked-files=all` SHA-256：`0084aa68bc368831ddcc6b731259d38967b151c0e719526b703c6a99ad2754e1`
- status 条目：307；明确为极脏工作树，只用于现场绑定
- 聚焦范围：64 个状态条目，覆盖本 Change 的 Agent、Skill、runtime、schema、MCP 接缝、相关 tests、scripts、OpenSpec、验证记录及多维产品文档
- 聚焦 diff SHA-256：`f713751639c8500f15bd18d1db7aac630d835e731b1e3a99ae5b9de1eb97008c`
- 产品受保护源码 `integrity_snapshot`：`a47b67967507265af14585d122857fc89f3924c5fdd5fbaf09543ece821f46fa`（138 files）

v32/v34 报告中的 Agent、Skill content hash 与复核时源码一致，两个批次均记录 `source_integrity_unchanged=true`。验证记录中的受影响测试计数已经统一为 98/98；Reviewer 未复跑测试或模型，该计数仅作为主开发提交的 Task 8.3 证据。

## 证据包标识

目录级标识按排序后的相对路径、文件完整 SHA-256 形成：

- v32 完整批次：157 个文件，`cf14f6269f5a1831bc339e7dae0c89adb9b66e1bddaefb7e8ff45b9aa3b1a693`
- v34 宏观定点批次：110 个文件，`e34ea9f42fcd300e008adcb744e4bc1c22a4ffb8f9d9ef1e4ce55be8270e1d11`

| 证据 | SHA-256 |
|---|---|
| v32 `run_manifest.json` | `4d2dec18b153e326d75ef19651e87fb8929d9f84489ba1094b318639f6475efd` |
| v32 `research/dispatch-index.json` | `895f679e6c74884c437cb0cda143450a38cf82c4965bbd06b086f8e40bceb2e3` |
| v32 `invocation/subagent-events.jsonl` | `9c7b212ff28faa4fde2169e79294337a2ddb8f9bf4805f626c77f7eca269f101` |
| v32 `invocation/subagent-dispatches.jsonl` | `2ea503aafaf79f57f1ab9a13187874b8a9797388f45262129f30df6eef98a54f` |
| v32 Gate | `5c98c9c95bc88b22bbaf2353afc4a93383b139cd7832d3bc9d713d393facf6a7` |
| v32 bundle | `478c9a2e4a282612620dc956c9d286a250414f3196d400c73158e1583365c396` |
| v32 execution proof | `049ef84c474fe055911b20238a5281a45da05635f3a3eddbff405600396ee678` |
| v32 consumption proof | `9a288259c3af03af9b84b7fdc8f5e14da7723db8ce05044c90fe0ef30df9d1e5` |
| v34 `run_manifest.json` | `eba1ad64e596e331b8fe306a8ba882bc95e3f4fd7d3d7efee25d0279dd09e548` |
| v34 `research/dispatch-index.json` | `30ea1d7bba056d250165e91b2088290fd8d06d237784fd11881b05489572e94e` |
| v34 Gate | `7f19a32f224a572958b7ee39319dfedebf4e1734ea6b97c7c63134b1a84c3dd6` |
| v34 宏观报告 | `15193f5b1c23d63edc55b0ba8f80718e061e3d4358206fac99fec00689f9c823` |
| v34 task proof | `a4b153221055006cd983d497d0ff5ed5dcd081b3b2089e7300c1835ea2dfe577` |
| v34 subagent events | `4f6ff8a2feb3a33e31133197bed1aebe1207ad1a23f6b2543c5556f35a3d50b6` |
| v34 dispatch events | `a7cbcbc029136fcecddd87188a1f95d99298b210a2ff71a26bc956f5d7fd3a05` |

## Design 第 5 节逐维复核

| 维度 | 独立结论 |
|---|---|
| 技术结构 | 通过。三股均解释 20/60 日趋势、相对 SPY 强弱、波动、回撤和量价关系，并给出推翻条件；252 日历史不足被明确限制，未制造长周期信号。 |
| 基本面/事件 | 通过。ALB、MRVL、WOLF 均覆盖经营驱动、盈利与现金流口径、估值依赖假设、关键事件与未知项；未把经营现金流冒充自由现金流，资料不足时未强造 P/E、目标价或生存期限。 |
| 行业比较 | 通过。ALB–DD、MRVL–ALAB、WOLF–PLAB 使用已冻结双方事实，说明相对位置、行业与公司因素、业务模式及期间限制；未物化同行和未授权计算被保留为缺口，没有机械排名。 |
| 宏观市场 | 通过，以 v34 关闭 Task 5.3。报告使用 10 年期美债收益率、CPI、失业率及 SPY 20/60 日市场状态，区分 WOLF 与 ALB 的融资敏感性，保留 MRVL 公司特定传导缺口，并给出显式假设及反向观察条件。 |
| 研报 | 仅受限分支完成，不是研究能力 PASS。实际执行 8 次搜索和 9 次正文尝试；正文均因 `PUBLIC_RESEARCH_CONTENT_API_KEY_REQUIRED` 处于 `BLOCKED_CONFIGURATION`，没有 `BODY_VERIFIED` 文档。正式报告未伪称读过正文，也未伪造作者依据、分歧、research relationship 或利益披露。 |
| 所有权 | 仅 `SOURCE_LIMITED` 分支成立。ALB、MRVL、WOLF 的 SEC 所有权请求均为 `SEC_ENDPOINT_REJECTED`，无可用所有权 Evidence；报告未声称机构变化、内部人方向或“聪明钱”流入。 |
| 期权/资金 | 仅 `SOURCE_LIMITED` 分支成立。三股 Yahoo 期权请求均为 `YAHOO_HTTP_401`，快照为零 records、零 evidence；没有伪造期限结构、持仓量变化、历史分位或资金方向。 |

## 执行、引用与安全边界

v32 完整批次有 19 次 `SubagentStart`、19 次 `SubagentStop` 和 19 个 `SAVED`；19/19 报告通过结构和绑定，24 个证券/能力覆盖项齐全。报告中的 65 个唯一 Evidence 引用均位于对应任务白名单及 Gate 内；三份技术计算 artifact 共锁定 1,098 个底层 Evidence ID，没有悬空引用、缺失来源时间字段或 PIT 越界。consumption proof 为 `CONSUMABLE`，且 `downstream_models_started=[]`、`complete_portfolio_decision=false`。

v34 仅补证宏观 Task 5.3：模型为 `gpt-5.6-terra`，Agent/Skill 为 `runtime_market_catalyst` / `macro-market-analysis`，恰好一次 `ALLOW`、一次 Start 和一次带 `SAVED` 的 Stop。宏观报告的 9 个事实引用和 SPY 市场计算 lineage 闭合；task proof 明确为 `SINGLE_TASK_EVIDENCE`、`complete_holding_research_bundle=false`、`downstream_models_started=[]`。v34 没有冒充完整 bundle，也没有改写 v32。v33 没有 `SAVED` 输出并以 `MULTIDIMENSIONAL_TARGET_OUTPUT_INVALID` 失败，只作为 Stop Hook 根因和 fail-closed 证据。

安全边界符合本 Change：Specialist 为只读 sandbox、`approval_policy=never`；无通用 Web、App、券商、订单或账户写入权限；正式分析不继承研报准备阶段的搜索/正文权限；未启动 Skeptic、CIO、Risk 或其他下游模型；输出不包含组合动作、目标权重或订单，也未发现学习优化输出自动修改生产文件或版本指针。

## 最终任务状态

- Task 8.4：PASS
- Task 6.3：仍未完成，等待人工接受所有权 `SOURCE_LIMITED` 延期
- Task 7.3：仍未完成，等待人工接受期权 `SOURCE_LIMITED` 延期
- Task 8.5：仍未完成，需集中接受研报 `BLOCKED_CONFIGURATION`、所有权/期权受限清单及延期 TODO，并给予明确人工完成批准

Reviewer PASS 不是人工批准。当前 Change 尚不能归档、提交或推送。本次独立复核未运行测试、产品模型、网络、Gate、Regression、Replay、Calibration 或 Ablation，也未修改产品实现。
