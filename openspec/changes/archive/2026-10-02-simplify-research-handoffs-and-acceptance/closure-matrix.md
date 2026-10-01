# H01–H19 确定性关闭映射

最新补验进度请先看 [当前状态](current-validation-status.md)：normal、独立 Runtime Eval及用户另行批准新输入的predecision CIO补验均通过，进度29/30，仅最终人工完成批准未完成。旧predecision原包仍缺失、不重签；新证据不是修复旧包。下文保留当时结论，不用历史失败覆盖最新成功，不按旧次数重跑。

日期：2026-10-01。仅确认实现与确定性接缝，不是独立评审、真实研究质量、原八维验收或候选晋升 PASS。问题、优先级和规格标题沿用 [Design 第8节](design.md)，没有新增验收条件。

## 执行与源码依据

- 实际命令、完整输出、各输入及产物 hash：[p2-input-delivery-evidence.json](p2-input-delivery-evidence.json)。仓库外原件：`/private/tmp/stock-agent-handoff-input-evidence.UiIrPV`。
- A：40个相关模块的464项确定性接缝通过；B：限定 Claim、资料准备及普通股派发的58项通过；C：最新输入交付及成本的16项通过。三组存在重叠，不将数量相加成独立案例数。实际命令由上述 JSON 保存，不用模块目录存在替代运行证明。
- A/B 执行后仅增强了 `test_research_input_delivery.py` 的工具事件原件保存、`test_research_cost_diagnostics.py` 的独立日志测试。产品源码字节未变；A 的执行时完整文件 hash 保存在外置 `execution-record.json`，C 使用最新639文件快照。不存在把旧测试结果改写成新测试执行的情况。
- 最新20组输入原件、工具输出、事件和目录副本的全部文件 hash 已逐项重算相等；639份源码/配置文件也已按实际字节核对。副本保留原绝对路径文本，因此不是可直接 Execution Replay 的产品包。
- 下表中的函数名是实际已执行模块内的测试定位。A/B/C 对应上面的真实执行，不代表模型调用。

### 获批准备后的证据增量

上述A/B/C和639文件核对描述的是对应执行时快照，不是最新整树未变声明。准备新run时实际发现冻结材料peer final-view与execution Gate身份混用；现已在原准备调用中仅对显式`reuse_frozen_gate`选择source Gate，仍从原件完整验证新执行Gate，历史文件不改写。

最新完整旧/新hash、命令、33项受影响测试和三份准备产物见[bounded-runtime-preparation-evidence.json](bounded-runtime-preparation-evidence.json)。与C快照比较仅`product/runtime/multidimensional_stage.py`、`tests/test_research_materials_stage.py`变化；其它637文件字节相同。旧A/B/C用于未受影响项，不包装为最新源码全套重跑。

此增量对应H16/Task4.3的来源读取与新执行身份分离，以及Task5.3的唯一新run定点准备。正例实际从材料生产者导入到新准备运行；负例包括重新签名后的source Gate/允许集篡改、execution cutoff漂移及未显式复用旧run，均确定性拒绝。5项聚焦与33项受影响测试重叠，不相加。基本面→研报、期权与normal准备成功，只证明准备/绑定及闭包，真实加载、执行、内容和局部修订效果仍NOT_RUN。

## 问题 → 规格 → 实现 → 正负证据

