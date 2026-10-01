# 实施证据（进行中）

最新补验状态及精确证据见 [current-validation-status.md](current-validation-status.md)：本轮 normal 完整闭环、独立 Runtime Eval 已通过。以下记录为历史时间线，不代表最新仍需重复执行。

## 2026-09-30：普通股语义提交及跨文件协议绑定（Task 3.1 部分推进）

新 prepare 在 manifest/task/invocation 中声明 `equity-research-semantic-draft/1.0.0`，当前草稿由原业务 Schema 派生，实际 Start 不再要求模型填写 run/invocation/agent、Skill/来源绑定或顶层 `artifact_refs`。Stop 先核真实派发/Start 身份，再校验原语义草稿，才读取计算执行记录；从模型明确写入研究字段的计算引用集合装配顶层索引，并复用原 envelope、引用交付校验及正式产物生成，不挑选新证据、不补写计算结果、不改研究句子。旧正式报告读取结构仍保持。

新增模式的 manifest/task/invocation 必须一致；资料模式的 task/invocation 也必须一致，未知协议及删除 flag 尝试降级均拒绝。普通股重建校验使用 manifest 声明生成期望 task/invocation，不能遗漏新字段后误报合法新包为配置漂移。原未标记入口仍待逐一完成当前执行/历史读取分离，未把它们包装成已退休历史分支；Task 3.1 保持未完成。

实际验证（零 LLM/网络）：

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_common_stock_semantic_handoff tests.test_material_semantic_handoff tests.test_research_materials_stage tests.test_common_stock_research_contracts
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_common_stock_semantic_handoff tests.test_material_semantic_handoff
openspec validate simplify-research-handoffs-and-acceptance --strict
```

- 前一条：**142 tests / OK，34.242s**，包含现有 100 项普通股及资料准备接缝。
- 后一条：随后补充删除 flag 的实际 Stop 拒绝断言，**20 tests / OK，5.928s**；产品源码未再改变，复用前一条未受影响检查，不重复跑产品级 Gate。
- 新正例从真实 stdio query/calculate 取得事实和计算结果，经模拟但真实执行的 Hook 交付/Stop 生成正式 JSON/中文报告，再执行当前 Finalizer；逐字段比较原研究文本、假设、信心及条件不变。新负例涵盖技术字段误填、外来/正确身份回填、未知 Evidence、未执行计算、损坏 MCP 事件与缺字段并存、协议 flag 降级。它们不证明真实模型推理、研究质量或晋升。
- 首次普通股试跑暴露重建器遗漏新协议字段及测试仍提交旧格式，修正当前重建器并显式迁移测试草稿，100 项通过；新增测试曾误读 query 返回键，按实际 `evidence` 对象核对后 6 项通过。未放宽业务验证以配合测试。
- OpenSpec strict valid；相关共享源码/测试 `git diff --check` exit 0。没有模型、真实 Smoke/Replay/Eval/Regression/Gate、归档、提交或推送。

本节完整文件字节快照（不是产品锁，包含其它授权修改）：

| 文件 | SHA-256 |
|---|---|
| `product/runtime/common_stock_stage.py` | `b572f12b69e8323cee2e7edba7f21c1211aa09e1bc25d6230f2b52111a9b6f62` |
| `product/runtime/codex_hook_recorder.py` | `310593856c1ee511d242009e6617127b2e902ce7cf359baf49c5c7d66df5f17c` |
| `product/runtime/research_materials_stage.py` | `a958cd4dfcad16b8fd89c452d19c9b4086ef9842fe202a4dbd62d09165fe1e48` |
| `product/runtime/multidimensional_stage.py` | `f5cc6363c48e703aa789a90f983a861dae3966bfb79bec5fe600cc2fc7bea232` |
| `tests/test_common_stock_semantic_handoff.py` | `65db7a7944b70e562cac9a9b2caffe22c4db0650e1a4e1611be482e0f79d979d` |
| `tests/test_common_stock_research_contracts.py` | `be7ff10b0f36940686eb5f1dd1d3a6a4b9076a2156de5caf40d7118275375422` |
| `tests/test_material_semantic_handoff.py` | `80d0b58fa5a8592494b4f30bb4a3c0e8aa5a51c8f274e2557cd06b26ce7962f1` |
| `tests/test_research_materials_stage.py` | `89909f74bda774c555a9fb23a838399c9e3d1db70b37d0db58841e8193c734a7` |

整体 **11/30**。Task 3.4 已关闭；其它角色的语义/短引用迁移、旧执行分支准入、局部修订及消费者仍按原未完成任务推进。真实 LLM 证明保持 **NOT_RUN**，在 Task 6.4 合并预算后才执行，原八维继续暂停。

## 2026-09-30：原稿结构前置及无默认目录的计算参数接缝（Tasks 3.1、3.3 部分推进）

### 首差异与修复映射

- **结构前置缺口**：上一轮新选择格式仅检查 `calculation_selections`，整稿缺研究字段时仍可能先读取收据。现在 `calculation_handoff.semantic_selection_draft_schema` 从冻结 `output_schema` 派生新选择草稿，同时处理 v4/v5 的 `core_statement/research_relation_clauses`。同一函数供普通/首次定点交付、提交前检查及可信 Hook 使用；选择协议不再另维护一份关系字段格式。模型不填的身份、计算结果、完整文档与路径仍由程序装配。
- **实际顺序**：工具提交先检查原授权/凭据，再检查新选择草稿完整结构；可信 Stop 先核原 Start/任务/模型身份，剥离已绑定身份后检查原稿，随后才选文档、读计算目录、解析引用和执行原正式报告/PIT/事件校验。`_assemble_draft` 对正式重读所需的原稿使用相同检查。未知 Evidence 的字符串可以通过结构检查，但必须在原精确映射/冻结允许集检查中失败；这不是放宽 Evidence Closure。
- **两个错误并存的真实反例**：测试先由实际 MCP 成功产出比值，再将临时 ledger 损坏，并提交缺 `question` 的原稿。实际 Hook 返回 `SCHEMA_REQUIRED_MISSING:$.claims[0]:question`，没有误报计算未执行，没有保存正式报告或更改原句。合法结构但未知 `e.*` 仍返回 `REFERENCE_UNKNOWN`；损坏事件及结果篡改继续由上一轮负例检验。
- **工具参数首差异**：无 `default_run_dir` 的 stateless 工具目录原来仍要求 LLM 填 `calculation_id`，尽管当前实际执行器能服务端编号。现在目录支持当前可选 ID 参数，真正授权仍按每次调用的实际 run、Invocation、协议及工具权限检查。实际无默认目录 stdio 正例生成成功收据，OPTIONS 越权仍拒绝；旧协议省略 ID 返回 `CALCULATION_ID_REQUIRED_FOR_LEGACY_PROTOCOL`，随后原显式 ID 调用仍可成功。旧绑定 Gate 参数契约未改，不扩大任何任务数学权限。
- **交付一致性**：当前选择协议的实际格式说明直接用同一规范派生结构；其研报说明不再同时指导填写旧四字段 upstream selections 或完整文档后再靠另一段覆盖。未启用新选择协议的已存在迁移分支保留原格式并明确仍待处理，不能将这些当前新写入分支冒称历史只读。

### 实际确定性验证

统一前缀为 `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest`。均在临时目录运行实际确定性组件，模拟生命周期，不执行模型、真实 Subagent、产品研究或真实 Eval。

| 实际测试模块 | 结果 | 适用范围 |
|---|---|---|
| `tests.test_calculation_handoff`（第一次） | 16 tests，1 error | 新 v5 关系格式测试误使用测试 helper 默认 v3；修正测试显式请求 SHORT_RECEIPT_VERSION，未放宽产品关系规则 |
| `tests.test_calculation_handoff tests.test_research_submission tests.test_multidimensional_stage` | 135 tests / OK，32.983s | 结构前置、现有提交及两条实际上下文交付 |
| `tests.test_calculation_handoff tests.test_server_calculation_ids tests.test_native_evidence_gate` | 45 tests / OK，5.510s | 当前无默认目录参数与任务权限；此时尚未新增旧协议恢复测试 |
| `tests.test_server_calculation_ids tests.test_calculation_handoff tests.test_research_submission tests.test_multidimensional_stage` | 142 tests / OK，34.812s | 最终聚焦集，包含旧协议省略 ID 拒绝后原调用恢复及规范交付结构 |

最终受影响下游接缝的实际完整命令：

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_calculation_handoff tests.test_scoped_research_claims tests.test_server_calculation_ids tests.test_multidimensional_references tests.test_research_submission tests.test_multidimensional_stage tests.test_multidimensional_research_contracts tests.test_independent_skeptic_stage tests.test_predecision_cio_stage tests.test_native_evidence_gate tests.test_component_versions tests.test_market_breadth_calculation
```

结果：**337 tests / OK，66.765s**。本轮新增六项测试，覆盖嵌套类型/必填字段、结构先于损坏收据、v5 关系字段、提交未写入前拒绝、实际格式与校验结构一致、未知 Evidence 不因结构通过获准、无默认目录 stdio 成功及越权拒绝、旧参数协议恢复。既有计算有序输入/成功事件/篡改/并发、文档/依赖版本及 Skeptic/CIO 消费测试继续通过。不是全仓测试、真实研究质量验收或 Release Gate。

- `openspec validate simplify-research-handoffs-and-acceptance --strict`：valid，exit 0。
- `git diff --check -- product/runtime/fixture_mcp.py product/runtime/multidimensional_stage.py product/runtime/codex_hook_recorder.py`：exit 0。
- 没有模型、网络探针、Smoke、真实 Replay/Eval/Regression/Gate、归档、提交或推送；没有重写任何历史包/版本锁。

### 未完成项保持真实

整体仍为 **10/30**，不提前勾选 Tasks 3.1–3.3。此次关闭的是已接入新选择格式的整稿结构前置与 stateless 参数接缝，不代表资料、普通股、Skeptic 等全部新写入角色已经迁移。完整当前新写入/旧读取分离、所有消费者、审计装配及一次局部修订仍按原任务推进。已授权无效草稿的尝试计数和局部补丁协议仍属未完成 Task 5.1，不能因本轮提交前拒绝而宣称已有限重试。真实新选择格式与交付证明仍为 **NOT_RUN**，在 Task 6.4 合并预算后才运行；原八维继续暂停。

### 当前文件字节快照（非产品锁）

下列共享文件还包含此前及其它授权修改；SHA-256 只标识本轮检查时的完整文件字节，不是全部 hunk 已复核或可提交的声明。上一节旧快照仅适用于当时结果，不包装为本轮最新模型证明。

| 路径 | SHA-256 |
|---|---|
| `product/runtime/calculation_handoff.py` | `3d3bcd81364c9ec66e90901c79a8ca3e3e7a75e030c936fb0e33d0b3ef158cd8` |
| `product/runtime/codex_hook_recorder.py` | `425c385bcf19260b7f3ba7ba2ecc28bfaf71e08f0fc8ed64945b9fa909f2de03` |
| `product/runtime/fixture_mcp.py` | `97a9b437cb5461d69cdce7ba2795517d2706b3b6276203e172fb8c7793d26c9e` |
| `product/runtime/multidimensional_stage.py` | `3b81ff2adf97010d621cf2e945b5b3458b5e36dfe501cfcf4d24257ec60a85ab` |
| `product/runtime/research_submission.py` | `d5940c624c521e2d3c5d4ea7647c1d5d1095a73ade499157ba85ec9809040c5b` |
| `tests/test_calculation_handoff.py` | `99fded9b60bacae57e775763054f3bbc464f38b79f6cde91d2cab434b4c56a63` |
| `tests/test_server_calculation_ids.py` | `f1200e95071c9e54fc9ce8653e4ffc9e02ebbb60432190e970a98babbc92a54b` |

## 2026-09-30：计算选择到正式报告的实际装配（Tasks 3.2、3.3 部分推进）

### 修改映射与验证范围

- `calculation_handoff.py` 是既有收据/附件的机械适配，不是计算编排器、Agent 或存储平台。当前绑定 run 的多维 MCP 成功计算返回 `k.*`；引用由原任务短表作用域及完整成功收据版本派生，新增另一结果不重编号。失败/未执行/错任务/错类型/未知选择不通过，完整收据、事件及有序输入仍须实际闭合。
- 模型提交 `calculation_selections=[{calculation_ref, claim_ids}]`，在关联主张原句中解释用途和局限。程序装配计算 ID、method/value/unit/input_evidence_refs/artifact_ref 和主张计算关联；不补写解释、不选择主张、不改写正文。混合完整计算记录与短选择、重复结果、未知主张、选择中私填 value 均拒绝。
- 当前普通/首次定点上下文从原业务 Schema 派生选择格式；文档选择同样使用允许的 `d.*`，Hook 使用原文档目录装配全部元数据。模型视图不要求填写运行身份、完整计算结构、产物路径及 claim.calculation_refs；预计算目录不再重复交付全部日线 ID。正式业务 Schema 文件及历史报告没有改写。
- 工具成功收据与事件由共享读取器精确校验。当前计算协议的标量报告另外核对 method/value/unit，原来仅核 ID/输入/事件而未核报告结果的缺口已补齐。历史无新协议标记的读取保留原 unit=null 等契约，不重写旧收据；旧稿仍先按原完整计算结构检查，不能把错误字段自动改名。
- 技术/市场预计算目录只提供 COMPLETE 窗口的非空指标及真实广度合计；保留窗口、as_of、price_basis、单位与完整附件血缘。冻结任务分别绑定 `allowed_calculation_evidence_ids` 与原 `allowed_evidence_ids`：前者仅为附件计算输入闭合，不授权查询或直接事实引用。测试明确证明技术任务的直接允许集仍为空，把附件 ID 写入 claim.evidence_refs 仍失败。
- 研报可从当前声明依赖的已核验报告/收据选取计算。原报告版本、源主张和收据再次精确检查；短选择必须同时关联模型明确选择的上游主张，不能由程序猜引用。复用沿原 upstream selection/accepted record/中文渲染读取链，研报没有新增 calculate 权限。
- 金额换算保留所有原转换记录（原数量级、转换量级、货币、税基等），不擅自选取其中一个金额；机构期间的复合投影保留早/晚期间、各原字段及原有有序输入，不把计数和比例当作同一单位。

### 实际执行

