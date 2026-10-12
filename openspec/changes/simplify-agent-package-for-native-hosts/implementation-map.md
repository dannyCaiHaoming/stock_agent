# 实施与验收映射（未完成，不是发布批准）

## 当前Claude优先映射（2026-10-08，旧来源停止，fresh-start零模型就绪）

- `source_id`: `native-package-claude-fresh-start-implementation-map:20261008`
- `as_of`: `2026-10-08T14:11:00.630358+00:00`
- `retrieved_at`: `2026-10-08T14:12:34.767579+00:00`

当前24/29：原6.2/6.4迁入[遗留清单](host-backlog.md)，并非完成两项；6.1/6.3/7.1/7.2/8.1全部未完成。D4.1当前只验收Claude，D4.2依据真实来源错误修正薄指引；完整业务依赖及安全不变，不增加路由器、加载器、CC Switch凭据读取或新后端。

| 当前义务 | 复用/修改位置 | 状态与边界 |
| --- | --- | --- |
| 宿主别名/批准映射/实际观察分列 | Claude main-thread/README、INSTALL、运行手册；角色inherit及native Skill无model覆盖保持 | 第二窗口主线程新转录gpt-6.1-sol与用户opus映射吻合；专业作者未创建、Provider wire/CC Switch配置读取未验证，不改原报告状态 |
| 实际来源与加载边界 | Design D4.2、native-agent-package场景及四份薄说明 | 新cwd/CLAUDE.md已观察，但portfolio-council正文Base directory仍为旧minimal-slice；同名/hash相同不放行，首错停止；新会话须从精确目录创建并逐项核对，缓存内部成因未证 |
| 当前Claude精确候选与接线 | 既有export_package/verify_export、prepare及stdio；原191项按适用字节复用 | 修改后29项通过（13.188秒、exit 0）；fresh-start 274源仅3份说明overlay、308导出、3新任务/CIO连接及stdio正负例通过，2,471旧文件hash不变，见[准备证据](claude-fresh-start-readiness.json) |
| 实际原生/业务/内容 | 既有fixture正反/CIO与独立MRVL技术Market；后续5任务/30分钟约束 | 第二窗口消息已实际执行，但来源拒绝后停止，专业/业务/报告0，见[第二窗口结果](claude-mapped-window-2-result.md)；早期准备不证明6.1完成。新会话/第三窗口尚未授权或启动 |
| 文档与收尾 | 本Change当前规格、任务、遗留及停止记录；最新链接/格式/strict/凭据排除 | 检查结果见[文档检查](claude-fresh-start-document-check.json)；原会话和失败保留，Codex/OpenCode未验收、不运行；最终人工完成批准、主规格同步、归档/提交/推送未执行 |

第一窗口未进入CLI的[结果](claude-mapped-native-result.md)与更早的模型名称差异停止记录独立保留，不由本次成功投递/映射吻合回签。当前问题是实际Skill来源，不再称消息完全未启动或模型名称冲突。下文24/31、三宿主前置及更早“未激活”等均为各自历史快照，不覆盖当前范围；原始JSON不改。

## 历史最小修复与候选接线映射（2026-10-08T11:48:26Z，新原生执行当时未运行）

- `source_id`: `native-package-minimal-repair-implementation-map:20261008`
- `as_of`: `2026-10-08T11:48:26.566637+00:00`
- `retrieved_at`: `2026-10-08T11:48:42.021620+00:00`

当前仍 **24/31**，七项门禁不勾。D3.4.1计算目录/精确输入血缘页与大型报告MCP无损JSON页已实施；内部完整目录、报告、提交血缘、依赖与归档消费者不改。D2.5已有Market/Skeptic的Claude固定原生Skill、各自MCP引用和精确导出已实施；共享角色补实际Skill加载、本角色前缀和当前窗口首错停止要求，无新增控制框架或来源能力。

| 规格/设计 | 实现与最新有效证据 | 未完成边界 |
| --- | --- | --- |
| D3.4.1有界精确计算/报告交付 | `tools/research.py`、`mcp/research.py`；[191项最终聚焦检查](minimal-repair-check.json)，含15个新测试方法及真实routed stdio大型合成报告无损回读 | 合成报告不替真实原生作者消费；内部完整读取保持 |
| D2.5固定原角色、工具和模型继承 | 两份Claude薄Skill、原角色MCP引用、`package_content.py`映射；模板/缺源/漂移/冲突负例包含在191项内 | 原生工具池、实际Skill/模型/独立首轮仍未重新验证 |
| 6.1独立候选/任务/真实stdio | 原272源仅10项包内覆盖＋2新增入口，共274源；三包含manifest为305/308/301文件，9专业任务及CIO连接；[接线证据](minimal-repair-candidates-readiness.json) | 未原生激活；Codex/OpenCode保留disabled；CIO等真实正反报告才建任务 |
| 原MRVL计算运输接缝 | 各候选完整目录27项/16,663字节；精确血缘首个页64/1,518 ID；任务文件无变化 | 只验证首个页，不冒称完整消费或替作者选指标；作者query/calculate/submit/新报告0 |
| 7.x/8.1保护和完成 | 38项指定源码/测试、1,689项指定旧候选/任务/公共样本/结果文件hash一致；公开证据排除21个已知能力凭据值 | hash不是OS只读；三宿主切片/内容/人工完成批准仍缺，未归档/暂存/提交/推送 |

