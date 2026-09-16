## Why

当前实现已经形成可复用的美股真实数据采集基础，但本 Change 同时承载了已被后续分阶段研究架构替代的完整 Council、三股上限和投资动作验收。需要把范围重新聚焦为“真实数据与 Evidence 底座”，让已确认持仓稳定进入 Company Analyst，而不是在数据接入阶段提前完成投资委员会。

## What Changes

- 将 `us-equity-live-advisory-slice` 收缩为美股普通股真实只读数据基础：NASDAQ 证券目录、Yahoo/yfinance 主行情、AKShare/东方财富受控备用和 SEC 公司披露。
- 以已确认的 `PortfolioHandoff v3` 为唯一用户持仓来源，内部生成最小数据采集请求；不再要求用户维护第二套 live portfolio、mandate 或 focus security 输入。
- 对输入中的全部普通股执行数据准备，不设置 1 只或 3 只产品上限；只允许通过并发数、请求预算、超时和数据量限制保护运行资源。
- 输出冻结的数据快照、PIT Gate、来源选择、证据和结构化缺口，供现有普通股研究及后续多维研究消费。
- 保留来源、时间、身份、缓存、PIT、主备路由、隐私和 fail-closed 边界；数据不足时不得伪造事实。
- **BREAKING**：退役 `--profile live-us-equity --portfolio ...` 直接启动完整 Council 的旧产品入口，以及 `prepare-live-batch`、`launch-live-batch`、`summarize-live-batch` 三股批次入口。
- **BREAKING**：本 Change 不再要求 Analyst、Skeptic、CIO、Risk、投资动作、中文决策报告或语义 Eval；这些由后续研究和组合决策 Capability 负责。
- 保留各类契约当前实际使用的版本，包括采集请求 v2、SEC fact v1 和来源访问 v4；仅删除确认没有现行或保留消费者的旧分支，不进行统一升版、来源权限重设计或兼容平台建设。
- 保留研究 Agent 经现有只读工具提出补充资料请求的能力；新增资料仍须冻结、通过 PIT 和引用校验，既有冻结包不得原地改写。
- 历史技术试拉、故障过程和三股运行记录保留为历史证据，不再作为当前产品行为规格或待完成验收。

## Capabilities

### New Capabilities

- `live-us-equity-data`：从已确认持仓生成美股普通股数据采集请求，使用免费优先的只读来源形成带来源、时间、PIT 和缺口信息的冻结研究证据包。

### Modified Capabilities

无。本次不修改最终投资建议或 Council 编排行为；旧 delta spec 在尚未归档前从本 Change 移除。

## Impact

保留 `product/mcp/live/` 中的行情、SEC、NASDAQ、缓存、身份、来源选择和 Evidence 实现及现行 PortfolioHandoff 数据接缝。优先退役旧批次命令和宿主入口；代码、Schema、测试的删除须有具体清单及消费者检查。共享函数或仍被历史证据读取使用的部分允许保留，不以共享旧分支全部清零作为完成条件。

被后续验收引用的历史报告、运行包和版本锁保留；重复说明仅在确认无人引用后清理。用户真实运行包、截图、原始数据不在自动清理范围。验收只证明清理后的数据交接和兼容性，不宣称研究资料充分或研究质量通过。

`macro.py`、`options.py`、`ownership.py`、`public_research.py`、`peer_candidates.py` 属于后续多维研究能力，不在本 Change 的删除范围。真实持仓、凭证、Cookie、原始缓存和运行产物继续保存在仓库外。此次更新只修改规划产物，代码清理须在后续 apply 中实施。
