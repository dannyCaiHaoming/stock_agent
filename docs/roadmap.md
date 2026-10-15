<!-- 2026-10-13 批准的开发路线；阶段进度在本文件末尾「进度」一节维护。 -->
# Stock Agent 後續完整開發規劃（唯讀分析，待審查）

## Context

2026-10-12 瘦身後，倉庫只剩業務能力：資料源接入、確定性計算、持倉錄入、Tiger 唯讀與交易日誌，以及研究方法 Skills。舊 Runtime、Council、Gate、Replay、任務授權 MCP 已刪除，研究流程完全失效。
本計畫從目前狀態出發，規劃一套真正可用的「股票研究與投資決策 Agent Package」，在 Claude Code 與 Codex 上原生執行，只用免費資料源，市場限美股與 ETF。

已確認的決策：
- 兩個宿主同時驗收。
- 只用免費資料。
- 只做美股與 ETF。
- 動作集：BUY / ADD / HOLD / REDUCE / EXIT / NO_TRADE。

標記：**[事實]** 表示由目前程式碼確認；**[判斷]** 是我的技術判斷；**[假設]** 表示仍需驗證。

---

## A. 目前狀態與可復用能力

### A1. 可直接復用 [事實]

| 能力 | 位置 | 狀態 |
|---|---|---|
| SEC：companyfacts XBRL、submissions、10-K/10-Q/8-K 章節、Forms 3/4/5、13F | `mcp/live/sec_client.py:103`（`SecClient`，`source_access=None` 時不需准入）、`sec.py:113`、`disclosure.py:84`、`ownership.py:39`、`sec_13f.py` | 可匯入，測試通過；需含 email 的 User-Agent；限速 2 req/s |
| Yahoo 日線 OHLCV、quoteSummary（含 earningsTrend、recommendationTrend）、期權鏈 | `market.py:341`、`yahoo_research.py:199`、`options.py:353` | 可匯入；受舊准入機制限制，但 v1 存取紀錄只要求 `status=AUTHORIZED` |
| Eastmoney 美股日線（備援） | `eastmoney_transport.py:182` | 可用 |
| 宏觀：BLS、Treasury、Fed、BLS 發布日曆 | `macro.py:410` | 不需准入，但會強制寫出檔案 |
| 市場背景：SPY、11 個行業 SPDR、TLT/UUP/GLD/USO/HYG、VIX | `market_context.py:231` | 不需准入 |
| Nasdaq 股票全集、同業候選 | `nasdaq.py:266`、`peer_candidates.py:35` | 可用 |
| 新聞標題：Moomoo public、Yahoo search | `moomoo_public_news.py:80` | 只有標題 |
| 估值：現行倍數、Forward PE、TTM、PIT 版本選擇、PE 歷史百分位、財務比率、同業比較 | `deterministic/equity_valuation.py:154,235,351,399,479,489,675,835` | 以 Decimal 計算並帶狀態碼，測試通過 |
| 估值算術：情境價值、FCF 橋、比率（期間與單位不一致會拒絕）、PV | `deterministic/valuation.py:151-331` | 每次計算都要求附證據 ID 或假設 ID |
| PIT TTM EPS | `runtime/company_valuation_report.py:103` | 可用 |
| 技術統計：20/60/252 日報酬、相對報酬、波動率、最大回撤、量比 | `deterministic/market_analysis.py:148` | 可用；但沒有均線/RSI/beta，唯一的測試也載入失敗 |
| 組合指標、硬風險檢查 | `deterministic/metrics.py:32`、`risk.py:146` | 只支援長倉，`market="FIXTURE"` 寫死，接不上 Handoff v3 |
| 持倉錄入 v3（截圖由 LLM 原生讀取 → JSON → CLI 校驗與確認） | `intake/v3.py`、`intake/cli.py`、`intake/tiger.py:66` | CLI 可用，但沒有可運行的測試 |
| Tiger 唯讀：持倉、資產、訂單、成交、資金；FIFO 交易分析 | `broker/tiger/*` | 測試大多通過 |
| 交易日誌與反思 | `trading_journal/*` | 唯讀與合成資料路徑可用；**真實寫入被 `privacy.py:163` 擋住**（依賴已刪除的 packaging） |
| 研究方法 | `product/skills/*` | 方法有價值，但幾乎每份都夾帶已刪除的 Gate/contract 用語 |
| 評估素材 | `evals/grading/common-stock-research-rubric-v1.json`（9 個維度，0–3 分）、`evals/fixtures/portfolio-intake/`（14 個合成案例） | **全部是合成資料，沒有真實結果**，無法衡量決策品質 |
| 品質教訓 | `archive/research-samples/alb-*`、`archive/pending-ideas/*` | 見 H 節 |

### A2. 已失效，且不應恢復 [判斷]

