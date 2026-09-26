## ADDED Requirements

### Requirement: 研报观察条件引用必须闭合且不丢失有效内容
`RESEARCH_REPORT` 正式报告的观察条件、失效条件及其他 Claim 引用 MUST 指向同一报告真实存在的 Claim ID，并保持报告、Evidence 与附件引用闭合。悬空引用 SHALL 在保存和下游交接前按现有有界纠正规则交原 Agent 处理；无法纠正时保留明确失败及已合法完成的独立维度，不得通过删除观察条件、创建虚构 Claim 或只因 JSON 可解析就标为完成。

#### Scenario: 观察条件引用不存在的 Claim
- **WHEN** `RESEARCH_REPORT` 草稿出现 `DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING`
- **THEN** 将该报告内 Claim 条件引用错误纳入现有一次原 Agent 纠正入口，返回具体引用路径及报告内合法 Claim IDs；纠正后重新执行全部契约校验，仍非法则该任务失败且下游不可将它视作合格研报研究

#### Scenario: 纠正次数已用尽或错误不在允许范围
- **WHEN** 原任务的一次纠正已用尽，或报告失败属于 Evidence/PIT/权限违规
- **THEN** 本次新增的条件引用纠正路径不得继续调用或承接这些错误，保留失败；不得扩大通用重试、删除内容或放宽校验

#### Scenario: 研报正文来源受限
- **WHEN** 正文不可得但报告合理记录 `SOURCE_LIMITED` 与受影响判断
- **THEN** 保留合法缺口及其他维度已完成结果，不为使研报维度显示 COMPLETE 而伪造引用或正文
