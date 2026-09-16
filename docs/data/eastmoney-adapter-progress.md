# 东方财富适配：依赖与请求接缝阶段

日期：2026-09-10。Change：`us-equity-live-advisory-slice`。下方第一阶段 hash 是历史证据；最新增量与仍未接通之处见文末第二阶段。
证据标识：`eastmoney-scoped-sdk-offline-20260910`。

## 已实施与证明边界

- Task 1.2：live extra 改为 AKShare 1.18.94、exchange-calendars 4.13.2，当前 macOS/Python 3.13 安装版本锁已更新。旧 Yahoo 环境、试拉和历史 hash 清单未修改，不能将其包装成新来源证据。
- Task 2.1/2.4 部分：新增 `eastmoney_transport.py`，实际 SDK 的函数代码使用逐调用独立 globals 注入内存 transport；不改原函数、全局 requests 或安装文件。SDK 版本和函数源码 hash 在请求前核验。
- 请求前把 SDK 的 `end=20500000,lmt=1000000` 改为明确的 `beg/end/lmt`；最大日期跨度 365 天。保留原参数与实际参数、实际 HTTP 次数、时间和原文字节 hash。
- 401/403/429、重定向、HTML/错误身份/日期/价格均停止；暂时故障最多重试两次、受请求预算约束。提供读取时 2 MiB 上限函数。
- 模块没有默认网络 transport，尚未连接 collection、缓存、来源授权和证券身份。不能据此宣称生产 Session、全批次速率、身份校验或正式采集通过。任务 2.1/2.4 保持未完成。

## 实际命令与结果

工作目录均为本仓库。AK 环境为外置 `/private/tmp/stock-agent-source-trial.JhvGbZ/ak-env`；旧 Yahoo 环境 `/private/tmp/stock-agent-live-deps.cBmS73/venv` 未改。仅向 AK 环境安装交易日历依赖；试拉原始结果文件没有变更。

```sh
/private/tmp/stock-agent-source-trial.JhvGbZ/ak-env/bin/python -m pip install exchange-calendars==4.13.2
/private/tmp/stock-agent-source-trial.JhvGbZ/ak-env/bin/python -m pip freeze
/private/tmp/stock-agent-source-trial.JhvGbZ/ak-env/bin/python -m pip check
env TMPDIR=/private/tmp /private/tmp/stock-agent-source-trial.JhvGbZ/ak-env/bin/python -B -m unittest discover -s tests -p test_live_eastmoney_transport.py -v
env TMPDIR=/private/tmp python3 -B -m unittest discover -s tests -p test_live_eastmoney_transport.py -v
env TMPDIR=/private/tmp /private/tmp/stock-agent-source-trial.JhvGbZ/ak-env/bin/python -B -m unittest discover -s tests -p test_live_market.py -v
env TMPDIR=/private/tmp python3 -B -m unittest discover -s tests -p test_native_evidence_gate.py -v
openspec validate us-equity-live-advisory-slice --strict
```

| 检查 | 实际结果 | 适用范围 |
| --- | --- | --- |
| pip check | No broken requirements found | 当前隔离环境；版本锁不是跨平台 wheel hash 锁 |
| 新接缝，AK 环境 | 11/11 OK | 合成 JSON、真实 SDK 解析，网络 Session.request 显式禁止；未获取行情 |
| 新接缝，基础环境 | 10 OK、1 skip | SDK 未安装的离线兼容；SDK 源码漂移断言后加入，仅最终 AK 运行涵盖该断言 |
| 既有 market 测试，AK 环境 | 6 OK、1 skip | 日历假日/夏令时/提前收盘真实计算；其他为旧源合成接缝，不算新源标准化通过；Yahoo SDK 测试明确跳过 |
| fixture Gate，基础环境 | 17/17 OK | 基础环境实际无 akshare/yfinance/exchange_calendars；不代表全量 fixture 回归 |
| OpenSpec strict | PASS | 规划一致性，不是数据准入或运行验收 |