| 问题 / Task | 规格定位（Design第8节的 Requirement） | 实现位置（均相对仓库根） | 正例 / 负例定位及执行 | 确定性结果 / 模型状态 |
|---|---|---|---|---|
| H01 / 2.2、3.1 | 当前语义草稿区分模型判断与技术装配 | `invocation.py`、`codex_hook_recorder.py`及各阶段装配器，均位于`product/runtime/` | `test_common_stock_semantic_handoff`：`test_actual_start_and_stop_keep_research_and_derive_exact_calculation_refs` / `test_technical_echo_and_conflicting_identity_fail_without_formal_report`；A | PASS / NOT_RUN |
| H02 / 3.1、3.2 | 引用选择任务限定且不可模糊修复 | `product/runtime/multidimensional_references.py`、任务原允许集校验 | `test_skeptic_semantic_handoff`：`test_multiple_selected_short_refs_preserve_order_and_research_text` / `test_raw_decorated_unknown_and_cross_type_ids_fail_before_save`；A | PASS / NOT_RUN |
| H03 / 3.2 | 同上，限定报告身份与版本 | `product/runtime/multidimensional_references.py`的scoped Claim | `test_scoped_research_claims`：`test_same_name_keeps_two_report_versions_and_local_name` / `test_old_map_is_readable_but_ambiguous_bare_claims_fail`；B | PASS / NOT_RUN |
| H04 / 3.3 | 语义草稿与引用选择 | `product/runtime/calculation_handoff.py`、`multidimensional_references.py`及文档选择装配 | `test_scoped_research_claims.test_document_reference_locks_exact_content_and_type`同时验证原文档与错误类型/版本；`test_material_semantic_handoff.test_unknown_selection_and_claimed_foreign_identity_fail_closed`；A/B | PASS / NOT_RUN |
| H05 / 2.1、3.3 | 派生计算选择真实成功结果；先结构后血缘 | `product/runtime/calculation_handoff.py`、`fixture_mcp.py`、原计算校验 | `test_calculation_handoff`：`test_actual_stdio_to_hook_preserves_prose_and_assembles_exact_result` / `test_native_whole_draft_structure_precedes_damaged_receipt_at_actual_hook`、`test_rehashed_ledger_cannot_override_actual_event_or_report_result`；A | PASS / NOT_RUN |
| H06 / 3.4 | 材料CIO及Eval审计来自真实记录 | `product/runtime/research_materials_stage.py`工具审计 | `test_material_semantic_handoff`：`test_actual_start_schema_and_stop_assemble_fixed_fields_and_tool_audit` / `test_unexecuted_missing_and_duplicate_intents_fail_without_rewriting`；A | PASS / NOT_RUN |
| H07 / 2.2 | 提交回执精确绑定且不复制hash | `product/runtime/research_submission.py`及可信Stop解析 | `test_bounded_research_submission`：`test_valid_first_submission_reaches_original_formal_report` / `test_exact_rejected_receipt_is_not_latest_valid_draft`、`test_wrong_credential_has_no_target_state_or_quota_effect`；A | PASS / NOT_RUN |
| H08 / 3.1 | 当前语义草稿与技术装配 | 同H01；各角色保留独立业务Schema | 资料、普通股、八维、独立反证、两类CIO、两类Eval模块均在A；合法native稿与冒用身份/技术字段负例；C保留全部当前入口输入原件 | PASS / NOT_RUN |
| H09 / 2.3 | 材料CIO及Eval审计来自真实记录 | `product/runtime/cio_handoff.py`、`predecision_cio_stage.py`、`run_package.py` | `test_cio_handoff`：`test_real_read_and_native_assembly_preserve_decision_then_risk` / `test_catalog_does_not_prove_read`、`test_all_required_reports_must_be_read`；`test_cio_reference_handoff`覆盖另一CIO；A | PASS / 两类新Hook待真实补验 |
| H10 / 2.4 | 同上，评分语义与元数据分离 | `product/runtime/common_stock_eval.py`、`runtime_eval.py`、`eval_execution_proof.py` | `test_eval_handoffs`：`test_fixture_runtime_also_uses_native_draft_and_real_input_read` / `test_runtime_wrong_model_and_metadata_in_draft_are_rejected`；A；C保存实际模拟输入读取事件 | PASS / Runtime Eval新加载待补验；普通股Eval NOT_RUN |
| H11 / 5.1 | 原Agent局部纠正有限并复验 | `product/runtime/local_revision.py`、`cio_local_revision.py`、`eval_local_revision.py`及原Hook/MCP | `test_cio_local_revision`：`test_both_main_cio_entries_repair_one_field_preserve_base_and_reverify` / `test_scope_second_failure_technical_fields_and_illegal_reference_fail_closed`；普通股/资料/Specialist/Eval对应修订模块同在A | PASS / NOT_RUN |
| H12 / 2.5 | 当前组件版本单一批准来源 | `product/runtime/versioning.py`、`product/version-manifest.json`、显式镜像检查脚本 | `test_component_versions`：`test_current_actual_components_and_stage_adapter_scopes_match` / `test_approved_manifest_is_not_silently_inferred_from_actual_resources`；A | PASS / 声明一致不等于加载 |
| H13 / 4.1 | hash对象口径及历史算法 | `product/runtime/hashing.py`及对应调用方 | `test_hashing_contracts`：`test_file_bytes_and_canonical_object_have_distinct_scope`、`test_historical_hash_vectors_stay_byte_compatible` / `test_invalid_value_is_located_and_nonfinite_is_rejected`；A | PASS / 确定性能力不要求LLM |
| H14 / 4.2 | Memory事实与观察/Gate视图分离 | `product/runtime/research_memory.py`、`product/mcp/provenance.py` | `test_research_memory`：`test_nested_fact_value_fields_are_not_observation_metadata` / `test_gate_freshness_is_view_only_and_ambiguous_history_fails_closed`；A | PASS / 确定性能力不要求LLM |
| H15 / 2.6 | 先结构后血缘且所有约束生效 | `product/runtime/schema_validation.py`、原决策专用校验及MCP入参校验 | `test_strict_schema_validation`：`test_no_trade_conditional_and_sibling_constraints`同时测null/0；`test_local_ref_does_not_skip_sibling_or_nested_constraint` / `test_unknown_keyword_dialect_and_remote_ref_fail_before_validation`；A | PASS / NO_TRADE安全边界保留 |
| H16 / 4.3 | 冻结读取与当前执行准入分离 | `product/runtime/predecision_cio_stage.py`、`independent_skeptic_stage.py`、Memory/浏览器只读入口 | `test_cio_artifact_reading`：`test_actual_package_to_frozen_inputs_survives_move_without_rewriting_history` / `test_missing_contract_unknown_version_and_path_escape_fail_readonly`；`test_skeptic_artifact_reading`、`test_research_handoff_consumers`；A | PASS / 未启动Execution Replay |
| H17 / 4.4 | 当前数据路由及消费状态共享权威映射 | `product/runtime/research_input_topology.py`、`research_consumption_audit.py`、原任务路由 | `test_research_routing_contract`：`test_actual_prepare_and_query_producer_reach_scoped_consumer_counts` / `test_wrong_security_and_skeptic_do_not_gain_forward_access`；A | PASS / 配置、获取、查询、引用分开 |
| H18 / 4.5 | 研究结果区分进程契约来源与内容 | `product/council/multidimensional_output.py`及CLI/展示消费者 | `test_research_terminal_projection`：`test_author_status_is_projected_identically_from_saved_report_to_browser` / `test_exit_zero_with_six_saved_one_failed_one_unstarted_is_not_stage_pass`、`test_not_run_is_not_failed_or_reviewed_or_promoted`；A | PASS / 内容未审阅不转READY |
| H19 / 6.1、6.2 | 角色方法任务分层；当前验收义务与历史分离 | `.codex/agents/dev_*.toml`、对应Agent/Skill/生成Prompt、原八维当前义务及历史索引 | `test_research_instruction_layering`实际交付/模型与权限解析；`test_research_acceptance_history`原任务/规格字节相等及未完成义务覆盖；A | 实施与检查PASS / 独立Reviewer PENDING |

