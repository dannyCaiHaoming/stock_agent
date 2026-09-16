# 公司研究首版深度：TODO 与收尾增量

日期：2026-09-13。Change：`establish-common-stock-holding-analysis`，对应第 7 组。用户授权先更新需求并继续实现，不代表最终完成批准。私人输入和原始研究包继续外置。

## 本次结果与范围

- 7.1：三层 TODO 已写入 `docs/product/common-stock-holding-analysis.md`，区分本次修正、公开资料后续深化、更多资料依赖。后两类不计入本 Change 完成门槛。
- 7.2：company-research/valuation 先更新为 2.3.0；7.4 收尾时 company-research 进一步更新为 2.4.0。实际期间、现金质量、现实反证、比率限制、现有关键事实解释和具体缺口进入方法。派发保留原期间并提供单位、来源和数据类型；既有 Rubric 最终更新到 1.3.0，不新增评分平台或硬编码投资判断。
- 7.3：中文呈现完整假设和理由、主张类型/关联、全部主张、来源实际期间/单位/发布时间/链接；重复主张只展示一次正文。JSON 不修改，未知不补数。复用已有 LOW_CONFIDENCE 状态映射与测试。
- 7.4：受影响确定性检查、真实 Terra 批次、三份聚焦 Eval 与独立增量复核均已补齐；详细证据见后文，本项完成。
- 5.4：最终人工完成批准未取得，不勾选、不归档、不提交、不推送。

## 实际检查

```text
python3 -m unittest tests.test_common_stock_research_contracts -q
python3 -m unittest tests.test_common_stock_research_contracts tests.test_valuation -q
openspec validate establish-common-stock-holding-analysis --strict
git diff --check -- product/council/research_output.py product/runtime/common_stock_stage.py product/skills/company-research/SKILL.md product/skills/valuation/SKILL.md product/version-manifest.json tests/test_common_stock_research_contracts.py docs/product/common-stock-holding-analysis.md openspec/changes/establish-common-stock-holding-analysis evals/grading/common-stock-research-rubric-v1.json
```

结果：第一次 52 tests / OK；补入相关估值模块后的检查为 58 tests / OK，零失败、零跳过。OpenSpec strict 有效。diff --check exit 0；该命令不检查未跟踪文件的完整内容，不把它冒充全仓审查。

新增四项确定性测试覆盖：假设正文/类型/所有主张不遗漏且不重复；部分期间与来源展示；未知期间和非法链接不补造；派发保留起止/单位/来源且 packet hash 绑定正确。已有 native finalizer 测试覆盖低置信度状态不升级及报告同源失败拒绝。它们不证明 LLM 已实际遵循新方法。

独立 Reviewer 指出重评/失效/观察项还需逐项展示已有内部引用。随后补齐该展示并新增第五项局部关联测试，执行 `python3 -m unittest tests.test_common_stock_research_contracts.CommonStockDispatchTests -q`，18 tests / OK。这是最后渲染修复的受影响测试结果，不将此前58项描述为最后快照下全部重跑。

Skill Creator 的 `quick_validate.py` 分别通过系统 Python 和桌面 bundled Python 尝试，均在导入时返回 `ModuleNotFoundError: yaml`，属于工具依赖问题，未运行该校验器主体，不记 PASS；未安装依赖。使用已有 Ruby YAML 解析器完成替代文件头检查，两项均 PASS：

```text
ruby -ryaml -rjson -e 'ARGV.each { |p| t = File.read(p); f = YAML.safe_load(t.split("---", 3)[1]); abort("invalid name") unless f["name"] == File.basename(File.dirname(p)); abort("invalid description") unless f["description"].is_a?(String); abort("invalid version") unless f.dig("metadata", "version") == "2.3.0"; puts JSON.generate({path:p,frontmatter:f,status:"PASS"}) }' product/skills/company-research/SKILL.md product/skills/valuation/SKILL.md
```

## 旧证据能证明什么

历史运行 `host-common-stock-24e1ccd6-c5d6-4da1-be6d-404273f84eeb` 的真实输入绑定、独立派发、模型调用与并行事实未由本次改写。它仍只证明当时版本，不能证明新 Skill/Prompt 已加载或新内容质量。

本轮只读核对发现一份历史重组样本原始报告把不足一年的流量期间称为财年并用于观察基线；底层资料已有真实起止日期。这是语义口径问题，不是简单引用悬空。旧 LOW_CONFIDENCE/coverage 差异也仍在原件中；当前代码修复不等于原件被修正。该中文原件有额外字符，与先前同源记录的文件 hash 不同，无法归因于具体修改者，不能继续复述三份中文文件均有效。

