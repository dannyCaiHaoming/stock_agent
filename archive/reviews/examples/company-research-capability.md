# 能力契约：company-research

## Input

`ResearchRequest`、证券标识、决策截止时点，以及有效的 `EvidenceBundle`。

## Tool / Data

只读基本面、公告/新闻、市场环境和证据查询工具，以及确定性估值计算器。

## Skill / Reasoning

LLM 负责解释商业质量、假设、估值情景、反证、不确定性和失效条件；计算器只执行数学运算。

## Structured Output

输出 `AgentResearchReport`，包含带证据引用的主张、假设、反证、数据缺口、失效条件、置信度及其理由。

## Eval

Fixture 样本用于衡量证据支持度、事实/假设分离、反证覆盖、失效条件质量、Schema 有效性、延迟和 token 消耗。注册为生产能力前，必须通过全部硬检查和预先声明的评分阈值。