- **任務授權與 Gate 一類機制**：task_token、Gate ID、凍結快照、准入紀錄逐位元比對、版本鎖、Replay Capsule、Hook 狀態重建、兩稿修訂協議、重度 Schema 的報告契約、fixture Council。ALB 案例證明：「執行與檢查全部通過」照樣產出不合格報告。品質問題出在研究行為，不在基礎設施。
- **`mcp/live/collection.py`、`research_supplement_collection.py`**：重度的收集編排，改由新的薄工具取代。
- **`contracts.require_source_admission` 的 v4 核准紀錄與 `source_routing` 的版本雜湊鎖**：保留 PIT 時間戳、原始內容雜湊、限速/預算、SEC UA；其餘略過。
- **`runtime/evidence_gate.py`**：PIT 過濾改由資料工具的 `as_of` 參數直接實現。

### A3. 缺失的產品能力 [事實與判斷]

1. 沒有任何 MCP server 或宿主配置，Agent 拿不到工具。
2. 沒有完整的端到端研究流程與輸出。
3. 沒有決策紀錄，無法評估。
4. 沒有前瞻績效評估。
5. 免費資料的缺口：沒有情緒資料、沒有預估歷史與修正、沒有法說會逐字稿、資金流只能靠付費的 OpenD，也沒有非美市場。

---

## B. 推薦架構

```
宿主（Claude Code / Codex 原生會話）
 ├─ 主執行緒 = 研究協調 + 最終決策（PM 角色）
 │    └─ 入口 Skill：stock-research / portfolio-review
 ├─ Subagents（只在需要上下文隔離或並行時使用）
 │    ├─ skeptic：獨立反證，不看正向結論
 │    └─ company-analyst：持倉多時逐股並行（第 3 階段）
 ├─ Skills（研究方法，單一來源 product/skills/，兩宿主共用）
 └─ MCP server「stock-data」（Python stdio，兩宿主共用）
      ├─ 資料工具：價格 / 財報 / 申報章節 / 估計與評級 / 宏觀 / 市場背景 / 內部人 / 期權 / 新聞
      ├─ 計算工具：估值倍數 / TTM / 比率 / PE 百分位 / 技術統計 / 情境估值 / 組合指標 / 風險檢查
      └─ 紀錄工具：save_decision（寫入決策紀錄）
私人資料目錄（倉庫外，STOCK_AGENT_DATA_DIR）
  cache/  reports/  decisions.jsonl  portfolios/
```

**單 Agent 還是多 Agent？[判斷]**
- 預設單 Agent（主執行緒 + Skills）。ALB 案例中 21 次 subagent 運行、耗時 86 分鐘、22 次連線錯誤，多 Agent 的成本與脆弱性已有實證。
- 只在兩種情況引入 subagent：
  1. **Skeptic**：反證需要真正的信息隔離。在同一個上下文裡自我批判，會受確認偏誤影響。
  2. **持倉並行**：持倉超過約 3 檔時，逐股研究會撐爆主上下文，需要逐股隔離並行。
- 宏觀與市場研究在組合層級只做一次，並在主執行緒內進行，不拆成 Agent。

**兩宿主共用方式 [假設，需在第 1 階段驗證]**
- Skills 只放在 `product/skills/`，由 `.claude/skills` 與 `.agents/skills` 以符號連結指向它。
- MCP 用 `.mcp.json`（Claude Code）與 `.codex/config.toml [mcp_servers.stock_data]`（Codex），啟動同一個 stdio server。
- Subagent 在 `.claude/agents/*.md` 與 `.codex/agents/*.toml` 各放一份極薄定義，正文只寫「載入某 Skill」，不重複方法內容。

## C. 職責劃分

| 層 | 負責 | 不負責 |
|---|---|---|
| **Agent（LLM）** | 選擇要問的核心問題、決定調用哪些工具、閱讀申報原文、形成 Thesis、反證、處置衝突、綜合決策、寫報告 | 數學計算、單位換算、時間過濾 |
| **Skill** | 研究方法與紀律：數字規則、期間/單位檢查、事實/假設/推論分類、缺口分類（未取得 ≠ 未披露）、反證規則、決策定義與輸出模板、工作流程步驟 | 程式碼、Schema 契約、工具參數細節以外的流程控制 |
| **MCP 工具（Python）** | 取得資料並保留 `source_id/as_of/retrieved_at`；`as_of` 截止過濾（PIT）；快取；限速；所有金融計算；決策紀錄持久化 | 任何主觀判斷、評分、動作建議 |
| **純 Python 腳本** | 前瞻績效評估（第 4 階段）、Tiger 同步、交易日誌 | — |

**必須採用確定性程式的計算 [判斷]**：
- 估值倍數、TTM、PIT 版本選擇、百分位、財務比率、情境估值與 FCF 橋；
- 報酬、波動、回撤、相對強弱；
- 單位與幣別換算、期間對齊；
- 組合權重、集中度、換手、硬風險限制；
- 前瞻報酬與命中率統計。

