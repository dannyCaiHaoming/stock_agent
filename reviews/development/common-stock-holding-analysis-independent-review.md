# 普通股持仓研究独立差异复核

Reviewer：`dev_reviewer`（独立只读子 Agent）。父任务 ID：`01a09619-ecea-75a1-a6d8-b804486d017d`。复核只读取当前 Change 差异、规格和已有底层证据；未重跑测试、产品研究、Eval 或完整 Gate，也未修改文件。

## Reviewer 原始结论

CHANGE_REVIEW: PASS

阻断项：无。

独立 Reviewer 核验结果：

- 未新增研究 Agent；复用 `runtime_company_analyst`，绑定 `evidence-grounding`、`company-research`、`valuation`、`catalyst-analysis` 四项 Skill。
- Python 仅负责契约、证据闭包、确定性计算、调度及校验，没有把主观投资判断编码为评分或规则引擎。
- AAPL、MSFT 使用两个独立子会话，执行区间分别为 `2026-09-12T14:00:44.910997Z–14:03:37.074326Z` 与 `2026-09-12T14:00:47.172048Z–14:03:10.634102Z`，实际重叠。
- 两份 `EquityResearchReport` 均包含事实、假设、估值限制、反证、失效条件和监控项；事实具有 `source_id`、`as_of`、`retrieved_at`。未发现买卖动作、仓位、目标权重、订单或完整组合结论。
- MCP 事件共 11 条，均为只读查询或确定性计算；无 broker write、生产写入或版本晋升。
- Skeptic 首轮隔离由输入契约拒绝 Analyst 报告/摘要字段；CIO 接口接收经校验的完整报告而非摘要。本次两股研究按规格在 Skeptic、CIO、Risk 前停止。
- 外置持仓是 AAPL/MSFT 合成 fixture，不是用户私人持仓；未发现私人账户或持仓数据进入仓库。
- 暂停的 `us-equity-live-advisory-slice` Task 5.3/5.4 仍未勾选；其 tasks hash 为 `6aef7b0405e34383103b71465cade0cd13fada68e8702502ef44318b85dd3219`，未见本次工作改写其任务或历史证据。

Reviewer 对 AAPL Eval 的判断：实际 `dev_eval` 子会话输出已由 Hook 保存为 `PASS`，九个维度完整且均不低于 2，报告、输入、Rubric、模型、证据引用和 canonical hash 均闭合。其结果标识为：

- Eval ID：`eval-common-stock-aapl-v12-v2`
- canonical result hash：`9a1d332aa910219df8f8415e289aceb8028fec65c35e5bd7160bfb9c6fb87b31`
- `eval/result.json` SHA-256：`50c155f387ea4ffbc9d1cd0478541a2fe70ed0335328b92d1e62eb725515d5e7`

原 `process-result.json` 保留 `FAILED / COMMON_STOCK_EVAL_DIMENSIONS_INVALID`，SHA-256 为 `cb95b616b4ebcb19c894d8d37899dcc4b7d5bc938d0a4ce6d15e09c99f6a6d4a`。原因是旧收尾器把 JSON 对象键顺序当成维度顺序；当前校验器比较维度字段集合，保存的同一结果可通过全部校验，期间没有重新调用 AAPL 模型。因此该证据足以证明当次实际聚焦 Eval 及语义 PASS，但不能表述为当次 launcher/process 已 PASSED，原失败必须继续保留。

MSFT 的 `eval-common-stock-msft-v12-v2` 同时为语义 `PASS` 和 process `PASSED`，canonical result hash 为 `1263ab0e6a7cc0771143f97f2348374fb7fbc830851fae086c00b933b60ae616`。

Reviewer 核验的主要证据锁：