原件 SHA-256（只做标识，不披露持仓明细）：

| 产物 | SHA-256 |
|---|---|
| 原 Gate | bacc4d7e1f3b666783880d4ea55ec1085683561ea1ddb816040920eb309c152e |
| 原 coverage | 61cd45a4f1be5dba2864e9aae8d1487181b9f88003b904b9d6b4a9ca9a60fd5c |
| 发现口径问题的原 JSON | 68f263232ac0da48b00849e765da7597b3575b34a714aeb8c052a9194c76c49f |
| 本轮读到的对应 Markdown | a179d09b7dcf5f327c997b3d72e79584c519cbdc36fd16ed9d512e580d598b07 |

本次没有对原件运行新的收尾器或覆盖旧 Eval，没有将旧报告重渲染后包装成新研究，也没有修改历史版本锁。

## 当前实现标识

以下为文件字节 SHA-256，不是生产晋升锁，也不代表全仓源码快照：

| 文件 | SHA-256 |
|---|---|
| docs/product/common-stock-holding-analysis.md | 1bf81afd7ac0cf3289af8b36e19db2c0c6bde3fb66a4746dbd6da1607533241e |
| product/skills/company-research/SKILL.md | 117b2ecfac227006adfd6dd03f6f449ea32fbb32f779dfdcefcc7726c558ff6d |
| product/skills/valuation/SKILL.md | b725c6e9ee26f38257f9196e49f8696c80b473b46b39edf2684d4a4083fb29a5 |
| product/council/research_output.py | c3af07388e8acc128d09d42fbf3fd04a76f51ce2110d3d51dd2af8b247400b1d |
| product/runtime/common_stock_stage.py | eeb8a18e499cd101d4bca9705b4f5b817314873419fd4e935bf85e30e5a5c3c0 |
| evals/grading/common-stock-research-rubric-v1.json | a22d2c77398cd16499c4a9306db0f532c7a27dc1d9b7c1be30664e254a0e7d7d |
| product/version-manifest.json | 321021f7270d7bca0dcde2835835de8554b3283a90ba8ec87fa7e923784a0bad |
| tests/test_common_stock_research_contracts.py | 093a6891d662123767cb699bf7fe90e36c27f8b17d00723e1ec9eb5b5e5fe9d5 |

## 受授权的新版本真实研究与聚焦 Eval

用户明确批准后，只执行一次受影响的普通股研究批次和对应聚焦 Eval。旧 Gate 原件的 `run_id` 与新批次不匹配，第一次 launcher 在 prepare 阶段以 `COMMON_STOCK_STAGE_GATE_RUN_MISMATCH` 拒绝，模型未启动。随后从旧 Gate 派生一份仓库外的未绑定副本，仅移除旧 `run_id` 与旧 `bundle_hash`，由现有 prepare 逻辑为新运行重算绑定；`decision_cutoff`、Evidence、来源与时间均未改写，历史包保持只读。

实际研究命令：

```text
bash scripts/run-product-smoke.sh --stage common-stock-research --handoff <外置已确认Handoff> --gate <外置未绑定冻结Gate> --model gpt-5.6-terra /private/tmp/stock-agent-common-stock-depth-v24-output.9VNaJw
```

运行 ID 为 `host-common-stock-06318d6c-523c-4019-944f-6a6d8f3f8d38`，外置运行目录为 `/private/tmp/stock-agent-common-stock-depth-v24-output.9VNaJw/run`。结果为 `status=PASSED`、`completed=3/3`、`parallel_overlap=true`；阶段为 `PARTIAL_RESEARCH`，同时反映一份重组样本按资料限制合法返回 `LOW_CONFIDENCE`，以及完整输入中的 ETF、期权仍为 `CAPABILITY_GAP`，不是执行失败。未启动 Skeptic、CIO、Risk、Regression、Replay 或完整 Gate。