完整最小范围、旧测试失败及夹具修正、三宿主剩余条件见[修复与候选报告](minimal-repair-readiness.md)。旧原生窗口全部停止；本次产品模型/来源网络/账户0，无专项Eval/Replay/Promotion。下节及更早“未新增代码/测试/Schema”等仅描述各自历史窗口，不覆盖本次修复；旧原始结果不改。

## 历史真实原生验收映射（2026-10-08T10:03:31Z，窗口均停止）

- `source_id`: `native-package-minimal-native-implementation-map:20261008`
- `as_of`: `2026-10-08T10:03:31.019729+00:00`
- `retrieved_at`: `2026-10-08T10:03:31.019729+00:00`

当前 **24/31**。本轮执行已展示并在最新继续/所有授权反馈后采用的每宿主5原生任务/30分钟方案，不借旧额度，不把用户反馈虚构成新的逐项预算选择。只交付原生Agent Package；未新增产品代码、Schema、测试、Fed/来源功能或控制平台。四份OpenCode原报告是真实产物，但不能覆盖首错停止和消费缺口，三宿主验收未完成。

| 规格/任务 | 实际实现/检查及原生证据 | 裁定/剩余项 |
| --- | --- | --- |
| 有限三宿主准备；6.1 | 既有fixture与MRVL技术切片、9专业任务、三固定窗口均进入原生准入/执行 | Codex信任未决定；Claude作者前失败/模型元数据冲突；三宿主原生权限及必要证据仍不齐，不勾 |
| Codex薄配置/实际加载；6.2 | 本次进程原生解析四MCP enabled；实际交互停于Folder trust，未代选保存信任，Ctrl-C回shell | 模型/专业/业务0；不能推断历史unknown role根因或自动恢复 |
| Claude四连接/原生作者；6.3 | 新项目加载，Company/Skeptic/Market原生context分别匹配新任务；官方转录核实09:41:20 Agent含worktree/opus并失败 | 2/5停止，作者/报告0；Company-native未重测；配置/回告claude-opus-5与转录gpt-6.1-sol不一致，Provider模型未验证 |
| OpenCode原生角色/独立首轮；6.4 | primary＋三个专业4/5，主子metadata glm-5.2；Company/Skeptic同一parent消息派发，首个报告前均开始；各自唯一初始用户消息精确等于dispatch prompt，仅自己grant | 隔离观察只覆盖实际导出用户输入/工具，不扩展到Provider wire；Company无Skill调用，Skeptic evidence-grounding加载缺证；父prompt误写CIO前缀 |
| 业务读取/计算/提交/原Risk | 四份真实VALIDATED/精确回读；CIO实际prepare/context/read_reports/query/submit/read，正反依赖精确绑定，Market不混入fixture；Risk APPROVED/SAFE_NO_TRADE | Company09:38:10.869换算错误后仍有19次业务调用；Market两次统计截断且calculation_selections为空，不能勾6.4或升级内容 |
| 内容与历史保真；7.1 | 开发核对fixture数值/单位/时点及CIO反证回应；原报告host_execution UNVERIFIED/content_verdict NOT_REVIEWED不改 | Codex/Claude本次无专业报告；缺三宿主内容裁定，不另启Reviewer/评分器，不把fixture当真实建议 |
| 保护范围/证据/发布；7.2/8.1 | 三候选303/304/299，共906文件前后hash相同；公开证据白名单及21个已知能力凭据值排除；旧28项聚焦结果按范围复用 | hash不证明OS只读；三宿主验收/最终人工批准缺失，不归档/暂存/提交/推送，不恢复其他Change |

本轮实际结果、四个精确回执、首错后时间线、统计截断及最小宿主需求见[结果](minimal-native-result.md)和[脱敏证据](minimal-native-result.json)。OpenCode本地终端停止确认不晚于09:55:45.067535，Provider取消未验证；所有窗口停止，不重派/续期。下面08:57准备映射及更早快照保留其原时点，“未授权/模型0/未切新项目”不覆盖本节；原始结果JSON不改。

