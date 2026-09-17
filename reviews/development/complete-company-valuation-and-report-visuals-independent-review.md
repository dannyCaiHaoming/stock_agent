# complete-company-valuation-and-report-visuals 独立复核

- `source_id`: `independent-readonly-review`
- `as_of`: `2026-09-16T20:26:49Z`
- `retrieved_at`: `2026-09-17T03:39:21Z`
- 最终结论：`PASS`

复核全程为只读，未修改代码或验收产物。前三轮发现的当前点进入历史分位、同行缺少目标行与真实估值、混合量纲连线、报告摘要缺失、同行口径不一致、价格证据缺失、语义校验可被同步重算 hash 绕过，以及同行限制文本矛盾均已修复。

## 最终重验

- 真实 acceptance package 上，同步修改 P/S `revenue + value + calculation_ref + artifact/entry/package hash` 被拒绝。
- 真实 acceptance package 上，同步修改 TTM `annual + result + value + calculation_ref + artifact/entry/package hash` 被拒绝。
- 同公司唯一 `GAAP_TTM_REVENUE` 已与营业利润率、P/S 的期间、分母及 revenue evidence 绑定；artifact 级和 package 级回归攻击均有测试。
- acceptance package hash `0c89904387a7c7674af85fc6a4ef44eef4c523898bac527c9efebc34b90d68a1` 与 Gate hash `98e8796e1f7cec4fa67afcd26b0e4aea0696bb381bb19ef7bd12e8ca7eafd5ad` 绑定验证通过。
- model-acceptance package hash `57633e32cbc2fe4748c016018289cf26cc7c2a811b9cc6d5280f02f76a0ffb19` 与 Gate hash `ccca3a241c0a14eb96cdb77a30904ca40b377f9792fbe8a9cdc2589f8f3ef843` 绑定验证通过。
- PLAB、ALAB、MRVL 的同行表均使用 `FY + current YTD - prior-year YTD` 的 GAAP TTM 收入；PLAB 保留独立 Yahoo 冻结价格证据。
- 旧的“未年化”说明及重复 TTM 文本已从 JSON、HTML 和 PDF 清除。最终 PDF 为 29 页 A4 横向、无 JavaScript、未加密，并已重新逐页渲染检查。
- 相关聚焦测试 31 项全部通过，OpenSpec strict validate 通过。

## 边界与任务状态

冻结 raw hash/Evidence 负责来源真实性边界；本 Change 的 validator 负责已冻结指标之间的算术、期间、口径和引用一致性。规格未要求 validator 重新解析 SEC 整份原始文件。

## 第五轮 MRVL 成功产物增量复核

本轮只读复核覆盖最终授权的 MRVL v6 模型运行、同源图文报告和窄屏断行修复；
没有修改文件、启动模型、Runtime Eval、Replay、Regression 或 Promotion。

- 运行确为单次 `gpt-5.6-terra`、单证券 `US:COMMON_STOCK:MRVL`：只有一组配对
  Start/Stop，Coverage=`RESEARCHED`、stage=`RESEARCH_COMPLETE`、进程退出码 0，
  当前开发工作区源码完整性不变。
- 四类附件在同一次成功查询中返回。报告 16 个 Evidence 与两个 calculation_ref
  全部闭合；P/S 可按
  `221.6999969482422 × 847,300,000 ÷ (8,194,600,000 + 5,157,100,000 − 3,901,400,000)`
  复算为 `19.87729568524233263071013619`，三个输入期间在 Claim 中逐项保留。
- 报告状态为 `LOW_CONFIDENCE`，PIT EPS、历史估值、基准、指引、治理和同行不足
  均明确保留；未出现交易、仓位、目标价、订单或自动评分字段，也没有 PLAB 混入。
- 最终视觉 manifest 及 24 个图表/数据文件 hash 均通过；HTML 无脚本或外部 HTTP
  依赖，包含 251 个交易日、两期完整 FY 和六组明确 `LIMITED` 原因。
- 最终 PDF 为 20 页 A4 横向；20 张最终页面渲染及 contact sheet 未见裁切、中文
  缺字或错误连线。桌面和 390px 窄屏截图均与最终 HTML 对应。
- `.limit{...overflow-wrap:anywhere}` 是最小局部修复；精确回归断言已覆盖，没有引入
  新的布局机制或工程阻断。

第五轮 findings 为 none，`CHANGE_REVIEW: PASS`。任务 6.4 与 6.6 均可标记完成；
任务 6.7 的人工完成批准、归档、提交与推送仍未发生。本 PASS 不代表人工完成批准、
Runtime Eval 或 Promotion PASS。
