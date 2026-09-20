# 本机研究资料浏览器

本入口只读取已经保存的 Research Memory 与显式配置的冻结运行目录。它不会联网刷新资料、调用模型、启动研究调度，也不会写入事实、checkpoint、View、报告或 reuse event。

## 启动与停止

实现使用 Python 3.11+ 标准库 HTTP 服务，不增加 Web 框架、Node 或浏览器端 JavaScript 依赖；因此也不会进入现有 Agent 的导入或启动链。

先执行只读诊断：

```bash
python3 scripts/research-browser.py \
  --memory-root "/path/to/existing/research-memory" \
  --check
```

启动：

```bash
python3 scripts/research-browser.py \
  --memory-root "/path/to/existing/research-memory" \
  --port 8765 \
  --run-dir "/path/to/an/exact/frozen-run" \
  --run-root "/path/to/a/run-root"
```

然后主动打开 `http://127.0.0.1:8765/`。停止时在启动它的 Terminal 按 `Ctrl-C`。服务固定监听 `127.0.0.1`，没有可配置的公网 bind 地址。

`--run-dir` 和 `--run-root` 均可重复：

- `--run-dir` 精确读取指定运行目录或 source-package 目录。
- `--run-root` 只检查根目录的直属子目录，且只接纳含已知 manifest 的子目录；不会递归扫描其他磁盘位置。
- 页面内“重新扫描已配置目录”只重读这些本地目录，不访问 Provider 或刷新数据。

Memory 目录必须已经存在且包含受支持的数据库。缺库不会创建，版本不兼容不会迁移。Macro/Market 目录与 Memory 相互独立：其中一类不可用时，另一类仍可浏览。浏览器只会选择引用完整的最新 View 作为默认版本；历史不完整 View 仍可显式打开，但会显示引用总数、成功解析数、缺失数和校验失败数，且不会用数据库中的其他最新事实补齐。

## 页面与状态

- `Macro`：官方宏观快照中的 CPI 指数、失业率和 10Y 收益率，以及新版本 `MACRO_CONTEXT` 报告。历史 `MACRO_MARKET` 只显示为 `LEGACY_COMBINED_COVERAGE`；单次观测不画伪趋势，没有 historical vintage 时会明确提示。
- `Market`：基准价格事实、已有 20/60/252 日计算和新版本 `MARKET_STATE` 报告。历史 `MACRO_MARKET` 可兼容阅读但不算作独立 Market 通过；页面不补算缺失统计。
- `Company`：所有已保存公司，不推断“当前持仓”。默认先展示营收、净利润、稀释 EPS、经营现金流，再按相同指标和可比期间绘制趋势；资本开支、现金和债务保留在可展开的指标表。价格与成交量分图，原始长表和采集诊断默认收起或进入独立分页页。披露事件与模型研究严格分层：前者只呈现已保存事实，后者只呈现通过契约和版本绑定校验的报告。

公司只有事实版本但尚无 View 时，页面明确标为“未冻结事实目录”：可以分页查原始版本，但不显示 View 完整率，也不把全部修订聚合为当前指标、趋势或行情图。保存合格 View 后才进入默认阅读路径。

公司页并列显示三种时间，含义不可互换：

- 资料截止：当前所选已保存 View 的 `decision_cutoff`。
- 最近实际检查：该对象最近的采集 attempt 或 reuse event 时间。
- 报告研究截止：报告原包绑定的研究 cutoff；`reports.stored_at` 不用来冒充检查时间。

列表筛选分别表示“有新资料无新报告”“数据缺口”“来源失败”和“尚无报告”。Checkpoint/coverage、来源检查 attempt、运行状态、reuse event 和研究充分性保留各自原始状态，不合并成一个“成功”。

四条 Company 图形路径为价格与成交量、相对表现与回撤、财务趋势、Trailing P/E 历史。优先读取与所选证券、View cutoff 和 run 精确绑定且通过 hash 校验的 `visual_bundle`；没有附件时只使用当前 View 已有事实形成保守展示，否则显示具体限制码。缺 PE 历史是合法限制，不阻止其余页面，也不会显示空的 `AVAILABLE` 图形。

