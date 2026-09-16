# WOLF fresh-start 可比性定点修复验收记录

日期：2026-09-14
Change：`establish-common-stock-holding-analysis`
范围：仅核对普通股公司研究中的跨重组可比性、Evidence 引用和观察基线；不代表完整 Council 或版本晋升。

## 根因与修复

旧 WOLF 报告虽然提到 `fresh-start accounting`，仍把重组前后两个 91 天期间称为可比，并将 EPS 算术差额解释为经营恶化和现实反证。根因是确定性期间比较只说明了同指标、同单位、同披露和相同天数，没有显式区分“可做算术”与“会计基础、报告主体、每股分母和经济含义可比”；Company Analyst 与 Rubric 也没有把结构断点设为明确解释边界。

本轮完成：

- 确定性比较输出声明 `comparability_scope`、`accounting_basis_status`、`share_denominator_status`、`trend_interpretation_status` 和明确限制；算术能力不输出投资判断。
- 同一 Company Analyst、`company-research` Skill、派发指令和 Rubric 明确：跨 `fresh-start`、重组、前后继主体、重述或重大处置时，没有额外可比 Evidence 就只能分别呈现原值和限制，不能解释为趋势、改善、恶化或现实反证。
- 大幅百分比需要原值、绝对变化和基数/一次性限制；数值 Evidence 对应的观察基线必须保留实际数值、单位和期间。
- `evidence_refs` 继续严格 fail-closed，不截断、不模糊匹配、不自动纠错；Agent 输出前须逐项与 `allowed_evidence_ids` 做完整字符串核对。

## 聚焦确定性检查

实际命令：

```text
env TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_live_financials tests.test_common_stock_research_contracts tests.test_product_config tests.test_native_invocation_validation
openspec validate establish-common-stock-holding-analysis --strict
git diff --check -- <本轮相关文件>
```

结果：`101/101 PASS`；OpenSpec strict `PASS`；差异格式检查 `PASS`。

`financials.py` 的 `sec-comparison/1.2.0` 元数据由聚焦测试直接证明。真实研究继续使用冻结 Gate，不改写其历史 Evidence 或旧 `sec-comparison/1.1.0` 派生事实；新报告没有把这些旧派生差额用于趋势判断。

## 失败证据保留

运行 `/private/tmp/stock-agent-common-stock-wolf-freshstart-v3.3C5YJk/run` 中，模型已正确识别跨重组不可比，但一个 `evidence_refs` 在原 ID 中误插入字符。Evidence Closure 返回失败，未生成合法最终报告；被拒绝原件 SHA-256 为 `8fab38e8c0861e6420f46427dd68d78d3285151b5fab672ef10b2f26f31f8f3b`。该记录只证明严格拒绝生效，不作为成功报告证据。

## 当前真实研究

实际宿主入口：

```text
bash scripts/run-product-smoke.sh --stage common-stock-research --handoff <外置已确认Handoff> --gate <外置未绑定冻结Gate> --model gpt-5.6-terra /private/tmp/stock-agent-common-stock-wolf-freshstart-v4-20260914
```

运行目录：`/private/tmp/stock-agent-common-stock-wolf-freshstart-v4-20260914/run`
run ID：`host-common-stock-da2e3609-dc45-4245-ac9b-514441177019`

launcher 仍按完整冻结 Handoff 派发了三个普通股任务，结果 `3/3 PASS`、`parallel_overlap=true`。本轮只把 WOLF 报告及其 Eval 作为新增验收证据，不重新评价或替换 ALB、MRVL 的已接受报告；这一额外派发不被包装为新增能力证明。

WOLF 当前报告：