## 历史有限验收准备映射（2026-10-08T08:57:41Z，范围收敛后）

- `source_id`: `native-package-minimal-implementation-map:20261008`
- `as_of`: `2026-10-08T08:57:41.164940+00:00`
- `retrieved_at`: `2026-10-08T08:57:41.164940+00:00`

当前 **24/31**；五份规划已实际修订并strict通过，七项未完成任务不删除、不勾选。Fed新接缝/文档类型方向撤回；完整公开股票八维与来源覆盖不再作为本Change完成前置，但其正式业务依赖和成功条件不变。没有新增产品代码、Schema或测试。

| 规格/任务 | 现有实现及本次实际检查 | 原生/内容状态与剩余项 |
| --- | --- | --- |
| native-agent-package有限三宿主验收；6.1 | 原272项批准源、已有fixture与MRVL冻结Gate；实际候选prepare CLI各生成Company/Skeptic/Market任务，共9项 | 每宿主新有界模型计划、原生项目准入/工具池/权限仍待确认；不勾6.1 |
| 四职责、输入隔离及正式依赖不退化 | 既有fixture Company/独立Skeptic及主线程CIO；Market为MRVL技术切片；两类输入不混用。各任务实际stdio context/错凭据拒绝、Skeptic禁读正向报告通过 | 服务端隔离不等于宿主上下文隔离；CIO仅准备连接，等真实报告后建任务，不手写上游依赖 |
| Claude原生项目接线；6.3 | 新候选272源/304导出、四服务均绑定各自角色；按实际.mcp.json命令检查三专业context/task_hash及CIO目录通过 | 原产品会话仍idle在旧项目，新增模型/作者0；父/子工具池与zero tools修复UNVERIFIED，不按相同失败声明盲派 |
| fixture及范围/读取/授权回归 | 本次28项聚焦测试通过，230项源码/焦点测试字节不变；旧候选及私有任务1219文件hash不变 | 不是OS强制只读、原生研究、内容或Promotion；与历史174项不累加 |
| 三宿主实际场景与内容；6.2–6.4/7.1 | [最小准备报告](minimal-slice-readiness.md)、[脱敏证据](minimal-slice-readiness.json)明确输入、权限、新预算提案与停止点 | 新提案未激活/未另获明确运行授权；三宿主实际最小切片、合法原报告和内容核对仍缺 |
| 人工完成与限定归档发布；7.2/8.1 | 当前范围/实现/旧证据与未运行项分列，旧失败与停止记录保留 | 最终人工完成批准、归档/提交/推送均未执行 |

下文全部进度、完整研究前置及“原七项不变”等均为各自历史时点，不覆盖现行Specs/Tasks；旧原始结果JSON不改，未运行专项不写PASS。

## 历史映射（2026-10-08T07:48:38Z，范围收敛前）

- `source_id`: `native-host-change-map-current:20261008T074838Z`
- `as_of`: `2026-10-08T07:48:38.893483+00:00`
- `retrieved_at`: `2026-10-08T07:48:38.893483+00:00`

当前 **24/31**：新增并完成D3.4/2.6完整事实字节分页，D3.3/2.5已完成，原七项不变；调用入口、配置或零模型修复完成不等于三宿主研究或内容完成。

