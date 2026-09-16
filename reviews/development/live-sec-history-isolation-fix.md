# SEC 三股采集兼容修复

## 人工批准与范围

2026-09-11 用户针对 `live-three-sec-history-blocker.md` 提出的“历史索引缺文档名显式隔离、危险路径及其他完整性错误继续拒绝、继续三股验收”答复“好”，批准本次实施。对应 Task 2.2/5.3，非最终完成批准。Proposal、Design 3、live 数据规格及 Tasks 已同步。

## 实现与真实原始响应

- `sec.py`：只在历史分页提供隔离记录容器时处理空字符串；先检查结构、accession、时间、期间和重复，再隔离。记录 `sec-history-isolation/1.0.0`、行号、source_id、as_of、retrieved_at、原文 hash；无 URL、无可用 filing。recent 空文档名仍拒绝。
- `sec_client.py`：保留隔离记录；跨页及 recent 与隔离 accession 冲突仍拒绝。存在隔离时 coverage 为 `PARTIAL_LISTED_HISTORY`，companyfacts 无合格 filing 继续排除。
- `collection.py`：隔离内容进入采集事件及快照缺口，原始页照常保存，不偷偷跳过。
- 苹果原失败页原文 hash `25eca683c9774d8d92dcc4e3e2381ca1a89fc5ceb325e46dff6defee78380899`：离线实际解析得到1137条可用 filing、109条隔离，无交叉；后续真实采集事件亦记录 AAPL 隔离。
- 苹果后续真实身份绑定失败为交易所全名未映射，非两来源真实矛盾。SEC 封面 hash `4ad5bea67cedfa7542d623900355cc8d143ef95c1acc135a597f2eedabdb9177` 的同一 c-2 context 包含普通股、AAPL 和 `The Nasdaq Stock Market LLC`。只新增该完整名称到 XNAS 的精确映射，不模糊匹配。名称/MIC 对应另见 [SEC 公开申报](https://www.sec.gov/Archives/edgar/data/1650107/000165010726000042/a20260401ccepform6-kmonthl.htm)，未将此开发核对加入投资 Evidence。
- NVDA recent 页 hash `c44def4586aa95ededa9c9ef4516d17843de9ba8e9bc738f421b0cf6c3f1b33d` 含两条 N-PX 路径 `xslN-PX_X01/primary_doc.xml`。只为既有单层 xsl 目录名增加连字符字符类，不允许额外目录、点路径、URL、编码斜杠或穿越。不隔离非空非法路径。
- NVDA 季报 hash `e2634e509c241c5f45e3f6c115dc38a85645e5fdbee760b4a04f5e9035f6f7a9` 的 c-1 context 使用 `The Nasdaq Global Select Market`。新增这一精确 Nasdaq 名称映射，沿用既有 XNAS 市场归一口径，不接受带额外后缀的未知名称或与 XNYS 行情冲突。

## 实际局部测试

环境：既有 live 合并 Python；独立 `TMPDIR=/private/tmp/stock-agent-sec-history-tests.LhBkHy`；零网络、零 LLM。

```sh
env TMPDIR=/private/tmp/stock-agent-sec-history-tests.LhBkHy PYTHONDONTWRITEBYTECODE=1 /private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest tests.test_live_sec tests.test_live_sec_client tests.test_live_collection tests.test_live_filing_selection tests.test_live_financials tests.test_live_security_metadata -q
```

最终结果62项通过，0失败、0跳过，退出码0。包括原文血缘、财务排除、隔离行重复/非法时间/非法路径、采集冻结留痕、精确交易所全名和反例，以及 N-PX 单层目录与穿越反例。此前51项为中间快照结果，不当作最终62项的独立重复证明。

## 版本与证据复用

最后安装插件 `0.3.0+codex.20260910170554`。既有完整性保护范围快照 `9858754cd5ed9607761c24a1d50c1730beb35c3bdb36939f2c0367a328785a13`，不是全工作区或强制只读证明。

| 当前实现 | SHA256 |
| --- | --- |
| sec.py | 892e25b037c47071ca1bb923f0e27386d53cc930a82935a299fdb0b654cb4a73 |
| sec_client.py | 00d363d662bcdceb8f40ed47caab99a249afbc4fe4a0595d1c59449c91baadd6 |
| collection.py | e4abeb95e5dd49445e44eeff38c988576f56f916fc60a9178f039af4424262b3 |
| security_metadata.py | 21a25effb2c17ec66159467dda346cc36c7d2b60ff55fce2bb94f8e8ab7b344c |

此前单股 Agent/Skill/CIO/Risk/Eval 未修改，仅继续证明当时单股研究能力；不伪装成当前源码锁。新数据分支用本次局部测试和新三股采集证明。原始失败目录 `stock-agent-live-three.xcXLr5`、`stock-agent-live-three-fixed.g2yJm4`、`stock-agent-live-three-ready.6rGOq8` 均保留于 `/private/tmp`，全部在模型启动前失败，不改记成功。

`/private/tmp/stock-agent-live-three-council.SEwwpy/smoke` 保留 NVDA 全名映射修复前失败。

## 最后一次三股宿主结果

```sh
bash scripts/run-product-smoke.sh --profile live-us-equity --portfolio /private/tmp/stock-agent-live-three.xcXLr5/portfolio.json /private/tmp/stock-agent-live-three-final.icwtKe/smoke
```

沿用既有 live Python、外置 SourceAccess、SEC 联系环境变量及 `/private/tmp/stock-agent-nasdaq-tls.dZ9JbD/cache`；未修改预算、代理或原生权限。

| 验证项 | 实际结果 |
| --- | --- |
| 三股行情、SEC、普通股身份及冻结 | PASS，snapshot `1bd62fdff908d7f56cfc4ad5148620d2710dc050ae45e35f62e40e6547c6370e` |
| 批次 prepare | PASS，三个子运行均 DISPATCH_REQUIRED |
| 真正启动 Council | FAIL，三个子运行均在构造 Prompt 时 START_CONTEXT_TOO_LARGE |
| 独立语义 Eval | NOT_RUN，缺少合法研究产物，不伪造评分 |
| 整体 Task 5.3 | 未完成，宿主返回5，批次 FAILED |
| OpenSpec strict validate / git diff --check | PASS |

批次 `live-batch-dc8da52b-5d93-4795-8104-b9e02bff4318`，manifest canonical hash `52c664a9e7804fb30b78202be5efd0e57a2a135bf5e1f38d01d0419007ef6559`。

- MSFT：`live-4a8e8ad5-ad43-4bb8-acc3-a40807641f89`
- AAPL：`live-06cc2245-7cbc-4314-832a-9b5848023661`
- NVDA：`live-90a4fca3-daab-469d-8aff-88915ecb90b5`

底层证据在最后产物目录的 `data/snapshot.json`、`batch/prepare-result.json`、`batch/runtime-result.json` 和 `batch/launch-logs/<run_id>/stderr.log`。未生成模型 JSONL、decision 或 report；模型启动前异常，不是模型推理失败。三个子运行 check-run 的 TRACE_TERMINAL_STATE_INVALID 是缺少终态的后果，不是第一原因。

定点检查 MSFT Analyst 派发包：351个允许 ID，JSON155948字节（尚未计入外层启动包装），超过131072字节上限。agent_input约40178字节，invocation约29608字节，task_prompt约29040字节，output_schema约55758字节；允许 ID 在多个字段中重复。

待处理建议：下一步仅对启动输入做无损去重（保留完整允许 ID 集合及等价 Schema 约束），不提升上限、不丢弃证据、不改独立性或 Risk。此处未修改启动包契约，未再次运行模型。

本记录不宣称 Task 5.3 完成，不归档、提交、推送。ISOLATION 继续 UNVERIFIED。
