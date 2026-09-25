## Context

参见 [proposal.md](proposal.md)。当前 `product/runtime/multidimensional_stage.py` 在写入完整 `audit/provider-coverage.json` 后，把 `fallback_policy`、完整 `capability_routing` 和按 provider 名称过滤的 `providers` 放进每个研究 packet。同一 provider 可能跨 `plane`，而单条 provider 记录可含多个与任务无关的数据集和长 `evidence_ids`。Macro/Market 的 `facts` 与 `evidence_catalog` 已按能力选取，不是本次减量目标。

## Goals / Non-Goals

**Goals:** 缩小 Macro/Market 模型可见的来源覆盖信息，同时让模型能判断正式任务的实际交付、失败、时间、来源层级和回退边界；保留从冻结审计原件到 packet 的可验证关系。

**Non-Goals:** 重做采集/Normalize/PIT、重划 Agent 职责、裁剪 Evidence Catalog、变更报告 Schema、对全部任务推广通用投影框架、改变来源优先级或投资判断。

## Decisions

### 1. 在现有 packet 组装边界做两个能力的确定性投影

仅在 `stage == MULTI_DIMENSIONAL_HOLDING_RESEARCH` 且 capability 为 `MACRO_CONTEXT` 或 `MARKET_STATE` 时使用同一小型投影函数；独立反证阶段及其他能力保持现有 packet 内容与说明。两个阶段共用组装入口，不能只判断 capability。投影读取已经构建并保存的完整覆盖对象，不重新查询供应商、不新增 Agent/工具，也不改变审计文件。保留原始 `coverage_hash`，以阶段和任务能力标记模型视图，packet 继续由既有 hash 机制锁定。准备阶段校验原件 hash 和投影所引用观察的身份/时间；无法核对则在分派前失败。新增校验仅适用于新视图，旧 packet 继续使用原有读取与 hash 校验路径。

曾考虑直接裁剪审计对象或给所有 Agent 换新 Schema；前者损失回放和复核材料，后者扩大迁移面，均不采用。

### 2. 用明确的消费集合选择观察，来源身份不降维

候选 provider 范围沿用现有 `provider_scope`。相关数据集集合由本任务既有 capability 路由、实际被选入任务的 Evidence 所属数据集，以及当前 Macro/Market 明确消费的跨域背景数据集共同确定；无 Evidence 的路由/背景数据集仍须保留其失败和不可用观察。实现时先核实真实任务资料与拓扑映射，列出该小集合并用冻结样本锁定，不以 `DATASET_CAPABILITY_ROUTES` 单独作为过滤条件。未知或无法证明无关的观察采取保守保留，不静默丢失。

投影以 `(plane, provider, security_id, dataset)` 等原有身份维度保留数据集观察。当前官方宏观等 provider 可能已有 Evidence、却没有 `dataset_observations`；候选 provider 记录不得因观察为空或过滤后为空而删除。保留它的全局覆盖状态、计数和限制，并区分原件没有明细与本任务没有相关明细；不得由空数组推断未采集、失败或无 Evidence。来源全局计数不是任务交付数，也不是各 `plane` 独占的贡献数。

模型视图的字段约定如下；这是现有 packet 内部字段约定，不新增外部报告 Schema 或通用投影注册器。