SDK 原函数签名为 `stock_us_hist(symbol, period, start_date, end_date, adjust)`，实际使用 daily/空 adjust，唯一目标是 `https://63.push2his.eastmoney.com/api/qt/stock/kline/get`。函数原始 SHA-256：`e539a1b0b85c31fa6dd6d84ea0b19241a805abb62138e7da4844f50509f9ba46`。新接缝实际离线执行复用其 DataFrame 解析；测试不是抄写解析后的静态结果。

## 被测文件完整 SHA-256

```text
afa193f5590f544bdd91529fde445898497bd6d40cf015412e8612fb928ca91e  product/mcp/live/eastmoney_transport.py
28456805dbac20f3c106637b6596fdb41c7d30e7dbde8fcfab79a9f8836717e9  tests/test_live_eastmoney_transport.py
a469cd3aca7207407e03aff7283a165352789cd4e2c185b1ed644d179509f418  pyproject.toml
3dd436399a4e8f3420baeec98307e7b82deaf27e61707d7f31407dadc897592b  requirements-live-macos-py313.lock
75a56d6f3b01c9fafb0d0d9eb9144f21c13e9439035451dc4971f0e3a5f3b915  product/mcp/live/market.py
7be3f9c515ebae7e0b557d81ccb3671521ca52c98d84a5e91030a3e7fb6acfc3  tests/test_live_market.py
678c2c9a1ce6d4dc9aa85426b2a4b238420284f748515682436f93ace4837dca  tests/test_native_evidence_gate.py
```

## 尚缺与停止条件

1. 正式来源准入仍未确认；不新增试拉、不抓行情、不启动 Council/LLM。
2. 原 SDK 文档要求从 `stock_us_spot_em` 的代码字段取得 provider_symbol；不能由单个成功样例推断全交易所前缀、股类和 USD。需要可追溯的小范围身份材料及 SEC 封面绑定，不为三只持仓下载全市场表。
3. 当前 collection/profile/Schema 仍是旧 Yahoo 实现，迁移未完成；新依赖环境不用于运行旧入口。接下来完成版本化身份/来源契约、实际有界传输及缓存、Gate/Trace 接通后，才可做对应新源集成验收。
4. 旧 105/131 项证据仅证明其历史快照。当前依赖已变，不以其替代本次受影响接缝；未改源码部分保留历史适用范围。

未运行完整 Regression/Gate，未修改金融判断、网络配置、生产指针；未归档、提交或推送。

## 第二阶段：连续推进来源契约、缓存、PIT/估值

证据标识：`eastmoney-contract-cache-gate-offline-20260910`。

新增独立 v2 fact/source-access/snapshot Schema，历史 v1 原文件不改；按 schema_version 选择，未知版本失败。新来源集合验证只接受 eastmoney＋SEC、准确 client/adapter 版本与最小域名；拒绝 Yahoo、混源、试拉用途、未知字段和锁漂移。此校验接通 v2 快照，尚未接通旧 collection/profile，不宣称当前宿主已能执行新源。

新增独立 HTTP opener（单一端点、禁止重定向、不持久化 cookies、限长读取）和 EastmoneyClient，串行集合共享 HTTP 预算/限速/拒绝状态。缓存键含 provider/client/adapter/日期/口径，原文字节保留首次获取时间。真实 SDK 的离线内存 transport 证明缓存命中、去重、拒绝及跨证券预算传播；正式网络路径未运行。

新增 eastmoney_market 价格规范化，保留 raw hash/时间/SDK 参数，未知分红和拆股为 null。冻结快照按新来源选择 v2，原 PIT 和完整组合估值不放宽。价格缺失、未来事实/公开/获取时间均不能继续估值。该 helper 依赖上层已验证证券身份，测试的 identity_verified 是合成前置条件，不是上游身份证明；不能暴露为用户绕过身份验证的开关。完整身份验证、实际采集接通及 Trace 新来源锁仍未完成。

