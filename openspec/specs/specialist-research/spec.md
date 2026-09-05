# specialist-research Specification

## Purpose

定义由专业 Skill 和少量 runtime Agent 执行的可组合投研能力，使 LLM 研究保持开放推理，同时让输入、证据、输出和评价可结构化验证。

## Requirements

### Requirement: 每项研究能力必须具有完整 Capability Contract
公司研究、估值、市场与催化剂、反证等能力 MUST 定义 Input、Tool/Data、Skill/Reasoning、Structured Output 和 Eval，缺少任一部分的能力不得进入产品运行面。

#### Scenario: 注册新研究能力
- **WHEN** 开发控制面准备注册一项新研究能力
- **THEN** 能力清单中存在可验证的五段式契约和至少一组 Eval 样本

### Requirement: LLM 与确定性计算职责必须分离
LLM SHALL 负责研究、解释、Thesis、反证、冲突分析和决策综合；确定性程序 SHALL 仅负责数据获取与标准化、数学计算、持仓核算、硬风控、验证和存储。

#### Scenario: 估值能力执行
- **WHEN** Agent 评估标的估值
- **THEN** 确定性层计算给定假设下的数值，Agent 解释假设、情景、适用性和不确定性

#### Scenario: 主观判断被编码为规则
- **WHEN** 实现将“优质公司”“好估值”或“应买入”等主观投资判断写入大型 if/else 规则
- **THEN** 架构评审判定其违反职责边界并阻止晋升

### Requirement: 专业研究输出必须结构化
每份 Agent Research Report MUST 包含研究范围、Claims、证据引用、反证、不确定性、数据缺口、失效条件、置信度及其理由，并 MUST NOT 直接决定完整组合的最终动作。

#### Scenario: Company Analyst 完成研究
- **WHEN** Company Analyst 完成一个标的的质量和估值研究
- **THEN** CIO 收到符合统一 Schema 的报告，并能区分事实、假设和解释

### Requirement: 反证能力必须保持独立性
系统 SHALL 支持 Skeptic 在接触 CIO 初步结论前进行独立研究，并可在草案形成后执行针对具体 Thesis 的第二轮压力测试。

#### Scenario: 独立反证研究
- **WHEN** CIO 为同一标的并行委派公司研究和反证研究
- **THEN** Skeptic 的第一轮上下文不包含其他 Agent 的结论

### Requirement: Agent 数量必须由可测增益决定
新增 runtime Agent MUST 在证据质量、反证覆盖、冲突识别、决策校准或效率方面通过相对于现有系统的消融评估。

#### Scenario: 新 Agent 未产生增益
- **WHEN** 消融评估显示新增 Agent 未达到预先声明的接受阈值
- **THEN** 该 Agent 不进入默认 runtime 配置，其能力保留为现有 Skill 或按需流程
