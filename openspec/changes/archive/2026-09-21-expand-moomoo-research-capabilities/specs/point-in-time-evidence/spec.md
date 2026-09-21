## ADDED Requirements

### Requirement: 复合供应商响应必须具有字段级时间语义
当同一响应中的字段具有不同观察、有效、推荐、更新或公开时间时，系统 MUST 按字段族或 section 生成独立时间语义，至少保存 `as_of`、`published_at`、`retrieved_at`、时间来源及无法确认的限制。响应级 `update_time` MUST NOT 自动覆盖全部字段；缺少字段有效时间时 MUST 使用明确的保守策略或拒绝历史用途，不得伪造精确时点。

#### Scenario: 期权价格和 Greeks 共用一个响应
- **WHEN** Market Snapshot 的 `update_time` 只被官方定义为最新价格时间，而 OI、IV 或 Greeks 没有独立有效时间
- **THEN** 价格 Evidence 使用该报价时间，其他字段使用检索时点的保守 snapshot 语义并记录供应商有效时间未知，不把它们描述为与最新价同时更新

#### Scenario: Morningstar section 更新时间不同
- **WHEN** fair value、economic moat、financial health、bull/bear、analyst note 或 investment thesis 具有各自更新时间或正文缺失
- **THEN** 系统按 section 保存 Evidence 和时间，缺正文的 section 只形成字段 gap，不用 analyst report 总时间覆盖整份材料

#### Scenario: 评级推荐日早于供应商更新时间
- **WHEN** rating item 的 `recommendation_date` 与 `update_time` 不同
- **THEN** `as_of` 保存推荐日，`published_at` 使用供应商更新时间或更保守的获取时间，历史 cutoff 早于可知时间时排除该评级

### Requirement: 期间、公开版本与当前供应商修订必须分离
Macro、机构汇总、评级和期权统计 Evidence MUST 区分经济观察期或报告期、供应商公开/更新时间、当前检索时间与历史 vintage 可用性。供应商响应只提供当前 `previous_value`、consensus 或修订值时，系统 MUST 标记当前快照，不得将其回填为过去 cutoff 已知版本。

#### Scenario: Macro History 包含 data time 和 release time
- **WHEN** Moomoo Macro 数据点同时返回 `data_time`、`release_time`、actual、predict 和 previous
- **THEN** 系统分别保存观察期、可知时间和数值角色；发布时间时区未核实时 fail closed 或以 retrieved_at 保守处理，不能按本地默认时区猜测

#### Scenario: 机构持仓 period_text 和 update_time 不同
- **WHEN** Moomoo 机构汇总返回报告期间和供应商更新时间
- **THEN** `as_of` 对应已解析并核实的报告期，`published_at` 对应供应商更新时间；无法解析报告期时记录 gap 而不把更新时间冒充持仓期末

#### Scenario: 当前 consensus 被用于历史研究
- **WHEN** 当前响应的预测值或评级共识没有历史版本标识，而目标 decision cutoff 早于本次获取
- **THEN** Evidence 不进入历史研究包，只能形成新的当前 cutoff 快照

#### Scenario: 历史 actual 已被供应商修订
- **WHEN** 当前获取的历史 actual 带有旧 release time，但没有证明当前值在旧 cutoff 已知的原始版本
- **THEN** 系统将其作为当前获取版本，不以旧 release time 自动放行历史用途

#### Scenario: 当前已知的未来日程
- **WHEN** 日历或 FedWatch 指向未来事件，而该日程或预期在当前 cutoff 已公开
- **THEN** 分别保存事件目标时间与资料可知时间，允许引用当前已知日程/预期，但不得表述为事件已经发生或结果已确定

### Requirement: 供应商字段单位和时区必须显式标准化
系统 MUST 对 Moomoo 字段保存官方声明的市场、时区、百分比缩放、货币和单位，并以实际响应验证转换。无法从文档与响应共同确定比例或时区时 MUST 保留原值、原标签和 gap，不得基于示例或字段名称自动乘除、转换日期或混合不同市场时区。

#### Scenario: 百分比响应使用小数值
- **WHEN** Macro History 返回 `unit_type=PERCENT` 且实际数值为小数形式
- **THEN** Normalize 通过批准的字段定义保存原值与标准化值及转换版本，不因 UI 表示习惯重复除以或乘以 100

#### Scenario: 美国行情包含盘前盘后和夜盘字段
- **WHEN** Snapshot 同时返回 regular、pre-market、after-hours 或 overnight 字段
- **THEN** 各交易时段分别标记并保持原时点，不合并为单一 close/last，也不与 Yahoo 不同时段的字段静默拼接

#### Scenario: 同名宏观指标的口径不同
- **WHEN** 官方 CPI 指数水平或非农总人数与供应商同比、环比或新增人数同时出现
- **THEN** 系统显式保留统计口径与单位，未经有据可查的换算不得直接比较为冲突或相互替代
