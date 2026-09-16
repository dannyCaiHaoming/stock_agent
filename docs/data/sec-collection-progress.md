# SEC 采集与外置缓存阶段记录

## 2026-09-10 后续执行：有限比较、披露选择与附件接缝

Task 2.3 完成依据：`disclosure.py` 的章节/总长度预算、缺失及遗漏位置记录；`financials.py` 的同证券/发行人/标签/单位/上下文、非重叠日历周年比较与父证据/hash/公式/版本。正负测试覆盖 YTD 与单季不可混算、单位/指标/证券不匹配、非有限值、缺失/重复父证据、瞬时事实、非正基数及未来父时间不回填。恶意文本只作为带 `untrusted_data` 标记的数据；不宣称实现运行时防注入或完整财报识别。

计算输出绝对变化及正基数百分比，不生成观点或动作。不提供 TTM；52/53 周或无法严格匹配的期间明确拒绝比较，不估算补齐。完整 live Schema 与 PIT 接入仍由其他任务负责，此处的计算不会自行宣称父证据已获 Gate 允许。

Task 2.2 部分推进：按已有披露选择最近年报、较新季报及 90 天内最多三份 8-K，附带年/季报修订而不以修订替换基准报告。选择参考时点是 `selection_as_of`，不是尚未冻结的最终 decision_cutoff。附件按索引中的 EX-99 与明确业绩描述匹配，验证同 accession 档案目录、保存索引原文 hash/行号与附件来源，未知用途/遗漏明确记录。索引格式变化不代表已验证覆盖，不猜测外站链接。

实际执行：`python3 -B -m unittest discover -s tests -p 'test_live_*.py' -q`，**38 项通过**。其中新增 13 项覆盖有限比较、披露选择、附件及整个读取/提取接缝；全部使用合成响应与 fake transport，无网络/模型访问，临时缓存由测试清理。无环境错误或断言失败。原有相关测试在本次版本重新执行；不复用旧 Council PASS 为新代码背书。

| 当前被测文件 | SHA-256 |
| --- | --- |
| product/mcp/live/financials.py | 9ac02ad7917da3659996365efad020e9081c9e3be747ca3407e6717b74df5efa |
| product/mcp/live/filing_selection.py | a5caa70edd3b77210b824ecde2aed228cea3a0ae90d5eb81556e58cd25fe487d |
| product/mcp/live/attachments.py | 0efb16c23b8f0bc9c8f116c3c7a4af7a69fbd73f23b0267c4b01dd4656b668d0 |
| product/mcp/live/sec_client.py | c862245978363f1ed77fc24359057453c1ccdbf30baaf8ccc909cafb9a7e6a33 |
| product/mcp/live/disclosure.py | 3aac9c60f93e10c8dc6afa6fd80e7d5180c7734daddcce39ef53a914980878dd |
| tests/test_live_financials.py | 2b6e460307bf156c4bcca5643b0859c77f66ad755ac20b77af826b5744706952 |
| tests/test_live_filing_selection.py | 294fa8c08243fbbe37fc1e971aae0fed336931dd38ad661907d190ac2d2c870c |
| tests/test_live_sec_client.py | a94d3d45d83bb4bab36cdfb7529a6c1461636c7c727e90154a6261cd0fe626ae |
| tests/test_live_disclosure.py | 9bee735057b6d65545f416d52266df6b2bf15e1f092173c2c084d8c17e817fe2 |

总体进度：1/21 项完成。Yahoo 仍暂停，其他任务未提前勾选；证券身份映射、live 契约、PIT/价格/运行接缝与真实验收仍未完成。本记录不代表 Change 完成、候选晋升或全进程隔离通过。

## 2026-09-10 后续进度：历史分页与披露文本

本节为后续执行记录，不覆盖下方早期 hash/结果。

- Task 2.2：新增主 submissions 列表驱动的同 CIK 历史页读取；限定页数、去重，记录未读取页。历史财务的公开时间来源保留实际分页 URL 和原始分页 hash，不伪装成主响应。合并 accession 实质冲突时拒绝；仍需补披露选择/附件与真实数据核验。
- Task 2.3：新增 `disclosure.py`，严格解码、移除 script/style/ix:hidden 内容，以章节标题匹配提取业务、风险因素、管理层讨论；保留原始 HTML 字符区间、原文 hash、编码、解析版本、章节与总长度预算。重复标题保留独立位置并共享章节预算，不宣称已区分目录与正文。无法识别的章节报告缺失。
- 文本标记为不可信数据，保留普通文本中的恶意指令供后续受限研究处理；本次不证明运行时防注入能力。字符位置是解码后原始 HTML 的 end-exclusive 区间，不冒充字节偏移。

实际命令：`python3 -B -m unittest discover -s tests -p 'test_live_*.py' -v`；25 项通过（原 18 项 + 分页 2 项 + 文本 5 项），无环境错误/断言失败。输入为测试内合成响应；临时缓存由测试清理。`openspec validate us-equity-live-advisory-slice --strict` 通过。未联网、未调用模型、未修改入口/代理，未运行全量 Gate。