以下是确定性测试：调用实际准备器、MCP stdio、Hook 和正式报告/读取代码；Agent 生命周期由测试事件模拟，没有真实模型、Subagent 或产品研究运行。临时目录由 unittest 清理，不把临时报告当作可发布的真实研究包。

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_calculation_handoff tests.test_scoped_research_claims tests.test_server_calculation_ids tests.test_multidimensional_references tests.test_research_submission tests.test_multidimensional_stage tests.test_multidimensional_research_contracts tests.test_independent_skeptic_stage tests.test_predecision_cio_stage tests.test_native_evidence_gate tests.test_component_versions tests.test_market_breadth_calculation
```

- 最终当前实现：**331 tests / OK，64.961s**。包括实际 stdio→Hook 保存→中文报告、两个有序比值、追加结果后引用稳定、无成功收据/无事件、混合/重复/错任务/错类型/不存在 ID、重算摘要仍无法冒充原事件、错误结果/单位/方法、有序输入被改、预计算窗口/附件漂移、计算血缘不能变成直接引用、符号链接越界、基本面实际保存→研报短选择→accepted record 重读、依赖漂移、研报计算权限拒绝，以及历史 null 单位只读兼容。
- 最终聚焦集 `tests.test_calculation_handoff tests.test_server_calculation_ids tests.test_market_breadth_calculation`：**28 tests / OK，5.580s**；其中 12 个本轮 handoff 测试，不是 12 个真实 LLM 案例。
- `openspec validate simplify-research-handoffs-and-acceptance --strict`：valid；本轮已跟踪修改的 `git diff --check`：exit 0。没有完整 Release Gate、真实 Eval/Replay/Regression、归档、提交或推送。
- 开发失败记录不改成 PASS：初次 18 项出现 3 failures/2 errors（上下文序列化丢失规范短表，导致 Start 无法交付；预计算未区分计算输入允许集）。使用规范 packet 生成选择指导及单独冻结计算血缘后关闭，没有放宽身份隔离。随后 71 项出现 1 failure/1 error（旧合成结果 unit=null，以及原路径未使用计算却被要求额外事件）；更新当前合成结果为真实 ratio 单位，旧路径仅核实际选用结果，选择候选仍须真实成功事件，随后 71 项 OK。新增依赖测试漏建测试 invocation 目录、金额测试错误期待转换器补小数位及相邻税基文本互相进入原工具窗口，也保留为测试/既有工具语境问题；未修改金融计算逻辑，测试用明确分开的来源语境证明原结果保真。旧格式说明断言改为实际派生字段集合；目录、来源限制及内容原值断言保留。

### 尚未关闭的范围

整体仍为 **10/30**。Tasks 3.1–3.3 不提前勾选：这里只接通当前 run-bound 多维的计算/文档选择及其下游读取，所有角色的统一新写入模式、整个原稿结构先于全部血缘的迁移、动态无默认 run 的工具目录、一次局部修订和其它消费者还需按各自任务补齐。旧完整草稿的迁移分支仍存在，不能将其改称历史只读便宣称当前入口全部完成。Skeptic/CIO/Eval、Memory/网页等此前证据只按原适用范围复用。

既有 monetary_scale 的短文本窗口可能同时看见相邻金额的不同税基；本轮只保证不篡改其返回记录，不声称税基抽取算法已优化。该金融抽取问题记录为范围外已知限制，不增加本 Change 的运行或金融算法修改任务。

**真实运行状态：NOT_RUN。** 新选择格式/工具返回/Hook 交付改变，所缺真实定点证明仍归 Task 6.4 一次说明预算，未获批准前不启动。计算选择装配通过不代表研究关系成立、八维内容验收完成或候选晋升。

### 当前文件字节快照（不是产品锁）

共享文件还包含此前及用户已有修改；下列 SHA-256 仅定位本轮验证的源码，不代表整工作区可提交或已独立复核。

| 路径 | SHA-256 |
|---|---|
| `product/runtime/calculation_handoff.py` | `d8a9ca42fbdcb0d6ecba9d5058c0aca2cea6c67cc73fce0ce5c5f029b4c8532c` |
| `product/runtime/codex_hook_recorder.py` | `dcac2f42e3baa557e5a94ecc54437814a24cd6b2e2ec728c8049f68c18010604` |
| `product/runtime/fixture_mcp.py` | `6c4e4083853a71cec3a5e5055f5bf13c1a7491fafc5a71f331d56059b0cb018d` |
| `product/runtime/multidimensional_stage.py` | `da7de5966e31d3514f50d26af689518ce9c04b224f10f0fea35114e20d063bb5` |
| `product/runtime/research_submission.py` | `2cb3f7dd12f85c9ae26a4ddcefc6c6ffb874d6ae6a72fd18f54bf2de97757279` |
| `product/council/multidimensional_research.py` | `2d600e22c50bc254550a2a33d87a2b352139119d5b84556dde3cfdba114985ee` |
| `tests/test_calculation_handoff.py` | `f774604cf00967ac03db0c82f17a9d51e971af3f1985abe3de49676acf2b8646` |
| `tests/test_research_submission.py` | `622fbd5848657f74cca3e123dcf00759ed5ab18979385d6aade6329b02ebfbec` |
| `tests/test_multidimensional_stage.py` | `3903764933e9edbd96f33782c79d10dc0e0e00771d17abefbcf709f6642a5c03` |

## H03 / H04 / H05：限定版本主张、文档短引用及服务端计算编号（Tasks 3.2、3.3 继续实施）

### 实际修复及边界

- 根因不是随机输出：原 `multidimensional_references` 在短表里保留 report_id，却在还原时只保留裸 claim_id；两份合法依赖报告同名主张直接报歧义。当前新包改为 `multidimensional-references/2.0.0`，运行时把 `c.*` 精确装配成版本化 `rc1.<report_id UTF-8 hex>.<report_hash>.<claim_id UTF-8 hex>`。该字符串可逆解码，报告版本不丢失；继续符合原正式报告的 canonical-ID 字符串结构，不改历史 Schema 文件或旧报告 hash。只解码不代表授权，正式消费者仍用实际上游报告重新构造允许集。
- 模型目录只交付短引用及可读的报告/主张定位，不新增长 canonical_ref 或让模型复制报告版本 hash。同名本地主张可以保留；本地主张不能冒占 e./c./d./k./rc1. 运输命名空间。正文、原值与研究关系句不替换。
- Hook、普通/定点 finalizer、研究包消费者与 bundle 的跨报告允许集改用同一限定版本解析；已保存关系的精确语句验证和复制包的上游计算读取保持报告归属。旧 v1 映射按原版本读取，不补写 canonical_ref；旧裸引用只在实际报告集合中无歧义时可读。当前 v2 写入不得用裸名称猜上游。
- 文档提供任务局部 `d.*`，绑定 document_id 和原始完整对象 hash；草稿及实际提交工具接受精确文档选择，由程序装配原元数据。混合长/短同一文档的重复选择、错类型、旧映射、换版本或元数据漂移均拒绝。两条实际上下文序列化路径的选择 enum 均来自允许短表；正式 JSON 保留原 source_id/as_of/retrieved_at 和其余资料。中文展示解码限定版本主张为报告/主张名称与完整版本，不要求读者识别十六进制编码。
- 当前 v2 多维任务的 MCP calculate 可省略 calculation_id，由服务端授权后分配唯一 ID，原有序输入及真实结果进入原计算 ledger；旧显式 ID 调用及旧 fixture 参数契约保留，不开放未授权任务的 calculate。新增随机 ID 不是随机投资判断，数值计算和权限不变。
- **仍未完成**：各角色统一短引用与草稿写入、计算结果短选择/预计算装配、完整 Memory/网页消费及历史模式分离还在 Tasks 3.1–3.5。服务端分配 ID 不等于模型已无需重写整个计算记录。Tasks 3.2、3.3 不勾选；整体仍为 **10/30**，不把上述部分成果冒称全部 H02–H05 关闭。

### 执行与负例

所有以下测试均在当前开发环境使用临时目录运行确定性组件，没有产品模型、真实 Runtime Eval/Replay/Regression/Ablation 或 Gate。实际统一命令前缀为 `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest`。

- 第一组 `tests.test_multidimensional_references tests.test_research_submission` → 52 tests / 3 failures：旧断言仍要求裸主张 ID，及合成上游计算选择仍用裸引用。改为实际目录短引用/正式限定版本引用，保留原计算值和语句断言；随后 scoped + submission → 45 tests / OK。
- 初次新 scoped 模块误直接导入 fixture TestCase，导致额外收集整组测试；140 tests / 2 failures 分别为旧目录断言、测试另起父会话不符合既有真实 Start 绑定。改用模块别名，不重复收集；测试使用原可信父会话，未放宽产品身份隔离。
- `tests.test_scoped_research_claims tests.test_multidimensional_references tests.test_research_submission tests.test_multidimensional_research_contracts tests.test_multidimensional_stage.MultidimensionalStageTests.test_dependency_report_is_delivered_as_structured_agent_input` → 84 tests / OK（文档短引用加入前）。
- 文档短引用接入后 scoped/reference/submission → 61 tests / 1 failure，旧文档 enum 断言还要求完整 document_id；改为从实际短表取允许选择，并仍要求正式产物完整文档等于冻结原对象。后续 scoped/reference/submission/contracts/skeptic/predecision → 190 tests / OK。
- 服务端计算测试初次调用了不存在的测试注入参数：37 tests / 1 error（测试 API 用法错误）；改为与既有测试相同的真实 stdin/stdout stdio 入口 → 37 tests / OK。不修改产品接口来迎合测试。
- 最终初始上下文/纠错定位去除长机械引用后，`tests.test_scoped_research_claims tests.test_server_calculation_ids tests.test_multidimensional_references tests.test_research_submission` → **67 tests / OK**。正负例包含两份实际正式生产者同名主张→消费者、真实 Hook 保存、报告 hash 漂移、非法同名裸引用、局部同名、UTF-8 可逆 ID、15 主张 JSON 键序、跨任务/run/Gate/目录、文档漂移/错类型、服务端有序比值、12 并发计算 ID、实际 MCP 参数错误在写入前拒绝和无数学权限任务拒绝。
- 在上述最终源码上执行全部本次受影响接缝：`tests.test_scoped_research_claims tests.test_server_calculation_ids tests.test_multidimensional_references tests.test_research_submission tests.test_multidimensional_stage tests.test_multidimensional_research_contracts tests.test_independent_skeptic_stage tests.test_predecision_cio_stage tests.test_native_evidence_gate tests.test_component_versions` → **308 tests / OK，61.326s**。它覆盖研究包、现有下游与旧版 Schema/工具参数，但不是全仓测试、真实模型调用或 Release Gate；未作新的内容质量/Promotion 声明。
- `openspec validate simplify-research-handoffs-and-acceptance --strict` → valid；上述本轮已跟踪改动的 scoped `git diff --check` → exit 0。人工完成批准、归档、提交与推送均未执行。

### 当前源码记录（文件字节 hash，非产品版本锁）

以下为本轮接缝的共享工作区文件完整 SHA-256；它们包含此前相关及已有修改，不代表整工作区已审核或允许提交。不得把测试本地合成执行当真实 Agent 研究。原历史包没有改写。

| 路径 | SHA-256 |
|---|---|
| `product/runtime/multidimensional_references.py` | `5ed89e3080775bbdc088097193fb717c6b50b52139a7159ddb722a9975d686a4` |
| `product/runtime/research_submission.py` | `7eebf57f8f39e98980ed3b00c72b4bdbe8240f58b954b3419084527fd331c612` |
| `product/runtime/multidimensional_stage.py` | `20e4ace806b9873131b27c65eefd2f0a3ddd6275718a3ebcc2711c8af2d731ed` |
| `product/runtime/codex_hook_recorder.py` | `b75daaf3dc7a1fa5e853e7474d1296814827955687ee3f74ea40ee6cfc46dcdc` |
| `product/runtime/fixture_mcp.py` | `64170cd126c1210f6819266719c11fe772536124535cc73d4bde49957e5af868` |
| `product/council/multidimensional_research.py` | `cca84ba67366d71294638f6a3788dfcf618e1f76f14b6b0c1d3fb873b487bf9c` |
| `product/council/multidimensional_output.py` | `b5a17b98a7a9fc0239e663676987953c29213c40f470d6c02404b51fafdd15d0` |
| `tests/test_scoped_research_claims.py` | `8703b8b56a365698784db75feb53f4852b5de497638023d2ad1abd15754a4455` |
| `tests/test_server_calculation_ids.py` | `7b0472afb5fd2a26c4bb33b9c6db3e51c84fffb6c4b10172ab93cf7e502d0fa1` |
| `tests/test_multidimensional_references.py` | `ca4c27d1cdcfee865c16e6643e5547c7cb77e7a61d11ca0bcfc1bf99b96bab7b` |
| `tests/test_research_submission.py` | `17346a02f2779a5a390d70a172bd2569e104c6fac8202b522fdf3e11f5438467` |
| `tests/test_multidimensional_stage.py` | `5df21942fc491b61bf8c30249f58f947154740048ad14636cd0b0830ba930f34` |

## H13 两类 Eval / Invocation 的摘要接缝（Task 4.1 继续实施）

- 普通股 Eval input/result/launcher invocation、Runtime Eval semantic output、原不适用终态、grader execution proof 及 Council Invocation 的生产/读取改为同一 `legacy_envelope_hash`；普通股阶段 `_claimed_hash` 也委托同一 helper。仅顶层排除各自自字段，原 `canonical-json/1.0.0` 摘要保持不变。文件 hash、报告对象 hash、事实投影/交付 View 不被替换或互相比对。
- 新 `verify_legacy_envelope_hash` 的错误说明对象类型、算法版本、产物位置、自字段和期望/实际摘要；相应专用错误码仍保留。不会要求模型重算，不对损坏对象自动改 hash。历史生成/校验兼容向量与当前真实生产→消费正反接缝同时检查；未把 v2 类型化算法套到现有正式对象。
- 实际执行 `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_hashing_contracts tests.test_eval_handoffs tests.test_common_stock_research_contracts.CommonStockFocusedEvalTests` → **24 tests，OK**；扩展 `tests.test_hashing_contracts tests.test_eval_handoffs tests.test_eval_execution_proof tests.test_runtime_eval_job tests.test_native_invocation_validation tests.test_native_run_package tests.test_common_stock_research_contracts.CommonStockFocusedEvalTests` → **57 tests，OK**。日志中的两个 run-error JSON 是测试明确构造的模型证明缺失/依赖缺失负例，suite 结果为 OK，不是额外真实运行。
- **未关闭范围**：完整 H13 对象类型/算法/位置清单及其它资料、CIO、bundle/展示读取接缝尚须核对，Task 4.1 保持未完成。没有运行产品模型或写回历史产物。
- 随后新增真实普通股 Eval 装配输出的篡改诊断断言，单独执行 `tests.test_eval_handoffs.EvalHandoffTests.test_common_hash_diagnostic_names_contract_and_path_without_repair` → **1 test，OK**：保留原 result hash、报告 `self-excluding-envelope/canonical-json/1.0.0/eval/result.json` 的准确口径，没有静默修复。

## H12 版本权威与退役边界（Task 2.5 确定性实现完成）

- `versioning.py` 复用当前 `product/version-manifest.json` 的批准值，实际读取 Skill frontmatter、当前报告 Schema 和工具实现声明；拒绝未知组件、错版本、错 Schema ID、未知 Adapter 作用域。通用查询/多维/资料/CIO、普通股字段查询、独立 Skeptic 分别绑定 `2.5.0/2.4.0/2.3.0`，不是选最大数字。仅补齐当前清单已实现 Schema 项和三个当前 Adapter 作用域，未修改历史清单或晋升指针。Risk 固定实现版本共用常量，并核验当前批准值；未变任何风险限制。
- fixture discovery、普通股/多维/资料准备、Runtime Eval 准备、普通股 Eval Schema 构造及 MCP 实际查询分别按相应作用域检查；Agent 绑定沿用批准清单，三处 Skill 版本读取复用同一 frontmatter 解析。原专用资源、角色、权限与实际执行证明检查保留。
- `--check` 只读；`--render` 只输出批准值派生的 profile，`--render --skill <name>` 只输出批准版本镜像、保留方法正文。正反接缝验证两次生成相同、未自动写文件、错版本即使 hash 重填仍失败、错误实际 MCP 版本在事件产生前拒绝。
- CIO 当前镜像的 `3.1.2` 批准依据沿用下文已记录的归档提交 `bad1504`，没有因数字较大而选它。`3.1.0` 位于已退役冻结 live profile：保留原字节/hash，当前真实 `prepare_live_run`、Invocation 和 launcher 明确拒绝该入口；只有显式 `authenticity_required=False` 的合成兼容构造使用批准身份的内存投影并标 `compatibility_fixture`，launcher 仍拒绝真实启动。它验证旧格式读取，不是历史实际执行包，也不冒称当前产品运行证明。原历史包未迁移、回写或补造。
- 初次扩展验证 `tests.test_product_config tests.test_runtime_foundation tests.test_native_invocation_validation tests.test_common_stock_research_contracts tests.test_cio_handoff tests.test_multidimensional_stage` → **224 tests，2 errors**：资源漂移诊断前读取了不属于小型测试包的 Skill；普通股绑定把所有产品组件误当自身依赖。按职责修复检查顺序及作用域，未将缺文件忽略。定点 `tests.test_component_versions tests.test_runtime_foundation tests.test_common_stock_research_contracts.CommonStockNativeStageTests.test_company_stage_restores_full_profile_and_fails_closed` → **15 tests，OK**。
- 退役接缝初次 `tests.test_live_profile tests.test_live_contracts_gate tests.test_live_eval_contract tests.test_live_cio_final_response` → **45 tests，2 errors**，两条旧测试还要求退役 launcher 启动。改为保留纯确定性最终响应→Risk 读取接缝，并验证退役启动在创建 invocation/进程/执行证明前拒绝；不是跳过测试。随后 `tests.test_component_versions tests.test_live_cio_final_response tests.test_live_profile tests.test_live_contracts_gate` → **47 tests，OK**。冻结 live profile hash 仍为 `d38d6124d4e2b14d2889e36af7ca700f9ac62ed96b21c5472adb5ac2bbd496bb`。
- 当前接缝扩展 `tests.test_component_versions tests.test_common_stock_research_contracts tests.test_research_materials_stage tests.test_product_config tests.test_native_invocation_validation tests.test_native_run_package tests.test_predecision_cio_stage` → **189 tests，1 failure**：CIO 的 `read_reports` 工具被不需要 CIO 的资料阶段目录看到。修正目录只在 fixture Council/predecision 阶段暴露，仍在每次调用核验实际授权，保留 prepare-cio 前可发现性以避免目录缓存。定点 `tests.test_component_versions tests.test_cio_handoff tests.test_research_materials_stage tests.test_eval_handoffs tests.test_runtime_eval_job tests.test_common_stock_research_contracts.CommonStockFocusedEvalTests` → **61 tests，OK**。
- 最后受影响消费者 `tests.test_multidimensional_stage tests.test_independent_skeptic_stage tests.test_hashing_contracts tests.test_live_eval_contract tests.test_runtime_eval_job tests.test_eval_execution_proof tests.test_native_replay tests.test_native_eval tests.test_runtime_ablation` → **209 tests，OK**。这里的 Replay/Eval/Ablation 模块均为确定性合成单元测试，未启动对应真实作业。以上测试实际环境均为 `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest <所列模块>`；版本检查命令为同一 Python 执行 `scripts/check-product-version-mirrors.py --repo . --check` → `PROFILE_VERSION_MIRRORS_OK`。
- **验证层级**：静态资源与配置一致、确定性生产→消费接缝通过，不宣称模型已经加载。当前清单/启动准入变化对应的最小宿主补验证在 Task 6.4 一次提出；没有继承旧预算或运行模型。下文旧“未关闭”条目保留为过程历史，由本节覆盖当前 H12 状态。

## H15 实际 Schema 与不适用终态（Task 2.6 确定性实现完成）

- 复用下文已实现的离线 Draft 2020-12 标准适配器与准备期定义检查；CIO 原正式规则和 native 草稿均实际检查，Schema 条件/组合/引用及兄弟约束、未知关键词/注解、非有限数与 bool/number、NO_TRADE 的 null/0 正负例均有接缝。非法工具实参在函数副作用前拒绝，未删除 Evidence/PIT/Risk 专用检查。
- `NOT_APPLICABLE` 是既有程序终态产物，不是 dev_eval 的模型评分。新增从原正式 Schema 派生的独立校验投影，严格要求 `deterministic-not-applicable/model=none`、全部不适用、grade=null、空引用；producer 保存前和只读 verifier 均执行结构、真实输入血缘与 hash 验证。模型提交仍只接受 dev_eval 契约，不适用结果冒充模型评分、模型/输入漂移、伪 PASS、grade=0 或伪 Evidence 均拒绝。原 Schema 文件字节/hash、已存在正式版本和原 rubric 未改，不给历史结果补造模型证明。
- 执行 `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_runtime_eval_job tests.test_strict_schema_validation tests.test_eval_handoffs` → **20 tests，OK**；扩展 `tests.test_strict_schema_validation tests.test_cio_handoff tests.test_eval_handoffs tests.test_runtime_eval_job tests.test_native_evidence_gate tests.test_native_decision_contract tests.test_native_output_handoff tests.test_native_invocation_validation tests.test_predecision_cio_stage tests.test_component_versions` → **108 tests，OK**。相邻研究/反证/两类 Eval 消费者见上节 61/209 项结果。
- `openspec validate simplify-research-handoffs-and-acceptance --strict` 通过；受影响文件 `git diff --check` 通过。未运行产品 LLM、真实 Runtime Eval 或完整 Gate；下文保留的旧 NOT_APPLICABLE 缺口由本节实现关闭，不将当时失败改写成通过。

## H10 两类 Eval 的语义草稿装配（Task 2.4 确定性实现完成）

- 普通股 Eval 当前准备器显式标记 `common-stock-research-eval-draft/1.0.0`，输出 Schema 从原九维业务契约派生，仅含 `schema_version/status/dimensions`。Hook 依据实际 Stop 模型及对应 Start 的完整 packet/input 绑定，调用确定性 finalizer 装配技术身份和 `result_hash`，评分/理由/引用保持原样。输入自 hash、已存在 launcher invocation 的身份/模型/输入 hash、真实 Start 事件及原评分阈值继续验证。
- Runtime Eval 的所有当前新 Job，包括 fixture，复用既有 `native-draft/1.0.0`；真实 transcript collector 装配 grader/input/prompt/rubric/output hash。任务绑定使用子线程完整读取冻结 manifest 的真实工具响应，结合既有角色、独立调度、模型与原始输出校验，不再以模型复制 lineage hash 作为任务绑定。原始草稿与正式评分分别保存。
- 当前旧完整结果不再用于新模型提交；普通股旧正式结果仍由 `validate_common_stock_eval_result` 读取，Runtime Eval 旧正式结果仍由既有只读验证器读取。旧普通股作业拒绝启动/新写入；旧 Runtime Eval 作业拒绝生成可执行评分 Prompt 或再次 finalize，不把活跃旧写入分支伪称历史兼容。显式合成测试仍可构造 formal candidate，以验证读者；这不证明模型实际评分。
- `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_eval_handoffs tests.test_common_stock_research_contracts tests.test_runtime_eval_job tests.test_eval_execution_proof tests.test_native_output_handoff tests.test_native_invocation_validation` → **138 tests，OK**。随后拒绝旧作业新写入的改动使用 `tests.test_eval_handoffs tests.test_eval_calibration tests.test_runtime_eval_job tests.test_eval_execution_proof` → **20 tests，OK**。一次误写不存在的 `tests.test_runtime_calibration` 导致 loader ImportError；实际模块为 `tests.test_eval_calibration`，已更正命令，未把该失败记为产品通过。
- 测试正例使用实际准备器、Hook 状态流和 transcript collector 的确定性模拟事件；负例覆盖错误模型、Start 之后修改输入且重算摘要、缺模型证明、错输入绑定、旧完整结果冒充草稿、非法评分/引用和九维 FAIL 不被平均值覆盖。当前包经只读历史 validator 验证，原稿文件未回写。
- **验证层级**：未启动真实 Eval、Calibration 或产品模型。新 Job 交付/Schema/Hook 改变，Task 6.4 仍须列出两类 Eval 最小真实补验缺口及预算；这里不冒称真实评分效果或全量发布门禁通过。

## H09 CIO 语义草稿与真实报告读取（Task 2.3 确定性实现完成）

- 当前 fixture Council 和 predecision CIO 新写入使用 `native-cio-draft/1.0.0`，从各自既有正式业务 Schema 派生草稿；模型保留决策/研究字段和 `report_selections`，运行层装配身份、Skill、来源绑定及 `consumed_reports`。正式产物继续采用原业务契约，未修改动作/Risk/PIT 语义。
- 在现有 run-bound fixture MCP 增加受限 `read_reports`，只允许已准备且获 `research_reports.read` 授权的 CIO 读取目录内完整报告；路径、文件字节、调用身份和目录绑定均检查。工具目录在 prepare-cio 前可发现，以免客户端缓存导致后续工具不可见；其它角色和未准备 CIO 实际调用均拒绝。
- `cio_handoff.py` 根据真实工具交付事件重验报告内容与目录，区分获准、工具读取/交付和模型选择。不把工具读取等同于模型内在理解；研究综合质量仍须后续内容复核。缺必需报告、未读却选择、篡改事件/报告、越权角色及 Schema 中的技术字段均拒绝。当前 predecision finalizer 拒绝旧完整模型输出的新发布，历史正式输出仍由原对应读取器读取。
- fixture finalizer 在草稿/消费证明/原正式 Schema/动作与 Evidence 专用验证均通过后保存原稿与装配产物，再进入原 Risk Engine；`REVISE_REQUIRED` 仍保留原硬限制。predecision finalizer 与 Trace checker 重建同一正式产物和消费证明，保持 `RESEARCH_SYNTHESIS`、`risk_status=NOT_RUN` 的原范围。
- `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_cio_handoff tests.test_predecision_cio_stage tests.test_native_run_package tests.test_native_invocation_validation tests.test_native_decision_contract tests.test_native_evidence_gate` → **82 tests，OK**。另运行 `tests.test_native_replay tests.test_native_eval tests.test_runtime_ablation` → **20 tests，OK**；后者只运行确定性单元接缝，无模型/真实 Replay/Ablation 作业。测试中的旧 formal fixture 构造继续属于显式 `authenticity_required=False` 合成场景，不证明真实模型消费。
- 原 `runtime_cio.toml` 受当前资源锁约束，本轮曾加入通用说明后触发 `product resource hash mismatch: cio_agent`；已仅撤销该新增行，保留真实失败而未重写任何历史锁。当前 Schema 与动态 Prompt 承担草稿交付，稳定角色及权威镜像将在 Tasks 2.5/6.1 按整体范围处理。
- **验证层级**：上述只关闭 Task 2.3 的实现和确定性接缝。CIO 的 MCP 交付与 Schema 改变，fixture/predecision 各自缺最小宿主真实运行证明；按 Task 6.4 一次列明预算，未经授权不启动，不将旧运行当作新协议 Smoke。原八维 Change、Promotion 和全局安全验收均未据此关闭。

## P0：最新计算记录首差异

- 历史包：`eight-dimension-v4-acceptance.8iWZu9/run`（仓库外私人验收目录；未复制原始内容、未修改原包）。
- 原始草稿：`research/raw-drafts/e08e27fd5cb0940b49306228f00e1a3ea6384c5ce92cee2ad166283259e1fba0-attempt-1.json`；文件 SHA-256 `19cd87924256985256e10a9c0e600a881ad084b9540f977010a2658245f3445c`。
- 真实计算收据：`research/calculations/b3f4b3da1e39da42/tool-results.jsonl`；文件 SHA-256 `4c3d1c1eabc11c06a42a2d9695a06e2080b031a4348a479738e17aa0c53c7028`；计算 `mrvl_fy26_close_pe_20260925_01` 对应的事件存在，`tool_event_hash=ab6dedc5cb6d78fdf2d0626c83a381a24f156b92f68d9eae2aa828530f1805b2`。
- 历史 Hook 首次失败为 `MULTIDIMENSIONAL_CALCULATION_RECORD_MISSING`、`repair_state=NOT_ALLOWED`。脱敏结构反例为 `calculations[0]={calculation_id,method,result,unit,evidence_refs,artifact_ref}`，而冻结契约要求 `value,input_evidence_refs`。原始文件的计算项用冻结 Schema 检查，实际返回 `DIMENSION_REPORT_SCHEMA_INVALID:SCHEMA_REQUIRED_MISSING:$.calculations[0]:value,input_evidence_refs`。前后两次文件 hash 一致；这只证明首差异定位正确，不证明整稿在其它检查下可以通过。
- 新的聚焦测试 `test_calculation_shape_precedes_receipt_lineage_without_rewriting_draft` 通过：结构错误优先于血缘，原稿不被静默更名；更正后的合成草稿可通过结构和真实收据校验。既有收据测试同时验证未知计算、输入不符、收据篡改、事件缺失，全部按各自错误分类拒绝。
- 执行：`python3 -m unittest tests.test_multidimensional_stage.MultidimensionalStageTests.test_calculation_shape_precedes_receipt_lineage_without_rewriting_draft tests.test_multidimensional_stage.MultidimensionalStageTests.test_runtime_calculation_receipt_is_citable_and_tamper_rejected` → 2 tests, OK。

此记录不构成原八维内容验收，也不授权新的 LLM 调用。

## P0：短提交回执与可信绑定（Task 2.2）

新准备的结构化研报任务使用 `research-object-submission/5.0.0`：工具在原两份不可覆盖草稿槽位上签发 `r1.*`/`r2.*` 短引用，存稿仍保存完整内容 hash；模型最终只返回该引用。Stop 必须先有真实 Start/身份绑定，再由当前任务私有目录选中**确切槽位及引用**、重算完整 hash，不能据序号或“最新一稿”推测。旧 v3/v4 JSON hash 回执继续按冻结协议读取，未改历史运行包。

正反例验证：两份草稿选第二份后正式报告保留第二份研究措辞；冲突身份与错凭据在创建槽位前拒绝；不同 invocation 的引用、旧式完整 hash 回执与被改写的存稿拒绝；两条并发提交只占独立的 1/2 槽位，第三条拒绝；有效 bearer 与短回执在不匹配的 Stop child 上仍不能通过可信身份门禁。Bearer 只防误路由，不作为模型会话认证。新正式/首次定点上下文均交付 v5 短引用指令，v4 原读写行为保留。

执行 `python3 -m unittest tests.test_research_submission tests.test_multidimensional_stage tests.test_multidimensional_references tests.test_multidimensional_research_contracts` → 155 tests, OK。这里只验证确定性交接和兼容，没有启动产品 LLM。

## 共享工作现场与归属

核对时 HEAD 为 `eefc90ab2f827b469861bb5fb3af8c5192ac8211`，工作树已有大量已修改/未跟踪文件；不是本 Change 可清空的临时状态。`complete-eight-dimension-source-consumption` 的 Proposal/Tasks 及历史验收记录仍归原 Change；其中最低研究问题、来源补齐、真实同 Gate 八维 `8/8` 内容、调用账和最终人工批准不属于本次交接修复。原 Change 当前为暂停，`8.40`、`5.3`、`5.5`、`5.6`、`6.16` 等未完成项不由本 Change 勾选。

共享源码 `product/runtime/codex_hook_recorder.py`、`product/runtime/multidimensional_stage.py`、`product/runtime/research_submission.py`、`tests/test_multidimensional_stage.py`、`tests/test_research_submission.py` 中已经存在原 Change 的派发、收据、研报 v4、来源表达与内容保护实现。本次仅按 `handoff-inventory.md` 修改相应交接边界；本阶段实际新增的是 Hook 中计算结构优先诊断与错误分类、对应聚焦测试。其它脏文件（包括券商/历史回放的活跃 Change）保持原状，不通过本次任务覆盖、提交或推送。后续每一共享文件 hunk 均须在关闭矩阵标明归属；最终提交若无法可靠区分，须停下而非把整文件现有脏差异一并纳入。

执行 `git diff --check -- product/runtime/codex_hook_recorder.py tests/test_multidimensional_stage.py` 无空白错误；它仅检查本次受影响源码文件的差异格式，不证明全部工作树通过验收。

## 未关闭：CIO 版本来源

只读检查确认 `product/version-manifest.json` 的 `agents.runtime-cio=3.1.2`，而原 `product/runtime-profile.json` 的 `agents.runtime_cio.version=3.1.0`；既有八维验收记录也曾在 CIO Invocation 准备处观察到同一漂移。`runtime_cio.toml` 本身未声明独立批准号。`git log -p -S '"runtime-cio": "3.1.2"'` 追到已归档的 `bad1504`（simplify LLM runtime boundaries）将 manifest 从 3.1.1 提至 3.1.2，却未同步 profile 镜像。按这份已归档来源将**当前工作树**的镜像改为 3.1.2，当时的 profile 文件字节 hash 为 `d1320df6cc262955f5616b5c066f951348f417246e4dba5cf5bdea31051715b3`；后续市场 Agent 镜像修订后的当前 hash 见下节，不能再使用这个中间值。旧候选锁未回写。`product/runtime/invocation.py` 已有当前执行时 profile 与批准版本不一致即拒绝的逻辑。Task 2.5 仍未勾选。

配置测试原有三处静态期待与当前产品不符：新的普通股专用配置文件虽已跟踪，却未列在配置清单中；技能版本表滞后；CIO 版本写死 3.1.0。本次让受 manifest 管理的技能/Agent 测试读取批准版本，普通股专用文件按实际角色名及技能集合核对，不改变产品角色或配置。`python3 -m unittest tests.test_product_config tests.test_native_invocation_validation` → 24 tests, OK。另 `tests.test_multidimensional_stage` → 80 tests, OK；`tests.test_multidimensional_research_contracts tests.test_research_submission tests.test_multidimensional_references` → 70 tests, OK。以上均为确定性检查，不构成新的真实 CIO/八维产品运行证明。

## P0：H12 当前版本镜像继续核对（Task 2.5 未完成）

- 当前 `product/runtime-profile.json` 的市场 Agent 镜像原为 `1.0.1`，批准清单及多维实际绑定均为 `1.2.0`；现镜像改为 `1.2.0`，其当前文件字节 hash `2e8fa19227db5d72752c9cd9ccf328ccc3e4f96f618768a7fa622ff6e2a96a0c`，同步当前 manifest 的 `resource_hashes.runtime_profile`。`discover_product_resources` 在模型前比对 profile 与批准版本；即使手工重新填写文件 hash，错版本仍拒绝。多维 Agent 绑定改为读取批准清单，不再维护两处版本常量。
- `product/profiles/live-us-equity.json` 属于拓扑中 `RETIRED/COMPATIBILITY_ONLY` 的旧 profile，`holding-research-inputs.json` 仍锁定其原字节 hash。第一次把它当当前镜像更新，导致多维聚焦测试出现 `RESEARCH_TOPOLOGY_REFERENCE_HASH_MISMATCH:retired_live_profile`；已只撤销本次对应版本改动及当前镜像检查，不改历史引用，也不将退役版本强行升至新版本。随后同组 111 项测试通过。
- 当前 manifest 的 `assurance_hashes.runtime_eval_rubric` 曾误指向普通股 rubric 的 `a22d2c...`；实际 Runtime Eval rubric 的 canonical hash 为 `8c4e0b...`，既有独立评审记录与冻结运行引用相同。`runtime_eval_grader_agent` 当前文件字节 hash 为 `3b38cef...`，已有普通股 Eval 证据使用该版本。仅更正当前 manifest 的两项绑定，不回写历史包；其余六项 assurance hash 经逐项计算与当前资源一致。
- `scripts/check-product-version-mirrors.py --repo <repo> --check|--render` 只读：检查当前 fixture 镜像/文件 hash，或从批准清单渲染预期 profile 供人工审阅，不修改源码。纯派生函数连续执行两次结果相同；旧退役 profile 不进入此生成流程。`python3 scripts/check-product-version-mirrors.py --repo /Users/caihaoming/Documents/stock_agent --check` → `PROFILE_VERSION_MIRRORS_OK`。
- `python3 -m unittest tests.test_runtime_foundation tests.test_multidimensional_stage tests.test_product_config tests.test_live_profile tests.test_native_invocation_validation` → 119 tests, OK；此前只对 `ProductDiscoveryTests` 等的 35 项聚焦测试也通过。没有启动产品模型、Replay、Regression 或 Gate。
- **未完成范围**：当前 Skill/Schema/Adapter/Risk 镜像是否全部由权威版本派生或在使用前校验、以及旧锁隔离的完整负例尚未逐项收口。因此不勾选 Task 2.5，不把本次 fixture 检查冒称 H12 全部通过。

### H12 后续接缝补证（仍属 Task 2.5，未完成）

- 普通股 `current_research_bindings` 不再使用复制的 Company Agent 版本常量：从当前批准 manifest 取版本，并在准备时核对 Agent 文件字节 hash 与四项 Skill 的实际 frontmatter 版本；Prompt policy 复用这份已检查绑定。多维 `_agent_binding` 及 `_skill_binding` 也从批准 manifest 取版本并拒绝 Skill 版本漂移。两者都保留实际内容 hash，不让模型填版本或 hash。
- 正向用真实仓库 Agent/Skill 生成绑定；负向在临时目录只改变 Skill frontmatter 或 Agent 文件字节，普通股与多维分别拒绝。执行 `python3 -m unittest tests.test_common_stock_research_contracts tests.test_multidimensional_stage tests.test_runtime_foundation tests.test_product_config tests.test_live_profile tests.test_native_invocation_validation` → **219 tests, OK**。没有模型调用。
- 继续核对发现 `fixture-gate-scoped` 是同名家族而非单一协议：当前 Council manifest 为 `2.1.2`，Skeptic 验证读取 `2.3.0`，普通股字段查询返回 `2.4.0`，当前多维 MCP 默认 `2.5.0`；不能把一个阶段的版本直接覆盖另一个或回写冻结包。当前 `tests.test_independent_skeptic_stage` 89项通过，但它们未证明新 MCP 生产事件的 `2.5.0` 可通过仍要求 `2.3.0` 的消费检查。Adapter 作用域与真实 producer→consumer 接缝仍需明确，因此 H12 不得关闭。

### H12 Skeptic 工具事件生产→消费接缝（Task 2.5 仍未完成）

- 后续定点检查确认 `_bound_tools` 在 `INDEPENDENT_COUNTER_THESIS_RESEARCH` 阶段原先会以默认 `fixture-gate-scoped/2.5.0` 记录真实查询，而 `finalize_skeptic_phase` 只认可 `2.3.0`；原收尾正例是手工写入 `2.3.0` 事件，未覆盖实际工具生产者。这是阶段 Adapter 版本错配，不是研究模型输出问题。
- 现让 Skeptic 的真实工具绑定和收尾过滤共用 `SKEPTIC_ADAPTER_VERSION`，其他多维与普通股字段查询版本不变。收尾正例改为由 `StatelessFixtureTools.query` 真正生成查询事件及 hash，再交给 finalizer，结果为 `PASSED`、`DOWNSTREAM_READY`；只验证确定性接缝，不冒充真实 Subagent 或模型运行。
- 聚焦执行：`/private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_independent_skeptic_stage.IndependentSkepticContractTests.test_finalizer_builds_reference_only_package_and_blocks_hash_drift tests.test_independent_skeptic_stage.IndependentSkepticContractTests.test_two_securities_have_distinct_server_side_query_permissions` → 2 tests, OK；同环境 `-m unittest tests.test_independent_skeptic_stage` → 89 tests, OK。
- 相邻阶段保护：同环境运行 `tests.test_common_stock_research_contracts.CommonStockNativeStageTests.test_common_stock_field_query_uses_only_current_security_and_delivered_ids` → 1 test, OK，字段查询仍返回 `2.4.0`；`tests.test_multidimensional_stage.MultidimensionalStageTests.test_fundamental_eps_focus_reaches_formal_model_context_without_value` → 1 test, OK，新增断言确认多维查询仍返回 `2.5.0`。
- 未关闭：批准清单中的 `fixture-gate-scoped` 仍只表示 Council 的 `2.1.2`，其它阶段版本的权威键、当前执行检查及历史锁隔离尚未统一；不能把本次常量共用当成 H12 完成，也不能把旧包重标成新版本。

## P0 未关闭接缝：Eval 新写入模式与 Schema 实际执行

- **H10 / Task 2.4：** 当前 `product/runtime/runtime_eval.py` 的 `prepare_eval_job` 仅在 `run_manifest.source_mode == "live"` 时启用 `native-draft/1.0.0`；fixture 模式仍生成可新写入的完整 `semantic-rubric-result/1.0.0` 输出说明。`product/runtime/common_stock_eval.py` 的普通股 Eval 当前结果 Schema、Prompt 和 Hook Stop 收尾仍要求模型给出 `run_id`、`input_hash`、`model`、`result_hash` 等技术字段。历史结果读取与当前新写入不能混称。两类入口均未完成语义草稿迁移，本项未勾选；本检查未调用评分模型。
- **H15 / Task 2.6：** 对当前 `product/runtime/schema_validation.py` 作零模型最小负例：对象 Schema 同时声明 `action == NO_TRADE` 时 `maximum_notional` 必须为 `null`，传入 `{"action":"NO_TRADE","maximum_notional":0}`，`validate_schema_instance` 正常返回并打印 `INVALID_ACCEPTED`。这证明该通用校验器目前未执行 `if/then`；不能拿既有专用 NO_TRADE 校验替代 Schema 生效证明。执行命令：`python3 -c 'from product.runtime.schema_validation import validate_schema_instance; s={"type":"object","properties":{"action":{"type":"string"},"maximum_notional":{"type":["number","null"]}},"if":{"properties":{"action":{"const":"NO_TRADE"}}},"then":{"properties":{"maximum_notional":{"type":"null"}}}}; validate_schema_instance({"action":"NO_TRADE","maximum_notional":0},s); print("INVALID_ACCEPTED")'` → `INVALID_ACCEPTED`。本项未勾选；未修改产品校验器或运行真实模型。

### H15 标准 Schema 校验接缝（Task 2.6 进行中）

- 在隔离的 `/private/tmp/stock-agent-schema-ZEXpH8/venv` 安装 `jsonschema 4.26.0`，项目依赖声明加入 `jsonschema>=4.23,<5`；未向生产环境安装包，未启动产品模型。通用校验入口改用 Draft 2020-12，并在执行前拒绝未知关键字、未知 dialect 与远程 `$ref`；明确保留本地已准入 Schema 引用。`if/then/else`、`allOf`、`not`、`$ref` 及其兄弟约束由标准实现执行；保留可定位的原错误码。仓库中 72 份现有 Schema 的关键字预检全部通过。
- `fixture_mcp` 在调用工具方法前校验实际公布的 `inputSchema`；获授权的 `calculate` 在参数不满足条件约束时只有脱敏 `mcp_tool_error`，没有计算记录或收据。已核验非法 `NO_TRADE` 字段从原先 `INVALID_ACCEPTED` 改为 `SCHEMA_TYPE_INVALID:$.maximum_notional`。本次未移除 Evidence/PIT/Risk 的专用验证。
- 聚焦命令与结果：`/private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_strict_schema_validation tests.test_native_evidence_gate tests.test_market_breadth_calculation tests.test_assurance_contracts.AssuranceSchemaTests` → 41 tests, OK；`... -m unittest tests.test_assurance_contracts.AssuranceSchemaTests tests.test_multidimensional_research_contracts tests.test_common_stock_research_contracts` → 125 tests, OK；`... -m unittest tests.test_research_submission tests.test_market_breadth_calculation tests.test_multidimensional_stage` → 修正工具错误优先级后130 tests, OK。第一次扩展测试中 `tests.test_live_cio_final_response` 因隔离 venv 未安装原有 `exchange-calendars` 而报环境错误，`AssuranceBoundaryTests` 在无关 `product/demo/runner.py` 发现已有硬编码 Demo 断言；二者均不能记为本项通过/失败。
- **未关闭范围：** CIO正式动作Schema、普通股Eval Schema与Runtime Eval现行写入路径的完整接缝及工具参数负例矩阵尚未全部验证，宿主执行Python依赖安装也未验证。因此Task 2.6继续未完成，不能把41/125项聚焦通过冒称全链Schema PASS。
- CIO当前新运行已在专用 `validate_cio_draft` 前增加权威 Schema 校验；`tests.test_native_decision_contract.CanonicalDecisionContractTests.test_actual_cio_schema_enforces_no_trade_without_replacing_action_validator` 对完整CIO草稿验证 `NO_TRADE` 两执行字段为null通过，0/非null在Schema和原动作验证中均拒绝；`tests.test_native_decision_contract tests.test_native_run_package` → 20 tests, OK。宿主live CIO测试在隔离环境补足原有 `exchange-calendars==4.13.2` 后可启动，但6个案例在 `prepare_cio` 提前因 `agent profile version differs from candidate manifest` 失败；这是仍未关闭的H12版本镜像冲突，不能归类为Schema回归或声称live CIO已验收。对应命令：`/private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_live_cio_final_response` → 9 tests，6 errors（H12前置版本阻断）。
- Runtime Eval 的 `semantic-rubric-result.schema.json` 只允许 `grader.agent == dev_eval`，而当前 `finalize_eval_job` 在合法 `NOT_APPLICABLE` 分支确定性写入 `grader.agent == deterministic-not-applicable`；若直接把同一Schema强制应用到所有Eval结果，会误拒绝已有合法终态。H15/H10后续须明确“模型评分正式结果”与“不适用确定性结果”的Schema/版本边界，不允许只跳过Schema或修改旧包凑绿。普通股Eval现行Schema也仍与模型原始完整结果耦合，须与H10新写入协议一并核对。
- 本轮又补齐标准验证器的 `Decimal` NaN/Infinity 拒绝和 `patternProperties` 下 `additionalProperties` 错误定位；动态生成 Schema 只对白名单内 `x-generated-from`、`x-evidence-id-constraint`、`x-eval-ablation` 作为注解放行，其余未知扩展仍拒绝。`create_invocation_manifest` 在模型准备前验证当前输出 Schema 定义，而不是仅保存文件 hash。聚焦执行 `/private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_strict_schema_validation tests.test_native_invocation_validation tests.test_native_run_package` → 31 tests, OK；同一隔离环境执行 `... -m unittest tests.test_predecision_cio_stage tests.test_common_stock_research_contracts tests.test_assurance_contracts.AssuranceSchemaTests` → 119 tests, OK。Task 2.6 尚未覆盖两类 Eval 终态及所有当前正式报告入口，保持未完成。
- `prepare_cio` 原先仅用手写 Specialist 校验，未执行冻结的动态输出 Schema；主张或挑战对象多出未声明字段时仍可能交付 CIO。现在在既有一轮格式修订边界内，对正式 Analyst/Skeptic 报告执行冻结 Schema：普通顶层格式错保留原一次修订；其它 Schema 错误直接生成 `SPECIALIST_REPORT_VALIDATION_FAILED`，不准备 CIO、决策或 Risk。分别向 Analyst claim 和 Skeptic challenge 注入未声明字段的负例均拒绝，原格式修订正例仍通过。执行 `/private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_native_run_package tests.test_native_invocation_validation tests.test_strict_schema_validation tests.test_native_evidence_gate` → 55 tests, OK。Task 2.6 仍未完成，尤其两类 Eval 终态未核定。
- 两类已有**模型评分正式结果**在原有语义、身份及 hash 检查后，现额外执行各自真实 Schema，再允许持久化：普通股 Eval 的 `grade=true`（Python 原集合检查曾把 bool 当整数）被 Schema 拒绝且不生成 `eval/result.json`；Runtime Eval 模型结果中的非字符串 Evidence 引用被 Schema 拒绝。此改动不改变评分阈值或研究判断，也不把确定性 `NOT_APPLICABLE` 冒充模型结果。执行 `/private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_common_stock_research_contracts tests.test_native_output_handoff tests.test_eval_execution_proof` → 初次 115 项中 1 项因 macOS `/var` 与 `/private/var` 别名的读取证明路径比较失败；修复下述接缝后同组 **118 tests, OK**。
- H10 相关实际读取证明的路径比较原先要求命令文本逐字包含已 `resolve()` 的路径；macOS 同一临时文件可由 `/var/...` 与 `/private/var/...` 指向，导致错误的 `EVAL_NATIVE_MANIFEST_READ_MISSING`。现将工具调用参数中的绝对文件路径解析到同一真实路径，同时仍要求对应工具输出包含冻结 manifest 原文；别名正例、另一文件即使内容相同以及错误输出负例已测试。`tests.test_native_output_handoff tests.test_eval_execution_proof` → 19 tests, OK。此处只修读取证明，不证明 H10 两类新写入都已完成。
- 真实工具调用可能把 shell 命令包在 `code` 参数里，故读取证明继续识别被包装的**精确**目标路径；相似文件名前缀不算目标文件。追加包装调用正例后，`tests.test_native_output_handoff tests.test_eval_execution_proof` → 19 tests, OK。

### H15 当前研究与评分草稿的准备期 Schema 预检（Task 2.6 仍未完成）

- 普通股研究、多维研究和资料准备的当前输出 Schema 现在在构造交付包时调用同一 `validate_schema_definition`；普通股 Eval 正式输出 Schema 及 Runtime Eval 的完整/`native-draft` 输出 Schema 也在评分前预检。未知关键字、非法定义和未批准引用不能等模型返回后才发现。实例校验及已有 Evidence/PIT/Risk 检查不因此删除。
- 对两份真实动态研究 Schema 注入未知关键字，构造阶段均以 `SCHEMA_KEYWORD_UNSUPPORTED` 拒绝；资料准备与普通股 Eval 验证预检调用确实发生；Runtime Eval 的完整与 `native-draft` 两种输出 Schema 均有正例和未知关键字负例。执行 `/private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_strict_schema_validation` → **8 tests, OK**。
- 受影响研究阶段执行同环境 `-m unittest tests.test_strict_schema_validation tests.test_common_stock_research_contracts` → **107 tests, OK**；`-m unittest tests.test_multidimensional_stage tests.test_research_materials_stage` → **104 tests, OK**；普通股 Eval 类 `tests.test_common_stock_research_contracts.CommonStockFocusedEvalTests` → **11 tests, OK**。
- Runtime Eval 扩展组首次执行 `-m unittest tests.test_runtime_eval_job tests.test_native_eval tests.test_strict_schema_validation` → **20 tests，19通过、1错误**，`TRACE_EVIDENCE_CLOSURE_FAILED:dangling`。定点重现发现新 Schema 正确先拒绝悬空 ID，但错误仅为 `SCHEMA_ENUM_INVALID:$.claims[0].evidence_refs[0]:allowed=...`，没有实际悬空值，旧 Trace 无法把此失败确认为已经封闭的 Evidence 错误。现保留 Schema 先执行；只有专用校验明确返回 `EVIDENCE_CLOSURE_FAILED:<id>` 时采用该精确错误，非法报告仍无法进入 CIO/Risk，也不自动改写引用。原失败案例新增断言：错误包含 `dangling` 且无 `decision.json`。重跑上述完整扩展组 → **20 tests, OK**；`tests.test_native_run_package tests.test_strict_schema_validation` → **24 tests, OK**。H10/H15 对合法 `NOT_APPLICABLE` 终态的独立 Schema 边界仍待规划澄清，Task 2.6 不勾选。
- 定点检查发现 `validate_schema_definition` 原先接受不存在的本地 `#/$defs/missing` 或离线文件引用，直到实例校验才报错。现准备期递归核验本地 JSON Pointer 及受控仓库 Schema 引用，外部子 Schema 的内部引用按其完整文件根解析；远程引用仍拒绝且不取网。负例覆盖缺失定义/文件、非法转义与外部文件内悬空引用，正例覆盖转义 Pointer 和现有跨文件引用。执行 `tests.test_strict_schema_validation` → **9 tests, OK**；当前 `product/schemas` 72 份 Schema 全量定义预检 → **72/72**。受影响组 `tests.test_native_run_package tests.test_native_invocation_validation tests.test_strict_schema_validation tests.test_native_evidence_gate` → **58 tests, OK**；`tests.test_common_stock_research_contracts` → **100 tests, OK**；`tests.test_multidimensional_stage tests.test_research_materials_stage` → **104 tests, OK**。这些仍是确定性契约证明，不构成真实模型加载或 H15 全项完成。
- `NOT_APPLICABLE` 边界再核对：`finalize_eval_job` 会确定性生成 `grader.agent=deterministic-not-applicable`、`model=none`、五维均不适用并保存 `semantic-rubric.json`；`verify_eval_job` 的该分支只做 hash/值检查，未执行 `semantic-rubric-result.schema.json`。用该实际结构调用当前 Schema 得到 `SCHEMA_CONST_INVALID:$.grader.agent`。这不是可以改填 `dev_eval` 的格式错误，而是模型评分与确定性不适用结果的正式契约分支缺失。需按规划确认分别约束两分支、保持旧包读取及禁止伪造模型证明；在此之前不勾选 Task 2.6，不以跳过 Schema 宣称全量 H15 PASS。

## P0 未关闭接缝：H09 CIO 报告消费证明（Task 2.3）

- fixture Council 的 `prepare_cio` 将 `validated_reports` 整份放入 CIO 输入，当前 Prompt 要求模型复制 `validated_report_hashes`；`validate_cio_draft` 只比较模型回写的 `consumed_reports` 与报告 hash。这能证明报告存在、已验证并交付，不能证明模型逐份实际阅读或明确选为论据。
- predecision CIO 当前将完整报告放入 Prompt，同时用 `expected_consumed_reports` 要求模型原样复制目录。现有 Evidence query 事件证明 Evidence 被查询，不能单独证明报告被实际消费。为避免把“已交付”伪装成“已读取”，Task 2.3 暂不勾选；下一步需按当前规格区分目录、真实交付/读取事件与模型明确选择，再由确定性层装配身份/hash，不能仅将复制动作改到 Python 后即宣称关闭。

## P1：H14 事实/获取观察/Gate视图身份（Task 4.2）

- 旧事实投影会按字段名递归删除 `retrieved_at` 等字段；反例是 `value.retrieved_at` 改变而内容 hash 不变。新写入只在顶层剔除获取观察字段，明确例外 `metadata.calendar_hash` 属于可变化的日历获取上下文，并在观察记录中保存原 hash；其它嵌套同名字段保留。Gate freshness 字段不得进入事实写入，仍由 View 处理。
- SQLite 事实版本新增可空 `projection_version`：无标签旧行严格按原投影/原 hash 验证，新行按 `fact-projection/2.0.0` 写入。v2→v3 只增加列，不重建事实、改写旧 hash 或推进 checkpoint；旧 v2 数据库在升级前仍可通过只读 resolver 和浏览器读取。新观察只有在按新语义投影可证明等价时才关联旧事实；旧投影碰撞但新语义不同会保留新版本，并在尝试详情记录旧/新版本 hash。
- View 回绑对每个历史行先用其记录的算法验证内容 hash 与逻辑键，再按当前显式语义投影做唯一匹配；零匹配或多匹配继续 fail-closed。离线 View 修复与网页浏览器也按行版本验证，不把当前算法套到历史行。
- 定点红灯：`test_nested_fact_value_fields_are_not_observation_metadata` 在旧算法下确实出现相同 hash，修复后通过。最终执行 `/private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_memory tests.test_research_memory_chain tests.test_local_research_browser tests.test_common_stock_research_contracts` → **160 tests, OK**。之后仅增加投影冲突的旧/新 hash 诊断并重跑对应三项聚焦测试 → **3 tests, OK**；`git diff --check` 对本项源码与测试通过。未运行产品 LLM、Replay、Regression 或完整 Gate；旧历史包未改写。

## P1：H13 hash 口径（Task 4.1 进行中）

- 当前 `product/runtime/hashing.py` 的旧 `canonical_hash` 与 `product/mcp/provenance.py` 的 `content_hash` 均无算法标签且保留原序列化；文件 SHA256 独立按原始字节计算。没有对旧包重算或写回。
- 新增显式 `canonical-json/2.0.0` 类型化序列化：对象/数组/标量有类型标签，Decimal 保留十进制文本，带时区时间转 UTC，Unicode 原码点保留，非有限数和无时区时间拒绝。新 hash 带 `canonical-object`、`self-excluding-envelope`、`fact-content` 或 `delivered-view` 域分离；这是后续版本化新写入的基础，**尚未切换现有正式产物**。
- 将研究草稿提交的 `content_hash` 生产、Stop 解析、正式接受及历史复制包读取改为同一 `legacy_envelope_hash`（仅顶层排除自身字段，旧摘要不变）。原 `submission_version` 仍是旧算法选择依据，不把新算法套到旧存稿。`/private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_hashing_contracts tests.test_research_submission` → **44 tests, OK**；覆盖空白/键序、hash 类别、自身字段、Decimal/时间/Unicode、非有限值、错误口径/位置、旧/新固定向量与研究提交正反接缝。
- Research Memory 的增量计划、Research View 与报告引用三类旧版 envelope，生产和读取验证现在也共用相同的顶层自字段排除 helper，不改变 `company-research-*/1.0.0` 旧摘要。执行 `/private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_hashing_contracts tests.test_research_submission tests.test_research_memory tests.test_research_memory_chain tests.test_local_research_browser` → **104 tests, OK**；这只证明这些具体生产者/消费者接缝，未扩大为全部历史包验证。
- 随后仅为新 v2 算法补上非法 Unicode 定位拒绝，`tests.test_hashing_contracts` → **6 tests, OK**；`git diff --check` 通过。旧算法和上述旧版接缝未改。
- **未关闭范围**：其它本 Change 涉及的报告、Gate、工具事件、Memory/View、Eval 与历史读取生产者/消费者尚未逐对归并并核对错误诊断；Task 4.1 保持未完成。上述 44 项不证明全部 hash 路径，也不授权产品模型或完整 Gate。

