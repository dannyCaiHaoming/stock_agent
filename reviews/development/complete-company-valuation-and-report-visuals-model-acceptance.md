# complete-company-valuation-and-report-visuals 专项模型验收记录

本记录的 `source_id` 为 `mrvl-single-model-acceptance-2026-09-17`，研究资料截止
`2026-09-16T15:53:32.729494Z`，运行开始于 `2026-09-17T00:30:12.431863Z`，
失败终止于 `2026-09-17T01:00:12.490810Z`，本记录取得于
`2026-09-17T01:08:26Z`。

## 结论

用户明确授权将冻结的 MRVL 持仓与研究附件发送给 `gpt-5.6-terra`，并限定为
唯一一次专项模型验收。宿主 launcher 实际启动一个
`runtime_company_analyst`，证券仅为 `US:COMMON_STOCK:MRVL`，但在 1,800 秒硬
超时前未返回终态。运行以 `COMMON_STOCK_STAGE_TIMEOUT`、进程退出码 `124` 和
`stage_status=FAILED` 结束。

本次没有生成 `equity-research.json`、Markdown 报告或 execution proof；MRVL
覆盖仍是 `NOT_RESEARCHED`，阶段仍是 `PARTIAL_RESEARCH`。因此 OpenSpec 任务
6.4 不勾选，Runtime Eval 保持 `NOT_RUN`，也没有执行 Replay、Regression、
Promotion、归档、提交或推送。唯一模型批次已经消耗，未自动重试。

## 输入与隔离

- 冻结持仓只有 MRVL 2 股；账户标识和净资产已移除，研究子集现金为 0。
- PortfolioHandoff hash：`05ff755b27479850be818a5c9ea8538d2420e0b02a6c03758383e347610a48be`。
- Gate hash：`3d99b90fc43e4572a5fbfdcc3aa65fcdec6fd60ebc65943dcaa9a71d077c5e6b`。
- 研究附件 hash：`858b8e9d9f0cd12f7decbc63acb93bb8f9be23c8d548625650cc1a4ac5beb393`；包含
  `valuation_snapshot`、`fundamental_supplement` 和 `peer_comparison`。
- 输入根目录：`/private/tmp/complete-company-valuation-mrvl-model-acceptance-inputs-v4`。
- 运行目录：`/private/tmp/complete-company-valuation-mrvl-model-acceptance-run-v3/run`。

启动前两次失败均发生在模型进程创建前：一次是系统解释器缺少
`exchange-calendars`，一次是附件任务重建校验缺口。后者已通过范围内修复和回归
测试解决；两次都没有消耗模型批次。

## 执行证据与失败边界

- `subagent-events.jsonl` 只有一条 `SubagentStart`：模型
  `gpt-5.6-terra`、任务 `company_research_1`、证券 MRVL；没有
  `SubagentStop`。
- 没有重复派发。父线程一次尝试主动查询在运行中的研究 Agent，被现有 Hook 以
  `DENY_ACTIVE_RESEARCH_CONTROL` 正确拒绝，随后继续等待直到宿主硬超时。
- 派发包为 `4,044,588` bytes，Gate 为 `4,284,178` bytes，而新研究附件仅
  `21,817` bytes。现有证据表明超时暴露的是公司研究上下文体积瓶颈，而不是新
  附件本身；是否压缩上下文须作为后续显式需求处理，不能用本次失败隐式扩项。
- 运行结束时完整性检查发现子进程改动了
  `product/runtime/common_stock_stage.py`。该文件已精确恢复到启动前 SHA-256
  `a991476ec3fcb4c083cd5b7cdc986d56040e21d1067f31ee4dc3ce6cb7680fcf`；启动前
  已完成的附件绑定修复保留。子进程对测试文件留下的上下文压缩断言也已撤销，
  不可信运行时改动没有并入需求实现。

## 状态判定

这次运行证明了 MRVL 冻结持仓、Gate 和研究附件能够通过宿主预检并实际进入既有
研究角色，但没有证明角色能在预算内完成报告，也没有证明引用、口径解释或禁止
动作的最终报告质量。因此专项模型验收结论为 `FAILED_TIMEOUT`，不是 PASS，也
不是可忽略的环境跳过。

## 后续新授权批次（2026-09-17）

用户随后另行明确授权了一个新的、仍然至多一次的 MRVL `gpt-5.6-terra` 专项模型
批次。该批次通过同一宿主 launcher 于 `2026-09-17T02:52:35.407674Z` 开始，
于 `2026-09-17T02:56:48.110893Z` 结束；外置运行目录为
`/private/tmp/complete-company-valuation-mrvl-model-acceptance-v5.x5rBRn/run`。
本次没有超时、没有进程异常退出，也没有修改当前开发工作区；隔离源码副本已丢弃，
运行层记录 `source_integrity_unchanged=true`、`process_exit_code=0`。

实际执行证明如下：

- 只派发 `company_research_1`，证券为 `US:COMMON_STOCK:MRVL`，模型为
  `gpt-5.6-terra`；实际存在一组配对的 `SubagentStart` / `SubagentStop`。
- Hook 紧凑上下文为 `154,335` bytes，低于 `262,144` bytes 硬上限。
- Agent 实际调用 `equity_research_attachments.query`，同一次成功返回
  `valuation_snapshot`、`valuation_history`、`fundamental_supplement`、
  `peer_comparison` 四类附件、19 个可引用 Evidence 和 3 个冻结计算 ID。