测试文件均在`tests/`。规格定位的完整中文标题与Requirement对应关系见Design第8节，不以本表替代规格。H01–H11的研究语义仍归模型；格式及机械装配通过不证明Thesis正确。

## 输入与统计 Task 5.2 / 5.4

- C包含4种资料准备、普通股、八维全部任务、独立反证、fixture双Specialist、fixture/predecision双CIO、普通股/Runtime双Eval，共20份表示测量。八维是合成数据与显式缺口报告，不是新真实同批8/8。
- 明确位置删除重复技术包装；不递归按字段名剔除。完整原值、单位、期间、主体、来源时间、脚注、否定、冲突和来源限制经原目录与授权工具读取保持等价。实际参数、正式业务Schema、PIT/Risk与引用闭合未放宽。
- 工具原始响应与短引用运输表示分别统计；全部工具而非仅query记录已观测字节及缺失项。父CLI每turn usage、子会话累计usage分别沿原日志/执行证明读取，缓存是input的子集，不再次加计。全链费用仍为未观测。
- 初始表示并非全部变短：资料准备额外语义指导、无Evidence的宏观/市场任务增加字节，真实记录正数差额，不删资料凑比例。CIO测量分别限定冻结JSON与嵌入request包装，不能当完整历史Prompt/token基线。
- 零LLM合成事件的usage正负测试只证明统计代码口径；不声称本次消耗了这些token，真实usage/成本需Task6.5。

