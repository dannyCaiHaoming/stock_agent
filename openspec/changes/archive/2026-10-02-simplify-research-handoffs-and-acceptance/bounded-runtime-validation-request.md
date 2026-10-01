# Task 6.4：一次整体真实补验授权申请

状态：**APPROVED_BOUNDED_EXECUTION**。日期：2026-10-01。用户已明确批准下述限定执行与资料发送，批准记录见[bounded-runtime-validation-approval.md](bounded-runtime-validation-approval.md)；不继承历史额度，不等于最终完成批准。确定性实现与正负证据见[关闭矩阵](closure-matrix.md)。

## 需要实际运行的最小集合

| 项目 | 原有入口及资料 | 所缺证明 | 上限 |
|---|---|---|---|
| 基本面→研报 | 宿主`--start-multidimensional-task`，新run绑定已获准冻结资料，选择RESEARCH_REPORT的最小依赖闭包 | 原生Agent实际调用工具、选择计算/文档/上游Claim、短提交、同任务修订与报告内容；不拼批成八维8/8 | 1父 / 2子 |
| 期权定点 | 同宿主入口，选择OPTIONS_FLOW；资料不足必须如实保留，不补抓新来源 | 同共享语义选择路径在非研报任务的实际交付与终态 | 1父 / 1子 |
| normal fixture Council | 现有宿主normal入口，用全新run；保留fixture原路由 | 本次新增主线程SessionStart/Stop真实加载、两独立Specialist、CIO到原Risk/终态；不能用合成事件代替 | 1父 / 2子 |
| predecision CIO | 现有宿主`--stage predecision-cio-synthesis`，仅原已授权目标与RESEARCH_SYNTHESIS，从真实有效正反包准备新运行 | 第二类主线程CIO的新Hook真实加载及原报告消费证明；Risk按原阶段NOT_RUN，不扩大为投资动作 | 1父 / 0子 |
| Runtime Eval定点 | 原显式维护入口：对上述新normal的合法底层产物`eval-prepare`，真实独立dev_eval，原collector/finalizer | 更新后的评分Skill与模型视图真实读取、native稿、同一grader局部修订以及执行证明消费 | 1协调父 / 1子 |

合计上限：**5次父运行、6次子Agent派发**。其中原建议基础额度为2父/3子，额外3父/3子明确用于本次改变真实Hook加载的双CIO及Runtime Eval；不把3子/2父默认为其它阶段通用额度。失败或用户中止也计入父/子已启动次数，同Agent首稿加一次原允许局部修订不新增派发；它仍可能增加该会话模型请求及token，不能把派发数量当底层HTTP请求总数。

实际调用前只做已有确定性准备/来源与当前配置准入。2026-10-01已完成一次只读资料库存核对，结果见下节；旧正反包在本次检查位置不可用。若不存在符合原授权目标和cutoff的真实有效包，predecision项在模型前停止并报告具体缺证，**不**伪造上游、不启动原八维整批或额外Skeptic补齐。上表Runtime Eval的协调父沿原native工作流执行，未宣称`--prepared-run`已经支持Eval Job，也不另造Python LLM编排器。

## 本次只读输入核对与具体缺口

原始命令、路径、完整文件hash及检查范围见[runtime-input-inventory.json](runtime-input-inventory.json)。本节不是当前执行准入或研究质量批准，也没有模型调用。

- 稳定目录`/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/eight-dimension-rebuild-20260928/`仍保留`data-v2/gate.json`、实际入口所需的`data-preparation.json`及`host-v2/materials-run`；失败批次`eight-dimension-v4-acceptance.8iWZu9/run`保留Handoff、Gate和材料导入。已检查的Gate/import envelope有效，源材料两份manifest字节hash与导入清单一致，10份复制附件与原清单hash一致。这些只能作为基本面→研报及期权新定点准备的候选资料；仍须由原准备入口检验当前准入和完整依赖，不继承旧任务身份或执行锁。
- 已记录的`/private/tmp/activate-independent-skeptic-mrvl-20260924-v9/company-run`、同根`run`、`/private/tmp/verify-research-cio-20260926-v4/run`及`/private/tmp/activate-cio-mrvl-enum-uvVgh3/run`均不存在。指定稳定验收根中也未找到原入口读取的`pre-decision-research-package.json`；没有搜索整个用户目录，不能宣称不存在任何其它备份。
- 因而predecision CIO当前缺的是**真实正反包及其冻结依赖正文**，不是再跑测试或重新算几个hash。恢复原始完整备份后按原入口验证；不得从验收摘要、失败八维批次、Memory事实或fixture拼出原Skeptic报告，不自动增启Skeptic或完整八维。
- 若仅批准上限，仍不能自动填补该输入缺口：其它有输入的获批项可继续，predecision保留`NOT_RUN / SOURCE_PACKAGE_MISSING`，Task6.5不能因部分调用成功就整体勾选。若要用合成输入替代这一真实输入要求，必须另行透明讨论其证明范围，当前申请不作该替换。

## 模型、输入与成本

- 基本面/研报/期权与predecision开发测试遵循当前`agent_development_test_model()`所选`gpt-6-luna`；若服务拒绝，不静默回退或改变预算。
- normal保留当前fixture原锁/路由，Runtime Eval的`dev_eval`实际配置为`gpt-5.6-terra`。沿用既有产品评分策略，不把研究开发模型强写进grader；调用前保存实际命令、模型与当前输入锁。
- 允许发送的输入限于这些任务需要的已授权冻结持仓/研究资料及上述新fixture产物。不发送账户凭证、券商Client、私有数据库或无关对话；不重新抓取来源或恢复暂停的来源工作。
- 本次仅有确定性字节测量，没有真实模型费用基线。不预估精确美元费用，不将bytes当tokens；运行后按真实父/子可见usage和缓存分别记录，缺失保持NOT_OBSERVED。派发次数上限不是费用价格承诺。

## 未额外派发入口的处理理由

资料准备、普通股研究、独立Skeptic、普通股聚焦Eval的技术装配及输入变化继续走原SubagentStart/Stop/任务工具边界，没有增加启动参数、权限或第二种加载器；当前逐入口正负测试与完整输入原件已验证。其**对应阶段新真实运行仍标NOT_RUN**，不宣称本次证明了这些阶段的研究质量或局部修订发生频率。代表性原生子上下文在基本面/研报、期权和fixture双Specialist中验证共享机制；不为H01–H19逐编号启动19次模型。

## 停止及完成判断

- 启动前安全/版本/输入/来源准入失败则不发模型，保留具体错误；不能改历史锁使其兼容。
- 不修改实现后自动重跑；授权次数用尽或新的实质语义错误不能在原一次修订内消解则保存原件，停止新增调用并提出具体选择。
- 保存实际命令、真实加载/执行/提交/读取/正式报告及失败原稿、可见usage。对研究报告核对原值/期间/单位/来源、反证和上下游关系；不以schema PASS代替内容复核，不对FAIL重评凑分。
- Task6.5完成后仍需Task6.6独立只读差异复核和Task6.7人工完成批准。原`complete-eight-dimension-source-consumption`保持暂停、未完成；本次不启动Regression、Calibration、Ablation、Promotion、Execution Replay或完整Gate。

人工批准记录：本会话用户明确回复“批准”，对应此前发出的5父/6子限定补验及资料发送确认。Task6.4完成；Task6.5–6.7仍未完成。
