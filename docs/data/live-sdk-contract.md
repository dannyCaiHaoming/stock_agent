# Live SDK 与请求边界核对（离线）

当前差异说明（2026-09-10）：选型已改为 yfinance 主行情＋AKShare/东方财富备用，下面单源依赖和暂停记录属于旧阶段。Yahoo transport 1.1.0 已将 429 调整为立即失败，不再使用下文历史 429 重试行为；5xx/超时仍执行有界重试。NASDAQ 目录适配与 source-access v3 已新增离线接缝，但完整主备采集尚未接通，不能将配置 Schema 已存在当作真实加载证明。合并依赖验证及最新测试范围见后续进度记录。

2026-09-10；只核对本地安装及代码路径，未访问 Yahoo 或 SEC，不构成来源准入或服务可用性证明。

## 锁定与隔离

`pyproject.toml` 将 live 定义为可选依赖；本次 macOS/Python 3.13 环境锁在 `requirements-live-macos-py313.lock`。直接依赖：yfinance 1.7.0、exchange-calendars 4.13.2。此锁没有提供跨平台 wheel 内容保证。

实际安装目录：`/private/tmp/stock-agent-live-deps.cBmS73/venv`。基础 Python 检查 `find_spec` 输出 `yfinance=False, exchange_calendars=False`，在该环境执行的 131 项共享/旧入口确定性测试通过。可选 SDK 只在显式采集/日历路径导入，fixture 不必安装或访问它们。

## 所用参数与端点

- `download` 固定 `interval=1d`、`auto_adjust=False`、`back_adjust=False`、`repair=False`、`actions=True`、`threads=False`、`progress=False`、`group_by=ticker`、`timeout=20`；起止日期及证券集合显式传入。实际 SDK 签名及合成 DataFrame 形态测试通过。
- 自定义 Session 类型通过已安装 yfinance 的 `is_supported_session` 检查，创建时请求计数为 0。不能把该项当作真实下载成功。
- 允许的代码路径为批准域名下的 `query1.finance.yahoo.com` / `query2.finance.yahoo.com` 的 `/v8/finance/chart/<本次 ticker>` 与 `/v1/test/getcrumb`，以及 `fc.yahoo.com` 的匿名 cookie bootstrap。运行配置仍须逐域明确授权；其他域名、路径或证券不因 SDK 想访问而自动放行。
- 本地 `data.py` 确有 guce/consent fallback 及 POST 路径；本实现**拒绝**这些路径、自动重定向和非 GET，不替用户点击 consent、不登录。真实运行若需要这些路径应失败并报告，不默认为它们取得授权。
- 401/403 不重试；429/临时错误最多重试两次，`Retry-After` 超过等待预算即停止。失败锁防止 SDK 捕获异常后继续重试或返回空表伪装成功。逐次请求计数不等于 SDK 调用次数。
- 只缓存 chart 原文字节；查询缓存键移除 crumb，事件不保存查询参数值、请求头或 cookie。匿名 SDK 状态目录只在外置本次采集目录下新建。未修改宿主代理、网络权限或全局认证文件。

上面是**实际安装源码与本实现端点边界**，不是联网观测的最终域名清单。首次真实运行仍须记录实际请求事件，超出边界即停止，Task 1.1 继续未完成。

## 本地 SDK 文件 SHA-256

以下为该安装目录 `lib/python3.13/site-packages/yfinance/` 下的文件：

| 文件 | SHA-256 |
| --- | --- |
| `_http.py` | `573e7c0ffd118af820c12068ba4d081ccb55c8ed3590cff21e5d39273052bca2` |
| `data.py` | `5f41a4cec99d50be3a13c8ae5f2674e1b5e1582be1a861fcdbb57bba783629da` |
| `multi.py` | `61aa5ec181f26c134ed74661b9ed6644935a054d0543b7d1f5b67a1bc0e3dd83` |
| `cache.py` | `9d78cf4439d607142f7683fac28e1c2e98953be6a300355dd843f896a36e3bba` |

真实调用的域名需求、数据质量、更新时效与服务稳定性仍为未验证；Yahoo 按用户要求保持暂停。