### H13 Skeptic 查询事件的生产→消费接缝

- `GateScopedFixtureTools._record` 原用 `product.mcp.provenance.content_hash` 为查询事件生成 `event_hash`，`finalize_skeptic_phase` 原用 `product.runtime.hashing.canonical_hash` 排除自身字段后校验；JSON 内容当前字节口径相同，却由两个模块平行实现。现两端都复用已有 `legacy_envelope_hash(event, hash_field="event_hash")`，**只改生成/核验函数，不改变旧事件摘要值或其它工具结果的旧算法**。
- 真实 `StatelessFixtureTools.query` 生产事件的正例同时验证返回结果的 `output_hash`、新共用 helper 与旧 `content_hash` 摘要一致，再交给 Skeptic finalizer，仍得到 `DOWNSTREAM_READY`；改动事件正文而不改 `event_hash` 的负例摘要不再匹配。执行 `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_independent_skeptic_stage tests.test_hashing_contracts tests.test_native_evidence_gate` → **118 tests, OK**。未启动模型；其它工具事件及报告的生产/消费算法仍待逐对核对，Task 4.1 保持未完成。

## H12 退役 profile 的冻结引用复核（Task 2.5 未完成）

- 本次对 `live-us-equity` 作当前镜像校验时，先将其 CIO 版本从 `3.1.0` 改成 `3.1.2`。随后核对 `holding-research-inputs.json` 才确认该 profile 是 `RETIRED/COMPATIBILITY_ONLY`，其冻结文件字节 hash 为 `d38d6124d4e2b14d2889e36af7ca700f9ac62ed96b21c5472adb5ac2bbd496bb`。改动后的文件 hash 为 `1cf4f042f6cd51ac0822f86f66e83888316d2ae33a5cae36170a75490872ebc6`，实际拓扑测试报 `RESEARCH_TOPOLOGY_REFERENCE_HASH_MISMATCH:retired_live_profile`。这不是应通过改写拓扑旧锁解决的当前版本漂移。
- 已仅撤销本次退役 profile 的版本改动、对其新增的当前镜像检查及相应测试；恢复后文件 hash 与原冻结引用完全一致。执行 `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_input_topology.ResearchInputTopologyTests.test_current_topology_maps_three_domains_and_provider_planes tests.test_live_profile.LiveProfileTests.test_live_discovery_lock_does_not_modify_fixture_manifest` → **2 tests, OK**。未修改拓扑 hash、历史包或当前 fixture 批准版本。
- 旧 `tests.test_live_cio_final_response` 的 CIO `3.1.0/3.1.2` 冲突不能通过升级已退役的冻结 profile 来消除；其相关失败继续如实保留，不冒充当前主研究路径的版本验收。H12 仍须明确 Council 与 Skeptic/普通股/多维各阶段 Adapter 的权威作用域及生产→消费检查，Task 2.5 不勾选。

## H13 计算收据与工具事件接缝（Task 4.1 仍未完成）

- `StatelessFixtureTools.calculate` 写入的 `receipt_hash`、`research_submission` 读取的收据及复制包事件、Hook 核验的收据及事件，现在复用 `legacy_envelope_hash`，只排除顶层指定的自 hash 字段。Hook 原本独立维护的 `_canonical_hash` 也委托给共享的旧版 `canonical_hash`；直接脚本启动与包导入分别走同目录或相对导入，不依赖偶然的仓库 cwd。未将新 v2 算法套到旧收据，也未修改任何冻结包。
- 真实计算工具生成的收据与事件进入 Hook 正例和 `research_submission` 上游选择/复制包读取正例；同一收据摘要与既有 `content_hash` 口径一致。改动收据数值或给事件增加字段而不更新摘要的负例均被拒绝；独立 Hook 脚本以非法输入启动时返回预期的 `HOOK_INPUT_NOT_OBJECT`，证明共享 hash 模块在该启动方式下可加载。
- 执行 `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_hashing_contracts tests.test_multidimensional_stage.MultidimensionalStageTests.test_runtime_calculation_receipt_is_citable_and_tamper_rejected tests.test_research_submission` → **46 tests, OK**；扩大至 `tests.test_hashing_contracts tests.test_multidimensional_stage tests.test_research_submission tests.test_independent_skeptic_stage tests.test_research_materials_stage tests.test_native_evidence_gate` → **261 tests, OK**。`git diff --check` 对已追踪的受影响文件通过。均为确定性接缝验证，没有启动产品模型、Regression 或 Gate。
- 这只关闭计算收据/工具事件的一个生产—消费子路径；其它报告、Gate、Eval 等 hash 口径仍须逐对检查，Task 4.1 不勾选。

## H13 Gate 摘要生产—消费与 H12 live 工具接缝（均未整体关闭）

- fixture/live `evidence_gate` 仍按原 `content_hash` 字节口径生成 `bundle_hash`，但通过统一的 `legacy_envelope_hash(..., hash_field="bundle_hash")` 表达顶层自身字段排除；Skeptic、研报提交与 Hook 中本次覆盖的 Gate 读取也调用同一 helper。旧冻结包、PIT 规则和允许集未改。
- 真实 fixture Gate 正例验证原 `content_hash` 与共享 helper 摘要相等，改动 cutoff 而不更新 hash 的负例不相等；live Gate 有同样的旧摘要兼容正例。执行 `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_native_evidence_gate tests.test_independent_skeptic_stage tests.test_research_submission tests.test_multidimensional_stage tests.test_hashing_contracts` → **238 tests, OK**。
- 扩展到 `tests.test_live_contracts_gate` 时首次为 **25 tests，1 failure + 1 error**：live 查询事件继承了 fixture Adapter `2.5.0`，且 `StatelessLiveTools` 缺少 `_last_reference_map` 初始化。现 live 工具显式传入既有 `LIVE_MCP_VERSION=live-gate-scoped/1.0.0`，基类初始化空引用映射；两条原失败测试重跑后，查询/版本断言通过，但 `test_live_prepare_reuses_native_invocations_without_fixture_alias` 继续到 CIO 准备时遇到既有退役 profile `3.1.0` 与当前批准清单 `3.1.2` 冲突。未修改退役 profile 或旧版本锁，不把该测试记为通过。
- 精确执行 `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_live_contracts_gate.LiveContractGateTests.test_live_gate_hash_preserves_legacy_content_digest tests.test_live_contracts_gate.LiveContractGateTests.test_live_tools_only_expose_verified_gate tests.test_native_evidence_gate tests.test_hashing_contracts` → **32 tests, OK**；相邻 `tests.test_live_admission` → **10 tests, OK**。H12 的 live CIO 版本冲突及 H13 其余 Gate/报告/Eval 消费者仍未关闭，Tasks 2.5、4.1 均不勾选；这些测试不代表真实模型或完整 Council 运行。
# 资料准备语义提交及实际工具审计（Task 3.4，2026-09-30）

本节记录当前写入入口的确定性关闭证明。共享源码还有其它授权修改；下列文件快照不表示所有共享 hunk 已独立复核，也不是候选版本锁。

- **生产者**：新 prepare 为公司研报、同行、宏观和市场材料任务声明 `research-material-semantic-draft/1.0.0`。草稿结构由原正式业务结构派生；实际 SubagentStart 交付相同结构及说明。模型只提交状态、摘要、检索意图、选择、理由和缺口，不填写 run/invocation/agent/security 固定身份、文件路径、hash 或尝试审计。
- **审计**：Stop 先按可信派发/Start 绑定身份并验证语义草稿结构，然后从实际 MCP 事件与原文件装配查询、每次获取尝试及路径。逐条核对 task 身份、输入/输出 hash、文件字节及获取尝试/正文绑定，保留重复查询和缓存命中。未知路径、无事件文件、未执行查询、非法选择、事件或文件篡改均拒绝；不会替模型猜正文或修改说明。`BODY_VERIFIED` 是原获取分类，不能证明内容足够支撑投资结论。
- **消费者**：Finalizer、宿主完成判定及正式研究导入重新计算底层审计，不只相信 `tool_audit_hash` 或保存状态；正式研究同时复制原审计字节。导入原来仅按 `document_id` 匹配，完整记录加入后把 fetch attempt 和 document 误作两份正文；现按原 `verified-research-document/1.0.0` 类型和原 candidate/document ID 匹配，仍要求唯一正文、BODY_VERIFIED 及既有 PIT，不删尝试记录规避错误。
- **历史**：原正式报告读取结构仍保留，不重写历史包、事件或锁。当前语义模式拒绝旧全包草稿，不把当前模式称为历史兼容以接受技术字段。其它尚未迁移角色仍归 Task 3.1，不据此宣称全系统迁移完成。

实际命令及结果：

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_material_semantic_handoff tests.test_research_materials_stage tests.test_multidimensional_stage tests.test_research_submission
openspec validate simplify-research-handoffs-and-acceptance --strict
git diff --check -- product/runtime/research_materials_stage.py product/runtime/codex_hook_recorder.py product/runtime/multidimensional_stage.py tests/test_research_materials_stage.py
```

最终 **155 tests / OK，35.129s**；OpenSpec valid、差异空白检查 exit 0。测试走实际 stdio 参数校验/事件落盘和真实 Hook/归集/导入代码，传输由测试 provider 替身提供；生命周期是模拟的，不证明真实 Codex Subagent 或 Skill 推理。

首次 23 项旧接缝中 2 项导入失败准确暴露正文/尝试同 ID 误判，修复消费者类型辨识后 23/23 通过。新测试初次因只模拟一个子任务却设置三任务首波约束而被原 Hook 拒绝；测试改为真实配置允许的一并发，不放宽产品约束。旧格式负例按结构首差异断言缺 `query_intents`，补该字段后仍因技术字段拒绝。保留这些失败说明，不以最终结果覆盖首次差异。

当前文件完整 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `product/runtime/research_materials_stage.py` | `a958cd4dfcad16b8fd89c452d19c9b4086ef9842fe202a4dbd62d09165fe1e48` |
| `product/runtime/codex_hook_recorder.py` | `a608d8f7ed87405f147d1ae1031e13fdba4c429573421a22911362ade9c2bb29` |
| `product/runtime/multidimensional_stage.py` | `f5cc6363c48e703aa789a90f983a861dae3966bfb79bec5fe600cc2fc7bea232` |
| `tests/test_research_materials_stage.py` | `89909f74bda774c555a9fb23a838399c9e3d1db70b37d0db58841e8193c734a7` |
| `tests/test_material_semantic_handoff.py` | `63455afdeb197c5f05da3c247c359366b5adb906966ab05122be9d2c300cd8a2` |

仅 Task 3.4 完整勾选，整体 **11/30**；Task 3.1–3.3/3.5 仍保留未完成部分。本轮未调用模型、网络、Smoke、真实 Eval/Replay/Regression/Gate；未归档、提交或推送。新写入的实际 LLM 证明为 **NOT_RUN**，统一在 Task 6.4 明确预算后执行，原八维保持暂停。

## 独立反证语义提交与多证券主张交接（2026-09-30）

**范围**：Task 3.1 的独立反证当前写入入口、Task 3.2 的待反证问题主张绑定，以及 Task 6.1 对应的 Agent/Skill 输出职责片段；这些 Task 仍有其它入口未完成，不整体勾选。对应规格为 `research-handoff-contracts` 的“当前语义草稿必须区分模型判断和技术装配”“引用选择必须任务限定且不可模糊修复”“材料CIO及Eval的审计必须来自真实记录”，以及 `codex-development-environment` 的“角色方法与任务上下文必须分层且实际交付一致”。

- **生产者与交付**：`prepare_skeptic_phase` 及新 resume attempt 声明 `specialist-semantic-draft/1.0.0`。共享 `invocation.specialist_semantic_schema` 从原正式业务 Schema 派生草稿，去掉 schema/run/invocation/agent/Skill/artifact 技术字段，保留挑战、假设、置信度及理由等原研究结构。实际 Start Hook 交付派生结构，不要求模型补固定身份；首轮输入仍不含正向报告、结论、私人组合、bundle hash 或未解决问题。旧 attempt 不回写。
- **接收与归集**：Stop 先验证原派发/Start 可信绑定，再校验语义草稿，由原 envelope 装配正式 `CounterThesisReport/2.1.0` 并保存 JSON/中文报告。Finalizer 要求实际同 invocation 的 MCP 查询与报告引用闭合；合法但未查询的 ID 不能因装配而变成 DOWNSTREAM_READY。包内正式报告由现有 predecision 读取器重验。测试确实走 stdio 参数检查、查询事件落盘、实际 Hook/报告/归集/消费者代码；生命周期及研究文字是测试合成，不证明真实 LLM、Skill 推理或真实 Codex Subagent。
- **冻结绑定与历史**：当前 index/task/invocation 协议标记必须一致。packet 即使重新计算摘要，也不能替换冻结 invocation、研究输入、任务身份、Prompt 或派生 Schema。测试用旧格式 packet 可读取，但旧格式 capture 与 launch 明确拒绝新写入，且不会调用子进程。原正式业务 Schema/Validator 保留；本项仅证明该旧格式接缝，不代表 Task 4.3 已完成完整历史包离线读取。没有改写真实历史包、历史锁或生产版本指针。
- **发现并修正的生产—消费首差异**：双证券真实 bundle 归集暴露同名局部 claim 的待反证问题仍使用裸 ID，消费者正确拒绝 `HOLDING_RESEARCH_BUNDLE_QUESTION_CLAIM_DANGLING`。程序现在从原报告/原版本确定性限定待反证问题的引用，不改写局部 claim、观察条件正文或原报告；跨报告同名正例及双证券完整前置 Gate 通过。不将此子路径当作全部短引用入口完成。
- **角色同步**：Skeptic Agent 保留原工具权限、独立首轮隔离和研究职责，Skill 保留原反证方法；输出结构交由实际任务 Schema。当前 `product/version-manifest.json.resource_hashes.skeptic_agent` 显式绑定该 Agent 实际字节；批准版本号、模型路由、原运行锁和生产指针未改。不静默忽略资源漂移。

实际命令与结果：

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_skeptic_semantic_handoff tests.test_scoped_research_claims tests.test_independent_skeptic_stage.IndependentSkepticContractTests tests.test_product_config tests.test_native_invocation_validation tests.test_native_output_handoff tests.test_native_run_package tests.test_predecision_cio_stage tests.test_multidimensional_research_contracts
openspec validate simplify-research-handoffs-and-acceptance --strict
git diff --check -- product/runtime/invocation.py product/runtime/independent_skeptic_stage.py product/runtime/codex_hook_recorder.py product/council/multidimensional_research.py product/.codex/agents/runtime_skeptic.toml product/skills/counter-thesis/SKILL.md product/version-manifest.json tests/test_independent_skeptic_stage.py
```

最终 **127 tests / OK，22.165s**；OpenSpec valid，已追踪受影响文件差异空白检查通过。控制台的 `proof-failure`、`dependency-failure` 是既有负向测试故意注入的终态，不是产品运行结果。较早的 **192 tests / OK，39.248s** 包含由模块导入重复收集的八维测试，不能将其全部算作新增反证测试或候选晋升证明。

首次新测试 **8 tests：1 failure、1 error**：failure 为测试错误地期待 package 内包含异常字符串（实际契约只保存 FAILED，查询集合在 execution-proof）；改为检查底层查询证明和原闭合 Validator。error 是上述双证券裸主张生产者缺口，已修复。Agent 指令同步后聚焦 **44 tests：1 failure、20 errors**：旧文本断言所需 `data_gaps` 职责仍保留，当前 Agent 字节 hash 未同步造成 discovery 严格拒绝；显式同步当前资源 hash 后 **44 tests / OK**。这些首次差异保留，不将它们归因于模型非确定性。

Skill 专用 `quick_validate.py` 在测试 venv 和 bundled Python 下均因缺少 `yaml` 无法启动；系统 Python 的单独 `import yaml` 检查也失败。状态为 **ENVIRONMENT_ERROR / NOT_EXECUTED**，没有安装依赖或宣称该脚本通过。原 `tests.test_product_config` 已执行并通过 Skill frontmatter/批准版本、配置及链接检查；没有改 Skill 元数据字段。真实产品加载与推理仍为 **NOT_RUN**。

本节源码/测试完整 SHA-256（工作现场快照，不是候选晋升锁）：

| 文件 | SHA-256 |
|---|---|
| `product/runtime/invocation.py` | `3129255d32628fb11334e41f0d8930ae027df4aa7b5319b16f9f301113535227` |
| `product/runtime/independent_skeptic_stage.py` | `e5407715fe6a358ff3a15674e07f390200b561002ccd46a37e793c0df6988866` |
| `product/runtime/codex_hook_recorder.py` | `553c8af5b0a1b4294aeb82edfce601fcbfa899d259fbdacd2be6a77b8adaac1d` |
| `product/council/multidimensional_research.py` | `858d544726aecea64d0d6a7958a7cb26e098734bab416bbcffbcf40ec93dad6d` |
| `product/.codex/agents/runtime_skeptic.toml` | `1874690b7a00841fe1b20404d42f6e7b566786a5244baed2e4f5cfd18a89374d` |
| `product/skills/counter-thesis/SKILL.md` | `fff0e890d3d4b200475aaffc3bf92caff07f7d4a9727346142f28623337a7e2b` |
| `product/version-manifest.json` | `cb13fe449ced86e8ecefc51906c481cac5db27d08b1f7b75ddc5b3afe462b2d7` |
| `tests/test_independent_skeptic_stage.py` | `f94107e56f2bccfb5ff8d9af3f9182209cd3d8c1f91c14743274a97d5e994ac8` |
| `tests/test_skeptic_semantic_handoff.py` | `0c15cd611b847f059d295089625a5b780cd9f14b6149fae6feb1719efcaa84b7` |
| `tests/test_scoped_research_claims.py` | `be06211abe3dc13b9ffba859f33bb48106b13d614f3ca2687fee18d8c52e1b57` |

本次不新增整体完成勾选：仍为 **11/30**。fixture Council Specialist 当前写入、其它角色短引用、历史离线读取、局部修订及其它未完成任务继续按原任务推进；没有启动真实模型、Smoke、Eval、Replay、Regression 或 Gate，也没有归档、提交、推送。

## fixture Council 专业报告的语义提交接缝（2026-09-30）

对应 Tasks **3.1、5.2 的当前 fixture 子路径**及 H01/H02/H08；复用先前共享 envelope，不新增调度器、Agent 或业务判断。两项 Task 尚有其它入口或要求未关闭，继续未勾选。规格依据为“当前语义草稿必须区分模型判断和技术装配”“材料CIO及Eval的审计必须来自真实记录”“精简输入不得隐藏研究边界”。

### 实现及消费边界

- 当前 `prepare_run` 同时声明 `subagent-start-context/2.0.0` 和 `specialist-semantic-draft/1.0.0`，各 Specialist Invocation 绑定相同草稿协议并重算其原 manifest hash。原正式角色 Schema、Evidence/PIT/Risk 语义未改；草稿 Schema 从原角色 Schema 派生，不合并公司主张与反证挑战结构。
- 主线程只派发简洁任务；Start Hook 独立交付该角色冻结输入。新生成 Prompt 不再要求父线程复制两份完整 Input/Invocation/Schema、手工保存或改写子报告。工具调用仍按原授权身份参数执行；短 Evidence/Calculation 引用及剩余常驻角色提示继续由 Tasks 3.2、3.3、6.1 处理，不宣称本项已全部精简上下文。
- Stop 使用真实 Start 的父/子会话、模型、冻结输入绑定，并复核原 ALLOW dispatch 的事件 hash、协议和输入 hash。草稿不能自报身份覆盖绑定。共享 envelope 仅装配原 schema/run/invocation/agent/Skill/artifact 技术字段，研究字符串、选择、信心及原数组顺序不变；结构及原 Evidence Closure Validator 在正式保存前执行。
- 保存独立 `.native.json` 原稿与正式报告；幂等相同稿可读，不同稿不可覆盖。CIO 的现有 `prepare_cio` 读取这些正式报告，真实性要求下重新检查 Start；后续执行证明读取器从原稿、冻结 Schema/Invocation 重建正式对象，核对两类输出 hash 和 Start。无效原稿返回明确 `ExecutionProofError`，而不是绕过或冒充 NO_TRADE。
- 当前 launcher 拒绝未标记的旧执行协议；原已退役 live/兼容 fixture 仍拒绝真实启动。旧 native-full/v1 capture 明确拒绝新写入；历史 envelope/正式报告读取与旧证明校验保持原算法，不重写旧包或旧锁。不是 Task 4.3 的完整离线搬迁验收。
- 首轮反证仍不含 Analyst 结论。输入非法及未来/过期资料安全终止保留零 Specialist 行为；当前清单同样声明新协议，不能因没有子报告而被误当旧入口。

### 实际命令与结果

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_council_semantic_handoff tests.test_native_output_handoff tests.test_native_run_package tests.test_native_invocation_validation tests.test_nested_codex_launcher tests.test_native_execution_proof tests.test_skeptic_semantic_handoff tests.test_common_stock_semantic_handoff tests.test_product_config tests.test_cio_handoff tests.test_runtime_ablation
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_council_semantic_handoff tests.test_native_run_package
openspec validate simplify-research-handoffs-and-acceptance --strict
git diff --check -- product/runtime/invocation.py product/runtime/codex_hook_recorder.py product/runtime/run_package.py product/runtime/nested_codex.py product/runtime/execution_proof.py product/runtime/smoke_prompt.py tests/test_native_run_package.py tests/test_native_output_handoff.py
git diff --no-index --check /dev/null tests/test_council_semantic_handoff.py
```

- 受影响集合 **136 tests / OK，58.580s**：包含真实确定性 Hook/MCP 及 CIO 消费者、原先普通股/反证交接、历史 envelope、launcher、执行证明和已有消融装配单元测试；没有运行真实 Ablation Job。
- 随后仅补输入非法清单的当前协议标记（其它源码不变），并增加对应安全终止正例。受影响子集 **27 tests / OK，8.115s**，覆盖输入非法、未来/过期 Gate 的 SAFE_NO_TRADE、无子上下文及不出现派发。
- 新测试共11项，覆盖合法双角色→CIO、合法多引用顺序、拼接 source/time 和未知 ID、技术字段回填、错模型/跨子会话、缺 Start、缺/坏/重新签 hash 但输入不符的 dispatch、协议降级/未知、同稿幂等/不同稿不覆盖、输出路径逃逸、原稿篡改、旧 launcher 在子进程前拒绝及零 Agent 安全终止。合成执行事件仅用于测试读取器，**不是本次真实 LLM/Skill 加载或执行证明**。
- OpenSpec strict valid，已追踪差异检查 exit 0。新增文件 `git diff --no-index --check` 无空白错误输出；exit 1 表示 `/dev/null` 与新增文件有差异，不能把它称作普通 `git diff --check` 的 exit 0。
- 首次受影响57项有2个测试环境设置错误：旧手工报告测试在当前真实性路径缺 Start，提前形成失败；测试现在通过实际 Hook 函数建立合成的 Start/dispatch，然后分别验证缺最终执行证明仍 fail-closed。另有测试调用签名错误、固定中文断言错误及已创建 invocation 的临时包无法再启动；按实际接口/结构检查及全新旧协议测试包修正，不放宽产品校验。保留失败事实，不归因于 LLM 非确定性。

### 本轮完整字节快照

仅标识工作现场，不新增候选锁，含已授权共享文件其它改动；提交时仍须按 hunk 分离。

| 文件 | SHA-256 |
|---|---|
| `product/runtime/invocation.py` | `5e29152ef836bbbfd5640ab240e7386198dc890ad1a601adcb44b42de9f7e7ab` |
| `product/runtime/codex_hook_recorder.py` | `ee580b9ef9b73604f95ae943500a756181ca3c6db42bc7928b71151380511bbc` |
| `product/runtime/run_package.py` | `68be8c0390cef1dfe03a81c71b1be23c6a1f8025aaff700c43dc408852685043` |
| `product/runtime/nested_codex.py` | `25293d218b3a77d89bf6996ca6f26c28788668029f7bb5ad4ae79df96e531af0` |
| `product/runtime/execution_proof.py` | `f7beaa31359e63d287fff14938f07df85f97ee67552a24db48007b7b12c095eb` |
| `product/runtime/smoke_prompt.py` | `1937416c1e584b20039b250f82bf67c8c82c28fc4dc646720b33d6743a129c7e` |
| `tests/test_native_output_handoff.py` | `c01f00a0e293b2defcf5fe861e57e68fc232d4efa58dd5c53d07e440fd971ebc` |
| `tests/test_native_run_package.py` | `c4c88bb6e2491c5af818e81bfc20a15b843c07efa719a8f36ac7b227e3157071` |
| `tests/test_council_semantic_handoff.py` | `c95751ddca378e299cd5c98673c8fd73541d8a283600ae9ae962d2d1a20a2e07` |

总进度仍为 **11/30**，不是本轮只修改11项：其余19个大任务有多项子路径已实现但尚不能整体勾选。本轮完成 fixture Specialist 的原稿→正式报告→CIO/证明读取接缝；尚需短引用全入口、局部修订、历史离线依赖、映射/状态投影及统一有限收尾。真实 LLM 补验为 **NOT_RUN**，按 Task 6.4 合并缺口与预算后供批准；原八维继续暂停。未运行模型、网络探针、Smoke、真实 Replay/Eval/Regression/Calibration/Ablation/Promotion/Gate；未归档、提交或推送。

## 普通股任务短 Evidence 引用贯通（2026-09-30）

对应 **Task 3.2 / H02 的普通股子路径**，并涉及 Tasks 3.1、3.3、3.5、5.2 的部分接缝。依据“引用选择必须任务限定且不可模糊修复”“当前语义草稿必须区分模型判断和技术装配”“精简输入不得隐藏研究边界”。这些大任务尚未覆盖全部角色和要求，保持未勾选；总进度仍为 **11/30**。

### 实际交接与保留边界

- 复用 `multidimensional_references` 既有 v2 映射，不新增框架。普通股新 Run/Task/Invocation 声明一致的 `reference_transport_version`；映射绑定任务身份、冻结 Gate、原始包内容及运行目录。实际 Start Hook 交付模型视图：目录/允许集使用短引用，草稿 Schema 从原业务结构派生，其 Evidence enum 仅含本任务短引用，完整映射不交付模型。
- Hook、查询工具和 Stop 使用相同的冻结包构造器。当前映射必须从冻结请求、Gate、Schema 和 Invocation 重建；重新签 `map_hash`、packet/index/manifest hash 不能使假映射通过。协议降级、未知版本及任务/Invocation 不一致拒绝，不继承摘要 PASS。
- 普通查询与原有估值/基本面附件查询均转换明确引用字段；审计仍保存原始 Evidence IDs 和原始结果 hash，另记录模型交付视图及映射 hash。附件允许引用只来自原请求授权集和既有获准附件，不扩权限；原附件及其 hash 不回写。事实值、source_id、as_of、retrieved_at、期间/单位、正文、脚注、否定、限制及 value/metadata 内同名键不替换。
- Stop 先按模型实际获得的 Schema 验证，再精确展开所选引用，最后沿原 envelope、Evidence Closure 和计算/附件消费检查保存正式报告。正式引用、数组顺序及中文附录保留原始 ID；研究文字、信心和判断不改写。Start/Stop 保存实际视图/原稿 hash 和映射 hash，不要求 Agent 抄录。有效原稿装配后复用同一已核验 packet，不重读另一映射作为这份报告的证明。
- 实际 MCP 已验证可省略 calculation_id，由既有服务端分配；倒序分子/分母调用得到真实 ratio=5，原审计保留有序输入。这里只完成普通股的 ID 分配接缝，**不宣称 Calculation 短选择及全部血缘装配已完成**，其余要求仍属 Task 3.3。
- 旧运输格式及正式报告保留只读、原算法/字节验证。旧普通股运行明确拒绝新启动和新写入；兼容测试只构造临时旧格式副本，不改真实历史。不是 Task 4.3 的完整离线迁移证明。没有测量真实模型 token/费用，不用短 ID 或上下文字节宣称总成本下降。

### 命令与真实结果

以下均为零模型的确定性测试；Hook/MCP 调用是真实 Python 接缝，子会话事件为合成测试输入，不是实际 Codex Subagent/Skill 加载证明。

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_common_stock_semantic_handoff tests.test_common_stock_research_contracts
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_common_stock_semantic_handoff tests.test_common_stock_research_contracts tests.test_skeptic_semantic_handoff tests.test_scoped_research_claims tests.test_independent_skeptic_stage
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_multidimensional_references.ReferenceBoundaryTests.test_short_query_calculate_and_stop_preserve_canonical_report tests.test_multidimensional_references.ReferenceBoundaryTests.test_legacy_packet_keeps_full_id_tool_protocol tests.test_council_semantic_handoff tests.test_native_execution_proof
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_common_stock_semantic_handoff tests.test_common_stock_research_contracts.CommonStockNativeStageTests
openspec validate simplify-research-handoffs-and-acceptance --strict
git diff --check -- product/runtime/common_stock_stage.py product/runtime/codex_hook_recorder.py product/runtime/fixture_mcp.py product/runtime/multidimensional_references.py tests/test_common_stock_semantic_handoff.py tests/test_common_stock_research_contracts.py
```

- 先前普通股集合 **111 tests / OK，32.630s**；关联反证/限定 Claim 消费者集合 **222 tests / OK，70.057s**（含导入复用用例，不代表222个新增用例）；共享八维引用/历史协议及 fixture Council/执行证明子集 **26 tests / OK，5.845s**。这些结果用于未受随后旧入口退役影响的接缝，不包装成最新真实运行。
- 新增退役检查、正例有序计算和捕获绑定后，仅重验受影响普通股集合。最后一次在下列源码快照下 **46 tests / OK，22.037s**；其中普通股语义/引用测试12项，涵盖实际 Start→stdio Query/Calculate→Stop→正式报告→归集、多个合法引用顺序、跨证券/目录/类型/版本、拼接 source/time、未知及原始 ID 新写入、映射重签/降级、原值保真、历史读取和旧入口在进程前拒绝。原有 Memory 保存/重启零模型复用测试也通过。
- 初始6项有1个旧断言失败，初始106项有5个旧接口断言失败：测试仍期待工具返回原始 ID、旧包不含允许集或把原始 ID 写入新草稿。测试改为比较模型短引用和原始审计/正式产物，未放宽闭合规则。一次测试命令用了不存在的 `CommonStockAttachmentDispatchTests` 类，11个有效用例通过、1个加载 ERROR；随后按实际 `CommonStockNativeStageTests` 执行，不将该命令当 PASS。缺计算负例使用合法短 Evidence，仍由原校验准确返回 `EQUITY_RESEARCH_CALCULATION_REFERENCE_DANGLING`，避免先被其它格式错误挡住而形成假覆盖。
- OpenSpec strict valid；已追踪差异检查 exit 0。测试产物位于各测试独立临时目录；本记录保存命令/结果/源码标识，不声称这些临时会话是可发布真实运行包。未运行网络、模型、真实 Smoke/Replay/Eval/Regression/Calibration/Ablation/Promotion/Gate，未归档、提交、推送。

### 最新完整字节快照

仅为本轮工作现场标识，不新增产品版本锁，含共享文件中原有授权修改；提交仍按 hunk 分离。

| 文件 | SHA-256 |
|---|---|
| `product/runtime/common_stock_stage.py` | `7d41e2c7c6b5b32aa08d0031b8221c7afafcaacc003de9202c3d91700d2699ee` |
| `product/runtime/codex_hook_recorder.py` | `ac4897ef579882a05a2f9fd6e8cfd43be71d2572c4cec7d6bc20515a74150499` |
| `product/runtime/fixture_mcp.py` | `b195e160e7ec78737a6c02219e00cb759865ad777aa81594e497f62add7e0a7b` |
| `product/runtime/multidimensional_references.py` | `3861d5c8f5c07a21032fd93bd6b56380936fe2268b1e4db3cceb6e49ee994636` |
| `tests/test_common_stock_semantic_handoff.py` | `302fd5420563e4ddfcc4b49d894560049910f22a4be2fe7e5902cf7376c3dfb3` |
| `tests/test_common_stock_research_contracts.py` | `71c0efb29ff358019c8c0d293a55a05edc5b927e1d9442a80312a3e77496cd65` |

下一步延续同一任务：将既有映射继续接到独立反证及其它当前可写入口，完成 Document/Calculation 选择和限定 Claim 的下游读取，再处理局部修订、历史离线读取、路由/状态及有限收尾。原八维保持暂停；各真实加载/执行缺口汇总到 Task 6.4 一次预算请求，不逐项启动模型。

## 独立反证短 Evidence 接缝（2026-09-30）

对应 Task 3.2 / H02 的独立反证子路径，及 Tasks 3.1、3.5、5.2 的部分交付。大任务仍未覆盖全部入口，保持未勾选；总进度 **11/30**。依据引用任务限定、语义与技术装配分离、精简输入不隐藏研究边界三项规格；本节不是原八维内容验收或候选晋升证据。

- 首轮与恢复沿既有 `_skeptic_packet` 构造器，复用 v2 短引用映射。Index、Task、Invocation 的协议须一致；实际 Start Hook、MCP 和 Stop 使用同一冻结 packet。Model Schema 从原角色业务 Schema 派生，三个 Evidence 选择位置仅允许本任务别名；未扩大工具、证券、事实或报告权限。
- 模型视图去掉完整 Invocation、映射及固定技术字段，保留研究问题、持仓期限、证券、cutoff、模式、资料限制、全部允许引用和原研究结构。Start 记录实际交付字节/hash/map hash；工具仍返回原事实值、source_id/as_of/retrieved_at、期间和单位。审计保存原始 ID/hash，正式报告经短允许集校验、精确转换及原 Validator 保存，研究文字、信心及数组顺序不改写。
- 重新签 packet/index/map hash 不能替换真实绑定；跨角色、证券、run、类型、恢复尝试、拼接来源/时间、未知或原始 ID 的新草稿失败。允许但未实际查询的事实仍不能让 finalizer 判为 DOWNSTREAM_READY。独立首轮没有接收 Analyst 报告、主张或待解决问题。
- 旧完整协议及旧 native 全 ID 协议只读兼容；新写入/启动/恢复明确拒绝。兼容案例是临时构造副本，不改任何历史包或锁，不宣称完整离线包迁移已完成。恢复只换未就绪股票的 Invocation/短映射，成功项的原 Invocation、报告和先前包字节不变。
- 修复本轮发现的实际路由缺陷：反证父阶段仍须复核上游计算，不能按父阶段把上游 Invocation 误路由到 Skeptic。共享 loader 先精确匹配反证任务；非反证 Invocation 沿原上游索引校验，未知/歧义仍失败，模型未因此取得上游报告查询权限。

### 实际执行与结果

