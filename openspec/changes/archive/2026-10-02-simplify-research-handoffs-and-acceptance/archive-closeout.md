# 归档发布收尾（2026-10-02，Asia/Shanghai）

本页是最终收尾入口，历史失败、预算、原源码快照及取证文件原样保留。用户在八维需求已归档发布后明确要求：

> 那这个需求simplify-research-handoffs-and-acceptance 也可以同步且归档了

此授权接续原最终完成批准，允许本 Change 的规格同步、归档、限定提交及推送；不启动新研究、真实 Eval、Replay、Regression、Ablation 或 Promotion。

## 原发布归属阻断的解除

原 [发布归属记录](publication-scope-review.md)是当时真实停止记录，不删除、不把旧阻断改写为未发生。八维相关共享机械实现现已由 `05905dcd0f136bbce3a8d460d26d4aad38a3958e` 发布，收尾记录为 `ebceab37f9b47cef16f62b81decde5c5c9c14734`；本次以该 HEAD 为可恢复基线审阅剩余差异。

- 已发布的引用、计算、序列化、Schema、路由、Memory、材料准备及八维交付作为共享依赖复用，不重复认领其全部实现。
- 本次发布剩余的普通股/独立反证/两类 CIO/两类 Eval 语义草稿及技术装配、实际读取证明、一次原会话修订、历史只读适配、组件镜像检查及角色分层，对应 H01–H19 已批准边界。
- 明确排除 Tiger/私人账本/交易复盘、其他活跃 Change、根开发模型与权限设置、Luna 专项文档测试、额外 `--question` 入口，以及未归属于本 Change 的同行/calendar 测试。
- 根与产品指令、版本 manifest、环境说明、宿主脚本及混合测试只提交已审阅内容；其他用户改动保持原样，不整体暂存、不回退源码。

## 证据复用及同步核对

- H01–H19 接缝、normal 完整闭环、独立 Runtime Eval 及 predecision CIO 的原适用范围见 [验收入口](current-validation-status.md)、[独立内容复核](independent-predecision-review.md)。本次没有新模型调用，不把普通股 Eval 的确定性检查说成真实评分运行。
- 实际只读重验 CIO 原七个关键文件字节 SHA-256，与 [运行记录](predecision-native-handoff-validation.md)逐项一致；原 process_exit_code=0、stage_status=COMPLETED_RESEARCH_SYNTHESIS、timed_out=false、source_integrity_unchanged=true。研究内容的 LOW_CONFIDENCE 不被包装为投资确定性。
- 原640项取证映射按原增量链重建后 hash 仍为 `acb6109ca6e83a6259c8ff6f820623e1ae4d38f9fc30fbca1460541e6ee5fe49`。它标识当时现场，不代表当前全仓仍与该快照相同。八维后续修补及并行工作已改变部分文件，本次不重签快照、不改历史版本锁。
- 三个 delta 逐条核对：`codex-development-environment` 6 条、`multi-dimensional-holding-research` 4 条、`research-handoff-contracts` 11 条。已有主规格原要求与 Purpose 均保留，新主规格没有 delta 操作标题。
- 严格校验：本 Change valid；21项主规格通过、0失败。原有长段落提示不是校验失败。
- 为归档兼容仅修正历史保全测试的目录定位：读取同一八维历史文件，不修改其记录或原 hash。

## 不偷换完成层级

原八维 Change 已通过自身新同批内容8/8验收并另行归档，位置为 `../2026-10-01-complete-eight-dimension-source-consumption/`（归档后相对路径），不是由本 Change 的定点成功代为关闭。设计和历史记录中的“暂停/未完成”是当时边界，不是最新状态。

原 Skeptic 研发比较期间错误未被 CIO 传播，原稿仍保留；CIO 输入冗余及远端 compaction 重试造成高消耗亦保留。不宣称全链成本下降、账户适配、交易建议或候选晋升。`CHANGE_REVIEW: PASS` 与 `CANDIDATE_PROMOTION: NOT_PROMOTABLE` 分开。

