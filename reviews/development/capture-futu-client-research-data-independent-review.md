# capture-futu-client-research-data 独立复核

## 结论

`CHANGE_REVIEW: PASS`

同一只读 Reviewer 对修复后的代码差异、OpenSpec artifacts、持久化验证记录及 `/private/tmp/aapl-three-source-consumption-input-v2` 真实三源冻结包完成复核。当前没有代码级 blocker；本结论不是 Change 人工完成批准，也不是候选 Promotion。

## 已核对项目

- Moomoo 资金流只接纳检索时刻前已完成的分钟桶；`period_end/as_of`、`provider_valid_time` 与 cutoff 约束闭合。
- supplement fact 保存 `source_type`、`batch_id`、OpenD/SDK/method/manifest 版本；capability 保存 Evidence、raw hash 与请求预算。
- authoritative source plan 同时在 assembly 与 batch validator 执行；Yahoo 财报日历属于 `event_context`，不冒充发行人指引。
- SEC 分部解析跳过维度化文本，坏数值形成 gap，隐藏层/展示层重复事实按 Evidence ID 去重。
- Gate 要求 snapshot、gate、preparation cutoff 完全一致，并按 `collection-input.json` 限定证券集合。
- OpenD 使用独立 `_readiness_approved` 状态；失败先清空，只有 server version、`READY` 与 Quote 登录全部通过才原子批准。`QUOTE_NOT_LOGGED_IN`、`OPEND_NOT_READY` 后同一 client 再读均在连接第二个 context 前拒绝；成功 readiness 后才允许研究读取并携带已核实 server version。
- 最新聚焦命令为 134 tests / 0 failures / 0 errors / 0 skips；完整命令和输出 hash 见 `capture-futu-client-research-data-validation.json`。真实同一 client readiness → company profile 最小验证也已通过。
- v2 包含 228 facts、15 capabilities、10 source selections；MCP 查询返回 27 facts，来源精确为 SEC、Yahoo、Moomoo SG。5 条 `VENDOR_CALCULATED_FLOW` 完成 Capture → Normalize → PIT → MCP。
- 未发现联系邮箱、Cookie、Token、密码、私人账户资料；OpenD 边界保持 Quote-only，无 Trade Context、订单、账户、持仓、资金或交易解锁能力。

## 完成状态与剩余边界

- Task 7.3 的首次 Terra 消费因旧输入包存在未来分钟桶而作废，不能计为 PASS。
- 用户再次明确授权后，replacement Terra 已只消费 v2 冻结输入并通过；23 个引用全部闭合，事实/预测/观点、覆盖缺口、三源语义与供应商资金流限制均保持。权威记录为 `capture-futu-client-research-data-terra-consumption.json`。
- 本 Change 的实施任务现已完成；仍需用户给出人工完成批准，才能归档、提交和推送。
- 本 Change 未运行且不要求 Replay、Runtime Eval、Regression、Ablation、Promotion 或完整 Council。用户另行要求的截图持仓 `COMMON_STOCK_RESEARCH` Smoke 不属于 7.3，也不改变本结论。

## 2026-09-17 截图持仓增量复核

`CHANGE_REVIEW: PASS`

同一只读 Reviewer 对紧凑派发包、长等待门禁、报告拒收/finalizer 边界、ALB 单股与 ALB/MRVL/WOLF 三股正式运行证据及最新 OpenSpec 口径做了增量只读复核。结论无 blocker；不代替人工完成批准、Promotion PASS 或生产批准。

- dispatch catalog 只排除后续 `technical-structure` 消费的 6 类逐日价量字段。静态核对三股冻结包：ALB 2358→852、MRVL 2339→833、WOLF 2085→633；减少数均等于各自交易日数×6，未丢失 SEC 财务/业务/指引、Yahoo 背景或 Moomoo `vendor_money_flow`。
- 活动研究任务期间会拒绝 `list/follow-up/interrupt` 和短等待；父 `Stop` 只核对同父会话、冻结 task/invocation 的真实终态。finalizer 只接纳 `output_capture.status == SAVED`；被拒报告保存在 rejected 区并确定性归类为 `REPORT_MISSING`。
- ALB v10 进程正常退出、`all_reports_valid=true`、源码完整性未变。三股正式批次 `completed=3/expected=3`、`parallel_overlap=true`，3 个 Stop 均为 `SAVED`，最终父 Stop 为 `ALLOW`。报告与日志 hash 均与验证 JSON 一致。
- 三份报告的 Evidence 均属于对应 request/Gate，无串证券；引用均出现在对应 invocation 的真实 MCP 返回中。每股都实际引用 SEC、Yahoo 和 Moomoo SG；MRVL 引用 `identity_profile`/`earnings_guidance`，WOLF 引用 `business_segments`。Gate 6,782 条 Evidence 无 cutoff 后事实，Moomoo 资金流嵌套 `period_end` 均早于共同 cutoff。
- 正式运行环境快照覆盖的 151 个源码文件与当前工作区逐项 hash 一致，没有用旧代码运行结果外推当前实现。
- Proposal、Design、Spec、Tasks 与 validation JSON 口径一致。旧 AAPL 仅作历史限定样本；v3/v8、ALB v7–v9 等失败运行均保留为失败、无效或被取代证据，未用于证明当前持仓验收。
- 未发现联系邮箱、Cookie、Token、密码或交易解锁材料进入当前 Change/验证材料。Moomoo 仍为 loopback、Quote-only；ETF 与 SOXL 期权继续保留 `CAPABILITY_GAP`。本次未启动 Runtime Eval、Regression、Promotion 或完整 Council。

最新受影响检查为 234 tests / 0 failures / 0 errors / 0 skips；完整命令、输出 hash、运行目录和产物 hash 见 `capture-futu-client-research-data-validation.json`。
