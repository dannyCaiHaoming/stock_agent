# Macro / Market / Company 三域实施验收

日期：2026-09-20
范围：`align-macro-market-company-research-inputs` 的真实资料采集、PIT/Gate、正式多维研究消费、provider 降级和旧入口退役。本文不构成 Runtime Eval、Regression 或 Promotion 证据。

## 真实采集

使用已确认的 MRVL `PortfolioHandoff v3`、仓库外 source-access、锁定的 macOS/Python 3.13 live 依赖及宿主允许的只读网络完成一次确定性采集：

- 数据目录：`/private/tmp/align-macro-market-company-three-domain-data-20260920-v5`
- run_id：`host-three-domain-data-v5`
- Gate cutoff：`2026-09-19T16:51:56.453074Z`
- Gate facts：5,080
- MRVL Company facts：2,428；SPY benchmark facts：1,511
- Yahoo Market context：1,135；覆盖 SPY、11 个板块 ETF、TLT/UUP/GLD/USO、HYG 信用代理和 VIX
- Macro：6；覆盖 CPI、失业率、非农、10Y Treasury、Federal Reserve 政策正文和 BLS 已公布日历
- Options snapshot facts：151
- Market 24 小时新闻真实请求返回零条，保留 `MARKET_NEWS_WINDOW_EMPTY`，没有伪造新闻
- Company supplement 对 MRVL 为 `INSUFFICIENT_EVIDENCE`；SEC 财务/披露及 guidance 候选可用，OpenAlex 独立正文仍受内容 API key 限制

首次采集使用基础 Python，在 NASDAQ 阶段因缺 live 可选依赖失败且形成 0-fact Gate；该失败 run 没有被覆盖。安装仓库锁定依赖到 `/private/tmp` 隔离 venv 后，真实采集暴露并修复 Market snapshot cutoff 未覆盖实际获取完成时间的问题。显式历史 cutoff 仍保持严格 PIT 行为。

## 正式模型消费

宿主 launcher 运行：

- `/private/tmp/align-macro-market-company-three-domain-smoke-20260920-v9/run`
- 同一 Handoff、同一 Gate hash `e9c9c2a03c3f51eaf78e4a1ba8199d1fdbf36fca13fa9e22be90c6347b9be557`
- process exit 0，stage `PASSED`，源码完整性未变化

该 run 对三域形成真实引用：

| 域 / capability | 真实输出 | 引用闭合 |
| --- | --- | --- |
| Company / `FUNDAMENTAL_EVENT` | `LOW_CONFIDENCE`，6 条主张 | 10 个 SEC Evidence 均解析到 Gate，覆盖收入、毛利、经营利润、净利润、EPS、OCF、CapEx、R&D、SBC、稀释股数 |
| Macro / `MACRO_CONTEXT` | `LOW_CONFIDENCE`，5 条主张 | 8 个引用全部闭合：BLS 3、Treasury 1、Federal Reserve 1、SEC 公司敏感性 3 |
| Market / `MARKET_STATE` | `SOURCE_LIMITED`，4 条主张 | 22 个引用全部闭合，其中 Yahoo 18；HYG 仅按 ETF 代理解释，缺新闻正文和信用利差时准确降级 |

`RESEARCH_REPORT` 在该 run 因 issuer document 少 `retrieved_at` 被确定性拒绝。后续真实 run 证明该字段补齐后进入下一层校验，又暴露 `interest_disclosure` 仍为旧字符串；现已改为 schema 要求的 `{status, statement, location}` 对象并加入聚焦测试。独立研报正文仍是已知受限增强，不把 issuer material 冒充独立研究。

当时的只读消费检查对 `/private/tmp/align-macro-market-company-three-domain-smoke-20260920-v11/run` 返回：

- `status=PASSED`
- `structural_status=STRUCTURALLY_CONSUMABLE`
- `coverage_count=9`
- `decision_cutoff=2026-09-19T16:51:56.453074Z`
- `downstream_models_started=[]`

该检查证明冻结 bundle 可被下游解析，不表示完整组合决策或 Promotion PASS。不同模型批次对 Fundamental 的置信状态存在差异；验收依据是引用闭合和准确降级，不要求模型产生乐观结论。

## 实施中发现并关闭的问题

