# 实施验证记录

## 本轮结论与边界

本轮已修复 Research View 引用闭合、Company 数据适配和默认展示，并以真实 MRVL Memory 的只读预检、离线副本和经授权的稳定目录修复完成确定性验证。旧版“只读取 1500 条事实但页面已可用”的结论已被本记录替代。

浏览入口固定监听 `127.0.0.1`，不调用 Provider、模型或研究调度，也不写入或迁移 Research Memory。离线修复是与网页分离的显式命令，默认只读，执行时要求不存在的备份目录。本记录不代表 Runtime Smoke、Eval、Regression 或 Promotion 已运行或通过。

## 缺陷原因与修复

真实 MRVL 的 4 份旧 View 均声明引用 2068 条事实，但数据库只能按 View hash 解析 1500 条，缺失 568 条。逐条只读核对结果为：

- 4 份 View 均为 `reference_count=2068`、`resolved_count=1500`、`missing_count=568`、`ambiguous_count=0`、`unresolved_count=0`。
- 每一条缺失 hash 都能从 View cutoff 之前、内容地址与 snapshot 契约均校验通过的冻结对象唯一还原；所用对象 hash 为 `e8ad150119fcd616a69e60bc6d7e8e49de768f237c6a9484bf9d76bacafaa8e0`。
- 根因是 Gate 交付时加入 `freshness_status` / `freshness_policy_version` 后计算的 hash 被写入 View，而 Memory 中实际提交的是不含 Gate 临时上下文的事实版本；不是事实本体丢失。

当前实现使 `save_view` 在同一写事务内先把交付事实唯一绑定到已提交事实版本，再写 View；无法唯一绑定、事实损坏或引用缺失时不提交。旧 View 不被覆盖。独立修复工具只依据已校验冻结对象建立旧 hash 到既有事实版本的唯一映射，先备份，再新增修复 View 和 receipt；不改变事实、checkpoint、报告或原 View。

## 规格场景与确定性证据

| 场景 | 证据 | 结果 |
| --- | --- | --- |
| View 保存引用闭合 | `test_save_view_binds_gate_freshness_to_committed_fact_and_rejects_missing`、既有 Memory 保存测试 | freshness 临时上下文可唯一绑定；缺失事实拒绝保存 |
| 不完整 View 读取 | `test_missing_view_references_are_counted_and_not_selected_by_default` | 先做完整性核对再分页；默认跳过不完整版本，显式旧版本显示计数警告 |
| 离线修复 | `test_offline_reference_repair_is_backed_up_audited_and_idempotent` | 备份、receipt、checkpoint 不变、重复执行 `NO_CHANGES`、引用变动事务失败和 receipt 失败补偿回滚均通过 |
| 财务期间与曲线 | `test_financial_periods_price_volume_and_empty_pe_are_not_mixed` | 同日季度/累计不混合；原价/复权价有明确基准；价格与成交量分图；空 PE 不标 AVAILABLE |
| 披露正文与 Form 4 | `test_disclosure_timeline_prefers_body_and_decodes_form4_without_interpretation` | 同申报目录短句折叠，正文优先；Form 4 转为人类可读字段，不显示原始 JSON，不生成利好/利空判断 |
| 生产 Company 报告 | `test_report_output_is_allowlisted_and_private_context_removed`、`test_report_package_rejects_request_evidence_attachment_and_manifest_drift` | 使用 request schema/self-hash、实际 Evidence 集合及可选附件均闭合的 `equity-research-report/1.0.0` 样本呈现六章节；request、Evidence、附件或 manifest 任一不闭合即拒绝 |
| Company 补充研究 | `test_company_dimension_reports_are_exactly_bound_and_missing_is_not_absence` | 四类多维报告按 security/run/cutoff 精确绑定；绑定失败与未生成分开，缺失不解释为没有事件或观点 |
| 冻结附件版本 | `test_company_uses_only_exact_view_cutoff_frozen_visual_attachment` | 仅采用 security、cutoff、run、package/bundle hash 全匹配的附件 |
| Macro/Market 选版 | `test_macro_market_and_shared_report_render_from_saved_artifacts` | 快照可显式选版；报告与计算只跟随其来源版本，不串入默认最新版 |
| 运行版本精确绑定 | `test_same_basename_runs_do_not_cross_bind_reports`、`test_macro_market_reject_mismatched_bindings_and_evidence` | 不同绝对目录即使 basename 相同也不串报告；cutoff/run 与 benchmark evidence 不闭合的报告/计算被隔离 |
| 无 View 降级 | `test_company_without_view_is_an_unfrozen_fact_catalog` | 仅显示“未冻结事实目录”，不宣称 View 完整，不生成当前指标和趋势 |
| 嵌套符号链接 | `test_memory_objects_directory_symlink_is_rejected`、`test_artifact_nested_directory_symlink_is_rejected` | Memory objects 及冻结产物任一祖先目录的 symlink 均不能越过准入根 |
| 只读、安全、并发与兼容 | `tests.test_local_research_browser` 其余测试及既有 Memory/visual/package 测试 | 缺库不创建、DML 拒绝、输入转义、完整事务读取和旧契约兼容均通过 |