当前执行锁：Company Analyst `3.0.8` / `1158a35c657e4b597bdc4487b02e038c604b4417f565d5b560a3b238a531c96c`；company-research `2.4.0` / `922f5b41643a45212847febf371ea377fc3ddc460a0c65644bfc2e8fece10778`；valuation `2.3.0` / `b725c6e9ee26f38257f9196e49f8696c80b473b46b39edf2684d4a4083fb29a5`；Rubric `common-stock-research-semantic/1.3.0` / `48bee4c568d13774808c9625085392f6ecb8c97f612e5ccce1033cdac2e41476`。execution proof 的 canonical `proof_hash` 为 `ab6442b6feca55592a99f3a427c3b04d7da8d5b191a255fc3a9498f0d6effb9f`，文件 SHA-256 为 `13ea28425dcf6c0c9b8b8f39fb71d5972c52cf0ef112290211d35d2e535a238b`。

三份报告均生成同源 JSON 与中文 Markdown。JSON SHA-256 依次为 `f32bb5e5fd0b378fbf5c8179a31fece219964c3b0c2188f15f751f239f28a629`、`ff7e35dd48df32636488f0bb8ef520eecd4f629e8c840b0e3c790116224440da`、`f865d62c4361f773f5f3f9effda00c3cc88579fad4d846ade2154247fb52bd99`；Markdown SHA-256 依次为 `c3ef0a0e50a1e24ed4c971d2490d4af70801407a00c032d558607fe395f362bb`、`15837ec243aed1414f48cd66ec4e4d89a86cf7e19723451ae1cc0ac8fd5651e1`、`2413d1ccc7ffdef4a71436bb4c8158ebd1b12377ad5f959286105332d7fc8a8d`。

三份报告的摘要、关键事实解释、现金流边界与估值边界均符合本轮要求；一份报告使用确定性历史价格/EPS 视角并明确其不是完整 TTM、目标价或公允价值。但独立 Reviewer 进一步直接核对 Gate 后发现，重组样本把起始日相差一天的收入/EPS与净利润/经营现金流统一概括为 272 天，仍不满足逐事实期间要求。因此本批次与三份 Eval 只作为两份未受影响报告及缺陷发现证据，不能单独关闭 7.4。

三份 Eval 分别从真实报告、HoldingResearchRequest、冻结 Gate、MCP 事件与 Rubric 1.3.0 准备并通过；最低维度分数依次为 2、2、3，result hash 依次为 `100f677bc19ce9a2fd2237e55c7eea6b5c0aa2ccdae94af37f63e2501693b81b`、`df17fb0dc6408206c5c815e62c51b76ca1d33f5dcb5ed68947c79dd46f588dc5`、`fc7fbb772d35fcfac55a297079dd332c9b38216c7f4bfbbfc603220c116e0753`。Reviewer 证明第三份 PASS 漏检跨事实期间合并，故该结果不再用作该维度的有效关闭证据。证券名称和账户事实仅保留在外置运行包，不写入仓库证据索引。

## 期间口径定点修复与最小补证

独立 Reviewer `01a09a4b-de30-7bb2-9f7d-ffa66468694b` 的首次结论为 `CHANGE_REVIEW: FAIL`，阻断项为跨事实期间合并、仓库说明出现私人证券标识，以及 `PARTIAL_RESEARCH` 原因描述遗漏 ETF/期权 `CAPABILITY_GAP`。主线程没有扩大验收：证券标识已脱敏，阶段状态说明已同时列出低置信度和能力缺口；Agent/Skill 明确要求逐事实读取 `period_start/period_end`，日期即使只差一天也不得合并。Rubric 同步把跨事实合并不同期间列为本维度不可通过的实质错误。

修复锁为 Company Analyst `3.0.9`、company-research `2.5.0`、Rubric `common-stock-research-semantic/1.4.0`。由于既有宿主入口按完整 Handoff 派发且没有安全的单证券重跑参数，为避免伪造部分 Handoff 或新增临时产品入口，使用同一外置冻结 Gate 再执行一次完整三股研究；只对受影响的重组样本补做 Eval，另外两份不重复评分。

```text
bash scripts/run-product-smoke.sh --stage common-stock-research --handoff <外置已确认Handoff> --gate <外置未绑定冻结Gate> --model gpt-5.6-terra /private/tmp/stock-agent-common-stock-period-fix-output.XRBpno
python3 scripts/council-dev.py common-stock-eval-prepare --report <受影响报告> --request <对应请求> --gate <新运行Gate> --rubric evals/grading/common-stock-research-rubric-v1.json --mcp-events <新运行MCP事件> --output-dir <外置Eval目录> --eval-id eval-period-fix-v1
python3 scripts/council-dev.py launch-common-stock-eval --repo /Users/caihaoming/Documents/stock_agent --eval-dir <外置Eval目录> --model gpt-5.6-terra --timeout-seconds 900
```

