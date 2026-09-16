# Live 契约与离线接缝实施记录

日期：2026-09-10。Change：`us-equity-live-advisory-slice`。Yahoo 真实抓取按用户最新选择继续暂停；本记录不是真实行情或 Council 验收报告。

## 已完成与适用范围

- Task 1.3：五类版本化 Schema、完整持仓声明、1–3 股、USD、正且有限数量、明确期限/Mandate/focus、外置输入路径；证券映射与股类/发行人绑定重算。成本价不能替代行情。身份快照保留底层映射，不只保存 PASS/hash。身份缺失或晚于 cutoff 时不得创建专业输入。
- Task 2.2 的采集/解析实现：CIK/ticker 映射、submissions 与受预算控制的历史分页、companyfacts、指定披露及相关附件读取，均已有合成响应测试。真实 SEC/Yahoo 访问仍属于未完成的来源准入和 Task 5.2/5.3，不能由这些测试替代。
- Task 2.5、3.2、3.3 局部：live PIT 独立时效规则、派生父证据闭包、版本化交易日历、Gate→完整组合估值→专业输入及 Risk helper、只读 query/calculate 核心。尚未接入 prepare/finalize/Trace/Eval/宿主全链，保持未完成。
- Task 3.1/3.4 局部：显式 live profile、拒绝未知 profile、明确 focus、共享快照的唯一子运行 ID 计划。配置文件存在不是实际加载；没有批次完成或真实执行证明。

## 实际验证

| 实际命令 | 结果 | 证明范围 |
| --- | --- | --- |
| `/private/tmp/stock-agent-live-deps.cBmS73/venv/bin/python -B -m unittest discover -s tests -p 'test_live_*.py' -q` | 68 tests，OK，无跳过 | 所有当前 live 合成测试；真实本地交易日历、SDK 函数签名及合成 DataFrame 接缝；不访问 Provider |
| `python3 -B -m unittest discover -s tests -p 'test_live_*.py' -q` | 68 tests，OK，3 skipped | 未安装可选 live 依赖仍可导入/执行其余测试；3 项 SDK/日历相关测试不据此判 PASS |
| `python3 -B -m unittest tests.test_live_profile tests.test_native_evidence_gate tests.test_native_invocation_validation -q` | 28 tests，OK | profile 分流、原 fixture MCP/Gate 和 invocation 的受影响确定性兼容接缝 |
| `openspec validate us-equity-live-advisory-slice --strict` | valid | 本 Change 规划结构合法，不证明功能完成 |

测试输入直接定义于 `tests/test_live_*.py`；写入为 unittest 独立临时目录中的合成缓存，测试后清理，不将临时目录冒充持久的真实运行包。没有环境错误、断言失败、模型调用、全量 Regression 或 Release Gate。

## 依赖锁与观察边界

`pyproject.toml` 的 live extra 固定 yfinance 1.7.0 和 exchange-calendars 4.13.2；实际在 macOS arm64 / Python 3.13 的独立 venv 安装成功。解析出的发行版版本保存在 `requirements-live-macos-py313.lock`，不是跨平台或 wheel 内容 hash 锁。

已对实际安装的 `yfinance.download` 签名验证显式参数，不联网；`auto_adjust=False` 不代表上游历史 Close 一定未经拆分调整。XNYS 日历实际验证假日、提前收盘与夏令时。原 fixture 不要求安装上述依赖。

SDK 源码出现的 Yahoo 域名包括 `fc.yahoo.com`、`query1.finance.yahoo.com`、`query2.finance.yahoo.com`、`finance.yahoo.com`、`guce.yahoo.com`、`consent.yahoo.com`。这是静态代码观察，不是本次实际访问记录、最小必要域名证明或授权。未修改 allowlist，未尝试绕过暂停。

Task 1.2 仍缺实际端点验证；Task 2.1/2.4 仍缺完整身份元数据获取及 SDK 内部请求预算/域名约束接缝。SDK 调用数明确不等于 HTTP 请求数。

