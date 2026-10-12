# 原生 Agent Package 实施证据

- `source_id`: `native-package-apply:20261005`
- `as_of`: `2026-10-05`
- `retrieved_at`: `2026-10-05`

## 实施授权与边界

用户通过 `/goal 实现需求simplify-agent-package-for-native-hosts` 明确要求开始实施；本次按 apply 处理，不授予真实研究、账户/来源访问、安装切换、模型预算、人工完成或发布批准。已重读 Proposal、八份 delta Specs、Design、Tasks、开发流程与环境说明；OpenSpec apply 状态为 ready，context/operationGuidance 均为空。

当前分支 `main`，实施起点 HEAD `a23dc76`。配置加载对齐已归档并有发布记录，不重开。暂存区为空，不新建/切换分支、stash、reset、clean或整目录暂存。

## 1.1 已有差异归属与可编辑范围

| 分类 | 当前现场 | 本次处理 |
| --- | --- | --- |
| 可按本Change修改 | 既有研究runtime/Skills/产品角色配置、业务MCP、相关历史读取与多数研究测试已在HEAD，当前没有工作树差异 | 按Design函数职责抽离，不整模块搬运；先真实业务接缝再退役控制 |
| 必须按hunk保留 | 根/产品AGENTS及PRODUCT已有Tiger只读边界；宿主脚本有Tiger13行入口；web rendering等有交易复盘增量 | 原内容不回退，仅研究入口或新报告消费者的明确差异可编辑；不认领券商/交易实现 |
| 不编辑 | 根`.codex/config.toml`、`.gitignore`、Intake Tiger接入、`pyproject.toml`的券商依赖、现有`.claude/`本地内容及全部暂停Change | 保留原修改/任务/证据；新原生模板另置自有产品路径，不覆盖用户配置 |
| 私人/原始材料 | 三个Tiger本地原证据、私人账本、账户配置、运行原转录和数据库 | 不读取正文、不改写、不打包、不提交 |
| 真正后置阻断 | 三宿主实际研究验收、已有安装目标切换、人工完成与Git发布 | 实现与确定性检查继续；到对应步骤列明最小环境/权限/预算，不自动调用或宣称PASS |

通过`git status`、共享文件实际diff和已列调用者核对上述归属。配置对齐提交使当前未提交差异收敛至12个已跟踪文件；不将其他Change的完成或dirty数量当作本Change验证。

## 1.2 宿主环境的零模型观察

| 宿主 | 实际观察 | 原生配置依据 | 当前未验证范围 |
| --- | --- | --- | --- |
| Codex | PATH可见CLI，`--version`实际返回`codex-cli 0.159.3` | 仓库既有TOML角色；官方原生Agent/Skill文档见Design | 当前版本新模板解析、角色工具限制、首轮不继承结论和实际Skill/Agent研究尚未验收；不升级以满足旧0.160.0锁 |
| Claude Code | 当前桌面Code会话元数据报告模型`claude-opus-5`；独立`claude`命令不在本次PATH | 官方原生Markdown角色/Skill文档；当前会话提供原生工具，但不能视为产品角色已加载 | CLI/内置运行版本未知，产品原生配置、工具权限与隔离仍待实际观察；元数据模型不替产品执行证明 |
| OpenCode | PATH可见CLI，`--version`实际返回`1.17.13` | 官方Markdown/JSON角色与权限、Skill发现说明见Design | 自定义角色加载、共享业务MCP、主/子会话历史继承、独立首轮及模型身份尚未验收 |

`--version`仅观察已安装程序，没有启动研究/模型、读取认证、调用doctor/来源网络、安装升级或改变权限。安装位置仅留本机观察，公开表不输出私人配置路径。公开文档与文件配置不是实际加载证明；未知保持未知，三宿主目标不缩减。

## 2.1 查询与计算业务抽离

