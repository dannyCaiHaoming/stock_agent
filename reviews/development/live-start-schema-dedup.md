# 三股启动输入无损去重

## 批准与边界

2026-09-11 用户针对“仅做输入包无损去重，保留全部 Evidence、Schema 与安全校验、不扩大框架”的建议明确回复“批准”。当前 Change 继续为 `us-equity-live-advisory-slice`，不代表最终完成批准。

## 实现

仅修改 `product/runtime/invocation.py`：对超限的 live v2 启动包，将展示 Schema 中完全相同的 Evidence 枚举共享为一个 `$defs` 定义，以本地 `$ref` 引用。程序先展开比较，必须与原 Schema 完全相等；名称冲突拒绝。包装记录 `start-context-schema-refs/1.0.0` 与原 Schema canonical hash，既有 context hash 绑定实际输出。

权威 Schema 文件、完整 Agent 输入、manifest、Prompt、允许 ID 集合和131072字节上限均未改变；fixture、旧 v1 及未超限包不变；压缩后仍超限继续失败。未引入新依赖、Agent、Skill、MCP、模型调用、代理或沙箱。

## 局部验证

```sh
env TMPDIR=/private/tmp/stock-agent-start-dedup.oMLdaM PYTHONDONTWRITEBYTECODE=1 /private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest tests.test_start_context_dedup tests.test_specialist_start_context tests.test_native_invocation_validation tests.test_specialist_dispatch -q
openspec validate us-equity-live-advisory-slice --strict
git diff --check
```

最终40项测试通过，退出码0；OpenSpec及差异空白检查通过。覆盖展开逐字段等价、全部351个 ID、非法/拼接引用拒绝、输入/Prompt/manifest不变、小包和历史兼容、仍超限拒绝与现有调用隔离。初次新测试因引用未安装的 jsonschema 导入失败，随后改用仓库现有校验器和完整结构还原对照；未安装依赖，未把该环境错误计为通过。

只读读取原失败批次的六个实际输入并在内存执行新构造函数，不写旧包：MSFT/AAPL/NVDA 的 Analyst 均129929字节，Skeptic 均129249字节，完整351个 ID 保留，均低于131072上限。这个测量是确定性接缝证据，不是真实 Agent 已执行的证明。

## 当前版本与真实尝试

- 安装插件：`0.3.0+codex.20260910171818`，已有本地市场，未改市场入口。
- invocation.py SHA256：`dbe2e90c048151b47e11c7bea71164d6fdc7fa1cddd70c476fc779f9dca70094`；已核对安装副本与源码相同。
- 既有保护范围源码快照：`fbda26463b33f9c8623c1cde48e96ac69228c761cc4aeb2abaee139e86914262`。不是全工作区或强制隔离证明。
- 新产物目录：`/private/tmp/stock-agent-three-dedup.wQ7Oed/smoke`。
- 实际宿主参数：`bash scripts/run-product-smoke.sh --profile live-us-equity --portfolio /private/tmp/stock-agent-live-three.xcXLr5/portfolio.json /private/tmp/stock-agent-three-dedup.wQ7Oed/smoke`。沿用外置批准、SEC联系环境变量、live合并Python和既有缓存，合成持仓、不发布凭证。
- batch_id：`live-batch-68af4c06-dc41-4786-b6a6-b19dbc88372d`；batch manifest canonical hash `36f162157434be8a0a382450dc617f962f0a2a3732d6bc04ea2ce9de9864ed2a`。
- 数据 snapshot hash：`eb5f81338ecf0d4c305b0bdff0db320e03f3fee1056e224e2c3eb49097929c68`。
- MSFT：`live-ad213561-abc2-4c41-aa36-a2ba2ccd82bf`；AAPL：`live-b45a63b0-7eab-46c8-a293-d79159a5a5a3`；NVDA：`live-fa9e96dc-8b4d-46e8-92ce-1fd102f9349d`。

## 实际运行结果