1. Market 实时请求开始时刻早于实际 `retrieved_at`，旧 snapshot cutoff 导致 `COMMON_STOCK_MARKET_CONTEXT_PIT_INVALID`；现由实时批次最终 cutoff 覆盖实际完成时间。
2. 三源 supplement batch 先冻结，Macro/Market 合并后总 Gate cutoff 更晚；旧代码错误要求两者相等。现要求 batch cutoff 不晚于 Gate，且 batch 的全部 Evidence 必须属于 Gate。
3. Provider coverage 曾以 supplement 失败覆盖同 provider 的 base Evidence。现 base Evidence 存在时，补充层失败汇总为 `PARTIAL`；最新零模型准备结果：SEC `PARTIAL`、Yahoo `PARTIAL`、Moomoo SG `SOURCE_LIMITED`、BLS/Treasury/Federal Reserve `AVAILABLE`。
4. SEC issuer document 缺 `retrieved_at` 且 `interest_disclosure` 类型错误；两项均已按 v2 document schema 修复并加入断言。

## 自检与回归

- 裸命令 `python3 scripts/council-dev.py self-check` 按现有控制面返回 `SELF_CHECK_COMMAND_NOT_ALLOWED`；它不是无参数测试套件，未伪装为 PASS。
- `self-check trace-check` 对多维专项 run 返回缺少 `decision_trace.json`，因为该 validator 只适用于完整 Council run；记录为不适用，不作为失败豁免。
- 多维专项的权威只读 validator `check-multidimensional-consumption` 已通过。
- 实施前/后对照集合：165 项，164 项通过，唯一失败仍是实施前已记录的旧工具集合断言差异。
- 最新 topology / multidimensional stage / Market PIT 聚焦集合：36 项通过。
- 最新 multidimensional contracts / stage / topology / Market 聚焦集合：55 项通过。
- 全仓 `unittest discover` 进入仓库既有环境、历史 fixture 和 promotion/ablation 慢测试后人工中止，不能记作 PASS，也不作为本 Change 回归证据。

## 剩余边界

- 公开独立研报正文仍 `SOURCE_LIMITED`；不能用 SEC issuer material 替代。
- 本次 Handoff 只有 MRVL 一只普通股，因此 Macro 跨至少两只持仓的差异传导被准确标记 `NOT_APPLICABLE`。
- Moomoo supplement 复用了 Research Memory 中的既有受限观测；Moomoo 不可用没有阻断 SEC/Yahoo/Macro/Market 核心链路，也没有回退 Cookie 或私有 API。
- 初始独立 Change review 返回 `FAIL`，其阻塞已由 v20 正式 Company 依赖链、v21 同批三域运行及 v22 当前版本复核关闭；最终独立复核现已通过，人工完成批准仍是 sync/archive/push 的前置条件。

## 人工边界接受记录

- 日期：2026-09-20
- 用户明确接受：公开独立研报正文仍受访问限制，维持 `SOURCE_LIMITED`，作为不阻断本 Change 的增强项。
- 接受范围不包括 Company / Macro / Market 三域核心采集、Evidence Gate、正式消费、引用闭合、provider 故障隔离、历史兼容或旧 live 入口退役；这些项目仍须由独立复核确认。
- 本记录不是完整 Change 完成批准，不表示允许跳过独立复核，也不构成 Runtime Eval、Regression、Promotion、sync、archive 或 push 授权。

## 独立复核与补证状态

- 独立复核记录见 `reviews/development/align-macro-market-company-independent-review.md`。
- 初始 `CHANGE_REVIEW: FAIL` 的 issuer 目录重复、正文 hash、7.2 任务口径、独立研报分级与 Market 零结果 cutoff 问题已完成确定性修复。
- v16 单任务证明当前 Gate 可形成合法 `FUNDAMENTAL_EVENT`；v18 同批 Macro/Market 合法，但 Company draft 因缺失 gap `impact` 被 schema 拒绝，依赖的 `RESEARCH_REPORT` 未启动。
- v20 使用相同 Handoff/Gate/cutoff 通过最小 Company 依赖闭包，`FUNDAMENTAL_EVENT` 合法保存后才解锁 `RESEARCH_REPORT`；两份去重 issuer 正文被实际引用，独立研报保持 `SOURCE_LIMITED`。
- v21 在同一 Handoff/Gate/cutoff 下完成 8/8 同批三域运行，`all_reports_valid=true`、`coverage_complete=true`，Company、Macro、Market 均形成独立合法报告；消费检查返回 `PASSED / STRUCTURALLY_CONSUMABLE`。
- v22 在统一 Market Catalyst `1.2.0` 版本锁后再次证明当前 Company / Macro / Market 核心报告及 Company 依赖链；最后一个非核心 Options 子任务缺 Stop Hook，因此准确保留 7/8、`all_reports_valid=false`，不宣称本批全包成功。v21 的 Options 报告在相同 content hash、schema 与 topology 下仍可复用。
- 5.5、7.3 与最终独立复核已完成；当前只剩人工完成批准。批准前仍不得 sync/archive/push，一次真实成功不声明来源或模型长期稳定。
