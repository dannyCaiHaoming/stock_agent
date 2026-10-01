# 独立复核情境输入

以下均为本Change构造的最小开发情境，不是实际产品运行记录，不证明历史运行成功。请只读取四个Skill交付文件及本材料，对每项返回：选择哪个入口（或不使用）、关键依据、拟采取的最小动作、是否需要新的用户授权及仍未知什么。不执行这些动作、不修改文件、不启动产品或测试。首次回答前不读取本Change的Proposal/Design/Specs/Tasks或前序评审，以免从验收答案反推结论。

Skill文件：`.agents/skills/agent-handoff-development/SKILL.md`、`.agents/skills/change-evidence-closeout/SKILL.md`、`.agents/skills/codex-development-diagnostics/SKILL.md`及其`references/research-handoff-diagnostics.md`。按各情境目的选择，不必每题重读全部文件。

## S1

用户：“修复当前提交字段错误，已授权修改该提交入口并运行受影响确定性检查；不启动模型。”当前输入契约要求`calculation_selections: [{calculation_id, claim_id}]`。工具收据为`{status: "success", task_id: "task-a", calculation_id: "calc-a", value: 12}`；草稿是`{claim_id: "c1", calculation_id: "calc-a"}`；入口校验在装配前返回`required field: calculation_selections`。正式输出不存在。用户未授权其他阶段修改。

## S2

用户：“只诊断为什么没有报告。”运行事件包含模型完成事件及非空草稿，草稿保存可读取；提交事件存在。其后收集事件`open(output_path)`返回`ENOENT`，配置输出路径与实际草稿路径不同。未提供装配成功或正式报告记录。stderr中另有更早的模型列表刷新超时，模型完成事件发生在其后。

## S3

用户：“看看这几份提交为什么不能通过，只解释不要修。”允许集：任务A有`ev-1`，任务B有`ev-2`。三份草稿分别引用`ev-1|source-a`、`ev-2`、`ev-1`。最后一份主张“2025全年营收100美元”；`ev-1`正文为“2024年第一季度营收100万元”，来源和时间可读。身份记录未提供其他冲突。

## S4

用户：“判断两项验收能否复用旧证据，不重跑。”旧测试原输入是`{amount: 100, currency: "USD"}`，保存的执行记录明确调用`normalize_money`并输出`{amount_usd: 100}`，测试断言及代码版本可查。

- A项：当前唯一差异是开发指南链接；函数、输入契约和依赖未改变，要求仍是USD原值保留。
- B项：当前需求改为同时支持EUR转换，函数新增汇率参数；现有证据仍只有上述USD输入和旧函数版本，其摘要为PASS。

## S5

情境项目为独立CSV导出工具，没有OpenSpec、stock_agent目录或发布审批制度。Issue要求导出的两列为`symbol,quantity`，用户已授权修复及一个本地确定性检查。实际生产者生成`{ticker: "DEMO", quantity: 2}`，消费者取`row["symbol"]`时报`KeyError`。原始输入及接口约定可读；开发者又想到增加PDF导出，但Issue不包含它。请说明此项目的修改入口与完成判断依据；不要对真实工作区实施该示例。

## S6

用户：“把帮助文档里一个错别字改正。”提供的差异只改变一个显示文字，没有接口、研究运行或验收收尾请求，也没有发布请求。

## S7

用户已批准需求A完成并要求仅发布A。工作区文件x的同一hunk包含A与未完成需求B的交织修改；现有记录只有编辑前hash，当前Git基线不是B编辑后的状态，没有旧内容、补丁或其他可确定归属的历史。同时文件y是A独占的新说明文件，无其他修改。请说明整体发布结论及文件y是否要求全仓快照。

## S8

用户：“只诊断开发工具启动报错。”当前命令在仓库根目录执行`./bin/helper`，stderr为`No such file or directory`，项目配置实际指向`tools/bin/helper`且该文件存在。没有产品运行目录、模型事件或研究提交。没有证据要求身份hash校验。