| 规格/任务义务 | 当前实现与确定性证据 | 实际宿主结果 | 内容/剩余条件 |
| --- | --- | --- | --- |
| D2.3/3.10：Company调用不生成隔离/模型可选参数 | 原生company-native固定Company角色；30项受影响检查 | 两次原始Skill只有skill/args；新入口实际发现，未再走Company Agent误参 | 两次均尚无合法Company研究报告，不能据此勾6.3 |
| D2.4/3.11：显式复用已有Company连接、不扩工具 | Company项目角色增加mcpServers字符串；原11工具/五Skill/inherit不变；27项配置/导出正负例及strict通过 | 修复候选仍在作者创建前zero tools拒绝，304文件不变 | 配置完成，实际修复未通过；宿主内部根因证据仍不足 |
| 6.1/6.4：当前OpenCode原生角色与输入交付 | 272审阅源、298导出加manifest；原生1.18.34解析四角色，新窗口仅Company/3任务/30分钟 | 新候选主子glm-5.2、两份附件、唯一Company作者及全部五专业Skill成功，context/catalog、两次8 ID query成功 | 首次32 ID query字节超限且作者首错后继续，窗口已停止；0计算/提交/报告/回读，不是完整6.4 |
| 已准备任务不误用操作方能力 | preparation/task不同能力门禁保留；末次profile的primary准备工具全部deny、task仅Company，不发operator-grant | 前次误用被拒；末次prepare_task实际0，completed/error业务调用均使用精确任务能力 | 不开放Read/Bash、不共享凭据；任务能力不证明宿主作者/模型身份 |
| multi-dimensional-holding-research：SEC结构化金额；D3.3/2.5 | evidence.py默认关闭、ResearchTools内部启用；同框架ratio及USD monetary_scale；MCP仅补描述，参数不扩展 | 旧窗口四ratio失败为对象到Decimal接缝、一次USD换算同因；就业人数拒绝正确 | 已装三份新候选，本次OpenCode止于query字节超限，尚未实际执行计算；原Gate、旧候选/任务/错误不改 |
| 2.5：来源/单位/期间/hash、授权与旧行为保持 | 新test_native_sec_calculations九方法；prepare→真实stdio→计算保存/catalog→提交选择/精确读取；非法对象/框架/单位/PIT/资源/凭据负例及旧默认拒绝 | 最终136项聚焦检查通过，含既有计算/业务接缝/模板/导出；不是模型运行 | 合成报告host_execution仍UNVERIFIED、content_verdict仍NOT_REVIEWED，不替真实原报告 |
| 3.5/6.1：修复进入洁净安装候选 | 同一272项批准源仅覆盖3项修复，三宿主含manifest 303/304/299项；各自独立Company连接/任务、514字节0600小包，真实stdio允许/拒绝通过 | 后续用户单独批准本次OpenCode新窗口并实际激活；Codex/Claude新候选仍未原生激活 | 不重开旧窗口、改旧截止或扩大到三宿主；新窗口2/3停止，不能勾完整6.1–6.4 |
| 6.4：查询字节预算及首错停止 | 原窗口query最多64 ID、64KiB上限；context/catalog ID分页不代表query字节容量 | 首次32 ID原响应重建99,085字节，正确拒绝；作者随后两次8 ID成功，未遵守fail-fast，开发方观察后关闭本地Terminal | 停止时分页未实现，原结果不改；当前确定性修复见下一行，Provider取消仍未验证 |
| D3.4/2.6：完整事实字节分页与实际读取收据 | ResearchTools.query可选offset/limit，最长完整前缀/next_offset；UTF-8页信封计入64KiB，全部ID先验、input_hash原参数/result_hash本页/收据实际ID；context与MCP同步说明 | 新增13项及最终174项受影响零模型检查通过，含真实准备→路由stdio→分页→未读后页拒绝/全读后保存精确回读；旧查询/SEC计算/提交/连接/导出/模板不退化 | 仅两项产品源和一项测试；尚未装入冻结候选，原窗口不重开，不据业务检查宣布真实作者、三宿主或内容通过 |
| 6.1：分页修复进入独立候选 | 沿既有批准安装范围，新建query-pagination-current-20261008；同一272项批准源只覆盖两项修复，含manifest 303/304/299文件，各自独立Company任务与514字节0600授权 | 候选真实prepare CLI及stdio的query页Schema/context限制/错能力/正式禁搜检查通过；原SEC候选根1244项文件hash不变 | 三份未原生激活，query/计算/提交0；不重开窗口、扩大来源或宣称Claude zero tools已修复，6.1仍不勾 |
| 6.3：zero tools接缝定位 | 直接执行新Claude项目声明的MCP命令，initialize/list成功；11项角色名全部在目录，prepare_task排除；官方格式支持 | 父/子原生工具池仍未验证，原生失败没有重跑 | 不把stdio目录当子工具池，不据缺证猜测配置、扩大白名单或宣布厂商根因 |
| 6.1/7.2：冻结官方原件与正文消费分别验证 | 稳定公共缓存找到Fed原HTML84741字节/RSS9645字节；既有record/key/raw与宏观快照hash/PIT通过，normalizer复现2511字符等于原事实且未触及12000上限，五原件未改 | 纯只读核对，无新作者、query收据、BODY_VERIFIED文档或准备回执；Claude失败2.1.289与静态检查2.1.291分列 | 当前OpenAlex-only原生准备仍阻断；离线官方正文接缝尚未实现，需先明确Design D5范围，不手写转换/省略依赖；见[定位与映射](native-acceptance-blocker-diagnosis.md)及[证据](native-acceptance-blocker-diagnosis.json) |
| 6.2/6.4及7.x：完整三宿主、内容和完成 | 既有完整代码/测试迁移映射仍见下文及test-retirement-map | 本机Codex现0.160.1，本轮无新Codex产品执行；OpenCode本地已停止，Provider取消未验证 | 正文依赖、完整Market/八维、独立Skeptic、主线程CIO及三原报告仍缺 |