## 发布状态

人工完成批准有效，限定候选的零模型检查及独立只读发布复核已通过；三个主规格已同步，本 Change 已归档至 `openspec/changes/archive/2026-10-02-simplify-research-handoffs-and-acceptance/`。

实现、主规格及归档提交为 `cf9e087c3dfd637df314d7572d2a1347dd36581a`，已成功推送至 `https://github.com/dannyCaiHaoming/stock_agent.git` 的 `main`，并通过实际远端 `refs/heads/main` 核对一致。Task6.7 在此真实发布结果后勾选，任务30/30完成；本页及验收入口的最终状态补记单独以文档收尾提交发布，不将其提交自身hash写入自身。

提交前限定120路径经过范围及敏感信息检查，82项实现与规格文件和已验证候选逐字节一致；归档后的21项主规格严格校验通过。发布未替换工作区；Tiger、交易复盘、其他活跃 Change、本地权限及模型配置仍为未纳入本次提交的用户修改。已接受的非阻断问题与 `CANDIDATE_PROMOTION: NOT_PROMOTABLE` 状态不变。

## 限定候选的零模型验证

实际源码候选 `ca95e1634cd77c48442fc99572a0c166f3ec8a88`，基线 `ebceab37f9b47cef16f62b81decde5c5c9c14734`。验证从临时 Git 导出执行，原工作区未被替换；这是发布范围核验，不是新产品运行后端或候选晋升。82项限定实现及主规格字节映射见 [publication-source-snapshot.json](publication-source-snapshot.json)，机械重验、28项当前现场与历史640映射差异及测试口径见 [publication-validation.json](publication-validation.json)。

| 实际检查 | 结果及适用范围 |
|---|---|
| 40模块首轮 | 631 tests，252.433s，5 failures / 10 errors；失败真实保留，不能称全套通过 |
| 首轮后5模块定位 | 74 tests，64.407s，3 failures / 9 errors；定位到旧 Demo 镜像，无新模型 |
| 第一轮兼容修补后7模块 | 84 tests，3.682s，4 failures / 10 errors；旧 Company Skill 镜像及另一grader资源hash仍未同步，保留失败 |
| 最终7模块聚焦 | 84 tests，3.240s，OK；覆盖全部首轮失败模块、版本/历史及动作Schema边界 |
| 版本镜像与格式 | PROFILE_VERSION_MIRRORS_OK；git diff --check通过 |

最后一组实际命令为 `env PYTHONDONTWRITEBYTECODE=1 TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -B -m unittest tests.test_native_output_handoff tests.test_nested_codex_launcher tests.test_runtime_foundation tests.test_agent_package_demo tests.test_component_versions tests.test_research_acceptance_history tests.test_native_decision_contract -q`。不把分组相加为独立样本总数，也不宣称631项在最终候选全部重跑。其余首轮检查按未受影响 Runtime 行为、依赖及原验收范围复用。

收尾最小修补仅涉及：当前 grader Skill/Agent实际字节hash显式同步；零LLM Demo 镜像对齐既有 Company 五项方法及两种已知完整MCP目录，角色工具权限不扩展；测试取消固定仓库目录，准确断言现行重复提交拒绝码；历史保全测试支持已归档目录。未知/不完整工具目录仍拒绝，角色绑定与PIT/Risk/评分/引用校验不改。没有新增生产 Agent、来源、编排器、模型调用或研究语义修复。

独立Reviewer `/root/macro_binding_admission_review` 对初始限定范围及上述增量只读复核，最终源码候选结论 PASS：Company 五项方法与现有 Profile/Agent 一致，工具仍为 query/calculate；grader Agent hash与实物一致且Terra模型不变；无新增Runtime差异或Tiger/交易/额外问题入口。Reviewer没有编辑、测试或模型运行，主线程记录已返回结论，不用其静态PASS代替真实内容验收。
