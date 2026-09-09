## 1. 契约、版本与安全边界

- [x] 1.1 定义并版本化 Replay Capsule、Execution Replay、Runtime Eval、Regression、Ablation 与 Promotion Gate 的 JSON Schema；通过 Schema 单元测试验证合法样例，并对缺字段、未知字段和错误类型执行 fail-closed。
- [x] 1.2 建立统一的模型路由与消耗策略，明确普通开发使用 GPT-5.6 Sol、重复 Runtime Regression 使用 GPT-5.6 Terra、GPT-6 Astra 仅在重大架构或 Eval 方法争议且获得人工批准后使用；通过策略解析测试验证非法模型组合会被拒绝。
- [x] 1.3 为 Replay、Trace、Eval、Regression、Ablation 和 Promotion 失败定义稳定的机器可读 reason code；通过契约测试验证同一失败在 CLI、JSON 与 Markdown 报告中使用一致代码。
- [x] 1.4 固化本 Change 的架构边界：不得引入 Python LLM 编排后端、真实数据 Provider、新投资 Agent、自动交易或自动修改生产 Skill；通过架构扫描测试验证不存在新增模型 SDK 调用、券商写操作或越界 Agent 定义。
- [x] 1.5 固化 canonical action 枚举为 BUY、ADD、HOLD、TRIM、EXIT、NO_TRADE，并将需求中的 REDUCE 类案例映射为 TRIM/EXIT；通过 Schema 测试验证 REDUCE 仍为非法 action。

## 2. Replay Capsule

- [x] 2.1 定义 Replay Capsule 的受保护资源清单和 content-addressed manifest，覆盖冻结 portfolio、PIT Gate 后 Evidence、Agent/Skill/Prompt/Instructions、Schema、Model、Risk Policy、runtime profile 与版本元数据；通过完整样例验证每个对象均可由 hash 定位。
- [x] 2.2 实现 Capsule 构建与密封流程，保存对象内容、相对路径、内容 hash、媒体类型和来源 run_id；通过两次相同输入构建验证逻辑内容标识稳定。
- [x] 2.3 对 Capsule 加入路径 allowlist、符号链接逃逸、大小限制、必需资源和敏感信息检查；通过路径穿越、外部链接、超限文件、缺失对象及疑似密钥样例验证全部 fail-closed。
- [x] 2.4 在 Council 持久化阶段生成 Capsule，并在 Decision Trace 中记录 capsule manifest hash 与对象闭包；通过集成测试验证历史运行不依赖当前工作区文件即可完成 artifact replay。
- [x] 2.5 为旧版无 Capsule 的运行定义兼容策略：允许明确标识为 legacy diagnostic，但不得宣称 execution replay 可复现；通过旧产物样例验证不会静默回退到当前或全局资源。

## 3. 统一 Trace Integrity Validator

- [x] 3.1 扩展 Trace 契约，覆盖 run_id、portfolio snapshot、Evidence closure、PIT、Agent/Skill/Prompt/Model/Schema/Risk Policy 版本、输入输出 hash、terminal_state、failed_stage、Risk lineage、运行拓扑和 Replay 来源；通过完整运行样例验证字段闭包。
- [x] 3.2 建立单一 Runtime Trace Integrity Validator，并让 artifact replay、execution replay、Runtime Eval、Regression、Ablation、check-run 与 Promotion Gate 共同调用；通过依赖测试验证各入口不再维护分叉规则。
- [x] 3.3 实现 terminal-aware lineage 矩阵：Risk 前失败允许 risk_lineage 为空，到达 Risk 后缺少 lineage 必须失败，成功运行必须具有完整 Risk 结果；通过 PRE_RISK、RISK、POST_RISK、COMPLETED、FAILED_VALIDATION 样例验证。
- [x] 3.4 校验 Evidence closure、PIT cutoff、Agent/Skill/Prompt/Schema/Model/Risk 版本及输入输出 hash；通过悬空 Evidence、未来 Evidence、hash 篡改、版本缺失和 run_id 不一致样例验证 fail-closed。
- [x] 3.5 支持 EVAL_ABLATION 与 EXECUTION_REPLAY 的受限拓扑和来源 lineage，同时禁止其冒充默认产品运行；通过合法评估运行与非法产品发布样例验证。

## 4. Artifact Replay 与 Execution Replay

