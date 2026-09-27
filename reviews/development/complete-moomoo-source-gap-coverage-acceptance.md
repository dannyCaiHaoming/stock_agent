# complete-moomoo-source-gap-coverage 实施记录

本记录仅保存脱敏的来源与验收摘要；原始供应商响应、SDK 日志、私人会话和账户信息不进入仓库。最终结论为 `CHANGE_REVIEW_PASS_WITH_LIMITATIONS`：来源、Gate、定点工具查询与一条有效公开线索引用已闭合，独立只读复核在限定范围内 PASS；用户于 2026-09-27 明确批准同步且归档。历史失败和先前复核结论保留在下文，不倒写为通过；这不是完整八维研究或候选晋升证明。

## 权限与 Quote readiness（2026-09-26）

- 当前宿主已能写 SDK 必需的 `.com.moomoo.OpenD/Log` 目录和 `/private/tmp`；未修改 `HOME`、SDK、OpenD、账户设置或全局权限配置。
- 经现有 `MoomooOpenDQuoteClient.readiness()` 实际读取：`OPEND_QUOTE_FEASIBLE`；region `SG`，loopback `127.0.0.1:11111`，SDK `10.10.7008`，OpenD server `1010`，检索时间 `2026-09-26T14:40:52.814097Z`，原始响应 hash `cd88f23d59ed99517b49eee19150bce9ddde5d43b9bc370b4551728ef968dedc`。这里只证明 Quote readiness，不证明各数据集均可用。
- 同一环境的公开新闻搜索仅作 HTTPS 连通检查：`MRVL`、`news_type=1`、`size=1` 返回 `code=0` 且 1 项；未读取正文、账户或交易数据。
- 上一沙箱环境的 SDK 日志权限拒绝属于另一次执行环境；不能因为本次 readiness 成功改写那次失败证据。

## OpenD 共享数据集有界读取（阶段性）

使用既有 `capture_shared_research_results` 一次读取，原始响应只留在仓库外 `/private/tmp/moomoo-shared-check.3cWJtq` 的内容寻址缓存；缓存中有 14 份成功 Quote 请求记录（readiness、8 个宏观历史、2 个全市场期权统计、FedWatch、Dot Plot、经济日历）。逐数据集 Normalize 结果：

| 数据集 | 本批状态 | Evidence 数 | 限制 |
|---|---|---:|---|
| `macro_history` | `PARTIAL` | 192 | 8 项现有来源/vintage gap；不代表官方历史版本 |
| `economic_calendar` | `PARTIAL` | 100 | 1 项分页/覆盖 gap |
| `fedwatch_expectations` | `AVAILABLE` | 3 | 市场预期，不是 Fed 承诺 |
| `dot_plot` | `AVAILABLE` | 12 | 供应商转引，不替代 Fed 原文 |
| `option_market_statistics` | `AVAILABLE` | 41 | 全市场统计，不归因 MRVL |
| `market_breadth` | `SOURCE_LIMITED` | 0 | `MOOMOO_QUOTE_CALL_FAILED`，没有原始成功响应 |

本次只执行来源读取与标准化；尚未把这批新的 Evidence 送入 Gate 或 Agent。Gate、工具交付和有效报告引用须在后续同截止点 MRVL 样本另验，不因上表的 `AVAILABLE` 自动升级。

## MRVL 同截止点确定性资料包（2026-09-26）