聚焦回归命令覆盖 `test_research_memory`、`test_research_memory_chain`、`test_research_visuals`、`test_equity_research_package` 和 `test_local_research_browser`，共 58 项，全部通过。系统 Python 缺少项目既有 `exchange-calendars` 分发元数据时，首次组合运行在环境导入阶段失败；改用仓库既有锁定测试依赖目录后完整通过，没有修改采集逻辑或测试断言规避环境问题。

## 真实数据副本验证

先对稳定 MRVL Memory 执行只读预检，再使用 SQLite online backup 复制数据库并复制内容寻址对象到临时目录，在副本执行一次修复：

- 新增 4 份修复 View，保留 4 份旧异常 View；再次执行返回 `NO_CHANGES`，View 总数保持 8。
- receipt hash 为 `d64a24829193ac3e2033dec08996d8d6a2336ed0aa1b4f496f4eb242148b3e98`。
- 修复副本默认选择最新完整 View，完整性为 `2068/2068`，缺失与校验失败均为 0。
- 页面值逐项核对：营收 `2,739,300,000 USD`（2026-08-01，单季）、净利润 `308,000,000 USD`（单季）、稀释 EPS `0.33 USD/shares`（单季）、经营现金流 `1,244,300,000 USD`（年初至今）。证据页显示原值、单位、财务期间、`as_of`、公开时间、获取时间、SEC 来源和事实版本。
- 资本开支、现金、债务也能从当前 View 适配；真实历史 Trailing P/E、基准相对表现附件和模型报告仍缺失，页面以具体限制或空状态呈现，不伪造数据。
- 当前完整 View 可形成 7 个可读披露事件：2 个 Form 4 交易、2 个 Risk Factors、2 个 MD&A 和 1 个 Business 事件；其中 5 组折叠了同申报/期间/语义字段下的目录短句或重复片段，正文长度约 3,894–7,969 字符，折叠项仍保留来源与事实版本。
- 稳定 MRVL Memory 的报告索引仍为 0，四类 Company 补充研究均显示 `NOT_GENERATED`；页面没有把这一状态解释为“没有事件、没有研报观点或没有持仓变化”。

取得本次实际写入授权后，已在一个此前不存在的独立目录创建 SQLite 与对象恢复备份，并对稳定 Memory 执行同一修复。执行结果为 `REPAIRED`，新增 4 份修复 View，receipt hash 与副本一致。随后只读复核显示：

- 稳定库共 8 份 View；4 份新 View 均为 `2068/2068`，4 份旧异常 View 仍为 `1500/2068` 且标记 `already_repaired=true`。
- 默认页面选择截止时间最新的完整 View `5f36b00b59ade2d1d8ebf366d7c41080fd9682e8a6919589e32eeb50c5c090a7`，核心指标、期间和证据链接与副本一致。
- 旧异常 View 没有被删除或改写；事实、报告与 checkpoint 没有被修复程序更新。

