# complete-company-valuation-and-report-visuals 真实验收

验收记录来源为 `bounded-real-acceptance-2026-09-17`，资料截止 `2026-09-16T19:20:00Z`，记录时间 `2026-09-16T19:24:11Z`。结构化明细见同目录 JSON；正式 Runtime Eval、Replay、Regression 与 Promotion 均未运行。

## 结论

- PLAB 真实盈利样本形成 DERIVED trailing PE `9.598591629887970422535211268`，五年请求 61 个观察点中 50 个有效点，总覆盖率 `81.9672%`；当前追加点明确排除后，49 个历史参考点覆盖率 `81.6667%`，mid-rank 分位为 `18.36734693877551020408163265`。逐点保留来源、三时间、单位、公式版本、可复算输入与 calculation_ref，并剔除一条来源公开晚于观察点的 FY2021 Q4 输入。
- 真实图文报告含四组核心图、七组补充呈现及目标公司加两家同行表；HTML/Markdown/SVG/JSON/manifest 均为离线相对引用，PDF 为 29 页 A4 横向打印产物。
- 基本面核心矩阵由 PLAB、ALB、MRVL、ALAB 多个预先限定普通股样本合计覆盖；条件项 ROIC、授信条款和实际/预期比较保留具体限制，不伪装成功。
- 工程实现和确定性真实验收已 PASS。首个 MRVL 专项模型批次硬超时，第二个批次因 DERIVED P/S Claim 的输入期间与冻结 calculation_ref 不完整被正确 fail-closed；两次失败均保留且未自动重试。修复后，用户再次明确授权唯一一次 MRVL `gpt-5.6-terra` 批次：该批次只研究 `US:COMMON_STOCK:MRVL`，实际查询四类附件，生成状态为 `LOW_CONFIDENCE` 的已验证 JSON/Markdown，并通过 Evidence、calculation_ref、多期间血缘及禁止动作检查。随后使用同一 Gate/附件生成 251 个交易日、两期完整财年和显式限制卡的离线 HTML/SVG，桌面、390px 窄屏与 20 页 A4 横向 PDF 视觉检查通过。第五轮增量独立只读复核 findings 为 none，`CHANGE_REVIEW: PASS`；用户已批准完成，任务 6.4、6.6、6.7 全部完成，主规格同步与 Change 归档已完成。

## 有界采集

PLAB/基准五年采集共 9 个真实请求、6 个 cache hit、1,264 个 PLAB 日线点；公司披露预算保持 2 份年度、4 份季度、4 份业绩发布、2 份代理声明、8 份其他 8-K、总计 32 份，同行固定为 ALAB 与 MRVL，不递归扩展。

## 核心真实矩阵

| 分组 | 状态 | 真实证据摘要 |
|---|---|---|
| 同目标期指引 | PASS | ALB FY2026 Specialties 两版数值指引可核对；PLAB 不同目标期为负例。 |
| 盈利质量 | PASS | MRVL FY2025/FY2026 SBC、回购、实际股数分列；ALB GAAP–adjusted bridge 精确闭合。 |
| 债务 | PASS | MRVL 三个未来本金桶、现金、流动/非流动债务均有 SEC Evidence；2.713B 未分配差额保留。 |
| KPI/集中度/治理 | PASS | ALB 两期同定义 LCE 销量；PLAB 匿名关联客户和审计委员会预批准政策有代理声明原文。 |
| 核心比率 | PASS | PLAB ROE、ROA、流动比率、OCF/净利润可复算；ROIC 明确 INPUT_MISSING。 |
| 两家同行 | PASS | PLAB、ALAB、MRVL 各三项同口径指标：GAAP TTM 收入、GAAP TTM 营业利润率和市值/GAAP TTM 收入；逐项带期间、三时间、价格/股数/收入来源和可复算输入，无评分或排名。 |
| 实际/预期 | CONDITIONAL | GAAP actual 与 non-GAAP guidance 不匹配，不生成 beat/miss。 |

## 关键产物

