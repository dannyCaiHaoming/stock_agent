## Context

动机见 Proposal。仓库已有 NASDAQ、Yahoo/yfinance、AKShare/东方财富、SEC、缓存、来源选择、身份核实和 PIT 实现；后续 Change 又建立了 `PortfolioHandoff v3`、普通股研究和多维研究阶段。旧 live 路径仍直接准备逐股 Council 子运行，并在数据接入 Change 中要求 Specialist、CIO、Risk 和语义 Eval，造成职责重叠。

当前清理必须保护仍被普通股研究复用的数据模块。相同目录下的宏观、期权、持仓披露、公开研报和同行候选模块由后续 Capability 所有，不应按文件目录一并删除。

## Goals / Non-Goals

**Goals:**

- 让已确认 PortfolioHandoff 中的全部普通股进入同一真实数据准备流程。
- 生成可被普通股研究阶段直接消费的冻结 Gate、Evidence、来源选择和数据缺口。
- 保留真实来源访问、身份核实、缓存、PIT、隐私和 fail-closed 边界。
- 退役已被分阶段研究链路替代的 live 完整 Council 与三股批次路径。
- 减少历史版本和开发试拉细节对当前产品路径的影响。

**Non-Goals:**

- 不在本 Change 中运行 Company Analyst、Market/Catalyst、Skeptic、CIO 或 Risk。
- 不生成 HOLD、TRIM、EXIT、NO_TRADE 或最终中文投资报告。
- 不实现机会搜索、股票排名、全市场行情下载、调度服务或券商连接。
- 不删除后续多维研究新增的宏观、技术、期权、持仓披露、公开研报和同行能力。
- 不扩建 Replay、Regression、Calibration、Ablation、Promotion、沙箱或代理平台。

## Decisions

### 1. 数据准备是独立 Capability，不是简化版 Council

本 Change 的终点为可被下游验证和读取的数据包。Python 执行数据获取、标准化、PIT、计算和存储，并报告机械性的获取失败或缺失字段；Agent 仍可判断研究需要什么资料、提出补充请求和解释缺口对研究的影响。

替代方案是保留旧的单股 Council 纵向切片，但它会绕过现有“公司研究→多维研究→Skeptic→CIO→Risk”阶段边界，因此拒绝。

### 2. PortfolioHandoff v3 是唯一用户输入

用户通过 `portfolio-intake` 确认持仓。数据层沿用现有内部采集请求，包含证券标识、ticker、账户快照时间和必要来源上下文。账户快照时间与研究 `decision_cutoff` 分开保存。现行 `live-portfolio/2.0.0` 已不含三股上限、mandate 或 focus 字段，无需重写；旧用户输入路径随旧入口退役，其他 Capability 的研究问题和风险约束不受影响。

全部普通股均进入采集计划，不设置持仓数量产品上限。资源控制使用可配置的 `max_concurrency`、每来源请求预算、响应大小和超时，不以截断用户持仓实现保护。非普通股保留在 Handoff 中，但由对应资产 Capability 处理。

### 3. 免费优先的受控来源拓扑保持不变

- NASDAQ：证券目录和候选身份资料；目录不可用不得单独否定一个可由 SEC 与行情来源核实的已知持仓。
- Yahoo/yfinance：非实时日线主行情。
- AKShare/东方财富：仅在允许的暂时可用性故障下作为受控备用，不与主源逐字段或逐日期拼接。
- SEC：公司身份、申报索引、companyfacts 和限定披露原文。

401、403、429、认证挑战、明确禁止、身份冲突、Schema 异常、原文完整性错误或 PIT 失败不得通过切换来源掩盖。所有实际尝试、选中来源、失败原因和原始内容 hash 随快照保存。

### 4. 按消费者清理，保留现行契约版本

不同类型独立版本化：当前采集请求使用 `live-portfolio/2.0.0`、SEC 事实使用 `live-fact/1.0.0`、来源访问使用 v4 均为合法现行组合。不得按数字较小判断过时，不统一升版，也不为清理迁移缓存或重建版本锁。

