## 1. 新版普通股资料定位与上游研究方法

- [ ] 1.1 在显式 apply 后记录本范围源码/Schema/历史报告基线，沿现有小型提取接缝实现新版章节定位 helper；以 Risk Factors/真实 MD&A 标题变体、标题后接正文、短实质文本、截断/未知元数据正反例验证，不按长度或最长对象选 Evidence，原输入不变。
- [ ] 1.2 将 research-evidence-delivery/1.0.0 绑定新版单股/已确认持仓 Company prepare/manifest/task/packet/实际 Hook，扩展期间索引保留章节/类型/截断/来源时间；以实际 packet→query 验证目录正文并存、目录不计查询、错版本/绑定拒绝及旧无标记分支不变，不新增列表入口。
- [ ] 1.3 在新版单股/持仓多维列式目录与任务复用同一定位；沿实际 Fundamental 目录/stdio query 验证正文/目录、期间单位及 source_id/as_of/retrieved_at 保真，分页/短引用/允许集不放宽，旧任务及行业原目录保持。
- [ ] 1.4 替换 Company/Technical Skill 与 Fundamental 实际任务指引相关核对段，逐条核对已读正文/缺口/主张/假设/指标窗口及摘要观察条件；通过实际 prepare→Hook→作者合成选择→原装配/持久化和版本镜像测试，不硬编码 ALB、不扩大局部纠正次数、不把零模型记内容 PASS。

## 2. CIO v3 处置与冻结计算支持

- [ ] 2.1 新增研究级 request v3、synthesis v3/native draft v2及显式路由，单股新准备选新版、持仓按标记启用；测试各自原准入目标、RESEARCH_SYNTHESIS/Risk NOT_RUN、跨模式/未知版本/PORTFOLIO_ADVICE拒绝及旧 MRVL/v1/v2/持仓/fixture原边界，旧 Schema 字节不变，不自动降级或提前接受列表。
- [ ] 2.2 实现 source_dispositions 与 challenge_dispositions 对象/唯一性/覆盖检查；测试每份非 Skeptic 恰一处置、全部目标正式挑战、未知 claim/gap/挑战及遗漏/重复/错类型；无稳定 gap_id 留空允许作者理由，不由程序判投资重要性或内容 PASS。
- [ ] 2.3 在原 prepare 冻结闭包纳入获准计算产物/成功收据/账本/事件，复用 research_submission/原计算验证器；以动态、Technical/Market 预计算和缺依赖/漂移/路径越界/错run验证，不增任意读取/计算权限。
- [ ] 2.4 将作者每条 key_fact/传导的 report_id/source_claim_id/calculation_id 精确选择装配 calculation_support，绑定原报告/版本/hash、方法/值/单位/窗口/证券基准及血缘；测试合法选择保真、原主张未采用/未知/跨任务/漂移拒绝，不按正文补引用或让作者抄元数据。
- [ ] 2.5 实现逐条直接 Evidence/计算闭合及传导 SUPPORTED/UNVERIFIED_UNKNOWN；测试当前 invocation 未query事实拒绝、计算不伪query、Gate/PIT/三项来源闭合、无支持key_fact/伪支持传导，不放宽全局collector或把结构当内容验收。
- [ ] 2.6 沿原 Prompt/read/query/短引用共享/Stop/一次局部纠正/finalizer/checker接入v3并更新批准版本镜像；测试实际launcher/白名单/tools-list交集、stdio完整读取/query、合成草稿/合法局部修订/第二失败接缝，CIO无calculate/search/新工具，旧Hook上限不变。
- [ ] 2.7 更新新版中文渲染及当前历史/报告消费者，显示原来源/挑战取舍、逐条支持与覆盖限制；测试正式JSON→Markdown同源、新旧artifact读取、无结论补写/未知理由隐藏，历史原字节不变。

## 3. 四阶段固定预算、可信状态与消耗记录