- [x] 4.1 将 artifact replay 明确定义为零 LLM 的历史运行包自洽验证，输出独立 replay result，不修改源运行；通过模型调用计数为零、源目录 hash 不变和篡改检测测试验证。
- [x] 4.2 实现 execution replay 准备阶段：按历史 Capsule 在隔离工作区重建 portfolio、PIT Evidence、Agent、Skill、Prompt、Schema、Model、Risk Policy 和 runtime profile；通过缺少任一关键对象时在 Agent 调用前失败的测试验证。
- [x] 4.3 通过现有 portfolio-council Skill 和独立 runtime Agent 上下文执行 execution replay，生成新的 run_id，并记录 source_run_id 与 source_capsule_hash；通过集成测试验证没有使用 Python callback 模拟 LLM 编排。
- [x] 4.4 实现 execution replay 收尾与比较报告，比较输入/配置闭包、终态、安全不变量和结构化差异，不要求 LLM 文本逐字一致；通过语义不同但契约一致的样例验证可通过。
- [x] 4.5 验证 replay 全程只读源运行，且不得从当前仓库、用户目录或网络补齐缺失版本；通过删除 Capsule 对象和修改当前资源的测试验证均按预期 fail-closed。
- [x] 4.6 密封 Execution Replay 物化工作区的全部文件与目录，并由 Finalizer 根据实际 Agent、Skill、Prompt、Schema、Model、Evidence、Risk Policy 等哈希重新计算配置等价性；通过可写目录和配置漂移负例验证不得继承或写死 `configuration_equivalent=true`。

## 5. Runtime Eval Runner

- [x] 5.1 建立不可变 Eval Job，直接读取真实 Runtime 产物并输出 `eval/result.json`、`eval/report.md`、输入 manifest、确定性评分和语义评分；通过源运行目录前后 hash 一致验证 Eval 不修改源 Trace。
- [x] 5.2 实现确定性指标：Schema 合法性、Evidence 引用正确率、PIT 泄漏、Risk 绕过、Trace 完整性与终态一致性；通过故障注入样例验证安全失败不能被平均分抵消。
- [x] 5.3 为 NO_TRADE 合理性、Analyst Thesis 证据支持、Skeptic 有效反证、CIO 冲突处理和 confidence/证据充分程度一致性建立版本化语义 rubric，并由开发控制面的 dev_eval 使用结构化输出评分；通过 grader identity、model、prompt/rubric hash 和输入输出 hash 留痕验证。
- [x] 5.4 支持对 COMPLETED 和预期 FAILED_VALIDATION 运行进行 terminal-aware Eval；通过悬空引用和非法 Specialist 输出案例验证失败产物可诊断、可评分且不会误报 Risk lineage。
- [x] 5.5 建立小型人工标注校准集，记录 rubric 分歧、可接受区间和 grader 版本；通过重复评分与人工标签比较，验证语义评分达到设计中声明的稳定性门槛。
- [x] 5.6 拒绝人工填写的静态 candidate 分数作为 Runtime Eval 证据；通过仅提供 aggregate JSON 而无真实 run_id、Trace 和 artifact hash 的样例验证失败。
- [x] 5.7 验证 JSON 与 Markdown Eval 报告包含一致的 run、指标、reason code、grader lineage 和安全门禁结论；通过报告一致性测试验证。
- [x] 5.8 为重复语义校准保存独立 `dev_eval` session、执行事件、模型、Prompt/Input/Output hash、时间、评分产物和原始 rollout hash；通过同会话复用、证明篡改和静态评分 JSON 负例验证 fail-closed。

## 6. Regression Dataset 与 Runner

