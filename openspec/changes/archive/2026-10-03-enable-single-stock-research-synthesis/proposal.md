## Why

用户希望只输入美国雅宝 ALB 就使用现有 Stock Agent 得到研究结论；当前公司/多维/反证入口仍绑定真实持仓 Handoff，CIO 的实现与 Schema 只接受 MRVL。需要开放不依赖账户的单股研究入口，而不是伪造持仓或绕过样例限制。

## What Changes

- 接受单只美股普通股代码、研究问题和资料截止点，生成独立的单股研究请求；不要求持仓、数量、成本、现金或 Mandate。
- 复用 SEC、Yahoo、Moomoo OpenD/新闻工具的现有准入、冻结、PIT、确定性计算与 Research Memory，建立同源 Company → 八维正向 → 独立 Skeptic → CIO 的研究链。
- 新运行明确区分 `SINGLE_STOCK_RESEARCH` 与 `PORTFOLIO_HANDOFF` 输入身份；程序装配技术绑定，模型只承担研究语义。旧持仓与历史报告保持原版本，不迁移旧包。
- CIO 不再按 MRVL 常量准入新合格研究包，而按来源请求、目标普通股及真实正反报告绑定准入；删除对新目标不适用的“MRVL 已清仓”上下文。
- 输出仍为 `RESEARCH_SYNTHESIS`：综合判断、业务前景、价格吸引力的依据或未知、主要反证、传导、研究期限和重评条件。不开放 BUY/ADD/HOLD/TRIM/EXIT、账户建议、金额、数量或交易执行。
- 以 ALB 同源真实研究链生成的中文报告作为首个非 MRVL 样本，本期交付收敛为“有限、可追溯的 ALB 首版研究综合”。明确执行、资料覆盖和结论质量的不同状态，不承诺完整年度风险覆盖或充分的 Macro/Market 研究。
- 补齐独立反证实际可发现的任务内资料目录，按需读取指标/期间/来源及章节类型而非盲扫编号；对齐交付结构与既有挑战取证门禁，保留一次原作者局部纠正。最终采用的事实、判断和重要反证仍须准确且有合法依据；未采用的上游疑点及未核验/未用于判断的资料可以明确保留，不要求本期逐项修复全部上游报告，也不把结构通过冒称内容通过。

### 本期交付范围调整（2026-10-03，用户已确认）

用户明确选择“收敛为限定版”。本期验收保留真实输入与执行链路、所采用事实/引用/期间单位、重要反证准确性、限制与结论一致性，以及账户隔离和禁止交易底线。年度风险正文未全面核验、既有 Macro/Market 窗口未用于定向综合，可以作为已披露的覆盖限制，而不是宣称资料不存在或传导已得到验证。

这是交付范围调整，不是原内容缺口已修复。原第五稿 FAIL、第六稿此前尚无独立裁定及全部失败原件保留，不回签旧运行或重记上游内容 PASS。现有报告及执行证据复用，不追加模型、上游重跑或其他任务联动。2026-10-03用户随后明确“我通过当前限定版验收，允许同步切归档”，已取得本期限定版人工内容验收与最终完成批准，按同一Change限定同步、归档及发布；不是原Reviewer裁定或旧完整标准PASS。更充分的风险研究和 Macro/Market 消费不在本期完成前提中，也不自动新建后续任务。

## Capabilities

### New Capabilities

- `single-stock-research`：非持仓单股输入、冻结资料及端到端研究结论的最小产品契约。

### Modified Capabilities

- `common-stock-holding-analysis`：增加非持仓请求分支，复用原 Company Analyst 与校验；原持仓分支不放宽。
- `multi-dimensional-holding-research`：资料准备、多维与独立反证接受真实单股研究身份，保持同源绑定和隔离。
- `portfolio-council-orchestration`：研究级 CIO 按目标与来源闭包准入，而非仅 MRVL 样例；保持旧兼容链和禁止动作边界。

## Impact

涉及既有宿主 launcher/CLI、采集入口、普通股/资料准备/多维/反证/CIO 准备与消费者、运行 Schema、历史读取和产品使用说明。特别检查 `product/mcp/live/collection.py` 的持仓采集依赖、各阶段的 `audit/portfolio-handoff.json` 读取、CIO Schema 的 MRVL const、提示和中文渲染。

不新增 Agent、Skill 推理职责、Provider、调度后端、通用绑定平台、自动重试、历史回测或绩效评分。与未实施的 `enable-historical-single-stock-advice-replay` 分开：本需求只做当前/合格冻结截止点的研究综合。实施和真实运行需后续显式 apply；本规划不启动模型、不提交或归档。