- JSON：`research/reports/US_COMMON_STOCK_WOLF/equity-research.json`，SHA-256 `1ee804570535e4e3f0c17f5d1a05d868d959a2c9ceeaf2cd3e83d300a9355802`
- 中文报告：`research/reports/US_COMMON_STOCK_WOLF/equity-research.md`，SHA-256 `cf110c0f78badf328c5b62b521987e9911847e5492e45771a8a26162e36eebc2`
- execution proof：canonical `74876c1bfb141bbda1a44889a9f375878b7094de5f57edd624c966772856b614`；文件 SHA-256 `9885cadb29777fd80762c9834b5ffef726917972456a8ba8c8bbb8396fefe36f`
- Gate：canonical `dea185fabcd8c1741e5426bb7ef8b28107b2222afca41e036e0c048facac273a`；文件 SHA-256 `08181494c0ea84a65bcbe27fbb6a6dccbd8b6f38626d620acde60654b786d2d4`
- MCP events SHA-256：`7f2be2d3845e182ba3c0418194865e1d33c34d716333948f4232a2dc426144c8`
- `source_integrity_unchanged=true`，阶段 `PASSED`。

报告明确说明重组后成为新的财务报告主体，禁止把重组前后收入、利润、现金流或每股数据描述为改善、恶化或可比趋势。现实反证改为同一重组后时点的现金缓冲和流动债务事实，对长期融资压力作窄范围限定；经营现金流观察基线保留 `-180800000 USD` 与 `2025-09-30–2026-06-28` 实际期间。全部结构化引用通过 Evidence Closure。

## 当前聚焦 Eval

实际命令：

```text
python3 scripts/council-dev.py common-stock-eval-prepare --report <当前WOLF JSON> --request <当前WOLF请求> --gate <当前Gate> --rubric evals/grading/common-stock-research-rubric-v1.json --mcp-events <当前MCP events> --output-dir <当前WOLF Eval目录> --eval-id eval-wolf-freshstart-v4
python3 scripts/council-dev.py launch-common-stock-eval --repo /Users/caihaoming/Documents/stock_agent --eval-dir <当前WOLF Eval目录> --model gpt-5.6-terra
```

Eval 目录：`research/evals/US_COMMON_STOCK_WOLF`
eval ID：`eval-wolf-freshstart-v4`
结果：`PASS`，Rubric `common-stock-research-semantic/1.7.0`，模型 `gpt-5.6-terra`。九个维度全部通过；`comparable_financial_analysis=3`，`reevaluation_conditions=3`。canonical result hash 为 `157631dff5e02fd2481a8c342fc219f182da18554e78ba7e0db050e69b074c7a`，结果文件 SHA-256 为 `eaa5bf3d466202720e802d9cd45a41d6abdf6280eac066fc146ce18f1afaa992`。

## 当前源码锁

| 文件 | SHA-256 |
|---|---|
| `product/mcp/live/financials.py` | `d841fee0ee5cd6a0adf18fcb2553704204bbb817cd157504769d7f1a0b2d4bd6` |
| `product/mcp/live/collection.py` | `6edf6f68d9f757bf2c6b8c9079510878d0238b18d34fad6833eb5c371692610c` |
| `product/runtime/common_stock_stage.py` | `4959ab46beb2439382b3c159ac5bb584fd554c5b436ec176473a618358a08129` |
| `product/.codex/agents/runtime_company_analyst.toml` | `b7ecd21655e2f7a0d7aa1119ce63f9d94391d677598595586419a77a9d96b949` |
| `product/skills/company-research/SKILL.md` | `57302d4433b7ed19f49564e4abbb31d198d5b24b6aaf70a06ac6f3f602ecfddb` |
| `evals/grading/common-stock-research-rubric-v1.json` | `7d77d54dc32264c9fdd3bb5905f239f795feda512c5a005a92876985cfcaa98f` |
| `product/runtime-profile.json` | `345290d8ba23f07ca953c35ef4114ab1e013b53457791f2ad1c41abce537b919` |
| `product/version-manifest.json` | `8fe2b447c09e8f1714ffd7e6b8a807f7c1ca3d05ed379ff122bc401dd8a60ffe` |

## 边界

本轮证明 WOLF 公司研究可作为后续 Agent 的结构化输入，且不会再把 fresh-start 跨期算术误作经营趋势。它不证明 ETF/期权研究、Skeptic/CIO/Risk、完整组合建议或 Promotion。Task 5.4 仍须用户明确批准；未经批准不归档、提交或推送。