全部为零模型确定性接缝，实际执行 Python Hook / MCP stdio / finalizer；会话事件是合成测试输入，不是实际 Codex Subagent 或 Skill 加载证明。

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_skeptic_semantic_handoff tests.test_independent_skeptic_stage.IndependentSkepticContractTests tests.test_common_stock_semantic_handoff tests.test_common_stock_research_contracts.CommonStockNativeStageTests
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_multidimensional_references.ReferenceBoundaryTests.test_short_query_calculate_and_stop_preserve_canonical_report tests.test_multidimensional_references.ReferenceBoundaryTests.test_legacy_packet_keeps_full_id_tool_protocol tests.test_scoped_research_claims.ScopedResearchClaimTests tests.test_predecision_cio_stage.PredecisionCioPreparationTests
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_skeptic_semantic_handoff.SkepticSemanticHandoffTests.test_actual_hooks_query_formal_report_package_and_reader_preserve_semantics tests.test_skeptic_semantic_handoff.SkepticSemanticHandoffTests.test_synthetic_previous_native_packet_stays_read_only_and_byte_stable
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_skeptic_semantic_handoff.SkepticSemanticHandoffTests.test_multiple_selected_short_refs_preserve_order_and_research_text
openspec validate simplify-research-handoffs-and-acceptance --strict
git diff --check
```

- 受影响集合 **71 tests / OK，52.606s**，包含反证17项、恢复/权限8项、普通股短引用12项及原普通股34项；共享引用和限定 Claim/CIO 消费者 **30 tests / OK，1.448s**。后续仅增加交付字节/hash断言和多引用保序正例（产品源码未改），分别 **2 tests / OK，2.096s**、**1 test / OK，0.838s**。不是全量 Gate 或真实 Runtime Eval。
- 初始反证11项出现18个 ERROR（含子案例）：共享 loader 以父阶段选错 Invocation 索引；按真实归属修复后11项通过。原反证8项有2个旧断言 FAIL：仍将模型短 ID/视图 hash 当成原始 ID/审计 hash。改为分别断言模型视图与精确还原的原始审计，未放宽权限、闭合或 hash 验证。
- OpenSpec strict valid；当时已追踪 `git diff --check` exit 0。测试运行产物位于各自独立临时目录，并随测试清理；不把它们包装为可发布真实运行包。所有源文件快照如下，仅记录现场，不新增候选锁。

| 文件 | SHA-256 |
|---|---|
| `product/runtime/independent_skeptic_stage.py` | `c120fff1560bfadca24bfa409084db1d850f14e86c7116492e7f34d737a11947` |
| `product/runtime/multidimensional_references.py` | `ae2c42b2bc468eb00c383ccd4f8a008bd574d5e8470e69a4bdc8308b2ea925d6` |
| `product/runtime/common_stock_stage.py` | `c931c9700374f9ba22f19e105e24ebf4470fe1249fef19b771c56f75ef47fe6a` |
| `product/runtime/fixture_mcp.py` | `30431c8404546139ffc8fbc4f559c985cfa41dd58b3ea57140fe61fc7304e179` |
| `product/runtime/codex_hook_recorder.py` | `b865106621f56ea8bc1b2cef8ed742a7c7467d7be8e17db18a624e34ee120e32` |
| `tests/test_skeptic_semantic_handoff.py` | `ad189029a215963a2e9c3fee60684306fe49ae359469215a17b527a447423639` |
| `tests/test_independent_skeptic_stage.py` | `5dc279788b36c3beb7eef9481d21c0627283335d369b085789c09825d9ba7273` |

真实运行为 **NOT_RUN**；新 Start 交付及工具视图涉及的最小真实 Smoke 缺口归并 Task 6.4，未批准不启动。Calculation/Document/限定 Claim 全入口迁移、一次局部补丁及历史离线/路由/状态等剩余要求仍按原 Tasks 推进，不因本子路径通过勾选整体完成。没有启动模型、网络、真实 Smoke/Replay/Eval/Regression/Calibration/Ablation/Promotion/Gate，没有归档、提交、推送；原八维保持暂停。

## 普通股成功计算选择与附件传递（2026-09-30）

推进 Tasks 3.1–3.3 的普通股接缝，复用已有 `calculation_handoff`、收据/事件及正式报告 Validator，不新增 Agent、Schema 平台或编排器。总任务进度仍为 **11/30**；本节不证明所有角色已经迁移，也不替代真实模型验收。

- 新 prepare 明确绑定 Run/Task/Invocation 的 `research-calculation-selections/1.0.0` 和本任务计算账本。实际 Start 的草稿 Schema 去掉 `claim.calculation_refs`，要求 `calculation_selections=[{calculation_ref,claim_ids}]`。模型只选成功结果及关联主张，不再填写计算 ID、记录、文件路径或输入血缘。原正式报告格式不变；研究文本、假设、置信度和条件保持原样。
- MCP 先保存原始成功事件/收据，再返回内容与任务绑定的 `k.*`。数值和有序输入保持；新调用不会重编号已有引用。账本、事件、输入顺序、输出 hash、任务/权限须闭合；失败计算、未知/跨类型/跨任务/跨目录引用、虚构主张、重复或混合填写失败。`run_id` 仍作为 stdio 审计所需字段保留，尚未把技术工具包装全部精简的 Task 5.2 宣称完成。
- 冻结附件仍由原 package Validator 准入。实际附件查询只转换计算身份字段，原值、单位、来源、期间、时间、公式及 `value/metadata` 内同名键不变；原审计与模型交付 hash 分开。未实际读取的附件计算在原正式引用校验中拒绝；合法查询→选择→Stop 保存→finalizer→中文报告实际跑通，附件字节/hash 不回写。
- 新协议加入研究输入 fingerprint，避免旧格式报告被误当成相同输入的当前结果。旧全 ID 和旧短 Evidence/完整计算格式均可按原算法只读验证，启动/新写入明确退役。兼容测试仅在临时目录构造旧格式，未修改真实历史数据或版本锁。未知协议、删除 flag 及错账本路径，即使重签外围摘要仍拒绝。
- 生成 Prompt 的当前分支已改为选择式说明，历史分支字符串保持原样。稳定 Agent/Skill 的旧计算转录说明须在 Task 6.1 与批准资源镜像一并处理，不能仅凭此动态 Prompt 宣称指令全集已一致。其它入口的完整短引用及下游贯通也仍由原 Tasks 承接。

### 实际命令与结果

全部为零 LLM 的 Python Hook/MCP/finalizer 确定性接缝，生命周期事件是合成输入，不是实际 Codex Subagent/Skill 加载证明。

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_common_stock_semantic_handoff tests.test_common_stock_research_contracts.CommonStockNativeStageTests
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_common_stock_semantic_handoff tests.test_calculation_handoff tests.test_common_stock_research_contracts
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_skeptic_semantic_handoff tests.test_independent_skeptic_stage tests.test_multidimensional_references tests.test_scoped_research_claims tests.test_research_submission tests.test_server_calculation_ids
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_common_stock_semantic_handoff.CommonStockSemanticHandoffTests.test_old_short_evidence_packet_is_readable_but_cannot_bypass_calculation_migration tests.test_common_stock_semantic_handoff.CommonStockSemanticHandoffTests.test_old_full_reference_package_is_readable_but_new_execution_and_write_are_retired tests.test_common_stock_semantic_handoff.CommonStockSemanticHandoffTests.test_calculation_selection_schema_and_results_do_not_require_mechanical_fields
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_common_stock_semantic_handoff
openspec validate simplify-research-handoffs-and-acceptance --strict
git diff --check -- product/runtime/calculation_handoff.py product/runtime/common_stock_stage.py product/runtime/codex_hook_recorder.py product/runtime/fixture_mcp.py tests/test_common_stock_semantic_handoff.py tests/test_common_stock_research_contracts.py
```

依次：**50 tests / OK，26.429s**（新增附件用例前）；**134 tests / OK，42.553s**；**177 tests / OK，69.874s**；**3 tests / OK，1.616s**（增加旧短 Evidence 兼容及指令断言）；**20 tests / OK，15.316s**（最后新增重签协议/账本负例后）。后两轮仅修改测试，产品源码与 134/177 集合一致。strict valid；已追踪相关差异检查 exit 0。

初次 12 项测试曾有 1 FAIL：移除工具输出 `run_id` 破坏原 transport 审计；恢复该必要字段后通过。附件聚焦 2 项初次有 1 FAIL：测试期待后置交付错误，但原正式 Schema 更早以 `EQUITY_RESEARCH_CALCULATION_REFERENCE_DANGLING` 拒绝未读计算；改为断言实际原安全边界，没有改产品校验顺序或放宽闭合。临时测试产物按用例清理，不包装为真实运行包。

### 完整字节快照（非产品版本锁）

| 文件 | SHA-256 |
|---|---|
| `product/runtime/calculation_handoff.py` | `360f91e7aa125371621fd6fc0bf71dc962ea02393c734788f335faf094ea383e` |
| `product/runtime/common_stock_stage.py` | `97ea7f001516a4525a6fa6e33b3540593e1d71ffa63797b0f8b902486855fcc4` |
| `product/runtime/codex_hook_recorder.py` | `98f2a59bcc4a2d83ff3abb076aeb086d4ac1ed64f22e60a3b4169284d2b560da` |
| `product/runtime/fixture_mcp.py` | `427a24f50ca705d8016bd675961f52690b6dbf220087db882294958c841438ab` |
| `tests/test_common_stock_semantic_handoff.py` | `ea8e2fdc2d3603f372b2ea530fdbb6dfe0b1d80ad35377785810fefc01528240` |
| `tests/test_common_stock_research_contracts.py` | `bdaa5c443fa92738472dd6497439fd8a0909e3c75fe929aaa6596cf2787899a0` |

共享文件仍含其它授权修改，快照不是全部 hunk 可提交的声明。真实运行继续 **NOT_RUN**，缺口并入 Task 6.4；没有模型、网络探针、Smoke、真实 Replay/Eval/Regression/Gate、归档、提交或推送。原八维继续暂停。

## 两类 CIO 的任务限定引用交接（2026-09-30）

对应 Tasks **3.1、3.2、3.5、5.2 的 CIO 子路径**及 H02/H09，复用既有 `cio_handoff`、共享引用映射、Invocation、MCP、最终装配和 Risk，不新增 Agent 或编排器。规格依据：“当前语义草稿必须区分模型判断和技术装配”“引用选择必须任务限定且不可模糊修复”“材料CIO及Eval的审计必须来自真实记录”“精简输入不得隐藏研究边界”。这些大任务仍有其它入口/交付要求未关闭，继续未勾选；总进度仍为 **11/30**。

### 本轮实际交接

- `predecision_cio_stage` 与 fixture Council 的模型 Schema、上下文、报告读取和 Evidence 查询使用同一任务限定 `e.*` / `p.*` 映射。报告选择绑定完整冻结目录（含文件/内容 hash），Evidence 选择绑定本次 Gate 与 Invocation；报告内本地 `claim_id` / `challenge_id` 不猜测改写。
- fixture 准备器保存原始权威 `inputs/runtime_cio.json`，另机械派生 `inputs/runtime_cio.model.json`：保留研究问题、截止点、组合计算值、机械冲突及获准报告角色，移除无需填写的目录路径/报告 hash。主线程的产品/消融生成指令使用新模型视图，原始技术包仍在运行层；实际工具与 finalizer 重建并核对模型视图，篡改即失败。
- Schema 准备和正式 Invocation 共用原身份算法，不以包含 Schema hash 的完整 Invocation 递归生成引用。带新协议的 Invocation 必须与原输入导出的身份一致，重签摘要不能替换运行身份或协议。
- 实际 `read_reports` 先核验原报告字节/权限，再返回短引用视图；服务端保留原始 ID 的读取事件及 canonical 输出 hash，stdio 另记录实际交付视图的 hash/字节数。Evidence 查询仍交付原值、来源、时间；`value`、`metadata` 和中文正文中的同名键/引用文字不被递归替换。
- 模型草稿先受本任务 enum 与原动作 Schema 约束，再精确还原原始 ID；正式报告、中文输出及原 Risk 继续消费原始引用。未读报告、遗漏必需读取、悬空/跨类型/跨运行/拼接 source 或时间的选择均拒绝；不静默截断。报告角色子集约束没有扩成整个目录。
- 独立 CIO 的 Trace checker 重算原稿到正式综合结果及读取证明，记录 `reference_map_hash` / `semantic_output_hash`，仍为非动作 `RESEARCH_SYNTHESIS` / `risk_status=NOT_RUN`。fixture 的实际最终装配测试到达原 Risk，保留通过、要求修订及否决边界。
- 新协议绑定原资源检查，独立 CIO 额外锁定共享引用代码/哈希代码；旧无短引用协议的临时测试包可只读验证，启动/新写入明确退役，历史包不升级或回填。此处只证明当前读取器在资源仍匹配时的旧格式兼容，**不是 Task 4.3 的历史离线搬迁/当前资源升级验收**。

### 聚焦命令与结果

统一使用既有隔离测试环境，不安装依赖，不启动 `codex exec`：

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_cio_handoff tests.test_cio_reference_handoff tests.test_predecision_cio_stage tests.test_native_run_package tests.test_council_semantic_handoff tests.test_native_invocation_validation tests.test_live_cio_final_response
```

最新最终快照下：**86 tests / OK，15.470s**。覆盖真实准备器、MCP stdio、草稿装配、Risk、Trace 和中文报告消费；模型结果/生命周期输入及独立 CIO 的上游包为测试合成数据。测试打印的 `NATIVE_EXECUTION_PROOF_FAILED` 与 `RUNTIME_DEPENDENCY_MISSING` 是原负向案例的预期产物，不代表有实际模型执行。

在补充最后一条“重签 Invocation 不能冒用身份”检查之前，还执行了共享引用的受影响集合：

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_cio_handoff tests.test_cio_reference_handoff tests.test_predecision_cio_stage tests.test_native_run_package tests.test_council_semantic_handoff tests.test_native_invocation_validation tests.test_runtime_ablation tests.test_live_cio_final_response tests.test_multidimensional_references tests.test_server_calculation_ids tests.test_skeptic_semantic_handoff tests.test_common_stock_semantic_handoff
```

实际结果 **154 tests / OK，97.464s**。该集合运行期间追加了仅作用于 native CIO 的身份校验及其测试，所以不宣称整组绑定到最终同一源码快照：CIO/Invocation 受影响部分以上述最终 86 项结果为准；共享引用、普通股、反证、计算返回的未改动路径可复用该组结果。此处的 `test_runtime_ablation` 是确定性测试模块，**没有执行真实 Ablation**。先前 CIO/消融关联集合另有 **95 tests / OK，43.462s**，仅作未受后续身份校验影响的拓扑/schema接缝证据。

过程发现并修正：旧测试仍期待原始 ID（改用真实映射并检查正式产物还原）；报告读取遗漏哈希函数导入；临时旧包测试使用错 hash 字段；新增测试调用 Prompt 构造器参数错误。未修改 Evidence Closure、Schema 枚举或 Risk 以让负例通过。修正后上述最终集合无断言失败。

- `openspec validate simplify-research-handoffs-and-acceptance --strict`：通过。
- `git diff --check`：通过。
- 真实模型/加载/研究内容补验：**NOT_RUN**，合并到 Task 6.4 的预算与入口清单；不复用原八维授权。

### 最终完整文件字节快照

以下为本轮复核定位，不是新增产品版本锁或候选晋升依据；共享文件仍含既有授权工作，不表示全部 hunk 可提交。

| 文件 | SHA-256 |
| --- | --- |
| `product/runtime/cio_handoff.py` | `6451aa9d47c20629aa53fbb5bdc8d75b8c0e2e6d4eb07ec5e192afddf5bfbb5c` |
| `product/runtime/multidimensional_references.py` | `4866330182148b5422db37c334bbcf60a806247e7a6a9045feb45050861b5fa9` |
| `product/runtime/predecision_cio_stage.py` | `08eb4e67e54dc520876d0e665ee6798b301f6e11f1a00f26dbd72d5f477463b1` |
| `product/runtime/fixture_mcp.py` | `3e0e108926105cec38c49c1f87d2ff3743e862e0340bcef3c007d37fa415d9cc` |
| `product/runtime/invocation.py` | `d3c5e898d21ddd92021f5d38e394a10def24100044042ed21b4a1fe6583644a0` |
| `product/runtime/run_package.py` | `1f52df89e94ad137dca4d0780b096b343472e14dd77ed8a0ee6017e0906a52ef` |
| `product/runtime/smoke_prompt.py` | `8feb5fccf5b9bfc1bcb26f03e78da9e08f5d9d9741929877175ca5d1fd5c034b` |
| `product/runtime/nested_codex.py` | `052a38e2ad52c72d5b5aad3a22ddbbd5a237ca05608c682b611ba91ed62ce8c1` |
| `tests/test_cio_handoff.py` | `e7f48acaf599efaeda6b48e2c321da791060fd2c0bfe1416f4643778a8a042f1` |
| `tests/test_cio_reference_handoff.py` | `9d76f06fbd699753e87237cab18f5ef0031172bc670ebc87fec4d3774383d6ff` |
| `tests/test_predecision_cio_stage.py` | `886c507d05c595a1980bc4606864627bd951b4a7f1197bc06abbe60f46256c06` |
| `tests/test_native_run_package.py` | `753adda898deeb9d3e2132cc47635c20525f4b5f8bf726470aa56aaf61bc4778` |

本轮没有模型、网络探针、Smoke、真实 Replay/Eval/Regression/Calibration/Ablation/Promotion/Gate、归档、提交或推送。原八维继续暂停，未改其任务状态或内容标准。仍需完成其它角色的统一交接/精简输入、历史离线读取、局部修订、coverage/状态投影及既定独立复核/人工批准；本节不宣称 Change 已完成。

## 原 Agent 的有界对象修订（2026-09-30，Task 5.1 部分推进）

### 已落实的接缝

- `local_revision.py` 只执行作者明确提交的字段操作。沿原 Hook/两次尝试边界，以可信派发/Start 的父会话、子会话、Agent、Model、任务和 Invocation 绑定首稿；不增加 Agent、调度器或重试额度。
- 对已定位的八维直接对象错误及独立反证 Schema 错误，先保存首稿，再生成不可覆盖的约束包。约束包保存完整身份、原稿 hash、允许路径和绑定 hash；模型只收到 `base_draft_ref`、允许路径和定位信息，不再收到这份包的路径/hash、整份原稿及重复 Schema。
- 模型可返回 `base_draft_ref + changes`。范围外字段、错误基础稿引用、技术身份修改、重叠路径和未经允许的数组插入被拒绝。数组修改使用原稿索引，先修改字段、最后按索引倒序删除，不能通过移动位置改到另一主张。被定位的错误主张/观察条件可由原作者修改或删除，其它对象保持；程序不选择 Evidence 或补写结论。
- 保留既有完整对象传输兼容，但绝非无约束整稿替换：服务端绑定同一首稿，计算精确差异并验证范围外字段不变；记录 `FULL_OBJECT_COMPATIBILITY`，新反馈优先要求 `NATIVE_PATCH`。类型、数值、否定语句及单位均按原内容比较，不模糊匹配引用。
- 第二稿组装后继续经过原 Schema、身份、Evidence、依赖关系、计算及事件校验；局部修改合法但引用仍悬空时，报告仍失败。第二次失败不产生第三次纠正机会。首稿及第二份已授权提交（包括非法补丁）均保留原文；未授权身份/模型在原稿写入前拒绝，不占用原 Agent 额度。原稿保存同时拒绝符号链接越界。
- 独立反证接缝实际执行 stdio query、Start/Stop Hook、补丁解析、正式报告保存及现有 `finalize_skeptic_phase`；原研究字段、反证、信心理由、引用选择和中文内容与作者目标稿逐字段一致。

### 实际检查与适用范围

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_local_revision tests.test_multidimensional_stage tests.test_independent_skeptic_stage tests.test_research_submission tests.test_strict_schema_validation
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_local_revision tests.test_skeptic_semantic_handoff
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_local_revision tests.test_skeptic_semantic_handoff tests.test_multidimensional_stage tests.test_research_submission tests.test_strict_schema_validation
git diff --check
openspec validate simplify-research-handoffs-and-acceptance --strict
```

- 第一组 **233 tests / OK，52.202s**：在增加最终原文保留/路径保护检查之前，覆盖既有八维、研报提交和独立反证阶段逻辑；不是最新整树测试证明。
- 第二组 **34 tests / OK，33.112s**：包含新独立反证真实归集接缝；随后更新原文保存顺序及目录防越界，受影响用例由第三组重新执行覆盖。
- 第三组是本节最终源码快照：**164 tests / OK，62.510s**。覆盖基础稿/约束包篡改、合法局部修订、完整对象绕过尝试、其它字段被修改、错误模型不占额度、第二次悬空关系失败、第三次拒绝、实际正式报告和下游反证包读取。测试事件模拟 Agent 生命周期，未调用模型；测试数不代表真实 LLM 用例或研究质量。
- Strict validate 通过，`git diff --check` exit 0。中间检查暴露 helper 调用错误（共享 hash API 的关键字参数）、技术字段诊断误入允许路径、旧测试仍要求重复 Schema/整稿、以及数组删除后移位问题，均在本节实现/测试内修正；没有放宽 Evidence/PIT/Risk 或替作者选择引用。

### 尚未关闭的 Task 5.1 范围

1. MCP `research_report_submit` 的对象在专用提交文件中，不能把 Stop 的短回执当作研究基础稿。本轮未将该入口冒充为已完成的局部修订；仍需绑定真正提交对象、约束第二份对象，并处理已授权但预存稿校验失败的次数记录。
2. 非法 JSON 仍沿原有解析器定位/两次尝试反馈；本轮不自动推断缺失语法，也未证明此分支的其它语义字段不变。它与可解析对象的局部修订证明分开，不能据此勾选整个 H11。
3. 普通股、CIO、资料准备和 Eval 未凭本节测试宣称新增统一修订入口；其已有业务/权限与历史读取界面不被替换。新执行协议/版本锁及完整 H01–H19 关闭矩阵继续由对应未完成任务核对。

Task 5.1 保持未完成；其余任务状态未变。没有真实模型、网络探针、Smoke、Replay/Eval/Regression/Calibration/Ablation/Promotion/Gate、归档、提交或推送，未修改原八维的任务状态、历史包或预算。

本节完整文件字节快照（含共享文件其它已授权修改，不是产品锁）：

| 文件 | SHA-256 |
| --- | --- |
| `product/runtime/local_revision.py` | `e9b0894c6d174f55c02d00e7bc92af9fcaef60edabf4340ae584489cc5794752` |
| `product/runtime/codex_hook_recorder.py` | `521f4d70e2126c5d1961d0ba3ae4af07558356e3ae1aa149ae1ca7f58ce1720d` |
| `product/runtime/schema_validation.py` | `79767c0558210ed59d7a0f56083c51f6cf8a7ce6f7b0c5d3fe271c4dc189986b` |
| `tests/test_local_revision.py` | `71a00d9b7615ab5a1911c7a50ba39e908226a39fd125100abbfd394f84e10765` |
| `tests/test_multidimensional_stage.py` | `8002bdaea9cc41fe80f41889fabd30f66c25b4d022c868032ebef2c2d720fe2b` |
| `tests/test_skeptic_semantic_handoff.py` | `4fb692df3ac6b6727bdea740d52ba4ca9af2eef0bd0e35369edc9e9fbd87a0d3` |



## 研报 MCP 有界修订与任一维度首次定点入口（2026-09-30，Task 5.1 / 5.3 部分推进）

### 实现与验证范围

本节继续当前 Change，不创建新 Agent 或编排器。原八维仍暂停；没有修改其历史运行包、任务状态、最低内容标准或预算。下面的模拟生命周期与进程只证明程序接缝，**真实模型运行、加载效果、研究质量及候选晋升均 NOT_RUN**。

| 对应规格 / Task | 本轮实际实现 | 程序证据与限制 |
| --- | --- | --- |
| 原 Agent 局部纠正 / 5.1，精确回执 / 2.2 | 新准备的结构化研报任务采用 `research-object-submission/6.0.0`，沿原 MCP 工具和 Stop 保存边界运行。首稿无效也保存并占用额度；第二稿用 `base_draft_ref + changes`，不是整稿重写 | 实际 stdio 工具结果与事件、私有不可覆盖草稿、真实 Hook 代码及正式报告；会话事件由测试构造，不是模型执行证明 |
| 局部范围及完整再验 / 5.1 | 基础稿 hash、packet、原提交事件与允许路径绑定；第二稿保持范围外字段，保留作者原补丁和组装后的稿件，继续原完整校验 | 正确修订保存；整稿替换、错基础稿、范围外修改作为第二份已授权无效稿保存且耗尽额度；第三次拒绝。错误凭据、损坏约束包和不可信 Stop 不进入接受或宽松修订 |
| 定位错误与安全边界 / 5.1、2.6 | Schema 诊断与正式输入使用同一派生结构；错误过多或反馈过大则有界失败，不自动猜字段；补丁并发使用单一剩余槽位 | 文档误选、悬空观察条件、重新签名的稿件、缺失/非法实际事件、事件父目录符号链接、约束包重签与并发负例均按预期拒绝 |
| 研究语义保留 / 3.5、5.2 的本次研报接缝 | 复用原 citation/source/monetary 辅助检查，不把辅助检查当接受证明；作者自己选择文档和关系句 | 非空主张的否定/限定原句、关系句及对应报告版本引用经过 stdio→Stop→正式报告→`finalize_multidimensional_task_evidence` 后一致；不证明观点质量合格或所有角色已贯通 |
| 最小依赖闭包 / 5.3 | 复用 `--start-multidimensional-task` 和既有 launcher：八个已配置维度均可首次定点运行；Company 保留既有有界目录，其它维度沿完整模型视图，不新删资料 | 模拟进程运行八种选择：研报为基本面→研报两任务，其它七种各一任务；实际派发、Start 注入、Stop 保存及 Finalizer 只覆盖所选闭包 |
| 无隐式其它任务 / 5.3 | 缺依赖、循环、重复名字/ID、非法依赖类型、跨 run 的重签索引及当前 Agent/Skill 漂移在进程前拒绝；同一已启动目录不能再次首次启动 | 未启动维度明确列在 `not_run_task_names`，不生成完整研究 bundle，不冒称 8/8；宿主脚本分流测试使用命令替身，不实际调用 Codex |

### 实际命令与结果

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_bounded_research_submission tests.test_targeted_research_closure tests.test_research_submission tests.test_local_revision tests.test_skeptic_semantic_handoff tests.test_multidimensional_stage tests.test_strict_schema_validation tests.test_calculation_handoff tests.test_host_proxy_scripts.HostProxyTests.test_initial_targeted_host_entry_routes_to_existing_launcher
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_bounded_research_submission.BoundedResearchSubmissionTests.test_nonempty_relation_keeps_authored_qualifiers_through_stop_and_finalizer tests.test_bounded_research_submission.BoundedResearchSubmissionTests.test_revision_deleting_claim_is_still_checked_for_dangling_conditions
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_bounded_research_submission tests.test_targeted_research_closure
openspec validate simplify-research-handoffs-and-acceptance --strict
git diff --check
```

- 第一组 **206 tests / OK，74.664s**，对应本节最终产品实现。随后只补充一个非空关系测试并去除另一个测试草稿中旧式 `calculation_refs`，没有再改产品实现。
- 第二组 **2 tests / OK，0.605s**，覆盖上述最后两处测试调整；不与第一组相加冒称不同用例总数。
- 第三组是最后测试文件快照的聚焦重验：**26 tests / OK，8.682s**，覆盖本轮研报提交和八种维度选择。不以旧空报告正例代替非空主张证明。
- Strict validate 通过，`git diff --check` exit 0。
- 测试输入来自 `test_research_submission`、`test_multidimensional_stage` 的合成 handoff/Gate/冻结依赖，没有发送真实持仓。临时输出为各用例自建并清理的 run 目录，包含 `research/submissions/*/1.json`、`2.json`、`1.repair.json`、`accepted.json`、`events/mcp/events.jsonl`、`invocation/subagent-events.jsonl`、正式维度报告和定点 proof；不是持久保存的真实 LLM 验收包。

中间失败保留分类：缺少提交事件时原拒绝已发生，但反馈生成再次抛异常，现已保持原失败码且不开放修订；一项旧断言固定英文工具描述，在说明改中文后失败，现检查协议标识并继续保留服务端授权负例；另一次汇总命令误写不存在的 `HostProxyScriptTests`，是测试选择错误，不是产品断言失败，正确 `HostProxyTests` 用例及第一组已通过。没有放宽 Evidence/PIT/Risk。

### 仍未关闭的范围

1. Task 5.1 的已解析对象/MCP 接缝已有上述证据，但非法 JSON 文本仍不能凭本节证明语义字段不变；普通股、材料、CIO、Eval 的修订边界也不能自动继承本节结果。保持 Task 5.1 未完成。
2. Task 5.3 的任一维度首次闭包已实现，但新调试 `run_id` 的唯一生成/重复检测，以及恢复或复用输入时方法、工具、Schema、Model 等完整版本适用性仍须核对。现有首次目录防重复和 Agent/Skill 检查不冒充完整版本证明，保持 Task 5.3 未完成。
3. `WRITE_VERSIONS` 仍有 v3/v4/v5 写入分支，不能将它们称为已经退役的历史只读。当前 prepare 默认 v6，不代表 Task 3.1 所要求的全部入口和新旧写入边界已经完成；旧协议测试只在其实际覆盖范围复用。
4. 本节不证明全部角色输入精简、历史离线读取、coverage/状态统一或 H01–H19 整体关闭。后续真实补验只按 Task 6.4 一次合并预算供人工批准，不复用原八维额度。

任务计数仍为 **11/30**，未提前勾选部分实施的任务。未归档、提交或推送；共享文件已有其它授权修改，以下 hash 只用于定位本次证据适用的完整文件字节，不是产品新锁或可整文件暂存的批准。

| 文件 | SHA-256 |
| --- | --- |
| `product/runtime/research_submission.py` | `62ba60bbfc27c702b09c43b0fe3f4770e91e77313e7073309d0289986603993b` |
| `product/runtime/calculation_handoff.py` | `36a678e6eec364d58490d3b032dba9940071b8935a681ca0944e8a8fd4cc1557` |
| `product/runtime/codex_hook_recorder.py` | `2e455c7d8cf9c03362e537be495689ad18bb4f0024ab62dd0f485bd8a9e3418c` |
| `product/runtime/multidimensional_stage.py` | `471926871fbaddd020134d7076e0cddf12015b652072e560d17c6f1f34c3beae` |
| `product/runtime/fixture_mcp.py` | `651a33ae5a6ceeeb05091eab1f3233c3247a5942032a6339148fd465021ddb00` |
| `tests/test_bounded_research_submission.py` | `d4d9379ddd0efbd4f661392b427986e8b6018fade6ba9daead74b6155e51f313` |
| `tests/test_targeted_research_closure.py` | `a3d8a0342a9555b8fc23500c14f8522888f73902c27c727e58bbaae7747fff20` |
| `tests/test_research_submission.py` | `a680401c886824c92a1a87fbb069c0842b5361bd14c073db224fbd4de956e62e` |
| `tests/test_multidimensional_stage.py` | `b377918760765194f4193afc9f6fb798094ca6d1cc91b2e492532cb06ed94366` |

## 当前写入与历史读取的实际退役边界（2026-09-30，Task 3.1 / H01、H08 子路径）

本节承接上一节仍未关闭项第3条：**研报 v3/v4/v5 写入已经实际删除**，不修改原历史记录，不把旧测试结果追认成当前 v6 的运行证明。资料准备也补齐旧协议的执行/写入拒绝。相关整体 Tasks 3.1、4.3、5.1 仍未勾选；总进度仍为 **11/30**。

### 实现及生产者—消费者映射

| 规格 / Task | 本轮实际变化 | 正负接缝 |
| --- | --- | --- |
| 当前语义草稿 / 3.1 | `research_submission` 分开 `READ_VERSIONS`、`ASSEMBLY_VERSIONS` 与仅允许 v6 的 `WRITE_VERSIONS`；删除 v3–v5 写入代码 | v1–v5 逐版直接调用，即使合法 bearer 也拒绝；无提交目录/新槽位/进程状态。历史 resolve 不改原字节；篡改仍拒绝 |
| 字段职责与实际交付 / 3.1 | 工具目录只向当前写入协议公开提交工具；旧上下文明确只读、无工具/提交凭据；全批/首次定点/恢复启动均检查当前协议 | 实际 stdio 的旧工具调用为 UNKNOWN_TOOL；混合新旧任务索引中即使工具可见也不能写旧任务 |
| 当前选择契约 / 3.1、3.3 | `require_write_protocol` 被提交、上下文与 launcher 共用；v6 不能删除/换掉选择协议而退回抄 calculations/document metadata | 重新签名包装但降级选择协议的负例仍拒绝，不产生状态；当前真实 MCP 选择、正式报告和下游计算重验通过 |
| 结构先于血缘 / 2.1、2.6 | v6 预检查直接用 `semantic_selection_draft_schema`，与交付端共享纯结构，不为取得 Schema 先生成上下文、读取计算目录 | 实际 stdio 提交缺字段时，不读计算目录且保存准确字段反馈；结构合法但计算完整性损坏仍失败关闭、不可获得语义修订许可 |
| 资料准备当前写入 / 3.1、3.4 | launcher 核对 index/packet/invocation 的语义协议；Stop 拒绝无当前标记的旧完整输出，当前草稿仍用真实工具审计装配 | 三个位置分别退回旧标记时都在进程/目录创建前拒绝；旧正式结果只读校验保持，旧 Stop 不保存新结果 |

框架、金融判断、来源权限、PIT/Risk、模型路由与历史锁没有扩建或调整。提交权限检查先于读取研究依赖：旧任务不会因缺基本面依赖而把退役原因误报成依赖缺失；当前任务错误凭据也不先读依赖或消耗额度。

### 历史测试与当前测试不混用

- `tests/historical_submission_fixture.py` 仅在测试临时目录构造旧存档格式，保留旧装配/辅助检查测试向量。只有测试模块引用它，产品目录没有导入；不恢复生产写入，不 monkeypatch 生产准入集合。
- v3–v5 的构造回执及内存辅助事件是**合成历史读取夹具**，不是当前 MCP、新模型或真实历史执行证明；原版 Hook/正式报告/accepted marker 的兼容检查继续执行。
- 涉及当前凭据、实际 stdio、研究报告选择、成功上游计算的测试改用 v6；测试作者显式提供原生选择字段，不由产品代码静默修旧草稿。
- 当前首次提交/唯一局部修订、真实工具事件及可信 Stop 边界继续由 `test_bounded_research_submission` 验证。本文的可信生命周期均为测试输入，不代表真实 Codex Subagent 已运行。

### 实际命令及结果

```text
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_submission_protocol_admission tests.test_research_submission tests.test_bounded_research_submission tests.test_targeted_research_closure tests.test_material_semantic_handoff tests.test_research_materials_stage tests.test_multidimensional_stage tests.test_multidimensional_references tests.test_calculation_handoff tests.test_local_revision tests.test_skeptic_semantic_handoff tests.test_strict_schema_validation
openspec validate simplify-research-handoffs-and-acceptance --strict
git diff --check
```

最终受影响集合 **267 tests / OK，96.107s**；不是全仓测试、真实产品调用或 Release Gate。Strict validate 通过；diff check exit0。合成输入/输出位于各测试独立临时目录并按用例清理，包括提交槽位、MCP/Hook 事件、正式报告与读取校验；没有持久真实研究验收包，不发送真实持仓。

中间失败未被隐藏：
1. 旧回执断言仍把短引用当 JSON；迁移后按真实 raw 文件的短引用及结尾换行验证。
2. 直接工具测试未保存实际返回事件，第二次请求按新边界报 EVENT_MISSING；改由现有事件写入器保存真实工具返回，没有伪造或放宽事件要求。
3. 超长材料上下文测试原 mock 仅有 instruction、没有真实 task；改用实际生产者 packet，仅修改超长 instruction，保留先查协议再查长度。
4. 一组264项受影响检查曾有两个 FAIL subtest、一个 ERROR，均涉及旧计算测试仍调用退役 v5；迁移同时发现 v6 的 Schema 预检查错误读取计算目录。修复该真实顺序问题后追加实际 stdio 的正负例，最终267项通过，不将初次失败冒称通过。

### 未覆盖与停止边界

- 本轮仅关闭研报提交与资料准备的上述退役子路径。非 MCP 八维提交中的旧完整 calculations 草稿兼容分支，以及 `prepare-multidimensional --stage INDEPENDENT_COUNTER_THESIS_RESEARCH` 的旧运输入口，仍须与当前写入/独立 Skeptic 契约逐项核对，不改称已经退役的历史路径；Task 3.1 不提前完成。
- 完整冻结包离线读取/当前执行准入、全角色短引用/计算消费者、分层状态/路由及 H01–H19 总关闭证明仍由对应未完成任务承接。本节不替代 Task4.3 的离线移动/资源升级证明。
- 普通股、CIO、材料、Eval 的有界修订及唯一 run_id/完整输入版本检查没有凭本节自动完成。
- 真实模型/Smoke/Replay/Eval/Regression/Calibration/Ablation/Promotion/Gate 保持 **NOT_RUN**；Task6.4 一次合并新预算获批前不启动。原八维继续暂停，不改其任务、历史产物或预算。未归档、提交或推送。