### 实际验证

```sh
env TMPDIR=/private/tmp /private/tmp/stock-agent-source-trial.JhvGbZ/ak-env/bin/python -B -m unittest tests.test_live_eastmoney_transport tests.test_live_eastmoney_contracts tests.test_live_eastmoney_market tests.test_live_contracts_gate tests.test_live_profile tests.test_live_batch_execution tests.test_live_host_entry tests.test_live_eval_contract -q
python3 -B -c 'from pathlib import Path; import json; from product.mcp.live.contracts import validate_contract; validate_contract("portfolio", json.loads(Path("docs/product/examples/live-portfolio.synthetic.json").read_text())); print("synthetic portfolio schema: PASS")'
openspec validate us-equity-live-advisory-slice --strict
git diff --check
```

测试实际返回 59 项、5.138 秒、OK、退出码 0；合成输入 PASS、strict PASS、diff check 无输出且退出 0。此前新测试误用 value_portfolio 参数产生一次 TypeError，修正测试传入 snapshot/calendar 后复验通过；没有为测试改动业务估值规则。没有真实 Provider/LLM 请求或全量 Gate。

新源测试 20 项，旧接缝 39 项。后者只证明被测源码/依赖下仍适用的机制，不表示旧 Yahoo 正常路径是新候选的真实研究证据。59 项不是全产品回归，也没有证明当前 profile 已完成换源。

### 当前增量完整 SHA-256

```text
92ade64ac6cd18fa38e900cd091a7661896630070135d14a07b007c6ed05f5f8  product/mcp/live/contracts.py
c960a210e6d25ca695a68a0f0a69a6ba97665ad1e1467c26c47a191e1368e756  product/mcp/live/eastmoney_transport.py
a3fabfa0e51db14c666eed65f37ce5886a5bb6d293d681c1060f06df3998c3ce  product/mcp/live/eastmoney_market.py
da91207a374acd00f02fc3b80704e34eb26d021b8be1e0b267140b75866f2a7e  product/runtime/live_input.py
7ea2884c65dcd6796cbfeb208de7c7afdc0cd366a0919d18536103172bc37e48  product/schemas/runtime/live-fact-v2.schema.json
a06c0ab55313397fbc629311ebe3c6d86022cdef0b42dc202f93343001a01700  product/schemas/runtime/live-snapshot-v2.schema.json
207b5d671a3c84b7be6d8ad45a870540c4a26ea17e3fe47b4bb43a6dc1ce98fb  product/schemas/runtime/live-source-access-v2.schema.json
ca65b9465f6b1da61b5c26df47af1af13fc8a8513652caf985bb35529994cbfd  tests/test_live_eastmoney_contracts.py
4296ebc1622020aaa8b2c059676043fc7b5be74510141a4611b29e4fd3202b14  tests/test_live_eastmoney_market.py
28456805dbac20f3c106637b6596fdb41c7d30e7dbde8fcfab79a9f8836717e9  tests/test_live_eastmoney_transport.py
76772b07b26659c619e3bf39d47de1cfb2624559cfba2b7d4f3040247dfbbd30  docs/product/us-equity-live-advisory.md
8ceae5b79b4374e465e06bd85cec0fd43627e4331dd09014dd870c85224ffcbb  docs/data/us-equity-sources.md
```

Task 4.3 的当前来源、历史标记、隐私、入口待迁移与合成示例说明已更新并验证。Task 1.1 仍缺正式使用条件；Task 1.3/2.1/2.4/2.5/3.1/5.1 保留未完成，因为新源的证券身份和整体接通尚无关闭证据。后续优先明确身份端点、返回字段及映射依据；已向用户申请一次有界身份技术验证，未获批准前不新增请求、不沿用旧试拉额度，不修改生产授权状态。