本次新批准窗口及实际结果见[OpenCode新候选原生结果](opencode-sec-amount-native-result.json)：UTC06:17:58.054640—06:47:58.054640、主线程1＋Company1＝2/3；首次导出发现首错后关闭本地Terminal，0报告，未重派/续期。此前证据见[Claude修复后结果](claude-companymcp-native-result.json)、[OpenCode旧最终结果](opencode-company-prebound-result.json)、[旧固定窗口](opencode-company-prebound-window.json)、[SEC金额修复检查](sec-amount-native-fix-check.json)及[三份新候选接线与定位](sec-amount-candidates-readiness.json)。旧OpenCode末次2/3、旧总账8/15和首轮4/3偏差保留，原总硬截止UTC04:22:58.710038不变；本次新批准不是旧余量续期。136项与前76项重叠不累加；四项SEC修复源/测试hash是此前原生观察时的保护范围，不替代OS只读证明。新三候选、旧两候选和旧连接文件在上述观察时保持原字节，本次开发未写入这些路径。随后按D3.4/2.6修改两项产品源并新增一项测试，最终174项受影响检查通过（含新增13项、不与历史批次累加），新hash及精确检查范围见[分页修复证据](query-pagination-native-fix-check.json)。旧原生失败JSON和三份冻结安装不改。随后新增的独立分页候选、任务及stdio接线只补6.1准备，见[新候选证据](query-pagination-candidates-readiness.json)；不启动新窗口或回签原生/内容通过。未隐式Eval/Replay、归档、暂存、提交、推送或修改生产版本指针。

## 2026-10-08 goal推进：调用入口已进入精确候选

- `source_id`: `claude-company-native-readiness:20261008`
- `as_of`: `2026-10-08T02:54:05.314870+00:00`
- `retrieved_at`: `2026-10-08T02:54:05.314870+00:00`

D2.3原生入口已从批准基线加四项精确宿主overlay导出为272源/303导出候选，company-native发现文件与审阅源一致；旧包302文件和三个专业角色不变，Intake保留原批准字节。候选的现有准备入口生成独立Company任务/514字节私有小包，两个旧任务8文件不变。无需重复未改代码的30项聚焦批次；新的候选完整性/准备证据见[readiness](claude-companynative-readiness.json)，交接见[准备报告](claude-companynative-readiness.md)。这只补6.1的安装准备，未原生激活、未Skill执行或新报告，不补6.3/7.x或人工批准，仍21/28。新窗口按既定显式授权边界处理，原停止额度不自动续期。下文按原时点保留。

## 2026-10-08 Company调用端原生入口修复

- `source_id`: `claude-company-native-call-focused-check:20261008`
- `as_of`: `2026-10-08T02:39:27.422788+00:00`
- `retrieved_at`: `2026-10-08T02:39:37.226241+00:00`

当前**21/28**：新增D2.3/3.10调用入口修复，原七项不变。指定会话原始两次调用均已含worktree/opus；捕获Agent Schema仅description/prompt必填，无可选字段default，Skill只允许skill/args。原“Schema未知”为较早快照，现已补原生Schema但仍无Provider wire输入，不能进一步武断归责模型或桥接。先前指引已加载仍失败，不继续把提示交付当行为解决。

| 规格/设计 | 实现 | 本轮确定性证据 | 仍缺实际证据 |
| --- | --- | --- | --- |
| Company调用不暴露额外派发参数；D2.3 | Claude专属`skills/company-native/SKILL.md`以context fork固定原角色；main-thread使用Skill(skill/args) | 捕获Schema哈希一致、Agent省略合法、新Skill额外隔离/模型参数被Schema拒绝 | 本机原生新入口发现、custom agent执行与实际模型未运行 |
| 沿原研究职责与受限能力 | 原Company角色/五Skill/精确MCP工具与共享方法不改，无Skill级权限/模型覆盖 | frontmatter固定绑定与原角色工具/五Skill核对；既有stdio/旧入口检查保留 | 专业五Skill实际预加载、工具拒绝与业务query/计算/提交尚缺 |
| 精确源→Claude发现路径，不覆盖/回退 | `package_content.py:export_package`新增一处原字节映射、缺源/冲突拒绝 | 缺源/hash漂移/共享Skill目录冲突写前拒绝、旧包保留及恢复，Codex/OpenCode不安装该入口 | 实际候选安装/激活未执行，旧产品会话仍旧副本 |

30项聚焦检查通过（9.671秒）；384项产品/焦点测试字节前后相等，只是测试写入范围观察，不是OS隔离证明。详见[聚焦证据](claude-company-native-call-check.json)与[脱敏诊断](claude-company-native-call-diagnosis.json)。本轮新增产品模型任务/Company报告0，无新研究授权、Hook、SDK、子CLI、重派或专项执行；原七项6.1–6.4/7.1/7.2/8.1保持未完成，不把配置修复当三宿主完成或人工发布批准。下文按各时点保留。