**研究結果的整合 [判斷]**：
- 主執行緒逐條處置 Skeptic 的挑戰（接受 / 部分接受 / 拒絕 / 無法判斷），並說明對結論的影響。
- 禁止投票與平均。

**資料品質的處理**：
- 時效：工具回傳 `as_of`。
- 衝突：保留雙方，由 Agent 說明。
- 缺口：在 Skill 中規定四類原因。
- PIT：工具層統一用截止點過濾。

---

## D/E. 完整 Roadmap（各階段交付與驗收）

每個階段分開兩類驗收：「功能驗收」看功能能否用；「策略有效性」看決策是否有效，後者只在第 4 階段之後才有數據。

### 第 1 階段：單股研究端到端（兩宿主）
- **目標**：輸入一個代碼，就能在 Claude Code 與 Codex 得到可用的研究報告與 BUY/…/NO_TRADE 建議。
- **功能**：
  - MCP 核心資料：價格、SEC 財報、申報章節、Yahoo 估計與評級。
  - MCP 核心計算：倍數、TTM、比率、PE 百分位、技術統計、情境估值。
  - `save_decision`。
  - 6 份重寫的 Skills。
  - 兩宿主配置。
- **復用**：`SecClient`、`sec.parse_companyfacts`、`disclosure`、`market.collect_daily`、`yahoo_research`、`equity_valuation`、`valuation`、`market_analysis`、`company_valuation_report`、`SnapshotCache`、`provenance`。
- **交付**：
  - `product/mcp/server.py` 及資料/計算工具模組；
  - Skills；
  - `.mcp.json`、`.codex/config.toml` 段落、Skill 連結；
  - 3 份實跑報告（兩宿主）。
- **驗收（功能）**：
  - 3 檔不同類型股票，兩個宿主各跑完，每檔 15 分鐘內完成；
  - 報告中的每個數字都能對回工具輸出；
  - 沒有出現「工具有提供，卻寫成資料缺失」；
  - 決策紀錄已寫入；
  - 按 rubric 人工評分平均 ≥ 2 分（滿分 3）。
- **風險**：SEC XBRL 科目差異大；Yahoo 非官方 API 不穩；Codex 對 Skill 符號連結與 MCP 的支援方式。

### 第 2 階段：批判與綜合品質
- **目標**：透過獨立反證與更廣的背景研究降低錯誤。
- **功能**（2026-10-13 按用戶設計調整為「正向 / 反向 / CIO」三方結構）：
  - 正向研究員 advocate subagent（兩宿主）：從證據中找亮點，用 `forward_returns` 做歷史驗證，判斷是否值得博弈；
  - 反向研究員 skeptic subagent（兩宿主）：獨立首輪查證風險，並檢驗當前價格隱含的預期是否被基本面支撐（例如 10% 增長能否支撐 30 倍 P/E）；
  - CIO（主線程）：先寫初步判斷，再逐條說明如何使用正反論點（決定性 / 支持 / 僅觀察 / 駁回，含是否已被定價），用三個情景給出風險收益；NO_TRADE 必須給出轉為 BUY 的價格或條件；
  - 論證審查：由 skeptic 雙向審查 CIO 的最終判斷；
  - 宏觀與市場背景工具及 Skill；
  - 同業比較（Yahoo 候選 + 人工篩選 + 同業估值工具）；
  - 新聞/催化劑：8-K 與 EX-99.1、moomoo 官方搜索類與異動類 Skills（僅作第三方參考）。
- **復用**：`macro`、`market_context`、`peer_candidates`、`moomoo` 官方 Skills、counter-thesis/macro/industry Skill 的方法內容。
- **驗收**：
  - advocate 與 skeptic 首輪都看不到主研究結論（Claude Code 檢查傳入提示；Codex 檢查 `fork_turns="none"`）；
  - 每份報告的正反論點都有 CIO 用法與理由，論證審查意見全部被回應；
  - 與第 1 階段同樣的樣本相比，人工評分不下降，且「挑戰處置」「反向情景」兩個維度提升；
  - 兩宿主都跑過新結構；
  - 對照測試：估值相對歷史與同業偏低、增長未惡化的樣本，流程能給出 BUY 或清楚說明為何不能（排除結構性偏向 NO_TRADE）；
  - 單股耗時不超過 25 分鐘。
- **依賴**：第 1 階段。
- **風險**：反證流於形式；宏觀資料傳導到個股時過於空泛（ALB 第 6 份報告的問題）；正反結構使結論系統性偏向 NO_TRADE。

### 第 3 階段：真實組合
- **目標**：讀取真實組合，逐股研究後輸出組合層級建議。
- **功能**：
  - 持倉錄入：截圖、手工輸入、Tiger 唯讀快照，產出 Handoff v3；
  - 逐股並行（company-analyst subagent）；
  - 組合指標與風險檢查改為直接讀取 Handoff v3：支援 ETF、標示不支援的期權，移除寫死的 `FIXTURE`；
  - 組合決策：各持倉動作 + 建議權重區間 + 集中度與現金約束。
