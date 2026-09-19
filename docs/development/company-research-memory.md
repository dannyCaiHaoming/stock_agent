# Company Research Memory 运行说明

`Company Research Memory` 为普通股基本面资料和已验证 Company Agent 报告提供单机、跨运行持久化。它不包含回测、历史 Agent 重放、后台刷新、远端同步或交易能力。

## 稳定目录与启动边界

Memory 必须位于源码仓库之外的稳定本地目录。显式 `--memory-root` 优先于环境变量 `RESEARCH_MEMORY_ROOT`。自动 live 采集在任何 Provider 请求之前验证该目录；缺少配置、目录位于仓库内、符号链接或权限不足都会失败。预先冻结的 fixture/prebuilt 数据仍可在不配置 Memory 时运行，但不会获得跨运行资料或报告复用。

```sh
export RESEARCH_MEMORY_ROOT=/absolute/external/path/stock-agent-research-memory
scripts/run-product-smoke.sh ...
```

需要只验证真实数据准备、Gate 与 Company 运行包而不启动模型时，使用现有宿主 launcher 的模型前停止选项：

```sh
scripts/run-product-smoke.sh --stage common-stock-research --prepare-only \
  --handoff /absolute/path/to/confirmed-handoff.json \
  /absolute/path/to/new-output-directory
```

该模式仍要求 `LIVE_SOURCE_ACCESS_FILE`、合规 `SEC_USER_AGENT` 和稳定 `RESEARCH_MEMORY_ROOT`，结果只能标记为 `PREPARED`；它不代表 Company Agent 已运行或研究已完成。

默认原始响应缓存位于 `$RESEARCH_MEMORY_ROOT/raw-cache`。数据库为 `research-memory.sqlite3`，大对象位于 `objects/`，数据集进程锁位于 `locks/`。不要把这些目录提交到 Git，也不要将它们放入单次运行输出目录。

每个冻结 snapshot bundle 都绑定生成它的 canonical `cache_root`，复用前会重新读取并校验全部 raw object；切换显式缓存目录、对象缺失或内容 hash 不符时不会继续走 provider-zero 的 fresh bundle 复用。系统会在网络前把既有计划提升为显式 `RAW_CLOSURE_REPAIR`，Yahoo 使用最多 365 日窗口，并逐条保留仍可验证的旧对象。修复无法覆盖当前 View 必须保留的旧事实时，该证券在任何成功 checkpoint 写入前失败关闭；不会静默删历史后宣称刷新成功。

## 首版增量政策

| 数据集 | 首次范围 | 刷新与重叠 | 有界限制 |
| --- | --- | --- | --- |
| Yahoo 日线/公司行动 | 最近 365 个自然日 | 成功检查超过 24 小时、已知缺口或新完成交易日；策略记录 5 个交易日重叠 | 一次正常区间请求；有修订证据时最多一次 365 日窗口内修复 |
| SEC 身份 | 当前映射 | 24 小时或身份变化线索 | 仍受现有 SEC 总预算；身份不确定时只失败该证券 |
| SEC submissions/companyfacts | 既有 7 年度/24 季度上限 | 24 小时或新 accession 线索 | 汇总端点各一次逻辑刷新，历史分页最多一页 |
| SEC 文档 | 既有 selector 选择的年报、季报、事件及附件 | 新文档身份或明确修订线索 | 旧文档不会仅因 TTL 重下；超预算保留待补状态 |
| 当前估值/公开补充 | 各数据集既有有界快照 | 默认 24 小时；公司简介 7 天 | 每数据集一次逻辑采集；可选来源失败形成缺口，不无限重试 |

当前估值 checkpoint 使用逻辑 `market` provider 表示既有 Yahoo→Eastmoney 路由；每次 attempt 的 `actual_providers` 保存实际选中来源。Yahoo 日线研究序列仍单独记为 `yahoo`，因此 Eastmoney fallback 不会被伪记成 Yahoo 历史序列成功。

采集前的 `planning_as_of` 只用于规划请求；Provider 响应保留真实 `retrieved_at`；采集完成后才确定 Research View 的 `decision_cutoff`。checkpoint 保存覆盖与待补缺口，失败不会推进成功水位。Yahoo 研究序列会用锁定交易日历核对实际返回行之间的已完成 session；来源漏掉的中间交易日记录为 `YAHOO_COMPLETED_SESSION_MISSING`，周末、休市和尚未完成的 session 不会误报。历史事实不会因一次刷新失败失效，但当前价格仍必须通过现有 Gate 时效校验。

每次结果区分缓存跳过、实际检查无变化、首次/增量获取、未尝试、来源受限、验证失败和持久化失败。单证券 SQLite 写失败会回滚该事务、生成运行目录诊断并阻止该证券派发，其他证券可继续；若轻量完整性检查也失败，则按共享库故障停止整个批次。不可变 SEC filing 文档不因普通 TTL 过期重下；对象缺失或损坏时只允许一次受预算约束的 Provider 验证恢复。

## 报告保存与复用

finalizer 仅在报告 JSON/Markdown、Evidence Closure、计算引用和附件绑定全部验证后保存报告包。报告包包含原请求、选中 Evidence、引用计算、冻结附件、校验记录及闭合 manifest；数据库只保存索引，私人问题不会进入公共事实表。

复用要求当前 `research_input_fingerprint` 完全等价，覆盖证券资料、冲突/缺口、附件与图形、用户问题/Thesis/持有期限、模型、Agent、全部 Skill、输出 Schema 和语义策略版本。同一 `decision_cutoff` 可作为完全相同冻结输入的原样重放；cutoff 变化时还必须由本次 live 数据包证明所有纳入政策的数据集均已成功检查、没有待修缺口，并绑定本次不可变 Research View。任一来源刷新失败、结果缺失或绑定无法证明都会拒绝复用并创建新 Invocation。引用会同时显示本次 `checked_at` 与原始 `original_report_cutoff`；“今天检查仍可复用”不等于“模型今天重新研究”。对象缺失/损坏或使用 `--force-rerun` 时也会创建新 Invocation。

全部目标复用时，launcher 直接执行确定性 finalizer，父模型和 Company Agent 调用数均为零。混合运行的 dispatch-index 只包含真正需要 `RUN` 的证券。

指定报告保存失败后，可在原报告文件仍完整时执行确定性补存：

```sh
python3 scripts/council-dev.py persist-common-stock-report \
  --repo /absolute/path/stock_agent \
  --run-dir /absolute/path/to/run \
  --security-id US:COMMON_STOCK:MRVL
```

补存会重新验证既有报告并幂等写入，不访问 Provider、不调用模型。

## 备份、恢复与诊断

不得在进程运行时只复制 SQLite 主文件，因为 WAL 可能包含尚未 checkpoint 的提交。使用 `ResearchMemory.backup(destination)` 生成 SQLite 一致性备份并复制被引用对象目录。恢复后先运行完整 `integrity_check()`；正常启动只运行轻量 `quick_check` 和必要表检查。遇到未知更高 schema、损坏对象或迁移失败时停止自动链路，不覆盖重建。

运行输出中的 `research-memory/manifest.json` 和每证券 View 用于审计本次 plan、checkpoint revision、选中版本与复用状态；稳定数据库及对象仍只存在外置 Memory。