## 2026-10-08新候选原生执行结果

- `source_id`: `claude-desktop-company-dispatchfix-window:20261008`
- `as_of`: `2026-10-08T01:41:24.642925+00:00`
- `retrieved_at`: `2026-10-08T01:41:24.642925+00:00`

D2.2/3.9的Claude根指引已通过实际宿主目录变更消息确认加载，主线程也已加载当前portfolio-council。该真实证据只关闭“新根指引是否进入本会话”的未知；主线程仍报告worktree/opus误参，Agent作者创建前失败，专业query/计算/提交/报告0、保守2/3停止且未重派。原生参数省略从未实际尝试，Schema required集合仍未知；不能据此声明省略不支持或Company角色/MCP失败，也不能把指引静态交付PASS扩展为行为复发预防PASS。

新任务三类JSON记录各0，候选与原导出清单一致；停止后快照时点及其非事前基线限制、开发方零模型函数误调用及修正、回告消息限制均在[限定证据](claude-company-dispatchfix-native-evidence.json)分列。下一证据缺口在正确原生调用/实际工具约束，不是重新导出或重复同一路径。详见[本轮结果](claude-company-dispatchfix-native-result.md)。保持20/27，原七项及三宿主/内容/人工批准/归档发布门禁不变；未改研究源码/配置或另造executor，下文为历史映射。

## 2026-10-08委派指引修复增量

- `source_id`: `claude-native-dispatch-fix-review:20261008`
- `as_of`: `2026-10-08T00:47:35.379988+00:00`
- `retrieved_at`: `2026-10-08T00:47:35.380139+00:00`

当前**20/27**，新增完成3.9，原七项未完成任务不变。实际worktree误参、可选参数接受UNKNOWN、主线程指引交付修复和下一次原生验证分列，不将缺指引认作唯一原因。没有新增派发器、SDK/模型后端、自动重试或跨宿主事件平台。

| 新增规格义务/设计 | 实现 | 确定性证据 | 宿主与内容缺口 |
| --- | --- | --- | --- |
| native-agent-package：Claude主线程指引随包加载；D2.2/3.9 | `product/hosts/claude-code/main-thread.md`；`package_content.py:export_package`按产品规则→Claude指引→CIO正文拼装根入口 | 精确已审阅字节、缺源/hash漂移写前拒绝、原副本恢复；`test_native_package_export`新增两项 | 新候选已导出但未原生加载；省略参数接受及LLM遵从未实跑 |
| 普通目录/继承模型不引入额外隔离或覆盖 | Claude最小JSON调用例；原专业模板`model: inherit`和精确工具/Skill未改 | 模板断言无`isolation/permissionMode`；三角色导出字节与旧修复副本一致 | 原失败作者未创建；专业五Skill、实际模型与工具权限未证 |
| 不扩大其他宿主或运行控制 | Claude README/INSTALL澄清；Codex/OpenCode根入口和共享正文保持原路径 | Codex/OpenCode导出及无Claude指引来源仍合法；旧正常启动入口退役检查 | 三宿主完整实际执行及内容仍缺，不能借静态结果勾6.x/7.x |

25项受影响检查通过（7.271秒），strict通过；没有为本轮文档重跑全批。新候选271项精确源/301项导出，保留原Intake批准字节，旧副本/旧任务不变；独立Company任务及514字节私有小包零模型准备完成，未切换产品目录或新开窗口。完整hash、范围及证据限制见[限定证据](claude-native-dispatch-fix-evidence.json)，中文结论见[复核报告](claude-native-dispatch-fix-review.md)。下文各进度、未运行和版本声明均为对应历史快照，不覆盖本节。

## 2026-10-08修复后原生观察增量

- `source_id`: `claude-desktop-company-deliveryfix-attempt:20261008`
- `as_of`: `2026-10-08T00:30:58.190658+00:00`
- `retrieved_at`: `2026-10-08T00:30:58.190658+00:00`

D3.1/D3.2的修复副本已切入同一Claude桌面产品会话。实际原生context调用后，产品主线程回报1398项/32项首个页/next32和完整Schema，不再超限；这补交付接缝观察，不补Company作者或内容。随后派发错误传入worktree和独立model，Agent在创建作者前失败，精确任务工具/计算/提交记录各0。失败2/3尝试即停、不自动重派；专业五Skill和工具权限仍未执行，完整6.3、三宿主及7.x/8.1仍缺。见[本轮限定证据](claude-company-deliveryfix-native-evidence.json)。本增量未改产品源码、配置或旧任务，不为文档重跑产品或确定性全批。