本次宿主批次已结束，外层退出码5；没有追加 Council 重跑。三股六位 Specialist 都留下真实 Start/Stop 事件，启动包超限已解除。三个 process-result 均记录 source_integrity_unchanged=true，现行保护范围快照仍为上述 hash；不扩展为全进程隔离证明。逐文件 SHA256、run manifest canonical hash 与运行结果标识见 `live-three-dedup-result.json`。

| 目标 | 启动及专业研究 | CIO / Risk / 原生 Eval | 独立研究质量评分 |
| --- | --- | --- | --- |
| MSFT | 两位专家均执行，报告交接未通过校验 | 未到达；FAILED_VALIDATION | 未启动，不能给无合法研究终态的运行补造评分 |
| AAPL | PASS | PASS，SAFE_NO_TRADE，四个终态产物齐全 | FAIL，analyst_thesis_grounding=1；其他四维 PASS |
| NVDA | PASS | PASS，SAFE_NO_TRADE，四个终态产物齐全 | INVALID_OUTPUT，实际评分已执行，但输出契约失败，不能计作通过 |

MSFT 第一处失败来自真实 `prepare-cio` 输出：`EVIDENCE_CLOSURE_FAILED`，保存的 Analyst 报告包含不存在的 ID `ev-sec-text-0e1cc2fe6f17b8176c0ccb6304c2f43ec33f888b469fc4ee6f59fdfc2625178ee463d`。随后宿主校验报告 `CHILD_REPORT_OUTPUT_HASH_MISMATCH:runtime_company_analyst`：Hook 记录的结构化输出 hash 为 `2b5b778f4abd91966106bc13eb274f80e51eb7316fbc354a50af75d8eb3a903b`，已保存报告 canonical hash 为 `d4758c840727bc098943f9a9a0e35b6ec6933a0521c3a97d4b41af7d43f40975`。Skeptic 两者一致。证据证明保存报告与原始执行输出不一致，不能在未保留原始完整消息的情况下断言具体哪个字段由哪一步改写。没有替换、截断 ID、覆盖报告或放松校验。

AAPL 的全部确定性硬门禁通过，真实独立 dev_eval/Terra 判定研究基础不足，保留 FAIL。原因是报告未建立合格行情和至少两期可比财务基础；这不是所有事实来源不可用的结论，也不以 NO_TRADE 本身判失败。既有输入含部分财务字段的歧义/截断限制，Agent 实际查询过派生指标、SEC 财务及文本，不能声称“完全未查询财务”。进一步整改需要核对证据选择和研究使用，不据此降低 rubric。

评分路径：`/private/tmp/stock-agent-three-dedup.wQ7Oed/semantic-aapl/eval/result.json` 与 `eval/report.md`。parent session `01a08c63-39dc-7b71-9c2b-8bfb362410df`，child session `01a08c63-aa6e-79f0-b2af-e3343c259280`，执行证明 hash `ed4dd3c829c6bfad0d068758c6cb2bef20f577ae1ffa2bf6fc46cc3abed9c90f`，Eval hash `ede5b69f52e39a49adf6178f50ee222c86c385a1afe32671d92f36a695022b16`。已使用 live 合并环境的 `verify_runtime_eval_job` 重新读取底层产物，重算保持 FAIL；未重复调用评分模型。

NVDA 评分协调线程落盘 JSON 缺少引号，原始 `semantic-result.json` 保留。使用仓库已有 `discover_eval_rollouts` / `_final_structured_output` 从实际 child session `01a08c6a-db8c-7aa0-8957-231d6e731ce9` 原样提取最终对象到 `semantic-result-from-session.json`，不改任何字段。parent 为 `01a08c6a-77d3-7751-8d29-5400da524ad7`，child 原始会话文件 SHA256 `ab24f43cab48d863c87e93f28ffbc21bdddb9f90a374dbeed3a4e5b1f9b2f1aa`，提取对象 canonical hash `e0b45478efce99b053d98cfb9850fe5a92036202e9dcdf53932878804836d647`。恢复后真实执行证明通过，proof hash `8abc691ca754bfeaab9ff7efa39c62a70a7f4e1fe8e8c1cd96226aac98099d2e`；但原始评分自己的 output_hash 仍不合法，`eval-finalize` 退出6、`SEMANTIC_OUTPUT_HASH_INVALID`。没有重新计算后替换该字段，也未重评；因此不存在可接受的 NVDA 语义 Eval 终态。原始全局会话不复制进仓库。