```text
run_id                  common-stock-C4AC132C-EC4B-40DC-8D0D-C49B73C84CAD
execution_proof         70358cef3dcc85d4fc9543c5229b3295fc9fe8755bc5b9ae9e6ae5b61bc51598
runtime_company_analyst c03716c992c2a642e4bd96c54473476ce707c8a2f1e1ec3454a8aeaa09514768
common_stock_research   21f6e96f763c330f5a595a84fa70bb5124e6fd41dfb7c8c82d3c2dbfa5071589
common_stock_stage      7de1ef7aeb3d58a30f1352427aefaa0b017ac5bb16b9c9b7df24dcdcf6da94c8
common_stock_eval       f22b47674a304440aaad7757673c6584ca47088f34e38d130018cb531a2ff5b4
hook_recorder           0e9975c6edfd26a749103d003b3e330766e33fa12b9813fa83ba7ef51a9fe3b1
fixture_mcp             679e94b59734e3d5995aabfa4e3dcba80db3a3fb609ff0005d07d0bb8583940c
runtime_profile         cbf6bcc00d8b71dd1c84f2464c84eabe96fcfc221a4b7be0b8814ac09abe7232
version_manifest        44406411ad076de8127d032793061bec9a916e3d5837296130140d9af4057ae2
equity_report_schema    83607a6ad4734773e3093fc3280ea1b6a602d6ab13e0fc05d91d87124573b92e
rubric                  001edaf2af8727b4aedda49e8ad4e63af2d65bed11776b1cf913aae924eedca6
```

适用范围：本结论仅覆盖两只普通股的研究闭环及聚焦 Eval。它不是 Promotion PASS，也不证明完整 Portfolio Council、真实 Skeptic、CIO、Risk、Regression、Replay、Calibration、Ablation 或生产批准。Task 5.4 仍须用户明确人工批准。

## 主线程确定性抄录校核

Reviewer 原始长文本在抄写 MSFT 报告 SHA-256 时写为 `26ec8917...`，与其读取的机器证据索引不一致。实际文件与 `common-stock-holding-analysis-evidence.json` 均为：

```text
26ec116276ea98cdbc20badbea7b4c556a2d1936449654655efa11880135d791  /private/tmp/stock-agent-common-stock-acceptance-run-v12/research/reports/US_COMMON_STOCK_MSFT/equity-research.json
```

本注记只更正抄录，不修改 Reviewer 的 PASS 结论、外置运行产物或机器索引。Reviewer 原始输出保存在 `/private/tmp/common-stock-holding-analysis-independent-review.txt`。

## 2026-09-13 当前版本增量复核

Reviewer：`dev-reviewer`（独立只读子 Agent），Agent ID `01a096a9-0f4f-7540-bfef-f2d621c4cf00`。复核直接读取当前 Change、相关源码差异及仓库外底层运行包；未运行产品 LLM、Regression、Replay、Calibration、Ablation、Promotion 或完整 Gate，也未修改文件。

首次复核结论为 `CHANGE_REVIEW: FAIL`，发现两项阻断：stage finalizer 将一份 `LOW_CONFIDENCE` 报告错误归集为 `VALID_RESEARCH`；验收记录在缺少修改前 Markdown hash 时过度声明历史 AAPL 文件未修改。

主线程仅做定点修复：

- finalizer 改为从报告的 `COMPLETE / LOW_CONFIDENCE / INSUFFICIENT_EVIDENCE / TIMEOUT` 映射对应研究状态，新增真实构造 `LOW_CONFIDENCE` 报告的聚焦测试；修复后 `common_stock_stage.py` SHA-256 为 `3bebfa3a5a37ed553bad2ce35bbf61af150d3bc4e8a9cdaff4bd28178ae4ecee`，相关检查 `20/20 PASS`。
- 原始缺陷 coverage 保留并明确标记，不能再用作状态归集正确的证据；历史 AAPL 修改历史改为 `UNVERIFIED_NO_PRECHANGE_MARKDOWN_HASH`，只记录当前 JSON/Markdown 完整 hash，不伪造历史证明。

同一 Reviewer 的二次增量结论：

```text
CHANGE_REVIEW: PASS
阻断项：无。
```

Reviewer 确认 Task 5.3、6.6 可以完成，Task 5.4 必须保持未完成并等待用户明确人工完成批准。该 PASS 只证明本 Change 的普通股研究切片，不代表完整组合决策或 Promotion PASS。

## 2026-09-14 第 8 组限定增量复核

Reviewer：`dev-reviewer`（独立只读子 Agent），Agent ID `01a09b9a-dfa2-7f52-8e72-acdf33e841e8`。Reviewer 未重跑测试或模型、未修改文件，也未扩大到完整 Council、Regression 或 Promotion。

