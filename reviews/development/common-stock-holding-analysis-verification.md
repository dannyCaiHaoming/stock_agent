# 普通股持仓研究限定验收记录

日期：2026-09-12。对应 Change `establish-common-stock-holding-analysis` Task 5.1–5.2。本记录只证明普通股持仓研究切片，不代表完整 Portfolio Council、ETF/期权研究或候选版本晋升。

## 结论

- 受影响确定性测试：`129/129 PASS`。
- OpenSpec strict validate：`PASS`。
- 真实两股并行研究：`PASS`；AAPL 与 MSFT 使用两个独立 `runtime_company_analyst` 子会话，执行区间实际重叠。
- 历史 AAPL/MSFT 的两份 JSON 均通过 Schema、Evidence Closure、内部引用和计算产物闭合校验；后续重验发现历史 AAPL Markdown 与合法 JSON 不同源，原文件保留且不再作为报告对一致性证据。当前确认持仓批次的新三份 JSON/Markdown 报告对均通过同源重验。
- 聚焦 Eval：AAPL、MSFT 的 `eval/result.json` 均为 `PASS`；评分模型均为 `gpt-5.6-terra`。

## 2026-09-13 确认持仓增量验收

本节对应 Tasks 3.6、3.7、4.4、6.1–6.5，只记录脱敏结果。用户确认的 `PortfolioHandoff v3`、来源缓存、报告和 Eval 产物均保存在仓库外；仓库不记录证券明细、成本、盈亏、现金或账户信息。

### 真实输入链路与定点修复

实际入口：

```text
bash scripts/run-product-smoke.sh --stage common-stock-research \
  --handoff <仓库外已确认 PortfolioHandoff v3> \
  --model gpt-5.6-terra \
  /private/tmp/stock-agent-common-stock-current-handoff-20260913-c
```

第一次资料准备在首只普通股的 SEC/Yahoo 身份交叉核验处以 `SEC_YAHOO_EXCHANGE_CONFLICT` 停止。原始 SEC 10-K 使用法定交易所全称，Yahoo 使用交易所代码；修复只增加 `New York Stock Exchange → XNYS` 的精确别名，未知或不一致名称继续 fail closed。受影响聚焦测试结果为 `109 PASS / 1 SKIP`。随后同一 Handoff 通过现有宿主入口重新执行，未手工准备 Gate，也未替换或遗漏证券。

运行标识：`host-common-stock-24e1ccd6-c5d6-4da1-be6d-404273f84eeb`。资料快照内部 hash 为 `1568063daf8f28fffea23c0941b8dc880c3bd2b5c7fffec20e2687cfb30dfa2e`；Gate 文件 SHA-256 为 `bacc4d7e1f3b666783880d4ea55ec1085683561ea1ddb816040920eb309c152e`。研究模型和父运行模型均实际记录为 `gpt-5.6-terra`，但两者在契约中保持独立字段。

完整 Handoff 中有三只普通股、一只 ETF 和一份上市期权。结果为：

- 三只普通股均由独立 `runtime_company_analyst/3.0.7` 子会话完成，三个执行区间重叠，`parallel_overlap=true`；execution proof hash 为 `5d247a41fe2adfdd0efed7f7d285e47bd0bead1252f966e1827063819677e751`。
- ETF 与期权均保留在 `ResearchCoverage`，状态为 `CAPABILITY_GAP / NOT_RESEARCHED / NOT_STARTED`，没有被 Company Analyst 越权研究。
- 阶段终态为 `PARTIAL_RESEARCH`，未启动 Skeptic、CIO、Risk，也未生成完整组合决策。
- 三份 `equity-research.json` 与中文 `equity-research.md` 均重新通过同源渲染、Evidence Closure、内部引用和结构校验。
- 三份真实聚焦 Eval 均由 `gpt-5.6-terra` 执行并返回 `PASS`；九个维度全部不低于 2。实际 Eval 的路径、结果 hash 和被评价报告 hash 已回写到对应 coverage 项。

独立 Reviewer 随后发现，捕获运行的 coverage 虽正确关联报告与 Eval，却将一份 `LOW_CONFIDENCE` 报告错误归集为 `VALID_RESEARCH`。原始 coverage hash `c85b461b55e6b30b0e39a32be03a5e2b76f2c58d0fd5f2ff608e04b7ae419c12` 继续保留为缺陷证据，不能用来证明研究充分程度状态正确。根因是 stage finalizer 对全部完成报告写死 `VALID_RESEARCH`；当前实现已改为从报告的 `COMPLETE / LOW_CONFIDENCE / INSUFFICIENT_EVIDENCE / TIMEOUT` 映射对应状态，并由聚焦正向测试证明 `LOW_CONFIDENCE` 不再被提升。该修复不改变报告、Eval 或投资研究内容，因此未重跑 LLM。

