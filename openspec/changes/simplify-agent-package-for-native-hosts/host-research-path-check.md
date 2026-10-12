# ALB/MRVL 保存位置的宿主复核

- source_id: native-acceptance-host-path-check:20261006
- as_of: 2026-10-06
- retrieved_at: 2026-10-06
- 范围：用户要求进一步检查既有ALB/MRVL资料，怀疑是否被移除；只读路径/业务文件名及公开Gate字节，不删除、搬迁、写原件、取数或调用模型。

## 纠正此前目录工具观察的限制

目录授权工具返回could not be resolved不能证明文件不存在。经用户可见宿主Terminal检查，两个稳定目录实际存在：

- `/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs`
- `/Users/caihaoming/Library/Application Support/StockAgent/research-memory`

先前无法核对是该目录工具访问路径未成功，不是稳定资料丢失证明。两个明确ALB临时目录在原路径exists=false：`/private/tmp/single-stock-alb-research-20261002-v1`、`/private/tmp/stock-agent-alb-cio6-host.pl6vubq6`；没有证据说明删除时间/原因/操作者，也不排除搬迁或其他备份。

## 找到的MRVL稳定冻结资料

宿主Terminal已列出`acceptance-runs/eight-dimension-rebuild-20260928`中的多个保存候选，包含data/data-v2的Gate/来源包/准备清单，以及多个正式/准备目录中的Gate和正文导入manifest。未读取Handoff、账户/持仓正文、私人账本、凭据或原模型转录。

精确核对原公开清单中的文件：

`eight-dimension-rebuild-20260928/eight-dimension-v4-acceptance.8iWZu9/run/evidence/gate.json`

- 实际文件SHA-256：`35f8f89c7bc1405e9b8a7f3e6ed23e49272fdbed85669ad785ca72ea390cd0ba`。
- 与2026-10-01仓库归档runtime-input-inventory.json中的原字节hash一致。
- run_id：`eight-dimension-rebuild-20260928-v2`。
- decision_cutoff：`2026-09-28T12:35:32.208143Z`。
- allowed_evidence数量：8835。

这证明该MRVL候选的冻结Gate现物存在、字节与旧清单一致，不等于完整包闭合、全部内容合格或新的三宿主验收。MRVL旧包可能含持仓上下文；后续只核对公开事实/正文和合法业务血缘，不自动复制整包、不将它伪造成非持仓单股输入。

## Git与删除归因

Git未跟踪完整single-stock-request.json或source-bundle.json，所查匹配路径的历史删除记录为空；仓库ALB第六稿报告仍在被Git忽略的.codex-local目录。Git不能恢复未提交的外置文件，也不能据此排除或确认文件系统层删除。本会话未执行删除原研究目录操作；不声称其他历史会话从未执行清理。

## 后续准备

无需先重新研究MRVL。可以继续只读核对已找到的Gate、实际正文和同行物化清单/闭包，明确可复用范围；仍需确认是否采用MRVL替代原定ALB公开样本，不能静默更换验收样本。ALB继续沿明确备份/公开Memory指针查找，不据报告摘要重建事实。全部原资料不改，Change进度仍17/24，实际安装/模型/内容验收/发布未完成。
