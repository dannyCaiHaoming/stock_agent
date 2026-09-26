# `verify-research-evidence-to-cio-chain` 验收记录

本记录只验收 MRVL 一份旧截止点的正向、独立反证和非动作 CIO 链路，并另列 2026-09-26 当前来源检查。两个截止点不混用；这是研究链路验收，不是交易建议、历史回测或候选晋升。原始运行产物均留在仓库外，本文不复制凭据或完整账户资料。

## 冻结输入与真实执行

| 环节 | 证据与结果 |
|---|---|
| 旧研究来源 | `/private/tmp/activate-independent-skeptic-mrvl-20260924-v9/company-run` 与 `/private/tmp/activate-independent-skeptic-mrvl-20260924-v9/run`；证券 `US:COMMON_STOCK:MRVL`，截止点 `2026-09-23T16:19:01.418151Z`。Company 导入 manifest 拒收报告为空；多维 bundle 文件 SHA256 `513608204d9361d0943341fd09f0caecb568d2d33c8a9e3c4a5388a9d85618c8`，Skeptic package 文件 SHA256 `deb67f02e842a94a99df693a257da68d83ed020c9ee92bf64bd2f01054d937cb`。 |
| CIO 宿主补跑 | `/private/tmp/verify-research-cio-20260926-v4/run`，run ID `predecision-cio-38610d73-5ad6-4882-afff-6f071f005cc5`，显式 `gpt-5.6-terra`。来源包与原文件字节 hash 相同，package hash `104597b5956aef80ab9609dbf5a074e63df2f0a2a2f617ed49be085045360a26`；复制的来源 Gate 文件 SHA256 `7c6c4ea58bf7ce78b17d5f1951583016ae886d7090039ad7c4f79c258092556c` 与原来源相同。CIO Gate 按新 run ID 合法重绑定，bundle hash 改为 `d39a5da9f694372c9f8093575a647996c4ff0271c2f085846edc46356dfe2c4d`，两者仍为同一截止点、同为 5,804 条允许事实。进程退出 0、未超时、输入完整性未改变、终态 `COMPLETED_RESEARCH_SYNTHESIS`。Codex 事件含真实 `turn.completed` 和一次 `fixture_evidence.query`，交付 16 个 Evidence IDs。CIO 文件 SHA256 `31bb74dbecf136d76fd49169f8ddabc71e7db7803c6fef64a55c554e55610c5e`，Trace hash `712709a58b33f168a78982763597a97e4b18d980bb52d392888d3421c490025e`。 |
| 非动作边界 | 请求及实际级别均为 `RESEARCH_SYNTHESIS`；`advisory_only=true`、`complete_portfolio_decision=false`、Risk `NOT_RUN`，没有 `risk.json` 或 `decision.json`，正文没有买卖、仓位、金额建议。当前账户和用户持有期限未核验。 |
| 原始失败 | CIO v2 在本 Codex 环境权限阶段失败，v3 在宿主连接路由发现阶段失败；两份原始产物保留，不覆盖、不计为内容通过。v4 是唯一这次完成的 CIO 模型研究。 |

## 三域覆盖、正确性与实际消费

当前来源检查见 `/private/tmp/verify-research-current-data-20260926-v6`：新截止点 `2026-09-26T12:25:14.033288Z`，Gate 允许 5,033、排除 422、冲突 10。该批次仅证明当时有界采集和标准化状态，**不进入上述旧截止点 CIO**。旧链路的 invocation 级消费表为 `/private/tmp/verify-research-evidence-audit-20260926-v13/consumption.json`，SHA256 `bfb4a665f26184d46fff13fe611e20dc6467aee58cfa73cc9e58809c33d21c18`；中文摘要在同目录。核对入口已验证 Company 导入来源与报告 hash、CIO 来源运行/截止点/来源包和 Gate 复制；错配目录确定性拒绝。状态区分来源尝试、Gate、工具交付、报告引用和 CIO 报告清单；`event_file_presence` 仅证明日志文件存在，不是完整执行证明。计算附件父资料仅可证明整体输入关联，不能精确归因到某个指标或模型注意。