## 浏览器视觉检查

在临时修复副本启动实际本机 HTTP 服务并完成以下链路：

- 桌面页首先显示四项核心财务卡片、View 完整性和期间口径；原始价格长表、View 列表及采集诊断默认不展开。
- 财务趋势按单一指标显示，价格与成交量分开；负值和限制码可见，空 PE 不出现空图。
- 从营收卡片进入证据页可见 22 条该字段的版本记录及三时间；返回后通过页面选择器切换到另一份完整历史 View，页面标题、链接和完整性同步。
- 约 391 CSS px 视口实测 `innerWidth=391`、`documentElement.scrollWidth=391`，页面无整体横向溢出；宽表保留在局部横向滚动容器。
- Macro/Market 的历史快照和来源绑定由确定性集成测试覆盖；真实 Memory 未配置这些冻结目录时显示独立空状态，不影响 Company。
- 在当前稳定 MRVL 完整 View 上实际检查事件时间线：Form 4 摘要显示交易代码含义、取得/处置、证券、数量、每股价格和交易后持有量；页面没有泄漏原始 JSON，并明确说明只解码 SEC 字段、不推断动机、重要性或投资影响。
- 窄屏实际读取事件卡和生产报告样例；事件卡正文、折叠片段与来源可连续阅读。报告样例使用有效 `equity-research-report/1.0.0` 原包，六个命名章节全部可见，claims/证据、assumptions、失效/重评、监控、数据缺口和置信度分别呈现；页面宽度与文档滚动宽度一致，无整体横向溢出。
- 桌面宽度复核报告页的摘要、章节和折叠详情层级；宽表仅在自身容器滚动。真实 MRVL 没有可供展示的模型报告，因此报告视觉验收使用契约有效的本地确定性样本，没有触发模型或写入稳定 Memory。

截图仅作为本机验收会话证据，未写入仓库。

## 已登记的数据缺口

以下均属于后续数据/产物补齐，不阻断本次只读浏览器交付，也不能在当前页面上被推断为“事实不存在”：

- 稳定 MRVL 仅执行过 `--prepare-only` 链路，尚无保存的 `equity-research-report/1.0.0` Company Agent 报告。
- 当前披露事实能形成 10-K/10-Q Business、MD&A、Risk Factors 和 Form 4 事件，但缺少系统化的 8-K、业绩新闻稿、电话会文字稿、管理层指引变动和通用公司新闻事件流。
- 尚无外部卖方/独立研究机构报告语料及保存的 `RESEARCH_REPORT` 多维研究产物；页面不会用 SEC 披露冒充外部研报。
- `FUNDAMENTAL_EVENT`、`OWNERSHIP_DISCLOSURE`、`INDUSTRY_COMPARISON` 多维报告在当前稳定运行中也未生成；确定性事实层仍可单独阅读。
- 当前 View 没有真实历史 Trailing P/E 序列；估值区域保留具体限制，不以单点或其他指标拼成伪历史。

后续补齐应沿用现有 Research Memory 和冻结运行产物契约：由采集/研究链生成并保存，浏览器只做精确绑定和只读呈现，不在页面请求中新增 Provider、模型调用或第二套调度。

## 尚待收尾

- 本次事件时间线、生产 Company 报告和多维报告适配已完成三轮独立只读复核。前两轮共发现 5 个 MEDIUM 和 1 个 LOW：重复披露版本来源丢失、request/Evidence/附件闭合不足、多维报告 evidence/source context 自证、验证记录测试名错误、生产报告状态映射不兼容、外部 research claim 自证；均已修复并补充正负例。
- 最终独立复核 `CHANGE_REVIEW: PASS`，无剩余 finding；复核方重跑锁定依赖聚焦 58 项、OpenSpec strict 和 `git diff --check` 均通过。该 PASS 不代表 Runtime Eval、Promotion、新模型验收或人工完成批准。
- 取得人工完成批准前，不同步主规格、不归档、不提交或推送。
