# 三宿主验收样本准备结论：已有资料可用，未运行模型

- `source_id`: `native-public-sample-readiness-result:20261006`
- `as_of`: `2026-10-06`
- `retrieved_at`: `2026-10-06`
- 范围：原稳定备份/Memory只读核对，保留原文件和历史判断；没有联网补采、安装产品、创建实际任务/连接/token或模型调用。

## 一句话结论

后续用户已批准“MRVL＋补齐接缝”，下文中的“建议/仍需确认”是当时准备状态；当前选择、已完成补验和仍待批准的实际安装/产品模型见[preinstall-readiness.md](preinstall-readiness.md)，无需再次询问是否采用MRVL。原事实、失败与缺正文范围保持。

**不是旧研究证据都丢失。MRVL的公共冻结Gate、准备尝试与同行物化闭合，公共身份可以通过现有校验形成新的非持仓输入；ALB的事实视图和原Company包也仍在。** ALB原完整八维冻结包未找回，不能拿Company包充当全链资料。建议使用既有MRVL公开冻结资料作为三宿主候选样本，但更换原定ALB样本仍需用户确认。

## 1. MRVL：候选公共资料已实物核对

原备份在宿主的StockAgent/acceptance-runs/eight-dimension-rebuild-20260928。只读核对指定八维版本及其data-v2/host-v2公共来源，不读Handoff、账户、持仓正文或原模型转录。

| 检查 | 实际结果 | 证据 |
| --- | --- | --- |
| Gate原字节与历史版本 | SHA-256与2026-10-01清单相同；envelope、允许ID唯一性/集合一致 | mrvl-public-backup-readiness.json |
| 事实范围与时间 | 8835条允许事实；source_id/as_of/retrieved_at完整，无晚于cutoff或反向时间；检查的账户/凭据键无命中 | 同上 |
| 同行 | ADI/MPWR原物化FROZEN；manifest/file hash/最终View/Gate/事实集合绑定通过 | 同上 |
| 资料准备收据 | copied output/artifact与原source/import记录相等；尝试保留 | 同上 |
| 公共身份 | 原SEC映射和证券元数据可通过现有build/validate_single_stock_request；MRVL/XNAS/US普通股RESOLVED | mrvl-public-input-validation-v2.json |
| 新非持仓输入候选 | 仅内存构造；无Handoff/账户/数量/现金/成本/Mandate，不复制原持仓 | 同上 |
| cutoff | 保留2026-09-28T12:35:32.208143Z，不推进为latest或当前行情 | 同上 |
| 原数学 | MRVL/SPY技术及市场20/60/252窗口COMPLETE；不生成投资评分/结论 | 同上 |
| 原件保护 | 本次核对的原Gate/材料/同行/快照文件SHA-256前后相同 | backup及identity metadata证据 |

这是样本准备和业务准入检查，不是实际宿主、内容或Promotion PASS。原报告及执行事件不复制为本次新研究证据，也不进入独立Skeptic首轮。

### 原资料的真实限制不能删除

- RESEARCH_REPORT_DISCOVERY：SOURCE_LIMITED，选中的BODY_VERIFIED独立正文为0。
- MACRO_RESEARCH_DISCOVERY：BLOCKED_CONFIGURATION，选中的BODY_VERIFIED正文为0。
- MARKET_RESEARCH_DISCOVERY：SOURCE_LIMITED，选中的BODY_VERIFIED正文为0。
- PEER_SELECTION：READY，ADI/MPWR已物化为原公共事实。

上述不能解释成原资料丢失，也不能把0个已选择正文的空集合校验称为“正文齐全”。Gate仍包含合法公司/市场/宏观事实，可以验证有界研究与真实限制披露；若要求实际read_documents正向执行，需要另外明确样本正文或资料准备授权，不能自动联网补齐或伪造BODY_VERIFIED。

初版内存探查直接给所有能力传全Gate/同行集合，不能当真实任务允许集；已保留初版，将v2按生产prepare_task的证券预筛选及仅Industry同行范围重验。v2是当前范围核对依据，不修改生产权限/源资料或研究判断。

