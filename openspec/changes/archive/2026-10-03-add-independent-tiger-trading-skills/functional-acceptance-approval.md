# 功能验收批准与归档范围

- `source_id`: `user-approval:functional-archive:20261003`
- `as_of`: `2026-10-03`
- `retrieved_at`: `2026-10-03`
- Change：`add-independent-tiger-trading-skills`

## 人工批准

用户在收到实现复核及虚构浏览器验收结果后明确表示：

> 如果你只看功能实现，我觉得可以同步且归档了

本次按该指示批准**功能实现范围的主规格同步与归档**。成功归档后的限定实现、主规格及归档文档提交/推送沿用根AGENTS.md与开发流程；这不是新产品运行、私人页面访问或候选晋升授权。

## 结论与接受的例外

- `FUNCTIONAL_CHANGE_REVIEW: PASS_WITH_ACCEPTED_VISUAL_EXCEPTION`。
- 12.7：既有441项确定性检查、最终安装专项76项、独立源码复核和本轮虚构浏览器补证共同支持完成。没有重新执行或扩大旧测试结果。
- 6.1：真实采集、同文件同窗口重复导入、970条覆盖与绑定等已有有效证据；**真实私人图表/复盘页面的实际可视检查仍为UNVERIFIED**。原任务保持未勾，不伪称完整GUI验收。用户本次限定功能实现范围，接受该可视缺口不再阻断本次归档。
- 6.3：本记录完成明确人工批准及发布排除清单；归档、限定提交、推送按实际结果记录，不提前宣称执行成功。
- 真实历史仍为部分覆盖；开户起点、期初/费用、期权历史数据和意图缺口均保留。功能验收不证明完整绩效核算或综合能力评分。
- `CANDIDATE_PROMOTION: NOT_RUN`；不刷新候选指针，不启动Eval、Replay、Regression、Calibration、Ablation或真实Smoke。

本次不删除或改写历史验收证据中的原始未完成/阻断记录；本记录是其后新增的人工功能收尾决定。真实可视以后仅在新的明确授权和工具允许路径中补做，不绕过曾经的拒绝。

## 主规格与产品边界

同步两个新增能力：`tiger-desktop-trade-journal`、`historical-trading-reflection`。保留来源/覆盖/PIT/版本绑定、私人隔离、工具准入与只读券商职责。用户批准的归档例外不改写这些产品行为契约，不把未验证改成产品PASS。

归档期间另一会话请求冻结 `product/`。本会话不修改product源码、Skill、Agent、Schema、Risk或版本工作树文件；只写本Change文档和主规格。后续Git暂存共享文件时只从已审阅范围装配index，不替换工作树文件，不夹带并行单股研究/Tiger API/其他Change。

## 限定发布范围

允许：
- 两个独立Skill及 `product/trading_journal/` 确定性支撑；
- 对应 `tests/test_trading_journal_*.py` 合成检查；
- 私人隔离所需 `.gitignore` 精确新增段、三个既有测试的 `.private` copy排除、两个Skill版本登记；
- 已审阅的洁净插件来源切换；
- 本Change归档、两份主规格及脱敏验收/发布记录。

共享Runtime与其他复制排除已经进入历史基线时不重复提交；共享manifest仅提交两个独立Skill的新增登记，不提交其他模型、Agent、Schema、Council或候选锁的变化。

永久排除：
- `product/.private/` 的原始导出、账本、行情、报告、图表、观察回执和截图；
- `.codex-local/`、`.codex-runtime/`、私人会话数据库/转录、插件实际缓存及本次临时合成库；
- `.claude/` 浏览器启动配置、合成harness及本地截图；
- 凭据、认证笔记、完整账户身份、无关用户消息；
- 其他活跃Change以及无关dirty修改。

发布前核对stage路径与敏感内容、共享hunk、源码hash及有效证据；发现未知敏感信息、未审阅变更或验证失败即停止相关发布。按实际commit/push结果追加发布记录；不force push。

## 发布状态

待执行：OpenSpec严格验证、归档及主规格同步、限定提交/推送。后续实际结果见归档后的发布记录。