| 对象 | 保留或转换 | 删除或禁止推断 |
| --- | --- | --- |
| 视图身份 | `view_kind=TASK_SCOPED_PROVIDER_COVERAGE`、`stage`、`capability`；原件 `schema_version` 以 `source_schema_version` 命名；保留原件 `coverage_hash`、`decision_cutoff` | 不把原件版本或 hash 冒充精简对象的版本/hash；视图完整性由既有 packet hash 保护 |
| `fallback_policy` | 完整保留原有值 | 不改变回退权限 |
| provider 身份与限制 | 原样保留 `plane`、`provider`、`region`、`access`、`declared_status`、`limitations` | 不合并同名的不同 `plane` 记录 |
| provider 全局观察 | 把 `observed_status`、`delivery_status`、`evidence_count`、`capture_evidence_count`、`gate_delivered_evidence_count`、`failure_codes`、`actual_research_use_status` 原样放入 `global_coverage` | 不把这些值改称任务局部状态或局部计数，不从覆盖成功推断已被研究引用 |
| 数据集观察 | 仅保留相关记录的 `security_id`、`dataset`、`status`、`failure_code`、`checked_at`、`as_of`、`limitations`；保留原有空值 | 删除 `evidence_ids` 列表；不补造缺失来源、时间或成功状态 |
| 明细范围 | 增加 `dataset_observation_scope`，取 `RELEVANT_OBSERVATIONS`、`NO_RELEVANT_OBSERVATIONS` 或 `NO_DATASET_DETAIL`，分别表示有相关观察、原件有明细但筛选为空、原件本无明细 | 后两者仅描述视图明细，不能替代采集状态 |
| `capability_routing` | 只保留 `target_capability` 匹配本任务的观察，保留 `dataset`、目标 capability、三项 capture/Gate/delivered 计数、`delivery_status`、`actual_research_use_status`；`exclusions` 按原有 reason 汇总为计数 | 删除逐 Evidence 的排除清单及全局 routing 状态/失败码；原有全局路由完整性校验不变，精简视图不另造第二套门禁 |

任务说明同步解释 `global_coverage` 和明细范围；模型负责解读来源限制及投资影响，hash、路由完整性和计数核算由确定性层完成。Evidence Catalog 与查询工具继续负责证据定位，模型视图不重复承担该职责。

曾考虑只按 provider 名称或只按路由表过滤；前者几乎不能减量，后者会丢掉 Market 基准/跨资产和 Macro 持仓敏感性所需背景，均不采用。

### 3. 先比较信息完整性，再比较输入负担和研究效果

以同一冻结 MRVL 输入生成变更前后 packet，确定性核对完整审计文件/hash 不变、保留相关成功及失败观察、跨 `plane`/多标的身份、零 Evidence 缺口、cutoff 和 packet hash。使用相同 JSON 序列化方式计量，要求 Macro 和 Market 各自的 `provider_coverage` 及完整 packet 字节数均下降；未下降不能宣告消减完成。新旧 packet hash 应各自校验通过，不要求两者相等；其他阶段/能力按相同身份和冻结输入比较内容不变，避免把 run_id 等自然差异误判为回归。字节数不等同实际 token 用量。随后按仓库宿主入口分别真实运行 Macro 和 Market，记录模型输入 token（注明缓存影响）、证据查询与引用、来源局限、反向情景和具体缺口；独立只读复核判断是否有实质性质量回退。不设任意百分比节省门槛，不要求投资结论与旧版本逐字相同。

增加一组确定性兼容检查：在合法的同 run、同 cutoff 和既有绑定约束下，将 Macro/Market 报告走过现有汇总及 CIO 输入装配入口，确认报告契约和来源缺口能被消费；复用既有合法样本或聚焦夹具，不拼接不同 run 的真实报告。另验证旧 packet 的加载与 hash 核对、新 packet 的加载与校验、独立反证阶段输入不变。这些检查不启动 CIO 模型或历史 Execution Replay；真实 LLM 验收仍限定 Macro/Market。

仅跑合成 demo 或只看 packet 体积不能证明 Agent 保持研究能力，因此不作为单独完成证据。

### 4. 收尾聚焦启动兼容与已发现的内容问题

2026-09-25 的运行 `/private/tmp/simplify-macro-market-host-fixed.qGnrxM/run` 已保存 Macro/Market 报告，但依赖临时隔离配置；该结果证明目标任务能运行，不证明默认启动入口已经修复。优先评估现有 `predecision_cio_stage.py` 使用的 `--ignore-user-config`，在受影响入口显式保留产品配置、所需 MCP、模型和权限设置，继续启用 `--strict-config`。先确认当前 CLI 支持及最终参数，再通过真实宿主事件证明产品配置实际加载。不修改用户全局配置、不持久化认证副本、不新建第二套 launcher；若当前 CLI 不支持，则记录真实阻断，不以关闭严格校验替代修复。

