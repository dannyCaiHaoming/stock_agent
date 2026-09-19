# establish-persistent-company-research-memory 实施验收记录

日期：2026-09-19

## 当前结论

资料持久化、增量规划、报告持久化/复用及模型前运行包校验的确定性实现已经接通。受控 MRVL 多时点链路从空库执行真实 normalize、freeze、Schema、身份/PIT、Memory、Gate、prepare 与专项 validator，并通过跨进程复用、T1 增量、中间交易日缺口、价格修订隔离/修复及 raw-object 闭包验证。第二次独立复核指出的 stale DELTA raw 修复、生产中间交易日检测和逻辑请求重复计数均已修复并补证；第三次独立只读复核返回 PASS，没有 HIGH/MEDIUM 阻断，其唯一 LOW 建议的版本选择三分支也已固化为仓库单测。用户于 2026-09-19 明确授权将可联系邮箱仅作为本次 SEC User-Agent，并授权稳定外置目录写入；真实 MRVL 数据侧 T0、背景 sidecar 补建和新 run_dir 全复用均已通过。最终稳定 Memory 包含 2,491 个事实版本、2,491 个 observation、7 个 dataset checkpoint 和可读取对象，第二次修复后重启的所有数据集实际请求均为零，仍生成合法 Company task，且 `model_started=false`、`llm_calls=0`。第四次独立复核发现 sidecar 与 snapshot 的对象引用曾在成功 checkpoint 之后分步写入，可能在崩溃或陈旧执行下留下“fresh 但不可读”的状态；现已将对象引用、成功 attempt 与 checkpoint state 纳入同一 revision-CAS 事务，并增加 checkpoint 更新故障注入与陈旧 plan 回归。最终独立回查返回 `CHANGE_REVIEW: PASS`，无 HIGH/MEDIUM/LOW 问题，并确认无需为最终确定性对象格式重复执行真实联网验收。用户于 2026-09-19 明确批准本 Change 完成及归档、提交、推送。

## 证据矩阵