以下完整文件 hash 由本机摘要命令取得并直接装配记录，定位最终267项检查的源码/测试快照；共享文件含其他已有授权修改，不表示整文件可暂存或整个候选晋升。

| 文件 | SHA-256 |
| --- | --- |
| `product/runtime/research_submission.py` | `50e11f500bfafefe70ba095cce3a54ef710fcaf9e065ad0288cc2317fc34ffd4` |
| `product/runtime/multidimensional_stage.py` | `c7991d7d8e8393211b279056f4cf5673562bb781a618c0ca76011af80586d0db` |
| `product/runtime/research_materials_stage.py` | `253161ac4032ab3762573e683d3f6b3f99fcaf84f86b660113dc8eefd1c56263` |
| `product/runtime/codex_hook_recorder.py` | `d9ca609fe5c8cbf7b4371580c2e3118902d7cdfacaa91bd6a838450317007abb` |
| `tests/test_research_submission.py` | `c4eec74c5d4e77a259a09183f278e49810dee485cfcf12278a61406343320f14` |
| `tests/historical_submission_fixture.py` | `c775daa01a2dbd9c96ab94d940d5cb26fd876938fffd7e4b671d439b66e754ba` |
| `tests/test_submission_protocol_admission.py` | `710028eb2f876999205279dea454849731164c397ef883a7228adc1e4ca08302` |
| `tests/test_bounded_research_submission.py` | `19662f2258d2b6e780383abfe683aa8e53a7172c7ff28299438d149c6137497e` |
| `tests/test_calculation_handoff.py` | `ab9013d011e2090bd6774b508f2b164bd2a150d174b85bf2d1c9b0ff4d0dfa59` |
| `tests/test_material_semantic_handoff.py` | `85f00c95b90688dc1644515ecdb2539368f88889b4a2e92eec1574066104ffbf` |
| `tests/test_research_materials_stage.py` | `f0cd875527fc414716a93ce9fe76f69dc5206a57e69fbda0afd0523697cd94db` |
## 正向及反证前置交付协议一致性（2026-09-30，Task 3.1/3.3 子路径）

### 实际修改及生产者→消费者

- `prepare_multidimensional_stage_run` 对现有正向八维及反证前置研究统一生成当前 `calculation_selection_version`、`reference_transport_version`，调用与父 manifest 保留同一绑定；不新增 Agent、不把反证前置研究冒称独立 Skeptic 执行，不导入 Analyst 结论。
- 两种序列化入口沿现有业务 Schema 派生同一模型格式：选择 `calculation_selections` / `document_selections`，不要求模型填写身份、计算数值/血缘、文档身份或产物路径。正式报告结构、研究语义、来源与 PIT 要求保持。
- 原 MCP 消费者只在正向阶段加载短引用映射，导致反证前置的实际 stdio 查询返回 `UNKNOWN_EVIDENCE:e.*`。已修复到同一受限任务映射：反证前置的非 Skeptic 任务按其真实 Invocation 取得允许集；独立 Skeptic 仍走已有隔离 scope，不能借此取得上游报告。
- 新 `require_current_selection_transport` 在宿主启动、SubagentStart 交付前及 Stop 写入前重验任务/索引/Invocation 的协议、身份及 Invocation 自摘要。缺失或旧交付协议报 `MULTIDIMENSIONAL_LEGACY_SELECTION_TRANSPORT_EXECUTION_RETIRED`；重签的跨 run/task/Invocation 或损坏摘要报 `MULTIDIMENSIONAL_SELECTION_TRANSPORT_BINDING_INVALID`。
- 历史正式报告读取、旧版本装配不调用执行准入函数，不修改冻结包。保留原首次定点只适用于正向阶段的限制；反证前置负例使用原 batch/retry 路径，不扩阶段能力。

### 实际验证

新增 `tests/test_multidimensional_transport_admission.py` 的 6 个测试方法：

1. 两种真实准备器产物→两条上下文序列化→实际 Hook 生命周期→各 8 份正式报告；选择草稿原句与 gap 不被改写、正式自摘要合法。不依赖模型，也不证明内容质量。
2. 缺失 packet / task / Invocation 协议的重签负例：启动前确定性拒绝，子进程未调用、不创建启动状态，文件字节保持。
3. 跨 run、task、Invocation 及损坏自摘要拒绝。
4. 反证前置的实际 stdio query/calculate→成功收据→选择→Hook→正式计算与原句；另拒绝由其它运行的实际生产者生成的短引用。
5. Start 后任务协议漂移，Stop 不得直接写报告，明确拒绝。
6. 在 Start 前 Invocation 协议漂移，不能交付研究上下文。

实际命令：

```text
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_multidimensional_transport_admission
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_multidimensional_transport_admission tests.test_multidimensional_stage tests.test_multidimensional_references tests.test_submission_protocol_admission tests.test_targeted_research_closure tests.test_calculation_handoff tests.test_local_revision tests.test_skeptic_semantic_handoff
openspec validate simplify-research-handoffs-and-acceptance --strict
git diff --check
```

- 新聚焦集：**6 tests / OK，3.552s**；最终相关集合：**161 tests / OK，76.511s**。旧报告读取、既有正向提交/局部修订/最小闭包及独立 Skeptic 受影响接缝在该集合内保留检查；不是全量产品 Gate。
- 中间失败如实区分：新测试为每个任务使用不同父会话，违反既有依赖完成事件绑定；已改为同批父会话、独立子会话，不改生产门禁。另有错误的 Start 状态断言（实际为 DELIVERED）及从没有资料的持仓披露任务取第一条引用造成 StopIteration，均修正为准确的测试输入/断言。
- `UNKNOWN_EVIDENCE:e.*` 则是实际 MCP 消费者遗漏，已按上述代码修复。未以测试错误掩盖该实现错误，也未自动修正模型引用。

### 尚未关闭及证据范围

- **Task 3.1/3.3 仍不勾选**：本节关闭旧交付协议准入与反证前置的消费者遗漏。当前选择协议下，非 MCP Hook 仍有接受旧全字段草稿的格式兼容分支；需要继续将当前写入与历史装配分离并迁移对应显式测试输入，不能把本节 8 维合成选择草稿通过当作该分支已退役。
- 真实加载/模型运行状态为 **NOT_RUN**。上述启动及 MCP 交付改变的实际模型补验缺口应合并进 Task 6.4 一次预算说明，未获新授权不调用；不把合成 Hook 事件或 stdio MCP 测试当作模型执行证明。
- 原八维 Change 继续暂停；未改历史版本锁、业务最低内容、来源条款、其他 Change 的完成标记。未归档、提交或推送。总体进度仍为 11/30，不能以子路径检查冒领整个任务。

以下 SHA-256 由本机摘要命令取得并直接装配，仅绑定本节最终源码/测试快照；共享文件的既有修改不因此取得整文件暂存授权。

| 文件 | SHA-256 |
| --- | --- |
| `product/runtime/calculation_handoff.py` | `3639bad13d370f1bed179cdbfdd21d3ec46f554333ecf4b3f30f2dd7928948cb` |
| `product/runtime/multidimensional_stage.py` | `66c53c739be832dae9c7621392b4028587dd8be70a9d7eba3cc0773e57c84956` |
| `product/runtime/codex_hook_recorder.py` | `2330986a03980a758220d8486261efa5b063b2e96d178005a30ead7fcb3ffe47` |
| `product/runtime/fixture_mcp.py` | `a85994810bbadef9632a74406e20afc1441c1f1f69cb4e50cef36edcd9aff0b1` |
| `tests/test_multidimensional_transport_admission.py` | `674087029891580a208f2e3f69c023fbf83e22923c21216d3ef836e693a412d8` |


## 当前选择草稿强制校验与按角色纠错（2026-09-30，Task 3.3 完成；Task 3.1 子路径）

本节取代上一节“非 MCP 当前入口仍接受旧全字段草稿”的未关闭状态：该字段缺失回退已经移除。**Task 3.3 完成，总进度 12/30；Task 3.1 仍未完成**，不以本节代替其它工程契约、真实内容验收或候选晋升。

### 实际根因与修改

1. `validate_semantic_selection_draft` 原来只在出现 `calculation_selections` 时检查，字段缺失便落入完整草稿兼容装配。现在当前写入无条件使用冻结业务 Schema 派生的选择契约；两个选择字段必填，完整计算、文档元数据及附件路径均不是作者草稿字段。历史 `assemble_calculation_selections` 的显式旧格式读取保持，不回写原包。
2. 实际 MCP `resolve` 已验证保存的原稿、提交事件和修订证明并装配正式字段；Stop 不能把这个可信返回值再次当成作者草稿校验。它按可信 `submission_binding` 与实际任务版本识别装配结果，不根据模型自行声称“已装配”跳过校验，后续正式结构、Evidence、计算、文档、状态校验仍执行。
3. 本地纠错定位原来依赖作者填写 Invocation；新草稿没有该字段。定位现从可信派发/Start 绑定取得，作者若回填冲突身份仍拒绝，不改原始草稿。
4. 局部修订原来将正式报告 Schema 用于作者草稿，造成 `SCHEMA_DIAGNOSTICS_TOO_MANY`；初次统一派生又错误将八维 `$defs/id` 用于独立 Skeptic。现在纠错绑定按真实阶段重读原任务契约：八维使用选择 Schema，独立 Skeptic 使用自己的模型业务 Schema，不共用业务字段。首稿加一次局部修订及完整复验上限不变。
5. 测试作者分别提供 `dimension_draft`（当前选择草稿）与 `formal_dimension_draft`（显式历史/正式对象）。Stop 测试辅助入口不自动删字段或修 ID。零同行资料仍先按原冻结 Schema 拒绝主张；没有放宽 maxItems、诊断预算、Evidence、PIT 或业务血缘。

### Task 3.3 的逐项关闭依据

| 规定行为 | 实际生产者与消费者 | 正负测试及证明范围 |
| --- | --- | --- |
| 服务端计算 ID | 当前 MCP 参数契约 → 成功事件/收据 → `k.*` → 报告装配 | `test_server_calculation_ids` 的真实 stdio、有序输入、并发唯一性、越权与副作用前拒绝；不是模型执行证明 |
| ratio 顺序与真实结果 | 工具成功记录 → `load_tool_receipts` / `receipt_calculation` → 原正式血缘检查 | `test_calculation_handoff`、`test_common_stock_semantic_handoff`；逆序输入、重签账本、损坏/缺失事件仍拒绝，保留真实输出 |
| 预计算与失败不可选 | 冻结技术/市场附件 → 受限目录 → 明确选择 → Hook | `test_calculation_handoff`、`test_market_breadth_calculation`；不完整窗口不提供选择，篡改宽度/附件失败，失败及未执行收据不能引用 |
| 已授权依赖计算 | 基本面实际 query/calculate/Stop → 正式报告/选择记录 → 研报当前 v6 MCP → Finalizer / reopen | `test_successful_source_report_to_native_research_selection_and_reopen`；选择必须关联真实上游主张，保留原值/输入/原运行，不给下游新增计算权限 |
| 文档选择与元数据原样装配 | 冻结允许文档 + `d.*` → 作者选择 → `_selected_documents` → 正式报告 | `test_bounded_research_submission.test_unknown_document_can_only_be_replaced_by_authors_explicit_choice` 的真实 stdio/Stop/Finalizer；整对象等于原文档，包括原来源和时间；另有非 MCP 文档及关系正例，未知选择两稿仍失败 |
| 不要求模型抄结果/血缘/路径 | 两种实际上下文序列化 → 同一选择 Schema → MCP / 非 MCP 消费者 | `test_calculation_handoff`、`test_multidimensional_transport_admission`；缺选择字段、混合完整计算、错误参数都拒绝；正式中文报告/原句保留 |

独立 Skeptic、CIO、Eval 不因本任务新增计算或文档访问权限。现有角色隔离和消费者业务契约保持；其其它引用、历史执行准入与成本精简义务仍分别由未完成 Task 3.1、3.2、4.3、5.1、5.2 承担。

### 实际命令与结果

以下命令都在当前开发环境执行，测试仅写临时合成产物，未启动产品模型、网络探针、项目沙箱或任何 Gate。

```text
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_local_revision
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_skeptic_semantic_handoff tests.test_local_revision
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_multidimensional_stage tests.test_multidimensional_references tests.test_market_breadth_calculation tests.test_scoped_research_claims tests.test_calculation_handoff tests.test_research_submission tests.test_local_revision tests.test_server_calculation_ids tests.test_material_semantic_handoff tests.test_common_stock_semantic_handoff tests.test_skeptic_semantic_handoff tests.test_council_semantic_handoff tests.test_cio_handoff tests.test_cio_reference_handoff tests.test_eval_handoffs tests.test_submission_protocol_admission tests.test_bounded_research_submission tests.test_multidimensional_transport_admission
openspec validate simplify-research-handoffs-and-acceptance --strict
git diff --check
```

- 八维局部修订聚焦：**14 tests / OK，2.217s**。
- 独立 Skeptic + 局部修订：**34 tests / OK，34.319s**。
- 最终相关集合：**326 tests / OK，127.220s**，对应最终源码快照，覆盖各共享消费者；不是全量产品 Release Gate。
- OpenSpec strict 与差异空白检查通过。
- 中间失败如实保留原因：旧全字段测试样本已不符合新协议；一个工具测试只把事件留在内存，缺实际事件文件；独立 Skeptic 的共享修订 Schema 选错。前两项修正测试作者/记录，后一项修正实现。中间 157 项集合曾有 1 failure / 2 errors，不能当作 PASS；最后 326 项重新验证后才关闭本节任务。
- 所有测试中的 Hook 父子事件均为合成调用，MCP 为本地确定性执行。**真实模型加载、推理、内容质量及 token 收益仍为 NOT_RUN / 未观测**，需按 Task 6.4 统一提出缺口与预算，不复用旧 LLM 授权。

### 剩余边界与现场保护

- Task 3.1 尚需最终逐入口核对，尤其旧 MCP v3–v5 的历史 `resolve` 与 Hook 发布/保存边界；其历史辅助构造/读取向量不能当作当前 v6 的新写入证明。这里只关闭非 MCP 全字段回退及计算/文档选择，不宣称全部历史准入都已完成。
- Task 5.1 在其它角色的局部修订仍有剩余项；本节没有把八维/独立 Skeptic 修复当作所有入口均完成。
- 其它活跃 Change、暂停八维任务及全部未提交修改保留。没有归档、提交、推送、改历史包或新增产品版本锁。

以下完整 SHA-256 由 `shasum -a 256` 的机器输出直接装配到表格，只标识本节测试对应文件，不是产品锁、候选晋升或整文件提交授权。旧章节的快照仍保留为当时记录，不能混充本次快照。

| 文件 | SHA-256 |
| --- | --- |
| `product/runtime/calculation_handoff.py` | `4e142b24658a7c9b51072b8e7921d1ec09a4db19dd958326a0f836c668b278f9` |
| `product/runtime/codex_hook_recorder.py` | `4eeb2bbd1aeeebafa704e990c52b9eeb58d885d3b16726f551718ff6990c8195` |
| `product/runtime/research_submission.py` | `50e11f500bfafefe70ba095cce3a54ef710fcaf9e065ad0288cc2317fc34ffd4` |
| `tests/test_multidimensional_stage.py` | `bab99456754536ae33b6049681b09bea5972155ba9c11eb3d0f6ee3acaa01513` |
| `tests/test_multidimensional_references.py` | `8062ce8e2450b2ce06680ecaec281fe98242a2d173e8445882ed481682ea1c7b` |
| `tests/test_market_breadth_calculation.py` | `3f5fae49268cf41c8948fd2eb88f83170a9dbf262c3ec177febbe28ec339b727` |
| `tests/test_calculation_handoff.py` | `bf972784f6cd898853efff8865e9d01f9088b02cbd7150604f49a5698e810212` |
| `tests/test_research_submission.py` | `8697d6be18d244fb5cfbb6f1a9a96e069afa2e883dd57e32d5f6009436df9335` |
| `tests/historical_submission_fixture.py` | `2ad3a57b2490ec6e82076d27b500f5639456032f76c3bb04530c750b33d41821` |
| `tests/test_scoped_research_claims.py` | `6122db5d039d8b964427dd58b2c921b51fc0cbce7219cc5ed90cf39d1524d2c0` |
| `tests/test_local_revision.py` | `71a00d9b7615ab5a1911c7a50ba39e908226a39fd125100abbfd394f84e10765` |
| `tests/test_skeptic_semantic_handoff.py` | `4fb692df3ac6b6727bdea740d52ba4ca9af2eef0bd0e35369edc9e9fbd87a0d3` |

## 当前执行与历史读取分离关闭（Tasks 3.1、3.2；2026-09-30）

### 本轮修复及证明边界

旧 MCP v3–v5 虽已在工具/宿主启动退役，Hook 仍可能沿只读 `resolve` 保存新报告；部分历史测试把这种保存写成当前执行 PASS。本轮在真实 Start、Stop 解析、发布和接受记录边界执行当前版本准入。旧 v1–v5 在上下文交付前明确拒绝；调用旧发布器也不得生成新报告或 marker。

- `resolve(..., for_execution=True)` 用于实际 Stop；默认读取仍按原版本验证精确回执、身份、hash、计算及关系，不重签历史。读取目录使用 `create=False`，缺回执也不创建目录。
- `_read_multidimensional_report_artifact` 从原发布函数拆出纯业务读取，不负责执行准入、落盘、接受记录或 Hook 事件。当前发布器先核真实身份和协议，之后复用相同业务检查。
- 历史向量仅由测试模块在临时目录明确构造；旧正例验证读取和 consumer reopen，旧负例验证原错误与原文件不变。不调用旧 Hook 制造 SAVED、不用其 Finalizer 宣称当前执行成功。当前 v6 仍使用实际 stdio MCP、原 Hook 和最终检查。
- `mark_accepted` 拒绝退役 binding 与退役冻结任务，不能借伪当前 binding 恢复旧任务写入。
- Runtime Eval 增加旧结果只读 / 新提示及 native 收集拒绝接缝。纯旧 normalizer 的返回本身不是写入或执行许可；冻结结果保持不变。

### Task 3.1 逐入口关闭映射

下表的 producer 是实际确定性函数/工具输出，Hook 父子事件和模型草稿为合成测试输入；**不是实际 Codex 子 Agent 或研究质量证明**。

| 入口 | producer → consumer 与实际上下文 | 主要正负接缝 |
| --- | --- | --- |
| 资料准备 | 原 MCP search/fetch/事件 → 语义选择 → 工具审计/正式结果/读取器 | `test_material_semantic_handoff`：成功/失败原尝试、未知选择、未执行查询、越权身份、旧结构可读但新写入/启动拒绝 |
| 普通股 | 冻结请求/实际 query/calculate → 原角色语义 Schema → Hook / 正式报告 | `test_common_stock_semantic_handoff`：原句与计算保持、技术字段拒绝、实际上下文与引用表一致、旧包只读、新启动拒绝 |
| 八维正向/反证前置 | 实际 prepare / query / calculate → 动态选择 Schema → MCP/native Stop / 正式对象 | `test_multidimensional_transport_admission`、`test_submission_protocol_admission`、`test_bounded_research_submission`：各能力正例、缺/漂移协议、旧版本上下文/发布拒绝、真实 v6 有界提交、损坏事件与未知选择拒绝 |
| 独立 Skeptic | 自身冻结取证包/实际 query → 自身模型 Schema → 独立 Hook / package | `test_skeptic_semantic_handoff`：合法反证语义保持、错 run/证券/模型/技术回填拒绝、旧包可读但执行/写入拒绝；不获得 Analyst 首轮结论 |
| fixture Council / CIO | 实际 Specialist Hook / MCP 报告读取事件 → 主线程 CIO 决策草稿 → 原 Risk 前契约 | `test_council_semantic_handoff`、`test_cio_handoff`：消费事实来自真实交付、未读不冒称消费、原动作及 Risk 约束、旧执行和完整身份回填拒绝 |
| predecision CIO | 已验证报告与受限读取事件 → 短引用选择 → 冻结完整消费血缘 | `test_cio_reference_handoff`：实际 stdio、指定角色集合、错报告类型/run/版本拒绝、旧 packet 可读但执行退役 |
| 普通股 Eval | 原真实 prepare 冻结输入 → 语义评分稿 → 原结果装配/读取检查 | `test_eval_handoffs`：分数理由不变、错输入/缺模型/rubric 篡改拒绝、旧完整结果可读但新写入拒绝 |
| Runtime Eval | 原 prepare / 合成会话工具读取 → native 评分稿 → 执行证明接收器 | 同上：真实读取绑定、评分原值不改、错模型/技术字段拒绝、历史结果可读但提示/收集不准新写 |

上述入口各自保留业务 Schema、权限、角色及专用闭包检查；共享的是机械职责，不是一个万能提交/编排服务。实际交付结构不要求模型复制 hash、运行身份、路径或计算血缘。完整历史包迁移与当前资源升级仍由未完成 Task 4.3 验证，不借“旧对象可读”宣称它已经完成。

### Task 3.2 逐项关闭映射

| 原任务规定 | 实际证据 |
| --- | --- |
| Evidence / Document / Calculation 短选择 | 普通股、八维、独立 Skeptic 与 CIO 的实际工具/上下文/Schema 一致；`test_calculation_handoff`、`test_server_calculation_ids` 验证成功收据和选择，`test_scoped_research_claims` 验证文档原内容版本 |
| 跨报告重名及本地同名 | `test_scoped_research_claims` 的两份正式 producer 报告到 consumer；外部 Claim 限定 report ID/hash/local claim，局部同名不遮蔽外部版本或保留命名空间 |
| 类型、任务、run、旧映射及并发 | 相同输入在不同 task/run/Gate/报告版本下产生不同作用域；并发生成映射、服务端计算 ID，跨类型/跨任务/旧引用均失败；不截断、不猜测、无相似匹配 |
| 下游解析与语义保持 | 实际 Hook 报告进入正式验证及中文引用渲染；当前依赖计算经实际 v6 保存并重新读取；历史歧义裸 Claim 拒绝，原报告字节/hash 不改 |
| Skeptic 隔离 | 独立任务与首轮自身 Evidence 允许集保持；实际工具和报告拒绝另一证券/角色/run，新增短引用不增加 Analyst 结论读取权限 |

### 实际命令和结果

```text
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_submission_protocol_admission tests.test_research_submission tests.test_bounded_research_submission
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_material_semantic_handoff tests.test_common_stock_semantic_handoff tests.test_multidimensional_transport_admission tests.test_multidimensional_stage tests.test_research_submission tests.test_submission_protocol_admission tests.test_bounded_research_submission tests.test_skeptic_semantic_handoff tests.test_council_semantic_handoff tests.test_cio_handoff tests.test_cio_reference_handoff tests.test_eval_handoffs tests.test_scoped_research_claims tests.test_local_revision
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_eval_handoffs tests.test_hashing_contracts tests.test_multidimensional_references tests.test_calculation_handoff tests.test_server_calculation_ids tests.test_market_breadth_calculation
openspec validate simplify-research-handoffs-and-acceptance --strict
git diff --check
```

- 第一组 **70 tests / OK，26.147s**；逐入口集合 **278 tests / OK，113.098s**；补充集合 **65 tests / OK，19.061s**。集合重叠，不把相加当唯一案例总数。新增 Runtime Eval 历史准入用最后集合补验，不扩成真实评分运行。
- 中间失败如实保留：历史 fixture 路径键及接受 marker 缺失（68 项中的 2 errors）、直接 publisher 测试缺可信 output_binding（69 项的 5 subtest failures）、错误要求纯旧 normalizer 抛执行错误（65 项中的 1 failure）。前两者修测试的真实输入/构造，后者按函数只读职责与实际执行边界更正；未以此放宽产品门禁。
- OpenSpec strict valid；差异空白检查通过。以上均为当前开发环境的确定性检查，无产品 LLM、网络探针、Replay、Eval Runner、Regression、Gate 或沙箱启动。
- Tasks 3.1、3.2 关闭，总进度 **14/30**；本 Change 未完成。真实加载与模型效果 **NOT_RUN**，留待 Task 6.4 汇总最小缺口与一次新预算授权；不借旧八维额度运行。
- 其它未提交修改及暂停 Change 保留；未归档、提交或推送。没有改历史版本锁或产品权限。

本节文件字节快照由本机摘要命令直接装配，不是产品锁或晋升记录。

| 文件 | SHA-256 |
| --- | --- |
| `product/runtime/calculation_handoff.py` | `fcb903ba7da81acbb524876d3c0c1e3ce0a27a6aadf5c6a7607a4e5743ddb55a` |
| `product/runtime/research_submission.py` | `81947352b2624cedbd71a05ddcf15421a48c530ead7d05975ab23d50a2de7d6a` |
| `product/runtime/codex_hook_recorder.py` | `5fe73dc53b34440858647377a9aa790efc93201c7059231075589caf31ecdc86` |
| `tests/historical_submission_fixture.py` | `729323e2f67a6ed601d285f40f6acbd828407b973386b8584e3f9c48a875d83e` |
| `tests/test_research_submission.py` | `d32feec02042148ce941dcb324b3abc4295a5555513eb11b4a94b39296da4877` |
| `tests/test_submission_protocol_admission.py` | `cbc64c82781d2e455ce76b60305061b31d46952568764432614f493f1e307e6e` |
| `tests/test_eval_handoffs.py` | `2560e56414112b1439fc8acbb0696c7a103958aa30b864282d69750dd4d802b7` |

## 正式研报到只读浏览器的依赖主张闭合（Task 3.5 部分推进，2026-09-30）

### 首个具体消费者缺口与修改

`ArtifactCatalog._validate` 及 `company_reports` 原来总是传 `known_research_claim_ids=()`，因此当前 Hook 生成的研报虽然引用了同一目录中有效的基本面报告，仍被网页误判悬空。不是 hash 计算错误，也不是模型需要重新抄写引用。

现沿既有扫描器只读加载并校验报告：没有外部主张的有效报告先进入可用集，再对依赖报告逐项验证。允许集只来自**同一实际来源目录、相同 run 和完整组合/请求/截止点绑定**的已验证上游版本；使用原 `known_claim_references`，不根据文字相似或裸名称猜来源。先加载失败、未知、缺失、旧版本或另一目录中的同名报告均不能授权下游。循环依赖没有已验证来源时拒绝。完整扫描后再验旧裸引用歧义及拒绝报告的传播，避免扫描顺序选中第一份同名主张。

没有新存储、Agent、工具权限、网络或当前执行绕过。扫描仅产生内存展示目录，不回写报告，也不把旧研究升级为事实 Evidence。

### 实际接缝与结果

`tests/test_research_handoff_consumers.py` 的正例使用当前 prepare / 原 Hook 生成基本面报告，再用当前短引用草稿及实际 Stop 生成研报；已有 ArtifactCatalog 和 company_reports 读取它，整份对象及中文原句、否定与缺口保持。所有 Hook 事件为合成调用，**不是模型研究证明**。基础合成 Gate 未声明浏览器支持的 schema 时仍保留其 UNKNOWN 问题，不补造真实 Gate、不因报告接缝通过而宣称全包无问题。

负例实际在临时目录注入缺源、来源报告版本变化、非法来源引用及相同 run/binding 但其它目录的来源；研报不进入展示目录。旧同名裸 Claim 和真实双向依赖环也拒绝。读取前后完整文件摘要集合相同。

```text
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_handoff_consumers tests.test_local_research_browser
git diff --check
```

最终 **37 tests / OK，2.522s**；差异检查 exit 0。已有浏览器 34 项在最初产品修复后也通过（0.974s）。中间测试失败保留：误把基础合成 Gate 的 UNKNOWN 当整个目录零问题；另一个旧歧义案例与本地 Claim 同名，实际测成了合法本地主张，已修测试作者的 ID；最后修正测试模块直接导入 TestCase 造成重复收集，最终37项不含重复跑基础阶段81项。没有为这些测试问题放宽生产验证。

**Task 3.5 保持未完成**：本节只关闭网页的实际依赖主张遗漏，不替代 bundle、Memory、所有下游 source-inputs 及历史包迁移的剩余接缝。Task 4.3 也不勾选。没有产品 LLM / Smoke / Replay / Eval Runner / Regression / Gate、归档、提交或推送。

本节机器取得的文件字节摘要：

| 文件 | SHA-256 |
| --- | --- |
| `product/web/read_only.py` | `35a20c1201e8ca08876b474032988524a65a717517d5b512e1db7955534c63c4` |
| `tests/test_research_handoff_consumers.py` | `18ee266e64abfb0c23a8e1be941d7190ca18db8a3d09b5d4abd678bcae37936f` |
| `tests/test_local_research_browser.py` | `4d8b75050b0d867b5459aa4e1f7c4c24cb051716bf8b4516fa9cbcfa87b633c0` |

## 普通股当前语义报告到 Memory / 只读浏览器（Task 3.5 部分推进，2026-09-30）

同一新增接缝使用当前普通股 prepare（显式临时 memory_root）、真实本地 stdio query/calculate、语义草稿和原 Hook Stop，经原 Finalizer 校验并保存自包含报告包及索引。随后由既有 ResearchMemory 读取包、ReadOnlyResearchMemory 读取展示报告：整份正式报告、请求、原 Evidence 对象（含来源、期间、单位及所有时间）、主张原句和报告 hash 保持一致。没有让测试作者补写一个假技术包装来代替实际 producer。

在测试临时目录删除原运行目录后，自包含 Memory 对象仍可只读显示；篡改对象正文而不改原内容 hash 时拒绝，读取器不会修正文或旧 hash。这只证明该自包含对象不依赖旧目录，不代表所有历史包/旧读取器/当前资源升级已经验证；Task 4.3 不因此勾选。

实际命令：

```text
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_handoff_consumers
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_handoff_consumers tests.test_local_research_browser tests.test_research_memory
git diff --check
```

- 新接缝 **4 tests / OK，2.208s**。
- 受影响消费者及 Memory 集合：初次 **63 tests / OK，3.804s**；新增整 Evidence 对象等值断言后最终 **63 tests / OK，3.849s**。
- 不包含真实模型、来源网络、运行重放、语义评分或产品 Gate。
- Task 3.5 仍未完成：普通股 Memory 与网页依赖引用已补实证，仍须核对当前语义报告进入完整 bundle / 后续冻结 source-inputs 的逐入口消费及剩余版本/语义闭合。不能用本节普通股正例替代其它接口。总进度仍 **14/30**。

以下是最终接缝文件字节快照（上一节37项测试使用的旧测试快照保留为当时证据）。

| 文件 | SHA-256 |
| --- | --- |
| `tests/test_research_handoff_consumers.py` | `eb931822525ebfb286054af4603b437b4b3ea4b67047ade42d80a7173e33ab84` |
| `product/web/read_only.py` | `35a20c1201e8ca08876b474032988524a65a717517d5b512e1db7955534c63c4` |

## 正式产物交接关闭与 CIO 冻结读取分离（Task 3.5；Task 4.3 部分，2026-09-30）

### 当前入口交接覆盖

本节承接前两节的网页/Memory 实证，以及 Tasks 3.1–3.4 的逐入口装配证据。关闭的是**确定性产物交接**，不是模型研究充分性或候选晋升。

| 入口 | 实际生产者 → 消费者 | 证据及边界 |
| --- | --- | --- |
| 资料准备 | 原 search/fetch 工具事件 → 语义选择 → Finalizer/正式材料包/导入 | 本轮 `test_material_semantic_handoff` 重验事件、原文、尝试、未执行查询与越权选择；原材料包读取不改字节 |
| 普通股 | 原 query/calculate → 语义 Stop → 正式报告 → Finalizer → Memory → 网页 | 前节真实本地函数链保存整份报告、请求与 Evidence；原目录删除后仍读自包含 Memory，对象篡改拒绝；本轮普通股语义接缝重验 |
| 八维 | 八个合成语义草稿 → 原 Start/Stop Hook → 原 Finalizer → HoldingResearchBundle → 原消费解析器 | 新测试不是人工填八个 SAVED 摘要：各实际 Hook 确认 DELIVERED/SAVED；bundle 引用保持 report ID/hash/证券；依赖主张保持原句与限定报告版本。缺资料仍 STRUCTURALLY_CONSUMABLE，不成为研究充分或完整决策 |
| 独立 Skeptic | 允许事实的实际 stdio query → 自身语义 Stop → 原 Finalizer/package → CIO 的冻结输入 | `test_skeptic_semantic_handoff` 本轮重验原报告与中文反证语义；新 CIO 测试完整通过原正向/反证包验证，没有 mock 这些门禁。该测试的正向报告仍是既有合成 fixture，不冒称所有研究经模型运行 |
| fixture Council / CIO | 实际 Specialist 产物/报告读取工具 → native CIO 草稿 → 原消费装配/Risk/Trace | 本轮 `test_council_semantic_handoff`、`test_cio_handoff`；未读不冒称消费、旧路径不能写入，动作及 Risk 契约不改 |
| predecision CIO | 原验证后的正反包 → prepare 冻结 source-inputs → 实际 stdio read_reports → 还原完整报告 | 新测试按实际请求顺序读取报告，再逐报告比对全部字段与来源原对象；不是仅比对目录摘要。原 ID/hash/主张、否定、缺口、反证保留，无模型/CIO 最终研究产出 |
| 普通股 / Runtime Eval | 原 prepare/受控评分输入读取 → native 评分字段 → 正式结果及原读取验证 | 本轮 `test_eval_handoffs`，保留 rubric、分数、理由、引用及旧完整结果；只有确定性合成评分输入，没有启动 Eval Runner 或真实 grader |

Memory 仍使用已有普通股报告包/索引，不为维度报告新增存储服务；八维报告由原运行包和网页读取。旧格式仍按登记契约读取；此项不替代 Task 4.3 的所有历史包迁移/版本读取证明，也不创造新的下游产品入口。

### CIO 本轮实际修复

原 `validate_predecision_cio_run` 同时要求原目录、准备时绝对 output_dir、当前 discovery/resource hash；冻结内容完整也会因目录移动或资源升级拒绝。本轮在同一校验函数分离：

- 默认 `for_execution=True`，所有既有工具、提示、launcher 和 Finalizer 仍使用此默认，原目录/当前资源/当前权限准入不被只读模式放行。
- 显式 `for_execution=False` 只用于冻结输入读取，不调用模型、当前 discovery、原目录，也不产生消费事件或输出；按原请求/manifest、冻结文件锁、报告目录、来源包/bundle 自 hash、实际事实/PIT/Evidence 闭合校验。
- 新 prepare 保存请求 Schema 原始字节，并把来源 bundle/package 已声明依赖纳入 frozen_inputs；不是拷贝用户配置或认证，不改来源运行目录。
- 无冻结请求 Schema 的旧包，只在原文件 hash 与登记的 request/manifest 版本吻合时使用既有读取器；当前同名但不同字节拒绝 UNSUPPORTED_VERSION，不补造旧资源。
- 路径越界、`..`、文件/中间目录符号链接拒绝；缺冻结 Schema、缺输入、Schema 篡改或未知版本均失败。
- 测试复制并移动临时包、删除原目录和原副本后仍读取相同 manifest/request/报告；当前仓库不存在也能按冻结请求契约读取。另在临时仓库实际修改 CIO Agent 文件字节：只读不受当前升级影响，执行仍拒绝 resource drift。

**Task 4.3 保持未完成**：上述新增模式证明的是 CIO 冻结输入包，不是完成态 CIO Trace 的全部模型证明重验；研究依赖/全部登记旧 Schema 读取器及完整旧包适用性还需本任务逐项核对。没有增加 Execution Replay Executor，也没有用 artifact 通过准入真实执行。

### 实际命令及结果

