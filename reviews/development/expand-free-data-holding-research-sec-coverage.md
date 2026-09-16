# SEC 数据覆盖调试记录

## 范围与结论

本记录属于 `expand-free-data-holding-research` 的 Task 6.3。第一段验证确认持仓中的 ALB、MRVL、WOLF 是否能通过 SEC 只读实现完成身份、recent submissions、companyfacts、最新公司披露及最新 Forms 3/4/5 原始 XML 获取和解析；后续 v37 定点补证验证 ownership Evidence 能真正通过 Gate，并执行一次 GPT-5.6 Terra 所有权研究样本。13F 机构持仓比较仍未实现。

结论：**SEC 数据接缝 3/3 PASS，Gate 3/3 PASS，ALB 所有权研究按受限分支完成。** 13 个初始网络请求均为 `fetched`，没有失败；每只股票均取得最新公司披露及一份可解析 Form 4，并各形成 1 条带完整 `source_id`、`as_of`、`retrieved_at`、`evidence_id` 的内部人交易 Evidence。v37 中三条 Evidence 均进入允许集合且没有 ownership 排除项；真实 Terra 报告正确保留单期、交易背景和 13F 缺口，不生成投资动作。

## 实际执行

外置运行目录：`/private/tmp/stock-agent-sec-coverage-20260915-v1`

输入：

- 确认 Handoff：`/private/tmp/stock-agent-portfolio-intake-clear.yXyy56/portfolio-handoff.json`
- Handoff hash：`84b42d952bfaaedb7d496de152f464b7be4c2667354eacf2d408049598853365`
- 来源配置：`/private/tmp/stock-agent-multidimensional-source-access-20260915.json`
- 来源配置 hash：`38a9662d0c6621f225ad11320ee1371b12a4dbe87a10322c80460038848d3dd5`
- 生效 SEC 配置 hash：`e77516eb62c4f730ff76aedd500a089117b0f2c650134121319bc7f483a6ef3b`
- 生效版本：`sec-readonly/0.3.1`、`sec-parser/0.2.0`、`sec-ownership-xml/1.1.0`
- 请求预算：30；实际请求：13。

执行命令由外置 `run-sec-coverage.py` 调用仓库现有 `SecClient`、`parse_submissions`、`parse_companyfacts`、`read_document`、`read_ownership_document` 和 `parse_ownership_document`。SEC User-Agent 只从运行时环境读取；产物仅记录其存在，不保存联系身份。

## 逐股覆盖

| 股票 | CIK | submissions | companyfacts | 最新公司披露 | 最新所有权披露 | 原始交易代码 | 结果 |
|---|---|---:|---:|---|---|---|---|
| ALB | `0000915913` | 1000 filings | 25463 included / 5778 excluded | 2026-08-05 Form 10-Q | 2026-09-04 Form 4，1 Evidence | `A` | PASS |
| MRVL | `0001835632` | 835 filings | 8423 included / 0 excluded | 2026-08-28 Form 10-Q | 2026-09-02 Form 4，1 Evidence | `S` | PASS |
| WOLF | `0000895419` | 1000 filings | 28469 included / 2180 excluded | 2026-08-20 Form 10-K | 2026-09-02 Form 4，1 Evidence | `A` | PASS |

ALB、WOLF 被排除的 companyfacts 均为 `SEC_PUBLICATION_NOT_VERIFIED`：相关历史 accession 不在本次 recent submissions 集合，系统按既有 fail-closed 规则隔离，不能把它们当成已验证历史事实。这不是传输或解析失败，也不代表完整历史已覆盖。MRVL 在本次响应中没有该类排除项。

`A` 只表示申报原值中的 acquired；它可能是授予、行权或其他取得，不能自动解释为公开市场买入。`S` 是申报 transaction code 原值，仍须结合价格、数量、持有变化、关系和脚注由所有权 Skill 解释，不能直接推断动机或资金方向。

## 产物与完整性

| 产物 | SHA-256 |
|---|---|
| `input-manifest.json` | `92813c5afebd4f0c09d99eb91667e44de0c3cc3c9d3267af722c05e956977c78` |
| `effective-sec-source-access.json` | `e77516eb62c4f730ff76aedd500a089117b0f2c650134121319bc7f483a6ef3b` |
| `request-events.json` | `59cfde52269ef0d78273a08b948dbee989981d3f3ba6cce54f54454ede6ae116` |
| `coverage-result.json` | `81228b2f7dee36ca72e08d59b10ee4781cda42564e5ff069658a5a2a64e74165` |

外置 cache 含 13 个 record 和 13 个按内容寻址的原始对象。请求事件中没有失败码，也没有保存 SEC 联系身份。

## v37 Gate 与真实所有权研究

外置数据目录：`/private/tmp/stock-agent-multidimensional-repair-20260915-v37-data`

外置研究目录：`/private/tmp/stock-agent-multidimensional-repair-20260915-v37-ownership-prepared`

运行 ID：`host-common-stock-sec-ownership-20260915-v37`。修复后的 `sec-ownership-xml/1.1.1` 将 `source_type` 绑定到获准供应方 `sec`，由 `kind=ownership` 和 `semantic_field=ownership_insider_transaction` 表达资料语义；Evidence Gate 只对 Forms 3/4/5 使用 90 天当前资料窗口，未知来源或未知表单仍 fail-closed。