首次结论为 `CHANGE_REVIEW: FAIL`：Task 8.2 的一份报告遗漏 Gate 内较新且适用的可比收入事实；只有一份报告达到全部语义维度；94 项测试记录缺少精确选择器和原始日志 hash。主线程只修复对应的最新事实自检，补一次受影响真实批次及一份聚焦 Eval，并绑定已有测试原始记录；旧失败报告和结果均保留。

最终限定复核结论：

```text
CHANGE_REVIEW: PASS
Tasks 8.1–8.6: 可勾选
阻断项：无
Task 5.4: AWAITING_USER_APPROVAL
```

Reviewer 核验当前 Company Analyst `3.0.15` 的 sample A 报告分别使用两个同口径上半年累计期间，将二季度单季净利润/EPS 单列，并仅以 2025 全年亏损作为跨周期现实反证。对应 Eval `eval-recency-current-lock-v1` 九维均为 3，canonical result hash 为 `3efae1022acf28aad119216eba1a42c2ab6ac19c9bb5c0b4baf81ec1ff75b4db`；它与上轮不受本次指令修复影响、已全维度 PASS 的 sample C 共同满足两份实质报告标准。

聚焦测试原始日志为 `/private/tmp/stock-agent-common-stock-depth-v8-final-evidence/focused-tests.log`，记录 `Ran 94 tests` 和 `OK`，SHA-256 为 `50274272aa94dc2ff278083e97d4db2041b0d2e94c992e0a451e66b73c89b1bc`。OpenSpec strict 日志 SHA-256 为 `31fe5edc2de56dd279c58271e1ff314368bcd0a21cbdb27423e7066082157bba`。

该 PASS 只关闭第 8 组实现与限定质量证据，不构成人工完成批准、归档批准、完整组合研究或 Promotion PASS。

## 2026-09-14 当前三份输出逐份验收复核

Reviewer：`dev-reviewer`（独立只读子 Agent），Agent ID `01a0a00c-0cae-72d3-9650-b5fe02392586`。复核直接读取当前差异、Rubric 声明、实际 Rubric 文件、聚焦测试记录和 ALB/MRVL/WOLF 底层运行及 Eval 产物；未修改文件，也未重跑研究模型、Eval、完整 Council 或发布门禁。

首次结论为 `CHANGE_REVIEW: FAIL`：当前普通股聚焦 Eval 实际使用 `common-stock-research-semantic/1.6.0`，但候选 manifest 没有独立锁定该 Rubric，因此 Task 8.6 暂不能完成。主线程没有覆盖完整 Council 的通用 `runtime_eval_rubric`，而是在 `product/version-manifest.json` 的 `assurance` 中独立声明普通股 Rubric ID 及实际 SHA-256 `e20c3a0875d203dd8ad67b74c592ebe5e8c15094fa43d85686335251f8b804a9`，并由契约测试绑定实际文件版本和 hash。

Reviewer 最终结论：

```text
CHANGE_REVIEW: PASS
Task 8.2: 可勾选
Task 8.3: 可勾选
Task 8.6: 可勾选
阻断项：无
```

Reviewer 确认通用 `assurance_hashes.runtime_eval_rubric` 保持原值，没有把普通股聚焦 Rubric 冒充完整 Council Runtime Eval Rubric；100 项聚焦测试日志 SHA-256 为 `fe47d03eab441945311c4f9ad84d096f668602527e4d0a8aecead8ce64601081`，OpenSpec strict 日志 SHA-256 为 `31fe5edc2de56dd279c58271e1ff314368bcd0a21cbdb27423e7066082157bba`。结合此前直接核验的三份底层产物，本轮 ALB、MRVL 与最终 WOLF 报告均绑定自身 Eval 且为 PASS；失败的 WOLF 3.0.16 尝试继续保留，没有改写 Rubric 或伪装成功。

适用范围仅为本 Change 的普通股公司研究输出可供下游。它不证明完整 Portfolio Council、Skeptic、CIO、Risk 或 Promotion PASS；Task 5.4 仍须用户明确人工批准。