- `product/tools/evidence.py` 从原 GateScopedFixtureTools 无损迁出六个查询/计算方法，AST（不含位置）一致；旧 MCP 继承共享实现，不复制第二份金融算法。
- Company 既有排除字段/数据集及判断函数迁至 `product/tools/research_scope.py`，原 Stage 继续引用同一规则。
- `product/tools/research.py` 提供合法单股/确认Handoff和冻结Gate的确定性任务准备、0700/0600外置存储、写前任务能力校验、精确证券/Gate范围、元数据目录、实际事实查询及受限计算。授权记录同时绑定原任务hash，重签任务不能扩权；任务访问能力与实际宿主调用方认证/执行明确分离，后者仍UNVERIFIED。
- `product/mcp/research.py` 提供绑定一个授权任务的普通stdio业务工具，不接受模型自填run/agent/路径，不创建模型或调度任务；凭据仅来自本地连接环境，普通审计与错误不回显凭据/私人内容。
- 新接缝首次13项通过；追加重签扩权和非法RPC拒绝后，与四个现有模块合并实跑63项/9.138秒，0失败/错误/跳过。六个受影响源码文件测试前后字节hash一致。这是确定性业务/transport验证，不证明任何产品Agent实际加载或研究质量。

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_native_research_tools tests.test_native_evidence_gate tests.test_server_calculation_ids tests.test_market_breadth_calculation tests.test_task_bound_research_tools -v
```

实际63项批次由相同模块清单的unittest runner执行并检查上述六个文件hash；前述命令为对应可复现清单，不把一次批次与首次48项/13项累加为覆盖数。所有材料为合成数据，现有CLI/Hook正常路径尚未退役，不能提前宣称架构迁移完成。

## 2.2 原生语义提交与有限修订

- Company/维度/Skeptic 的既有内容、关系和引用规则迁出到 `product/tools/research_content.py`，旧消费者保留原技术信封/Schema/hash检查后调用同一内容函数；原指针定位和补丁函数迁至 `product/tools/revision.py`，无宿主调用。
- `report_contracts.py` 从既有业务Schema派生研究字段，计算/文档只由作者精确选择；`report_submission.py` 在任务授权后保存不可变首稿/唯一修订、精确回执和原生业务信封。没有Codex Stop或假执行字段，访问凭据不当作者身份证明。合法回执可由相同stdio业务面读取。
- 首稿无效占一个提交名额；唯一原作者修订使用精确基础回执及定位路径，越界或第二稿不合法仍关闭，不产生第三稿。缺/错误/另一任务凭据在目录和名额之前拒绝；身份冲突不进入宽松修订。
- 金融结果、单位、输入顺序和真实计算收据由服务端装配，实际直接Evidence引用须query；计算血缘不被伪造为query。合法保存仅标业务VALIDATED，宿主/作者UNVERIFIED、内容NOT_REVIEWED，Risk NOT_RUN。
- 84项聚焦检查/11.281秒通过（新查询/提交、原局部修订、多维契约和历史输出交接），0失败/错误。原生Company、维度和独立Skeptic均走实际业务提交/读取；没有模拟宿主Agent或调用模型。

### 保留的失败与后续检查范围

- 内容抽离第一次语法切片包含残留try，在写旧消费者之前失败；改用AST边界后，40项中出现7个缺status局部变量错误，补齐原变量后同40项通过。精确补丁移动也有一次写旧源前的切片语法错误，使用预先固定源码片段后56项通过；不把首次失败改为PASS。
- 公司旧综合测试有一处硬填`gpt-test-evaluator`，而评分作业已冻结Luna；改为消费该作业真实`grader_model`，单例重验通过。没有改评分门禁、模型路由或做真实评分。
- 包含整个公司旧Stage模块的182项扩大检查仍有6个子用例错误：旧launcher单测实际PATH测得0.159.3与旧锁0.160.0不符，尚未进入被mock的模型执行。它们属待退役/迁移的控制接线，不升级CLI、不更改锁或伪称全批通过；在5.1/5.2完成对应替代与测试收敛后再核对。当前不发布、不标整体全绿。
- 新提交初次26项有1个身份冲突修订反馈错误，关闭该攻击分支后84项重验通过。所有失败原始工具输出保留，当前尚未完成CIO/依赖原生消费、历史读取迁移、宿主配置或控制退役。

## 2.3 依赖读取与当前主线程综合的业务接缝

- 原生任务可冻结同输入/Gate/证券/cutoff的合法业务报告；CIO保留原六项核心正向加独立反证依赖，不因迁移缩小准入。缺依赖、漂移或未就绪在新任务创建前拒绝；Skeptic首轮拒绝任何正向依赖。
- `report_reading.py` 区分允许目录与实际完整read，综合提交核对全部目录读取、明确采用、合法报告引用及正式挑战。业务绑定与实际宿主执行仍分列，UNKNOWN不能装成旧严格执行证明。
- 中文读取仅展示已保存研究原文和真实限制，不由Python生成总评；新增stdio报告读取与业务收据同源。
- 首次5项中2项合成CIO草稿缺原Schema字段（rationale/judgment_impact/reevaluate_when和必需传导条目）失败，按冻结契约修正夹具，不改生产门禁；与新查询/提交合并33项/12.208秒通过，0失败/错误。用真实业务工具分别生成七份合成源报告再验证query/read/选择/提交/中文，不模拟宿主Agent，不证明内容或实际隔离通过。

## 2.4 历史只读与原生归档

- 旧Company报告包的Schema/身份/引用/旧hash验证从ResearchMemory迁至纯业务`report_packages.py`；原Memory方法继续按原错误语义读取，未引入执行器。
- `report_history.py` 使用既有Memory内容对象保存原生报告及合法输入/Gate/任务/同源中文，读取保持原字节和验证范围，不写入旧严格报告索引或把保存升级成当前事实/执行/内容PASS。
- 网页ArtifactCatalog读取显式原生归档文件时先验证闭包，仅投影报告，不把原输入、完整Gate、任务或凭据送进浏览器；历史普通报告消费者保持原版本。
- 规范临时路径下，4项新归档与14项旧交接/历史CIO/Skeptic读取合并18项/34.136秒通过。原任务目录移动后Memory仍能验证读取，未知版本/对象损坏/缺失明确拒绝，网页重扫原文件hash不变。
- 首轮14项有一个macOS `/var`→`/private/var`路径断言差异；按既有手册的TMPDIR=/private/tmp重验，该读取项通过，不改生产路径规则。扩大加入旧Memory全取数链时仍有一个既有mock采集失败：PackageNotFoundError导致SEC_MAPPING失败；这是未解决的依赖/夹具基线，不把扩大15项称PASS，不安装live/券商依赖或真实取数。

## 3.1–3.4 共享正文与薄原生配置

- 四份自有角色正文已放入`product/agents/`，公共portfolio-council改用当前宿主主线程与原生专业委派；专业方法保留，counter-thesis目录说明去除旧Codex专属交付条件。没有新增CIO子Agent、模型SDK或事件适配器。
- `product/hosts/`提供三种原生配置模板及加载/权限限制说明：Codex TOML、Claude Code精确MCP工具列表与Skill预加载、OpenCode primary/subagent及默认deny权限。正文由ROLE_BODY占位或原生prompt文件引用共享源，不维护三份独立方法。
- MCP增加四个固定角色的环境绑定参数；服务启动先验证私有任务授权及role匹配，不接受任意环境前缀。实际stdio负例证明Company任务不能被Skeptic连接冒用，错误不回显凭据；合法连接在越权拒绝后仍可query。
- 当前manifest的portfolio-council=4.0.0、counter-thesis=2.2.0及council内容hash已对应新源；版本镜像检查实际PROFILE_VERSION_MIRRORS_OK，不改历史锁或生产晋升指针。
- 43项共享正文/模板及新业务接缝检查/13.075秒通过；git diff --check通过。这是Python TOML/JSON/固定frontmatter解析、来源链接、工具参数和业务stdio检查，不是宿主实际解析、加载、原生权限或研究质量PASS。
- 本机Codex/OpenCode只读help没有启动模型；Codex文件访问隔离与目标版本的shell_tool参数实际生效、OpenCode子会话历史继承、Claude Code环境及模板实际加载保持未验证。Claude MCP补充官方文档获取超时，未换通道重试；配置扩展语法仍需实际版本核对。实际安装目标未写入，三平台真实验收未执行。

## 3.5 精确候选导出与依赖收敛

- 新增最小`package_content.py`导出：只消费明确传入的审阅文件/hash清单，验证局部Python依赖和模板后写全新目标；同名目标拒绝，不更改真实注册、缓存或旧安装。ROLE_BODY及路径在导出期展开，不在运行期编排Agent。
- 初版导入闭包仍牵入旧控制模块，实际定位到runtime包初始化的隐式discovery/versioning、纯引用与旧任务包加载混放等链路；已将纯引用、输入绑定、能力资料范围及计算选择结构分离复用，runtime根的可选旧接口按显式请求延迟导入。不是通过删业务规则或伪造安装消除此问题。
- 合成候选的232项精确来源保留全部自有Skills/Schema和独立交易模块；不包含nested-codex/Hook等控制文件，也不包含并行broker/Tiger API。测试用Intake初始化来自HEAD批准基线，不覆盖当前工作区的Tiger差异；该测试候选不等于本机安装或用户最终批准发布。
- 三宿主导出实际以各候选自己的路径导入业务MCP，确认未加载旧fixture MCP/模型控制；复制字节、同名保留、缺依赖、来源漂移、私密/无关哨兵排除、缓存内容/文件集合漂移均覆盖。原独立交易模块保持字节，实际私人写入仍需其原安装隔离凭据，导出不自动恢复。
- 初次40项中2个模板占位检测把正常JSON相邻大括号误判为未展开，改为只匹配明确占位后同40项通过；加入更严格依赖收敛检查后的93项/23.608秒通过，版本镜像、strict和diff格式通过。另一次扩大73项含旧retry launcher用例，在0.159.3/0.160.0版本拒绝处失败，保留为待5.2迁移的旧接线失败，不称全批PASS。
- 安装说明见`product/hosts/INSTALL.md`，只授权合成候选与新产物检查；未写真实用户配置、安装目录、注册或私人账本，没有产品/模型调用。

## 4.1 最小原生业务链的确定性贯通

同一合法合成单股请求与冻结Gate通过真实业务prepare/query/submit/read生成Company、必要核心维度及独立Skeptic回执，再生成CIO业务任务，实际读源报告、query最终事实、明确选择并保存同源中文。见`test_native_research_reading.py`与新stdio/提交测试；覆盖错任务/未query/未read/未知对象/动作/首轮正向读取拒绝。此切片只证明新业务生产者消费者，不模拟原生Agent，不冒称完整八维、资料准备或三宿主实际执行；这些仍由4.2/6.x完成。

## 3.6 已批准的请求／角色多任务路由

- 用户明确批准更新连接边界及继续实施，相关Spec/Design/Tasks严格校验通过，新增3.6不回签旧单任务证据。
- `research_connection.py`只绑定合法输入/研究请求/Gate及角色，不维护原生任务生命周期。操作方确定性准备返回精确task_ref/task_token，各业务调用写前重验连接、请求、角色、任务权限及对象；任务正文与连接绑定不可串用，凭据仍不证明实际caller身份。
- 三宿主模板使用固定角色请求连接环境，不逐股票更改配置；每次调用从实际MCP Schema获得task_ref/task_token要求，旧task-root接口保留原范围。专业工具面没有任务创建、Agent派发、wait、retry或源码能力。
- 新路由覆盖同连接两证券交替、并发查询、独立两份报告/稿件名额、跨任务凭据、跨请求物理复制、未知/路径覆盖、角色/问题越权、Skeptic正向读取拒绝及实际stdio错误后恢复。任务/连接凭据不进入普通审计或输出。
- 与模板、新旧单任务/提交/读取/历史/候选导出合并57项/21.802秒通过，0失败/错误；版本镜像实际通过。portfolio-council当前4.1.0，历史锁与生产指针未改。没有产品模型、实际安装、来源/账户或专项评估运行。

## 4.2 完整范围、资料准备与严格业务复用

- 续接已落盘的资料发现、同行物化、共享Macro/Market及全输入覆盖代码。`research_scope_plan.py`按四个停止点保留全部普通股、ETF及期权；九份正式报告（Company加八维）的真实提交/读取覆盖已贯通，辅助Options缺失保留其余八份，缺独立反证仍拒绝CIO。
- `documents.py`按原维度Schema机械投影实际取得的BODY_VERIFIED正文，保留来源、期间与正文节；正式任务目录不注入正文，必须实际`research_read_documents`后才能选择用于提交。无正文、跨证券、未来时间、未知ID和未读选择拒绝；超响应上限明确停止，不截断。三宿主工具模板对应更新，未安装或宣称实际加载。
- `material_inputs.py`从真实准备回执保留原输入/Gate/尝试/作者选择，复用现有`freeze_latest_research_request`生成正式共同cutoff血缘；新Gate必须保留原事实，正式连接机械消费已选正文与原配置失败。同行继续复用原数据物化器，不升级候选为事实；MCP不导入同行采集或旧Stage，操作方采集单独显式授权。
- 请求连接的操作方可明确绑定已准入来源权限、候选池、同行物化和冻结准备输入；专业Agent没有准备凭据和任务创建权限。正式任务不继承搜索，Skeptic不能接收准备结论。没有新派发/等待/生命周期或模型执行器。
- 任务冻结实际Skill/角色/Schema/MCP业务实现/原Risk字节，`reuse_archive`仅消费明确指定版本并严格比较完整输入、Gate、任务研究范围、依赖和资源；改变问题/允许事实/版本拒绝，保留原报告cutoff与状态，零新模型，不搜索“最近”版本、不新增缓存策略、不生成本次取证或宿主证明。
- 最终11模块88项/28.483秒通过，0失败/错误；受影响工具/模板/Skill/manifest源码前后完整SHA-256一致，见[full-scope-check.json](full-scope-check.json)。旧硬Risk检查未改规则；镜像、strict及diff格式通过。portfolio-council为4.2.0，历史锁和生产晋升指针未改。
- 首次57项批次有2失败/1错误：合成缺口缺gap_id且reason_code不在原枚举，实际OpenAlex正文的record_hash未从研究Schema投影。修正夹具及机械投影后13项通过。扩大83项首次有1个导出依赖闭包错误：冻结校验与可选同行采集混在同模块重新牵入旧Stage；按职责拆分material_inputs后88项通过，不放宽依赖检查。系统python3缺jsonschema的镜像检查属于解释器环境问题，改用既有.venv后实际通过，未安装依赖。
- 三宿主实际研究、真实来源/账户、内容裁定、专项Eval/Replay/Promotion仍未运行；本切片只证明业务契约，不冒称实际独立上下文、内容质量或完整Change完成。

## 5.1 控制退役与完整fixture等价接缝（2026-10-06）

- 六类旧launch及两个私有模型进程执行器移除实际执行体，只保留零副作用退役拒绝；CLI删除7个旧模型执行分支，按具体确定性命令延迟导入，正常help不加载旧Stage/Hook/CLI探测。旧probe/preflight仍拒绝。
- Shell移除normal、stage、resume及五父串联，保留原Tiger严格只读宿主块。显式EXECUTION_REPLAY经check-frozen-replay核对source manifest/封闭快照/仓库外workspace，再由execute-frozen-replay转发冻结旧版本自己的入口；当前nested-codex-smoke仍拒绝。原产物和Capsule不改，未实际运行Replay。
- 保留完整fixture的数据/Company/独立Skeptic/主线程CIO/硬Risk业务：fixture_input只接受批准的合成fixture，不伪造Handoff；fixture_business复用原研究/冲突/动作结构规则；原Risk四函数无损迁至fixture_risk、旧消费者共享。CIO原稿、实际query/read、机械当前权重及两份Risk记录保留，唯一修订后仍不合格按原硬否决NO_TRADE，无第三稿。真实研究输入不能获得fixture动作能力，host/model/author未观察仍UNVERIFIED，不进入旧严格执行消费者。
- native归档保留fixture源字节，历史读取不依赖当前fixture文件；无效输入/空Gate按原模型前安全终止。报告只展示原稿和单列硬Risk终态，不让原稿动作掩盖否决。候选导出明确允许精确审阅的六个合成fixture及原决策契约，不扩展任意evals/私人目录；真实安装未切换。
- 最终37模块527项/251.072秒通过，0失败/错误，受影响源码前后完整SHA-256一致，模型调用0，见[control-retirement-check.json](control-retirement-check.json)。独立交易隐私/核心/反思、金融数学和Memory基础另跑182项/5.003秒通过；两批不累加为独立覆盖数。strict、版本镜像、Shell语法、diff格式及受影响文档链接通过；portfolio-council当前4.3.0，历史锁及生产指针未改。

## 5.2–5.3 迁移结果与真实环境缺口

- 逐方法退役纯模型进程、重复调度/状态/重试、五父Shell和固定模型参数测试；混合业务、权限/Schema/PIT/引用/数学/修订/持久化/历史负例保留。理由与替代位置见[test-retirement-map.json](test-retirement-map.json)，非按数量/LOC删测试。保留的历史Schema共享枚举与票据断言改为检查实际无损结构，不要求已退役launcher产生旧输出。
- 首轮迁移256项出现27失败/3错误，均为旧正常启动/固定默认/文档断言或未迁移接线；原输出保存于[retirement-migration-first-check.json](retirement-migration-first-check.json)。另一75项首轮7失败/19错误，其中6项历史live上下文因缺exchange-calendars==4.13.2，其他为旧正向模型接线和旧紧凑投影断言；保存于[legacy-control-first-check.json](legacy-control-first-check.json)。其余相应50项重验通过，6项缺依赖未运行保持真实，不安装可选依赖或回签PASS。
- fixture首次Risk修订样本min=0.65超过原硬max=0.6，原Engine正确REJECTED，改用原REVISE_REQUIRED样本范围0.55–0.8；第二次夹具缺JSON patch op导致LOCAL_REVISION_OPERATION_INVALID，补齐原replace操作后54项通过。不改Risk阈值或修订门禁。
- 根/产品指令、PRODUCT、README、开发流程/环境、运行与Memory手册对齐当前原生入口/明确冻结维护，保留Tiger、独立交易、源只读及产品/开发隔离。当前.claude/用户全局配置未编辑，原私人材料未读取/打包；未启动网页服务或认证实际宿主加载。
- 5.2/5.3仍待对应历史live检查的依赖授权/补验及最后映射确认，不勾未完整验证项目。6.1–6.4的三宿主安装/样本/模型/预算授权、7.x内容与人工完成批准、8.1归档发布全部未完成，见[native-acceptance-plan.md](native-acceptance-plan.md)和[implementation-map.md](implementation-map.md)。无真实模型、来源/账户、专项Eval/Replay/Regression/Calibration/Ablation/Promotion运行，未Git提交/推送。

## 5.2–5.3 补验收敛（2026-10-06）

用户在AskUserQuestion明确允许仅在项目.venv补exchange-calendars==4.13.2及必要依赖，不授权模型/真实取数/全局配置。安装后SpecialistStartContext完整18项/6.802秒通过（含原缺依赖6项），相关源码前后完整SHA-256一致，见[calendar-context-check.json](calendar-context-check.json)；此前缺依赖失败保持原样，不回签旧真实执行。

另对Design列出的研究提交、有界提交、task-bound权限、Company语义交接、局部修订/消费者和独立交易隐私/核心/反思、金融数学/Memory运行297项/80.282秒通过，见[retained-business-check.json](retained-business-check.json)。首轮115项的2个旧调用退役码断言位于共享helper，保留原字节/计算/历史拒绝逻辑仅统一退役码，2单例先通过后再跑297项；不放宽业务条件。各批有重叠，不累加覆盖数，不称全仓全绿。

镜像、strict、diff格式、Shell语法及受影响文档链接/治理检查通过，5.2/5.3按相应证据勾选；1.x–5.x共17/24任务完成。剩余6.x真实三宿主授权/执行、7.x内容核对及人工完成、8.1归档发布均未完成。补依赖批准不扩展为产品安装或模型预算，未运行产品、来源/账户、专项评估或实际Replay，未提交/推送。

## 用户明确保持实际验收阻断（2026-10-06）

用户在后续AskUserQuestion选择“暂保持验收阻断”。本次停在17/24：不运行6.1–6.4产品模型、不缩减三宿主目标、不归档或发布。三宿主验收清单已交付；恢复需要用户另外提供/批准当前产品会话、精确包/安装范围、同一合法冻结公开样本、实际模型与调用/时间预算和停止条件。此决定不否定已验证代码，也不是人工完成或发布批准；7.x内容核对/人工批准及8.1继续未完成。所有工作树修改和其他Change现场保留，main未切换，未Git提交/推送。

## 6.1 只读准备部分授权与实际发现（2026-10-06）

用户后续明确允许先只读查找已有合格公开ALB冻结样本、核对包来源并提出新的外置产品工作区/安装清单，顺序Claude Code→Codex→OpenCode；明确不运行产品模型、不联网补采、不安装包、不覆盖配置。本次未执行导出器/真实安装、未创建外置产品目录或业务grants，未读取私人账本/会话/原始模型转录，未更改生产源码/原资料。

- 公开归档及明确交付README定位到原ALB证券/cutoff/source package hash与两个精确外置临时目录。目录授权工具对原single-stock-alb-research-20261002-v1及CIO6 host均返回could not be resolved，不能读取/验证，未绕过目录工具扫描整个tmp或私人缓存。项目内第六稿副本SHA-256仍29d84a4a6b34fba9c011467d9e27b51f6d51bafb9000a1f4d99c5e83afec9ca1，只是报告，不是请求/Gate/实际正文/同行包；不得据摘要重建事实或沿用旧有限内容PASS。
- 核对已有测试候选的精确来源闭包253项，发现3份并行broker Schema；记录原盘点，提出排除3项、补操作方prepare.py的251项待审清单。intake初始化显式取HEAD a23dc764b082591e3c47c8bb30e3569040bc18b8批准基线，其他250项是工作树候选，不将dirty全目录视为批准来源。静态导入闭包通过、SHA漂移/既有常见密钥模式无命中，无模型或真实来源调用；不认证独立敏感审阅、实际宿主加载或已安装支持。
- 安装前具体缺口：operator prepare.py不在此前测试导出闭包；可选material_preparation→peer_materialization→common_stock_data→research_materials_stage→multidimensional_stage静态链仍牵入旧Hook控制器。不能把这些入口未经验证放入禁止旧控制器的包，不靠动态import藏闭包。全冻结样本的既有material_inputs消费边界与仍需准备/同行操作的完整安装要求分别说明；本次只读发现，不修代码、不缩小整体Change或回签原已测切片。
- 已交付[acceptance-readiness.md](acceptance-readiness.md)、[acceptance-source-inventory.json](acceptance-source-inventory.json)、[acceptance-proposed-source-list.json](acceptance-proposed-source-list.json)，提出未创建的新仓库外分宿主产品/产物/私有授权布局与安装前用户选择。提案清单规范SHA-256 95f86af4f64eeb26dd19aeb18f13d15017290575e802515693269ade86782bda是待审来源，不是已批准候选或实际加载证明。
- 清单结构核对、当前规划身份hash、OpenSpec strict及git diff格式通过；本次没有重跑产品/模型/专项Eval、导出/安装测试或真实来源。6.1只推进准备部分，完整可读冻结样本/安装源和路径/模型预算/实际权限及隔离待齐，当前仍17/24，6.2–6.4及7.x/8.1不勾选，不归档/提交/推送，其他Change现场保留。

## 检查与运行记录

### 安装前接缝补验续接（2026-10-06）

本次按已批准的“MRVL＋补齐接缝”继续核对现有实现，未追加产品授权。操作方prepare/material_preparation、同行数据/补充事实及公开政策资源的完整候选闭包已实际验证：三个临时导出均可导入自身业务工具，合成操作方任务可准备/查询，冻结同行可零Provider复用；未加载旧模型启动器/Hook/Stage。对HEAD的8项纯函数/类比较中7项AST相同，1项仅更换纯raw-record校验依赖路径，原错误类型和旧消费者共享，见[preinstall-extraction-recheck.json](preinstall-extraction-recheck.json)。

最终六模块102项/15.412秒通过，0失败/错误，完整命令/原输出及受影响源码前后SHA-256见[preinstall-operator-check.json](preinstall-operator-check.json)。本次先跑12项包含于102项，不累加覆盖数；不称全仓全绿、宿主加载或研究质量PASS。

新增[acceptance-proposed-source-list-v2.json](acceptance-proposed-source-list-v2.json)为未来安装审阅的270项精确来源，清单SHA-256为82c86bd39535ca00fafdbc76ca38aaccbd659ba478be8a24bb8e663bd74e4411。原251项提案保留，新增19项准备依赖/公开资源并更新prepare.py字节；未复制并行broker Schema/Tiger初始化、现有.claude、原转录或私人状态。实际外置安装与宿主MCP批准未执行，来源清单不替代人工批准或完整敏感审阅。

MRVL公开身份、8835条Gate事实及ADI/MPWR物化绑定重验通过，内存范围核对使用真实prepare_task的预筛选/能力数学，原公开资料hash不变；见[mrvl-preinstall-sample-recheck.json](mrvl-preinstall-sample-recheck.json)。没有创建实际请求、任务、连接或token。旧研报/Market的SOURCE_LIMITED、Macro的BLOCKED_CONFIGURATION及0正文保留；旧准备manifest不能改技术信封冒充原生作者提交，不能省略它绕过原生Macro依赖拒绝。完整Smoke仍需合法准备血缘与对应样本阻断处理，未回签旧内容或缩减三宿主目标。

更新[native-acceptance-plan.md](native-acceptance-plan.md)至已批准MRVL选择，新增[preinstall-readiness.md](preinstall-readiness.md)给出外置根、270项来源、现有解释器、三宿主项目安装顺序及明确缺口。Change仍17/24，6.1仅准备部分；6.2–6.4/7.x/8.1未完成。模型/来源网络/账户、实际安装、专项Eval/Replay/Regression/Calibration/Ablation/Promotion未运行，main未切换，其他Change保留，未归档/提交/推送。

- 已运行：OpenSpec规划严格校验、文档映射/格式、只读现场/版本观察及上述聚焦确定性检查。
- 未运行：产品、研究模型、真实来源/账户、独立Reviewer、Runtime Eval、Replay、Regression、Calibration、Ablation、Promotion。
- 后续确定性实现和检查按纵向切片记录，不用本记录提前证明其余任务完成。

## 已批准的外置项目文件安装（2026-10-06）

本会话用户明确回复“安装吧”，批准此前具体列出的外置根/270项来源/现有解释器及三项目安装准备。安装前重验HEAD、完整来源清单/hash、依赖、目标不存在和符号链接边界；按Intake初始化来自批准HEAD、其他文件来自精确工作树字节的既定映射建立source-reviewed，Claude Code→Codex→OpenCode分别生成原生项目文件。未覆盖开发.claude、全局配置、既有安装或原研究备份。

根为`/Users/caihaoming/Documents/stock-agent-native-acceptance/20261006`；各product-workspace分别300/300/296项导出文件，完整验证通过。实际从各安装副本导入业务MCP/操作方/同行工具并核对所有已加载product模块均来自副本，未触达旧控制器；prepare帮助正常，缺研究环境的MCP均exit=2、NATIVE_RESEARCH_TASK_ENV_REQUIRED，未创建实际业务任务/连接/token。源码前后hash一致，完整原输出与hash见[installation-evidence.json](installation-evidence.json)。

源码副本文件0444/目录0555，产物/grants父目录0700，仍不宣称全进程强制只读或实际宿主隔离。原导出manifest继续EXPORTED_NOT_INSTALLED，其语义未改；本次安装记录单独标PROJECT_FILES_INSTALLED_HOST_NOT_LOADED，不把导出标志改成真实宿主支持PASS。只读CLI版本观察为Codex 0.160.0、OpenCode 1.17.13；当前shell PATH未发现claude，其他安装/桌面入口保持未知，不自动安装或换宿主。

MRVL原冻结包/判断/转录未复制；Macro准备阻断与合法原生准备血缘缺口仍保留。产品模型、来源网络、账户调用均0，MCP原生批准/真实角色加载未执行，内容裁定/专项评估未运行。Change仍17/24，6.1安装准备部分推进但完整授权/实际能力未齐，6.2–6.4/7.x/8.1不勾完成；未归档、Git提交或推送。

## 用户选择零模型后的实际准备（2026-10-06）

用户选择暂不进入模型验收，回复“先继续零模型准备”。同一合法公开MRVL请求/原Gate/候选池已保存在批准外置根；各宿主分别创建私有四角色连接/四项准备任务，来源授权false，未原生启用MCP。三个安装副本分别使用其导出的业务Python命令执行stdio initialize/tools/list及允许/拒绝检查，专业探针与待用准备任务分离，后者无取证/提交记录。凭据仅留外置0700/0600文件，普通证据不含具体值；源码及23份公开原件（含候选池）的前后hash不变。见[zero-model-readiness.md](zero-model-readiness.md)与[zero-model-preparation-evidence.json](zero-model-preparation-evidence.json)。

本次产品模型/来源网络/账户调用和报告提交均0。原生项目加载/权限/上下文隔离保持UNVERIFIED；MRVL旧Macro失败及研报/Market来源受限保留，无旧稿转换或新取证倒填。更新验收计划、当前Tasks状态及实施映射，但仍17/24，不勾6.x/7.x/8.1。专项维护未运行，未归档、Git提交或推送。

本次收尾检查：OpenSpec strict、git diff格式、变更文档链接及270项批准源重验通过；三个副本共57项实际stdio工具允许/拒绝观察通过，23份公开原件（含候选池）未改。记录见[zero-model-closeout-check.json](zero-model-closeout-check.json)。未重复102项测试或新增模型调用。

## 无产品模型推进与共享差异准备（2026-10-07）

用户继续要求完成当前Change中不消耗产品模型的部分。当前证据有效范围核对发现旧88项及部分旧527项记录存在源码hash漂移，保留历史不回签；23项上下文/原生归档补验通过。发现ArtifactCatalog的native_reports未被真实网页调用，已在原生范围内接通只读/reports导航与渲染；47项网页/历史/交易页回归通过，本机浏览器以明确合成ALB报告完成有限页面加载/可读观察，临时服务与标签已关闭。首次新增断言误用摘要结构失败原记录保留，修复后完整批次通过，不称研究内容或三宿主执行PASS。

补齐逐方法迁移证据：41个移除方法全部对应40退役/1更严冻结路径迁移；替代方法/路径存在。132项实现候选按3份共享文件精确投影，排除5份纯并行/用户配置及所有未授权新增；私有临时Git index应用检查与候选web模块42项实际历史/网页测试通过，Tiger网页模块未导入，不改变真实index/工作树。候选补丁外置，不把重复源码补丁带入Git；安全扫描仅指定Change/候选文件和实际生成能力凭据，不扫描私人会话或账户。源码行数净增加730，未虚称总LOC或token节省。完整结果见[no-model-closeout-summary.md](no-model-closeout-summary.md)及关联原记录。

产品模型/来源网络/账户调用0，三宿主执行与内容裁定仍NOT_RUN，MRVL资料缺口保留；当前17/24，不提前勾6.x/7.x/8.1或同步主规格。未运行专项维护/晋升，未归档/提交/推送，其他Change修改保留。

2026-10-07本轮最终检查：strict、文档链接/格式、候选v2补丁临时index应用、270项批准源与23份公开原件重验通过；真实暂存区为空。v2相对已测v1只新增README使用说明，42项分离web检查按字节未变范围复用。见[no-model-progress-closeout-check.json](no-model-progress-closeout-check.json)。


## 2026-10-07 继续零模型：操作方精确归档接缝

沿提交→Memory→网页追踪发现，`archive_report`此前只有底层调用，操作方无已实现入口将有效提交交付网页目录。本次复用现有连接/任务校验与归档函数，新增`product.tools.prepare archive`：连接/任务凭据及精确有效回执先验，再写Memory与新私有目录的`native-research-archive.json`；不猜最后稿、不覆盖、不新增专业Agent工具/模型编排。归档不含能力凭据，业务保存不升级宿主/内容状态。操作说明见`product/hosts/INSTALL.md`。

首个系统python命令缺jsonschema，两个模块导入错误、实际用例0；改用既有项目.venv，没有安装依赖。第一批42项通过见[原记录](no-model-archive-cli-check.json)。补齐目标目录安全及实际网页消费断言后，操作方、历史、连接、提交及导出43项检查通过，源码测试期间hash不变，见[最终记录](no-model-archive-cli-check-2.json)。覆盖错token/错回执写前拒绝、精确Memory/网页可读、重复导出不覆盖、symlink/公开目录/目标重叠拒绝、凭据不输出。合成测试不是实际模型或内容裁定。

限定实现候选已更新为外置v3补丁，仍132项；未改变真实index或认领并行Tiger修改。已有42项分离网页证据仍适用于两个未改网页模块，不代替本次新入口43项检查。详见[范围检查](no-model-archive-scope-check.json)和[当前发布候选](release-scope-review.json)。原270项安装保持原字节，3项新版源尚未安装；原stdio观察不能回签新版。Change17/24，真实三宿主、资料依赖、内容裁定和人工完成门禁未变，未归档/提交/推送。

最终格式检查补充：候选临时index发现10个新增工具文件末尾多余空行，已只清理EOF且逐文件Python AST不变，见[格式记录](no-model-candidate-format-check.json)。最终外置v4候选`git diff --cached --check`及精确应用检查通过；43项接缝按最终源码重跑通过见[最新记录](no-model-archive-cli-check-3.json)。与原安装批准源有12项字节差异，原安装保持不变；前述3项指行为/说明更新，不含无语义格式。v3及更早补丁仅为历史快照。

## 2026-10-07 同意Claude有界方案后的运行前停止

用户最新“同意”按此前15任务/30分钟的Claude具体方案解释，不扩展来源/账户/其他宿主/最终完成。已从原安装副本真实检查三项准备search拒绝，私有任务、23份公开原件与导出文件不变。原Macro BLOCKED_CONFIGURATION及三类正文0保留，按核心依赖停止条件在模型启动前结束。完整限定证据见[预检](claude-bounded-acceptance-precheck.json)。调用0/15；原生模型/加载/权限/隔离尚未观察，未覆盖安装、归档或发布。另备[公开来源准备提案](mrvl-public-source-preparation-proposal.md)供用户审阅，未执行。

2026-10-07用户“是”已批准OpenAlex公开准备9检索/15正文及新合法cutoff，保留Claude15任务/30分钟。已知宿主/Claude配置未提供OPENALEX_API_KEY，按批准方案在来源/模型前停止，实际全部0，原任务/安装未改，见[配置缺口](mrvl-authorized-source-configuration-stop.md)。当前17/24，不重复索取预算，继续需已有安全配置，未自动新增凭据或换来源。

2026-10-07最新用户调整为Codex当前环境优先。已建立当前v4精确源产品副本，追加本机三角色/四业务MCP连接，原开发配置字节与设置保留；四服务stdio和Company精确context通过。实际原生角色spawn返回unknown agent_type，当前研究工具未挂载，未用开发Agent或子CLI兜底。保守计2/15任务尝试、余13，源网络/账户0，待宿主重载，见[实际记录](codex-current-native-activation.md)。仍17/24；本机.codex配置不纳入发布候选，Claude/OpenCode后续，三宿主门禁不缩减。