## 有效证据复用与尚未完成

本轮A/B重验现行接缝，不依赖历史PASS摘要。旧运行、原失败稿、旧版本锁和冻结包只在对应只读兼容测试及原历史章节中复用；不包装为当前候选真实运行或晋升证据。未签名历史桩拒绝进入可信成本统计，不补写hash冒充新证明。

Task6.4已由[人工限定批准](bounded-runtime-validation-approval.md)完成，总进度27/30。Task6.5–6.7仍未完成：获批宿主运行及内容核对、独立只读Reviewer、最终人工完成批准与同步归档。准备产物不代替真实执行；当前工具禁止操作宿主Terminal，外置一次命令见`host-run-instructions.md`。predecision CIO仍缺真实正反包完整备份；Runtime Eval须等待本次normal合法底层产物。原八维Change继续暂停，最低内容与预算不变。完整Gate、Regression、Calibration、Ablation、Promotion、本Change真实模型均未启动，当前模型预算消耗0/5父、0/6子。
# 2026-10-01 真实执行后的状态补充

本节覆盖文内早前“准备成功、真实NOT_RUN”的时点结论，不覆盖原失败记录或原八维最低标准。完整原件与hash见[bounded-runtime-execution-evidence.json](bounded-runtime-execution-evidence.json)，逐项内容说明见[implementation-evidence.md](implementation-evidence.md)末节。

- 基本面→研报与OPTIONS_FLOW已实际执行，分别2/1子Agent，正式报告及定点契约通过；内容为主开发核对，独立复核NOT_REVIEWED。
- normal实际启动失败：全局CLI配置未知字段`mcp_servers.computer-use.type`，未到模型；不得用其他两项成功覆盖此项。
- H06/H07/H17消费事件接缝本轮发现真实格式缺口，已由精确稿/packet身份重验修复；80项受影响确定性测试通过，真实原件只读消费统计成功，未回写历史事件或追加LLM。
- 有界预算已消耗3父进程启动、3子Agent，normal不可自动重试；predecision包缺失、Runtime Eval NOT_RUN、独立Reviewer NOT_RUN。
- Task6.5–6.7仍未完成，整体27/30；CHANGE_REVIEW未出具，CANDIDATE_PROMOTION=NOT_PROMOTABLE。

## 追加 normal 后的当前状态

以[normal-runtime-handoff-evidence.json](normal-runtime-handoff-evidence.json)覆盖上节“normal未到模型”的当前时点结论，原失败保留。追加normal已实际执行2个Specialist并保存首稿，但CIO工具启动/白名单接缝失败，未形成合法终态。该两处接缝已修复，52项受影响确定性测试通过；修复后真实normal仍NOT_RUN，不能将首稿SAVED当完整Council通过。

