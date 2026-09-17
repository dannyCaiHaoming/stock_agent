# complete-company-valuation-and-report-visuals 实施范围

## 基线与复用

- 基线核对时间：2026-09-17。
- `capture-futu-client-research-data` 当前为 49/56；已完成部分提供 SEC/Yahoo/Moomoo supplement sidecar、CompanyBackgroundSnapshot、冻结 Gate/MCP、候选披露与真实 AAPL 三源证据。
- 本 Change 复用 `research_supplement.py`、`research_supplement_mcp.py`、`common_stock_data.py` 的冻结接缝，以及 `collection.py` 已有 SEC 财务字段。它不修改前序 Change 的任务状态，也不复制 Stop Hook、launcher 等待屏障或三源准入任务。
- 既有 `valuation.py` 的通用算术、`technical_chart.py` 的相对表现 SVG 和 `research_output.py` 的 JSON/Markdown 同源校验继续保留；新功能通过独立契约和附件目录增量接入。

## 本 Change 文件归属

- 新增 `product/deterministic/equity_valuation.py`：当前/历史估值、TTM、PIT、比率和基本面确定性标准化。
- 新增 `product/runtime/equity_research_package.py`：估值、基本面、同行和图表附件的冻结、验证与查询。
- 新增 `product/council/research_visuals.py`：同源 chart-data、SVG、HTML、Markdown 与 manifest。
- 新增四份 runtime schema；扩展 Yahoo 估值字段、既有冻结研究消费和说明文档。
- 新增聚焦测试和本 Change 的真实验收/复核产物。

## 明确排除

- 不新增 Agent、第四数据源、交易接口、全市场扫描、通用 RAG、历史一致预期数据库或发布级 Eval/Regression/Promotion。
- 不把 Moomoo 身份/评级成功推断为估值字段权限；Moomoo 仅消费已验证允许方法返回的字段。
- 不把候选摘录当核实事实，不用当前股数/预测回填历史，不用固定阈值生成投资结论。

## 旧证据适用性

- `docs/development/sec-yahoo-moomoo-research-supplement.md` 证明三源接缝和部分背景字段可用，不证明五年 PIT 估值、完整基本面组或本 Change 图文报告。
- 前序 AAPL 真实包可复用其原始 SEC/Yahoo/Moomoo Evidence；本 Change 新计算、历史点、同行和图表必须生成新的附件与校验记录。
- 前序专项模型消费不覆盖新增附件；本 Change 只在确定性实现和真实资料矩阵完成后使用一次已授权联合专项批次。

## 默认实际采集清单与预算

| 资料 | 每目标公司上限 | 用途 |
|---|---:|---|
| 10-K | 2 | 年度财务、债务、经营定义与治理背景 |
| 10-Q | 4 | 季度/累计期间、指引变化和 KPI |
| 已申报业绩发布 | 4 | 指引与 GAAP–adjusted 调节 |
| DEF 14A/DEF 14C | 2 | 薪酬、控制权与关联交易 |
| 近 12 个月其他相关 8-K | 8 | 重大融资与管理变化 |
| 原文附件合计 | 32 | 超限记录为预算截断，不表述为未披露 |
| 结构化财务 | 近 8 季度/5 财年，估值 warm-up 独立 | 当前比率、趋势与 PIT 历史 |
| 同行 | 默认 2–3、最多 5 个固定候选 | 仅身份/业务依据、估值及构造同口径指标所需财务 |

## 2026-09-17 MRVL 运行修复基线

本节对应 OpenSpec Task 7.1，只固定本轮接缝实施范围，不改写旧失败结论。

### 旧失败证据锁定

- `reviews/development/complete-company-valuation-and-report-visuals-model-acceptance.md` SHA-256：`9f59d525d758ba107a390e32110de14b0415d499aecdf304a3b65c65842c0c40`
- `reviews/development/complete-company-valuation-and-report-visuals-model-acceptance.json` SHA-256：`caa06f8c7a39a05aa992f59a6dafca3be3ff869a914e15504aeb438b52945ca8`
- 后续实现和零模型检查只能引用这两份失败证据，不得把新状态回写到其中。

### 共享文件初始快照与归属

| 文件 | 初始 SHA-256 | 本轮归属 |
|---|---|---|
| `product/runtime/common_stock_stage.py` | `2e9087c7462387bb491c1dfb9750355636c99c3e02c30f1c4417ce5ee5cd2627` | 启动包、附件权限、超时清理、Coverage v1 归集 |
| `product/runtime/codex_hook_recorder.py` | `915fac7a274c432a3f1aef0304731832b9eac0d02f1da2d00125fa0e2b10ee49` | 实际查询/计算交付引用闭合；保留既有等待屏障 hunk |
| `product/runtime/nested_codex.py` | `d415355e51a8cfb42516c6580f661ee01e8fcadcf71411bc3c865d9a1946d4cd` | 仅复用命令构造器并增加隔离来源参数，不重做通用 launcher |
| `product/runtime/equity_research_package.py` | `d8c32e86a3a452e93b3f604020e724462d295b5b510a72b201cac34347d6f819` | 四类冻结附件查询和冻结计算索引 |
| `product/runtime/fixture_mcp.py` | `08619cf7f94ec785252fcc383cadae56eac6e49d2344a534f2ac3fa9ca299bad` | 将现有附件查询接入实际 `tools/list`/`tools/call`，不增加目录分页 |
| `tests/test_common_stock_research_contracts.py` | `81ec1821314db7c940e95d1a678b42732a31e7d3a2f76aad9223d610a472c406` | 普通股派发、归集、隔离与零模型门槛 |
| `tests/test_equity_research_package.py` | `5c7ac0b3412bfc815a3d6cecbb351735365c8786d1f15a16bc35317fcda994d5` | 四类附件、Gate 和引用负例 |
| `tests/test_nested_codex_launcher.py` | `78b2fcbd6633dba397b901fd8e637b432b5607bb57eb3248e1c199b462261e1a` | 命令边界和隔离来源检查 |

### 候选压缩 hunk 复核结论

- 复用 `common_stock_stage.py` 中已存在的三个方向：不在输出 Schema 重复完整 Evidence 枚举、不在 Company Analyst 目录注入逐日 OHLCV/volume、压缩重复的 request/identity 字段。
- 不原样接受当前 `evidence_period_index` 只保存 ID 的实现；本轮必须补回 semantic field 对应的期间、单位与 context 摘要，使紧凑索引仍能支持完整期间发现和冲突核对。
- 保留现有事实查询 `fixture_runtime.query`，不实现 `catalog.list`、cursor 或通用分页平台。
- `codex_hook_recorder.py` 中现有 parent-stop/wait hunk 属于前序等待屏障修复，本 Change 只在不撤销它的前提下增加交付引用记录；不把等待屏障重做为新的 lifecycle 平台。

### 明确不触碰

- 不修改 `capture-futu-client-research-data` 的 OpenSpec 状态或三源采集逻辑。
- 不启动产品模型、行情网络探针、OpenD、Runtime Eval、Replay、Regression 或 Promotion。
- 不自动恢复、覆盖或清理其他工作区差异；共享文件只做本 Change 可定位的增量 hunk。
