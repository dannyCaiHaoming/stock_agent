## ADDED Requirements

### Requirement: 独立 Reviewer 必须按需使用
开发流程 SHALL 按需使用独立 Reviewer，不把它作为每个普通 Change 的必经步骤；其他已批准 Change 的明确复核要求 MUST 保留。需要复核时沿用现有只读职责、证据范围及原定完成批准，不扩大为新的流程或取消产品晋升要求。

#### Scenario: 普通改动无独立复核需要
- **WHEN** 本次普通修改及相关检查已完成，且没有用户或当前明确验收要求调用 Reviewer
- **THEN** 不因未调用 Reviewer 阻断完成摘要，仍保留既有人工完成批准

#### Scenario: 现有 Change 明确要求复核
- **WHEN** 某项已批准 Change 的原验收明确要求独立复核
- **THEN** 继续遵守该要求，不把按需约定解释为自动豁免

### Requirement: 外部引入的 Skill 必须保持只读
项目开发 SHALL 在自有指令和内容中维护项目规则；外部引入的 OpenSpec 及其他 Skill MUST 保持只读，不通过修改其正文或通用流程实施项目调整。

#### Scenario: 第三方默认流程与项目约定不同
- **WHEN** 项目需要自己的开发约定
- **THEN** 修改项目自有内容而非第三方 Skill，不能宣称第三方原始流程已被改变