新运行 ID 为 `host-common-stock-22233166-affa-4ba8-9011-701bc9b85401`，结果仍为 3/3 报告完成、并发重叠、`PARTIAL_RESEARCH`，没有启动完整 Council。受影响报告明确分别写出：收入/EPS 为 `2025-09-30–2026-06-28`，净亏损/经营现金流为 `2025-10-01–2026-06-28`；不再把它们合并为同一期间，也明确不是完整财年。该报告保持 `LOW_CONFIDENCE`，JSON SHA-256 为 `70b87960d9dada39df44dc46e5f4da1522c42a08c3c16788fec84da83671052a`，Markdown SHA-256 为 `0bb8e51debce8d9c915f7a9e9bd63581720309f7c49fa3ef2a3b8dbe840ec3e2`。

补充 Eval `eval-period-fix-v1` 使用 Terra 与 Rubric 1.4.0，结果 `PASS`，最低维度分数为 2；`comparable_financial_analysis` 为 3，直接确认各事实分开使用 89、91、270、271 日口径且没有把部分期间称作全年。canonical result hash 为 `3abff7eb11b156a708a29ca1277af86d79f1c14edb9a0c4c8cd6fd2c12632e86`，文件 SHA-256 为 `8e1ab9151605514d3b146fb9e61171ecb9d0fac59179d5c2b11ceaca037a2df8`。新 execution proof canonical hash 为 `a078aa5dbbc460b601798cd88ac1f48225ab8b24ff19542286c18524243d4033`，文件 SHA-256 为 `30a3ee024e5b5f1ea4f71291d4f8f1eb38b1f2bd242c6b89b86172dbf25d6e93`。

同一 Reviewer 再核对后指出，首轮定点报告虽区分收入与净亏损，但仍把经营现金流错误并入净亏损期间；Rubric 1.4.0 的 Eval 也漏检。该运行与 Eval 继续原样保留，但不作为关闭证据。最终规则升级为 Agent `3.0.10`、company-research `2.6.0`、Rubric `1.5.0`：一个 Claim、章节或观察项引用多个流量事实时，必须逐个按自己的 Evidence 日期核对，成组表述要求起止日完全相同；任一错配使期间维度低于通过线并导致 Eval FAIL。

最终补证运行目录为 `/private/tmp/stock-agent-common-stock-period-fix2-output.uUDrtR/run`，run ID `host-common-stock-224452dc-f0d3-4862-82c2-bd13fed35d92`。运行仍为 3/3、并发重叠和合法 `PARTIAL_RESEARCH`；受影响报告把单季收入/净亏损/EPS 的 `2025-12-29–2026-03-29` 与经营现金流的 `2025-09-30–2026-03-29` 分开，也把 10-K 净亏损的 `2025-10-01–2026-06-28` 与收入的 `2025-09-30–2026-06-28` 分开。报告 JSON SHA-256 为 `1ae20b9a9f3b1b3bad41dd08849df85d9d4af325f9f64bfb7a98db62a43c9b0b`，Markdown 为 `74879526f5dddcbc4885a85b2d569d1244ea873c6ebeb6cefd81f4a714b3dd66`。

第一次 Rubric 1.5.0 Eval 的语义评分内容为 PASS，但评分 Agent 抄错一个 Evidence ID，Evidence Closure 以 `COMMON_STOCK_EVAL_INPUT_INVALID` 正确拒绝；rejected result SHA-256 为 `e7a208c4cb5f909e9491c1f632f2d3e8a9d7aca2782c92d18df842ecb2fce221`，没有静默修复。随后只对相同锁定输入执行一次全新 Eval ID 的有界重试，`eval-period-fix-v2-retry` 返回 PASS；最低维度分数 2、期间维度 3，canonical result hash `42b641622328fe4eb1ea35b8eb606c9621c60997609171fb305ce6c52aef8105`，文件 SHA-256 `c8f5b53d5cd18d42216891e006837a303dc01912db4fa8b7667e700c4eb65b5d`。最终 execution proof canonical hash 为 `e9f2ce3556963eb341d32acfca7c81cb660e3bae78ab6cc5370332b6ae5a6443`，文件 SHA-256 `a67ea31c675c385288cccc0c795fbbac8eeb29dde3da9ecd80b3a61b707d790a`。

## 独立复核与真实剩余项

