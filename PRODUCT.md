# Stock Agent Product North Star

## 最终目标

构建一个运行在 Codex 上的 LLM-native 多 Agent 股票研究与组合决策 Agent Package。

用户主要输入真实持仓。

系统通过专业 Agent、Skill 和只读 Tool/MCP 获取并分析：

- 市场行情与市场状态
- 全球宏观
- 行业与热门板块
- 个股基本面、财报、估值和催化剂
- 研报与产业研究
- 资金流、杠杆和系统性风险
- 期权结构
- 基金持仓变化
- 政客交易与重要人物动态
- 新闻、社区和热门话题

专业 Agent 独立研究并提供证据、Thesis、反证和失效条件。

CIO 结合：
- 所有专业 Agent 的研究
- 当前持仓
- 组合暴露
- 风险约束

最终输出：
BUY / ADD / HOLD / REDUCE / EXIT / HEDGE / NO_TRADE
以及建议仓位、理由、风险、证据和失效条件。

## 产品核心形态

Portfolio
↓
Research Skills + Read-only Tools
↓
Specialist Agents
↓
Independent Skeptic
↓
CIO
↓
Deterministic Risk Engine
↓
中文组合决策报告

## 架构原则

LLM 是研究和判断主体。

Skill = 专业研究方法。
Agent = 使用 Skill + Tool 完成研究和判断。
Tool/MCP = 获取事实和执行确定性计算。
Python = 数据、计算、验证、Risk、持久化。

不得把投资研究逐步迁移成大型 Python 规则系统。

## 当前最高优先级

任何阶段都优先建立“用户能看到的产品能力”。

Milestone 0 的 Agent Package 装配 Demo 与普通股基本面研究已经形成基础数据流。当前不继续扩建 Demo 平台，优先完成确认普通股持仓的免费多维研究资料包：

确认持仓
→ 价格成交量与技术结构
→ 基本面深化与公司事件
→ 自动研报读取与对比
→ 行业与宏观市场
→ 可得的所有权、期权和资金结构
→ 可供下一专业 Agent 直接消费的中文/JSON 研究包。

这一步只形成研究输入，不提前启动 Skeptic、CIO、Risk 或输出买卖动作。核心免费维度形成实质资料后，再进入 Independent Skeptic 和组合决策闭环。

除非直接阻塞该链路，否则：
- 不继续扩建 Replay 平台
- 不继续扩建 Sandbox
- 不继续扩建 Hash/Trace 基础设施
- 不继续增加治理层
- 不增加与当前 Demo 无关的 Agent

## Demo 优先原则

每增加一个 Capability，都必须回答：

“它能让最终投资建议增加什么新的有效信息？”

如果不能明确回答，则暂缓开发。

优先顺序：

1. 普通股持仓的基本面、技术、行业、宏观与研报研究包
2. Independent Skeptic 反证研究
3. 3–5 只持仓的 CIO + Risk 决策闭环
4. ETF 与期权持仓专项研究
5. Options / Flow / Leverage 与 Fund 持仓深化
6. 全市场机会发现
7. Politician / Social 等补充资料
8. Reflection / Self-improvement

工程基础设施只做到足以支持下一项产品能力。