本批关键版本绑定：Company Analyst 配置 hash `9201b6e47b853169330bb32e77555cc08786dd72ec55c326b8641286c12273e5`；`evidence-grounding/2.1.0`、`company-research/2.2.0`、`valuation/2.2.0`、`catalyst-analysis/1.2.0` 的 hash 分别为 `6a96be50b82c73da7383a94708275a9bb14b369d828ff4f0277a21df41443c63`、`2bd57a8fe5bd6c1abafeb76f41d3ea41c62197d8618a3382772d23b44017f293`、`7087023fca1ead433490fbebd3fb7e5cbd8f24aad91d344e33f004828d4aa8be`、`e2fdc5ca5191a6a3b42cc3c66633467ac67c43b73143e25df4e1a6d2a5b34781`。

### 历史 AAPL 产物诊断

当前同源校验器重读历史 AAPL 包时确定性返回 `RESEARCH_OUTPUT_MARKDOWN_MISMATCH`。合法 JSON 及其语义 Eval 仍保留原结论；错误只在旧 Markdown 的引用渲染，不能再用该 Markdown 证明报告对一致。当前可确认的 JSON 与 Markdown SHA-256 分别为 `5ad12a3a43c0f6bd44d91eec19b68a76e66fc2ce797c41169bad52c9f0b6a8a6` 和 `922a88ad857fb08031bc1e06a110671ecf548954f484b0aa1bd3b6224cb2e893`；由于没有修改前 Markdown 的完整 hash，本记录不能证明该历史文件从生成后从未被修改，只能确认本次修复没有改写它、没有静默截断引用，也没有为此重跑 LLM。当前版本在每份报告落盘后立即重读 JSON 与 Markdown，并以同一 JSON 重新渲染比对，因此本次三份新报告均关闭该缺口。

### Reviewer 阻断修复后的聚焦检查

```text
python3 -m unittest \
  tests.test_common_stock_research_contracts.CommonStockNativeStageTests.test_hook_allows_distinct_tasks_denies_duplicate_and_finalizes_bound_reports \
  tests.test_common_stock_research_contracts.CommonStockFocusedEvalTests \
  tests.test_live_security_metadata
```

结果：`20/20 PASS`。其中 finalizer 测试实际生成 `LOW_CONFIDENCE` 报告并确认 coverage 保留该状态；交易所别名测试继续拒绝扩展、未知或冲突名称。修复后的 `common_stock_stage.py` SHA-256 为 `3bebfa3a5a37ed553bad2ce35bbf61af150d3bc4e8a9cdaff4bd28178ae4ecee`。

## 实际执行链

### 资料冻结与研究

外置输入为 AAPL、MSFT 合成持仓，不含用户真实持仓。现有只读适配器的冻结快照 hash 为 `c2ee8e42cab9020bb7e37e489c1c9c5d48cbe9130da96fdb1eca242dbd40fb53`，共同 cutoff 为 `2026-09-12T13:52:48.298843Z`。

运行使用现有入口：

```text
python3 scripts/council-dev.py prepare-common-stock-data --handoff /private/tmp/stock-agent-common-stock-acceptance-input/handoff.json --portfolio /private/tmp/stock-agent-common-stock-acceptance-input/collected-v5/portfolio.json --snapshot /private/tmp/stock-agent-common-stock-acceptance-input/collected-v5/snapshot.json --calendar /private/tmp/stock-agent-common-stock-acceptance-input/collected-v5/calendar.json --output-dir /private/tmp/stock-agent-common-stock-acceptance-input/research-data-v12 --run-id common-stock-C4AC132C-EC4B-40DC-8D0D-C49B73C84CAD
python3 scripts/council-dev.py prepare-common-stock-research --handoff /private/tmp/stock-agent-common-stock-acceptance-input/handoff.json --gate /private/tmp/stock-agent-common-stock-acceptance-input/research-data-v12/gate.json --data-preparation /private/tmp/stock-agent-common-stock-acceptance-input/research-data-v12/data-preparation.json --run-dir /private/tmp/stock-agent-common-stock-acceptance-run-v12 --run-id common-stock-C4AC132C-EC4B-40DC-8D0D-C49B73C84CAD --model gpt-5.6-terra --question 分析已确认的普通股持仓。 --max-concurrency 3
python3 scripts/council-dev.py launch-common-stock-research --run-dir /private/tmp/stock-agent-common-stock-acceptance-run-v12 --timeout-seconds 1800
```

运行标识：`common-stock-C4AC132C-EC4B-40DC-8D0D-C49B73C84CAD`。Company Analyst 版本 `3.0.6`，配置 hash `c03716c992c2a642e4bd96c54473476ce707c8a2f1e1ec3454a8aeaa09514768`。四项 Skill 及 hash：