财务页面保留 Provider 原值，不把同一截止日的季度、年初至今和年度值混成一条曲线。每个核心数值和图表的“证据”入口可回到所选 View 下的事实版本，并展示单位、财务期间、`as_of`、公开时间、获取时间、来源和版本 hash。切换 View 后，页面指标、图形和证据链接会使用同一版本。

### 公司事件与研究报告

公司事件时间线优先展示同一申报、期间和语义字段下的有效正文；目录短句、重复标题和短摘录折叠到事件卡内，但不删除其来源或事实版本。Form 4 只做确定性字段解码，包括交易代码及含义、取得/处置、证券类型、数量、每股价格、交易后持有量和持有方式；它不会推断内部人动机、交易重要性或利好/利空。

保存的 Company Agent 报告仅在原包 hash、security、run、decision cutoff、request 和 calculations 绑定均闭合，并通过 `equity-research-report/1.0.0` 校验时展示。页面按生产契约显示研究摘要、六个命名章节、claims/证据、assumptions、催化剂与反证、失效与重新评估、监控指标、数据缺口及置信度依据。未知或旧版结构只给出不支持提示，不把猜测字段当作生产报告。

Company 补充研究区可读取同一 security/run/cutoff 下已经保存的 `FUNDAMENTAL_EVENT`、`RESEARCH_REPORT`、`OWNERSHIP_DISCLOSURE` 和 `INDUSTRY_COMPARISON` 报告。每类状态独立显示：

- `AVAILABLE`：报告存在且绑定闭合，可以阅读摘要、主张、来源、缺口和限制。
- `BINDING_FAILED`：发现候选报告但版本关系不闭合，已隔离，不能借用到当前公司版本。
- `NOT_GENERATED`：当前运行没有该类保存产物；只表示尚无可展示报告，不表示现实中没有事件、研报观点、持仓变化或可比公司差异。

浏览器不会为了填补这些空状态调用模型或联网补采。当前 MRVL 尚缺保存的 Company Agent 报告、系统化 8-K/业绩材料/电话会/指引/新闻、外部研报语料及对应多维研究产物，也没有真实历史 Trailing P/E；这些是数据链与研究链的后续工作，不应在展示层用拼接或推断代替。

## View 引用预检与离线修复

网页没有修复按钮，也不会在读取时改库。若旧 View 因 Gate 临时加入的 freshness 上下文形成悬空 hash，先执行只读预检：

```bash
python3 scripts/research-memory-repair.py \
  --memory-root "/path/to/existing/research-memory" \
  --security-id "US:COMMON_STOCK:MRVL"
```

输出会逐个 View 给出 `reference_count`、`resolved_count`、`missing_count`、`ambiguous_count` 和 `unresolved_count`。只有缺失引用能通过 cutoff 当时已经保存、内容寻址校验通过的 snapshot 唯一映射到既有事实版本时，`repairable` 才为真。预检不会写数据库、对象目录、checkpoint 或调用 Provider/模型。

执行修复必须先取得该稳定目录的实际写入授权，并指定一个尚不存在的备份目录：

```bash
python3 scripts/research-memory-repair.py \
  --memory-root "/path/to/existing/research-memory" \
  --security-id "US:COMMON_STOCK:MRVL" \
  --apply \
  --backup-root "/path/to/new-research-memory-backup"
```

执行时先用 SQLite backup API 复制数据库并复制内容寻址对象，再在单一事务中新增引用闭合的修复 View；旧 View、事实版本、报告和 checkpoint 全部保留。修复 receipt 写入 Memory 的 `repairs/`，重复执行返回 `NO_CHANGES`。任一引用变动、歧义、证据不足、备份目标已存在或 receipt 冲突都会拒绝执行；事务或 receipt 失败会撤销本次新增 View。恢复时应停止写入器和浏览器，以备份中的数据库与 `objects/` 替换对应目录。