独立 Reviewer `01a09a28-5f94-7330-b61b-28bcb1cd1bc4`（dev-reviewer）只读检查对应规格、实现、测试和历史包。首次发现上述一项中文逐项关联缺口，已实施修复，交同一 Reviewer 定点确认；不把本轮复核包装为全仓审计。Reviewer 精确实际模型未知，未猜测。其未复跑测试，主线程测试结果与独立静态复核分别记录。多数实现文件此前已未跟踪，缺少本轮开始前完整源码快照，不能把整个文件认作本轮新增。

此前渲染 P2 已关闭。期间口径 Reviewer 的首次和二次 FAIL 均如实保留；最终补证后，同一 Reviewer 直接核对 Gate、报告、Eval、文档与证据 hash，返回 `CHANGE_REVIEW: PASS`。它确认逐事实期间、私人证券标识脱敏和 `PARTIAL_RESEARCH` 完整说明三项原阻断均已关闭，Task 7.4 可以完成。5.4 继续等待最终人工完成批准。本轮证据只证明普通股公司研究切片，不是完整组合决策或 Promotion PASS。

Task 7.4 已按最终独立复核完成。当前唯一剩余项是原 Task 5.4：向用户提交示例、已证明范围及 ETF/期权边界，并取得明确人工完成批准。未经该批准不归档、提交或推送。

## 第 8 组：金额准确性、最新事实与解释力增量

本节只记录 Tasks 8.1–8.6 的增量证据，不改写前述历史运行或 PASS。用户授权继续完成当前需求后，先执行确定性聚焦检查，再通过既有宿主入口运行当前 Company Analyst；没有启动 Skeptic、CIO、Risk、完整 Council、Regression、Replay 或 Promotion Gate。

### 实现与聚焦检查

- 新增无业务判断的 canonical 金额数量级换算模块，并把 `monetary_scale` 接入 Company Analyst 实际使用的 `fixture_runtime.calculate`。换算保留币种、来源数量级和 `PRE_TAX`/`AFTER_TAX`/`UNSPECIFIED`，不按证券代码修补结论。
- Company Analyst `3.0.14` 的冻结包包含 `evidence_period_index` 与相关 `evidence_conflicts`；指令要求先核对期间/主体/单位/会计基础，旧基线说明用途，不能消解的冲突保留。`counter_claim_refs` 只允许已有 Claim ID，挑战假设时在文字中说明，不能污染引用字段。
- `company-research 2.7.0`、`valuation 2.4.0` 和 Rubric `common-stock-research-semantic/1.6.0` 明确经营驱动、现实反证、条件情景、金额和最新适用事实边界。Eval job `1.1.0` 同时读取同源 JSON 与 Markdown，覆盖状态只绑定同一 run 内、hash 一致的结果。

实际聚焦命令等价于：

```text
python3 -m py_compile product/runtime/monetary.py product/deterministic/valuation.py product/runtime/fixture_mcp.py product/runtime/common_stock_stage.py product/runtime/common_stock_eval.py
python3 -m unittest tests.test_valuation tests.test_common_stock_research_contracts tests.test_product_config tests.test_native_invocation_validation tests.test_native_evidence_gate.GateScopedFixtureToolTests.test_calculation_manifest_matches_bound_callable_parameters tests.test_native_evidence_gate.GateScopedFixtureToolTests.test_monetary_scale_calculation_extracts_disclosed_amount_and_tax_basis tests.test_native_evidence_gate.GateScopedFixtureToolTests.test_monetary_scale_rejects_missing_target_or_wrong_arity tests.test_native_evidence_gate.GateScopedFixtureToolTests.test_mcp_rejects_undeclared_parameter_and_records_redacted_error
```

最终结果为 94 tests / OK。原始输出保存于 `/private/tmp/stock-agent-common-stock-depth-v8-final-evidence/focused-tests.log`，SHA-256 为 `50274272aa94dc2ff278083e97d4db2041b0d2e94c992e0a451e66b73c89b1bc`。覆盖 billion、million、亿、万、负数、等值和十倍误写拒绝，MCP 参数契约、冲突传递、Agent/Skill 版本绑定、JSON/Markdown 同源及 Eval 输入。曾因测试类名写错产生 unittest loader error，改用仓库实际类名后 4/4 通过；该错误不是产品断言失败。

### 真实运行、失败保留与成功证据

