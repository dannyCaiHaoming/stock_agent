# SEC 离线解析阶段记录

日期：2026-09-09。Change：`us-equity-live-advisory-slice`。

## 范围与实际结果

用户已明确仅暂停 Yahoo 抓取，其他实施继续。本次仅实现 Task 2.2 的 submissions/companyfacts 离线解析部分，尚未实现采集、分页读取、原文获取及完整 live 链路，因此 **Task 2.2 保持未完成**。

来源输入为 `tests/test_live_sec.py` 内合成响应，不是真实 SEC 数据或历史运行证据。模块导入与解析不执行网络请求；没有调用模型，也未使用联系邮箱。

解析保留 CIK、accession、期间、单位、修订及原始响应 hash；公开时点绑定 submissions acceptanceDateTime，不将报告期间或 filingDate 当作公开时点。缺少对应 accession 的数据单独隔离，缺指标不填零。这里的解析结果尚未接入 PIT Gate，不代表已完成时效验证。

## 实际验证

命令：`python3 -B -m unittest discover -s tests -p 'test_live_sec.py' -v`

结果：8 项测试通过，退出码 0。覆盖 CIK、公开时间与来源、YTD/单季区分、单位和缺失值、未验证 accession 隔离、非有限数值/期间/绑定错误、畸形 submissions 及修订保留。

命令：`openspec validate us-equity-live-advisory-slice --strict`

结果：通过，退出码 0。未执行全量测试或 Release Gate。旧运行证据没有被用于证明新增解析器。

## 被测文件 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| product/mcp/live/__init__.py | 93a54486d02d3f400373283411ccd89400c98368f96ab482cb1baa92711395bb |
| product/mcp/live/sec.py | 928a82f2f44b1f198e25b468d22d546e778f854d0159c6f32f609e8152878113 |
| tests/test_live_sec.py | 131747556e1827af8e8833f262b991b6f2be9b444632feff8986d5076c4705e3 |

## 后续未完成项

继续实现 SEC 有限只读采集、历史分页与披露文本、外置缓存和 live 契约及接缝。Yahoo 自动抓取继续暂停；完整任务勾选、真实 Council 验收及人工批准仍需各自实际证据。