- `evidence-grounding/2.0.0`：`7b1581a5b46374e86990b4598949a72f428713726b77f078970c8c8a6662abee`
- `company-research/2.1.0`：`00b9cc8b8dd98159df28a13571ca8808a16349fd11bcda985b861aee1a31ef50`
- `valuation/2.1.0`：`9ea9ce47cd229abc01a49c623ec3fee3879b2636bf2637bfa6a63cad8c9f9ea6`
- `catalyst-analysis/1.1.0`：`26d303160788db3042cbfc361c4ed3ba19b48ed64e29f0c05efae02b781a04ca`

实际子会话区间：

- AAPL：`2026-09-12T14:00:44.910997Z` 至 `2026-09-12T14:03:37.074326Z`
- MSFT：`2026-09-12T14:00:47.172048Z` 至 `2026-09-12T14:03:10.634102Z`

`parallel_overlap=true`，execution proof hash 为 `70358cef3dcc85d4fc9543c5229b3295fc9fe8755bc5b9ae9e6ae5b61bc51598`。运行只到研究报告集，没有启动 Skeptic、CIO、Risk 或生成完整组合决策。

### 聚焦 Eval

每份 Eval 输入均直接绑定真实报告、HoldingResearchRequest、冻结 Gate、Rubric 和本次 MCP 计算事件：

```text
python3 scripts/council-dev.py common-stock-eval-prepare --report <equity-research.json> --request <holding-request.json> --gate /private/tmp/stock-agent-common-stock-acceptance-run-v12/evidence/gate.json --rubric evals/grading/common-stock-research-rubric-v1.json --mcp-events /private/tmp/stock-agent-common-stock-acceptance-run-v12/events/mcp/events.jsonl --output-dir <eval-dir> --eval-id <eval-id>
python3 scripts/council-dev.py launch-common-stock-eval --eval-dir <eval-dir> --model gpt-5.6-terra --timeout-seconds 900
```

- AAPL：`eval-common-stock-aapl-v12-v2`，结果 hash `9a1d332aa910219df8f8415e289aceb8028fec65c35e5bd7160bfb9c6fb87b31`，九维分数均不低于 2。
- MSFT：`eval-common-stock-msft-v12-v2`，结果 hash `1263ab0e6a7cc0771143f97f2348374fb7fbc830851fae086c00b933b60ae616`，九维分数均不低于 2，launcher 返回 `PASSED`。

AAPL 的实际 `dev_eval` 输出已由 Hook 保存并判定 `PASS`，但当次 launcher 在把 JSON 按键排序后，旧收尾器错误要求 dimensions 保持插入顺序，因此 `process-result.json` 原样保留 `COMMON_STOCK_EVAL_DIMENSIONS_INVALID`。当前实现已改为严格比较字段集合而非无语义的 JSON 键顺序，现有 AAPL `eval/result.json` 在当前校验器下重新验证为 `PASS`。该历史失败记录未覆盖、未改写，也未再次调用 AAPL 模型。

两次 Eval 的 Agent 配置 hash 均为 `3b38cef3716234827c074dd0e2ef4196b301beb70ddce2484c304aa289a4b1fe`，`runtime-eval-grading` Skill hash 均为 `f3ae47051732109a6417d75da2ea5b1eab91011332b696034735d8e34fbc5f0c`。

## 限定检查

```text
env TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_common_stock_research_contracts tests.test_valuation tests.test_native_run_package tests.test_native_invocation_validation tests.test_native_output_handoff tests.test_live_financials tests.test_product_config tests.test_nested_codex_launcher
```

结果：`Ran 129 tests`，`OK`。测试中输出的 `FAILED_VALIDATION` JSON 来自预期负向案例，不是测试失败。

```text
openspec validate establish-common-stock-holding-analysis --strict --json
```

结果：`1 passed / 0 failed`。

## 产物与完整 hash

- 机器可读索引：[common-stock-holding-analysis-evidence.json](common-stock-holding-analysis-evidence.json)
- 外置运行目录：`/private/tmp/stock-agent-common-stock-acceptance-run-v12`
- 外置资料目录：`/private/tmp/stock-agent-common-stock-acceptance-input/research-data-v12`
- 仓库只保存合成样例、实现、规格及 hash 索引；未复制真实用户持仓、Cookie、凭据或完整来源缓存。

## 已证明范围与待办边界

已证明：确认持仓到普通股研究请求、系统资料准备/PIT、两股独立并行 Company Analyst、四项专业 Skills、确定性计算、结构化及中文报告、聚焦质量 Eval。

未证明且不属于本 Change：ETF Research、Options Research、完整 Skeptic/CIO/Risk 决策闭环、机会搜索、真实下单、完整 Regression/Replay/Calibration/Ablation/Promotion。Task 5.3 仍需独立 Reviewer；Task 5.4 必须等待用户明确人工完成批准。