- 真实验收包：`/private/tmp/complete-company-valuation-real-plab/acceptance/`
- 冻结附件：`equity-research-package.json`，package hash `0c89904387a7c7674af85fc6a4ef44eef4c523898bac527c9efebc34b90d68a1`
- Gate hash：`98e8796e1f7cec4fa67afcd26b0e4aea0696bb381bb19ef7bd12e8ca7eafd5ad`
- 专项模型验收记录：`reviews/development/complete-company-valuation-and-report-visuals-model-acceptance.md`
- 最新 MRVL 冻结输入：`/private/tmp/complete-company-valuation-mrvl-model-acceptance-inputs-v5/`
- 最新 MRVL 失败运行：`/private/tmp/complete-company-valuation-mrvl-model-acceptance-v5.x5rBRn/run/`
- 最终 MRVL 成功运行：`/private/tmp/complete-company-valuation-mrvl-model-acceptance-v6.r2u9Rz/run/`
- 最终 MRVL 图文目录：`/private/tmp/complete-company-valuation-mrvl-model-acceptance-v6.r2u9Rz/acceptance/report-final-v2/`
- 最终 MRVL 打印检查：`/private/tmp/complete-company-valuation-mrvl-model-acceptance-v6.r2u9Rz/acceptance/mrvl-report-final.pdf`（20 页 A4 横向）

## 保留限制

- Yahoo 当前 provider PE、forward PE、完整 EV/EBITDA 和历史一致预期不是核心完成条件；字段缺失或口径不明时维持条件受限。
- PLAB 选定结构化资料没有债务期限表和 GAAP–adjusted bridge，因此对应真实正例分别由 MRVL 与 ALB 覆盖；PLAB 报告仍显示自身 PARTIAL 限制卡。
- 同行 P/S 的市值分子由冻结价格与截止点前最新已发布实际流通股数确定性计算；三家公司收入分母均按 `FY + current YTD - prior-year YTD` 重建 GAAP TTM，业务结构差异和有限可比状态仍显式保留。
- 前两次分别获得明确授权的 MRVL 模型批次均已消费：第一次硬超时，第二次在报告期间血缘校验处 fail-closed；没有自动重试。第三次由用户再次明确授权的唯一批次已通过，并未启动 Runtime Eval、Replay、Regression 或 Promotion。人工完成批准与归档已完成；提交和推送属于本记录后的开发收尾，不构成候选晋升证据。

## 确定性验证

- 受影响模块：`193` 项通过，`4` 项按环境跳过；使用 `/private/tmp` 避免 macOS 默认临时目录的符号链接路径策略干扰。
- MRVL 超时后的清理回归：锁定运行环境下 `195` 项全部通过；同时确认核心运行文件恢复为启动前 hash、旧 MRVL 运行包可重建，且新增附件绑定回归通过。
- 归档前最终回归：统一 `runtime-company-analyst 3.0.20`、Agent 资源 hash 与 runtime profile 派生 hash 后，受影响套件 `204` 项全部通过、无跳过。
- `openspec validate complete-company-valuation-and-report-visuals --strict`：PASS。
- Python 编译、JSON schema 文件解析、冻结包/Gate 重验、`git diff --check`：PASS。
- 语义校验器负例：重新计算 hash 也无法掩盖历史分位、覆盖率、同行覆盖状态、跨指标 TTM 收入、P/S 分母或价格证据篡改，相应用例包含重算 artifact/package hash 的包级攻击并均 PASS。
- 独立只读复核：第五轮已对最终 MRVL v6 运行、报告、图文目录、视觉证据和窄屏修复完成增量检查，findings 为 none，`CHANGE_REVIEW: PASS`；该结论不替代 6.7 人工完成批准。
- 最终 MRVL 增量验证：1 次 Start/Stop 完整配对；Coverage=`RESEARCHED`、stage=`RESEARCH_COMPLETE`、source integrity 不变；7 条 Claim 的 16 个 Evidence 与两个 calculation_ref 全部闭合。图表测试 8 项通过，OpenSpec strict 与 `git diff --check` 通过。
- 全仓套件共运行 `972` 项，结果为 8 failures、27 errors、22 skips。失败集中于既有 Demo fixture 漂移、系统解释器缺 `exchange-calendars`、旧 candidate/promotion/version manifest 基线和默认临时目录策略；本 Change 的聚焦模块重跑全部通过。当前 CLI 不提供 `self-check` 子命令，调用被明确拒绝为 `SELF_CHECK_COMMAND_NOT_ALLOWED`，未伪装 PASS。

## 人工完成批准

用户于 `2026-09-17` 明确回复“我批准”，批准
`complete-company-valuation-and-report-visuals` 完成收尾。任务 6.7 已完成，随后按开发
流程同步主规格、归档 Change、执行范围与敏感信息检查，并提交推送到根
`AGENTS.md` 指定远端。该批准不改变 Runtime Eval、Replay、Regression、Ablation
与 Promotion 的 `NOT_RUN` 状态，也不将 Change PASS 表述为生产候选晋升。