首次接入工具后，MCP 子进程从 `product/` 启动时因 `deterministic.__init__` 的绝对 `product` 导入形成循环，报告合法降级为资料不足。根因通过实际 MCP 启动命令复现；金额换算随后移入 package-neutral `runtime/monetary.py`，`python3 -m runtime.fixture_mcp --help` 在产品目录成功。另两次当前版本批次分别因模型把 assumption ID 放入 `counter_claim_refs`、抄错一个 Evidence ID 而 fail closed；被拒绝原件和完整 MCP/标准错误均保留，没有自动截断或静默修正。

最终成功命令：

```text
bash scripts/run-product-smoke.sh --stage common-stock-research --handoff <外置已确认Handoff> --gate <外置冻结Gate> --model gpt-5.6-terra /private/tmp/stock-agent-common-stock-depth-v8-tool-run-20260914-f
```

运行 ID 为 `host-common-stock-a5ab7573-0e61-434e-bdc1-9886ee53717f`，结果为 3/3 普通股报告完成、`parallel_overlap=true`、合法 `PARTIAL_RESEARCH`；ETF 与期权继续保留 `CAPABILITY_GAP`，没有完整组合决策。执行证明 canonical hash 为 `e1109837e9400af4cf8b93f53412373579430b7a44dc062cb0bef7ff2ad2e53d`，文件 SHA-256 为 `68be4f48157304ee00b741072aff8d9cdbbd2f914c3149cb09943baf65cc3dbd`；Gate、MCP 事件和最终 coverage 文件 SHA-256 分别为 `88921a87df10dc332df4e4b5a068260eefcbcc80dd202665c98a6ca22c6076bc`、`13974c63a792781d800745259545c74d25d32f4a1236a7faaa270cb464ee9856`、`6619c7b27ac3cf2e8dab9f09cbb99b11ff9686780addecbf2f103e4034267c8e`。

MCP 事件明确记录三次 `operation=monetary_scale`、`target_scale=亿` 及对应 Evidence IDs。受影响报告把 `$1.8 billion` 表示为 `18 亿美元税前出售收益`，同时把其他实际采用的 billion/million 金额按等值中文数量级呈现并引用真实 calculation ID。另一报告保留不能消解的文本冲突；第三份报告以同长度近期收入和每股亏损作为现实反证，并明确重组前后不可直接串联。三份 JSON/Markdown 均由同一结构化报告落盘并通过引用闭包。

### 绑定聚焦 Eval

三份 Eval 均由同一 run 内的真实 JSON、中文 Markdown、请求、Gate、MCP 事件和 Rubric 1.6.0 准备，并通过 `launch-common-stock-eval --model gpt-5.6-terra` 执行；结果直接回写 `ResearchCoverage`：

- sample A：`FAIL`。金额、税前口径、经营解释、反证、估值等维度通过，但遗漏包内更新的可比季度收入，`comparable_financial_analysis=1`。result hash `748e1ed55e1976e712a7c184e99ae9bbaacaf78722befbf6b930de5bb5c66eaf`。
- sample B：`FAIL`。期间、经营、现金流、估值与条件链通过，但没有已发生的公司特异性现实反证，`counterevidence_quality=1`。result hash `455564f16f88645eb4c3edba5813e80528f01740c4d6076725c7cef9990e134b`。
- sample C：`PASS`，九个维度全部通过，最低分 2；最新事实、期间可比性、现实反证、冲突限制和条件情景均由底层 Evidence 支持。result hash `36705072e3ea14d4bfc78046057a1a8c1fbeb198d1262b9bb88a2c3da267246e`。

两个 FAIL 是报告级真实质量结果，不以平均分抵消，也不改 Rubric。任务证据按 Design 14.2 分项使用：金额准确性由确定性正负测试、实际 MCP 事件和 sample A 的通过维度证明；最新事实与现实反证由 sample C 的全维度 PASS 证明；sample A/B 的剩余缺口作为样本差异保留，不宣称每份报告均达到全部质量维度。是否足以关闭第 8 组由后续独立 Reviewer 按现有 Specs/Tasks 判断。

### 3.0.15 最新事实缺口关闭

独立 Reviewer 指出上轮 sample A 实际使用旧年度收入时遗漏 Gate 内较新的适用季度收入，因此 8.2 与“两份实质报告”标准仍缺证据。修复没有放宽 Evidence Closure 或修改 Rubric，而是在 Company Analyst `3.0.15` 的实际指令中增加逐指标自检：报告采用某指标前必须查看 `evidence_period_index`；存在主体、定义、单位、期间性质和会计基础均适用的较新事实时必须纳入，否则明确给出不可比或不适用原因，不能只写旧年度基线。