## 当前被测文件完整 SHA-256

```text
31ee56b3c564fb1175323ae6d5d93181f67c3095bdf1a6a597f0fcaaccbfc5b4  product/mcp/live/contracts.py
44db7f38294ad874bf9e307b51f6981c010745efc1c35b70f0b28ddcca0d05dd  product/mcp/live/identity.py
46dadc158a6078fe81d536fa9a6a48cbcaa7994bc680ecaff7af5523b47d4beb  product/mcp/live/market.py
15750f24c1f940619a52b56ea6b5fbe3b23a39f7f953708984b70fa937797759  product/mcp/live/sec.py
94011bbdafc18ff959a0b313b6b60dafd87769a7b9bde2a7a228efad9271c641  product/mcp/live/sec_client.py
db412d637601b09b4d87f699599b9bd26b7458e34f98511b17b840c819485e54  product/runtime/evidence_gate.py
df9b9f0437801e6c2b636725492c5e2b4836694ada6bc34d1b17936193e5a285  product/runtime/live_input.py
c6af1fec66b42ac8b5234257de1d4ed60b810af9d8825b7a1b81c6fb21d621e5  product/runtime/live_mcp.py
18a0c829ea23bf1359c3c0ef745630f5435d9d1ae0d895f52789c6839ae17e9f  product/runtime/fixture_mcp.py
8be7366dc65d8e123feee3a8dbbe6dc0bbacaab4bab4fd24ab0ca98f94565884  product/runtime/invocation.py
d4cde1079f3c1645669223c7d03ea17f081b058127032fa007ec709c290607b6  product/runtime/risk_runtime.py
098a824f4bbfa94584d9915195f444a1be136beacd8c69dc4698e1675ecdde88  product/runtime/runtime_profiles.py
767cba5b6567ebdee166afba553a97a1d558acc670d50592af9a365beccd57db  product/profiles/live-us-equity.json
4ca1e49bd057144107c0fb6f1e544dec2f65133f13869af73a57d8052cde36e4  product/schemas/runtime/live-portfolio.schema.json
ecc9155d5dc2f24e36b5f5d55cbacd62f3703c6250c43c9a1eaf174b40cdb706  product/schemas/runtime/live-fact.schema.json
a1e22011bc575778bf8facfb5f3e4f79e3235744fc8bf71b0d8fe33b2e7c958d  product/schemas/runtime/live-source-access.schema.json
1d4779ce3fbeab769f777fd60fb169b83537929c1df2ea693f75954fd3c92eea  product/schemas/runtime/live-snapshot.schema.json
256704d0548d110e6a66b7318b85c0be24d1d573d6be89c54ffd4fde6aff73e3  product/schemas/runtime/live-batch.schema.json
4f7c22d65411760847cc1985ab4ec74d2fd7e7028d69e725c23d8a6837a67b8d  tests/test_live_contracts_gate.py
7be3f9c515ebae7e0b557d81ccb3671521ca52c98d84a5e91030a3e7fb6acfc3  tests/test_live_market.py
5688e9dacfdb17a3d36ff2fa7773a4fd8d3d3f6319e15d9a14f7c269b84696e0  tests/test_live_profile.py
c51716a3ca8f7a07d702a80c457df9fb36be6444e20a501007ff4ae2ce7787ab  tests/test_live_sec_client.py
3584c3a4fa0cc2ca18a3e0e3ded23e0d39ceaf57b9f8102e63e35395e75acfc5  pyproject.toml
47e6aefe5fd91a2f36d3fd7bdb46d7494e5be9ce4245b28fdb61edf7798d1b86  requirements-live-macos-py313.lock
```

此表只绑定上述阶段被测文件，不是候选完整源码锁或生产晋升证据。后续受影响实现变更需要更新对应测试证据，旧真实 fixture 运行不能替代 live 验收。