```text
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_predecision_cio_stage tests.test_cio_reference_handoff
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_cio_artifact_reading
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_handoff_consumers tests.test_cio_artifact_reading tests.test_predecision_cio_stage tests.test_cio_reference_handoff tests.test_skeptic_semantic_handoff tests.test_local_research_browser tests.test_research_memory
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_cio_artifact_reading tests.test_research_handoff_consumers tests.test_predecision_cio_stage tests.test_cio_reference_handoff
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_material_semantic_handoff tests.test_common_stock_semantic_handoff tests.test_council_semantic_handoff tests.test_cio_handoff tests.test_eval_handoffs
openspec validate simplify-research-handoffs-and-acceptance --strict
git diff --check
```

- 旧当前 CIO 接缝 **24 tests / OK，0.634s**；新冻结读取初版 **4 tests / OK，10.309s**。
- 受影响合并集合 **112 tests / OK，46.250s**，包括八个当前 Hook 到 bundle 的新测试；其后补强真正的 CIO stdio 报告消费与来源包依赖闭合。
- 补强后当前 CIO/交接集合 **33 tests / OK，14.033s**；其它当前入口重验 **70 tests / OK，30.253s**。
- 最后新增“当前 Agent 实际字节升级”的负例后，冻结读取测试 **4 tests / OK，10.645s**；产品实现字节与33项通过时相同。
- 中间失败保留：5项中1 error，测试误查不存在的 bundle.complete_portfolio_decision，改从消费 proof 检查；9项中1 failure，测试把按请求返回的报告顺序误当 catalog 原顺序，改为分别核对请求顺序及每份报告全部原字段。未为此改工具排序/放宽校验。
- 集合重叠，不相加冒称唯一案例数。OpenSpec strict valid、diff 检查 exit 0。
- Task 3.5 关闭，总进度 **15/30**。Task 4.3 未关闭；其它未完成项没有借本节勾选。真实 LLM、加载/研究效果、Replay、Runtime Eval Runner、Regression、Gate 均 **NOT_RUN**。
- 未修改暂停八维任务、历史锁、产品权限或用户模型配置；未归档、提交、推送。

以下快照由摘要命令直接装配，只是本轮证据定位，不是候选版本锁。

| 文件 | SHA-256 |
| --- | --- |
| `product/runtime/predecision_cio_stage.py` | `f292c6918fe32bee4b5f7549bb4aa6ca7c88304ff9456573cd05129f3a42f96e` |
| `tests/test_cio_artifact_reading.py` | `e8b4d33d905d8beed591fcec7ec0242452a4ec989fd0be385da15f98ace6c82d` |
| `tests/test_research_handoff_consumers.py` | `651664941d3ffe0adafd62a3e9758bb963f15763a1dd65d80eb97567c13770f9` |
| `product/web/read_only.py` | `35a20c1201e8ca08876b474032988524a65a717517d5b512e1db7955534c63c4` |
| `product/runtime/research_memory.py` | `356442a3558c252da7442d59a4e1a8ad2f6bb8a21eec70beea0de5e8aad5fb87` |
| `product/runtime/common_stock_stage.py` | `97ea7f001516a4525a6fa6e33b3540593e1d71ffa63797b0f8b902486855fcc4` |
| `product/runtime/research_materials_stage.py` | `253161ac4032ab3762573e683d3f6b3f99fcaf84f86b660113dc8eefd1c56263` |
| `product/runtime/codex_hook_recorder.py` | `5fe73dc53b34440858647377a9aa790efc93201c7059231075589caf31ecdc86` |
| `product/runtime/independent_skeptic_stage.py` | `c120fff1560bfadca24bfa409084db1d850f14e86c7116492e7f34d737a11947` |
| `product/runtime/multidimensional_stage.py` | `66c53c739be832dae9c7621392b4028587dd8be70a9d7eba3cc0773e57c84956` |
| `product/runtime/common_stock_eval.py` | `79f02ce3b9a45a3920ea4c26a4b02b914033ce13ce4b5966b6320537e31afa06` |
| `product/runtime/runtime_eval.py` | `725aa679b6c786558d941f0086e5cdf22a72fa27dcf7fa21a3ddd67e9ea08acc` |

### 历史读取与执行准入关闭（H16 / Task 4.3，2026-09-30）

本节关闭的是冻结产物的确定性读取，不是 execution replay、模型研究质量或 Promotion。旧包不补写、不改 hash；缺少对应契约或依赖时明确拒绝。此前 Task 4.3 部分记录保留，以下为新增关闭依据。

| 覆盖入口 | 实际生产与消费 | 正例 | 负例及边界 |
| --- | --- | --- | --- |
| Memory / 网页 | 普通股 stdio MCP → 原生 Hook → 原 Finalizer → 持久化对象 → Memory / ReadOnlyResearchMemory | 原运行目录删除后，完整报告、原 Request、Evidence、计算与中文内容保持；无当前 Agent 准入调用 | 真实存储对象与索引 hash 自洽但 report 版本为 99 时，Memory / 网页均报告 READER_UNSUPPORTED_VERSION；原主库及对象字节保持 |
| 八维 bundle | 八个当前原生 Hook 报告 → 原 Finalizer → 原消费者 | 副本搬迁、原路径不可达且传入不可用仓库后，完整消费证明与原结果相同；原包 hash 不改 | 缺派发 packet、packet 符号链接逃逸、缺原绑定根目录均拒绝；上游版本漂移仍失败 |
| 计算依赖 | 真正成功 stdio 计算 / 事件 → 原生对象提交 / Stop → 依赖报告 → 原选择读取器 | 当前 v6 原生提交的上游计算选择在搬迁后恢复相同输出；普通报告的本地计算收据也可独立核验 | 原生提交按当前执行身份读取搬迁包仍失败；实际删除计算 ledger 后 artifact 校验失败，不把空返回当证明 |
| 独立 Skeptic | 真实准备 / 查询 / Stop / 原 Finalizer → validate_predecision_package | 完整反证包搬迁、原目录删除后，用实际冻结 package 契约与生成 Schema 核验全部报告和查询闭合，不访问当前 Agent | 输入 / Prompt / Schema 缺失或篡改、未知 Schema 版本、路径 / 符号链接逃逸拒绝；artifact_schema 不能覆盖执行准入 |
| CIO source-inputs | 原上游校验 → CIO prepare 冻结 → 原只读输入校验 | 冻结实际任务 Invocation、Input、Prompt、Schema 与恢复链；包内契约 hash 和原业务 / 查询校验结合，原仓库及原目录不可达仍可读 | 实际临时仓库 Agent 升级只影响当前执行；冻结契约 / 任务输入缺失或篡改拒绝。旧包未保存契约时报告 SOURCE_CONTRACT_MISSING，不拿当前文件补造 |
| Schema 适配 | 同一 Draft 2020-12 适配器接收显式冻结资源集合 | 原冻结约束及传递依赖仍生效；空集合明确表示不准读取当前外部 Schema | 缺依赖、未知 / 远程 / 越界引用拒绝；显式集合不会回退当前仓库 |

实现要点：

- 八维 artifact 读取沿用原生成与装配方法，仅把“原引用身份的目录字符串”与“实际文件读取根目录”分离；原目录只参与身份重建，绝不用于读文件，不重新签发旧短引用。
- current / execution 默认仍为严格分支。真实 Hook、MCP 工具权限与最终执行准入没有被历史读取授权替代；原 Finalizer 默认校验未改为 artifact 分支。
- CIO 新 prepare 复制经原上游校验的实际依赖与契约，不修改来源包。恢复链只允许上一尝试的固定引用，防止循环或任意补件。
- 只读解析成功不提高原研究内容等级；合成八维不足案例仍为 STRUCTURALLY_CONSUMABLE，CIO 准备阶段仍为 RESEARCH_ONLY / Risk NOT_RUN。
- SQLite 只读连接可能创建 WAL / SHM 锁协调 sidecar。本轮证明主库和历史对象不改写，不宣称全进程无文件写入；旧的全进程隔离保证不在本任务范围内。

实际执行记录（均为确定性接缝测试，无网络或模型）：

1. 基础冻结 Schema / Skeptic 读取：`TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_skeptic_artifact_reading tests.test_strict_schema_validation` → 16 tests / OK（2.660s）。
2. 中间集成快照：`TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_strict_schema_validation tests.test_skeptic_artifact_reading tests.test_cio_artifact_reading tests.test_research_handoff_consumers tests.test_calculation_handoff tests.test_research_submission tests.test_multidimensional_references tests.test_skeptic_semantic_handoff tests.test_independent_skeptic_stage tests.test_predecision_cio_stage tests.test_cio_reference_handoff tests.test_multidimensional_stage tests.test_local_research_browser tests.test_research_memory` → 371 tests / OK（115.932s）。该命令开始后另有包路径保护与 Memory 未知读取器补丁，不能将此结果单独视为最终全部源码证明。
3. 路径保护后的包 / 计算集合：`TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_handoff_consumers tests.test_skeptic_artifact_reading tests.test_cio_artifact_reading tests.test_calculation_handoff` → 32 tests / OK（23.677s）。
4. Memory 未知版本拒绝后的受影响集合：`TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_local_research_browser tests.test_research_handoff_consumers tests.test_research_memory tests.test_common_stock_research_contracts tests.test_common_stock_semantic_handoff` → 185 tests / OK（45.945s）。
5. 最后路径保护对既有整包组装的接缝：`TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_multidimensional_stage.MultidimensionalStageTests.test_canonical_assembly_imports_company_reports_and_excludes_drifted_supplement` → 1 test / OK（0.763s）。
6. `openspec validate simplify-research-handoffs-and-acceptance --strict` → valid；`git diff --check` → exit 0。最终任务标记和本记录写入后再次检查。
7. 上述集合存在重叠，绝不相加为独立案例数。个别 Memory 测试仍有 ResourceWarning（未关闭 SQLite 连接），断言通过；不在本轮扩展为数据库生命周期重构。

普通修复过程保留：初次 CIO 接缝出现 15 个 fixture 缺 dispatch_index 的错误，修正隔离测试资料而非降低生产校验；网页新增只读字节断言先因 SQLite sidecar 创建失败，改为精确证明主库与历史对象；八维初次补丁漏导入哈希方法以及一条旧 fixture 被误当成原生对象提交的断言失败，分别修正导入及使用真正 v6 原生依赖案例。修复后的实际结果见上述命令，不抹去中间失败。

Task 4.3 标记完成，当前为 16/30。Task 4.1、4.4、4.5、5.x 和 6.x 保持原状态；本轮未启动真实 LLM、Eval Runner、Replay、Regression 或 Gate，模型验证为 NOT_RUN，未归档 / 提交 / 推送，也未勾选暂停的八维 Change。

以下为当前涉及文件的完整 SHA-256，由摘要命令与确定性装配生成；仅定位证据，不是新候选版本锁。

| 文件 | SHA-256 |
| --- | --- |
| `product/runtime/schema_validation.py` | `5f3873273063544f2807ee4f86597ce6da49849318d9fab43d6a061ee71f5955` |
| `product/runtime/independent_skeptic_stage.py` | `d847468031484047d6282b956615109508febbf1bc1b5dc8ed8ed32280255952` |
| `product/runtime/predecision_cio_stage.py` | `6ee7b141ed8c22b434ee92b898fe9e3cd898826ad2b8e34d751ead13d85443b1` |
| `product/runtime/multidimensional_stage.py` | `4de8b3fe435c89ef12490f59f71b5ba819d676fd234d066b99b75575dd40cb01` |
| `product/runtime/multidimensional_references.py` | `e02325eb4b9809ac4dda1812d8adbb6d5d53b3a320abeef0c9f40f750a279398` |
| `product/runtime/research_submission.py` | `8f8285e0caed8eba93f1951d6a4a11185dbade126b04857c6f2def64315915f9` |
| `product/runtime/research_memory.py` | `710ea07cb69dd3824a00ab0b3192e0b7f5abf027039a299a9b0858561b471953` |
| `product/web/read_only.py` | `4e97979df60119192f57985486e34649e19c536a07653d3523eb6383608a8a26` |
| `tests/test_skeptic_artifact_reading.py` | `60410b6f38654bc576220d718ad02f958bbc55f13a3e8620cfac4f00f5a8c437` |
| `tests/test_cio_artifact_reading.py` | `92486bf703201d705da0b3ba0d62966663ad2c00fc19c9564764c5f1e4dadf31` |
| `tests/test_strict_schema_validation.py` | `f54d42ab361210dcf3337274d43eec3b4b0550abe3aea58a5b38b67dd96370c7` |
| `tests/test_research_handoff_consumers.py` | `06fa942da575515e6c31db63abe6e8417aaf8722fdc292956e6172928f589286` |
| `tests/test_calculation_handoff.py` | `b11627e3f6317f8b0c8053e33c71d9ceae4e9a43e064446c0e058fa6f51378ea` |
| `tests/test_predecision_cio_stage.py` | `e23145dd6e90ed01dc4c2f21a8fcd1a555e92da7b4e5a5e768ac299409758145` |
| `tests/test_local_research_browser.py` | `5b133b3c97e042ab62b4700c09cebc26411d85ff908deee84659173c50570f58` |

### 路由权威整理起步（H17 / Task 4.4 部分，2026-09-30）

在 Task 4.3 关闭之后继续推进路由问题，将当前 dataset→capability 路由、capability→domain、dataset→domain 和八维输入清单集中至既有 `research_input_topology.py`；准备阶段及消费审计直接引用同一对象，不各自维护副本。保留原值、当前八维角色、profile 原有四能力声明和工具/信息隔离边界；没有改变数据筛选或 Provider 权限。

实际命令：
`TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_consumption_audit tests.test_research_input_topology tests.test_research_handoff_consumers`
→ 22 tests / OK（3.083s）。新增测试验证实际 producer / consumer 指向同一 registry，八维输入集合与现有角色相符，不把 Skeptic 混入正向角色。

`git diff --check` → exit 0；`openspec validate simplify-research-handoffs-and-acceptance --strict` → valid。

Task 4.4 **仍未完成**：下一步还须改掉 coverage 单值反向映射（多对多会覆盖）、未知项默认 COMPANY / 忽略、已采 / 已交付 / 已查 / 已引的实际消费映射，并为全体已声明 dataset 及信息隔离补齐正负例。不能把“常量已集中”当作 H17 全部关闭。原 Task 4.3 记录对应其关闭时快照；本节映射整理后仅重验受影响接缝，不将历史结果冒称新的完整候选晋升证据。

| 文件 | 此次整理后 SHA-256 |
| --- | --- |
| `product/runtime/research_input_topology.py` | `a5700ded5ec3148c4494e6dd575aeb9c0bc3928294d10f6330ff62f9dc25b22b` |
| `product/runtime/research_consumption_audit.py` | `8e0c3b09ad4a45dd457e41cc433876d02281822e7c6c48d6bf9c516c90737ad9` |
| `product/runtime/multidimensional_stage.py` | `e97de7188ccd5c9b5d319960c213a6e967d9c752c80ca9d9e8ed7c95ecb8ccbb` |
| `tests/test_research_input_topology.py` | `501c9ae38451ae68e4455bb4b08eb936caf5141c13e038495a98c7c56dedac78` |

总进度保持 16/30。所有真实模型验证仍为 NOT_RUN，未修改模型路由、产品权限或原八维状态；未归档、提交、推送。

### 路由与实际消费关闭（H17 / Task 4.4，2026-09-30）

对应规格：`multi-dimensional-holding-research/spec.md`「当前数据路由及消费状态必须共享权威映射」。沿现有 topology 模块集中八维角色/Skill/scope、四能力 profile 派生绑定、当前工具白名单、来源域、候选消费者和原事实选择器；不把四能力拓扑等同于全部八维，不新增 Provider、网络请求、Agent 或工具授权。

- 多对多：coverage 逐 dataset/consumer 保留记录，准备、消费审计及浏览器不再用 dataset→单 capability 字典覆盖；来源域与消费者域分开。原条件来源及证券范围继续由原选择器判断，如 OpenD financial_history 不因候选同行关系获得新增访问。
- 全声明覆盖：测试遍历现行 source-plan 所有22项，验证 domain、候选消费者及实际已接入选择器交付；对 OpenD manifest 的 source_capability（连通元数据）及 macro_indicator_catalog（发现目录）明确区别，不把目录当研究事实许可。未声明项显式 UNMAPPED，保留原件、说明影响、没有自动授予所有角色；浏览器保留未映射清单，不将其视为非法 Agent 名。
- 状态：准备 coverage 的 `delivery_basis=PREPARATION_SELECTOR_NOT_QUERY`，不自称查询或内容充分；消费审计分别读采集观察、Gate、逐任务允许目录、实际成功查询和报告直接/间接引用。允许目录由八维 dispatch/index 与 run manifest 的实际绑定取得，不声称模型已读；其它 dispatch 版本保留明确未投影状态，不从现有八维结构猜造加载证明。
- 实际查询按 invocation→capability 归属计数，基本面读取不冒称同行或宏观读取；有真实来源数据但未引用保持未引用。已签事件验证 self-excluding hash/run_id，篡改及跨 run 拒绝；未签历史事件可读但标 UNVERIFIED_LEGACY_EVENTS，不作查询执行证明；相互矛盾的数据集归属拒绝，不以后写 coverage 覆盖事实 dataset。
- 正向 registry 不引入 Skeptic；独立首轮原精确白名单负例复用并重新执行。原研究内容、Risk/PIT、原版本锁、历史文件和另一暂停 Change 状态均未修改。

实际执行记录：

1. 第一轮受影响接缝（171 tests / 35.482s）有1个真实失败：旧浏览器六角色白名单拒绝新增八维/UNMAPPED coverage，导致已保存研报显示 BINDING_FAILED。已修正同一消费接缝，不降低报告绑定或来源范围；该失败不改写为 PASS。
2. `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_multidimensional_stage tests.test_research_handoff_consumers tests.test_research_routing_contract tests.test_research_consumption_audit tests.test_research_input_topology tests.test_multidimensional_references tests.test_calculation_handoff tests.test_research_supplement tests.test_local_research_browser tests.test_independent_skeptic_stage.IndependentSkepticContractTests.test_first_pass_is_exact_allowlist_not_recursive_denylist` → **208 tests / OK（37.099s）**。包括实际 native Hook 到原 bundle/浏览器、搬移读取、原任务 Schema、计算绑定及 Skeptic 白名单接缝；无 LLM。
3. 最后仅增加全22项实际选择器表驱动检查和浏览器未映射清单投影，受影响重验：`TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_routing_contract tests.test_research_consumption_audit tests.test_research_input_topology tests.test_research_handoff_consumers tests.test_local_research_browser` → **66 tests / OK（4.312s）**。新接缝使用实际 prepare 产物及 GateScopedFixtureTools.query 事件，验证目录允许→未查询→已查询未引用；不是模型执行。
4. `openspec validate simplify-research-handoffs-and-acceptance --strict` → valid；`git diff --check` → exit 0。

Task 4.4 完成，总进度 **17/30**；H18、hash其余关闭和P2/P3仍未完成。模型加载、真实内容补验仍为 NOT_RUN，未启动产品 Smoke / Replay / Eval Runner / Regression / 完整 Gate，未归档或发布。确定性路由通过不代表八维研究充分，也不代表候选晋升。

| 文件 | H17 关闭后完整 SHA-256 |
| --- | --- |
| `product/runtime/research_input_topology.py` | `5b61679129fbc4f1ff40f7287835b41ab8bb3c6dd8bf8f933acfad00e71e8754` |
| `product/runtime/multidimensional_stage.py` | `0f72657e20700bf59b119f1e1783a168bbb36f497dc5121fd55547f8e7dd6042` |
| `product/runtime/research_consumption_audit.py` | `b142aba27d2a7b426bf432ce5b3d0fa97cfb78bb949463debec7c008c609a6be` |
| `product/web/read_only.py` | `333c432c1b703dc99f571758c961ceae1df72869d67d0e57946873645d813f9e` |
| `tests/test_research_routing_contract.py` | `04ea879d0ae55ddddfc9c68c900dbe95bf14d1443c8a4ea6c273543ab75cfe56` |
| `tests/test_research_consumption_audit.py` | `779bd4416f63b2704c3918079f5035e6b9800cb2d40967a912958b9687fd05db` |
| `tests/test_research_input_topology.py` | `501c9ae38451ae68e4455bb4b08eb936caf5141c13e038495a98c7c56dedac78` |

### H17 精选公司接缝补齐与 H13 继续归并（2026-09-30）

在上节关闭后沿 Task 4.1 继续：普通股请求、Gate/coverage 验证、八维报告与 bundle 的生产/消费统一使用既有 legacy_envelope_hash；provider coverage 生产和浏览器校验、MCP 事件消费也接入同一算法。删除本次因此不再使用的两份 _without_hash 副本；没有全库迁移、变更算法、重写旧包或切换正式产物到 v2。完整对象摘要、文件字节摘要及顶层自身字段排除摘要仍不能互代。

新增实际报告 producer→原业务 consumer 测试：旧标准 JSON 摘要相同、输入原文不变、正式 consumer 通过；把包含 report_hash 的完整对象摘要错当自身摘要时失败。八维报告/bundle、coverage 和事件错误保留原稳定错误码前缀，并补充 self-excluding-envelope / canonical-json/1.0.0 / 实际对象位置。原 Schema / Evidence / 业务关系检查不删。

同时核对 H17 原共享任务装配：MACRO_CONTEXT/MARKET_STATE 在基础选择器之外已有精选公司暴露资料。coverage 已使用同一个 _macro_company_context_facts 接缝，避免把实际允许目录中的精选公司事实误报为未交付；候选消费者登记 peer_comparison/close_price。没有增加新的资料权限或研究任务；来源域仍为 COMPANY，使用者是共享环境能力。新增正例验证这条真实已接入关系，并重验原宏观任务 packet。

本轮实际命令及结果（各集合重叠，不相加冒充独立案例量）：

- `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_common_stock_research_contracts tests.test_research_handoff_consumers tests.test_research_routing_contract tests.test_research_consumption_audit tests.test_research_input_topology tests.test_local_research_browser tests.test_hashing_contracts tests.test_multidimensional_research_contracts` → **198 tests / OK（30.414s）**。
- 随后增加共享公司接缝检查：`TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_routing_contract tests.test_research_input_topology tests.test_research_consumption_audit tests.test_research_handoff_consumers tests.test_multidimensional_stage.MultidimensionalStageTests.test_macro_packet_includes_scoped_company_context_without_report_dependency tests.test_multidimensional_stage.MultidimensionalStageTests.test_provider_neutral_routing_coverage_separates_delivery_from_actual_use tests.test_local_research_browser tests.test_hashing_contracts` → **78 tests / OK（4.631s）**。
- 最后仅补充八维 hash 诊断上下文及断言：`TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_hashing_contracts tests.test_multidimensional_research_contracts tests.test_research_handoff_consumers` → **37 tests / OK（3.307s）**。
- `openspec validate simplify-research-handoffs-and-acceptance --strict` → valid；`git diff --check` → exit 0。

Task 4.4 的关闭依据按此补充；Task 4.1 **保持未完成**，仍需逐对核对其它正式交接的 hash 类型/旧算法及定位诊断，不能把共用 helper 或现有 v2 工具的单元测试当成全部生产者已切换。总进度保持 **17/30**。真实 LLM/产品运行全部 NOT_RUN，没有新增授权预算、改写历史、归档、提交或推送。前面的快照和失败记录保持原样，不能用于宣称当前候选 Promotion PASS。

| 文件 | 本节检查后完整 SHA-256 |
| --- | --- |
| `product/runtime/research_input_topology.py` | `c62230501109b3f1e36a03b1b78f2e933d6e503d205bcd4dc31c2745e2a204c4` |
| `product/runtime/multidimensional_stage.py` | `c5f0b4d9b0e388628d42d3f0f8337884243704c2c7726c3396440cd775948e61` |
| `product/runtime/research_consumption_audit.py` | `c633801f3c5086279468d653659787330ff11fdf0de476977c7fea68d1f36580` |
| `product/web/read_only.py` | `6aef6852c01b3f3fe5678cb56684b366951d52ecc32d950d04c8eb934942dc0a` |
| `product/council/common_stock_research.py` | `1480740154615eff3bf4915913dc4111f99d08431232809d6833e11340d2c081` |
| `product/council/multidimensional_research.py` | `eddd245dc135b61d430b89c3231aff364a8b1d19a28c44cc246e5796a8236bf4` |
| `tests/test_hashing_contracts.py` | `07eb541741bac0fdc8d9e149c0888d55320ae78c2094538cc22d9f699797f64d` |
| `tests/test_research_routing_contract.py` | `3e2079eeff344d76685ec14d9a7c078ea9515813939424f5a16ce5fd8fe1a1fb` |

### H13 hash 口径关闭（Task 4.1，2026-09-30）

口径、旧算法、生产/消费关系与兼容边界详见 [hash-contracts.md](hash-contracts.md)。来源 Decimal/日期/时间序列化接入现有 hashing 模块，provenance 保留公开别名；纯 JSON 与来源旧算法明确区分。Hook、资料、普通股、八维、Skeptic、CIO、两类 Eval、计算、引用图及存稿的顶层自身排除均复用对应算法。完整 packet/报告/工具输入输出、原显式内容投影、Markdown 包装对象和文件字节仍不可互代，ratio 顺序未变。

计算收据按文件行、工具输入/输出按 calculation、Memory 按内容投影版本、提交按具体存稿、冻结 CIO 按文件字节定位。关键错误保留原码前缀，追加 kind/algorithm/location/expected/actual；身份/权限/业务绑定错误仍用原专门错误。独立脚本 Hook 可正常加载共享模块。现有正式写入仍用对应旧算法，v2 仅显式 opt-in，没有全库迁移或重写历史报告/数据库键/版本锁。

实际执行（各集合重叠，不累加作独立样本量）：

- `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_hashing_contracts tests.test_multidimensional_references tests.test_eval_handoffs tests.test_native_output_handoff` → **50 tests / OK（11.497s）**；session 9559。
- `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_hashing_contracts tests.test_eval_handoffs tests.test_runtime_eval_job tests.test_native_invocation_validation tests.test_calculation_handoff tests.test_multidimensional_references tests.test_research_handoff_consumers tests.test_research_memory tests.test_cio_artifact_reading tests.test_skeptic_artifact_reading tests.test_targeted_research_closure` → **108 tests / OK（39.504s）**；session 99110。
- `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_hashing_contracts tests.test_multidimensional_references tests.test_calculation_handoff tests.test_research_submission tests.test_bounded_research_submission tests.test_native_invocation_validation tests.test_native_output_handoff tests.test_eval_handoffs tests.test_eval_execution_proof tests.test_runtime_eval_job tests.test_council_semantic_handoff tests.test_common_stock_semantic_handoff tests.test_material_semantic_handoff tests.test_skeptic_semantic_handoff tests.test_cio_handoff tests.test_cio_reference_handoff tests.test_research_handoff_consumers tests.test_research_memory tests.test_cio_artifact_reading tests.test_skeptic_artifact_reading tests.test_targeted_research_closure tests.test_research_materials_stage tests.test_common_stock_research_contracts tests.test_multidimensional_stage tests.test_independent_skeptic_stage tests.test_predecision_cio_stage tests.test_runtime_foundation` → **599 tests / OK（192.263s）**；session 71146。
- `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_hashing_contracts tests.test_research_memory tests.test_local_revision tests.test_bounded_research_submission` → **76 tests / OK（9.872s）**；session 24716。
- `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_hashing_contracts tests.test_local_revision tests.test_bounded_research_submission tests.test_skeptic_semantic_handoff` → **71 tests / OK（41.362s）**；session 52638。

599 项启动后仅追加 Memory 原投影校验定位诊断，76 项负责该最新差异；随后仅追加局部修订 first-Stop/binding 的 envelope 诊断，71 项负责该最新差异。不能把此前已加载的模块冒称在599项里重新执行了最后的诊断。其余生产/消费影响复用599项，最后两组补充对应实际变更，不重新跑全仓或完整 Gate。

正例来自实际本地 producer/Hook/MCP/冻结副本消费者；负例包括类型/文件/对象口径误混、键序/空白、自身字段、对象篡改、未知算法/协议、Decimal/时间/Unicode/非有限数、计算错输入/事件、历史包搬移和旧引用篡改。当前 Schema 非有限值约束保持，旧裸 digest 的类型只从契约获得，不能靠64字符长度猜测。事实投影和序列化版本分别定位；历史包、原始数据和其它暂停任务未改。

Task 4.1 关闭，总进度 **18/30**。H11 整项与 H18/P2/P3 仍按剩余任务收尾，不能代为勾选。真实 LLM/产品执行仍 NOT_RUN：未启动 Smoke、Execution Replay、Runtime Eval Runner、Regression、Calibration、Ablation、Promotion 或完整 Gate，未归档/提交/推送。契约兼容不代表研究质量或候选晋升。

| 文件 | 本节实现后完整 SHA-256 |
| --- | --- |
| `product/runtime/hashing.py` | `58b108318363b1cbd6dde1af23c85f429e28543e45040e43669179a147b95387` |
| `product/mcp/provenance.py` | `dd3e4d166117e281eec10a64424d9c32f447df2e7a80a23fb4108dd46ec252cb` |
| `product/runtime/codex_hook_recorder.py` | `ab1aea804bee9e7e8ffad70473fb24c5deb674146b7316998bd03f6b93564ade` |
| `product/runtime/invocation.py` | `ce5ec1550e7696f90f1fb7a76867c40e62302b8c877a7f2fd73af8cdfaa1c4cf` |
| `product/runtime/multidimensional_references.py` | `d00fab712be54fdd6062f29b38f31dc736602fd946310a6eb7d1b17ccd32f509` |
| `product/runtime/research_submission.py` | `3dda7a6743be70746685856f3dda861de96dcb16fdee9abd0e5abfbeee4102b1` |
| `product/runtime/calculation_handoff.py` | `78ee3fe556c12d6462ef8e2dc0715ba0f1f4cc211e79d14c6fcf1d206ab0457a` |
| `product/runtime/local_revision.py` | `fabcff01859ffe242fe1c426e50c2a4399380349907876d81b3e512c8773d7f7` |
| `product/runtime/common_stock_stage.py` | `652e0dda22df8fc41ec0febc62a904a8a4280aaf88edbb0857f832b8e1275d91` |
| `product/runtime/multidimensional_stage.py` | `3070df412a245d3b428dcab666b31bb54f3edb5b1a99f527a42f1445ef50c4dd` |
| `product/runtime/research_materials_stage.py` | `b67d7a4a6af5dbf85398709928d1292751af74c9ec9171e020e090f8d5c4ed84` |
| `product/runtime/independent_skeptic_stage.py` | `2216827d2db022a6daf942daa2d7516c7ba9a98dd802b47e2a9eb950b7eaf3e9` |
| `product/runtime/predecision_cio_stage.py` | `3ba4aff03e09b9af2c64651bf7eb37d8073b91f73580a67e4c61e413c10305b8` |
| `product/runtime/common_stock_eval.py` | `3fad7323c2815ec2b10aeefcb54bb516e7351f4301f84f9dcb6eeed0367f00be` |
| `product/runtime/runtime_eval.py` | `07a22171985af60027956c3f1392cc6bfa3831ca7a83794aecec9ab8a32d78cf` |
| `product/runtime/research_memory.py` | `a62815c2f1f731039e7063b1a2ffc79636ec2129fabbdf87b5350208e437d7ff` |
| `tests/test_hashing_contracts.py` | `55f596eef4d0ff4f7547286744ad6eb12af4a00d842eb46521e0639ef123277a` |
| `openspec/changes/simplify-research-handoffs-and-acceptance/hash-contracts.md` | `baafed74943134748d47cc53c0b408781b1271369debcb45ec2a7b1093c7a0e3` |

### H18 分层状态接缝关闭（Task 4.5，2026-09-30）

对应规格：`multi-dimensional-holding-research/spec.md` 的“研究结果必须区分进程契约来源与内容”；Design H18。复用既有产物和校验，不新增评分器、Agent、权限层或总分。

- `multidimensional_output.project_research_status` 从已校验报告、覆盖行及进程记录投影进程、契约、来源限制、作者声明、独立内容复核、下游和晋升状态。作者 `evaluation_status=PASS` 不成为独立复核，现有报告本身只证明 `NOT_REVIEWED`；没有实际来源状态时保留 `NOT_RECORDED`，不推断资料完备。空输入是 `NOT_RUN` 而不是产品故障。
- 当前 finalizer/canonical 装配仅签发结构可消费标签；有效报告继续保存。实际失败任务使整批契约为 FAILED，退出 0 不能覆盖失败。消费证明仍可对自洽的失败包返回 artifact 校验 PASSED，但其分层契约 FAILED、下游结构状态及原始声明均同时公开，不能解释成研究完成。
- CLI JSON、进程记录、中文包报告、浏览器和下游消费证明使用相同投影。浏览器仅在进程记录与实际目录/报告 run 绑定时读取三个公开进程字段，保留文件完整 hash；不显示私有环境。冻结报告 JSON、历史摘要/hash 和原运行文件不回写。
- 用户中止返回 130，明确 USER_INTERRUPTED，未知子进程实际退出码为 null。Hook 已保存的稿件和 6/1/1 状态保留；Start 无 Stop 保留为未形成终态，不伪造失败 Stop。未取得的管道输出显式 `captured_process_output_complete=false`，不声称事件捕获完整。
- 反证是显式研究入口，不要求作者先自认证“研究通过”。实际结构绑定和原核心覆盖要求仍执行，原允许来源受限状态不变；作者已明确声明内容失败的报告拒绝进入正向依赖。当前结构可读/NOT_REVIEWED不自动推进反证、CIO、Risk或晋升。原 Skeptic 首轮隔离不变。
- 实际负例把临时冻结副本保留为合法结构并声明内容 FAIL，同时保留旧 READY 标签；消费者重新读取底层报告得到失败状态，显式反证准入拒绝。没有只篡改上游 PASS 摘要模拟缺陷，也没有改真实历史包。

实际命令与结果（重叠集合不累加独立案例）：

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_terminal_projection tests.test_multidimensional_stage tests.test_targeted_research_closure tests.test_multidimensional_research_contracts tests.test_local_research_browser tests.test_independent_skeptic_stage tests.test_cio_artifact_reading tests.test_research_handoff_consumers tests.test_skeptic_semantic_handoff tests.test_predecision_cio_stage
```

**284 tests / OK，95.063s，session 14237**。实际本地 Hook、CLI、冻结读取器及真实 finalizer，外部模型进程与 Agent 消息由确定性 fixture 模拟。执行期间追加的 CLI 输出读取、旧 READY+内容 FAIL 负例及 canonical 返回投影由下面最新补充覆盖，不把旧已加载模块冒称最后快照。

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_terminal_projection tests.test_multidimensional_stage.MultidimensionalStageTests.test_canonical_assembly_imports_company_reports_and_excludes_drifted_supplement
```

**7 tests / OK，4.096s，session 72688**：实际 CLI 退出 7/130、完整 6/1/1、来源限制、结构 PASS/作者 FAIL、未运行/未复核、未终态中止、旧 READY 不能掩盖内容失败，以及中文/浏览器/消费投影一致和原文件不改。最新版本影响检查由284项及这一受影响补充共同承担，不宣称全仓测试/真实内容验收。

先前中间快照 **243 tests / OK，61.011s（session 25957）**；随后的242项出现11个 errors（session 88703），均是旧反证入口只接受 READY 标签，与新的结构/内容分离不一致。该失败原样保留，修复为实际绑定/核心覆盖及明确内容失败检查后，10项定点及284项恢复通过，未删负例或改为无条件准入。既有 SQLite ResourceWarning 不是断言失败，本轮未扩修数据库。

`openspec validate simplify-research-handoffs-and-acceptance --strict` valid；`git diff --check` 无错误。Task 4.5 关闭，总进度 **19/30**。P2/P3、有限真实补验、独立复核及人工批准仍未完成；原八维 Change 继续暂停。本节真实模型、Smoke、Replay、Eval Runner、Regression、Calibration、Ablation、Promotion、完整 Gate 均 NOT_RUN，未归档/提交/推送。