## 2. ALB：仍有保存资料，不是只剩报告

稳定Memory主文件的不可变只读快照中：

- 4763个ALB事实版本；3份已保存Research View，原selected_fact_versions分别3513/3513/3463。
- 三份View的schema/envelope与事实版本hash、逻辑键及PIT引用均通过；没有缺失引用，检查的账户键无命中。
- 原Company内容对象仍存在、字节hash有效，确认为SINGLE_STOCK_RESEARCH/holding-research-request v2；原run与原cutoff 2026-10-02T02:51:27.261450Z一致。
- Company包保存4023条Evidence、3份计算，request/evidence/calculation/attachment组件hash通过。
- Company对象不包含原完整single-stock-research-request、完整Gate或八维/同行总包，不能假称完全恢复原研究批次。
- ALB当前dataset checkpoint没有可验证的live_snapshot对象引用；不能从“有事实”推导全链包恢复。

证据：[public-memory-view-readiness.json](public-memory-view-readiness.json)、[alb-public-package-metadata.json](alb-public-package-metadata.json)、[alb-public-snapshot-metadata.json](alb-public-snapshot-metadata.json)。Memory采用immutable只读主文件快照，不回放live WAL；查询公共事实/视图和对象索引，不迁移数据库，不输出/采用旧报告判断。

部分早期MRVL视图在同一主文件快照中有568个无法解析的版本引用，原有限问题保留；它们不是本次选择的2026-09-28MRVL公共Gate候选，不通过删视图或选择“最新”掩盖旧证据限制。对应两份2026-09-28事实视图引用已通过。

## 3. 现在具体还有哪些事

### 已解决，不再要求用户做

- 不需要用户寻找/整理MRVL原备份；目录工具曾无法解析，宿主Terminal已经找到并核对。
- 不需要手工做Gate或伪造非持仓输入；公共身份可经现有确定性校验使用。
- 不需要为了“比对结果”重新采集全部事实；新旧报告不要求逐字/观点相同，核心是同源证据、安全和业务/实际执行/内容的分别验收。

### 安装前需收敛的实现/来源项

前次251项来源是待审候选，不是已批准安装。已发现operator prepare.py未被原测试导出闭包覆盖，可选同行操作入口的静态闭包仍牵入旧Hook控制代码。这是项目侧的具体安装前工作，不是让用户找文件解决。需要按已批准Change目标核对/修复与聚焦验证；当前只读准备未擅自编辑生产源码、隐去旧导入或宣称完整可安装。

既有旧冻结准备manifest与新原生material_inputs不能仅改schema/hash冒充原生报告；实际样本接入须明确复用公共事实/合法已选择资料及原限制，不能让程序替模型重新选择证据或消解BLOCKED_CONFIGURATION。未实现的入口仍需相应任务准备验证，不仅靠安装说明宣称可用。

### 需要用户决定或后续批准

1. **样本决定**：建议三个宿主统一采用本次已核对的MRVL公开冻结资料，而不是强行用不完整ALB八维包；原来源受限/配置失败保留，新研究仍非动作。未自动替换ALB方案。
2. **安装范围批准**：新的外置产品工作区与精确来源；Claude Code先，后Codex/OpenCode，不覆盖现有.claude或全局配置。
3. **真实执行批准**：每宿主实际模型、调用/时间上限及停止条件；后置单独确认，不从“继续准备”继承。

## 4. 建议推进方式

先确认MRVL作为候选，并恢复安装前实现核对/聚焦修复（仍零产品模型、不联网取数、不安装或改用户配置）。主开发完成可安装来源和样本准入清单后，再请求外置工作区安装授权；安装/加载就绪后再请求真实产品预算。不要在一个模糊“继续”里混合这些批准。

6.1仍是准备中，Change17/24。三宿主实际研究、内容核对及人工完成/归档发布均未完成；不重复索取已经获批的只读查找授权，不宣称缺少旧证据就无法完成Change。
