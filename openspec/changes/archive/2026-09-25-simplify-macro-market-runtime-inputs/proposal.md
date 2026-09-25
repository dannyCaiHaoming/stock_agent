## Why

当前 Macro 与 Market 研究任务在已有能力事实、Evidence Catalog 之外，还会收到从完整 `provider-coverage` 审计记录截取的较大来源覆盖对象。它按 provider 名称筛选，却仍包含与当前研究职责无关的数据集观察和大量证据 ID，增加模型阅读负担，也让来源可用性、缺口和回退边界不够醒目。已有 MRVL 运行产物显示，Macro/Market 的 Evidence Catalog 已按能力收敛；本需求不重复改造它。

## What Changes

- 仅为正向 `MULTI_DIMENSIONAL_HOLDING_RESEARCH` 阶段的 `MACRO_CONTEXT`、`MARKET_STATE` 生成确定性的、按任务相关数据集收敛的模型可见来源覆盖视图；保留 provider 的 `plane` 身份、所涉标的、数据集状态、失败原因、时间、限制和回退含义。全局状态不得伪装为任务局部状态，零 Evidence 的失败或不可用观察不得因压缩消失；没有数据集观察明细的来源仍保留其覆盖状态和限制。
- 完整的 `audit/provider-coverage.json` 及其 hash 仍作为权威审计记录。模型视图从该记录派生并保持可追溯绑定，不以精简视图替换审计原件。
- 用同一冻结 MRVL 输入做确定性新旧包对比，要求两任务的来源覆盖视图及完整 packet 序列化体积实际下降；通过宿主真实运行和独立复核检查信息完整性及研究质量，不以任意压缩率或固定投资结论作为门槛。补充报告汇总、CIO 输入装配和历史 packet 读取的确定性兼容验证，复用现有合法产物，无需为此重跑整套 LLM。
- 不改 Agent 拓扑、`evidence_catalog`、Evidence Gate、Company/Skeptic/CIO 上下文、研究输出 Schema、模型或风险约束；不引入新的通用投影框架或编排器。
- 补齐已暴露的宿主 CLI 配置兼容问题：评估复用现有 CIO 入口的 `--ignore-user-config` 做法，在受影响的多维研究入口保留严格校验并证明产品配置实际加载，使正常运行不再依赖手工建立临时认证链接。
- 对真实 Macro 报告遗漏同一 Gate 内更新观察的问题完成证据定位、最小修正和定向验证；分开判断证据可访问性与模型选取质量，不把旧报告与新报告的不同 cutoff 当作严格 A/B，也不将缺乏历史 vintage 等同于当前冻结事实不可使用。
- 补齐真实运行的计量与引用记录：区分父轮次与子任务用量、缓存与未缓存输入；原生记录不可取得的项明确记为不可得并解释原因，不新增计量平台、不把父轮次总量或字节减量称为两任务 token 节省。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `multi-dimensional-holding-research`：约束 Macro/Market 正式研究任务接收的来源覆盖模型视图及其与完整审计记录的一致性。

## Impact

- 预计实施位置：`product/runtime/multidimensional_stage.py` 的 Macro/Market task packet 组装，以及聚焦的确定性测试。
- 收尾修正限于受影响的宿主启动配置、Macro/Market 输入说明或现有证据查询边界；只有原因明确且确有必要才修改。若需要改变共享基础设施或其他阶段行为，先重新界定范围。
- 验收涉及已有 MRVL 冻结输入、宿主真实 Smoke 产物和只读独立复核；本 Proposal 不启动产品运行。
- 既有审计文件、外部研究输出契约及其他 Agent 不迁移、不退役。
- 本次 Smoke 的 `COMPANY_RESEARCH` 缺口须按前序报告导入状态说明，不冒称公司 Agent 执行失败；技术结构引用失败单独记录并核对是否与本次差异相关。二者不自动扩大为本 Change 的修复任务。Market 原有行情、信用等采集缺口不在本次输入消减中补建。