- [x] 6.1 定义版本化 Regression manifest、案例 Schema、typed expected_invariants、执行结果和 cache key；通过 Schema 测试验证不得声明固定股票结论或固定 confidence 数值。
- [x] 6.2 建立 12 个固定案例：正常研究、Evidence 不足、Evidence 全部过期、未来信息泄漏、Analyst/Skeptic 强冲突、悬空 Evidence、Risk veto、高集中度持仓、LLM 过度自信、应当 NO_TRADE、合法 action 契约、Specialist 非法输出；通过清单测试验证案例齐全且 ID 唯一。
- [x] 6.3 为每个案例补齐 portfolio、source_id/as_of/retrieved_at、decision_cutoff、版本信息和 expected_invariants；通过 Evidence/PIT 预检验证测试数据本身可审计。
- [x] 6.4 将悬空 Evidence、未来泄漏、非法 Specialist 输出和合法 action 契约实现为明确的确定性测试注入，不消耗 LLM；通过模型调用计数验证这些路径为零调用。
- [x] 6.5 实现 Regression Runner，调用 Codex-native Council 或确定性故障注入，随后运行 Trace Validator、artifact replay 和 Runtime Eval；通过端到端测试验证每个结果都能追溯到真实产物。
- [x] 6.6 实现基于案例、版本闭包、模型和配置 hash 的缓存，避免无意义重复 LLM 调用，同时保存 token 与延迟；通过 cache hit/miss 和版本变化测试验证。
- [x] 6.7 验证 Regression 判定只检查 expected_invariants，不硬编码 BUY/HOLD/TRIM/EXIT 或具体 confidence；通过两个不同但均合法的投资结论样例验证都可通过。
- [x] 6.8 强制每个 Regression 案例使用全局唯一 `run_id`，并由 Runner 亲自执行 Trace→Artifact Replay→Runtime Eval，保存命令、产物、哈希和执行证明；通过重复 run_id、摘要冒充与底层篡改测试验证 fail-closed。

## 7. Multi-Agent Ablation

- [x] 7.1 定义仅供评估使用的三个 EVAL_ABLATION profile：A=CIO only、B=Company Analyst+CIO、C=Company Analyst+Independent Skeptic+CIO；通过 runtime profile 测试验证默认产品 Council 仍强制双 Specialist。
- [x] 7.2 为 A/B/C 在相同 portfolio、PIT Evidence、Model、Prompt/Skill 版本、Schema 和 Risk Policy 下构建可比运行，并让所有候选决策经过同一 Risk Engine；通过输入 hash 对比和 risk_lineage 验证。
- [x] 7.3 从真实运行和 Eval 产物提取 Evidence grounding、反证质量、NO_TRADE 质量、冲突处理、Risk violation、Schema failure、总 token 和延迟；通过缺失遥测样例验证标记为 N/A 而非 0。
- [x] 7.4 实现可比性检查和 honest no-gain 结论：输入或版本不一致时不比较，多 Agent 无可测增益时必须如实报告；通过不一致样例和持平样例验证。
- [x] 7.5 禁止 A/B 评估拓扑成为生产发布运行或绕过 Specialist 独立性要求；通过 check-run 与 Promotion Gate 负向测试验证。
- [x] 7.6 输出版本化 Ablation JSON 与 Markdown 报告，记录各运行 ID、artifact hash、指标、成本、延迟和限制；通过报告与源运行交叉校验验证。

## 8. Promotion Gate

- [x] 8.1 定义版本化 Promotion Policy 和输入证据图，直接引用 deterministic tests、Runtime Regression、Eval、Ablation、Trace 与版本 manifest 的真实产物 hash；通过缺少或篡改任一输入的测试验证 fail-closed。
- [x] 8.2 实现 Evidence closure、PIT leakage、Risk bypass、Schema success、NO_TRADE 安全案例和 Trace completeness 硬门禁；通过单项失败样例验证平均分或其他软指标不能覆盖硬失败。
- [x] 8.3 实现候选与 baseline 的语义、成本和延迟比较；只有新增或默认启用 Agent 的候选才强制要求达到版本化 Ablation 增益门槛，未产生增益时真实报告；通过适用与不适用候选样例验证。
- [x] 8.4 输出 `promotion/PASS`，或 `promotion/FAIL`、结构化 reasons、`result.json`、`report.md` 和输入 manifest；通过正反样例验证 sentinel、JSON、Markdown 三者一致。
- [x] 8.5 保留人工批准与版本晋升边界：Gate 不得自动修改生产 Skill、Agent、manifest 或版本指针；通过工作区前后 hash 和写入 allowlist 测试验证。
- [x] 8.6 拒绝旧式手工 aggregate candidate 文件作为晋升依据；通过缺少底层 run/eval/trace 引用的样例验证失败。
- [x] 8.7 验证相同不可变输入重复运行 Promotion Gate 得到相同判定和 reason code；通过两次执行结果 hash 对比验证。
- [x] 8.8 Promotion Gate 重新验证测试原始结果、Trace、Evidence/PIT/Risk、Replay、Eval、Regression、Calibration 与 Ablation，不信任上游 PASS 摘要；通过悬空 Evidence、未来信息、Risk 绕过、Trace 缺失、配置漂移和测试失败六类真实底层注入验证全部拒绝。

## 9. CLI、开发控制面与文档

