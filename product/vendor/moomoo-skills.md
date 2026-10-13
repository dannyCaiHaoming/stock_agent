# moomoo 官方 Skills（第三方，原样引入）

- 来源：https://www.moomoo.com/skills/moomoo.zip（安装说明 https://www.moomoo.com/skills/moomoo-install.md，v2.1.0，2026-04-27）
- 下载：2026-10-13，zip SHA-256 `85104dbe3a1b84e550a3e8bd7bc8f7b2f53c40ba9e80c25956b370984c99f4d4`，许可证 MIT
- 引入的 6 个 Skill（放在 `product/skills/`，内容未修改）：
  - 搜索类（公开 HTTP `ai-news-search.moomoo.com`，无需 OpenD）：`moomoo-news-search`、`moomoo-stock-digest`、`moomoo-comment-sentiment`
  - 异动类（需本机 OpenD，`futu-api` 的只读 `OpenQuoteContext`）：`moomoo-capital-anomaly`、`moomoo-derivatives-anomaly`、`moomoo-technical-anomaly`
- **明确不引入** OpenAPI 类 Skills（含下单、改单、撤单、期货交易、价格提醒、自选修改），符合券商接入永久只读的规则。
- 本项目中的使用约束写在自有 Skill `research-standards` 与 `stock-research` 里；更新时重新下载、核对差异后原样替换，不在第三方文件里改动。
- 异动脚本依赖：`.venv` 中的 `futu-api`（`pip install -e '.[moomoo]'`）；运行时用 `.venv/bin/python -I`。