- 使用既有已确认的 MRVL 历史研究 Handoff，只验证资料链，不推断其仍为当前持仓或生成账户建议。来源配置和缓存均位于仓库外；批次 `/private/tmp/moomoo-coverage-three-domain-v2.INAcJf/data`，`run_id=moomoo-coverage-three-domain-v2-20260926`，Gate cutoff `2026-09-26T15:07:16.556796Z`。Gate `bundle_hash=a2cb20ba4621607a08929a39f1b0cc9659babcabd2db77c69cc6a8797e3495d0`，来源包 `bundle_hash=f779d90731eb7842bdd136bd292127b275debfb3a2274d3403577ac43f8cbf62`，补充捕获批次 `batch_hash=7b6e4f140d73593a818131a636844842cdb25f36649380c6a8b5ed42e8aebbea`。
- 首个准备批次因系统 Python 缺 `certifi`，在 NASDAQ 阶段 `ModuleNotFoundError`，Gate 为 0；它只证明环境失败，不是资料成功。使用既有 live venv 后，第二批发现公开新闻检索晚于基础 Gate cutoff，被 `RESEARCH_SUPPLEMENT_PACKAGE_FUTURE_EVIDENCE` 正确拒绝；已将检索前移到证券快照冻结前。失败批次均保留在仓库外，未计入通过。
- 第三批 Company-only 宿主 `--prepare-only` 成功冻结，Gate 中有公开 MRVL `research_discovery` 10 项及 OpenD 共享数据 348 项；但逐股 OpenD 仍复用了首批 `MOOMOO_SDK_UNAVAILABLE` 失败 checkpoint。修复后，仅对缓存的 SDK/loopback 环境失败强制重新检查，不把正常行情字段不足当作缓存损坏。
- 最终同截止点包 Gate 准入 5,838 项：Yahoo 4,211、SEC 739、Moomoo OpenD 794、公开 Moomoo 公司线索 10、官方 BLS 4/Treasury 4/Federal Reserve 1，另含基准/期权/派生及 Market 公开标题。OpenD 逐股补充本次有 `research_discovery` 383、insider 38、management 12、money-flow 9 等；共享宏观历史 192、经济日历 100、全市场期权统计 41、Dot Plot 12、FedWatch 3。来源尝试与 Gate 准入分列，数值是 Evidence 项数，不是独立经济事件数。
- `market_breadth` 为 `SOURCE_LIMITED/MOOMOO_QUOTE_CALL_FAILED`；逐股机构持仓为 `SOURCE_LIMITED/RESEARCH_SUPPLEMENT_FACT_TIME_INVALID`。二者没有作为成功资料进入 Gate。OpenD 的供应商宏观值不替代官方 BLS/Treasury/Fed；FedWatch 是市场预期，不是 Fed 指引，Dot Plot 需以 Fed 原文核对。
- 官方宏观快照 `FROZEN`：BLS 4、Treasury 4、Federal Reserve 1，Gaps 0。市场快照 `FROZEN`：价格/指数代理 1,135 项；Yahoo 24h 新闻请求 HTTP 200 但无合格项，公开搜索按既定一次后备得到 10 个候选，其中 1 个 `market_news_item/TITLE_ONLY` 进入 Gate，其余因不相关排除。这个标题不是正文、行情方向或宏观数值。
- 此三域批次 Company 公开搜索的 10 项 `research_discovery` 全为 `LEAD_ONLY`，且均属评级/研究新闻；尚无公告索引。未取得正文，不能填平 OpenAlex 独立研报正文限制。Marvelous/ETF/未来时点等误命中由聚焦测试证明排除。此处只证明采集、Normalize、PIT/Gate 准入；Agent 工具交付和实际引用见后续独立小节，未验证前不得升级为 `RESEARCH_VALIDATED`。
- 身份复核发现历史 Handoff 的 `display_name` 为中文，而同证券 Yahoo 身份资料含英文 `longName`；按同证券冻结身份使用英文发行人名重新做零模型准备，批次 `/private/tmp/moomoo-coverage-company-name.krMGNB/data`、cutoff `2026-09-26T15:19:59.816333Z`。公开线索 Gate 准入 11 项：`RATING_OR_RESEARCH_NEWS` 10、`NOTICE_INDEX` 1（Marvell Technology 8-K 索引），均为 `LEAD_ONLY`，请求数 2、正文 0。该更新发生在唯一获批模型调用之后，不能倒推那次 Agent 已见到或使用公告线索。
- 原有 `RESEARCH_MATERIALS_ARTIFACT_REF_INVALID` 属研报材料阶段独立缺陷，本 Change 不修复、不借公开标题绕过正文门禁。

## 一次获批 Agent 验收的真实终态

- 依据用户“最多一次”预算，从上述同截止点 Gate 经现有宿主 `--prepare-only`/`--prepared-run` 启动一次 MRVL `gpt-6-luna` Company 研究；准备目录 `/private/tmp/moomoo-coverage-agent-prepare.JCUmAV/run`。真实 `SubagentStart`/`SubagentStop` 均可见，未追加第二次调用。
- 该次模型通过只读工具实际查询 200 个有效 Evidence ID（SEC 194、Yahoo 3、OpenD 2、公开研究 1），没有查询或引用本 Change 新增的 10 条 `moomoo_public_news` 公司线索。一次额外 `query` 错误请求使用了 63 位 hash 的 Evidence ID；Gate 中对应合法 ID 有 64 位，工具正确返回 `UNKNOWN_EVIDENCE`，没有模糊匹配或静默修复引用。
- 子 Agent 生成了结构化草稿，但一条 `MRVL-growth` FACT 同时引用不同流量期间 Evidence，却未在 Claim 文字中保留全部起止日；确定性渲染以 `EQUITY_RESEARCH_FACT_PERIOD_LINEAGE_INCOMPLETE` 拒绝草稿。产品进程退出码为 0、未超时，且隔离源码前后完整；最终终态仍为 `FAILED/COMMON_STOCK_REPORT_SET_INCOMPLETE`，完成报告为 0/1。零退出码、Agent 已启动和部分工具查询均不能证明研究报告通过。Market 的新标题只完成确定性路由与 Gate 准入，本次未启动 Market Agent；Macro/Market 既有历史消费证据不自动证明本新标题已被引用。
- 结论：来源接入和 PIT/Gate 闭合；新增公开线索的真实 Agent 消费 **未验证**。在用户已批准的一次模型预算内不能继续补跑。此处不修改产品 Agent 提示词或扩大模型预算来追求形式上的完成；任务 3.1 保持未通过，待明确新预算/独立复核后再决定最小修复。

