# WorkBuddy 金融 Skill 可移植性与供应链审计

审计日期：2026-09-19
对应 Change：`align-macro-market-company-research-inputs`
归档仓库：`https://github.com/infometa/workbuddyskills`
锁定 commit：`78170571d08e7d38c6baf0a13ef805487bfa6dc2`（commit time `2026-08-17T14:47:37+08:00`）

本次只做固定提交的静态读取、hash 和 npm registry 元数据/压缩包完整性核验。没有安装 Skill、连接 MCP、调用数据接口、执行 `npx`、执行归档脚本或写入任何凭据。归档 README 明确说明第三方包可能各有许可且归档可能落后官方；目标包目录没有独立 LICENSE，故不能从“公开可下载”推断获准复制或生产使用。

## 总结结论

| 候选 | 本 Change 结论 | 可映射数据集 | 不能准入的直接原因 | 后续最小解锁条件 |
| --- | --- | --- | --- | --- |
| `wb-finance-skill` 原包 | `NOT_VERIFIED` | 未知 | 锁定归档中没有该名称的原始包，用户也未提供原始分发目录；无法核对脚本、依赖、许可、端点或字段 | 用户提供原始分发地址/目录，重新完整静态审计 |
| `westock-data`（`westock-mcp` 模式） | `SOURCE_LIMITED`，不接入 | 美股行情/K 线/财务/公告/新闻/研报候选，跨资产/宏观工具声明 | 依赖 WorkBuddy 专属 connector；当前 Codex 没有该 callable MCP；认证、免费额度、许可、字段级时点和 provenance 未说明；同一 connector 还暴露自选、提醒和模拟交易能力，不符合本项目最小只读能力面 | 取得明确使用条款与认证方式；只暴露 `data_*` 的只读子集；用固定 schema 对相关美股返回做有界验证；由本项目 adapter 重建 PIT/provenance，绝不直连 Agent |
| `westock-data-clawhub@1.0.4` CLI | `REJECTED`（直接执行/接入） | README 声称可查美股 K 线、财务、profile、分红和卖空 | Skill 指示 `npx -y` 下载执行；npm 包只有一个约 2.6MB 的混淆 bundle 和 package.json，无依赖清单、无 license、静态无法可靠确认真实端点/遥测/认证；响应时点与来源定位不满足契约 | 不以当前包解锁；除非上游提供可审阅源码、许可、固定依赖和公开端点说明，再作为新候选重审 |
| 归档内旧 `westock-data` bundle | `REJECTED`（直接执行/接入） | 与 CLI 声明相近 | 3.3MB 混淆单文件；归档样本还包含内部遥测/配置域名字串；没有 lockfile 或目标包 LICENSE；部分说明建议远程 `curl | bash` 安装 Node | 不执行；不作为正式来源 |
| `neodata-financial-search/1.0.1` | `NOT_VERIFIED`，不接入 | Macro/Market 新闻、公司公告/研报、行情/财务候选 | 需要 WorkBuddy `connect_cloud_service` 提供 12 小时 token；当前环境无该工具或合法 token；Python 依赖 `requests` 未固定版本/完整性；返回把结构化内容装进自由文本 `content`，字段来源、修订、许可、费用及正文权利未说明 | 取得独立于私人 WorkBuddy 会话的正式认证/条款；固定依赖；对单个美股/市场数据集做一次有界真实响应并验证原始 URL、published/as_of/retrieved；只经确定性 adapter 进入冻结 MCP |

因此，本 Change 不把任何上述候选加入默认 provider、network allowlist 或 Agent 工具权限。Macro/Market/Company 核心项继续使用 BLS、Treasury、Federal Reserve、BEA、FRED、SEC、Yahoo、发行人 IR、OpenAlex 等已声明的官方/公开来源路径。该结论不会阻断核心实现，但也不得写成第三方候选已提供覆盖。

## `westock-data` 证据

### MCP 模式

锁定文件：

| 路径 | SHA-256 | 观察 |
| --- | --- | --- |
| `connectors/westock-mcp/mcp.json` | `de269b33acf3e9d61b35bdafc81a196302375648977b9d538ad0cae3c4a59094` | `streamableHttp` 指向 `https://stockbuddy.qq.com/cgi/cgi-bin/openai/mcp/mcp`；没有 token schema、认证、费用或使用范围声明 |
| `connectors/westock-mcp/skills/SKILL.md` | `7e9bc2f7bab9ca3507f02ca3d9921686dce4906431f0ca68299cf042bf0d2f59` | 同时描述查询、自选管理、提醒和模拟交易；能力面宽于本项目只读边界 |
| `experts/stock-partner-team/skills/westock-data/SKILL.md` | `7d33a3b5129f57db1243996501afe58862cbf30cbce0e19f04154a3be9a0f950` | 明确只能调用 connector `data_*`，connector 不存在时降级其他来源 |
| `experts/stock-partner-team/skills/westock-data/package.json` | `afdd7bfcc5af705ca436094596466dcb9777aaf808f9f7afcbb88aafcc199570` | `private: true`，没有运行依赖或 license；只是 Skill 元数据 |
| `experts/stock-partner-team/skills/westock-data/references/mcp-tool-map.md` | `f4c73d9fbe757e6f1c4974d932ba43c13b1fb41612567d9d2f60f5ad199cbf96` | 声明 `data_quote/kline/finance/news/notice/report/macro/...`，但不是服务 schema 或真实返回证据 |

