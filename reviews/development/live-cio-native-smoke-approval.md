# CIO 输出修复后的单股续跑批准

用户在说明“CIO 引用输出接缝已修复、52项测试通过，下一步申请一次真实单股运行，失败不自动重试”后回复“继续”。本记录仅规范化该次续跑授权，不是 Change 完成批准。

- 范围：现有宿主入口，一次真实单股 MSFT Council，合成数量/现金，Terra；成功后依据真实产物执行既有 Eval，不新增来源或模型编排。
- 不自动重试、不启动三股或全套 Gate，不归档、提交、推送或晋升。
- 复用52项接缝证据；本轮仅刷新已有插件缓存标识与对应 manifest hash，产品实现未再修改。
- 插件：`0.3.0+codex.20260910163141`，安装后核对 invocation、nested_codex、smoke_prompt、Hook、live_batch 和 version-manifest 与源码逐字一致。
- run_id：`live-7ba28fd5-ede7-4d0a-8e43-45b6e702b5b3`。
- batch_id：`live-batch-8858996a-3a68-4b57-9269-7f4166ab9738`。
- 外置产物：`/private/tmp/stock-agent-cio-native.kmoxeR/single`。
- 实际 candidate lock canonical hash：`d16313d1258d716e09eb0650f06438c674154a431720e155113873a8c586373d`。
- 运行前受保护源码快照：`6617a8dbf838f940ae904ba4426bfaf8d9df959ce2f9a606a3e3e1996581af4c`。

凭据、SEC 联系信息、代理环境和原始运行包不复制进 Git。全进程隔离继续 `UNVERIFIED`。本文件记录批准及运行身份，不预先记录成功。