## 开发者自审（不替代独立 Reviewer）

- 新公开适配器只对固定 HTTPS 搜索端点发起无认证 GET，不跟随重定向、不取正文；原始响应仅留仓库外内容寻址缓存。产品侧只加入来源枚举、同一 Gate 和既有 Company/Market 路由，没有账户、Cookie、Trade、订单能力，也没有新增 Agent 或编排器。
- 数据源失败仅降级自身：Company 返回 `SOURCE_LIMITED`，Market 保留 Yahoo 原结果或 `market_news_24h` gap；BLS/Treasury/Fed 与 SEC/Yahoo 主职责未改。Market 标题经 24h、PIT 和市场相关性过滤，Company 线索经 ticker/发行人名及 ETF/同名排除，均不能提升为正文。
- 受影响的 257 项确定性测试、`openspec validate complete-moomoo-source-gap-coverage --strict`、`git diff --check` 通过。工作区存在其他 Change 和用户既有改动，本 Change 不提交、不推送、不归档；独立只读复核结果见下节。

## 独立只读复核与剩余验收路径（2026-09-27）

- Reviewer 只读核对本 Change 的规格、差异、真实 Quote readiness、原始缓存/Gate、工具事件、失败草稿、缺口与回退；未编辑源码、采集网络或启动产品。结论：权限范围、公开标题 `LEAD_ONLY`/`TITLE_ONLY` 语义、已有采集与 Gate、失败开放回退均通过；新增公开线索的有效 Agent 消费和报告引用未通过，不能宣称 Change 完成。
- 发现原先计划补跑普通 `COMMON_STOCK_RESEARCH` 的路径不适合验证新 Company 线索：其 `COMPANY_RESEARCH_EXCLUDED_DATASETS` 排除 `research_discovery`，启动 `evidence_catalog` 和按 `semantic_field` 查询范围都经过同一过滤。精确 ID 查询虽可读取更宽 Gate，但启动目录不提供 ID，且研究指令要求报告引用来自目录；人工注入 ID 不是正常消费证明。新线索的既有专用消费者是多维阶段的 `RESEARCH_REPORT`，不是旧 Company 首版报告。此处不为验收而放宽 Company 上下文或修改投资判断。
- 用户本次额外批准的一次 MRVL Company 模型调用**尚未使用**。`RESEARCH_REPORT` 的既有任务依赖 `FUNDAMENTAL_EVENT`，宿主任务恢复会自动执行最小依赖闭包，至少需要两次产品子 Agent 调用，因此不能把一次批准默认为两次。若还需证明新 Market 标题被 Agent 实际引用，另需一次 `MARKET_STATE` 调用；Macro 既有消费证明不代表新批次引用。
- 最小后续路径：先零模型重新准备同一新截止点的三域 MRVL Gate，并确定性确认多维 dispatch 中 `RESEARCH_REPORT` 可见新 Company 线索、`MARKET_STATE` 可见公开标题；再由用户明确调整相应调用预算，经既有宿主入口执行受影响任务及依赖，核对工具实际交付、合法引用和报告终态。若仍失败，任务 3.1 保持未完成，不把 `LEAD_ONLY` 升级成正文。
- `market_breadth` Quote 调用失败、逐股机构持仓事实时间无效，以及独立的 `RESEARCH_MATERIALS_ARTIFACT_REF_INVALID` 继续单列，不因本次复核或某一阶段 `PASSED` 被遮盖。公开来源失败时保留 SEC/Yahoo/官方宏观主流程；必要时撤回公开来源政策与采集接线，不重写既有冻结产物。

## 新同截止点三域零模型复核（2026-09-27）

- 首次复用本 Change 前一批的外置验收 Research Memory 时，`collect-common-stock-data` 返回外层 `FROZEN`，但逐股项为 `FAILED/RESEARCH_MEMORY_RAW_CLOSURE_REPAIR_INCOMPLETE`，Gate 准入 0，截止点退回 `2026-09-17T00:00:00Z`；原始批次 `/private/tmp/moomoo-coverage-three-domain-check.B3lWLX/data` 不计为成功。此处只定位该外置验收记忆目录的原始闭包问题，未修改或删除旧记忆，也不外推为用户生产记忆状态。外层 `FROZEN` 不得代替逐股 READY 和非空 Gate 检查。
- 改用全新的仓库外隔离验收记忆目录，未动旧目录；批次 `/private/tmp/moomoo-coverage-three-domain-fresh.AR0pz2/data`，`run_id=moomoo-coverage-three-domain-fresh-20260927`，统一 Gate cutoff `2026-09-27T01:35:07.646501Z`，`bundle_hash=84357fb93cc842348a17ade746bdfd7e8baf53e31887fb55c1ad3d9a516b0e37`。逐股准备 `READY`，Gate 准入 5,826；公开 Company `research_discovery` 11 条，公开 Market `market_news_item` 标题 2 条，官方宏观 Evidence 9 条（BLS 3、Treasury 4、Federal Reserve 1，加发布日历 1），均只表示本次资料准入，不表示模型已用。
- 零模型 `prepare-multidimensional-research` 目录 `/private/tmp/moomoo-coverage-multidimensional-prepare.8a6GCR/run` 成功生成 8 个既有研究任务。`RESEARCH_REPORT` 的 `allowed_evidence_ids` 包含上述 11/11 条公司公开线索，`MARKET_STATE` 包含 2/2 条公开市场标题；`MACRO_CONTEXT` 包含 330 条允许 Evidence（含官方与 OpenD 补充）。这是 Gate 到任务授权目录的确定性证明，尚非工具查询、有效引用或报告完成。`RESEARCH_REPORT` 仍依赖 `FUNDAMENTAL_EVENT`，因此新模型阶段至少两次调用；截至此准备步骤，模型调用仍为 0。