美股相关声明包括 `usAAPL` 代码、quote、K 线、三表、profile、分红、卖空、新闻/公告/研报；宏观/市场还列出 `data_macro`、`data_futures`、`data_forex`、`data_bond`。然而文档没有为这些数据提供上游 `source_id`、可验证原文 locator、`as_of/published_at/retrieved_at`、修订/vintage 或美股逐字段 schema，不能直接通过本项目 Gate。

### npm CLI 模式

根目录 `skills/westock-data/SKILL.md`（SHA-256 `8ff389b4b5f278427513452382d4937e763f69fa8c6aa23284cbce0c736afcf8`）要求运行 `npx -y westock-data-clawhub@1.0.4`。本次没有执行它，只读取 npm registry 元数据并下载 tarball 做完整性校验：

- registry package：`westock-data-clawhub/1.0.4`；Node `>=18`；没有 dependencies 字段；license 为缺失。
- tarball SHA-1：`b434e6ca4b434455201f1d8af56da435f518b678`，与 registry `shasum` 一致。
- tarball SHA-512 base64：`Cr4IS69wJ6aFdaDv7Sh/Zwf1FEj+8BHxegIltjWg4bswjV2SfbG9VmM0YN4SwfaLJlP1INzM0Ed3LXP+3WpjSA==`，与 registry integrity 一致。
- tarball 仅包含 `package/package.json` 与 `package/scripts/index.js`；bundle 为 2,625,792 bytes，SHA-256 `e35d828669d1e106d3baa9e290076cc56e334b2d39695d2eb6bae40ef81a524a`，代码混淆，静态检索无法可靠还原数据端点和所有网络行为。

归档另含旧打包 CLI：

- `experts/strategy-backtest-expert/skills/westock-data/scripts/index.js`：3,348,177 bytes，SHA-256 `6edabd7e8842b4efa3b8031d044e9ebb08ba0a93c6e58d0625ad8027a27cb032`。
- `experts/a-share-analysis/skills/westock/scripts/data-index.js`：2,796,938 bytes，SHA-256 `36f5bc513b5750f4343ba764b35ca9a2d39ae4d1cb9ed8b91044d1783366e1bf`。
- `experts/a-share-analysis/skills/westock/scripts/data-vendor.js`：1,175,747 bytes，SHA-256 `2c70754e2b5edbf459498a22c8a409172e651e5d36398fa3cf9ddf8d661fc44a`；静态可见内部配置/遥测域名和 OTLP 端点字串。

压缩包完整性匹配只证明下载内容与 registry 声明一致，不证明代码安全、数据许可、字段质量或本项目可用性。

## `neodata-financial-search` 证据

锁定文件：

| 路径 | SHA-256 | 观察 |
| --- | --- | --- |
| `skills/neodata-financial-search/SKILL.md` | `1d55f6f745f86314ab910d292b1502a0191d2102f67277ab51cec87505981faa` | version `1.0.1`，允许 `Read,Bash`；要求 WorkBuddy `connect_cloud_service` 获取 `tempToken/token` |
| `skills/neodata-financial-search/reference.md` | `01001322b5bababfe7c0c2b315e723be8519df84584296cc9f9ed13685726720` | 声称覆盖美股、宏观、新闻、公告和研报；示例不构成真实返回 |
| `skills/neodata-financial-search/scripts/query.py` | `262a92cdb0e52ef7804836b83c75f83c23a3a06cbdc977bcaa2757df9d8cff2a` | POST `https://copilot.tencent.com/agenttool/v1/neodata`；Bearer token；`requests` 未固定；token 写入 `~/.workbuddy/.neodata_token` |
| `skills/neodata-financial-search/scripts/query.sh` | `42fa3413cd66006a117a2cab9ccea2d90f4939d2c524af5dc496d6ca1cde0ae3` | curl 备选，同样依赖私人 token 缓存和宿主环境 |

响应文档声明 `apiRecall[].content` 为文本，`docList` 有 title、publishTime、source、url、content。它尚不能保证 `content` 是全文、摘要还是再分发文本，也没有原始事实级来源、版本、修订和授权字段。本次没有合法 token，故没有发送无意义的未认证探针，也没有把 `401/403` 当成数据可用性验证。

## 准入决策对当前设计的影响

1. 不修改 `product/mcp/live/research-source-policy.json` 或 `holding-research-inputs.json` 来声明这些候选可用。
2. 不新增第三方 Skill 到 Agent allowlist，不复制其私人 token，不安装 `westock-data-clawhub`，不执行任何归档 bundle。
3. `westock-data` 声明的跨资产、宏观、新闻、公告与研报能力只能作为数据集发现线索；不会替代官方来源和现有 SEC/Yahoo/Moomoo/OpenAlex 链路。
4. 若未来满足解锁条件，仍须先做固定版本的项目内 adapter、最小域名 allowlist、字段/时间语义验证、故障隔离和冻结 MCP；不能让 Agent 直接调用第三方 CLI 或含状态修改能力的整个 connector。
