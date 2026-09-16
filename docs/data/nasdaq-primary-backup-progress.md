# NASDAQ 与主备行情：当前 apply 阶段记录

## 最新续进：主备采集接缝（2026-09-10）

用户说明当前仅个人自用；本轮继续实现与离线验证，不重复开展条款讨论，不将个人用途改写为来源已授权。以下覆盖范围取代下文旧阶段的“尚未接入 collection/snapshot”进度描述；旧 hash 和旧证据仍保留原适用范围。

- Task 1.3/2.5（部分）：新增 canonical 数据选择策略、SourceSelection Schema 和 snapshot v3；验证主备顺序、允许回退原因、选择 hash、证券/事实/缓存原文、时间及完整价格来源。旧 snapshot v1/v2 文件不改写。
- Task 2.1/2.6（部分）：已有 collection 接入 NASDAQ 目录、Yahoo 主行情及 AKShare/东方财富备用，复用原请求边界、日历、行情身份解析和 SEC 封面绑定。每只证券只采用一个来源的价格集合。未被选择的合法原文保留在审计包，不进入研究或估值。中文报告增加来源选择与目录覆盖说明；不生成投资结论。
- 原文验证和 prepare 支持新快照及备用行情身份；确定性测试实际执行采集替身→SDK 本地解析→冻结→原文身份重验→PIT→批次准备，止于 DISPATCH_REQUIRED，没有 Specialist/CIO 模型运行。
- 当前运行 profile/discovery 仍是旧 Yahoo＋SEC 拓扑锁，尚未完成 Task 3.1。因此 prepare 接缝通过不能当作新版正式运行锁、加载证明或真实研究通过。Task 1.3、2.1、2.4–2.6、3.1、4.3、5.1 均保持未完成，整体仍为 10/24。

实际执行（仓库根目录，合并依赖锁不变）：

```sh
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest tests.test_live_collection tests.test_live_source_routing -v
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest discover -s tests -p 'test_live_*.py' -v
openspec validate us-equity-live-advisory-slice --strict
git diff --check
```

结果：首次聚焦 16/16；补充过期主源原文保留用例后，当前 live 确定性集合 155/155，通过、0 跳过，5.804 秒，退出码 0。严格规格校验与已跟踪文件空白差异检查通过。上述为工具实际执行结果的记录，非完整原始 stdout 档案；不是独立 Reviewer 结论。行情 HTTP 响应及身份输入为合成数据，模型及宿主调用由测试替身覆盖，不能作为真实网络、LLM 或加载验收。没有运行全量项目 Gate/Regression 或提交私有持仓。

本轮相关文件完整 SHA-256（不是完整候选快照）：

| 文件 | SHA-256 |
| --- | --- |
| product/mcp/live/source_routing.py | fd8a5167f685598a9a21f9653f937fc5e2a6d333c3a7ad82fe15a0c4158c9439 |
| product/mcp/live/collection.py | 2a8877b626fc5ec53ffbca23bbed32f0e0a1e5355c65466cd5efc142e83c5683 |
| product/mcp/live/contracts.py | bf5a790ca0c3a73ec124b60b27d02c7406bad440959d7b7aca64ed4647d9a03b |
| product/mcp/live/eastmoney_transport.py | ccad69151fb123a5b689bf88a8e37ccb302f2d5a09b5691e4fc190879d9f5cd0 |
| product/runtime/live_input.py | b9e445a9910da236de1db4acedde3f3803951131c31d181746438b2ad651501d |
| product/runtime/live_context.py | b582db20a499bbcb583b9c201ed2f6136a0bda4257d677fdf5389fbf08963c3e |
| product/runtime/run_package.py | 4d098c2fc575be4632bfafebf247a9fc7912b95a726ad2e67ea54284e519c02c |
| product/runtime/live_report.py | 7fcfcefe9807a0b2a9469f8a82db5c54e08437a2054c5446bef8a4464cf838d6 |
| product/schemas/runtime/live-source-selection.schema.json | 6712f6668798ecb94dcf4415b5704d8bf82c894e0823d978b6a45112b8e2ad4a |
| product/schemas/runtime/live-snapshot-v3.schema.json | 49996cd065db4af23b56553f6f5de28ac6c02b5a63d32b5adf1dc82adbe61365 |
| tests/test_live_source_routing.py | 3c43b6c9730f570051380966bf5ab6541b11b7a4f8d2e8d8b5c397cd44936fea |
| tests/test_live_collection.py | 624cbc86ff0ac13d39132045c44651a2b582cd960d6c8abb4b168fc66f2f13a1 |
| requirements-live-macos-py313.lock | 0ed376457f4ba48b81876beeb3d2e2cf9a0eaffc53529c860e23160a0fd9cea0 |