## 目标任务首次启动阻断（2026-09-27）

- 用户随后批准将额外预算调整为 `FUNDAMENTAL_EVENT → RESEARCH_REPORT` 总计最多两次产品子 Agent 调用；需求已同步限定这一入口与有效引用标准。对上述新准备的运行包尝试宿主 `--resume-multidimensional-task dimension_research_3` 时，启动前返回 `MULTIDIMENSIONAL_RETRY_BASE_NOT_TERMINAL`。原因是现有定点入口仅允许已存在 `invocation/process-result.json` 的终态运行重试，新包尚未首次运行；常规首次入口会派发全部 8 个维度，超出本次两次调用上限。未伪造终态或绕过宿主入口。
- 运行包内无 `invocation/process-result.json`、无 `subagent-events.jsonl`；此次**模型与子 Agent 调用均为 0**，新获批的两次预算尚未消耗。宿主外层命令因错误后继续打印目录而返回 0，不代表产品启动成功；以真实 Python 异常和缺少事件/终态为准。
- 需要在此 Change 中明确一个最小的“准备后首次定点执行”入口及失败闭包，或另行批准完整 8 维运行；后者明显超出当前预算，不应默认采用。当前任务 3.1 继续未完成，Change 不归档。

## 首次定点运行修复与新增研究阻断（2026-09-27）

- 现有宿主脚本新增 `--start-multidimensional-task`，仅对新准备包首次执行 `FUNDAMENTAL_EVENT → RESEARCH_REPORT`；旧 `--resume-multidimensional-task` 继续要求终态与旧 bundle。首次模式校验 manifest、Gate、dispatch、拓扑、Agent/Skill 内容 hash、任务闭包及目录未使用，在同一任务级 finalizer 收尾，不调用旧 bundle 合并。完成时仍是 `DEPENDENCY_CHAIN_EVIDENCE`，`complete_holding_research_bundle=false`，其余六项记为未运行。
- 零模型测试经宿主参数路由与 runtime launcher 模拟两项 Hook/报告生成；验证无旧 bundle 成功、重复/越权/篡改拒绝、上游无效阻断下游、旧完整运行与终态重试。公开 `research_discovery` 线索可通过 Gate、任务列表与查询进入合法 `SOURCE_LIMITED` 报告的 `claims[].evidence_refs`，未知 ID 被拒绝。旧 Memory raw closure 测试在项目 live venv 中通过；多维准备新增逐股 `READY`、preparation hash 与 cutoff 就绪检查，外层 `FROZEN` 不单独视为可研究。
- 使用原新截止点准备包 `/private/tmp/moomoo-coverage-multidimensional-prepare.8a6GCR/run` 真实启动首次定点研究。实际 `gpt-6-luna` `FUNDAMENTAL_EVENT` 子 Agent 1 名启动、1 名停止，输出 `RESEARCH_OUTPUT_JSON_INVALID`，没有保存有效报告；其回复称未收到 Hook 冻结包。`RESEARCH_REPORT` 因 `RESEARCH_DEPENDENCY_NOT_READY` 被拒绝，未启动。宿主最终退出码 7，`process-result.json` 的两项状态分别为 `FAILED` 和 `DEPENDENCY_BLOCKED`，剩余六项未运行，源码完整性未变。此次消耗已批准两项产品子 Agent 调用中的 1 项；不得将 Hook `DELIVERED` 当成模型已接收或消费。
- 初始 `FUNDAMENTAL_EVENT` Hook packet 紧凑 JSON 约 672,332 字节，超过项目已有启动上下文 256 KiB 上限。它是模型未看到上下文的强线索，但 Codex 具体传输机制未证实。仅对首次定点 Company Hook 响应增加有界序列化；同一冻结包新响应为 `FUNDAMENTAL_EVENT` 196,501 字节（782/782 精确允许 ID）、`RESEARCH_REPORT` 134,876 字节（402/402 ID）。仍保留输出 Schema、任务/工具身份、按指标分组的精确 ID；完整事实和期间通过原有只读查询取得。超过 256 KiB 会在模型前明确拒绝，不再把过大返回记录为可靠交付。
- 截至本记录，新有界 Hook 只经过确定性检查，尚未获真实模型重新验收；任务 3.1 与最终独立复核仍待完成。原一次失败运行保留，不能复用或改写为通过。剩余 1/2 调用不足以同时重跑上游并执行依赖的 `RESEARCH_REPORT`，后续真实研究必须先解决预算边界。