| 能力 | 状态 | 证据与边界 |
| --- | --- | --- |
| 资料持久化与 raw closure | PASS（确定性） | `tests/test_research_memory_chain.py` 的 T0 从空库生成非空 `fact_versions`、至少 6 个 dataset checkpoint、可读取 raw object，并通过实际 Company prepare validator。stale DELTA 对象删除会生成 365 日 `RAW_CLOSURE_REPAIR` 并保留 9 月 9 日旧事实；对象损坏且响应缺旧事实、以及 cache A→B 无法完整重建时均在成功 checkpoint 前失败。`tests/test_research_memory.py` 另固定“已知旧版本拒绝、较低 rank 新版本拒绝、真正胜出的未知新版本允许”的 preflight 边界。 |
| 增量获取 | PASS（确定性） | 同一测试的新进程 T0 restart 不进入 Provider；T1 跨 freshness 后只请求有界 tail，旧 annual filing 网络请求保持 1 次，新 quarterly filing 获取 1 次，新版本增加且旧历史仍满足 Evidence Closure；T1 新 Evidence 通过运行包绑定的 `fixture_runtime.query` 实际读取。 |
| 缺口、修订与请求审计 | PASS（确定性） | 生产 `normalize_cached_research_series` 通过锁定日历发现来源漏掉的已完成中间 session，T1 写入 `YAHOO_COMPLETED_SESSION_MISSING`，补齐后清除；休市/未完成日不进入该缺口。生产链对 9 月 14 日价格口径修订写入 `PRICE_BASIS_REVISION`，冻结输入暂时移除不一致历史序列，下一次有界 repair 后恢复。routing+单次 provider HTTP 记录为 1 次 logical、1 次 actual。 |
| Provider 归因 | PASS（确定性） | 当前估值 checkpoint 使用逻辑 `market` provider，实际 `actual_providers` 保留 Yahoo/Eastmoney 选择；Eastmoney fallback 不再写入 Yahoo checkpoint。Yahoo 日线研究序列仍独立绑定 `yahoo`。 |
| 故障隔离 | PASS（确定性） | 实际采集入口分别注入 SQLite `OperationalError` 与 `IntegrityError`：失败证券产生 `RESEARCH_MEMORY_PERSISTENCE_FAILED` 外置诊断且不进入 Gate，另一证券继续；快速检查同时失败时以 `RESEARCH_MEMORY_SHARED_FAILURE` 停止批次。 |
| 报告保存与复用 | PASS（已有真实报告＋确定性回归） | 旧 MRVL v3 报告包及 v7 零模型复用继续有效；报告 hash 不变，v7 `process-result.json` hash 为 `b61afd203fdd46f8cf0d944aa9762ad7e787359c80a4605bd9746a0365bc8b0e`。附件、cutoff、问题变化和 mixed RUN/REUSED 由 `tests/test_common_stock_research_contracts.py` 覆盖。 |
| 旧 MRVL Memory 数据侧 | FAIL（历史证据限制） | `/private/tmp/establish-persistent-company-research-memory-store-20260917/research-memory.sqlite3` 为 `fact_versions=0`、`dataset_state=0`、`reports=1`；只能证明报告侧，不能证明资料侧。 |
| 稳定宿主配置与真实 MRVL 数据侧 | PASS（最终对象格式待复核） | 用户已明确批准将可联系邮箱仅作 SEC User-Agent，并批准写入 `/Users/caihaoming/Library/Application Support/StockAgent/research-memory`；仓库和验收记录均不保存该邮箱。完整锁定依赖环境实际加载 `exchange-calendars 4.13.2` 与 `certifi 2026.7.22`。v5 首次成功写入 2,491 个事实版本、2,491 个 observation、6 个基础 dataset checkpoint 和 1 个 View；随后重启暴露背景 sidecar 未独立持久化。v6 仅补建该 checkpoint，其他 6 个数据集为 `SKIPPED_FRESH/CACHE_HIT`；v2 新 run_dir 的 7 个数据集全部零请求，事实/observation 均不增加，Gate 的 2,333 条 allowed evidence 与 Company request 的 bundle hash 一致，仍生成 1 个合法 task。最终库为 `fact_versions=2491`、`observations=2491`、`dataset_state=7`、`research_views=4`、`attempts=56`；对象目录 2 个，raw-cache objects/records 各 37 个。输入 Handoff/source-access hash 分别为 `a6cbd7f8ca8294bc7993af30cce224c16419f622ad1e838513b69f2237164012` 与 `5ebbc4ff3f8c115516a224d1f411f1d9e3d24abca4209e78a56617fd02e34bab`。v6/v2 保存的是修复过程中的完整 sidecar 对象；最终代码改为只保存可跨 Gate 重建的外部采集结果，并在当前 Gate 上重新组包。该最终格式的首次写入、重启零重抓、事务回滚和 CAS 已由生产入口确定性测试证明；未在没有新增授权的情况下再次联网改写稳定实例。 |
| 独立复核 | PASS | 第一次复核的 cache closure、Eastmoney 归因及证据缺口已关闭。第二次复核发现的 stale DELTA 静默丢历史（HIGH）、生产未检测中间已完成 session（HIGH）、routing/HTTP 重复记 logical（MEDIUM）均已关闭。第三次整体复核及授权后错误码增量复核均返回 PASS。第四次最终复核发现 sidecar/snapshot 的对象 state 与成功 checkpoint 分步提交（MEDIUM）；改为 `ingest_dataset(..., state=...)` 的同事务 revision-CAS 并补齐成功、回滚、孤儿对象及陈旧计划正反例后，最终回查返回 `CHANGE_REVIEW: PASS`，无 HIGH/MEDIUM/LOW 问题；明确现有 v6/v2 真实证据与最终确定性生产入口回归足够，无需新增真实联网运行。 |

## 实际确定性检查