| 当前被测文件 | SHA-256 |
| --- | --- |
| product/mcp/live/sec.py | 73591f45323714bfa912c9c765c92d59e7e7f18ac248c2660cd0042b28ad4667 |
| product/mcp/live/sec_client.py | 297e0a2e70d9cd5eaf0e2958442feca7ad35dfa4c96798ea6ce9ab6f67d84943 |
| product/mcp/live/disclosure.py | 08465736e4e778ef1c20b0a4729aeef3cc2a9a0ca4cdec3211e38680441ed8e9 |
| tests/test_live_sec_client.py | f519997407ce63c1af8d5abe4b8dfd9220e7d14c7a65c0f7fcfd01bd5111009b |
| tests/test_live_disclosure.py | 432ce64a26a252373b0c5be3810ce7ea2a7043e22fe7688c81fe8aa80feba285 |

解析与客户端版本提升为 0.2.0，避免新旧缓存键混用。旧记录仅证明当时版本；本轮重新执行受影响测试。Task 2.2/2.3 保持未完成：财务可比计算、披露选择/附件、真实格式与链路接入仍缺实现/证据。PIT、live Schema/profile 与 Council 接缝未完成，不具备人工完成批准条件。

日期：2026-09-10。Change：`us-equity-live-advisory-slice`。

## 实施与验证范围

本轮继续 Task 2.2/2.4，保留 Yahoo 抓取暂停。新增 `sec_client.py` 为 SEC 适配的内部辅助模块，不是新的运行入口或 LLM 编排层。

- SEC 只读 GET：限定 submissions、companyfacts、ticker 映射及披露档案路径，拒绝任意域名、查询参数和跳转。联系身份仅在内存请求头中使用，不写缓存或事件。
- 串行单客户端请求间隔至少 0.5 秒；每次采集最多重试两次，所有尝试计入预算；401/403 不重试。Retry-After 超过等待预算时停止，不截短等待后继续请求。此限制不代表已实施跨进程总限流。
- 外置缓存按内容 hash 保存对象，追加版本记录作为索引；缓存命中保留原获取时间，刷新相同内容保留第一次获取时间，新内容追加，旧引用不覆盖。读取验证 hash，损坏不静默重新下载。
- 集合去重、部分失败及请求计数；最近 submissions → companyfacts → 指定披露原文的采集/解析接缝已用合成响应跑通。

没有实际访问 SEC/Yahoo，没有调用产品模型、修改宿主入口或代理。没有使用用户邮箱。测试联系身份为 `.invalid` 合成地址。

## 实际命令和结果

`python3 -B -m unittest discover -s tests -p 'test_live_*.py' -v`

18 项测试通过，其中原解析 8 项、新增采集缓存 10 项。写入均在测试创建并清理的独立临时目录；未出现环境错误或断言失败。输入为两份测试文件中的合成响应，产物为临时缓存对象/记录及测试输出，不将其冒充真实运行包。

`openspec validate us-equity-live-advisory-slice --strict`

通过。`git diff --check` 无输出；当前新增文件未暂存，该命令不能代替对新增文件的审阅。本轮未执行全量测试、Smoke、Regression 或 Gate。

## 新增被测文件 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| product/mcp/live/cache.py | 86886dada17a370c0d07019cc2708b5f0e228e5fccbd9945899cf927e5f50551 |
| product/mcp/live/sec_client.py | 61585ffe0440638b6363366c5517bbbc7c9f70a8e3035f98733ddbf73f73e328 |
| tests/test_live_sec_client.py | 4d21c842e14e5314daa0c7b2bfdde7f6a60d0c8e321a0909505ce5cc68f94250 |

旧解析文件未修改，hash 见 `sec-parser-progress.md`；本轮重新执行其 8 项测试。历史 Council 证据不用于证明新采集代码。

## 任务映射与剩余边界

对应 `live-us-equity-data` 的 SEC 追溯、有限重试、批量缓存及私有边界要求；本次只覆盖这些要求的局部实现。

- Task 2.2：尚缺历史分页完整接入、披露选择与相关附件覆盖、真实访问证据。当前明确输出 `RECENT_SUBMISSIONS_ONLY`，未知 accession 被隔离。
- Task 2.3：章节提取、截断定位及可比财务计算尚未实现。
- Task 2.4：SEC 缓存与有限请求已有测试；行情参数化缓存、完整采集增量策略及快照集成尚未完成。当前本地记录扫描索引不宣称全市场规模能力。
- PIT、live Schema/profile、组合估值与 Council/Eval 接缝尚未接入；缓存可用不等于事实已通过 PIT。

以上任务保持未勾选，不扩大证据证明范围；Change 仍在实施中，不具备完成批准条件。