## 第二次真实定点运行与引用闭包修复（2026-09-27）

- 用户明确批准产品子 Agent 调用总上限由 2 增至 3。使用同一 Gate 和标准准备入口生成新目录 `/private/tmp/moomoo-coverage-initial-retry.b0CBHZ/run`，经现有宿主首次定点入口运行。紧凑 Hook 上下文下，`gpt-6-luna` 的 `FUNDAMENTAL_EVENT` 实际输出了结构化草稿；此前非 JSON 阻断未复现。该次消耗第 2 次产品子 Agent 调用，累计 2/3。
- 冻结草稿含四条 claim；首个 `observation_conditions[0].claim_refs[1]` 引用 `mrvl_ai_demand_continuity`，但四条 claim ID 中没有它。既有确定性校验以 `DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING` 拒绝保存；`RESEARCH_REPORT` 因上游报告未就绪未启动，宿主退出码 7。合法 JSON、Hook 交付或草稿已产生均不等于研究报告完成。
- 旧同会话结构修复只覆盖 `RESEARCH_REPORT` 的这种错误。现限定为本次首次定点 Company 模式的 `FUNDAMENTAL_EVENT` 追加一次同子 Agent 修复机会：给原 Agent 返回上述悬空位置及现有 claim ID，由其重交完整草稿；Python 不删除引用、不补造 claim，不放宽 Schema/证据闭包。真实失败草稿可生成约 80 KiB 的有界修复请求；零模型 Hook 测试覆盖修正后保存、第二次仍错误即失败，以及完整运行和旧重试不受影响。
- 剩余 1/3 次调用不足以在全新准备包内执行 `FUNDAMENTAL_EVENT → RESEARCH_REPORT` 两项依赖任务；未获进一步明确批准前不启动新的产品研究。旧两次失败和各自报告/事件原样保留。任务 3.1、最终独立复核与 Change 归档仍未完成。

## 第三次真实定点运行：无依据 claim 被拒（2026-09-27）

- 用户批准调用总上限提高到 5。由同一截止点 Gate、同一已确认 Handoff 与候选池，经标准准备入口生成全新目录 `/private/tmp/moomoo-coverage-final.JykYl0/run`；版本绑定与 `gpt-6-luna` 模型保持一致。宿主首次定点入口实际启动一个 `FUNDAMENTAL_EVENT` 子 Agent，本次增加 1 次调用，累计 3/5。
- Agent 形成结构化草稿，但 `mrvl_valuation_unassessed` 是没有 Evidence、研究 claim、文档、假设或计算引用的 `INTERPRETATION` claim，内容为当前价格、估值附件及计算条件不足，不能形成估值结论。同一缺口已在 `data_gaps` 中陈述。现有报告契约以 `DIMENSION_REPORT_CLAIM_UNGROUNDED` 正确拒绝该 claim；本次未保存有效基本面报告，依赖的 `RESEARCH_REPORT` 被 `RESEARCH_DEPENDENCY_NOT_READY` 阻断，宿主退出码 7。其余六个维度未运行。
- 这与上一轮的 observation condition 悬空引用不是同一错误；目前没有获准将它纳入同会话修复范围。剩余两次调用恰好只够一条全新两项依赖链，不再盲目重跑。待确认最小范围修补后须先通过确定性测试，再决定是否使用剩余额度；若不批准，则 3.1 与最终独立复核保持未完成。
- 用户随后明确批准该最小修补。当前 Hook 只在首次定点 `FUNDAMENTAL_EVENT` 为此错误返回 `claims[3] / mrvl_valuation_unassessed` 给同一子 Agent；真实草稿生成的请求为 78,030 字节，低于 256 KiB。Python 不改原草稿，旧完整运行与终态重试不新增此修复。零模型测试覆盖同子 Agent 修复成功、第二次仍错误即失败及其他模式不受影响；受影响的 67 项测试、OpenSpec 严格校验与差异检查通过。剩余两次额度仍只用于一条全新依赖链，不自动超额重试。

## 第四次真实定点运行：截短引用及诊断纠正（2026-09-27）