| 文件 | 本节实现后完整 SHA-256 |
| --- | --- |
| `product/runtime/multidimensional_stage.py` | `606129c05d6933ba5cd2163b2dccc1828c9be533eedc982563c25d45af234164` |
| `product/council/multidimensional_output.py` | `4cab9d5dbf2388a2c0ff2646a8f9f25d4e2902d301d954c8c713897caeb4495f` |
| `product/runtime/independent_skeptic_stage.py` | `151a6c588c8e3edb831efcfb76a88f52ec240902e2ddc6f0510063dcebd8be05` |
| `product/web/read_only.py` | `7c5cc932ba21c67084134dc7e9469f1bf098b76d3168b021fa4f3413ed4dc9a9` |
| `product/web/rendering.py` | `893d48b2e3df4e64fb86c860e65dbe2eea6e5216f64fa5baeefbd201aa06ab35` |
| `tests/test_research_terminal_projection.py` | `ab8289a4faf4bc746eebd231313de219492ff500661ed48a75520869d18d4e08` |
| `tests/test_multidimensional_stage.py` | `53a9c8de71d17bec473f5ce40e0bea71686770e4177a9e13a0841c664963c59f` |
| `tests/test_independent_skeptic_stage.py` | `43a080f37fbd25c092aed03ecd5d6caa4fc1f4f186571e0fd5cfc0ef6e066eac` |

### H11 局部修订扩至普通股/资料准备；H19 交付分层与历史义务整理（2026-09-30）

#### 实际实现与完成边界

- 复用现有 `local_revision`、可信 Start/Stop 绑定及追加原稿，而非新建运行框架。普通股和资料准备原先在首稿结构失败后直接终止；现在 Schema 错误或可定位的引用选择错误允许原 Agent 同一会话的一次限定字段修订。模型仅收到短基础稿引用、允许路径及定位反馈，不抄 hash、不重发整稿；原草稿/约束包留私有运行目录且不可覆盖。
- 第二次先验证原身份与剩余额度，再保存补丁并解析；非授权调用不占目标额度也不写新原稿。绑定漂移、完整性错误不进入修订，第二次失败终止，第三次拒绝且不写第三稿。补丁后仍走各自原完整 Schema、Evidence、计算及工具审计/文档校验，不由 Python 猜改研究。
- 资料文档误选错误增加 `selections[n]` 定位，原错误类别与拒绝要求保持；成功选择与仍未知文档分别经过真实 Hook/MCP 装配，源文档字节被改仍立即拒绝且没有修订许可。并发测试保留“修订中的子任务不释放槽位”的真实事件要求。
- 多维正式/首次定点视图不再靠字符串 replace 改写既有 task instruction。当前任务生成使用中立引用/草稿指引；业务要求保留，两个交付视图的短引用、draft Schema、提交工具/凭据、两次上限和计算选择契约等价。既有依赖报告与正文未被裁剪。
- 四个开发角色明确 producer/consumer、语义与机械字段所有权；Reviewer 分层看结构/语义/来源/晋升，Eval 只按实际注入阶段和原 rubric工作，不默认拉起产品或完整 Gate。原 dev_eval `gpt-5.6-terra`、其他角色既有模型选择、沙箱和工具/App设置均未改变，不承诺模型自动跟随主线程。
- **Tasks 5.1、5.2、5.4、6.1仍未勾选**：局部成果不能代替全部当前入口的修订覆盖、完整输入保真/成本记录及产品角色/方法分层。CIO/Eval等尚未被本节证明有统一的有界局部修订；需要继续按剩余任务检查，不把仍活跃入口改称历史规避要求。

#### Task 6.2 关闭：当前义务不再累加历史重跑债务

- 原八维 `tasks.md` 的106项原文字、92项勾选和14项未完成、旧预算/失败全部按原字节保存至 `history/tasks-before-consolidation-20260930.md`，SHA-256 `61d94dc1f2c4d9edb5a8533e4bf693930e35d82da5d5a8d63f7346f397d73983`。
- `task-history-index.json` 保留全部原编号/状态/行号，并逐项把14项未完成映射到当前5个收尾职责；全部 `coverage_status=NOT_CLOSED`。历史已执行而内容未过不是 PASS，也不要求每个旧批次重跑成功。任务数量缩减不是实现进度增长。
- 当前只保留8.40（中断批次的最终验收职责）、5.3（同批八维最低内容）、6.16（引用语义）、5.6（同次质量/成本）及5.5（独立复核/人工批准/收尾），五项均未勾选。三项内容职责用同一最终候选，不扩成三轮新运行。
- Proposal/Design和原验收记录仅加当前PAUSED与历史计划适用范围说明；四份原delta specs逐字节不变。保持原同批八维内容8/8、最低内容、PIT/来源、成本与人工批准标准，不改历史运行包、锁或金融代码。
- 原八维仍PAUSED，至少180子/37父的历史启动账保留；旧181/37上限不恢复，本 Change 的建议3子/2父也未继承。当前没有新增模型授权。
- **Task 6.2关闭，总进度20/30**；原八维没有被标记完成，不同步/归档/提交/推送。

#### 实际命令与结果

以下都是确定性本地 Hook/MCP/装配器及模拟作者消息，公开来源客户端被fake替代；不是实际 Codex/LLM研究，重叠集合不累加成独立案例。

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_local_revision_handoffs tests.test_common_stock_research_contracts tests.test_research_materials_stage tests.test_common_stock_semantic_handoff tests.test_material_semantic_handoff tests.test_local_revision tests.test_bounded_research_submission tests.test_skeptic_semantic_handoff
```

**221 tests / OK，92.701s，session75966**。此时尚未增加材料文档选择定位和其新负例；后续受影响补充如下，不把旧模块已加载的检查包装成最新全快照。

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_instruction_layering tests.test_multidimensional_stage.MultidimensionalStageTests.test_formal_model_context_keeps_exact_catalog_and_source_limits tests.test_multidimensional_stage.MultidimensionalStageTests.test_formal_hook_delivers_measured_compact_context tests.test_multidimensional_stage.MultidimensionalStageTests.test_initial_hook_context_is_bounded_and_keeps_exact_query_ids tests.test_research_local_revision_handoffs tests.test_research_materials_stage.ResearchMaterialsStageTests.test_two_material_dispatches_can_finish_before_later_tasks_start
```

**12 tests / OK，3.859s，session70823**。两条真实序列化路径保持任务文本和研究问题、不调用其 `replace`；派生draft及工具选择等价，开发配置模型/权限/链接正确。局部修订覆盖正确/错误证据、正确/错误文档、未授权、越界、再验及耗尽。

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_acceptance_history tests.test_research_instruction_layering
```

**5 tests / OK，0.255s**：历史原字节、全部状态与逐项映射、当前五项仍未完成、零新增/继承预算、四份原规格字节不变及链接均可解析。

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_local_revision_handoffs tests.test_common_stock_research_contracts tests.test_research_materials_stage tests.test_common_stock_semantic_handoff tests.test_material_semantic_handoff tests.test_local_revision tests.test_bounded_research_submission tests.test_skeptic_semantic_handoff tests.test_multidimensional_stage tests.test_research_instruction_layering tests.test_research_acceptance_history tests.test_eval_execution_proof
```

**312 tests / FAILED（1 error），114.243s，session84005**，必须保留该真实结果。311项通过；唯一错误是原材料失败场景测试驱动在第一稿 `SubagentStopBlocked` 时就调用 finalizer，正确被拒为 `RESEARCH_MATERIALS_OUTPUT_MISSING`。生产契约未放宽，测试驱动改成原合成作者再交同一非法选择的受限补丁，真实第二次EXHAUSTED后再验证失败留痕。最终补充覆盖这一测试驱动变化及全部本轮材料路径：

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_local_revision_handoffs tests.test_research_materials_stage tests.test_research_instruction_layering tests.test_research_acceptance_history
```

**34 tests / OK，6.554s，session25207**。312项其余未变化的通过范围复用，34项承担最后仅测试驱动差异；不重新启动全仓或完整Gate，也不将312的失败输出改为PASS。

其它中间失败保留：新测试误用公司字段 `summary`（真实为 `research_summary`）导致3 errors，session15280的257项还发现并发测试旧假设；改为各角色实际Schema字段并验证修订阶段槽位后5项OK。两条交付新测试最初把未启用提交工具的基本面fixture当研报v6，12项出现1 KeyError（session89427）；改用实际启用v6的原研报producer，随后上述12项通过。均未改产品字段或权限迁就测试。

`openspec validate simplify-research-handoffs-and-acceptance --strict`、`openspec validate complete-eight-dimension-source-consumption --strict`均valid，`git diff --check`无错误。没有实际Smoke、LLM、Execution Replay、Runtime Eval Runner、Regression、Calibration、Ablation、Promotion或完整Gate；研究质量和候选晋升仍未验证。共享dirtytree不等于本轮可提交范围。

| 文件 | 本节最后检查的完整SHA-256 |
| --- | --- |
| `product/runtime/codex_hook_recorder.py` | `1eea3f6163d3d61873ce275410ddfeac901e9d6a77578312b51aa04bbcf7053b` |
| `product/runtime/research_materials_stage.py` | `acc1df56b531cb289a169790ef9ed0fec54a1c5706502a1f9f2de66e798703d7` |
| `product/runtime/multidimensional_stage.py` | `9b40e8dfebbb98818ae4fe576172222eddc517f6c07bead00526c8958f218987` |
| `tests/test_research_local_revision_handoffs.py` | `8d6b29fd06d44abf45f2e17acb63a15c15b0bf0b5194d64e91e320b98a3f3998` |
| `tests/test_research_materials_stage.py` | `e6e9845e290fb68e6520f94313bcc12bd2f951d8ae4de27d6399164bcc34a05a` |
| `tests/test_research_instruction_layering.py` | `573d59c66b8d3e514bf499b4cf939c98618602234149a54cd2a649854c07fca6` |
| `tests/test_research_acceptance_history.py` | `b2542ecba9d9e9c501654deae348c3306fffec452eeb643878afcea58d6f122e` |
| `.codex/agents/dev_architect.toml` | `f38e91b24ef384b0f8e27828c9676e8a939c96deda61a492d3c08b16b5fb84e8` |
| `.codex/agents/dev_contracts.toml` | `a6595fa5215f772380b874f0d95d18c54dac557bd127015dcfb86ecbc599a9a5` |
| `.codex/agents/dev_reviewer.toml` | `cc15695dd949e6f61179e07138c3adb1e086ac11b69101acd8499408ae113482` |
| `.codex/agents/dev_eval.toml` | `d70b07d3ac8cb895496e4444d1256b5b1755773af75b29724e1555f4abf06283` |
| `openspec/changes/complete-eight-dimension-source-consumption/tasks.md` | `89235d7676ec83a60aaf8fa4ddf17bde8d2d3e7151020f38d737d409b64f741d` |
| `openspec/changes/complete-eight-dimension-source-consumption/task-history-index.json` | `8219245c701dcaf8a6dd719960c44b9acfdd67920ee9f362e84e472267423fe3` |
| `openspec/changes/complete-eight-dimension-source-consumption/history/tasks-before-consolidation-20260930.md` | `61d94dc1f2c4d9edb5a8533e4bf693930e35d82da5d5a8d63f7346f397d73983` |
| `openspec/changes/complete-eight-dimension-source-consumption/proposal.md` | `7c7634868ad424904cfc101553b7b9dc26a5723c6725fd52ffb2eeb15da8392e` |
| `openspec/changes/complete-eight-dimension-source-consumption/design.md` | `d2472726ab891c4eec5add1004ef1ece6cb14462e69d0ad42e2cda30e75680aa` |
| `reviews/development/complete-eight-dimension-source-consumption-acceptance.md` | `8fe70728048d64ae9655184caee321585bfda68b3176bf205a06537ebcd57fa5` |

### H19 角色/方法/阶段分层关闭与 P2 用量口径修复（2026-09-30）

#### 实际差异及完成范围

- **Task 6.1 完成，总进度21/30**。沿用前节已解析验证的四个开发 Agent，不新增 Agent/Skill/调度器，不改变模型配置、实际权限、根开发优先级或既有阶段开放范围。
- Company Analyst 通用定义与实际普通股阶段定义只维护职责、隔离、任务契约、工具权限和提交边界；公司研究、期间/主体/单位、可比性、反证、观察基线及估值的方法留在已有 company-research/valuation。补齐原通用定义中较精确的多期间 DERIVED/TTM 说明、比较限制字段与部分期间 EPS 表述，没有把这些方法删除来凑减量。
- 精确引用规则服从本次 citation_contract；新协议选择短引用，旧模式选择原始 ID。正式 Evidence/source/time、计算数值/原值/输入血缘/路径仍由可信运行层还原，不让模型重新抄写。同行和技术 Skill 同样区分新模型草稿与旧正式记录，不放松事实、关系、参数或权限校验。
- PREDECISION_CIO_SYNTHESIS 的 MRVL 样本及用户清仓陈述从常驻产品 AGENTS/Skill/CIO 定义迁至实际生成上下文的 stage_constraints。原 RESEARCH_TARGET 校验与请求 Schema 未修改：非目标证券、PORTFOLIO_ADVICE、当前账户适配及未经允许的动作仍拒绝；Risk仍NOT_RUN，用户陈述明确是USER_REPORTED_NOT_ACCOUNT_EVIDENCE，不升级为账户事实或市场 Evidence。
- fixture/live Smoke Prompt 改为按已验证模式组合工具名、路径、保存方式和终态说明，不再对已生成文本连续replace；冻结派发消息未改写。旧live入口仍拒绝实际启动，未因此恢复旧产品路径。
- 本轮显式由文件字节计算并同步当前version-manifest中council_skill/cio_agent/company_agent三个资源hash；仅这些资源hash变化，没有更改候选/组件版本、模型路由、生产指针或任何历史运行锁。最初旧hash导致的拒绝是有效安全拒绝，未关闭检查或用新hash回填历史。
- **Task 5.4 仅部分完成，仍未勾选**。旧会话累计usage使用最后一条真实累计通知，不相加更新，不将缺失/bool/负数补0，不把通知数冒充模型调用数；缓存是输入token子集，不再次加进输入。父/子记录分别保留，观测会话之和明确不是全链成本，延迟不累加重叠子会话。public usage拒绝负值及缓存大于输入。
- SubagentStart实际额外交付文本记录UTF-8字节/hash，并在可取得同一冻结packet时给出完整表示基线；这是表示比较，不是历史模型或精确token基准。无基线入口标NOT_COMPARABLE。Cost diagnostics复用既有Hook/MCP事件，逐工具记录实际返回字节及缺测次数，规范返回与短引用返回列分开、不相加；未取得父/子token及费用就保持null/NOT_OBSERVED。没有新增观测平台或付费基准调用。
- Tasks5.1/5.2/5.3/5.4及6.3–6.7仍按其原范围待完成；本节不能替代所有角色局部修订、完整资料等价性、唯一调试身份、真实运行或独立内容验收。

#### 实际命令、结果与失败恢复

所有以下unittest中的模型响应、来源客户端和执行事件是合成测试输入；仅执行真实确定性producer/Hook/MCP/消费者，**产品LLM调用为0**。

1. 用量接缝初轮：

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_cost_diagnostics tests.test_eval_execution_proof tests.test_native_execution_proof tests.test_research_consumption_audit
```

初轮29 tests/OK/1.950s；新增全工具缺测计数后最终同命令**30 tests/OK/1.912s**。验证累计通知不重复相加、未知不是0、缓存子集、父子范围、非法public usage、真实Hook额外交付hash、篡改拒绝及现有CIO/Eval证明消费者。

2. 角色/阶段/生成Prompt的初轮70 tests（1.163s）为真实FAILED：3 failures、16 errors。三个当前资源hash未同步造成15项准备拒绝及一项缺失下游文件；同步本轮资源hash后解除。两项旧配置测试依赖中文逐字或Role中的工具名字列表，已改实际profile/权限/工具集合解析。另1项test_governance根sandbox_mode断言仍来自用户已存在的danger-full-access配置，非本轮修改，**未修配置或伪称该项PASS**；本轮限定复查不将它列为已通过证据。

3. 同步hash后的60 tests（4.452s）剩1项FAILED：旧predecision测试按“MRVL对基准/MD&A”固定句子判定通用Prompt。改为实际阶段context、request证券、允许级别、Risk状态、用户信息分类和锁定指令交付核对；未以另一组中文句子替代旧断言。查询绑定/越权拒绝由同模块真实工具接缝测试继续验证。

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_instruction_layering tests.test_predecision_cio_stage tests.test_live_cio_final_response tests.test_native_output_handoff tests.test_product_config tests.test_council_semantic_handoff
```

修正后73 tests/OK/10.531s。包含fixture Council原生语义、Risk/NO_TRADE负例、live退役拒绝、source/report读取绑定及模型前阶段拒绝，不启动产品。

4. 共享交付及版本接缝：

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_instruction_layering tests.test_research_local_revision_handoffs tests.test_research_materials_stage tests.test_common_stock_semantic_handoff tests.test_skeptic_semantic_handoff tests.test_eval_handoffs tests.test_component_versions tests.test_research_cost_diagnostics
```

95 tests/OK/57.742s；过程中随后完成普通股实际定义及行业/技术的最后分层调整，所以该记录用于未受后续差异影响的接缝，不冒称覆盖最终全源码快照。