## 当前增量（2026-10-08，修复准备时点）

- `source_id`: `native-package-implementation-map-current:20261008`
- `as_of`: `2026-10-07T16:26:21.297026+00:00`
- `retrieved_at`: `2026-10-07T16:26:21.297026+00:00`

当前19/26；新增完成3.7/3.8，不删除原七项验收/人工批准/发布任务。授权交付映射到`tools/prepare.py:agent_grant`及CLI选项，分页交付映射到`tools/research.py:ResearchTools.context`与MCP参数；对应新增操作方、研究工具及多任务连接测试，93项受影响检查通过。桌面实际新任务context超限失败及新副本13,055字符stdio交付分列，详见[当前规格→实现→测试→宿主/内容映射与缺口](native-delivery-fix-review.md)及[结构化证据](native-delivery-fix-evidence.json)。原生Company专业执行、三宿主完整报告及内容仍缺，旧安装/旧任务不回签。下文保留各阶段历史证据范围，不覆盖此当前记录。

- `source_id`: `native-package-implementation-map:20261006`
- `as_of`: `2026-10-06`
- `retrieved_at`: `2026-10-06`

| 规格义务 | 保留/拆出/退役实现 | 业务验证位置 | 实际宿主/内容证据 |
| --- | --- | --- | --- |
| 一份方法、四职责、薄原生配置 | product/skills、product/agents、product/hosts；不覆盖用户.claude或第三方Skill | test_native_host_templates、test_native_package_export | 三项目文件已安装，零模型工具检查通过；真实原生角色加载/执行未验证，6.x未完成 |
| 请求/Gate/角色及多任务路由 | tools/research_connection、mcp/research；精确task_ref/token；主线程准备输出不注入完整依赖/正文/资源hash | test_native_research_connection、test_native_research_tools | 业务能力凭据不是作者认证，UNVERIFIED |
| 完整输入、八维、停止点 | research_scope_plan、原生任务、报告依赖/归集；ETF/期权保留缺口 | test_native_full_scope、test_native_research_reading | 不把部分保存当完整多维或三宿主执行 |
| 实际正文与同行 | materials、documents、material_inputs、material_preparation/peer_materialization；搜索仅准备，正式任务实际读正文 | test_native_research_materials、test_native_full_scope | 只替外部HTTP边界的零模型检查，无真实来源访问 |
| 序列化、精确回执、两稿/有限Risk修订 | report_submission、report_contracts、revision；原判断不改、权限先于名额/写入 | test_native_research_submission、test_native_fixture_council；旧交接负例保留 | 无宿主model/author伪身份 |
| 原fixture完整业务与硬Risk | fixture_input、fixture_business、fixture_risk；原Risk函数无损共享；真实输入不能获得fixture动作能力 | test_native_fixture_council、test_risk、test_native_risk_runtime、test_cio_handoff | 合成业务不是实际研究；硬Risk不认证执行/内容/Promotion |
| 历史保真、Memory、中文/网页 | report_packages、report_history、report_reading及既有web消费者；fixture归档冻结源字节，读取不需当前fixture文件 | test_native_research_history、旧Schema/PIT/引用/计算/Artifact/Replay检查 | 原文件不改；旧身份/版本要求仍按原冻结用途 |
| 严格业务版本复用 | 明确对象/hash、完整输入/Gate/任务/依赖及业务资源比较；原cutoff/状态不变 | test_native_research_history及旧Memory混合测试 | UNKNOWN不进入旧严格执行/晋升消费者 |
| 退役第二宿主与控制接线 | 六个launch和两个进程执行器仅拒绝；旧CLI分支删除，正常help不加载控制模块；Shell仅冻结Replay/Tiger只读 | test_native_entry_retirement、test_host_proxy_scripts、test_replay_transport | 冻结Replay未实际运行；不回签旧维护PASS |
| 测试按职责迁移 | test-retirement-map.json逐方法列删除原因/替代覆盖，混合安全与历史读取断言保留 | 已有阶段结果及后续control-retirement-check.json | 不以数量/LOC判通过；原缺依赖失败保留，18项历史上下文已补验，最新有效范围见no-model-closeout-summary.md |
| 中文、安全与入口文档 | 根/产品AGENTS、PRODUCT、README、workflow/environment、运行与Memory手册 | strict、镜像、diff格式及governance | 文档不替实际产品加载/内容证据 |

## 未完成边界