- [x] 9.1 为 artifact replay、execution replay prepare/finalize、runtime eval、regression、ablation 和 promotion 提供稳定 CLI 命令及机器可读退出码；通过 CLI 集成测试验证失败终态返回非零。
- [x] 9.2 更新开发控制面的 dev_eval Agent 与必要 Eval Skill/指令，使其只承担语义评分而不作投资决策；通过 Agent/Skill discovery、结构化 grader 输出和架构边界测试验证，且不得新增投资 Agent。
- [x] 9.3 更新中文运行手册，说明 Run→Persist→Artifact Replay→Execution Replay→Eval→Regression→Ablation→Promotion Gate 的命令、产物、失败诊断、模型路由和成本控制；通过文档命令 smoke 校验验证示例可执行。
- [x] 9.4 更新 runtime、Agent、Skill、Schema、Eval rubric、Regression set、Ablation profile、Promotion policy 的版本 manifest 与 discovery hash；通过版本闭包测试验证 Trace 与 Capsule 可解析所有引用。

## 10. 确定性验证与兼容性

- [x] 10.1 运行 Replay、Trace、Eval、Regression、Ablation、Promotion 的聚焦单元和集成测试，并保存测试命令与结果；全部测试必须通过。
- [x] 10.2 运行全量确定性测试、架构扫描、Schema 验证和 OpenSpec strict validate；不得存在失败、跳过的硬门禁或未解释警告。
- [x] 10.3 验证当前四个 Council fixture 和已归档终态契约仍兼容，新功能不得降低 NO_TRADE、Evidence closure、PIT 或 Risk Engine 的 fail-closed 行为。
- [x] 10.4 验证旧运行包只能获得其能力范围内的明确诊断，不能被错误标记为完整 execution-replay-ready 或 promotion-ready。
- [x] 10.5 在显式独立且可写的 `TMPDIR` 中运行全量测试，分别记录环境错误与断言失败；不得以只读沙箱无法创建临时文件作为产品测试结论。

## 11. 真实验收链路与审计报告

- [x] 11.1 锁定候选版本、Regression/Ablation 集合、模型预算和空白验收输出目录；普通开发验证使用 GPT-5.6 Sol，后续重复真实运行使用 GPT-5.6 Terra，未经批准不得使用 GPT-6 Astra。
- [x] 11.2 使用真实 Codex LLM 完成至少一次源 Council Run→Persist，生成完整 Replay Capsule、Decision Trace 和终态产物；验证 portfolio-council Skill 与独立 runtime Agent 上下文真实加载。
- [x] 11.3 对源运行执行 artifact replay，证明零 LLM 调用、源产物未修改且历史包自洽。
- [x] 11.4 对同一源运行执行一次真实 execution replay，使用新的 run_id 生成完整终态产物，并验证输入、Evidence、配置与版本闭包一致，允许 LLM 输出非逐字一致。
- [x] 11.5 对源运行和 execution replay 运行 Runtime Eval，生成各自的 `eval/result.json` 与 `eval/report.md`，并验证安全硬门禁、语义 rubric 和 grader lineage 完整。
- [x] 11.6 运行完整 12 案例 Regression；仅对需要语义推理的案例调用 GPT-5.6 Terra，复用有效缓存，并验证所有 expected_invariants、token、延迟和真实 artifact 引用。
- [x] 11.7 在设计规定的代表性案例子集上运行 A/B/C Ablation，生成真实可比报告；无论多 Agent 是否提升，都必须如实记录结果和统计限制。
- [x] 11.8 对候选运行 Promotion Gate，并额外执行至少一个安全硬门禁负向案例；候选可真实得到 PASS 或带 reasons 的 FAIL，但负向案例必须 FAIL。
- [x] 11.9 生成可审计验收报告，记录全部命令、run/eval/gate ID、产物路径、版本与 hash、模型、token、延迟、缓存命中、PASS/FAIL 和已知限制；通过报告引用闭包检查验证无悬空产物。
- [x] 11.10 按仓库流程执行独立只读 Release Gate 和人工批准；仅在所有声明门禁满足后标记 Change 完成，归档、同步主规格、检查敏感信息并提交推送。

人工批准与本次收尾范围见 `reviews/runtime/runtime-replay-and-eval-hardening-approval.md`：复用独立证据复核，Change 实现获批；候选保持 `NOT_PROMOTABLE`，本轮不重跑测试或 Release Gate，不修改生产版本指针。