- **復用**：`intake/v3.py`、`intake/cli.py`、`intake/tiger.py`、`broker/tiger`、`deterministic/metrics.py`、`risk.py`（需改寫輸入層）、`evals/fixtures/portfolio-intake`。
- **驗收**：
  - 用你的真實組合跑完；每個持倉都有結論或明確的 NO_TRADE 原因；
  - 違反硬風險限制的建議會被標示；
  - 合成的錄入案例全部通過；
  - 總耗時與成本可接受（目標待你定）。
- **依賴**：第 1、2 階段。
- **風險**：上下文與耗時；期權持倉的處理範圍；不同宿主之間 subagent 並行的差異。

### 第 4 階段：決策紀錄與有效性評估
- **目標**：開始量化「建議是否有效」。
- **功能**：
  - 決策紀錄規範化（第 1 階段已開始寫入）；
  - 確定性評估腳本：1/3/6/12 個月前瞻報酬，相對 SPY 與行業 ETF，按動作計算命中率，並檢查信心是否校準；
  - LLM-judge 研究品質評分，使用 rubric v1；
  - 建立真實案例集（每月固定一批股票做紙上追蹤）；
  - 有限的歷史 PIT 重放：工具的 `as_of` 參數 + 只用模型訓練截止日之後的樣本。
- **復用**：`market.collect_daily`、`evals/grading/common-stock-research-rubric-v1.json`、`calibration/v1`。
- **驗收**：評估報告能自動從決策紀錄產出；至少累積 30 筆前瞻紀錄。真正的有效性結論需要數月資料，這裡只驗收「評估能力」本身。
- **依賴**：第 1 階段的決策紀錄格式。可以與第 2、3 階段並行。
- **風險**：模型已知未來事件（前視偏差），所以只有前瞻追蹤是乾淨的；樣本少，統計不顯著。

### 第 5 階段：覆蓋擴充與成本
- **功能**：
  - 內部人與 13F；
  - 期權結構與 ETF 期權；
  - 申報細分業務；
  - 研究記憶：增量快取，降低重複抓取，可能復用 `research_memory.py` 的事實版本表；
  - 觀察清單批次刷新；
  - 研報與 OpenAlex（選用）。
- **驗收**：重跑同一股票時，資料抓取次數或時間下降 ≥ 50%；新維度至少在 2 份報告中被實際引用並影響結論。
- **風險**：免費源的覆蓋上限。Moomoo OpenD 需要帳戶與本機服務，維持為選用。

### 第 6 階段：個人交易反思閉環
- **功能**：
  - 重新設計交易日誌的寫入保護，改成簡單的「私人目錄在倉庫外」檢查；
  - Tiger 成交與決策紀錄對照：你的實際操作 vs 系統建議；
  - 反思 Skill 引用決策紀錄。
- **復用**：`trading_journal/*`、`broker/tiger/analysis.py`、trading-reflection Skill。
- **驗收**：用真實帳本產出一份反思，含「與建議的偏離」分析。

### 第 7 階段：長期維護
- 用真實案例回歸集取代合成 fixture；
- 資料源失效時給出清楚的降級提示；
- 文件；
- 每季檢討評估結果並調整 Skills。
- 不建立品質門檻機制，評估結果只作為人工決策的依據。

---

## F. 下一個最值得做的：第 1 階段「單股研究端到端」

**為什麼先做 [判斷]**：它是所有後續階段的最小端到端路徑，涵蓋資料 → 計算 → 研究 → 決策 → 紀錄。它直接驗證兩個最大的未知：免費資料夠不夠用、兩個宿主的原生配置是否可行。決策紀錄從第一天開始累積，第 4 階段才有數據可評估。

**刻意不做**：subagent、組合、宏觀、Skeptic、研究記憶、准入機制、Schema 契約。

## G. 第 1 階段任務清單（建議順序）

> 新檔案的位置與名稱是建議值，實施時可微調。

**G1. 宿主可行性探針（先做，風險最高）**
- 在兩個宿主驗證：符號連結的 Skills 能否被發現；專案級 MCP stdio server 能否被載入。先用只有一個 `ping` 工具的最小 server。
- 檔案：`product/mcp/server.py`（最小版）、`.mcp.json`、`.codex/config.toml`（新增 `[mcp_servers.stock_data]`）、`.claude/skills` 與 `.agents/skills` 符號連結。
- 依賴：在 `pyproject.toml` 新增官方 `mcp` Python SDK（extra `server`），避免像舊 `mcp/research.py` 那樣手寫 JSON-RPC。[假設] 它支援 Python 3.13。
- 驗收：兩個宿主都能列出並呼叫 `ping`，也看得到一個測試 Skill。失敗則調整配置方式（例如改為複製檔案而非連結）。

