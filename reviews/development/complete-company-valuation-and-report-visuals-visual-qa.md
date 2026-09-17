# complete-company-valuation-and-report-visuals 视觉验收

检查来源 `deterministic-static-report-renderer`，资料截止 `2026-09-16T19:20:00Z`，检查记录时间 `2026-09-16T19:24:11Z`。

## 真实报告

- 桌面视图：1440px 宽，页面 `scrollWidth=clientWidth=1440`，0 个脚本、0 张损坏图片；核心图、长表、治理卡和同行表可读。
- 窄屏视图：390px 宽，页面不横向溢出；长表位于 348px 卡片视口内并保留 900px 可滚动表宽，避免列被压成单字。
- 打印视图：Chrome 离线打印为 29 页 A4 横向 PDF，`JavaScript: no`、`Encrypted: no`、无渲染错误。最终 PDF 重新逐页渲染；封面、历史估值页、补充卡片和跨页同行长表均实际检查，中文、负值和末页可见。
- 同行页：目标 PLAB 与 ALAB、MRVL 各显示 GAAP TTM revenue、GAAP TTM operating margin、market cap / GAAP TTM revenue，并保留逐指标期间、币种、三时间、价格/股数/收入来源、计算引用及有限可比状态。

检查图像保存在：

- `/private/tmp/complete-company-valuation-real-plab/acceptance/quicklook-final-desktop/report.png`
- `/private/tmp/complete-company-valuation-real-plab/acceptance/quicklook-final-narrow/report.png`
- `/private/tmp/complete-company-valuation-real-plab/acceptance/print-render-final-bound/`（29 页及 contact sheet，均晚于最终 PDF 生成）

## 盈利、亏损与重组负例

- 盈利：PLAB 真实数据生成当前 PE、50 个有效月末点和完整报告。
- 亏损：`tests.test_equity_valuation.EquityValuationTests.test_loss_pe_is_not_applicable_but_sales_remains` 验证负 EPS 的 PE 为 `NOT_APPLICABLE`，P/S 独立保留；图表 fixture 保留负 operating margin、Capex 和 FCF。
- 重组/断点：`tests.test_research_visuals.ResearchVisualBundleTests.test_core_charts_hashes_negative_values_and_short_sma` 验证 `ACCOUNTING_OR_ENTITY_DISCONTINUITY_NOT_CONNECTED`；显式价格缺口也不跨段连线。

## 修复记录

1. 文本型治理值曾进入通用数值折线导致 SVG 渲染异常；改为只有全部为有限数值的序列才绘线，文本保留表格，并增加回归测试。
2. 窄屏表格曾被压缩到不可读；改为卡片内横向滚动并保持最小 900px 表宽。
3. 打印封面曾留下孤立的下一节标题；增加 `break-after: avoid-page`，复验后封面和首图分开且无标题孤行。
4. 首版 CID 字体 PDF 中文消失；最终产物改为系统中文字体的 Chrome 离线打印，并逐页渲染检查。
5. 独立复核发现 mixed-unit 补充项和同行项曾被通用 SVG 跨字段连线；现改为不绘制混合量纲折线，只显示冻结记录说明与下方分单位表格，并增加无 `polyline` 回归测试。
6. 报告首段现确定性展示估值摘要、参考样本覆盖率、限制和既有解释；当前追加点不进入历史分位样本。
7. 清理同行说明中“未年化”的旧文本及重复 TTM 描述；最终同行表只保留统一 GAAP TTM 口径和可比性限制。

## MRVL 最终专项报告增量检查

最终 MRVL 模型验收报告来自
`/private/tmp/complete-company-valuation-mrvl-model-acceptance-v6.r2u9Rz/run`，资料截止
`2026-09-16T15:53:32.729494Z`。静态图文目录为
`/private/tmp/complete-company-valuation-mrvl-model-acceptance-v6.r2u9Rz/acceptance/report-final-v2`。

- 桌面视图：1440px 宽，页面 `scrollWidth=clientWidth=1440`，0 个脚本、0 张损坏图片；估值摘要、251 个交易日日 K/成交量/SMA、两期同口径完整财年趋势及补充卡片可读。
- 窄屏视图：390px 宽，修复后页面 `scrollWidth=clientWidth=390`；长表保留卡片内横向滚动。首次渲染发现 `PRE_ANNOUNCEMENT_VINTAGE_NOT_AVAILABLE` 等长限制代码造成 81px 页面溢出，渲染器现对 `.limit` 使用 `overflow-wrap:anywhere`，并有聚焦回归断言。
- 打印视图：Chrome 离线打印为 20 页 A4 横向 PDF，`JavaScript: no`、`Encrypted: no`。20 页全部重新渲染为 PNG 并检查联系表；封面、日 K 图、限制页、财务图和末页同行表均无中文缺字、裁切或重叠。
- 真实限制：基准行情缺失、PIT EPS 缺失导致历史 trailing P/E 0 有效点、事前预期、治理、指引和同行核心矩阵不足均显示明确限制卡；未以 PLAB 数据填入 MRVL 报告，也未伪造可用状态。