只补一次受影响的宿主批次：

```text
bash scripts/run-product-smoke.sh --stage common-stock-research --handoff <外置已确认Handoff> --gate <外置冻结Gate> --model gpt-5.6-terra /private/tmp/stock-agent-common-stock-depth-v8-recency-run-20260914-g
```

运行 ID 为 `host-common-stock-3777b460-fa2f-48fc-a225-6c80764a5bf5`。结果为 3/3 报告完成、`parallel_overlap=true`、合法 `PARTIAL_RESEARCH`；ETF 和期权继续为 `CAPABILITY_GAP`，未启动 Skeptic、CIO、Risk 或完整组合决策。执行证明 canonical hash 为 `8b1c4d327701a93b593b948bd1ddb20c5b9e4f6f1a4c9ed1509122645681bb30`，文件 SHA-256 为 `bb8f7dd1a4bde5a0915c506a054875b0c51b62449a30d24fc700b32fdd5a2ec6`；进程、Gate、MCP 事件和最终 coverage 的 SHA-256 分别为 `f1f1f0cb8d04ad3a5697db3e733c6b035da3974a1d2ad888ac781a79abf65402`、`b338ffa92151836519d707c2550220068e1e193f99e208518582cd59e9a9867b`、`55343db93c382979df432731c2ad042db66418389010f92d71dd8344b0b4c7cf`、`a6572bb96ec0a8bde5c04e5bdbf6c7ff52f7da205a015d7e0ec54e55c9cb521e`。

受影响 sample A 报告不再只用旧年度基线：它分别比较两个起止日完全相同的上半年累计期间，纳入收入、净利润和经营现金流，并把二季度单季 EPS 单独表述；2025 全年亏损仅作为挑战近期修复可跨周期延续的现实反证。JSON/Markdown SHA-256 分别为 `2e20213da084f09413d4425a9e6f6e35b7e8648cdf13a8c62f07024bc35c17bb`、`21919f008f01578a38fa4fcd3a8739b825b5d81181cdc2bdae40a9c91529097f`。

该报告使用 `gpt-5.6-terra` 执行显式聚焦 Eval `eval-recency-current-lock-v1`，九个维度均为 3，`status=PASS`；result hash 为 `3efae1022acf28aad119216eba1a42c2ab6ac19c9bb5c0b4baf81ec1ff75b4db`，结果文件 SHA-256 为 `9f2d9719befda84ad85756a48b4489b506204ca009402ff656dfc8167f8d6708`，并已绑定同一 run 的 coverage。它与上轮未受本次指令修复影响、已全维度 PASS 的 sample C 共同满足“两份实质完整报告”标准；金额工具的实际 MCP 证明亦继续复用。上轮 sample A/B 的失败结果保留，不改写为 PASS。

### 3.0.17 本轮输出逐份验收

用户明确要求：验收必须评价本轮实际生成的每份 Agent 输出，不能以同一证券的历史 PASS 替代。主线程因此保留 `3.0.15` 当前批次的 ALB 报告与已通过 Eval，补做该批次 MRVL 的真实 Eval，并只重跑有缺陷的 WOLF；未重复运行 ALB/MRVL 研究，也未启动完整 Council、Skeptic、CIO、Risk、Regression 或 Gate。

MRVL 使用原运行 `host-common-stock-3777b460-fa2f-48fc-a225-6c80764a5bf5` 的实际报告、请求、Gate、MCP 事件和 Rubric 1.6.0，执行 `eval-current-mrvl-3.0.15`。结果为 `PASS`，九个维度全部 3 分；canonical result hash 为 `4ffd2b7a73813461c16d71d767e79be8798199707416c4094e5710945d3e3d47`，结果文件 SHA-256 为 `de8dd21633ae5dbd15e396f53def48390a26c1d2c3b28fc3c0d5d6ffb19a13a5`。报告与 Markdown 文件 SHA-256 分别为 `184b677d1c8e87f18e5a31fa112e6d1dc2ce83cbc7ef77747d04ef6b0b6681b2`、`d4a001dd643b7a28ac15377c74316e9719e5b59b19f8baea7d28d732038f3236`。