**G2. 資料目錄與快取**
- `STOCK_AGENT_DATA_DIR`（預設改為倉庫內已忽略的 `.local/data`，2026-10-13 依用戶要求調整）、`STOCK_AGENT_CACHE_DIR`（預設 `.local/cache`）、`SEC_USER_AGENT`；直接用 `cache.SnapshotCache`。
- 檔案：`product/mcp/settings.py`。

**G3. 資料工具（每個工具都接受 `ticker` 與選填的 `as_of`，回傳的事實含 `source_id/as_of/retrieved_at`）**
- `get_price_history(ticker, start, end)`：沿用 `market.collect_daily`，在內部合成 v1 存取紀錄來通過准入（[假設] 只需 `status=AUTHORIZED`）；Yahoo 失敗時改用 Eastmoney。
- `get_financial_statements(ticker, period=annual|quarterly)`：`SecClient.read_company` → `sec.parse_companyfacts`，正規化為常用科目（營收、毛利、營業利益、淨利、EPS、OCF、Capex、股數、現金、債務、權益）。可參考 `archive/code/common_stock_data.py` 與舊 `collection.research_financials` 的科目選擇邏輯，**但重新撰寫精簡版**。
- `get_filing_sections(ticker, form, sections)`：`read_selected_disclosures` + `disclosure.extract_sections`，設字元上限並支援分頁。
- `get_analyst_snapshot(ticker)`：`yahoo_research.collect_quote_summary`（評級分布、EPS/營收預估、目標價、公司概況）。
- 檔案：`product/mcp/data_tools.py`。

**G4. 計算工具**
- `valuation_multiples`：`derive_current_valuation` + `derive_forward_pe`。
- `ttm`：`aggregate_ttm`、`build_pit_ttm_eps_versions`。
- `financial_ratios`：`calculate_financial_ratios`。
- `pe_history`：`build_trailing_pe_history` + `midrank_percentile`。
- `technical_stats`：`calculate_technical_statistics`，基準預設 SPY。
- `scenario_value`：`operating_scenario_value_per_share`。
- `compare_periods`：`comparable_period_change`。
- 輸入用工具回傳的數值加證據 ID，沿用既有函式的 `evidence_fact_ids` 要求。
- 檔案：`product/mcp/calc_tools.py`。

**G5. 決策紀錄**
- `save_decision(record)`：校驗必要欄位後，附加寫入 `decisions.jsonl`，並把報告存到 `reports/YYYY-MM-DD/<TICKER>.md`。
- 欄位：`ticker, decided_at, data_as_of, action, confidence(低/中/高), horizon, price_at_decision, thesis, key_evidence[], risks[], invalidation[], host, model`。
- 檔案：`product/mcp/decision_log.py`。

**G6. Skills 重寫（只保留方法，刪掉 Gate/contract 用語，描述寫明何時觸發）**
- `research-standards`：由 evidence-grounding 加上 company-research 的數字與期間規則改寫。
- `company-fundamentals`：company-research + catalyst。
- `valuation`。
- `technical-structure`。
- `investment-decision`（新）：6 個動作的定義、必答問題（核心判斷、分析期限、業務前景、價格吸引力、失效條件、重估觸發）、信心定義、NO_TRADE 規則、報告模板。
- `stock-research`（入口）：步驟清單、建議的工具調用順序、時間預算、最後呼叫 `save_decision`。
- 尚未重寫的 Skills 移到 `product/skills-pending/`，不暴露給宿主，各自在對應階段重寫：macro、industry、options、ownership、research-report、counter-thesis、portfolio-intake、tiger-trade-journal、trading-reflection。

**G7. 聚焦測試**
- 新工具模組各有離線單元測試，用錄製的回應 fixture，放在 `tests/test_stock_data_tools.py` 與 `tests/test_decision_log.py`。
- 不修舊測試。

**G8. 宿主配置與入口文件**
- 更新 `AGENTS.md` 與 `README.md`，寫明如何啟動研究；`.codex/config.toml` 的 `dev_eval` 指向已不存在的 Skill，要清掉。

**G9. 實跑驗收**
- 樣本 3 檔：
  - 一般成長股，例如 MSFT；
  - 週期或已知的失敗樣本：ALB，可與封存的報告對比；
  - 不同估值方法的類型，例如銀行 JPM。
- 兩個宿主各跑一遍，共 6 份報告。
- 我依 rubric 與第 1 階段的驗收清單逐份檢查，你做最終人工評分。

**進入第 2 階段的條件**：
- 6 份報告都完成，決策紀錄已寫入；
- 沒有重大數字或單位錯誤；
- 你對至少 4 份的評分達「可用」；
- 已記錄本階段實際遇到的資料缺口，作為第 2 與第 5 階段的輸入。

---

## H. 主要風險與待驗證假設