5. 最后角色/Skill/工具接缝快照：

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_instruction_layering tests.test_product_config tests.test_predecision_cio_stage tests.test_research_cost_diagnostics tests.test_common_stock_semantic_handoff.CommonStockSemanticHandoffTests.test_actual_start_and_stop_keep_research_and_derive_exact_calculation_refs tests.test_eval_execution_proof tests.test_native_execution_proof tests.test_research_consumption_audit
```

**66 tests/OK/4.031s**；此后仅补cost audit逐工具计数及其1个测试，受影响范围由第1项最后30tests验证，不重跑无关整批。

6. Skill创建指导要求的通用quick_validate已实际尝试：

```sh
/private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python /Users/caihaoming/.codex/skills/.system/skill-creator/scripts/quick_validate.py product/skills/company-research
/private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python /Users/caihaoming/.codex/skills/.system/skill-creator/scripts/quick_validate.py product/skills/valuation
/private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python /Users/caihaoming/.codex/skills/.system/skill-creator/scripts/quick_validate.py product/skills/portfolio-council
```

本机venv/系统及已捆绑Python均缺PyYAML，检查器在导入阶段退出1，属于环境缺依赖而非Skill断言失败，**不能写该检查器PASS**。未安装新依赖。仓库原有test_product_config已经覆盖实际Skill名、frontmatter/version、注册、链接与协议结构；上述66tests及版本接缝是本轮对应检查的有效替代证据，不冒称真实Skill推理质量通过。

7. `openspec validate simplify-research-handoffs-and-acceptance --strict`有效；`git diff --check`退出0。原八维Change仍PAUSED，未修改其最低规格、历史包、DB/checkpoint或预算；未启动Smoke/Replay/真实Eval/Regression/Calibration/Ablation/Promotion/完整Gate，未归档/提交/推送。工作区既有无关修改（含根开发沙箱配置）保留，未以这些确定性测试宣布Change或候选晋升通过。

#### 本节源码标识

下表由实际文件字节SHA-256生成，不要求LLM抄写给产品Agent；记录本轮最后快照，不重写前节历史hash，不新增产品锁。

| 文件 | SHA-256 |
|---|---|
| `product/runtime/execution_proof.py` | `a29ad406f496f242784347d5f7bf136f0cbf082744237303dbf10f043d5fe898` |
| `product/runtime/eval_execution_proof.py` | `381a5091afc4689bff67b308ae9166d0f37e34e3bf1e8da19b215e1a6d646df4` |
| `product/runtime/codex_hook_recorder.py` | `4c0b8db179a22157a970ce5492111dac1d19de64c2940f0ee63b23d2be408988` |
| `product/runtime/research_consumption_audit.py` | `b6a8ebd89a39e3127c9d221176abc42ebdaedd7b2c742c0f3aab1bd643c3f658` |
| `product/runtime/predecision_cio_stage.py` | `79ba0d6f3f6942861425ddf52aefd498493b034fe7193a246549a4c6bba617bb` |
| `product/runtime/smoke_prompt.py` | `a0c789bbb44e5b3c7983118e7d598f510116d816dca541860b23b620217edbe0` |
| `product/.codex/agents/runtime_company_analyst.toml` | `179e4e66bbcd89145b751f0fe7348b0a222aed2ff0619387ab77219dc91b070f` |
| `product/.codex/agents/runtime_company_analyst_common_stock.toml` | `bd5fd35e8c224385694e0472034d1ba9c4c1e2d20e2383141ee396ae3d8ca72e` |
| `product/.codex/agents/runtime_cio.toml` | `4fea35df67d05942e374fd4491289035b2fbc7cc3cc7f3897f4baa86eea808a2` |
| `product/.codex/agents/runtime_market_catalyst.toml` | `70d2251922de82ab7fae9b0611828e0ca2d4f064f1bd08308ac2ceae016ef488` |
| `product/skills/company-research/SKILL.md` | `fdf6c8e0cd7df283673496d4e9822ee005f88afdf3b7fc7978dff8612e7cc1e4` |
| `product/skills/valuation/SKILL.md` | `25b0cb9b159b9292f9f615daf877be9c744314827254e57fae920097d3fe8f9e` |
| `product/skills/portfolio-council/SKILL.md` | `430f2440c50f1ee17d5bb0b1e69f3f7d71acf329f5ddbb193e8870c6d9e22e8a` |
| `product/skills/industry-comparison/SKILL.md` | `2d1942fb5678d7d507cb098b6edbea55b60f65e6613ef29f7f850b45f99d3e8d` |
| `product/skills/technical-structure/SKILL.md` | `aab8c755cd51a67cd469c7454983d491691f36d6361a3c61f0bada6b29669e4b` |
| `product/AGENTS.md` | `e64608371c17dc14ffbfd3e69dd996fb8c20f2af91b7c78615f0e835ad1457f7` |
| `product/version-manifest.json` | `2ba0d33dff7aeaec6b5db9c47c3360e573e255689a1e98f487b68bec97aaffd1` |
| `tests/test_research_cost_diagnostics.py` | `c8aa1590903af77ddfdc582d9f2c77e83a47e675808df2b842027a45e89632f5` |
| `tests/test_research_instruction_layering.py` | `e76e7e544a36846f39df4b8f0df0a132eeb65520a2802c40892d3e36c64e24fb` |
| `tests/test_product_config.py` | `df4271e6b30847041ceafff292c4ae75b0ef67bc30f4431bf7ac757adea4655a` |
| `tests/test_predecision_cio_stage.py` | `f680450c5097c34a02d1db8f51820befaa5d3819e0c2ae1c4b8528ab19e59e3e` |
| `openspec/changes/simplify-research-handoffs-and-acceptance/tasks.md` | `d3280f129b38b19bacfa3a46a7f20e6b639b10bf97de660ed40aec8ea6f77a78` |

### P2 Task 5.3：最小闭包、唯一执行身份及严格复用（2026-09-30）

本节关闭 Task 5.3；整体进度 **22/30**。Task 5.1、5.2、5.4 及 6.3–6.7 仍未完成；不代为关闭原八维 Change。

#### 实际修复与范围

- 首差异：宿主多维新准备沿用外部 Gate 的 run_id；同一来源资料不能代表同一次执行。正向多维宿主新准备改为 UUID 身份，显式 `--reuse-frozen-gate` 创建本次 Gate 视图，原 Gate 字节作为冻结审计输入保存。原 source run/hash、事实内容 hash 与本次 run/hash 分开；不是修改历史版本锁或恢复模型预算。
- 复用原 evidence_gate、prepare、宿主 launcher 及拓扑闭包；材料准备与正式研究共用本次执行身份。原值、期间、单位、来源时间、截止点、排除记录均不变；来源 hash/冻结副本/执行视图不符即失败。反证仍采用原同批身份规则，禁止跨批 Gate 重绑。
- 原采集清单仍从原目录按实际 hash、cutoff、allowed Evidence、scope 读取；同行合并后的 base Gate 只在显式新执行资料复用模式下可保留原采集 run_id，内容 hash 和来源绑定不得跳过。
- OPTIONS 实际模拟 Hook/launcher 只派发一个任务，基本面→研报只派发最小闭包；无关六维、Skeptic/CIO/Risk 不隐式启动。缺依赖、非法/循环/重名任务拒绝，不以定点执行证明冒称整批8/8。
- 同包重试复用上游还须读取原报告与 Start/Stop 事件，并重验输入、允许集、cutoff、Agent/Skill、模型、Schema/工具拓扑及研究共享实现文件指纹。指纹是局部复用的确定性比较输入，不新建晋升锁平台。旧包缺该证明或当前配置漂移保持不可复用；历史 artifact 读取不因此补写证明。
- 未重新访问来源、未启动真实产品模型。模拟子进程/来源状态用于真实确定性 producer→consumer 接缝，不作为 Codex/Skill 实际推理证明。

#### 实际检查与结果

1. 初轮：
```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_debug_entry tests.test_multidimensional_references tests.test_host_proxy_scripts
```
81 tests / FAILED (2)，38.601s。两处来自同一个已有用例仍把已移入 Skill/任务契约的中文措辞强制留在常驻 Agent 指令；另因 TestCase 直接导入被 unittest 重复收集。改为实际 Skill 注册/资源 hash/交付权威契约检查，测试 helper 改模块引用；未修改金融语义或权限使测试通过。

2. 修正并加入 base Gate 身份分离：
```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_debug_entry tests.test_multidimensional_references tests.test_host_proxy_scripts tests.test_multidimensional_stage.MultidimensionalStageTests.test_merged_live_gate_reads_original_preparation_without_rewriting_cutoff
```
45 tests / OK，25.272s。

3. 补 OPTIONS 实际模拟 launcher 的独立任务证明：
```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_debug_entry tests.test_multidimensional_stage.MultidimensionalStageTests.test_initial_targeted_host_execution_finishes_without_retry_base tests.test_multidimensional_stage.MultidimensionalStageTests.test_initial_targeted_host_blocks_downstream_after_invalid_upstream tests.test_multidimensional_stage.MultidimensionalStageTests.test_initial_targeted_host_rejects_tampering_and_unknown_task
```
12 tests / OK，4.308s；最后补启动前共享实现指纹漂移拒绝后，同范围重验 **12 tests / OK，4.504s**。

4. 受影响材料准备、语义提交、闭包、报告复用及宿主分流：
```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_research_debug_entry tests.test_research_materials_stage tests.test_material_semantic_handoff tests.test_multidimensional_stage.MultidimensionalStageTests.test_merged_live_gate_reads_original_preparation_without_rewriting_cutoff tests.test_multidimensional_stage.MultidimensionalStageTests.test_initial_targeted_host_execution_finishes_without_retry_base tests.test_multidimensional_stage.MultidimensionalStageTests.test_initial_targeted_host_blocks_downstream_after_invalid_upstream tests.test_multidimensional_stage.MultidimensionalStageTests.test_initial_targeted_host_rejects_tampering_and_unknown_task tests.test_multidimensional_references tests.test_host_proxy_scripts
```
**88 tests / OK，31.673s**。随后仅补 initial-task 共享实现指纹漂移拒绝及负例，受影响部分由第3项最后12tests覆盖；不把88tests宣称最终全仓全量检查。

5. `bash -n scripts/run-product-smoke.sh` 与 `git diff --check` 退出0；`openspec validate simplify-research-handoffs-and-acceptance --strict` 报 valid。真实 LLM 调用为0，不运行完整 Gate/Regression，不归档/提交/推送。

#### 源码快照

表由实际文件字节 SHA-256 自动取得，保留前节历史快照原样。

| 文件 | SHA-256 |
|---|---|
| `product/runtime/evidence_gate.py` | `a9849f6becb383f167a66c537c4248b968ca46cbfce04cd6521894fc03459fde` |
| `product/runtime/multidimensional_stage.py` | `9da2ee229f76a8e6c0d72d94dae66bacd5a2e5df46336416b8c97c13798fbbf7` |
| `product/runtime/research_materials_stage.py` | `3b56818c4b61bab228ab72ebdf20a8c259234e47739bc073e212051e0832a66a` |
| `product/runtime/cli.py` | `b1d37e63819d12e25adf00867050379d34bd05ed3835e4f30698691973ee5e1b` |
| `scripts/run-product-smoke.sh` | `e69e9c6860e385cde47b9728513fe0238445de461a5970595c15fff3a6a554a0` |
| `tests/test_research_debug_entry.py` | `5bc876d84547cb9e09883f5a4276996cfb84278a3e3b5e1c0d18c25de04dbc1b` |
| `tests/test_multidimensional_references.py` | `20204d6f4db68fd7c8860ce1cd9e540ddfa7142dfa28ac3bc1d6e3f933bc01da` |
| `tests/test_multidimensional_stage.py` | `b31d1caf1505587dc43eef297508a74f525e30c86b0d5ca5f11fc1a8a71505a9` |
| `tests/test_host_proxy_scripts.py` | `e9c402c754d004a176bb39a0c3d7c79071c3c326ee5a7990e67286d2ad187e01` |
| `reviews/runtime/runtime-replay-eval-runbook.md` | `ec5b915f8254abc4fa6734f83a3f580b81dceaf6ae168ca3e86317a3d08fdcd4` |
| `openspec/changes/simplify-research-handoffs-and-acceptance/tasks.md` | `8d0b831e4f3e7c4ec9eec0c77a0d128c9ddf5fc8ec3f120274513fcac24ce5c1` |

## Specialist / 普通股评分有界修订与输入投影（2026-09-30）

本节继续当前 Change 的 Tasks 5.1、5.2、5.4，不新增角色或编排器。总进度仍 **22/30**；这些任务只部分覆盖，不能因本节通过勾选整项。真实模型、Smoke、Execution Replay、Runtime Eval Runner、Regression、Calibration、Ablation、Promotion、完整 Gate 均 NOT_RUN，未归档/提交/推送。原八维继续暂停，旧报告、锁、预算及最低内容标准不变。

### 实际改动与生产者—消费者闭合

| 规格 / 任务 | 实现及检查结果 | 证明边界 |
|---|---|---|
| 原 Agent 局部纠正 / 5.1 | fixture Company Analyst、fixture Skeptic 和普通股 dev_eval 沿原 Stop 复用 local_revision；先核对真实派发、Start、父/子会话、Model、输入，再记录首稿和一次局部修订。反馈只给短基础稿引用及已定位路径，技术身份冒用不进入修复 | 实际 Hook 与完整 Schema/业务校验；事件为测试构造，不证明真实模型 |
| 原稿保留、有限额度 / 5.1 | 非法稿与补丁分别保存；第二次失败终止，范围外改动拒绝；错 Model/子会话/冻结输入不占槽位，也不写目标评分草稿。非法评分稿先校验，避免占用正式 semantic-result.json 后无法合法修订 | 测试实际文件及次数，不只断言状态摘要；合法内容 FAIL 仍保存 FAIL |
| 下游执行证明 / 3.5、5.1 | Specialist 保留原 raw_* 的已解析对象 hash 口径；原消息另用 submission_path/hash。执行证明重新读取原稿、约束包、补丁及 Stop 事件，复用实际 resolve 重建，再比较正式语义稿；重新签名的摘要、基础稿/补丁/原消息漂移仍拒绝 | 合成公开遥测用于消费接缝，不当作真实 LLM 证明 |
| 重复交付 / 5.1 | 同一已接受消息的 Hook 重复交付保留幂等性，但重验实际草稿/补丁与正式输出；不同消息不能覆盖。证明读取器校验 duplicate_of 对应的完整原事件关键字段，不把它当新研究稿 | 不新增修订额度或掩盖不同内容 |
| 输入精简 / 5.2 | 当前 Specialist 交付不再重复 Invocation、Skill/hash 包装及 Schema 派生 contract_checks；本地 $defs 无损共享 Evidence 枚举。私有完整 packet 仍用于实际绑定。普通股 Eval 模型视图保留完整 report、中文 report_markdown、rubric、allowed_evidence、hard_gates，移除外围重复身份/路径/锁包装 | 新旧同冻结输入逐字段相等；否定、脚注、冲突、原值嵌套同名键不丢失，不递归按 hash/source 键删资料 |
| 交付统计 / 5.4 | 两 Specialist 与普通股评分 Start 记录真实交付字节/hash，基线是同冻结完整 packet；评分 Start/Stop/dispatch 同时绑定完整 packet 与实际模型视图。沿既有 diagnostics，不新增平台 | 字节不是 token，不把表示基线当历史真实模型成本；token/总费用未观测 |

CIO 两入口及 Runtime Eval 的有界修订仍未由本节实现或证明；其它入口的输入等价与成本关闭矩阵也继续承担原任务义务。没有把仍可写入口改称历史兼容以规避范围。

### 实际命令与结果

```sh
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_council_eval_local_revision tests.test_council_semantic_handoff tests.test_eval_handoffs tests.test_common_stock_research_contracts.CommonStockFocusedEvalTests tests.test_research_local_revision_handoffs tests.test_local_revision tests.test_native_execution_proof tests.test_research_cost_diagnostics
TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest tests.test_specialist_start_context tests.test_start_context_dedup tests.test_native_invocation_validation tests.test_native_output_handoff tests.test_research_debug_entry
git diff --check
openspec validate simplify-research-handoffs-and-acceptance --strict
```

- 第一组最终 **80 tests / OK，21.425s，session43229**。覆盖本节最后源码及补充原消息/基础稿漂移负例；此前同组80项21.152s不冒称包含最后新增检查。
- 第二组 **60 tests / OK，11.227s，session78366**。此后仅执行证明消息检查及评分未授权失败保存分支变化，由第一组重验覆盖；此60项只复用于不受它们影响的上下文、协议和准备/启动接缝。
- 定点补充：34项 / OK（10.728s，session29031），最后原稿/原消息漂移单项 / OK（1.860s，session91344）；与80项重叠，不累加成独立样本数量。
- strict valid，diff 空白检查退出0。输入表示与有界修订的程序检查不等同于实际 Skill 推理、研究质量或候选晋升。

中间失败原样记录：19项中1项失败，因为首版修订包装破坏同消息重复交付的既有幂等性，已修正并重新验证；扩展命令误填不存在的 tests.test_ephemeral_execution_proof，58项中1个命令导致的测试收集错误（并非产品断言失败），其余57项通过，改用实际 tests.test_native_execution_proof 后70项通过；上下文扩展60项初次2个错误，旧测试仍期待已退役的 legacy 草稿降级与 live Council 可写，现改为验证现行权威语义 Schema及明确拒绝，不恢复退役入口、不放松生产校验。

### 本节最后源码字节快照

以下表由实际 shasum 输出生成，仅绑定本节检查现场，不是产品版本锁，不回填任何历史证据。

| 文件 | SHA-256 |
|---|---|
| `product/runtime/codex_hook_recorder.py` | `46423e9addfafa9951ed8d631e0156b2f3adfefb4a52aa2b2190b2ced4f34819` |
| `product/runtime/execution_proof.py` | `f76f09659d721ee38ba70a8d4b6b77dc063ada3e97141183247074b4adbbcfdf` |
| `product/runtime/common_stock_eval.py` | `917dd6d9bfd66580032babf5403060f898b8c2ceb8d8f5d4b55e0b1beda3e04e` |
| `product/runtime/invocation.py` | `d86cda03ccdbd0294211b0381f9d5b4f03b6b14ef9ef18930d75e9e18d913231` |
| `tests/test_council_eval_local_revision.py` | `cf28ad46702120ca92ac9543b38d6fc95ed9da4453c257d6a5b93de9a1044060` |
| `tests/test_common_stock_research_contracts.py` | `49018eee43b1b5efeb13d05134411e89a293cb17fc53e97d2a3f21fd8357378e` |
| `tests/test_specialist_start_context.py` | `9d41aef7c9b8e0388c159a52f9a43a37d85e31ec0ac68e48a7e76ded29ede14f` |

## 两类 CIO / Runtime Eval 局部修订及输入表示（2026-09-30）

本节关闭 **Task 5.1** 的确定性实施义务，整体 **23/30**。Tasks 5.2、5.4 继续归集全部受影响入口的保真和统计证据，不因代表样本测量勾选整项；6.3–6.7 未完成。真实加载和推理仍须按6.4批准后在6.5补验，本节不冒称真实模型通过、原八维同批8/8通过或 Promotion PASS。原八维继续暂停，未新增角色、调度器、数据源或产品权限。

### 修复映射与消费者

| Specs / Tasks | 实际行为与关闭证明 | 限制 |
|---|---|---|
| 原Agent局部纠正 / H11、5.1 | 资料、普通股、八维、独立 Skeptic、fixture 两 Specialist 和普通股 dev_eval 沿原 Stop/MCP 复用基础稿/允许路径；本节补齐两类 CIO 和 Runtime Eval。首稿加一次局部修订，第二次失败终止；允许完整对象兼容运输，但必须由原稿差异检查证明其它字段未变 | 事件为合成测试输入，未证明原生真实加载 |
| CIO / H09、5.1 | fixture Council 和 predecision CIO 都绑定真实主会话 SessionStart/Stop；不编造子 Agent 身份。launch绑定模型、cwd、Prompt和当前实现字节；host 完成、原 finalizer 和执行证明消费者重新读取原稿、约束、事件及 JSONL 主会话/终态消息 | Stop 不执行 Risk、不发布决策；fixture 仍由原 finalizer 到达 Risk，predecision 仍为研究综合/NOT_RUN Risk |
| Runtime Eval / H10、5.1 | 原 eval-execution-proof collector 核对父/子真实身份、模型、指令、冻结 manifest 和输入读取；首稿可定位错误返回 EVAL_LOCAL_REVISION_REQUIRED，不保存正式评分或证明。原父线程原生 send_input 向同一 child 反馈一次，校验父/子日志不可变前缀及子会话实际收到反馈，再解析补丁完整复验 | 不另造 launcher、不由 Python 启动评分器；pending 的 exit0 不是 PASS，只有 VERIFIED 才允许 finalize |
| 完整性与额度 / H11、5.1 | shared verify_binding 在第二稿写入前检查身份、基础稿及范围完整性；未经授权的事件明确不计入槽位。错模型、错会话、配置/输入漂移、基础稿损坏不写目标稿；恢复原绑定后合法第二稿仍可接受 | 攻击不获修复权限；作者已获授权的错误修订仍计入两次上限 |
| 严格消费 / 3.5、5.1 | CIO 和当前 Eval finalizer 重建候选而非信任 SAVED/PASS、changed_paths 或重新签名的摘要。缺原事件、原稿漂移、范围外改动、未知引用仍拒绝；NO_TRADE 的0仍非法，只允许原模型在定位字段改为null | 不自动截断引用、不替模型选择证据、改分或改动作 |
| 无对象边界 / 5.1 | 旧 JSON 语法反馈曾要求整稿重生成，现不进入当前局部修订。保留原文及行列诊断，但不可解析对象没有可证明的字段范围，返回 NOT_ALLOWED；随后整稿提交也不能偷获修订授权 | 行列号不是字段边界；不自动修 JSON、不新增文本修复平台；可定位的合法对象错误仍可局部纠正 |
| 模型视图 / 5.2（部分） | Runtime Eval 保留完整 grader-input.json，模型读取 grader-model-input.json；按已知产物只移除外围重复技术包装。程序由完整输入重建投影，并验证子会话实际完整读取。原值内部同名键、来源/时间、期间/单位、否定、反证、冲突、脚注、风险结果和中文正文保留 | 重新签名的偷换投影也拒绝，历史包不回填新视图 |
| 统计 / 5.4（部分） | CIO 从实际启动文件计算 Prompt 字节及限定输入表示；Eval 从已证读取的文件记录新/旧字节。所有统计明确范围，文件字节不是完整上下文 token，当前输入表示不是历史真实模型成本 | 费用/未观测token为null，不补0，不合并父/子或重复缓存 |
| Skill / 6.1补齐 | 发现 runtime-eval-grading 仍描述旧完整结果与抄hash，按 skill-creator 的入口一致性要求修正为实际 native Schema、运行层元数据所有权及同子会话一次局部纠正；运行手册同步实际 collector 和 pending 分支 | 保留原五维标准和内容 FAIL；未改变模型、Rubric或预算 |

### 实际命令与结果

以下前缀统一为 `TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest`。均执行确定性组件与合成生命周期，不调用 LLM/真实网络。

| 实际模块（接在前缀后） | 结果及适用范围 |
|---|---|
| `tests.test_cio_local_revision tests.test_local_revision tests.test_council_eval_local_revision tests.test_cio_handoff tests.test_cio_reference_handoff tests.test_predecision_cio_stage tests.test_nested_codex_launcher tests.test_native_run_package` | 103 tests / OK，17.845s，session20470；当时 CIO 实施及原消费者，不冒称涵盖后续补丁 |
| `tests.test_runtime_eval_local_revision tests.test_cio_local_revision tests.test_local_revision tests.test_council_eval_local_revision tests.test_eval_handoffs tests.test_eval_execution_proof tests.test_runtime_eval_job tests.test_cio_handoff tests.test_cio_reference_handoff tests.test_predecision_cio_stage tests.test_nested_codex_launcher tests.test_native_run_package tests.test_research_cost_diagnostics tests.test_research_instruction_layering` | 143 tests / OK，38.178s，session17156；中间整合证据，后续变化由以下受影响集合重验，不将旧结果扩为最终全入口证明 |
| `tests.test_local_revision tests.test_council_eval_local_revision tests.test_research_local_revision_handoffs tests.test_native_execution_proof` | 最后 Hook/授权/原稿消费集合44 tests / OK，11.117s，session36385 |
| `tests.test_skeptic_semantic_handoff tests.test_cio_local_revision tests.test_runtime_eval_local_revision tests.test_multidimensional_references.ReferenceBoundaryTests.test_unparseable_json_preserves_diagnostics_but_cannot_authorize_full_regeneration` | 41 tests / OK，51.955s，session86437；覆盖旧语法反馈拒绝及独立 Skeptic 接缝；此后只改CIO统计和Eval投影/非对象拒绝，见以下两组 |
| `tests.test_cio_local_revision tests.test_cio_handoff tests.test_cio_reference_handoff tests.test_predecision_cio_stage tests.test_nested_codex_launcher tests.test_native_run_package` | 最终 CIO 集合84 tests / OK，12.441s，session22774；包含原 finalizer、两入口统计及重签摘要拒绝 |
| `tests.test_runtime_eval_local_revision tests.test_eval_handoffs tests.test_eval_execution_proof tests.test_runtime_eval_job tests.test_research_cost_diagnostics tests.test_research_instruction_layering` | 最终 Eval/视图/统计/指令集合41 tests / OK，25.332s，session77173；包含原消费者和非对象首稿拒绝 |

额外实际执行 `git diff --check`、`openspec validate simplify-research-handoffs-and-acceptance --strict`，均退出0。重叠测试不累加成独立样本量。stdout 的 NATIVE_EXECUTION_PROOF_FAILED / RUNTIME_DEPENDENCY_MISSING 为原测试的预期负例，suite为OK，不是本轮真实运行失败。

中间失败如实保留：CIO首组5项出现12个错误，测试 helper 未创建 cio 目录，修正后5项通过；评分36项一项断言错误，把“不抄写hash”的说明误当技术hash转录，改验字段集合及64位hash不出现后通过；语法接缝109项三项断言仍期待修订错误先于身份冲突，按实际身份先验断言修正；42项/随后已启动的122项各一项失败，快照误在测试主动篡改 sidecar 之前取值，修正为调用前现场后单项及44项均通过。产品校验未为这些测试放宽。122项中的其余121项通过只复用于未受后续修改影响的分支，不能将该次suite写成PASS。

Skill官方 quick_validate 实际退出1：环境无 PyYAML（ModuleNotFoundError: yaml）。系统Python也缺该依赖；未安装新依赖、不声称该工具通过。仓库本轮Skill入口/契约结构检查及指令集合通过，但不是完整官方YAML校验器的替代证明。

### 字节测量与源码绑定

实际通过临时合成包调用已有测试 helper、prepare/Hook/collector，测量10条入口表示（session86583，退出0）；不是模型基准。机器记录为 [p2-local-revision-evidence.json](p2-local-revision-evidence.json)，由工具真实输出及 shasum 生成，保存测量与最终检查两个完整源码字节快照，不新增候选版本锁。

| 入口 / 表示范围 | 完整表示 → 模型表示（字节） |
|---|---|
| 资料准备 SubagentStart | 3747 → 4226；增加479，包含当前交付约束，不能宣称每个入口都降低字节 |
| 普通股 SubagentStart | 19639 → 18687 |
| 独立 Skeptic SubagentStart | 8290 → 4232 |
| fixture Analyst / Skeptic SubagentStart | 8932 → 5457 / 7734 → 5127 |
| 普通股评分 SubagentStart | 19733 → 18989 |
| 八维技术结构代表 SubagentStart | 48101 → 15511；不是新同批8/8 |
| fixture CIO 冻结JSON表示 | 1401 → 1019；合成45字节启动Prompt不当真实产品上下文 |
| predecision CIO 内嵌request包装表示 | 2141 → 1374；不把它当整个Prompt基线 |
| Runtime Eval 读取文件 | 10827 → 8563 |

临时包已清理，行内hash只绑定当次合成表示，不能当可重放的真实运行包或晋升证据；保真与机械计算以实际测试源码及断言为依据。完整Prompt历史基线、真实子会话token和总成本仍 NOT_OBSERVED。尚需6.3汇总逐项关闭矩阵、6.4一次预算批准及6.5真实补验，再独立复核和人工收尾。本节没有归档、提交或推送。

## 全部入口输入保真、统计及确定性关闭（2026-10-01）

本节完成Task5.2、5.4、6.3；总进度26/30。H01–H19的规格、实现、正负测试、真实模型状态及旧证据适用性见[closure-matrix.md](closure-matrix.md)。它是主开发确定性关闭记录，不是独立Reviewer报告。

### 本轮最小实现

- 资料准备序列化只移除task中已在identity交付的身份字段及内部task_hash，保留kind/证券/cutoff/Skill方法/候选/来源限制；私有完整包、任务绑定及历史分支不变。
- 普通股模型视图只删除holding_research_request外围重复的agent/Skill与hash绑定，不递归剔除同名字段；用户上下文、问题、证券、期间、缺口及事实目录不变。
- 原消费审计补全所有工具的model transport字节与缺失数，不限query；canonical响应与短引用响应不相加。沿已有事件读取Skeptic独立目录和主线程CIO日志，标清父/子上下文。
- 父CLI可见per-turn usage来自原codex-events.jsonl，沿已有计数校验器验证；不同已完成turn分别记录，cache不再次计入input。缺字段/bool/负值/不可能cache保留未知；父usage不当子usage或全链费用。子会话统计仍由既有execution proof处理，不新增收费估算器或观测平台。

### 实际执行

所有测试前缀为`TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -m unittest`，未安装新依赖。完整命令、执行输出及source hash由[p2-input-delivery-evidence.json](p2-input-delivery-evidence.json)及外置`execution-record.json`保存；测试组重叠，不相加冒称独立案例数。

| 执行 | 实际结果 | 适用范围 |
|---|---|---|
| 40个声明的受影响接缝模块 | 464项OK，182.264秒，exit0 | H01–H19及原Risk/Schema/引用、局部修订、读取与状态消费者 |
| scoped Claims、research_materials_stage、CommonStockDispatchTests | 58项OK，9.167秒，exit0 | 限定Claim、资料入口及普通股派发接缝 |
| 最终`STOCK_AGENT_HANDOFF_EVIDENCE_DIR=/private/tmp/stock-agent-handoff-input-evidence.UiIrPV`运行`tests.test_research_input_delivery tests.test_research_cost_diagnostics` | 16项OK，4.955秒，exit0 | 最新20组输入原件及新增成本统计边界 |
| `tests.test_research_cost_diagnostics tests.test_research_consumption_audit` | 17项OK，1.318秒，exit0 | 最新独立日志正负例、原消费统计兼容 |
| `openspec validate simplify-research-handoffs-and-acceptance --strict`、`git diff --check` | valid / exit0 | 当前规划及差异空白；不是产品质量结论 |

464项输出中的`NATIVE_EXECUTION_PROOF_FAILED`和`RUNTIME_DEPENDENCY_MISSING`来自原预期负例，测试断言通过，不是本轮真实Smoke失败，也不声称安装了exchange-calendars。完整stdout保留这两条消息。

中间失败不抹去：新增输入测试首轮5项2失败1错误（测试表格ID还原方法、父会话依赖选择、CIO记录status所在层级）；第二轮5项6失败1错误（测试未结束合成活跃任务触发并发拒绝、Runtime Eval collector结果字段误读）；第三轮14项1错误（仍误读collector状态）；修正为真实事件结构与有序完整合成生命周期后14项通过。随后增强独立日志测试的16项初次1错误：上游测试基线有未签名历史桩，原统计严格拒绝；未改产品放宽，负例保留，正例用原signed Skeptic日志的字节相同副本验证读取。上述失败均属于接缝测试适配错误，不将失败执行本身改为PASS；最终独立命令16/17项通过。早期44项相关测试也通过，不以它代替最终证据。

### 可复核原件与版本边界

原件目录：`/private/tmp/stock-agent-handoff-input-evidence.UiIrPV`。保存20组`full-input.json`、`model-input.json`、`tool-output.json`、`tool-events.json`、`snapshot/`、`measurement.json`；根目录保存639文件完整源码/配置字节快照与实际执行记录。事实及底层查询输出全字段相等，反证/否定/脚注/单位/期间/主体/冲突/来源限制均保留；未知或拼接引用仍fail-closed。

所有测量清单所列文件hash及639份实际源码hash均已重算相等。完整源码快照标识、每组measurement hash、命令及结果见机器记录，运行元数据由程序计算并保存，不让Agent抄写。这里的源码快照是工作现场与验证绑定，不是产品候选锁或晋升门禁。内部包仍保留原绝对路径，目录副本不宣称可直接Execution Replay。私有合成访问token只留外置原件，不提交Git；仓库记录只包含hash、路径和脱敏执行结果。

464项执行后仅修改两份输入/成本测试增强留存及独立日志证明，产品源码与其它测试字节未变；旧测试快照保留在外置记录，增强部分由最终16项补验覆盖。没有声称把旧464项在新测试文件下全部重跑，也没有补造旧原件。上轮已清理临时包的测量仅保留为历史观察，不作为本节原件。

### 字节结果与未证明项

20组逐入口数值见机器记录。普通股冻结包19638→17579字节，技术结构48101→15511，fixture Analyst8932→5457，Runtime Eval读取文件7646→5971。资料准备4种表示增加115–145字节，无直接Evidence的宏观/市场增加499/502字节；原因是保留额外语义约束，不删资料制造百分比。

CIO的1401→1019、2141→1374分别只是冻结JSON、嵌入request包装表示，不作为整个历史Prompt基线。字节不是token，合成usage测试不代表真实消耗，完整上下文与费用仍NOT_OBSERVED。当前真实模型、Runtime Eval Runner、Smoke、Execution Replay、Regression、Calibration、Ablation、Promotion、完整Gate均NOT_RUN。

剩余Task6.4–6.7为一次整体真实补验批准、获批宿主执行与内容核对、独立只读复核、最终人工批准及限定同步归档。申请见[bounded-runtime-validation-request.md](bounded-runtime-validation-request.md)，尚未批准，不能先执行再补授权。原八维Change继续暂停，未改任务、内容标准、历史证据或锁；本轮没有归档、提交或推送。

## 真实补验输入的只读库存核对（2026-10-01）

继续处理Task6.4的执行前资料条件，未启动模型、准备新运行、重跑测试或Gate。实际只读命令与完整hash由命令输出直接落入[runtime-input-inventory.json](runtime-input-inventory.json)，没有人工转抄hash或改写原包。

稳定八维目录仍有原始Gate、实际`data-preparation.json`、Handoff与材料运行。对失败批次原Gate及材料导入按既有envelope算法验证通过，源材料manifest字节与原导入记录一致，10份复制附件hash一致；这是候选资料的局部完整性证明，不是当前执行准入、内容PASS或新的版本锁。初查时猜测的`data-manifest.json`不是实际入口要求的文件；按源码确认真实文件名后已核对`data-preparation.json`存在，不把误查文件名报成产品缺陷。采集Gate与运行Gate文件字节不同，不按字节相同推断新运行准入，也不修改旧hash凑齐。

旧正反研究与CIO证据记录中的四个临时来源目录已不存在；本次仅在指定稳定验收根枚举实际`pre-decision-research-package.json`，没有找到备份。predecision项明确为`SOURCE_PACKAGE_MISSING`，需原完整备份及底层依赖，不能以摘要、旧PASS、失败八维或纯事实Memory代替。该输入缺口与尚未批准的5父/6子整体预算分别列明；不增加调用、不缩减完成义务。Task6.4–6.7继续未完成，总进度26/30。其它Change、产品实现、原始资料和锁未修改，没有归档、提交或推送。

## 获批后的冻结输入准备与最小接缝修复（2026-10-01）

用户已批准一次限定真实补验及资料发送，见[人工批准记录](bounded-runtime-validation-approval.md)。Task6.4完成，总进度27/30；Task6.5–6.7仍未完成。前两节的“尚未批准”是当时状态，不能作为当前授权或运行结论。

### 首次差异、修复及聚焦验证

实际通过原`prepare-multidimensional-research --reuse-frozen-gate`准备新run，在模型启动前报`MULTIDIMENSIONAL_PEER_FINAL_VIEW_INVALID`。来源final-view绑定原Gate，准备入口却把重绑run_id后的execution Gate送入材料导入比较；不是LLM随机失败，也没有资料不足或Token问题。

最小修复仅改变该准备调用：显式复用冻结Gate时，材料导入核验source Gate；新execution Gate仍由原`validate_frozen_gate_binding`从冻结原件完整重算。非复用流程、原闭包/截止点/允许Evidence检查及Risk/PIT不变。不重签历史视图，不忽略错误，也不自动修研究语义。

在既有实际材料materialization测试中新增：新run复用成功、原三文件字节不变、事实/截止点不变、execution cutoff漂移拒绝、未显式复用仍拒绝旧run、source final-view Gate或allowed IDs被重新签名篡改仍拒绝。原截止点负例保留。聚焦5项OK（3.710秒）；受影响材料/准入/定点闭包33项OK（10.376秒），二者重叠不合计为38个独立案例。OpenSpec strict及相关diff空白检查通过，没有全量Gate。

与上一轮639文件源码快照比较，仅`product/runtime/multidimensional_stage.py`及`tests/test_research_materials_stage.py`两文件改变。完整旧/新hash、实际命令及执行结果见[机器记录](bounded-runtime-preparation-evidence.json)。旧464等结果仅用于未受影响契约，当前两文件delta由本轮33项覆盖，不宣称旧全套在最新源码重新执行。

### 当前真正准备完成的三项

外置目录：`/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/handoff-validation-20261001.X5jDjo`。

| 项目 | 当前结果 | 获批待运行范围 |
|---|---|---|
| `research-v2` | 原入口PREPARED；新run_id；冻结Gate绑定重验通过 | `dimension_research_2`基本面→`dimension_research_3`研报，1父/2子 |
| `options` | 原入口PREPARED；独立新run_id；冻结Gate绑定重验通过 | 仅`dimension_research_8`期权，1父/1子 |
| `normal` | 原入口DISPATCH_REQUIRED；新run_id；实际原runtime_repeated路由为`gpt-5.6-terra` | fixture Council 1父/2子 |

准备虽保留完整八维任务目录，宿主定点入口只启动上表最小依赖闭包；不得据此宣称8/8。研究模型为`gpt-6-luna`，不恢复原暂停的八维Change。初次失败`research`目录保留，后续准备使用新的`research-v2`及新身份，不覆盖失败运行。

### 尚未执行与具体阻断

当前预算消耗0/5父、0/6子。真实加载、模型执行、报告内容及Runtime Eval仍NOT_RUN。Computer Use明确拒绝操作`com.apple.Terminal`；不以AppleScript或其它路径绕过工具限制，也不在当前Codex中直接调用底层模型启动。已准备外置`host-run-instructions.md`，使用原宿主launcher一次连续执行三项，首个失败停止，不自动重试。现有launcher负责原始事件及产物保存，不新增运行框架、网络探针或沙箱。

predecision CIO仍为`NOT_RUN / SOURCE_PACKAGE_MISSING`，须原真实正反包和冻结依赖完整备份，不能重建历史锁或启动额外Skeptic。Runtime Eval等新normal合法产物后用原native workflow；`--prepared-run`不支持EvalJob，不伪称已接通。以上未完成项不能据准备成功勾选Task6.5，也不能开始最终归档/提交/推送。

## 已执行的 shell 宿主补验及消费接缝修复（2026-10-01）

用户明确要求改用shell后，已从当前shell调用原宿主launcher，顺序为基本面→研报、期权、normal；第三项失败后停止。不是另建编排器、控制Terminal应用或绕过原生权限。完整实际参数、run_id、原件路径、完整文件hash和运行前源码快照标识见[机器记录](bounded-runtime-execution-evidence.json)。早前“0次调用/NOT_RUN”是执行前记录，不是当前结果。

| 项目 | 实际结果 | 证据适用范围 |
|---|---|---|
| research-v2 | 退出0，两个真实子Agent Start/Stop，两份正式报告，依赖闭包契约PASSED | 基本面→研报最小闭包；不证明八维整批、反证或CIO |
| options | 退出0，一个真实子Agent Start/Stop，一份正式报告，单任务契约PASSED | OPTIONS_FLOW定点；不证明完整期权链或资金方向 |
| normal | 内层退出1，JSONL没有模型事件，无Specialist/CIO/Risk及合法终态 | 真实启动失败，不能按launcher开始执行冒称产品成功 |

保守计费为已启动3/5父进程、实际模型父2个、子Agent3/6；normal失败消耗其一次项目额度，剩余额度不得挪为normal重试。原命令顺序连续执行，未新增模型重跑。

### normal 的首次差异

stderr明确报用户全局`config.toml`第189行的`mcp_servers.computer-use.type`为未知配置字段。失败发生在模型及Skill加载之前，`SKILL_LOAD_PROOF_MISSING`只是后续缺失症状；不归因于网络或LLM非确定性。未修改全局配置、代理或sandbox，未重试。已经向用户提出精确字段修正与额外一次normal预算，批准前不执行。

### 实际报告内容核对（主开发，不冒称独立Reviewer）

- 基本面区分年度与季度/半年口径、分部口径变化、管理层指引与已实现事实；计算选择关联实际成功ratio，并说明EPS含出售收益及价格/盈利时间差。保留并购、融资与资料局限，没有要求模型抄写计算血缘。
- 研报保留Morningstar许可正文的观点、预测和估值假设，同一来源章节不冒称多份独立研报；关联有命名空间的基本面主张及实际计算，明确发行人披露不等于独立研报。第三方预测与公司指引不冒充已证实事实，冻结的旧搜索限制不冒称本轮重新取网。
- 期权报告保留同源bid/ask、合约身份与观察时间，明确给出已获得的OI、单位明确的合约IV及五项Greeks，并限制标的IV/HV的未知单位、有效时间及历史vintage。没有由单次OI或成交量推断主动资金方向，也没有把不同来源拼成同步全链。
- 三份报告均为LOW_CONFIDENCE/PARTIAL；本次不是来源扩展，原研究不足与限定仍保留。独立内容复核继续NOT_REVIEWED，不用契约通过替代Task6.6。

### 消费统计的实际 producer→consumer 首差异与关闭证明

首次运行既有`audit-research-consumption`返回`RESEARCH_AUDIT_EVENT_RUN_MISMATCH`。原查询/计算事件的run_id均正确，唯一缺失来自`fixture_mcp.research_report_submit`所写提交事件：含invocation/精确稿序号/output hash，却未写run_id/event_type。这是事件外壳契约不一致，不是Evidence越权或报告损坏。

修复让新提交事件从验证后的精确草稿和冻结packet确定性读取run/agent/invocation，写入事件外壳，不增加模型字段。历史无外壳事件仅在原协议形状下，由原packet、稿版本、内容hash及唯一提交事件重新验证身份；不猜ID前缀、不跳过事件、不回写原稿或事件。普通查询仍要求原run绑定；新外壳部分缺失、跨run、未知任务、错稿序号、内容篡改均拒绝。

实际stdio提交→消费统计正例、旧事件原协议只读正例和上述负例加入既有有界提交测试。首轮2项中1项测试构造错误：测试fixture没有查询事件；改成显式插入跨run查询负例后，执行提交/有界修订/消费/成本四个受影响模块共80项通过（20.092秒）。不是产品放宽，也不隐藏首轮失败。OpenSpec strict及四文件diff空白检查通过。

用修复后的只读统计器读取本轮真实原件，已输出外置`research-consumption/consumption.json`及`.md`；0次LLM。记录可见父usage、两任务交付字节及未观测子usage，缓存是input子集，不声称全链token节省。完整输出hash见机器记录。产品源码delta仅三处既有提交/消费文件，另有一个既有测试文件；原研究/期权证据绑定修复前实际源码快照，新delta由确定性接缝与原事件只读消费证明覆盖，不能包装成修复后模型重新执行。

### 尚未关闭的原验收项

Task6.5继续未完成：normal启动失败，Runtime Eval无新的合法normal输入；predecision CIO完整正反包仍缺失。Task6.6独立复核与Task6.7人工完成批准仍未开始。没有自动补跑、全量Gate、恢复暂停八维、归档、提交、推送或候选晋升。

收尾补充：加入历史事件显式冲突agent负例，身份冲突仍拒绝；同四个受影响模块再次80项通过（19.292秒，重叠不合计160项）。最终源码完整文件hash及前一测试快照均保留在机器记录。最终只读统计尝试复用输出目录被`RESEARCH_AUDIT_OUTPUT_EXISTS`拒绝，原统计未覆盖；改用外置`research-consumption-final`成功保存，仍0次LLM。三份正式报告及Gate原hash重验通过，引用集合闭合；8/11/7个不同Evidence分别携带source_id/as_of/retrieved_at。这是机械原件核对，不新增独立内容通过或晋升结论。

## 授权配置修正、一次 normal 补跑与 MCP 接缝关闭（2026-10-01）

用户明确追加批准后，仅删除全局配置的`mcp_servers.computer-use.type`；command/args与其余解析后的配置语义保持不变。`codex mcp list --json`退出0，证明配置可解析，不冒称各MCP均已启动。最初误用该子命令不支持的`--strict-config`已如实记录，未调用模型。批准及配置字节hash见[normal-config-correction-evidence.json](normal-config-correction-evidence.json)。

通过原shell宿主launcher仅补跑一次新normal：`host-normal-5b8742b1-3020-43ff-806d-7fc70ca3ebbe`，模型`gpt-5.6-terra`。原始产物在`/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/handoff-normal-extra.5UMIQ0/run`。两个Specialist均有真实Start/Stop、可信身份BOUND及首稿SAVED，无局部重试；但CIO未形成草稿，Risk未到达，只有初始Trace而无合法终态。内层退出0，launcher退出7；不能宣称成功。完整原件标识和hash见[normal-runtime-handoff-evidence.json](normal-runtime-handoff-evidence.json)。

**FIRST_DIVERGENCE：** normal实际命令未包含既有`mcp_servers.fixture_runtime`运行目录/解释器绑定，stderr出现该MCP的initialize握手失败；父线程最终明确缺少`read_reports`。**ROOT_CAUSE：** normal调用方漏传`fixture_mcp_run_dir`，而既有动态工具白名单也漏了CIO报告读取工具。不是网络403、hash转抄失败或LLM随机不响应。未单独保存旧MCP子进程内部stderr，不伪称观察到其精确退出码；零LLM未绑定负例另验证了该启动脚本会退出126。

最小产品修复只有`nested_codex.py`两处接线：normal传入当前run目录；既有CIO local-revision入口启用`read_reports`。其它研究模式不因此启用读报告；服务端CIO权限、Specialist独立性、PIT、Risk及原生workspace-write不变，没有新编排器、代理或探针。175文件的产品保护快照中只有该文件改变；测试文件不在这套快照中，另存完整hash，不把产品快照当整个Git工作区证明。

确定性聚焦3项PASS（0.445秒）；四个受影响模块52项PASS（最终8.787秒），重叠不累加。测试实际启动生成的本地MCP传输：未绑定失败、绑定后initialize及tools/list通过、CIO reader可发现而Analyst越权拒绝；normal调用方由stub拦截，不启动模型，退出0但产物不全仍返回非零。既有CIO读取/引用/版本/NO_TRADE/Risk及局部修订正负例保持通过。OpenSpec strict及相关diff检查PASS。最初只读元数据提取误查`process-result`字段归属，改为实际`environment-manifest`后成功；不是产品或测试失败，也未改原件。

本次normal发生在上述接缝修复之前，不包装为修复后的成功证据。追加额度已经用尽，总已启动4/6父进程、实际模型父3个、子Agent5/8；其它项目剩余额度不能移为normal第三次重试。Runtime Eval仍等待合法新normal；predecision CIO仍缺原完整正反包；独立复核未启动。Task6.5–6.7保持未完成，27/30，不归档、提交或推送，不恢复原暂停八维。下一次normal必须另获最多1父/2子的明确授权，失败即停；CIO输入需要原完整备份，不生成额外Skeptic或伪造历史。

## MCP 修复后一次真实 normal 与 CIO 阶段绑定修复（2026-10-01）

按用户本次“我同意授权”，只运行一次原 shell 宿主入口、1父/2子，模型 `gpt-5.6-terra`；审批见 `bounded-runtime-validation-approval.md` 末节。新 run_id 为 `host-normal-6202af6f-e4e8-4dca-9e0a-bf2975d9fc5b`，原件在 `/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/handoff-normal-bound.XxS1Xq/run`。实际命令、完整参数、原件完整 hash、运行快照及修复后保护快照见 [normal-cio-phase-binding-evidence.json](normal-cio-phase-binding-evidence.json)。

两个 Specialist 均真实 Start/Stop、可信身份 BOUND、首稿 SAVED；MCP 接线已越过此前断点，主线程已执行 prepare-cio 并保存 CIO 语义草稿，CIO Stop 首稿 SAVED。但宿主确定性收尾错误为 `CIO_LOCAL_REVISION_DELIVERY_DRIFT`；内层退出0、launcher退出7，37个有效JSONL事件，耗时130.829秒。Risk 未到达，无 decision/report/eval，初始 Trace 的 terminal_state 仍为 null。不能将草稿保存或 shell 退出0冒称合法终态。

**FIRST_DIVERGENCE / ROOT_CAUSE：** SessionStart 先于 Specialist 和 prepare-cio，启动记录尚无 CIO 输入（NOT_COMPARABLE）；研究后才生成输入（full/model 1588/1170 bytes）。旧收尾逐字段比较整个 delivery，把正常阶段推进误判为配置漂移。原合成辅助器在 SessionStart 前就 prepare_cio，因而漏测宿主实际顺序。不是网络、模型随机性或模型抄错 hash。

最小修复限于 `cio_local_revision.py`：协议升至1.0.1，启动仍绑定原 prompt；fixture 首次 Stop 另绑定已准备的 full/model canonical content hash，唯一修订与宿主收尾均重验该绑定。predecision 不接受未准备输入的启动例外；已准备输入、原契约、实际报告读取、引用闭合、Risk/PIT及权限仍严格检查。原失败记录及版本锁未重写，不用新代码事后恢复旧运行或补造成功证据。

新增四项零LLM测试覆盖真实先启动后准备顺序、唯一局部修订、等字节长实际输入变化、prompt/Stop绑定篡改和缺失。聚焦14项PASS（5.894秒）；最终五个受影响模块72项PASS（13.782秒），覆盖实际确定性 prepare→报告读取→Stop→finalize→Risk→decision/report/trace。重叠不合计86项，不当作真实模型补跑。负向测试中预期输出的 FAILED_VALIDATION 是断言验证的结果，测试进程退出0；不是另一次环境失败。OpenSpec strict、git diff --check 均PASS。只读证据提取首次输出因长度限制被截断，随后扩大工具接收预算机械归集成功；未修改运行原件。

本次运行期间产品保护快照不变；修复后175文件保护集合仅 `cio_local_revision.py` 改变，测试文件 hash 单列。产品保护快照不是整个脏工作区隔离证明。总已启动5/7父进程、实际模型父4个、子Agent7/10；三个 normal 项目额度均已消耗，剩余 Eval/CIO 额度不能挪用为重试。修复后的真实 normal 为 NOT_RUN，Eval 为 NOT_RUN；predecision 仍需原完整正反包备份。Task6.5–6.7保持未完成、整体27/30，不追加模型、不运行完整Gate、不恢复旧八维、不归档/提交/推送。

## 阶段绑定修复后的实际运行与 Trace 消费接缝（2026-10-01）

用户更新目标并明确“我同意运行授权”后，按此前一次1父/2子申请执行宿主 normal，模型仍为 `gpt-5.6-terra`。批准记录末节已保存；新 run_id 为 `host-normal-9ed026a0-3b9d-4c4c-92b5-b95edfe789a4`，目录为 `/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/handoff-normal-phase.OcOZBd/run`。实际命令、参数、原件hash、完整保护快照与差异见 [normal-trace-consumer-evidence.json](normal-trace-consumer-evidence.json)。

本次真实两个 Specialist 首稿 SAVED，CIO 首稿经1.0.1阶段绑定宿主重验通过，实际执行证明保存，Risk APPROVED，decision.json/report.md/decision_trace.json生成。CIO选择 NO_TRADE，两执行字段均null；正式报告及决策的引用均在Gate内，无悬空引用。主开发阅读报告，观察到明确的现金流、债务期限/成本、经营趋势、产能回报及估值缺口和对应失效/重评条件；这是fixture内容核对，不是独立Reviewer、live或八维内容验收。

但终态发布验证失败：内层退出0、launcher退出7，`DETERMINISTIC_CONTINUATION_FAILED:TRACE_TOP_LEVEL_KEYS_INVALID`。Trace标记SAFE_NO_TRADE不能代替通过Trace校验；Eval没有产物，也未启动评分模型。运行耗时149.087秒，38个有效JSONL事件；父usage直接取turn.completed，子usage未观测，cache不与input相加。

**FIRST_DIVERGENCE / ROOT_CAUSE：** native CIO装配向Trace2.1增加`cio_report_consumption`顶层字段，而既有Schema的additionalProperties=false与Validator的精确顶层集合均拒绝。此前测试检查native finalize返回及文件生成；常规Trace测试用正式CIO输入，未把native生产者产物继续送入Trace/Replay/Eval，因此遗漏接缝。不是LLM抄错hash、模型未完成、网络或前一阶段绑定问题。

修复仅将`run_package.py`的消费证明写入现有 `events` 的 `CIO_REPORT_CONSUMPTION_VERIFIED/proof`，保留相同证明内容；Schema、Validator whitelist、版本锁、权限、Risk/PIT和模型语义均不放宽。既有CIO断言改为读取该事件；实际启动顺序测试继续经过native装配、Risk、Trace Schema/Validator、Artifact Replay和Eval输入准备。聚焦3项PASS（1.379秒），八个相关确定性模块89项PASS（17.452秒，重叠不加总）。这些是零LLM接缝测试，不冒称真实dev_eval评分或完整Gate。OpenSpec strict与git diff --check通过。

原运行/失败Trace/决策/报告未改写，不用修复后代码恢复旧包伪装成功。运行期间产品保护快照不变；修复后175文件保护集合仅run_package.py改变，测试hash另列。总已启动6/8父进程、实际模型父5个、子Agent9/12；四个normal额度已消耗，Eval与predecision项目额度不转用。修复后的normal仍NOT_RUN；Eval等待合法新产物，predecision仍缺原完整正反包，独立Reviewer未启动。Task6.5–6.7仍未完成、27/30；不恢复旧八维、不运行Regression/完整Gate、不归档提交推送。