H09/H19缺口明确为修复后的真实normal加载及CIO消费证明，H10 Runtime Eval等待其合法产物；predecision仍为SOURCE_PACKAGE_MISSING。新增接缝证明不替代H01–H19原矩阵或独立内容复核。总消耗4父进程启动、5子Agent，两个normal项目额度均已消耗；不得挪用其它项额度重试。Task6.5–6.7未完成、27/30，原八维继续暂停；不触发完整Gate或晋升。

## MCP 修复后补跑及 CIO 阶段绑定的最新状态

最新授权 normal 的两个 Specialist、报告读取和 CIO 首稿均已执行，但在 Risk 前被 `CIO_LOCAL_REVISION_DELIVERY_DRIFT` 拒绝，未形成合法终态。根因为启动尚无 CIO 输入与研究后已准备输入的阶段统计误比较；本次最小修复及实际顺序正负接缝由72项确定性测试覆盖。完整原件标识、运行/当前产品保护快照及文件hash见 [normal-cio-phase-binding-evidence.json](normal-cio-phase-binding-evidence.json)，不能把该失败包或合成接缝当修复后模型运行通过。

H09/H19仍需新修复下合法 normal 的终态及消费证明；H10仍需其合法产物上的原获批 Eval。predecision 的原完整正反输入包仍缺失；没有补造或替换。当前累计5父进程启动、7子Agent，三个normal额度已消耗；不可挪用其它用途或自动追加。Task6.5–6.7仍未完成、27/30；独立复核未开始，CANDIDATE_PROMOTION=NOT_PROMOTABLE。修复不修改原八维最低内容、Risk/PIT、权限、历史证据或锁，不触发完整Gate。

## 阶段绑定后最新运行：Risk 到达但 Trace 消费拒绝

最新一次获批normal已真实完成两个Specialist、CIO宿主重验及Risk，保存decision/report/trace；但native装配多写Trace顶层`cio_report_consumption`，被原Schema/Validator拒绝，整体仍FAIL，不能按SAFE_NO_TRADE标签或退出0勾选。该证明已改存既有events扩展点，89项相关确定性测试通过；新接缝直达Trace/Artifact Replay/Eval输入准备，不放宽白名单、不改失败原件。完整证据见 [normal-trace-consumer-evidence.json](normal-trace-consumer-evidence.json)。

H09/H19的阶段绑定、真实报告消费和Risk已有上述范围内运行证明；完整合法normal/Trace发布仍待修复后新运行，H10真实Eval未启动。predecision原包缺失、独立复核/最终人工批准未完成。累计6父进程启动、9子Agent，四次normal额度均消耗，不能挪用其他用途。Task6.5–6.7保持未完成，27/30；不把有决策文件等同于Change完成或Promotion PASS。

## 最终定点补验及独立复核

前述为历史时点，不是当前未完成清单。normal及独立Eval已据实际原件与独立复核关闭；本轮新来源与predecision证明见 [真实执行记录](predecision-native-handoff-validation.md)及[独立增量复核](independent-predecision-review.md)。H09双CIO现有获批真实证明，H10独立Runtime Eval有真实证明，普通股Eval仍按其确定性范围而非冒称模型运行。

新source绑定、核心选择、模型白名单、Hook子身份、MCP attempt index及提示协议接缝各组测试/独立复核通过；公司、五核心、反证和主线程CIO真实执行，CIO终态COMPLETED_RESEARCH_SYNTHESIS。原反证期间错误未传播、保留为非阻断内容缺陷；成本记录不宣称整个CIO效率改善。Task6.5/6.6完成，29/30，仅6.7人工完成批准/限定发布未完成。原八维继续暂停，候选NOT_PROMOTABLE；不触发完整Gate或新模型调用。
