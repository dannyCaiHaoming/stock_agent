## ADDED Requirements

### Requirement: 产品指令必须显式限定入口与阶段
根开发指令 SHALL 指向各产品入口的既有授权条件，不将有效组合输入描述为所有产品能力的统一前提。产品指令、Agent 配置及插件介绍 MUST 区分独立 Intake/交易记录/复盘、持仓或单股研究、研究综合与完整 fixture Council。仅完整 fixture Council 适用的组合动作、`NO_TRADE`、Risk 和 CIO 修订规则 MUST 带明确作用域，不覆盖研究阶段的 `RESEARCH_SYNTHESIS`、Risk=`NOT_RUN` 及禁止动作约束；更新说明不授予新能力或自动推进阶段。

#### Scenario: 非持仓单股与研究综合
- **WHEN** 用户请求现有非持仓单股入口或显式研究综合阶段
- **THEN** 指令不要求无关账户字段、不要求输出 `NO_TRADE` 或执行未开放的组合 Risk，不将研究判断升级为账户建议

#### Scenario: 独立产品入口
- **WHEN** 用户只调用 Intake、交易记录或复盘
- **THEN** 使用该入口的既有输入和权限约束，不自动调用 Council、不取得 CIO 权限、不启动产品研究 MCP

#### Scenario: 完整 fixture Council 兼容运行
- **WHEN** 运行明确属于完整 fixture Council
- **THEN** 保留原动作契约、Risk 否决与有限修订规则，旧 live 完整 Council 不因通用 CIO 文案重新开放

### Requirement: 配置维护必须保持用户确认范围
配置维护 SHALL 将项目行为规则、长期操作说明与本机历史事实分开。长期文档 MUST 不把过往任务的“本次授权”或“本轮未执行”当作当前授权/验收结论。用户级清理 SHALL 只修改已明确纳入方案且当前确实存在的弃用项，并保留其余配置及全局命令规则；配置存在不等于实际加载证明，菜单模型选择不改变产品锁。

#### Scenario: 清理已移除开关
- **WHEN** 按授权清理用户级已移除开关
- **THEN** 仅修改对应项并验证配置仍可解析，用户全局 Git 放行规则和其他插件、模型、权限设置不变，用户级文件不提交到项目

#### Scenario: 警告对应键当前不存在
- **WHEN** 历史 Guardian 警告对应的键在当前配置和 profile 中均不存在
- **THEN** 记录未复现及已有证据，不新增再删除该键、不改写无关配置，也不宣称已证明历史警告的根因