- `PYTHONPATH=/private/tmp/stock-agent-test-deps python3 -m unittest tests.test_research_memory tests.test_research_memory_chain tests.test_live_sec_client tests.test_live_collection tests.test_live_contracts_gate tests.test_common_stock_research_contracts tests.test_technical_research`：177 项运行成功，其中 176 项通过、1 项按既有可选 SDK 条件跳过。
- `PYTHONPATH=/private/tmp/stock-agent-test-deps python3 -m unittest tests.test_multidimensional_stage tests.test_live_admission tests.test_live_cli tests.test_live_host_entry tests.test_host_proxy_scripts tests.test_governance`：61 项通过。
- 受影响 Python 文件 `py_compile`、launcher `bash -n`、JSON 解析和 `git diff --check`：通过。
- `openspec validate establish-persistent-company-research-memory --strict`：通过。
- `scripts/council-dev.py self-check --help` 按控制面返回 `SELF_CHECK_COMMAND_NOT_ALLOWED`；对旧普通股专项 run 误用通用 Council `check-run` 返回缺少 `decision_trace.json`。这两项保留为原始失败/不适用证据，不记 PASS。普通股专项使用生产 `validate-common-stock-research` 的同一 validator；受控 T0/T1 运行包均返回 `PREPARED`、`dispatch_count=1`、`model_started=false`、`llm_calls=0`。
- 实际宿主 launcher 的冻结包 `--prepare-only` 第一次因 source bundle 选错复制层、第二次因系统 Python 缺锁定日历依赖而失败；使用已验证的锁定依赖环境和完整 source package 后成功返回 `PREPARED`、`dispatch_count=1`、`model_started=false`、`llm_calls=0`。结果文件 `/private/tmp/establish-persistent-company-research-memory-prepare-only-20260918-v3/prepare-only-result.json` 的 SHA-256 为 `a51f5f0692a1a5659730974b3e4af4cdec19d6d695ddd0aa7441778960dde3ff`。该运行只重验既有冻结 MRVL 包，不替代 7.7 的真实数据采集。
- 授权后的稳定 Memory 真实采集保留了四次原始尝试。v1 使用了缺 `certifi` 的旧依赖环境，在 `NASDAQ_UNIVERSE` 失败；切换完整锁定环境后 v2/v3 暴露两个运行包错误：失败证券仍进入补充资料组包而遮蔽根因，以及实际 Provider 错误被泛化后与底层错误文件不一致。两项已修复并增加聚焦回归；错误码只允许经批准来源前缀及 canonical 大写语法，attempt、来源包和准备清单共用同一规范值，避免异常正文或联系信息进入审计产物。v4 在同一实际入口稳定记录 `SEC_MAPPING / SEC_HTTP_403`，通过专项运行包 validator，结果为 `PREPARED`、`dispatch_count=0`、`model_started=false`、`llm_calls=0`；这是可审计失败，不是数据侧 PASS。v4 `prepare-only-result.json`、`source-bundle.json`、`collection-error.json` 和 Memory manifest 的 SHA-256 分别为 `a311658368082bfd3bbf0d837cd8a964f483454e5965eb924cb7bc4a4fcb4179`、`1c6c3d0d7cac8518d152905eac5673e90589dbde50fb78bae021e1f4c814dcab`、`961d5771b1ffbb2e587c99ab1dc37f2928d06f7a668bfd4666ed590f0434bd97`、`71e0649206b82af9621b3f8f26b635b1c73e1c1b146d553435562546b23c1e30`。
- 使用获批可联系邮箱后，v5 从同一稳定 Memory 成功完成真实 MRVL 数据准备，返回 `PREPARED`、`dispatch_count=1`、`model_started=false`、`llm_calls=0`，首次落盘 2,491 个事实版本与 6 个基础 checkpoint。紧接的重启运行正确跳过基础数据集，但暴露背景 sidecar 每次重抓且新获取时间晚于复用 Gate cutoff；该运行以 `COMPANY_BACKGROUND_FUTURE_EVIDENCE` 失败，没有启动模型。修复将 sidecar 作为 `company_profile` 的低频内容寻址对象及独立 checkpoint 保存，并允许较早冻结且仍合格的 sidecar 加入较晚共同 cutoff，未来 sidecar 仍拒绝。
- 修复后 v6 只为缺失的 `company_profile` 执行一次 `FETCHED_BOOTSTRAP`，其余数据集请求数为零；结果、source bundle、Gate、data preparation 和 Memory manifest 的 SHA-256 分别为 `2cabfad6a14fba07e97cf09945a5b5748559b957970614b8567a872088f929a5`、`8c2a13c9b30a94cc1e0e984f49ccaa492bcf4e8162706472253e351e918776b5`、`59b359efa17ea6074fbbb1ee5929a7d376fdd8a86124ea4f1c64d2a4162f151e`、`e3604cd26ae476eaee82892e0346840de0aeb00ab21c374cf481399c885a6d60`、`148f8f0a69b19c5ae59a7780e4b87a416959ee5d44345fd5b80cef53d09d6347`。
- 第二个新 run_dir v2 中，`company_profile` 为 `SKIPPED_FRESH`，`live_snapshot` 为 `CACHE_HIT`，其余 5 个基础数据集均为 `SKIPPED_FRESH`；7 个数据集 `request_count=0`、`inserted_versions=0`、`observations=0`。结果、source bundle、Gate、data preparation 和 Memory manifest 的 SHA-256 分别为 `f1fcad733af2dc70eba946ca0ae3ab9138145c09d9e734c601cbd95d052305e5`、`2085b80bd50f9547932bf3df5344896ce5d24e13b9ad77b16c3a5b32f281ff2a`、`ae2d6aa57fd8ac7cfb883a929fb9aa0888899d06a146dad2267c253e8555406a`、`bb698b2a508a4520e2357aa478e4fc203eeea0f4f2e97360b598507732a64465`、`b0c63af16dcfe8b086d6bebebb43a411ae15ff74695f4392d78643c986c26f17`。两次运行的 Gate bundle hash 均与各自 Company request 的 `evidence_bundle_hash` 相同。
- 最终原子性修复把 `state_json` 合并进资料、成功 attempt 和 checkpoint revision 的同一短事务；测试先发布一个新对象，再用 SQLite trigger 在 checkpoint 更新点强制失败，确认新事实、attempt、revision 和 state 全部回滚、旧对象引用保持，先发布对象仅作为允许的孤儿保留。另以旧 revision 提交不同对象 state 时返回 `RESEARCH_MEMORY_CHECKPOINT_REVISION_CONFLICT`，不能覆盖新状态。生产入口两次运行测试确认外部补充采集只在首次执行，fresh 重启读取持久化结果、重新按当前 Gate 组包并记录 `SKIPPED_FRESH`。
- 未触发 Runtime Eval、Execution Replay、Regression、Calibration、Ablation 或 Promotion。

