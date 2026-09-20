# Why

当前系统已经具备 Company Analyst、Market Catalyst 以及 SEC + Yahoo + Moomoo Singapore 补充数据链路，但对外可见的研究域、Agent 拓扑和 provider 视图没有形成同一套权威表达：

- `live-us-equity/4.0.0` 是已退役的历史兼容 profile，却仍容易被误认为当前 live 入口；它只列出 Company Analyst、Skeptic、CIO，也没有表达 Market Catalyst 和 Moomoo 补充层。
- `MACRO_MARKET` 将宏观环境与市场状态合并为一个能力，无法稳定对应 Macro / Market / Company 三类研究输入，也不利于分别检查证据、缺口和时效。
- 产品文档和主规格仍把部分能力描述为延期至已归档的 `capture-futu-client-research-data`，与当前 SEC + Yahoo + Moomoo Singapore、OpenD quote-only 边界及实际完成状态不一致。

这类漂移会使使用者和维护者误判“当前有哪些研究输入、由谁负责、从哪里取数、哪些仍是缺口”，也会让后续实现继续围绕退役入口或过期状态扩建。

实施后的独立复核进一步发现 Company 消费闭环仍被输出交付阻塞：草稿从 1.1 契约生成，最终报告使用 2.0，嵌套字段约束分散；多次真实运行分别出现缺字段、额外字段与类型错误，结束时校验失败未形成可靠的原 Agent 有界纠正流程。剩余工作须闭合契约、反馈和依赖终态，不能仅增加提示词或重复完整模型运行。已接受公开独立研报正文受限，不豁免 issuer/IR 正文的真实消费。

本次交付进一步明确为：三域资料获取与研究消费闭环，以及旧 live 功能的定向退役。只有分类和配置不能补齐新闻、政策原文、跨资产与研报资料；历史可读也不意味着必须保留创建旧运行的完整链路。

# What Changes

- 新增当前持仓研究的权威 domain-input/topology 契约，明确 Company、Macro、Market 是研究输入域，而不是必须一一对应独立 Agent 的编排角色。
- 将新版本多维研究契约中的 `MACRO_MARKET` 拆分为 `MACRO_CONTEXT` 与 `MARKET_STATE`：前者负责利率、通胀、经济活动与政策环境，后者负责大盘、风格、波动、信用与市场状态；两者首期仍由 Market Catalyst 在隔离调用中分别承担，不新增 Agent。
- 明确 Company 域由 Company Analyst 承担公司基本面、公司事件和公司研报研究；宏观、市场策略材料按研究对象分别归入 Macro、Market，由 Market Catalyst 消费，材料类型不决定 Agent。
- 建立逐数据集覆盖清单，复用 SEC/Yahoo/Moomoo、BLS/Treasury 已有能力，补齐政策原文、经济活动指标、跨资产/信用环境、公开新闻与 issuer/IR 正文的有界获取、标准化、PIT、冻结 MCP 和实际研究引用。公开独立研报正文作为增强项：完成有界尝试后仍不可得时保留 `SOURCE_LIMITED`，不得用 issuer/IR 正文替代。新增免费来源按数据集准入，不再受“只能三家 provider”约束；三源补充包自身的契约继续保留。
- 核实 `wb-finance-skill` 原包、附带脚本、依赖服务、许可与免费额度及美股覆盖；同时将公开第三方归档 `infometa/workbuddyskills` 中的 `westock-data`、`neodata-financial-search` 纳入逐数据集候选审计。归档仓库只作为候选发现和代码审阅材料，不视为官方分发、可信数据源或可直接执行的生产依赖；只接入经锁版本、供应链审查和真实取数验证后可在当前环境独立使用的数据能力。原包未取得、平台专属依赖或无法验证时记录结论并采用公开来源路径，不以技能安装成功作为取数完成。
- 为当前研究入口提供可发现、可校验的 provider 视图：区分基础行情/披露 provider 与研究补充 provider，并引用既有 source plan、capability matrix 和版本/hash；Moomoo Singapore 仅作为受限补充层，不替代 SEC/Yahoo，也不扩大为交易或账户能力。
- 保留 `live-us-equity/4.0.0` 的历史内容和 hash 兼容性，将其显式标记为 retired/compatibility-only，并防止当前入口或文档把它呈现为权威研究拓扑。
- 更新 `multi-dimensional-holding-research` 的主规格与产品说明，移除对已归档 Change 的“延期”表述，改为按数据集能力矩阵和实际证据表达 ready、degraded、blocked 或 unavailable；归档本身不等于所有数据都可用。
- **BREAKING（旧运行创建入口）**：审计并退役旧 `prepare-live` 等仅服务旧 full live Council 的创建/派发分支及其专属测试；共享采集校验和必要历史读取保留。对旧 live 重复日志、中间产物及过期说明逐项审计，仅处理有明确恢复方式且不被引用的目标，不开展全仓库清理。
- 保持跨域主题/共识与非共识综合为下游综合职责，本 Change 不新增 Research Editor，不调整 CIO、Skeptic 的投资判断或浏览器信息架构；不承诺逐条复刻参考网页及其付费资料。
- 对能力枚举、schema、manifest 和旧产物读取采用版本化迁移：新运行写入新契约，历史 `MACRO_MARKET` 产物继续可读，不原地篡改冻结产物。

本轮补充交付：统一当前多维草稿与报告的结构约束并锁定版本/hash，在既有执行链路内支持每任务最多一次原 Agent 纠正，保留原始输出与完整校验；只有合法报告才能解锁依赖。先以确定性失败样例验证，再通过宿主入口验证 Company 依赖链和当前版本三域闭环。核对 `INDUSTRY_COMPARISON` 引用失败的归因并修复本次回归，不新增 Agent、通用重试平台或跨批次报告拼接。

# Capabilities

## New Capabilities

- `research-domain-inputs`: 定义三域实际数据获取与消费、免费来源准入、候选 Skill 可移植性、权威映射及旧 live 的定向退役和历史读取边界。

## Modified Capabilities

- `multi-dimensional-holding-research`: 将合并的宏观市场能力版本化拆分为独立宏观环境与市场状态输出，更新覆盖率、聚合、历史兼容和真实完成状态要求。
- `specialist-research`: 明确 Company Analyst 与 Market Catalyst 对 Company / Macro / Market 能力的职责边界、隔离调用规则和“不按数据源或页面栏目新增 Agent”的约束。
- `futu-readonly-research-data`: 将 SEC + Yahoo + Moomoo Singapore 的研究补充层纳入当前权威 provider 视图，并保留 OpenD quote-only、能力矩阵、降级和禁止交易边界。

# Impact

- 预计涉及当前研究拓扑/profile 或 manifest、能力枚举与 schema、多维研究 stage 绑定、Agent/Skill 版本绑定、provider discovery、产品说明和聚焦测试。
- `live-us-equity/4.0.0`、历史研究包及其 hash 不作原地修改；必要时通过新版本契约或显式 compatibility adapter 保持可读取性。
- 新来源适配和 2.0 契约先以非默认、可回滚切片落地；候选来源失败不得破坏现有 SEC/Yahoo/Moomoo、当前 Handoff 准备或历史读取。旧 live 分支只在当前生产调用已解耦且前后基线验证通过后退役。
- 不新增第二套编排器、缓存 Agent、数据源 Agent、券商交易能力或账户修改能力。
- 不以本 Change 自动触发 Runtime Eval、Regression、Promotion 或完整产品 Smoke；若实现改变真实模型分派或输出契约，验收阶段仅在显式授权后按宿主运行手册执行最小必要的真实 Smoke。