- [ ] 3.1 实现 research-execution-budget/1.0.0 与 research-execution-observation/1.0.0 的小型宿主记录，绑定四阶段准备/创建/通信/清理/校验/渲染UTC/monotonic和实际参数；确定性时钟/假CLI验证阶段顺序、离线准备间隔、异常、hash闭合，不倒填generated_at或给旧包补字段。
- [ ] 3.2 在四宿主创建前建立一次deadline，通信/父等待只用剩余预算；测试延迟创建、返回已超额、持续输出/重试/Hook与时钟跳变均不续期，明确同步创建/OS暂停/I/O不可抢占边界，不增加原timeout或新supervisor。
- [ ] 3.3 保留并补齐四阶段本组TERM/KILL/drain/grace、124/130及原字节闭包；用派生子进程/忽略TERM/关闭管道、中断及权限错误/无关进程测试有界收尾和remote UNKNOWN，不提升权限、改代理或清理其他组。
- [ ] 3.4 对计时缺失/错绑定/预算不符与成功/非零/超时/中断/校验失败建立明确归集；正反例验证通信预算与总耗时分开、证据不足不伪解释，原ALB86分钟原因UNCONFIRMED及日志不变。
- [ ] 3.5 沿原事件新增Company可信状态投影并统一四阶段research-progress/1.0.0观察；测试真实派发/Start/提交/Stop/hash、重复/错绑定/漂移、REPAIR_REQUESTED非终态、状态锁/读取有界及内容状态分列，Skeptic状态无正向正文泄漏。
- [ ] 3.6 替换实际四阶段coordinator的等待接线，派发前/wait后/归集前核对状态，等待切片受剩余预算/诊断边界约束；以实际Hook与假协作回执验证终态未通知即归集、依赖失败即阻断、空wait/普通消息不重置deadline、仍运行子任务不反复follow-up/list。
- [ ] 3.7 接入min(600秒,阶段timeout)无进展诊断及中文/CLI进度读取，显示最后有效事件、阶段/任务/依赖及预算；确定性时钟测试诊断不刷屏、不当挂死/内容失败、查询自身不算进展、到期真实超时，不新建监控服务。
- [ ] 3.8 实现research-usage-observation/1.0.0原运行事件投影与显式统计范围；测试父SELF/含子/UNKNOWN、累计/增量去重、日志重放、cached子集、模型前未运行/失败缺usage和真实父子绑定，不扫描私人数据库、不把缺失写零或父子重复相加。
- [ ] 3.9 记录Prompt/原始与模型响应/native及正式输出bytes、read/query次数和重复报告hash，接线既有无损共享/定点定位；测试完整语义展开全等/顺序重复保留/净增回原表示、新v3输出净成本及合法重读，不删除正文/反证/依据、不将字节变小等同token省费。
- [ ] 3.10 在派发前和usage更新后核对调用/固定时间/可观测usage边界，显示缺失覆盖及在途限制；测试额度耗尽不追加调用、UNKNOWN仍受调用/时间限额、完成后才有usage不假称实时硬token控制，不换模型或自动重试。

## 4. 通用确定性纵向验证与真实运行准备

- [ ] 4.1 完成prepare→实际launcher/stdin/Schema→MCP read/query→作者合成稿→Stop/装配→finalizer/checker→中文渲染零模型正反接缝，覆盖缺处置/未读报告/未知计算/未query事实/动作越权；保存选定测试日志，源码受保护、指定临时产物可写，不另建项目沙箱/启动模型网络或专项Eval/Replay。
- [ ] 4.2 完成旧MRVL/v1/v2/持仓/fixture聚焦兼容、Schema/历史字节、镜像、受影响strict、脚本语法及敏感信息/差异检查，记录具体结果与未运行项，不沿旧558项称当前dirty全绿。
- [ ] 4.3 按实际新版本/报告依赖输出ALB最小失效/复用表和宿主零模型准备计划，列准确父/子数、模型、cutoff、阶段/总时间/观测usage预算及停止条件；验证错误上游不当内容通过缓存、合法原资料复用与新准入闭合，不手拼包，此项不授权真实运行。
- [ ] 4.4 以至少一个非ALB资料结构和单股/已确认持仓新分支完成标题/短正文/缺正文/截断/单位窗口确定性矩阵；通过实际交付/选择/校验接缝证明无ticker/claim/Evidence硬编码，不回签旧MRVL或内容PASS。
- [ ] 4.5 完成四阶段多任务成功/失败/依赖阻断/终态无通知/空wait/持续输出/状态锁超时/预算耗尽故障矩阵；以实际宿主/Hook状态投影断言固定期限、独立成果保留、无关进程不变及无额外调用，不只测Prompt。
- [ ] 4.6 输出前后同信息上下文bytes与可核实usage统计口径/缺失表及真实非ALB样本计划；核对新增字段净成本、父子非重叠证明、无费用伪收益及准确调用预算，资料/模型样本未授权不启动。

