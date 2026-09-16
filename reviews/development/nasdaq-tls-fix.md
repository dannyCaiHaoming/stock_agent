# NASDAQ HTTPS 修复与有界真实验证

所属 Change：`us-equity-live-advisory-slice`。2026-09-10，用户要求继续修复数据来源错误。本轮不创建 Change、不修改代理、不关闭 TLS 校验，不执行模型或完整 Gate。

## 修复与实际结果

- 默认 Python CA 文件/目录不存在、信任库加载 0 张证书是前一轮离线检查的实证；原失败事件已丢失底层异常，不能回写为已证实的证书错误。
- NASDAQ 请求现在使用独立 HTTPSHandler，在保留系统信任基础上加载已锁定 certifi 2026.7.22；保持 CERT_REQUIRED、主机名验证、禁止重定向、20 秒及 2 MiB 预算。
- 传输版本 `nasdaq-https/1.0.0` 与 certifi 版本进入当前 live discovery 锁；数据/缓存原语义不回写，旧快照和历史锁未修改。
- 错误事件保留 TLS 证书、其他 TLS、DNS、连接拒绝、连接错误、超时或未知网络错误分类，以及存在时的整数 errno/verify_code；不保存原始异常正文、代理地址或请求头。失败仍锁住当前目录客户端，不重试。
- 36 项针对性测试全部通过、无跳过，涵盖实际 opener 的 SSLContext 绑定、证书加载、脱敏错误分类、拒绝停止、目录与原文字节校验、collection/prepare/profile/准入接缝。OpenSpec strict validate 与 git diff --check 通过。

## 一次真实执行

实际使用产品 NasdaqClient，沿用既有宿主适配检测到的代理值，无代理修改。执行脚本只在外置目录记录此次数据验证，不是新产品入口、探针平台或 LLM 编排。

`/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B /private/tmp/stock-agent-nasdaq-tls.dZ9JbD/verify.py`

结果：退出码 0；请求 1 次，limit=200、offset=0；HTTP 200；39,056 字节；200 行；来源声明总数 7,139。完成度保持 PARTIAL，没有额外分页。主机名验证 true、verify_mode=2、信任库 121 张 CA。没有访问行情/SEC或调用模型。

执行时间：2026-09-10T10:33:30.705414Z 至 10:33:32.673349Z。外置 `universe.json`、`result.json`、`effective-access.json` 与 cache 保存目录/页内容及其血缘。NASDAQ 原文 SHA-256 为 `a1e99836538d7d0df0cb7f14ec8cdaa0ada5f30704ffec01ee1a27afdb2fd17a`。

完整实际命令、测试输出、源码/配置及产物 SHA-256 见 `nasdaq-tls-fix-evidence.json`。原始目录内容留在外置目录，不提交 Git；上游许可仍为 UNVERIFIED，不将 HTTP 200 当授权。

## 任务与复用范围

Task 1.5：有界分页/去重/完成度等既有确定性证明继续有效，本轮补齐当前 v4 准入下实际目录页面、原文 hash 和 PARTIAL 完成度证明，标记完成。当前 19/24。

Task 2.4/3.1/5.1 受影响传输、版本锁和采集接缝由本轮 36 项覆盖；原 175 项仅为修复前快照的记录，不声称当前全量重跑。未扩张旧 fixture、模型加载、Risk、Eval 的证明范围。

Task 2.6、5.2–5.5 仍未完成：真实行情＋SEC＋单股 Council/实际 Eval，随后三股、独立复核和最终人工批准仍待完成。目录请求成功不等于完整投研可用；没有执行全套 Regression/Gate、归档、提交或推送。全进程隔离继续 UNVERIFIED。
