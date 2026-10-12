# 实施验证记录

验证日期：2026-09-23。

## 聚焦验证

执行：

```text
PYTHONWARNINGS=error::ResourceWarning python3 -m unittest \
  tests.test_tiger_readonly_adapter tests.test_tiger_ledger \
  tests.test_tiger_normalization tests.test_tiger_sync \
  tests.test_tiger_intake tests.test_tiger_trade_analysis \
  tests.test_tiger_cli tests.test_tiger_web tests.test_tiger_vertical_slice
```

结果：49 tests，全部通过，无真实账户、网络、LLM、Eval、Regression、Ablation 或 Promotion 调用。覆盖状态测试同时证明：四类同步缺失会降级为 `PARTIAL`，失败窗口可被后续同窗成功 receipt 正确替代，资金明细缺失时分红/税费不会误报为零，部分覆盖下的非空收益图标记为 `LIMITED`；连续快照将同一持仓保存为修订，未实现盈亏只使用最新账户快照的持仓集合；CLI 只回显白名单稳定错误码，不回显任意 provider 异常文本。锁定 SDK 3.8.0 wheel hash 已重新核对，配置 preflight 接受其实际支持的 `private_key`、`private_key_pk1`、`private_key_pk8` 三种字段，并拒绝只有公钥的配置。

受影响既有回归再加入 `tests.test_portfolio_intake`、`tests.test_local_research_browser` 与 `tests.test_governance` 后为 123 tests，全部通过。纵向切片使用仓库外临时合成 ledger，覆盖 US/USD + HK/HKD 混合账户、Draft、明确确认 Handoff、同步、分析和 `/trades`；只读浏览前后数据库及输入契约 hash 不变。

## 开发入口核对

仓库当前不存在可无参运行的通用 `scripts/council-dev.py self-check`：该入口只允许 `self-check check-run` 或 `self-check trace-check`，并且二者都要求既有运行目录。实际执行无参命令返回 `SELF_CHECK_COMMAND_NOT_ALLOWED`，因此没有虚构 PASS，也没有为本 Change 启动产品运行或 Eval。

全仓 `python3 -m unittest discover -s tests` 实际运行 1136 tests，用时约 679 秒，结果为 9 failures、27 errors、22 skipped。失败来自实施前已存在或与本 Change 无关的基线问题，包括 `FIXTURE_MCP_TOOL_DRIFT`、缺少 `exchange-calendars`、已归档 Change 路径仍被旧测试引用、候选版本/hash 漂移及既有 promotion 断言；新增 Tiger 聚焦套件没有失败。此结果不作为本 Change 的 PASS，也不会触发候选晋升。

## 严格规格与静态检查

- `openspec validate integrate-tiger-hk-readonly-portfolio-and-trade-review --strict`：通过。
- `git diff --check`：通过。
- 敏感信息定向扫描：未发现真实邮箱、个人绝对路径、私钥 PEM、长 Token、真实账号或个人交易；测试中的短值均为显式合成 fixture。

关键边界文件 SHA-256：

```text
248d6334c56bf28cfeccee79d05fe85ed6e42949c9b9c4832e9a873d6dd3172b  broker-sync-manifest.schema.json
859da9995500e0ba09beb02f2f9a6e089c36f298c7eea85d15fbda1005948bb2  tiger-account-snapshot.schema.json
48c7a4882171e3144aaa47667ff0bc28ea14db7e8c75573e92555ca9d2f4522c  trade-history-analysis.schema.json
ed7821c980d3d5fa2b6efbf7aca0a49904354ba28d503f84d770a997323fd32c  capability-manifest.json
31f9d397981afa79c678266de07a32108e3c6e828eb02e6e79adf293d56a2cf6  tiger-readonly-broker-data.md
```

## 尚未完成

尚未提供用户本机 Tiger 仓库外配置目录、私人 ledger root 与首次历史起点，因此未连接真实 TBHK 账户，未执行真实快照、重复同步、重叠增量和真实分析。Change 不得据此归档或宣称真实接入已跑通。