## 5. 另获明确批准后的ALB及跨证券真实执行

- [ ] 5.1 取得本次ALB及至少一个非ALB样本的具体阶段/失效闭包/准确父子数/模型/完整锁/cutoff/数据与时间及观测usage预算/停止条件批准，读取运行手册并保存授权和源码/历史快照；核对实际宿主入口/权限，旧额度不延伸，缺授权不启动。
- [ ] 5.2 经原宿主Terminal生成新ALB Company/Fundamental/Technical及必要上游，保留八维真实终态与独立Skeptic隔离/交接证明；核对query/计算/加载/身份/PIT/hash/父子计数与原历史不变，关键失败按批准条件停，不自动全链循环补跑；执行成功不替代内容通过。
- [ ] 5.3 从本次合格ALB包在全新外置run经原宿主执行获批CIO，保存JSON/中文原字节及SessionStart/Stop/turn.completed、完整read/query、装配/checker、源码保护/cleanup和v3闭合证据，失败保留计数不追加调用。
- [ ] 5.4 核对真实四阶段分段时间/实际预算/deadline/最后事件/终态归集及usage覆盖/父子口径，形成新耗时解释与具体未知；时间证据不足不勾，不用新字段或旧连接错误宣称旧根因已修。
- [ ] 5.5 沿获批最小范围取得非ALB新版本真实执行与内容核对所需原稿/支持/状态/计时/usage记录；验证不同资料结构沿同接缝、无无授权重试及原历史不变，不能用旧MRVL、ALB单次或零模型代替；本项不宣称两类列表刷新完成。

## 6. 独立实质验收与人工完成

- [ ] 6.1 交付ALB原问题→新上游对象→处置→实际支持→裁定逐项对照与原稿，由用户/本次授权复核者核对Company风险假缺口/截断、Fundamental主张/假设正文及期间单位、Technical20日波动/60日高低点/摘要观察；明确独立内容裁定后才勾，不恢复暂停Reviewer/联系其他会话/另启Agent。
- [ ] 6.2 取得新ALB CIO独立内容裁定：全部目标挑战/C3项目成本回报原对象、来源错误、已有政策/利率/目标基准同/相反窗口传导、核心支持与真实未知；账户未评估/Risk NOT_RUN/无动作、PIT/执行/时间仍为底线，结构/保存/测试不替内容PASS，不再整体用限定例外豁免。
- [ ] 6.3 取得非ALB新版本独立内容核对并核对通用等待/进度/净上下文及消耗证据；交付规格→样本→事件/支持→裁定映射，确认ALB之外真实泛化证据不缺，列表验收仍属另Change，不以少量样本承诺外部永不慢或系统全域无错。
- [ ] 6.4 在6.1至6.3全部完成后汇总完整确定性证据、真实执行/内容裁定、耗时解释、usage/费用未测及真实限制，取得人工最终完成批准；未获批准维持具体待完成，未运行专项Eval/Replay/Regression/Calibration/Ablation/Promotion如实标，不自签独立PASS。

## 7. 仅人工完成批准后的限定归档发布

- [ ] 7.1 按批准范围同步四项主规格、归档及限定提交/推送并核验远端hash；验证strict/测试/审阅/敏感信息/共享hunk分离合格，保留原报告/FAIL/运行包及用户dirty，排除私人转录/数据库/凭据/其他Change；报告commit/push和剩余工作区，不自行切分支/main/PR/force push或称Promotion。