实施前记录每个候选删除项的现行消费者、历史读取消费者和保留决定。存在必要消费者则保留；仅删除确认没有消费者的专属分支。来源访问的现行批准、暂停、拒绝和 hash 规则保持，不在本次重设计准入或开发新的兼容器。

### 5. 冻结研究数据包是唯一交接产物

每次准备至少输出：

- Handoff 与内部采集请求的 hash 绑定；
- 统一 `decision_cutoff`；
- 证券身份结果；
- 通过 Gate 的 Evidence；
- 被 PIT 或质量规则排除的 Evidence 及原因；
- 每证券 SourceSelection；
- 缓存、适配器和来源版本；
- 结构化数据缺口；
- 可供下游读取的 Gate 和 data-preparation manifest。

所有事实必须携带 `source_id`、`as_of`、`retrieved_at`；披露事实还必须携带可验证的 `published_at` 语义和原文定位。数据不足时保留现有状态和具体缺口，不引入新状态平台。结构可读不代表资料充分或 `DOWNSTREAM_READY`；本次不改变下游对研究充分程度的判断。

研究 Agent 可经现有工具请求同行、基准或公开研报等补充资料。相同有效资料优先复用缓存；新增资料形成明确的新冻结产物，按既有 cutoff/PIT 和绑定规则验证后才可消费。晚于当前 cutoff 的资料不得混入当前研究包。此边界保留多维研究主规格已有行为。

### 6. 旧 live Council 路径显式退役

先退役旧批次 CLI 与宿主脚本分支，再按文件/函数清单删除无保留消费者的专属实现、Schema 和测试。消费者检查包括普通股研究、多维研究、fixture、配置中的动态入口和必要历史读取。`collection.py` 仍调用 `live_input.py` 的 `freeze_snapshot` 与 `load_live_portfolio`，这些共享函数必须保留。其他共享 Runtime 分支无法安全拆开时保留并记录原因，不进行大范围重构。

历史报告先检查 Markdown、JSON manifest 和归档记录引用；被引用的记录原样保留，只从当前操作说明中撤下失效步骤。无引用的重复说明才能列入删除清单。私人截图、真实运行包、原始数据和历史锁不纳入自动清理。

旧 `--profile live-us-equity --portfolio ...` 必须明确报错并指向 PortfolioHandoff 数据准备入口，不能静默回退到 fixture 或旧 Council。

### 7. 验收聚焦数据交接，不启动产品 LLM

验收使用合成 PortfolioHandoff 和冻结来源样例验证多持仓、身份、主备路由、缓存、PIT、缺口和下游消费。已有真实来源采集证据可在源码与契约未受影响时复用；只有来源适配或请求行为发生变化才补一次最小真实采集。

不运行旧三股 Council、语义 Eval、Regression 或完整 Release Gate。独立 Reviewer 只核对本次差异、测试和底层数据产物。

## Risks / Trade-offs

- [删除旧 live Council 分支可能影响历史运行包] → 检查必要读取消费者，保留相应实现；不新建兼容平台或改写历史包。
- [去除三股上限后大持仓增加请求量] → 用并发、请求、响应和时间预算限制资源，不截断持仓；单证券失败隔离并结构化报告。
- [免费来源不稳定或字段缺失] → 保留缓存、受控备用和 `SOURCE_LIMITED`，不补造事实。
- [NASDAQ 目录不是历史成分数据库] → 仅作为当前目录和身份候选，不用于证明历史成员资格或自动选股。
- [清理变成契约迁移] → 保持现行版本、来源权限和历史语义，只删除无消费者代码。

## Migration Plan

1. 锁定现有数据适配器、当前下游消费入口和历史兼容引用。
2. 确认现行 Handoff 到数据准备、普通股研究和多维研究的交接保持兼容。
3. 用超过三只的合成输入验证现行采集无三股限制，预算未执行项必须显式记录。
4. 保留现行契约组合及来源权限，确认候选删除清单。
5. 退役旧批次和完整 Council 宿主入口，删除已确认无消费者的专属内容。
6. 执行聚焦确定性测试、OpenSpec strict validate 和独立差异复核。

回退时可恢复旧入口代码，但不得恢复已废弃的产品行为声明或把旧三股证据当作当前研究链路验收。