下一项实现是同步版本化 live profile/discovery/Trace 与新版拓扑，并完成对应来源版本锁和文档接缝。真实来源采集、单股/三股研究、独立复核与人工批准没有被此次测试替代。全进程源码隔离继续 UNVERIFIED。

日期：2026-09-10。所属 Change：`us-equity-live-advisory-slice`。本记录仅证明下列实际执行范围，不是 Change 完成、真实行情成功或 Promotion PASS。

## 实现与适用范围

- Task 1.2（完成）：新建独立合并环境 `/private/tmp/stock-agent-live-combined.jtbR6l/venv`，同时安装 yfinance 1.7.0、AKShare 1.18.94、exchange-calendars 4.13.2；`pip check` 通过，将实际 `pip freeze` 结果写入当前可选依赖锁。原两个隔离环境未修改。39 个发行版的版本锁不等于 wheel 内容锁或跨平台验证。
- Task 1.3（部分）：新增 source-access v3 的数据角色及 NASDAQ universe Schema/Validator。旧 fact/snapshot v1/v2 保持原契约；SourceSelection 和当前主备 profile 尚未接入，不能提前完成本项。
- Task 1.5（部分）：新增 `product/mcp/live/nasdaq.py`，显式创建客户端才允许请求；有界分页、去重、追加缓存、页面原文/hash、完成度及观察时间。目录中的股类和 ADR 不自动认定普通股，不提供投资排名。真实分页和正式准入尚无证据，不勾选。
- Task 2.4（部分）：Yahoo transport 升至 1.1.0，429 与 401/403 一样立即失败且锁住调用链；暂时性 5xx/超时仍有界重试。其他请求/缓存边界尚需原任务后续验证，不能以这一处修复勾选全部完成。
- Task 1.1：已更新 `us-equity-sources.md` 的当前选型及新 NASDAQ 条款依据。正式来源准入仍为 `BLOCKED_PENDING_AUTHORIZATION`，不是网络配置失败；本轮没有真实目录、行情或模型请求。

## 已实际执行的确定性测试

工作目录均为仓库根目录。所有行情响应是合成输入；真实 SDK 仅用于本地签名、解析和 Session 兼容检查。测试使用系统允许的临时目录，不新增沙箱。

```sh
python3 -B -m unittest tests.test_live_nasdaq -v
python3 -B -m unittest tests.test_live_nasdaq tests.test_live_contracts_gate tests.test_live_eastmoney_contracts tests.test_live_yahoo_transport -v
python3 -B -m unittest tests.test_live_nasdaq tests.test_live_yahoo_transport -v
/private/tmp/stock-agent-live-deps.cBmS73/venv/bin/python -B -m unittest tests.test_live_nasdaq tests.test_live_yahoo_transport tests.test_live_market -v
/private/tmp/stock-agent-source-trial.JhvGbZ/ak-env/bin/python -B -m unittest tests.test_live_eastmoney_transport tests.test_live_eastmoney_contracts tests.test_live_contracts_gate -v
openspec validate us-equity-live-advisory-slice --strict
git diff --check
python3 -B -m unittest tests.test_product_config tests.test_live_profile -v
```

结果按执行顺序：初始 NASDAQ 12/12；首次共享接缝 49 项中 45 通过、4 因基础环境未装可选 SDK 跳过；新增 3 项目录测试后 22 项中 21 通过、1 跳过；Yahoo 隔离环境 29/29、AKShare 隔离环境 41/41，均无跳过。严格规格校验、已跟踪差异空白检查通过。Git diff 不包含尚未跟踪文件，不能据此声称新文件已经过 Git 差异审核。