## 本次评分与汇总命令

两个真实评分各执行一次，使用仓库 `eval-prepare` / `eval-smoke-prompt`，并保存明确 prompt。宿主统一使用 Terra、原生 workspace-write、独立 SQLite/log/tmp、只读源运行和指定外部评分目录，无新沙箱。实际命令参数与执行事件分别保存在外部 `eval-aapl-invocation` / `eval-nvda-invocation`；产品 Smoke 命令见前节。评分入口形式如下（SLOT 为 aapl 或 nvda）：

```sh
codex --ask-for-approval never exec --json --sandbox workspace-write --add-dir /private/tmp/stock-agent-three-dedup.wQ7Oed -C /Users/caihaoming/Documents/stock_agent --model gpt-5.6-terra -c 'sqlite_home="/private/tmp/stock-agent-three-dedup.wQ7Oed/eval-SLOT-invocation/sqlite"' -c 'log_dir="/private/tmp/stock-agent-three-dedup.wQ7Oed/eval-SLOT-invocation/logs"' -c 'history.persistence="none"' --output-last-message /private/tmp/stock-agent-three-dedup.wQ7Oed/eval-SLOT-invocation/final-message.txt -
```

命令 stdin 来自各自 `prompt.txt`，stdout/stderr 分开保存；PATH 使用既有 live 合并环境，TMPDIR 指向各自 tmp。只进行确定性恢复，不额外启动评分或 Council。

```sh
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m product.runtime.cli eval-execution-proof --repo /Users/caihaoming/Documents/stock_agent --eval-dir /private/tmp/stock-agent-three-dedup.wQ7Oed/semantic-nvda --semantic-result /private/tmp/stock-agent-three-dedup.wQ7Oed/semantic-nvda/semantic-result-from-session.json --sessions-root /Users/caihaoming/.codex/sessions
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m product.runtime.cli eval-finalize --repo /Users/caihaoming/Documents/stock_agent --eval-dir /private/tmp/stock-agent-three-dedup.wQ7Oed/semantic-nvda --semantic-result /private/tmp/stock-agent-three-dedup.wQ7Oed/semantic-nvda/semantic-result-from-session.json
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m product.runtime.cli summarize-live-batch --repo /Users/caihaoming/Documents/stock_agent --batch-dir /private/tmp/stock-agent-three-dedup.wQ7Oed/smoke/batch --semantic-index /private/tmp/stock-agent-three-dedup.wQ7Oed/semantic-index.json --output-dir /private/tmp/stock-agent-three-dedup.wQ7Oed/summary
```

汇总退出5、FAILED，summary hash `ab241b9714680cd56ded54c06aeae3a7dcba8a3c59dda591d403e135fc02539f`。MSFT 为运行失败，AAPL 为研究质量失败，NVDA 为缺少有效语义终态；汇总不发布任何子建议。评分原始输出不是合法验收结果时，不用静态 candidate、修改分数或补写 hash 替代。

本轮授权的无损去重已完成并实跑验证；未扩大实现范围修复上述新暴露问题。下一步仅需处理 Specialist/评分结果原样交接与财务研究依据，不能以重新跑全套平台检查代替修复。

Task 5.3/5.4/5.5 均保持未完成。此轮不具备完成批准条件；未执行全量 Gate、Regression、归档或 Git 发布，ISOLATION 仍为 UNVERIFIED。