WOLF 的确定性修复在同源渲染前增加窄范围事实期间血缘校验：FACT Claim 引用多个 duration Evidence 且起止日不同时，文字必须显式保留每个实际日期，否则 fail closed；该检查不判断经营重要性或投资结论。Company Analyst/Skill 同时明确，反证必须挑战本报告实际提出的 Claim/假设，不能虚构极端判断后再反驳。第一次聚焦重跑 `host-common-stock-ca28090a-5324-4736-bdbc-8ea99eba4706` 关闭了这两项，但 Eval `eval-current-wolf-3.0.16` 发现 Agent 指令仍将 10-K 部分期间默认称为“历史财年 P/E”，因此整体 FAIL；原报告和失败 Eval 均保留，未修改 Rubric。

根因是 Company Analyst 估值示例与既有“10-K/FY 不证明全年”规则冲突。Agent `3.0.17` 明确：只有实际起止日证明接近完整财年时才可称历史财年 P/E；重组后部分期间只能按真实日期描述为非年化实际期间分母，负 EPS 时说明 P/E 不适用。只重跑 WOLF 的新运行 `host-common-stock-01f30c38-225d-4750-b813-659def3acdc3` 保留完整原组合 hash，但通过 `focus_security_id=US:COMMON_STOCK:WOLF` 只派发一个 Company Analyst 任务。运行结果 `1/1 PASS`、报告状态 `LOW_CONFIDENCE`；JSON、Markdown 和 execution proof 文件 SHA-256 分别为 `121c309f18ad021d94ccfc0b38ef1a3365f6e9c794a2bfdb5b38b1b2fb57c8e9`、`5415795d8f1b045a8f0fd3b75397e5b7a3374755beeef3cf26f795730f0d19d9`、`2c0360a6097b5e40e6016be525307d1e76cb2ee1c8f72c2dfa37f2eba6ee551d`。

新 WOLF 报告分别写出收入/经营现金流 `2025-09-30–2026-06-28` 与净亏损 `2025-10-01–2026-06-28`，并以两个真实可比 91 天期间的收入下降和 EPS 变化挑战“经营自然恢复”假设；部分期间估值明确不称年度、财年、全年或 TTM P/E。Eval `eval-current-wolf-3.0.17` 返回 `PASS`：除受资料限制的估值维度为 2 分外，其余八维均为 3 分；canonical result hash 为 `e3b807cd98121cc7f5cc3fecd98b9a48d7c0ab670f96243dac342c437240abb7`，结果文件 SHA-256 为 `7b1f8d886f943b28e22f28a3cfb6b09894a61a5d72db0b4861ebcae7a7956da4`。

当前接受集合为本轮 ALB、MRVL 与修正后 WOLF 三份实际输出，三者均有自身 Eval PASS，不引用历史同证券报告替代。最终受影响确定性检查为 100 tests / OK，日志 `/private/tmp/stock-agent-common-stock-depth-v8-final-evidence/focused-tests-3.0.17-final.log`，SHA-256 `fe47d03eab441945311c4f9ad84d096f668602527e4d0a8aecead8ce64601081`；OpenSpec strict 同样 PASS。该集合仍只证明普通股公司研究输出可供下游，不代表完整组合决策或 Promotion PASS。

独立 Reviewer `01a0a00c-0cae-72d3-9650-b5fe02392586` 首次复核确认报告、Eval、日期血缘、反证和 focus 入口均符合要求，但发现候选 manifest 只保留了完整 Council 的通用 Runtime Eval Rubric 锁，没有显式声明普通股聚焦 Eval 实际使用的 Rubric 1.6.0，因此 8.6 暂未通过。修复没有覆盖通用 `runtime_eval_rubric`，以免破坏历史 Replay；而是在 `assurance` 中独立增加 `common-stock-research-rubric=common-stock-research-semantic/1.6.0` 及实际文件 SHA-256 `e20c3a0875d203dd8ad67b74c592ebe5e8c15094fa43d85686335251f8b804a9`，并由聚焦配置测试验证 Eval 资源与声明一致。没有重新运行任何研究或 Eval 模型。

同一 Reviewer 随后直接读取修正后的 manifest、实际 Rubric、契约测试和已有底层运行/Eval 产物，最终返回 `CHANGE_REVIEW: PASS`，确认 Tasks 8.2、8.3、8.6 均可勾选且无阻断项。通用 `assurance_hashes.runtime_eval_rubric` 仍保持原值，普通股聚焦 Rubric 没有冒充完整 Council Eval 资源。该复核只证明本轮 ALB、MRVL、最终 WOLF 三份当前普通股报告及各自 Eval 可供下游；Task 5.4 仍等待用户人工完成批准。