旧验收记录曾把“147 项总运行且 1 skipped”误写成“147 项通过”，正确旧口径应为 146 passed、1 skipped。本轮不再沿用该数字，也不把没有适用成功产物的通用 self-check 写成 PASS。

## 关键实现结果

- Memory 使用外置 SQLite 索引、内容寻址对象、稳定 raw-cache 和按数据集文件锁；报告私人上下文不进入公共事实查询。
- 同一内容版本的后续获取只增加 observation。T1 冻结 View 优先使用本轮重叠窗口的观察绑定，历史研究序列从 Memory 补齐；当前估值 `close_price` 不被历史窗口意外扩宽，历史 raw record 索引继续进入新快照以保持 Evidence Closure。
- snapshot bundle 保存 canonical `cache_root`，任何 fresh reuse 与历史事实合并前都重验 raw-record schema、对象存在性和内容 hash。stale/DELTA 损坏会在网络前提升为有界 repair；仍可读旧对象逐条保留，无法重建的 retained fact 在 checkpoint 写入前阻断。交易日历窗口 hash 只属于采集 provenance，不再造成相同 Yahoo 事实的伪版本或伪修订。
- dataset outcome 区分 `SKIPPED_FRESH`、`CACHE_HIT`、`CHECKED_NO_CHANGE`、`FETCHED_*`、`NOT_ATTEMPTED`、来源失败、验证失败和持久化失败；实际 transport/cache 事件提供逻辑请求、实际请求、缓存和重试计数。
- 当前估值的 route-level checkpoint 使用 `market` provider，attempt 另存实际 Yahoo/Eastmoney 来源；只有真正的 Yahoo 日线研究序列进入 `yahoo_daily`。
- SEC 汇总仍按 TTL 检查，稳定 accession 文档按不可变身份与原文 hash 复用；对象缺失/损坏只允许一次 Provider 验证恢复，不伪装缓存命中。
- launcher 新增的 `--prepare-only` 只适用于普通股研究阶段，跳过代理/模型启动，在真实采集、Gate 和 prepare 后执行专项运行包 validator，结果只能是 `PREPARED`。
- 公开背景 sidecar 复用现由既有 `company_profile` 数据集策略控制：首次或过期时采集外部来源结果并写入内容寻址对象，对象引用、成功 attempt 与 checkpoint state 原子提交；fresh 重启读取这些结果、结合当前基础 Gate 重新生成运行级冻结 package 并记录 `SKIPPED_FRESH`。sidecar 不被伪装为基础事实版本，不新增 Agent、数据库或调度入口。
- live profile 已与实际 Company Agent 的 `research-report-analysis` Skill 锁同步，修复了原有 live prepare 的配置漂移。

## 既有 MRVL 报告侧证据

用户此前明确授权的唯一一次 MRVL `gpt-5.6-terra` 调用已在 v3 消耗完毕；本轮没有增加模型调用。v3 生成并持久化 `US:COMMON_STOCK:MRVL` 报告，v7 在严格输入等价下 `reused=1`、`model_started=false`、`pid=null`，`checked_at` 更新而 `original_report_cutoff` 不变。该证据只证明报告保存与严格复用，不证明 Provider 资料已进入旧 Memory；旧库统计限制已在矩阵中单列。

## 待完成

无。本记录不代表候选晋升，也未触发 Runtime Eval、Execution Replay、Regression、Calibration、Ablation 或 Promotion。
