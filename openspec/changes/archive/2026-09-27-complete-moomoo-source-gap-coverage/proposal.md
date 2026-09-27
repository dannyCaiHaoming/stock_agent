## Why

Moomoo OpenD 的宏观历史、经济日历、FedWatch 和 Dot Plot 已接入，且曾被 MRVL 研究使用；近期来源检查却因执行环境不可达而失去补充资料。新安装的 `moomoo-news-search` 能发现新闻、公告和评级线索，但尚未进入产品资料链，不能把搜索标题当作研报正文。需要按“接口存在→本批采集→Gate→Agent 实际引用”复核并补上最小缺口，而非重建宏观适配器或新增 Agent。

## What Changes

- 对现有 OpenD Quote-only 宏观与市场数据集进行有界宿主复验，区分 SDK 初始化/日志权限、OpenD 连通、登录/权限、数据为空与下游未消费；只修复复验确认的最小断点。官方宏观主源和当前 SDK/OpenD 版本锁不变。
- 将 `moomoo-news-search` 的公开搜索能力作为独立于 `moomoo_sg` OpenD 的标题/链接线索来源，优先补 Company 研报与事件发现及 Market 24 小时新闻缺口；核对证券身份、时间和来源层级，不将 `Research` 类别、评级快讯或转引升级为独立研报正文。
- 在需求中预先记录本次用户批准的最小只读权限范围与实际权限验收：本机 loopback OpenD Quote、SDK 必需日志目录、公开搜索 HTTPS 和仓库外临时运行产物。文档授权不等于操作系统或沙箱已授予权限；无法满足时显式标记环境阻断，不伪报来源失败，也不扩大到 Trade/账户能力。
- 用一个 MRVL 样本核对三域来源、Gate、查询交付和报告引用；Company 新线索只在现有多维 `RESEARCH_REPORT` 消费路径验收，不恢复到普通 Company 首版报告。未取得资料或正文时保留 `SOURCE_LIMITED`/`LEAD_ONLY`。不把已有 `RESEARCH_MATERIALS_ARTIFACT_REF_INVALID` 或历史回测、交易建议并入本 Change。

- 修复本次真实研究暴露的宿主首次定点执行阻断：在同一入口区分首次执行与终态重试，首次执行不要求旧终态记录、收尾不依赖旧研究包，仅运行 `FUNDAMENTAL_EVENT → RESEARCH_REPORT` 并生成任务级证明。补齐入口至收尾的确定性测试后再完成实际引用验收；保留原完整运行与重试行为，不新增编排器或放宽门禁。
- 对首次定点 `FUNDAMENTAL_EVENT` 真实草稿暴露的局部结构错误，仅由原子 Agent 在同会话内作一次有界自修：定位悬空观察条件引用或无依据 claim，不让 Python 改写研究判断，也不放宽 Evidence/Schema 门禁；失败继续阻断下游。
- 明确公开线索的研究用途与报告状态边界：Agent 核验后解释相关性及限制，正文充分性与配置失败仍按原契约判断；标题存在不强制降低整份报告状态，也不要求为引用数量拼凑主张。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `futu-readonly-research-data`：增加已实现 OpenD 补充接口的最小权限/环境阻断辨别和真实可用性复验契约。
- `research-domain-inputs`：增加公开 Moomoo 搜索线索的独立来源身份、Company/Market 消费边界与三域实际覆盖验收。

## Impact

预计仅涉及现有 OpenD Quote 客户端与来源采集/coverage、公开新闻线索的有限适配、PIT/Gate/研究资料路由、现有宿主定点入口及任务级收尾、聚焦测试和对应运行说明。`moomoo-news-search` 是发现接口与行为依据，个人 Codex Skill 的安装不视为产品 Runtime 已接线。不得改账户/Trade Context、券商凭据、CIO、Skeptic 信息隔离、风险或交易能力；不自动抓取或再分发第三方正文。