Macro 报告引用 2026-07 零售销售 `-0.54%`，遗漏同一 Gate 内 2026-08 `+1.24%`。该更新 Evidence 仍在允许列表中，因此不能直接断言投影删掉数据。排查顺序是 Gate 与允许 ID → packet 目录和查询可见性 → 已有查询记录 → 报告选取与解释；分别记录观察期、检索时点及 actual/previous 角色。已有记录不足时明确未知，不为证明原因反复启动模型。

最小修正以原因决定：确属可见性或来源覆盖误删则修复投影/既有查询路径；证据可读但模型漏选，则优先完善正向 Macro/Market 任务说明，要求用于当前状态判断的指标核对截止点内最新可用观察，引用旧值须解释用途及更新值的影响。不硬编码具体日期、数值、投资方向或“必须引用所有 Evidence”的清单，不新增评分器、Agent 或数据管线。历史 vintage 未证实仍限制历史回测，但不能因此否定截止点前已冻结的供应商当前快照。

修正后使用相同冻结输入、已授权模型，经既有宿主入口做受影响任务的最小真实验证，保留旧失败及新产物，不手工修改模型报告或拼接跨 run 产物。优先让一次必要的目标任务运行同时验证启动修复及内容修正；若入口只能运行完整多维阶段，事先记录实际分派范围，验收仍聚焦 Macro/Market，不扩大到整套 CIO LLM 链。非目标任务事件单独归集，不自动追加重试。

### 5. 完成证据与范围边界

- 已有确定性减量、审计绑定、历史读取和下游装配证据继续复用；发生相关代码变化时才补受影响检查。
- 真实运行记录注明请求/实际模型、Gate/cutoff、packet/报告身份、引用、来源限制、持仓传导和反向条件。优先从既有原生事件取得各任务 input/cache 用量；父轮次用量单独展示，不能代替子任务计量。缺少逐任务用量或查询日志时逐项标 `UNAVAILABLE`、记录原因与替代证据，独立复核判断可审查性。取得不可得原因及引用核对记录可完成记录任务，但不能据此宣称 token 节省；不为计量扩建基础设施。
- 内容遗漏必须修正并复验，或由独立复核以具体证据证明不构成实质问题。确定性可访问性检查不能单独代替研究质量复核；不要求投资结论逐字一致，不自动启动正式 Regression/Ablation。
- 此次 8 个分派任务不包含独立 `COMPANY_RESEARCH`，该能力由前序报告导入提供。核对导入缺失/不兼容原因；技术结构 `DIMENSION_REPORT_CLAIM_UNGROUNDED` 属于已观察到的另一任务失败，应记录其与本次差异的关系。若发现由本次实现引起，则修正并补受影响验证；否则作为非目标问题保留，不把它们伪装为通过，也不以此要求本 Change 补建公司研究或行情采集。
- 独立复核须检查最终差异、规格场景、真实报告及上述证据限制，给出明确验收结论。阶段 `PASSED`、文档齐全或任务勾选均不等于 Change 完成；复核后待人工完成批准，再同步归档。

## Risks / Trade-offs

- **相关集合误漏掉零 Evidence 的背景数据集** → 把已消费的跨域背景数据集显式纳入，并用失败/空证据样例做聚焦测试；不确定时保守保留。
- **全局 provider 状态与局部数据集状态混淆** → 使用明确的范围标签及任务说明，测试混合成功/失败记录。
- **按 provider 字符串合并跨 plane 记录** → 以完整来源身份组织观察，并测试同名 provider 的多 plane 记录。
- **压缩后模型忽视来源限制** → 宿主真实运行加独立内容复核；若质量退化，撤回模型视图接线，完整审计及旧 packet 组装路径不受损。
- **旧新运行的缓存与模型随机性影响性能比较** → 使用同一冻结输入、同一模型和独立输出目录，分开报告确定性体积与实测 token/内容，不把单次运行视为精确性能基准。

## Migration Plan

不迁移历史 run。变更仅作用于新准备的正向 Macro/Market packet；旧 run 继续按原 packet/hash 读取，并保留既有重放契约，本次以确定性读取验证兼容性。实施时先加聚焦验证，再接入投影并做冻结 MRVL 比对、下游装配检查、宿主 Smoke 和独立复核。若任一资料完整性或研究质量门槛失败，保留完整审计，回退新增 packet 投影接线；不需要修改持久化记录或外部报告消费者。