- Tasks当前完成17/24；1.x–5.x实现及其聚焦确定性验证已完成。527项控制/业务/历史焦点检查、297项保留提交/修订/交易隐私/数学/Memory检查及18项历史上下文补验通过，批次重叠不累加为独立覆盖数。实际宿主/内容验收、人工完成和发布仍未完成。
- 缺exchange-calendars==4.13.2的历史live上下文夹具已获用户明确补依赖授权；项目.venv补既有锁定包及必要依赖后完整18项通过（包括原6项），未启动模型/真实取数或改全局配置，见calendar-context-check.json。原失败证据仍保留。
- 三宿主6.1–6.4需用户确认当前产品会话、明确包/安装范围、相同合法冻结公开样本、实际模型/预算、只读权限和独立首轮，见native-acceptance-plan.md。
- 7.1/7.2需要三宿主原报告及明确内容核对、最终人工完成批准。8.1未获归档/发布批准，未Git提交、推送或修改生产指针。
- 未运行产品模型、真实来源/账户、实际Smoke、专项Runtime Eval/Execution Replay/Regression/Calibration/Ablation/Promotion；上述单元测试不属于专项执行。
- 其他Change、Tiger并行实现及已有用户配置/私人状态保留，不合并、回退、归档或发布它们。

## 三宿主零模型准备增量（2026-10-06）

规格中的请求/Gate/角色/工具授权已从三个实际安装副本的MCP stdio完成允许/拒绝检查，来源字节未变；同一公开请求/Gate/候选池、12项准备任务与独立的9项开发探针见[zero-model-preparation-evidence.json](zero-model-preparation-evidence.json)。这只补6.1准备证据，不补宿主原生加载/委派、独立上下文、主线程CIO或内容裁定。

新增原生报告0，三宿主内容裁定均NOT_RUN；7.2映射继续列出6.2–6.4、7.1及最终批准缺口。102项安装前聚焦结果及既有阶段证据复用，本次没有源码行为修改，不为文档更新重跑全批或启动专项评估。

## 当前零模型收尾增量（2026-10-07）

[当前结论](no-model-closeout-summary.md)补齐原生归档→实际网页消费、旧证据有效范围、41个移除测试方法及132项候选差异映射。实际网页/reports已接通原生只读报告，保留私人输入隔离和未验证执行/内容状态；47项当前工作树回归及42项分离候选模块检查通过，两批重叠不累加。发布范围/共享hunk与限定凭据扫描见[release-scope-review.json](release-scope-review.json)，未改变真实index或覆盖并行Tiger文件。

6.1仍待实际宿主权限/隔离、模型预算与合法原生资料血缘；6.2–6.4、7.1无真实报告或执行证据，7.2最终批准和8.1发布未完成。源码/测试新增量如实记录，不以控制路径删除宣称总LOC减少或用量改善。


## 2026-10-07 继续零模型：操作方精确归档接缝

沿提交→Memory→网页追踪发现，`archive_report`此前只有底层调用，操作方无已实现入口将有效提交交付网页目录。本次复用现有连接/任务校验与归档函数，新增`product.tools.prepare archive`：连接/任务凭据及精确有效回执先验，再写Memory与新私有目录的`native-research-archive.json`；不猜最后稿、不覆盖、不新增专业Agent工具/模型编排。归档不含能力凭据，业务保存不升级宿主/内容状态。操作说明见`product/hosts/INSTALL.md`。

首个系统python命令缺jsonschema，两个模块导入错误、实际用例0；改用既有项目.venv，没有安装依赖。第一批42项通过见[原记录](no-model-archive-cli-check.json)。补齐目标目录安全及实际网页消费断言后，操作方、历史、连接、提交及导出43项检查通过，源码测试期间hash不变，见[最终记录](no-model-archive-cli-check-2.json)。覆盖错token/错回执写前拒绝、精确Memory/网页可读、重复导出不覆盖、symlink/公开目录/目标重叠拒绝、凭据不输出。合成测试不是实际模型或内容裁定。

限定实现候选已更新为外置v3补丁，仍132项；未改变真实index或认领并行Tiger修改。已有42项分离网页证据仍适用于两个未改网页模块，不代替本次新入口43项检查。详见[范围检查](no-model-archive-scope-check.json)和[当前发布候选](release-scope-review.json)。原270项安装保持原字节，3项新版源尚未安装；原stdio观察不能回签新版。Change17/24，真实三宿主、资料依赖、内容裁定和人工完成门禁未变，未归档/提交/推送。

最终格式检查补充：候选临时index发现10个新增工具文件末尾多余空行，已只清理EOF且逐文件Python AST不变，见[格式记录](no-model-candidate-format-check.json)。最终外置v4候选`git diff --cached --check`及精确应用检查通过；43项接缝按最终源码重跑通过见[最新记录](no-model-archive-cli-check-3.json)。与原安装批准源有12项字节差异，原安装保持不变；前述3项指行为/说明更新，不含无语义格式。v3及更早补丁仅为历史快照。