- 同一冻结 Gate 与模型经标准准备入口生成 `/private/tmp/moomoo-coverage-final-v2.VRORw3/run`。宿主首次定点入口只启动一个 `FUNDAMENTAL_EVENT` 子 Agent，累计产品子 Agent 调用 4/5。报告草稿在 `observation_conditions[1].evidence_refs[0]` 使用截短的 `ev-sec-258b216044e721c548e3e1f1d1e2f0`；同一草稿的 `mrvl_fe_claim_cash_quality` 已引用完整合法的 `ev-sec-258b216044e721c5485508a9c54e0d0cd82f5c3cedfc5dd8f28b0e69fefb12f0`。Gate 没有截短 ID，`EVIDENCE_CLOSURE_FAILED` 拒绝报告正确；`RESEARCH_REPORT` 未启动，宿主退出码 7，其余六项未运行。
- **诊断纠正**：先前仅看到 `mrvl_fe_claim_valuation.evidence_refs=[]` 就称其无依据，这一判断不准确。该 claim 的 `assumption_ids` 实际引用已有的 `mrvl_fe_assumption_valuation_inputs`。新增诊断仅定位到截短 Evidence ID；只在内存中改正这一处且保留全部四条 claim，完整封装校验即通过。原先同时移除估值 claim 的内存试验不能证明该 claim 非法。原始文件从未写回，以上均非有效产品报告或 Agent 自修证明。
- 多问题同时定位仍有助于后续调试，但第四次真实草稿不是多错误共存的证据；该场景由合成反例验证。用户随后批准总上限提高到 6 次，目前已用 4 次。任务 3.1、最终独立复核及归档继续未完成。

## 轻量调试定位补充（2026-09-27）

- 首次定点报告失败时，现有 Hook 的 `output_capture.diagnostics` 记录阶段、首错、任务 ID、已定位的具体字段路径；终态 `process-result.json` 的对应 `task_outcomes[].diagnostics` 保留同样摘要。该摘要依附已有提交次数、原始草稿路径与 hash，不额外建日志系统。
- 扫描范围为非法 Evidence 引用、无依据 claim 和观察条件悬空 claim 引用；最多 32 项，保留发现数量和截断标记。文本型或过长的标识只记 hash，不复制研究正文/工具载荷。`NO_KNOWN_ISSUES` 只代表未发现这三类问题，不能当完整报告通过；无效 JSON、任务绑定缺失或诊断读取失败均返回 `UNAVAILABLE`，保留原首错。
- 同时覆盖三类错误的合成反例、合法假设引用不误报、原草稿不变、诊断有界与无效输入、失败依赖仍阻断及进程结果含定位信息。真实第四次草稿定位为 `observation_conditions[1].evidence_refs[0]`；本轮未新增模型调用或改写历史运行结果。
- 验证：`python3 -m unittest tests.test_multidimensional_stage tests.test_host_proxy_scripts -q` 共 69 项通过；OpenSpec 严格校验与差异检查通过。第三次真实草稿定位为 `claims[3] / mrvl_valuation_unassessed`，第四次只定位上述截短引用。诊断已接入下一次 Hook/进程结果；既有失败文件保留原样，真实 Agent 自修和公开线索引用验收仍待完成。

## 首次定点同会话引用修正的确定性验证（2026-09-27）

- 仅在首次定点 `FUNDAMENTAL_EVENT` 的第一次提交出现可定位的非法 Evidence ID、无依据 claim 或悬空观察条件 claim 引用时，Hook 向同一子 Agent 反馈诊断中全部已发现位置和原草稿；第二次提交仍经过原 Schema、Gate 和报告门禁。诊断缺失、截断、报告的非法 ID 与定位结果不一致或修正请求超过 256 KiB 时，不提出不完整的修正要求。Python 不自动替换 ID、不改写主张，其他模式未扩展。
- 用第三、四次原始失败草稿只读生成修正请求：分别准确定位 `claims[3] / mrvl_valuation_unassessed`、`observation_conditions[1].evidence_refs[0]`，请求约 80 KiB、81 KiB。第四次的合法估值假设引用不被误判为无依据。合成同会话测试覆盖多问题一起定位、修后保存、第二次失败终止、诊断不完整拒修和旧 `RESEARCH_REPORT` 行为保留。
- `python3 -m unittest tests.test_multidimensional_stage tests.test_moomoo_public_news tests.test_research_supplement tests.test_common_stock_research_contracts -q` 共 179 项通过；OpenSpec 严格校验与 `git diff --check` 通过。此处是零模型修补证明，非真实 Agent 自修或报告引用证明；真实依赖链仍需使用剩余 2/6 次额度验收。

## 第五、六次真实定点研究与新增线索消费缺口（2026-09-27）