| # | 項目 | 類型 | 驗證方式 |
|---|---|---|---|
| 1 | Codex 與 Claude Code 是否都支援專案級 MCP 與符號連結 Skills | 假設 | G1 探針 |
| 2 | v1 存取紀錄能否繞過准入，直接呼叫 `market.collect_daily` 與 Yahoo session | 假設 | G3 第一個工具 |
| 3 | SEC XBRL 科目正規化的覆蓋率：銀行、REIT 等特殊產業 | 技術風險 | G9 用 JPM 測試 |
| 4 | Yahoo 非官方 API 被限流或改版；免費資料沒有 SLA | 技術風險 | Eastmoney 備援；工具回報明確錯誤 |
| 5 | 免費資料缺預估歷史、逐字稿、情緒、資金流，影響前瞻判斷 | 已知限制 | 在報告中明示；第 5 階段再評估 |
| 6 | LLM 讀到了資料卻不使用（ALB 的教訓） | 品質風險 | Skill 規則（未取得 ≠ 不存在）+ 驗收時人工核對 |
| 7 | 歷史回測的前視偏差：模型已知未來 | 評估風險 | 以前瞻紙上追蹤為主 |
| 8 | 決策有效性需要數月資料與足夠樣本 | 評估風險 | 第 4 階段只驗收評估能力，不宣稱策略有效 |
| 9 | 新增 `mcp` SDK 依賴的相容性 | 假設 | G1 |
| 10 | 舊 `risk.py` 接不上 Handoff v3 | 事實 | 第 3 階段改寫輸入層 |
| 11 | 交易日誌的真實寫入目前被擋住 | 事實 | 第 6 階段處理；在此之前不使用真實寫入 |

## 驗證方式（第 1 階段完成時）

- `python -m unittest tests.test_stock_data_tools tests.test_decision_log` 通過（離線）。
- 兩個宿主各自新開會話，輸入「研究 MSFT」，能看到工具調用，並輸出報告與動作建議；`$STOCK_AGENT_DATA_DIR/decisions.jsonl` 新增紀錄。
- 逐份人工核對報告中的數字是否來自工具輸出，並依 rubric 評分。

---

## 进度

第 1 阶段（2026-10-13）：
- G1 宿主探针：完成。两宿主都能通过符号链接看到 Skills；Codex 已实际调用 MCP 工具（带 `readOnlyHint` 的工具无需审批；`save_decision` 在 `.codex/config.toml` 中预先批准）。Claude Code 已识别 `.mcp.json`，项目级 MCP 需用户在交互会话中批准一次。
- G2–G5 工具：完成。`product/mcp/{settings,data_tools,calc_tools,decision_log,server}.py`，共 15 个工具，已在 MSFT/JPM/ALB 实网验证。
- G6 Skills：完成 6 份（`stock-research`、`research-standards`、`company-fundamentals`、`valuation`、`technical-structure`、`investment-decision`）。
- G7 测试：`tests/test_stock_data_tools.py` 9 项离线测试通过。
- G8 文档：完成。
- G9 实跑验收（Codex，gpt-6-luna，2026-10-12）：MSFT、ALB、JPM 均完成并保存决策记录（单股 2–6 分钟，12–25 次工具调用）。实跑中发现并修复：虚报计算来源、只读沙箱下跳过保存、PE 当前值回退到旧值、季度现金流 YTD 未差分。观察到同一股票两次运行结论不同（MSFT 首跑 BUY、修复后重跑 NO_TRADE），决策稳定性列入第 4 阶段评估。Claude Code 三个样本待运行（项目 MCP 需批准一次，或登录 `claude` CLI 后用脚本运行）。
- G9 实跑验收（Claude Code，claude-haiku-5-5，CLI 2.1.296，2026-10-13）：MSFT、ALB、JPM 均完成并保存决策（单股 2–3 分钟，约 $0.03–0.13）。实跑中发现并修复：MCP SDK 隐藏非 ToolError 异常原因（模型无法自我纠正）、`save_decision` 参数格式过松、银行 10-Q 的 MD&A 不在标准 Item 中（新增 `query` 定位，并去除 XBRL 头）。修复后重跑 MSFT/JPM 无未处理错误。
- 6 份报告（两宿主各 3 份）的路径见 `.local/runs/`，待用户人工评分。观察：多数结论为 NO_TRADE；同一股票在不同运行间动作不同（MSFT 出现过 BUY），决策稳定性留给第 4 阶段评估。
- 2026-10-13：调试运行统一用 `scripts/dev-research.sh`（Claude Code 默认 `claude-haiku-5-5`、Codex 默认 `gpt-6-luna`，可选择），产物统一放入 `.local/`；此前散落在 `/tmp` 与 `~/StockAgentData` 的验收产物已迁移到 `.local/runs/20261012T163400Z-codex-phase1-acceptance/`。
- 2026-10-13：按用户决定直接使用 moomoo 官方 Skills（搜索类 3 个、异动类 3 个，不含 OpenAPI 交易类），原样放在 `product/skills/`。第三方方向判断/情绪/异动解读只放报告“第三方观点（仅供参考）”一节，无时间戳用读取时间。异动脚本依赖 `.venv` 的 `futu-api` 与本机 OpenD；Codex 调试使用 `workspace-write`（网络开启）并允许写入 futu SDK 日志目录 `~/.com.futunn.FutuOpenD`。两宿主 MSFT 实跑均完成全部 moomoo 步骤并符合模板；同一股票两宿主结论仍不同（Codex BUY、Claude NO_TRADE）。
- 2026-10-13：数据缺口排查与修复（见 `docs/data/known-data-gaps.md`）。修复：财报新增 D&A 组件推导、EBITDA/FCF 推导行、租赁负债、优先股、少数股东权益、`InterestAndDebtExpense`；TTM 增加 `eps_diluted_approx`；新增 `list_filing_documents` 与 `get_filing_text(document=...)` 读取 8-K EX-99.1 等附件；全文搜索支持短语→关键词同段回退、总命中数与翻页、封面/目录命中后置。固有限制记录在 known-data-gaps。
- 2026-10-13：第 2 阶段实现——skeptic 子 Agent（`.claude/agents/skeptic.md`、`.codex/agents/skeptic.toml`）、`get_macro_snapshot`/`get_market_context`/`get_peer_candidates`/`get_peer_snapshot`、Skills `skeptic-review`/`macro-market-context`/`peer-comparison`，`investment-decision` 逐条处置挑战并新增同业、宏观章节；`save_decision` 校验报告必备章节。验收运行（MSFT/ALB/JPM × 两宿主）：每份 6–11 分钟；skeptic 均被启动（Claude 传入的提示只有代码、时点与中性问题；Codex `fork_turns=none`，消息正文在会话记录中加密，无法直接核对）；每份 4–10 条挑战全部处置，合计 39 条中拒绝仅 1 条；结论除 Codex MSFT 为 BUY 外均为 NO_TRADE。调试运行关闭 Codex 全局记忆。待用户与第 1 阶段报告对比评分。
- 2026-10-13：按用户设计改为“正向（advocate：亮点 + 历史验证）/ 反向（skeptic）/ CIO（主线程逐条使用正反论点 + 情景风险收益）”，论证审查改为双向审查 CIO 最终判断；新增 `forward_returns` 历史验证工具。Codex 重跑 MSFT/ALB/JPM：10–17 分钟；三份均 NO_TRADE（初步判断已是 NO_TRADE，审查未改变动作，但修正了情景口径），均给出转为 BUY 的价格/条件；发现 Codex 一轮派生使用 `fork_turns=all`，已在 Skill 中强制 `none`。