v37 Gate 共有 5,131 条允许 Evidence、745 条排除 Evidence。其中 ownership 为 3 条，ALB、MRVL、WOLF 各 1 条；ownership 排除项为 0。Gate hash 为 `7bf83477c6046f5c5195537a3b74442bb63b3bac050047a83fa75ef31500504b`，ownership 摘要 hash 为 `685c4204f0e12547037ea030f3ce0c33b95af43f13c7cbe16ddec61ba42312b4`。

授权的单次专项研究使用现有定点入口运行 `dimension_research_14`，由 `runtime_market_catalyst` 加载 `ownership-disclosure` Skill，实际模型为 `gpt-5.6-terra`。ALB 报告状态为 `SOURCE_LIMITED / PARTIAL`：解释 2026-09-01 报告取得 1,476 股、Form 4 于 2026-09-04 被 SEC 接受、数量未经拆股调整，并明确 `A` 代码、0 美元申报价格和 footnote ID 不能证明公开市场买入、交易动机或整体内部人趋势。

该次运行只证明一个真实所有权研究样本；MRVL 与 WOLF 已证明数据和 Gate 可用，但没有消耗额外模型批次。13F 申报主体发现、两期机构变化，以及同一内部人的历史序列继续延期，不能宣称机构资金流或完整所有权研究覆盖。

| v37 产物 | SHA-256 |
|---|---|
| `run_manifest.json` | `2eb8b76f3fc185b8490af9e976ebda5fd10c6ac4a25996a670f11cd721569fb2` |
| `research/dispatch-index.json` | `197e4b4ca0b5f3e1a2468652a99e1d24e359ea626b862bd45fc4b43a895ad628` |
| `dimension-report.json` | `ec616be297bf916f5924b850936c766bbbbf9ab0a61725bf9a14fce5245cc5a1` |
| `dimension-report.md` | `b686abcfb6174839f0dea7e987a2c3d632dd7e50a99e422e92a50560290196e0` |
| `research/task-execution-proof.json` | `5440c455057d8b4eff7fd08b642005e2de0b6917fc66262f54b56eca5994e36e` |
| `invocation/codex-events.jsonl` | `45726e35835fb30c95c18b9e35e2a892c93ae7212da1d9fc2886bc2309b21846` |
| `invocation/subagent-events.jsonl` | `d46221880e2a795abc9a40abd13549b705d27d4a7782d98bc0647a871ae0b2d2` |
| `invocation/subagent-dispatches.jsonl` | `f999fb78ff505cb56111a449108c08579e39c2d9456a91394627dc949ec46220` |
| `invocation/prompt.txt` | `b075313280dd2cbef47f5c1a8bb2da30298c26e2f36650244f993a75cce5facc` |

`process-result.json` 记录 Codex 退出码 0、阶段 `PASSED`、未超时且源码完整性未变化。`task-execution-proof.json` 记录 `complete_holding_research_bundle=false`、`downstream_models_started=[]`，因此不会冒充完整多维研究包或下游决策。

源码快照：

- `product/mcp/live/sec.py`：`9ea5ac7e22c6c409da4043d1e9a3178ab2eedf206cf4fadcd06dc9466e72c0e9`
- `product/mcp/live/sec_client.py`：`297e114dfde734d5a5182e534b52ebd0e428696cc99e1dec00e3d3d9ab471760`
- `product/mcp/live/ownership.py`（v37）：`b5f3158ac5c95b3f1c5d478f39e05c543d85eb084968cce4cba5d2cde7f5a821`
- `product/mcp/live/collection.py`：`1b1f9df3c23f5dcf3c49dfd0621baf7a5feccfaadcc03f997bd80881431b14c5`
- `product/runtime/evidence_gate.py`（v37）：`96972f53740a596b63bf3f72dfb83e50fa2951797e31307a534aa0e7abb71c33`

## Task 6.3 判断

- 内部人 Forms 3/4/5 数据取得：满足，3/3 有真实 Form 4。
- Provenance 与 PIT 所需时间：满足本次输入准备。
- LLM 交易类型、滞后、覆盖和不可推断边界解释：已由 ALB 定点样本执行并通过结构化校验，评价保持 `SOURCE_LIMITED`。
- 13F 机构两期变化：本 Change 首版未实现，继续作为明确延期子能力。

因此 Task 6.3 按 Spec“只有内部人披露可得”的部分可得路径完成：保留可用的真实内部人研究，同时明确延期 13F 与历史序列。该勾选不代表完整所有权能力 `RESEARCH_VALIDATED`，延期清单仍须在 Task 8.5 最终人工批准时集中确认。

## 本轮确定性复核

最新执行 SEC、公司披露、财务事实、证券身份、所有权、Evidence Gate 与多维定点接缝的聚焦测试，共 148 项：146 PASS，2 项因当前环境未安装可选 live 日历/AkShare SDK 而跳过；两个跳过均不涉及 SEC 所有权接缝。OpenSpec strict validate 同时通过。

v1 的请求与原始解析证据保留原始源码锁；v37 的 Gate 与真实 LLM 产物另行锁定修复后源码及运行 manifest，避免把旧 hash 包装成当前候选证据。本轮没有启动 Council、Risk、Regression 或 Release Gate。