| 域 | 当前来源与正确性抽查 | 旧截止点实际使用与限制 |
|---|---|---|
| Company | SEC 财务/披露与 Yahoo 身份、事件、预期等已取得。SEC 原始 FY2026 diluted EPS 为 3.07 USD/share，主体、2025-02-02 至 2026-01-31 完整实际期间及披露时点与标准化事实一致；财务史总体仍 `PARTIAL`。Moomoo OpenD 在本执行环境不可达，治理/机构/部分分部补充不能称为当前可用。 | Gate 允许 1,217 项；26 组有交付，17 组被报告直接/间接引用。旧完整配置 Company 确实查询并引用了完整期间 EPS；另一失败实验的“目录可用但未查询”仅归属于其自身 invocation。CIO 明确把 2026-09-21 价格与 FY EPS 称为不同步的受限历史观察，不误写成前瞻估值或目标价。单季收入/毛利/经营利润、累计经营现金流及期末资产负债表期间没有互换。 |
| Macro | BLS CPI/就业、Treasury 收益率与 Fed 文本已取得；原始 2026-09-25 Treasury 2Y/10Y/30Y 数值和 2026-08 CPI 指数与标准化值/单位一致。BLS/Treasury 历史首发 vintage 未独立证明，不得用于更早 PIT 回放；Moomoo 补充不可达。 | Gate 允许 313 项；8 组有交付且被报告引用。Macro 报告为 `LOW_CONFIDENCE`，CIO 仅作利率/融资条件经客户资本开支传导的条件推理，同时写出客户投资保持稳健的反向情景；没有把宏观观察冒充 MRVL 已实现业绩。 |
| Market | MRVL、SPY Yahoo 日线和板块代理取得；抽查 2026-09-25 两者原始与规范化 close、交易时段/币种一致。`provider_close` 不保证历史复权，`historical_return_eligible=false`，不能充当严格回测收益序列；Moomoo 市场宽度/统计补充不可达。 | Gate 允许 4,274 项；17 组有交付，13 组被报告引用，另 3 组属于计算附件父资料关联。Market `SOURCE_LIMITED`、Technical `COMPLETE`：CIO 区分 MRVL 20 日相对修复与 60 日相对 SPY 落后及高波动；SPY/XLK 只是市场背景，HYG 只是 ETF 代理而非信用利差。 |

## 内容只读复核

复核直接读取既有 Company、Macro、Market、Technical、Skeptic 正式报告及 v4 CIO JSON/正文，没有修改任何原始报告或启动额外模型。Company 以实际完整财年 EPS、单季财务、累计现金流和期末余额支撑有限正向 Thesis，明确价格与盈利期间错配、MD&A 文本冲突及客户/供应/整合缺口；不把重组后短实际期间当完整财年。Skeptic 首轮按原执行证明仅接触冻结 Gate IDs 与研究范围，没有正向 Claim；三项公司特定挑战分别是客户与数据中心集中、供应/贸易/替代、收购整合及或有成本。CIO 对其分别 `PARTIALLY_ACCEPT`、`ACCEPT`、`PARTIALLY_ACCEPT`，明确降低盈利持续性、收入/毛利转换和财务灵活性的判断置信度，并列出需要的后续验证。CIO 的 8 项关键事实、两条 Macro/Market 传导和低置信度结论具有具体来源与期限，不是仅复制正向结论。

来源清单共 10 份报告，**不等于 10 份有效研究**。其中 `RESEARCH_REPORT` 为 `FAILED`，失败原因是 `RESEARCH_MATERIALS_ARTIFACT_REF_INVALID`；该辅助维度不属于现有六项核心下游前置，报告无 Claims，CIO 将独立研报不可用列为限制，未引用其正文作为事实。它不得改写为 `SOURCE_LIMITED` 或 COMPLETE，亦不证明本次新增的悬空观察条件纠正路径曾在真实宿主运行中触发；该纠正路径由聚焦测试验证。`FUNDAMENTAL_EVENT` 和 `INDUSTRY_COMPARISON` 分别保持合法 `INSUFFICIENT_EVIDENCE`，Market 保持 `SOURCE_LIMITED`，不会因 CIO 完成而升级。公开独立研报正文、同行 PIT Evidence、市场宽度/信用利差、客户与订单、债务结构仍是明确缺口。

结论：本次**核心正反研究至研究级 CIO 的同源链路及内容验收通过**，但不宣称全部来源、辅助维度或未来交易建议已经完成。`RESEARCH_REPORT FAILED` 是保留的辅助处理失败，不是合法来源受限；若后续任务要求有效独立研报研究，必须另行修复材料引用并重新取得真实报告，不能复用本次 CIO PASS 冒充该能力通过。

## 聚焦验证与收尾边界

- 受影响六个 `unittest` 模块通过 228 项；`openspec validate verify-research-evidence-to-cio-chain --strict` 通过；`git diff --check` 通过。消费核对新增同源绑定拒绝、错配 Company/CIO 反例及失败报告状态提示；不改原 CIO 或上游报告，并以真实 v4 输入生成新 v13 核对。
- 本 Change 的实现差异限于三域消费核对、Company 缺口/失败反馈、研报条件引用纠正和采集记录最小修复。共享工作区的 Tiger/Luna 改动不属于本 Change，不纳入验收或未来 scoped 发布。
- 尚未执行 Runtime Eval、Execution Replay、历史收益回测或候选晋升。用户已于 2026-09-26 明确批准同步及归档；四份主规格已同步并通过 `openspec validate --specs`（20 项通过），Change 归档于 `openspec/changes/archive/2026-09-26-verify-research-evidence-to-cio-chain/`。提交与推送状态以 Git 历史为准。

独立只读 Reviewer 对本次 MRVL 核心研究链路给出 `PASS`：已核对 v4 来源文件字节、截止点、真实模型/查询事件、内容取舍和 v13 同源绑定；首次指出的任意 Company/CIO 目录拼接风险已由拒绝式绑定校验及错配测试修复。Reviewer 未修改文件、未启动模型或再次运行测试；其 PASS 仅限本 Change 的研究链路，不把 `RESEARCH_REPORT FAILED` 升级为有效研报、来源受限或真实纠正成功。