- 使用同一冻结 Gate、已确认 Handoff 与模型，经标准准备入口生成 `/private/tmp/moomoo-coverage-final-v3.77vjR3/run`，并由现有宿主首次定点入口执行。`FUNDAMENTAL_EVENT` 第一次提交在 `assumptions[1].evidence_refs[0]` 使用非法 SEC ID；Hook 反馈精确位置，原子 Agent 在同一会话第二次提交通过完整门禁，报告保存为 `LOW_CONFIDENCE`。没有由 Python 猜测或替换 ID，也没有额外启动上游子 Agent。
- 依赖的 `RESEARCH_REPORT` 随后实际启动、保存 `SOURCE_LIMITED` 报告。任务级证明 `PASSED`，两项依赖闭合，宿主退出码 0、源码完整；但 `complete_holding_research_bundle=false`，其余六项明确未运行。本次累计 6/6 次产品子 Agent 调用；两项任务保存只证明这条定点链有效，不证明完整八维研究。
- 同一研报任务允许目录中有 402 项，其中公开 Moomoo 公司线索 11 条；实际研报 Agent 的 3 次成功 query 只涉及 2 个 SEC Evidence ID，公开线索查询 0/11，最终 3 条 claim 的公开线索引用 0/11。报告正确说明只有两份 SEC 发行人正文、独立第三方研报正文为 0，没有将评级标题冒充研报结论；但按本 Change 的明确验收标准，新增公开线索**尚未被报告消费**，任务 3.1 不能勾选。当前有效报告与历史失败均保留，不倒算通过。
- 对账定位为任务输入显著性问题：同一目录内 383 项 OpenD 评级快照与 11 条公开标题混列，原 `company_material_coverage` 只标明独立正文数为 0，未单列标题线索。不能据此推断模型内部动机；只在现有 `RESEARCH_REPORT` 输入中新增已准入公开线索 ID 列表，并要求至少查询一条、在已有 claim 引用中仅声明标题/链接线索存在与正文未核验。没有公开线索时不加该要求；`SOURCE_LIMITED`、材料层级、Schema、工具和其他维度不变。
- 零模型使用同一 MRVL 冻结资料重新准备 `/private/tmp/moomoo-coverage-lead-packet.3rxNHV/run`：`RESEARCH_REPORT` 明列 11/11 原样且允许的公开线索 ID，首次 Hook 上下文 136,436 字节；`FUNDAMENTAL_EVENT` 196,501 字节，Macro/Market 均无新增线索指令。新包未启动模型。聚焦测试 198 项通过；后续真实消费验收需新的明确调用预算，未获批准前不启动。

## 线索用途与整体报告状态边界修补（2026-09-27）

- 用户批准诊断提出的三项修补。Proposal、Specs、Design、Tasks 已同步；任务首页改为实际 6/6 次额度已用、两项链路通过但公开 Company 线索查询/引用为 0/11。历史决策和运行记录保留，并注明历史计数不代表当前剩余额度。
- 现有 `RESEARCH_REPORT` 提示取消“只要有标题就保持整体 SOURCE_LIMITED”。正常任务至少查询一条线索，采用时解释其对研究问题的具体核验用途和限制；可排除不相关、重复或无新增价值项并记录原因。线索保持 LEAD_ONLY，报告状态按正文对问题的实际覆盖判断。材料准备为 BLOCKED_CONFIGURATION/FAILED 时不追加线索查询/引用要求，原失败指令优先。
- 测试使用实际任务构建器，替换材料导入边界为合成输入，覆盖 SOURCE_LIMITED、READY 且有已核验正文、BLOCKED_CONFIGURATION、FAILED 四种状态与公开标题并存；检查正文元数据、状态、工具权限和状态 Schema 保留，并复用没有公开标题的既有检查。测试证明输入和契约兼容，不证明模型已经遵循语义指令。
- 相关 68 项确定性测试通过：`python3 -m unittest tests.test_multidimensional_stage tests.test_research_materials_stage tests.test_research_consumption_audit -q`。首次运行有一项旧测试因固定 `/tmp/bound-research-run` 不含所需 manifest 而失败；已改用既有合成准备流程构造临时运行，随后全部通过，未改工具生产实现。OpenSpec 严格校验与差异检查通过。
- 同一冻结 MRVL 零模型准备目录 `/private/tmp/moomoo-lead-boundary.xYvdcm/run`：公开 Company 原样允许 ID 11/11；研报首次上下文 136,826 字节，Fundamental 196,501 字节；Macro/Market 没有新增线索指令。新目录未启动模型，3.1 真实消费验收及 3.3 独立复核仍未完成。本次不新增模型额度、不归档。

## 第七、八次真实定点研究及三域逐层对账（2026-09-27）