- 2026-10-13：Codex 重跑 LITE（`fork_turns=none` 生效，论证审查经 `followup_task` 发给同一 skeptic）：约 12 分钟，初步与最终均为 NO_TRADE / medium，给出约 $600 的重评价位与 BUY 条件。
- 2026-10-14：第 2 阶段正文按三方结构更新；收尾待办：Claude Code 跑新结构（LITE）、人工评分、BUY 对照测试。之后进入第 3 阶段，并行启动第 4 阶段前瞻追踪。
- 2026-10-14：Claude Code（claude-haiku-5-5）跑新结构 LITE：约 6.5 分钟，NO_TRADE / medium，与 Codex 一致；advocate、skeptic 首轮提示只含代码与中性问题，论证审查 8 条全部接受、动作未变。问题：8-K EX-99.1 未取得原文（40 次 `get_filing_text`），部分倍数手工计算，moomoo 新闻调试时 curl 临时写入 `/tmp`。
- 2026-10-14：用户人工评分（MSFT，第 1 阶段 vs 三方结构）：第 1 阶段报告基本不可用；三方结构报告批准为可用，8 个维度各 2 分（满分 3）。
- 2026-10-14：修复 Claude LITE 运行发现的 3 个问题：EX-99.1 改为 `query="Outlook"` 定位指引，并要求记缺口前回看已返回的工具结果；新增 `implied_assumption` 工具（`scenario_value` 的反向计算：价格隐含的 EV/EBIT 倍数或利润率），取代手算；调试脚本 Claude 端改用 `--permission-mode dontAsk`（原先继承用户默认 auto 模式，`--allowedTools` 不构成白名单），curl 只放行 moomoo Skill 原样格式且禁止写文件。
- 2026-10-14：两次 Claude LITE 验证：第一次 `dontAsk` 拒绝了模型浏览文件用的 `for` 循环，模型随即放弃全部 moomoo 步骤；Skill 补充三个异动脚本的完整命令与“Bash 只用于这两类命令、被拒改正后重试一次”，`ratio` 错误提示写明期间标签必须一致。第二次（约 9 分钟，$0.59）：moomoo 五项全部执行，无文件写到 `/tmp`，指引按 8-K EX-99.1 引用，隐含倍数用 `implied_assumption`；仍为手算的只有情景加权与折现（无对应工具，已标注）。同时修复：亚洲时区传入当天日期作为 `as_of` 时，因纽约仍是前一天而被判为 `AS_OF_IN_FUTURE`。结论 NO_TRADE / medium，与前两次一致。
- 2026-10-14：用户确认 ALB、JPM 的新旧报告评分与 MSFT 相同（第 1 阶段不可用；三方结构可用，各维度 2 分）。第 2 阶段人工评分完成：评分未下降，“挑战处置”“反向情景”由不可用提升到 2 分。
- 2026-10-14：BUY 对照测试（ADBE：P/E 14.2x，10 年分位 1.2%，营收 +12.9%）。两宿主均 NO_TRADE / medium。Codex 初步 BUY → 最终 NO_TRADE（中性 +20%、乐观 +95%、保守 −27%），理由为“等下一季验证 AI 变现”，且承认小仓位 BUY 可辩护；Claude 中性 +7%（倍数锚定现价），自设 15% 门槛。诊断：缺少明确的建仓门槛；把“看多证据尚未量化”当作决定性反方；BUY 条件要求价格低于保守情景，几乎不可达；Codex 违反“不能只说等下一季”。待用户决定门槛后修改 `investment-decision`。
- 2026-10-14：修复四个与门槛无关的问题（“缺少证据”不能作为决定性反方；中性情景须列出现价隐含倍数版与历史/同业倍数版；BUY 条件须 1–2 季内可达；初步 BUY 改 NO_TRADE 须有有证据的反方论点；论证审查新增对称性与可达性检查；`save_decision` 只存一次）。重跑 ADBE：两宿主初步均为 BUY，论证审查后均改为 NO_TRADE（Codex 低信心、Claude 中信心），理由都是审查认为倍数回升“缺乏依据”，中性情景退回现价隐含倍数后上行约 0–12%。BUY 条件已可达（约 $190–220 加 1–2 季内可观察的事件）。观察：所有运行中论证审查只出现过 BUY→NO_TRADE，从未反向。
- 2026-10-14：advocate 与 skeptic 同时做论证审查后重跑 ADBE：两宿主仍为初步 BUY → 最终 NO_TRADE / medium。Claude 的改判依据已有损害证据（ARR 增速 11.2% 低于收入、GAAP 利润率同比下降）；Codex 仍靠审查后加入的无依据压力情景（25% 利润率、6x）。
- 2026-10-14：历史回放（用户选择：只做 LLM 案例复盘，样本取赢家/输家/随机对照，按季度多期）。新增：MCP 回放模式（`STOCK_AGENT_REPLAY_AS_OF`：时点工具固定在该日、只有当前数据的工具拒绝）；`dev-research.sh --as-of`（Claude 禁 Bash、Codex 关沙箱网络）；`scripts/select-replay-cases.py` 与 82 只大盘股候选池（`evals/replay/universe.txt`，有幸存者偏差）；`scripts/replay-batch.sh`；`case-review` Skill；stock-research 回放规则。2024-01 至 2025-10 共 8 期样本已选出（`evals/replay/cases/`）。冒烟测试 LIN（2024-01，对照组）：回放报告无未来信息，复盘写入 `evals/replay/reviews/`。
- 2026-10-14：8 期历史回放完成（72 样本，Codex）：71 个 NO_TRADE、1 个 BUY（ADBE 2025-07，输家），赢家/输家/对照三组没有区分。复盘归纳的问题：基准情景低于已披露经营轨迹；高估值压过已实现的加速；“价格回落再评估”的 BUY 条件对赢家几乎从不触发、对输家经常触发（逆向选择）；回放价格按今天拆股调整、与 SEC 当时口径不一致。过去 12 个月动量与之后表现无关（秩相关 0.01）。汇总见 `evals/replay/summary-2024Q1-2025Q4.md`。
- 2026-10-15/16：历史回放第二轮。补齐历史数据（宏观改用 Treasury/FRED/FOMC 并按发布日还原；SEC 历史分页与 XBRL 申报日期；Form 4 内部人；18 家知名基金 13F；众议院 PTR 议员交易与历史胜率；GDELT 新闻标题）。2024 学习组 v2：3 BUY（1 对 2 错）。10 条教训清单（规则与证据分离，防止检验泄露）；第 10 条按用户意见改为“先看这个人的历史记录”，议员胜率排行见 `evals/replay/congress-leaderboard-2025-01-01.md`（全体买入中位跑输 SPY 4%，Pelosi +7.5%）。2025 检验组（清单版）36 个全部 NO_TRADE。按用户决定改为：情景主观概率与概率加权期望回报、下行须有触发证据、BUY 条件不设价格上限、试探仓位、教训对照为必备章节。最终检验（2025-10，9 样本）：MU 给出试探仓位 BUY（之后 +475%），其余 NO_TRADE，无错误 BUY。