目录最终 15 项覆盖：有限分页、默认 20/7139 不报完整、空页/重复/总数变化、页/行/请求预算、401/403/429/重定向停止、HTML/超时、缓存首次观察时间、未来缓存、底层原文/hash 重验、伪造 COMPLETE/成员历史时间、来源准入/角色拒绝及符号标点不静默合并。真实 HTTP 分页参数仍未验证。

基础 Python 不含 yfinance、AKShare、exchange_calendars；其下产品配置/profile 的 20 项测试全部通过（无跳过），包括 Gate-scoped MCP 本地 stdio 握手，不访问 Provider 或模型。这不是真实 Council 加载/研究证明。

## 本阶段文件 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| product/mcp/live/nasdaq.py | 4522292daa62c8705bcd44b03ffa3bacaadd96b8b2e23e52124f3cb26d2c3673 |
| product/mcp/live/contracts.py | 7896cc8265049d7439bcb94c66a75a187eda98cf6a9d3cb203432e596af7b0bf |
| product/mcp/live/yahoo_transport.py | 5976cc2f51fbf29af79eb81594660c62b98ec23eb30d85dc1eaf2904a2791d3f |
| product/schemas/runtime/live-universe.schema.json | 8a5d75c3388725b001de81ebccf8c94c57b0ca784f81f720808896aebb85cdc2 |
| product/schemas/runtime/live-source-access-v3.schema.json | 381511848877ffa4362411f8339f032fb18113931b0593dcc8ed896f7ca4f429 |
| tests/test_live_nasdaq.py | 76638980aed15184706ee01da92920875ff56f372e04b055525bcdebd72fe786 |
| tests/test_live_yahoo_transport.py | 71e2ea58b927f2571a4495edf82830d25d74d17efadc0e9fd8b3699d34779ecb |
| requirements-live-macos-py313.lock | 0ed376457f4ba48b81876beeb3d2e2cf9a0eaffc53529c860e23160a0fd9cea0 |
| pyproject.toml | 56509d0db6a6baca816613202a545e7bc6f20249338bd3dfe33443983bec6831 |

以上仅为本阶段改动/新增文件标识，不是完整候选源码快照。旧 59/105/131 证据不得直接包装成此版本锁的整条运行证明。最近的东方财富身份映射修改不在本记录的通过范围内。

## 剩余边界

合并环境最终执行以下限定测试，90/90 通过，0 跳过，unittest 耗时 12.054 秒，退出码 0。命令和工具返回的完整测试输出保存在外置 `test-result.json`，不是模型写出的静态 candidate 分数。测试未访问数据 API、未调用产品 LLM；依赖安装只访问包分发服务。

外置记录：`/private/tmp/stock-agent-live-combined.jtbR6l/test-result.json`，SHA-256=`617725b510fe07730e5b27598c14ca6df466a3b066f78aa7c66e9a57bc1e2c5f`。

```sh
python3 -m venv /private/tmp/stock-agent-live-combined.jtbR6l/venv
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -m pip install -r requirements-live-macos-py313.lock yfinance==1.7.0
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -m pip check
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -m pip freeze
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest tests.test_live_nasdaq tests.test_live_yahoo_transport tests.test_live_market tests.test_live_eastmoney_transport tests.test_live_eastmoney_contracts tests.test_live_contracts_gate tests.test_product_config tests.test_live_profile -v
```

安装发生时 `-r` 为上一版 AKShare 锁，本轮成功后由实际发行版清单更新成合并锁；不能倒置这一顺序宣称当时使用了最终锁。原始输入锁见版本化阶段记录，新增解析依赖已全部固定在当前锁。pip 的宿主缓存不可写警告只导致禁用下载缓存，安装和依赖检查实际均成功；没有执行提权或改权限。

目录＋主备选择尚未连入 collection、snapshot/profile、Trace、中文报告与实际 Eval。继续复用现有实现，不另建编排后端。真实目录和 1→3 Council 仍须解决来源准入并完成受影响接缝后执行；未开展独立复核或人工完成批准，不归档、提交、推送，不修改生产指针。全进程源码隔离继续 UNVERIFIED。