- 用户随后明确要求继续补跑，将累计产品子 Agent 上限增至最多 8 次；以同一冻结 MRVL Gate、同一准备目录 `/private/tmp/moomoo-lead-boundary.xYvdcm/run` 经现有宿主 `--start-multidimensional-task` 只启动 `FUNDAMENTAL_EVENT → RESEARCH_REPORT`，未启动完整八维研究。本次两名子 Agent 启停，累计 8/8；宿主退出码 0，`process-result.json` 显示 `PASSED`、两项 `SAVED`、失败 0、源码完整性未变。任务级 `task-execution-proof.json` 为 `PASSED/DEPENDENCY_CHAIN_EVIDENCE`、依赖链闭合、`complete_holding_research_bundle=false`，其余六项明确 `NOT_RUN`。本次两项报告均为 `SOURCE_LIMITED`；研报内容 `report_hash=33945c724114b9311d6a2cf38f62451bb21af8d71a2a4605bde6b4cd39e25e3a`、实际文件 SHA-256 `199fef121110b5e3f78883b3ae4ad2767e89a9032c46e420b8a6d83336e13c06`，不能把任务成功等同资料充足。
- 统一来源截止 `2026-09-27T01:35:07.646501Z`，Gate `bundle_hash=84357fb93cc842348a17ade746bdfd7e8baf53e31887fb55c1ad3d9a516b0e37`，准入 5,826 项。来源/权限/标准化层沿用前述同批零模型记录：Quote readiness 已实测，官方宏观来源与 OpenD 补充均进入 Gate，公开 Company `research_discovery` 11 条均为 `LEAD_ONLY`，公开 Market `market_news_item` 标题 2 条为 `TITLE_ONLY`；这些数量是冻结资料项数，不代表有效观点或模型注意力。
- Company：普通首版 Company 研究仍排除 `research_discovery`；本次消费者是多维 `RESEARCH_REPORT`。任务允许目录含公开线索 11/11；工具事件显示同一次研报调用成功查询 11/11；有效研报的 3 条 claim 中，1 条原样公开线索 Evidence ID 被直接引用（出现于 2 条 claim），其余 10 条虽查询但未引用。被引线索为 `moomoo-public-news:post:75471765`，发布时间 `2026-08-28T12:30:14Z`、检索时间 `2026-09-27T01:34:15.194175Z`，对应原样 ID `ev-research-supplement-0746668731641f2237eabb9f353f43df0712300bedb31381c8866e483dfaf45d`。Claim 仅说明标题涉及 MRVL、原文及作者假设未核实，不能概括外部观点；另一条 SEC 正文引用用于发行人经营事实，未伪装成独立研报。报告 `sufficiency=INSUFFICIENT`，明确记录独立 `BODY_VERIFIED` 研报正文为 0，保持 `SOURCE_LIMITED`。
- Macro：本批官方 BLS/Treasury/Fed 9 项、OpenD 宏观补充及既有 Normalize/PIT/Gate 范围由零模型包和历史检查证明；本次定点链没有启动 `MACRO_CONTEXT`，其工具交付和有效报告引用属于 `NOT_RUN/NOT_VERIFIED`。此前 MRVL 运行的适用消费证明不应冒充本批截止点 Agent 已使用。Market：本批公开标题 2/2 准入且 2/2 进入 `MARKET_STATE` 允许目录，但本次未启动该 Agent，实际查询和引用均 0/2；Yahoo 既有 24h 路由和同批价格快照保持，不把标题当成方向或宏观数值。只读消费审计原先误将 `moomoo-public-news` 的 `market_news_item` 默认归入 Company；已在现有 dataset→domain 表补 `MARKET` 映射并用一项聚焦测试验证，此修正仅影响审计呈现、不改变冻结 Gate 或产品研究。
- 剩余缺口继续单列：`market_breadth` 为 `SOURCE_LIMITED/MOOMOO_QUOTE_CALL_FAILED`；机构持仓事实时间无效，`relationships` 也为 `SOURCE_LIMITED`；公开标题没有独立研报正文；`RESEARCH_MATERIALS_ARTIFACT_REF_INVALID` 是独立材料引用缺陷，本 Change 未修。公司标题采集或 OpenD 补充失败时，仍沿用 SEC/Yahoo/官方宏观主流程的来源限定或 gap，不能提升为资料完整。至此任务 3.1 的新增 Company 线索消费验收已满足，随后进行最终独立只读复核；人工完成批准前不归档、不推送。

## 最终独立只读复核（2026-09-27）

- Reviewer 对修正后的验收记录、真实运行进程结果、任务级 proof、Gate、任务允许列表、工具事件、研报和报告内容/文件 hash 给出明确 PASS，范围仅为本 Change 的定点来源与 Company 线索消费验收。经复核指出并纠正“内容 hash 误写为文件 hash”的记录笔误；报告 `report_hash` 与实际 SHA-256 现分列且均已核对。
- 复核确认 Company 11/11 公开线索被研报工具查询，1 条原样 ID 在两条有效 claim 中引用，`LEAD_ONLY/body_verified=false` 未升格；Macro、Market 本轮均未运行，不能称本批已被 Agent 引用。`market_news_item → MARKET` 的只读审计映射与聚焦测试正确；原首次定点入口与旧流程兼容有零模型检查及本次真实宿主证明。
- 该 PASS 不涵盖完整八维研究、全部数据源充分性、独立研报正文或 Promotion。`market_breadth`、机构持仓事实时间、`relationships`、独立正文及 `RESEARCH_MATERIALS_ARTIFACT_REF_INVALID` 仍单列；8/8 调用预算已用满。任务 3.3 已完成；用户随后于 2026-09-27 明确批准同步且归档，Git 提交和推送仍须通过范围与敏感信息检查。