- Agent 形成了完整结构化研究草稿，状态为 `LOW_CONFIDENCE`，并正确保留
  MRVL 历史 trailing P/E 无有效点、同行不足、催化剂与 FCF 资料不足等限制；
  草稿没有组合动作、目标权重、交易数量或订单。

但本次仍未通过确定性报告验收。`SubagentStop.output_capture.failure_code` 为
`EQUITY_RESEARCH_FACT_PERIOD_LINEAGE_INCOMPLETE:claim-derived-valuation:2025-02-02`：
派生市销率 Claim 引用了 FY、prior YTD、current YTD 三段收入 Evidence，却只写了
TTM 截止日，且未引用附件实际交付的冻结
`calc:price_to_sales:60c0b66528422817`。运行层因此将原始草稿保存到
`research/rejected/77ce7e720a7e2de74c298325c27484a234f19e66d00ebab2e9529665b3ce8b2a.json`，
没有生成已验证的 JSON/Markdown/HTML；Coverage 与 stage 均为 `FAILED`，宿主返回
`COMMON_STOCK_REPORT_SET_INCOMPLETE`。这属于正确的 fail-closed，不应放宽期间血缘
校验或把 rejected 草稿冒充报告。

问题根因是运行指令自相矛盾：前段把 `calculation_ref` 限定为本次
`calculate` 返回值，后段才允许冻结附件计算。范围内修复已统一 Company Analyst
配置与 dispatch packet：实际附件查询返回的冻结 `calculation_ref` 可以且必须在
引用 DERIVED 数值时进入 Claim 与顶层 `artifact_refs`；基于
`FY + current YTD - prior YTD` 的 FACT 还必须逐项保留所有输入期间。新增聚焦
断言所在的普通股研究与产品配置套件共 100 项通过。进一步的确定性内存诊断只对
rejected 草稿补上述引用与期间后，原
Schema、交付闭合、期间血缘及 Markdown 渲染全部通过；该诊断不改写原运行，也不
算真实模型 PASS。

修正后又使用同一份冻结 MRVL 输入完成一次零模型运行包重建，未启动模型。新 Hook
上下文为 `154,850` bytes，继续低于 `262,144` bytes；运行包重建校验通过，并确认
冻结计算规则、DERIVED 值的计算/输入引用规则、TTM 多期间规则均实际出现在绑定
dispatch packet 中。该零模型检查目录为
`/private/tmp/complete-company-valuation-mrvl-post-failure-readiness.KHmZ4e/run`，
packet hash 为 `78b8ae53dca94e38a70f021250097fa026dd2fbf380f71b9b92782f013108f0d`。

因此第二个授权批次的结论为 `FAILED_VALIDATION`。它已经消耗，未自动重试；任务
6.4 继续保持未完成，6.6 独立复核与真实 MRVL 图文视觉检查尚不能启动。Runtime
Eval、Replay、Regression、Promotion、归档、提交和推送仍为 `NOT_RUN`。

## 最终授权批次与通过结论（2026-09-17）

用户再次明确授权“发送冻结的 MRVL 持仓与研究附件给 `gpt-5.6-terra`，执行唯一
一次专项模型验收”。本次严格只运行这一批，没有自动重试。宿主 launcher 在
`2026-09-17T03:14:14.987510Z` 启动，于 `2026-09-17T03:19:21.364806Z`
完成；运行目录为
`/private/tmp/complete-company-valuation-mrvl-model-acceptance-v6.r2u9Rz/run`。

最终结论为 `PASSED`：

- 仅派发一只 `US:COMMON_STOCK:MRVL`，一组 `SubagentStart` / `SubagentStop`
  完整配对，模型为 `gpt-5.6-terra`；进程与 launcher 均以 0 退出，阶段为
  `RESEARCH_COMPLETE`，隔离源码完整性不变。
- Agent 实际查询 `valuation_snapshot`、`valuation_history`、
  `fundamental_supplement`、`peer_comparison` 四类冻结附件；最终 7 条 Claim 的
  16 个 Evidence 均属于 Gate 且实际由工具返回，两个 calculation_ref 均由冻结
  附件或本次确定性计算实际交付。
- 已验证 JSON 与 Markdown 均成功生成。报告证券及 handoff 都不含 PLAB，也没有
  action、target price、weight、quantity 或 order 字段；DERIVED P/S 的冻结计算
  引用与 `FY + current YTD - prior YTD` 输入期间通过既有确定性校验。
- 报告状态为 `LOW_CONFIDENCE`，原因是 PIT EPS 缺失导致历史 trailing P/E 无有效
  点、冻结包没有基准行情、forward P/E 与完整 EV 组件不可用、同行覆盖不足。这是
  显式限制，不是运行失败，也没有被静态页面伪装为可用数据。
- 同源 MRVL 静态报告使用 251 个冻结交易日和两期同口径完整财年。桌面
  `1440px`、窄屏 `390px` 均无页面横向溢出，0 个脚本、0 张损坏图片；20 页 A4
  横向 PDF 已逐页渲染检查。限制原因的长英文代码曾造成窄屏多出 81px，已在通用
  静态渲染器中增加强制断行并补回归断言，复验通过。

最终报告 JSON SHA-256 为
`58cbc460a19f099559f4e299e7b88d9a764e6d29da45254496283444c02352cf`；
视觉目录为
`/private/tmp/complete-company-valuation-mrvl-model-acceptance-v6.r2u9Rz/acceptance/report-final-v2`。
Runtime Eval、Replay、Regression 与 Promotion 仍为 `NOT_RUN`，不会因本次专项消费
验收被冒充为 PASS。任务 6.4 至此完成，随后只进入任务 6.6 的增量独立只读复核。