## 支持格式与兼容降级

首版 registry 支持：

| schema | 页面用途 |
| --- | --- |
| `company-research-memory` schema `2` | Company 事实、View、报告索引和状态 |
| `official-macro-snapshot/1.0.0` / `1.1.0` | Macro 指标、官方政策正文与已公布发布日历 |
| `benchmark-research-snapshot/1.0.0` | Market 基准 |
| `market-state-calculation/1.0.0` | Market 窗口统计 |
| `research-dimension-report/2.0.0` | 当前 Macro / Market 及其他多维研究报告 |
| `research-dimension-report/1.1.0` | 已有研究报告 |
| `equity-research-report/1.0.0` | 已保存 Company Agent 研究报告 |
| `equity-research-attachments/1.0.0` | Company 估值、基本面与图表附件 |

相同稳定身份和内容 hash 只显示一次；同身份不同内容会隔离为冲突。未知 schema 只显示版本/身份和“不支持”提示，不猜测字段，也不影响已有页面或任何 Agent 的开发、运行、验收与调度。增加同类证券或同类记录无需改网页；增加全新产物类型时，只需在 `product/web/read_only.py` 的小型 registry 和对应渲染映射中增加适配。

## 只读与隐私边界

- SQLite 通过 `mode=ro` 与 `query_only` 打开，使用短 busy timeout；不调用 `ResearchMemory` 写入型构造函数，不设置 journal mode。
- 内容寻址对象必须位于配置 Memory 的 `objects/` 内，引用与 SHA-256 必须一致；符号链接、路径穿越和任意文件 URL 会被拒绝。
- `objects/`、`evidence/source-package/`、`research/` 等候选路径的完整祖先链必须留在显式准入根内且不经过符号链接；最终文件不是 symlink 也不能绕过这项检查。
- HTTP 层校验本机 Host 和同源写表单，发送 CSP、`nosniff`、`no-referrer` 与禁止 iframe 响应头。
- 来源内容、报告字段和 SVG 文本均转义；页面不自动加载外部脚本、图片或数据。外部来源链接只有用户主动点击才会打开。
- 响应不提供原始报告包下载，并排除 private request、账户/组合上下文、凭据和真实绝对路径。报告页面只呈现允许列表内、通过原包 hash 验证的研究正文。

Macro/Market 内部使用 resolved run root 的不可逆标识区分来源，不把相同目录名视为同一次运行，且不在页面暴露绝对路径。报告必须与所选快照的目录、run（manifest 提供时）及 decision cutoff 闭合；市场计算还必须把已有 `evidence_fact_ids` 闭合到所选 benchmark snapshot。错绑定产物会被隔离为 `ARTIFACT_BINDING_MISMATCH`，不会串入历史版本。

浏览器不可用、页面尚未适配新能力或本服务停止，均不会改变产品 Runtime。真实 Smoke、Runtime Eval、Regression 和 Promotion 也不会由本入口隐式启动。

## 常见诊断

`--check` 输出只含状态码、schema 版本、公司/产物数量及问题数量，不返回本机绝对路径。常见代码：

- `BROWSER_MEMORY_DATABASE_MISSING`：配置目录或数据库不存在。
- `BROWSER_MEMORY_SCHEMA_UNSUPPORTED`：Memory 版本不受当前浏览器支持。
- `BROWSER_MEMORY_BUSY`：写入器短暂占用；稍后刷新即可，浏览器不会抢锁。
- `ARTIFACT_RUN_DIR_UNAVAILABLE`：显式运行目录消失或不含已知入口。
- `ARTIFACT_IDENTITY_CONTENT_CONFLICT`：相同稳定身份对应不同内容，已隔离。
- `ARTIFACT_SCHEMA_UNSUPPORTED`：发现已知候选位置中的新格式，当前只提示、不解释其正文。
