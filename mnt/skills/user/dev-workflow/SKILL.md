---
name: dev-workflow
description: 完整軟體開發流程 SOP。每次開發新功能、修 Bug、重構時強制執行。確保需求明確、介面一致、測試通過、commit 規範。
---

# 開發流程 SOP

> 適用場景：新增功能、修 Bug、重構、新增策略、新增 API 端點

---

## Phase 1 — 需求確認

在動任何程式碼之前，完成以下確認清單：

```
需求確認 Check-list
□ 功能目標是什麼？（一句話描述）
□ 輸入是什麼？（使用者操作 / API 呼叫 / 排程觸發）
□ 輸出是什麼？（UI 變化 / API 回應 / Telegram 訊息）
□ 影響哪些現有模組？（列出檔案名稱）
□ 需要新增還是修改 API 端點？
□ 需要修改資料庫 schema 嗎？（positions.db）
□ 需要新增前端 Tab / Modal / 元件嗎？
□ 需要新增 Telegram 指令嗎？
□ 有無向下相容問題？（舊資料、舊 API 呼叫）
□ 預估影響的測試檔？
```

□ 此功能需要 Telegram 也能使用嗎？（參考 /feature-parity 對照表）

**若任一項目模糊 → 先向使用者釐清，再繼續。**

---

## Phase 2 — 介面設計

在實作前，明訂所有對外介面（API / 類別方法 / 函式簽名）：

### 2-1 後端 API（若有新增/修改）

```
端點：  METHOD /api/<路徑>
輸入：  JSON body / query param（列出每個欄位與型別）
輸出：  {"ok": bool, ...}（列出每個欄位與型別）
錯誤：  4xx 狀況說明
衝突檢查：
  □ 路徑是否與 app.py 現有路由重複？
  □ 回應格式是否與同類端點一致（例如 /api/scan 的格式）？
```

### 2-2 Python 模組（若新增類別/方法）

```
class/function 名稱：
參數（含型別與預設值）：
回傳值（型別與結構）：
衝突檢查：
  □ 方法名稱是否與同模組其他方法重複？
  □ 若修改既有方法簽名 → 確認所有呼叫端已更新
  □ 向下相容 wrapper 是否需要保留？
```

### 2-3 前端介面（若有 UI 新增/修改）

```
新增元件：Tab / Modal / Card / Chart
觸發方式：按鈕 / Tab 切換 / 頁面載入
呼叫 API：哪個端點？
衝突檢查：
  □ DOM id 是否與現有 id 重複？
  □ JavaScript 全域變數/函式名稱是否衝突？
  □ CSS class 是否干擾 Tabler 或現有 class？
```

### 2-4 策略（若新增策略）

```
策略名稱（英文 key）：
繼承 BaseStrategy，實作：
  □ compute(df) → dict（確認回傳 signals / score）
  □ calc_entry_params(ind, capital, risk_pct) → dict
  □ signal_labels dict
  □ min_bars 設定合理
  □ 登錄至 trading/strategies/__init__.py REGISTRY
  □ 更新 /api/scan、/api/analyze 的路由說明
```

---

## Phase 3 — 實作

遵守以下原則：

| 原則 | 說明 |
|------|------|
| 單一責任 | 每個方法只做一件事 |
| 最小改動 | 只改需求要求的部分，不順便重構 |
| 不引入安全漏洞 | 不直接將使用者輸入拼入 SQL / shell / HTML |
| 不假設資料存在 | 所有外部資料（yfinance / API）需處理 None / 例外 |
| 先讀再改 | 修改檔案前必須先 Read |

**實作順序建議：**
```
後端模組（trading/）
  ↓
Flask 路由（app.py）
  ↓
前端 HTML/JS（index.html）
  ↓
Telegram Bot（若需要）
```

---

## Phase 4 — 測試

每次實作完成後，**強制**執行：

### Step 1 — 跑所有測試

```bash
cd trading_system/
python -m unittest discover tests/ 2>&1 | grep -E "^(Ran|OK|FAIL|ERROR)"
```

### Step 2 — 新功能補測試

```
補測試 Check-list
□ 新增的 public 方法是否有對應測試？
□ 快樂路徑（正常輸入）有測試？
□ 邊界條件（None / 空列表 / 資料不足）有測試？
□ 例外情況（API 失敗 / 型別錯誤）有測試？
□ 若修改了策略 → 確認 test_scanner.py 的 mock 簽名仍正確
```

**測試對應表（目前 444 tests）：**

| 測試檔 | 測試對象 | 測試數 |
|--------|---------|--------|
| `test_auth.py` | API 認證（require_auth、Security Headers） | 13 |
| `test_config.py` | ConfigManager（含 api_key） | 16 |
| `test_indicators.py` | IndicatorEngine + OHLCV 新鮮度 | 48 |
| `test_market.py` | MarketService | 17 |
| `test_news.py` | NewsAggregator（含 XXE） | 18 |
| `test_positions.py` | PositionManager | 30 |
| `test_scanner.py` | StockScanner | 27 |
| `test_telegram_bot.py` | TelegramBot | 73 |
| `test_scheduler.py` | TradingScheduler | 16 |
| `test_backtest.py` | BacktestEngine | 35 |
| `test_intelligence.py` | IntelligenceDaemon + GroqClient | 28 |
| `test_ohlcv_db.py` | OHLCVDatabase | 15 |
| `test_ohlcv_daemon.py` | OHLCVDaemon | 8 |
| `test_coverage.py` | CoverageReader | 15 |
| `test_strategy_trend.py` | TrendStrategy | 25 |
| `test_strategy_ict.py` | ICTStrategy | 23 |
| `test_strategy_fundamental.py` | FundamentalStrategy | 22 |
| `test_integration.py` | 跨模組整合（Backtest / Position / Scanner） | 15 |

> ⚠️ **不允許在測試失敗的狀態下繼續。**

---

## Phase 5 — 自我審查

提交前快速審查：

```
Code Review Check-list
□ 沒有 print() 調試殘留（除 [ClassName] 格式的 log）
□ 沒有 TODO / FIXME 未處理
□ 沒有硬編碼的 token / 密碼
□ API 回應格式與同類端點一致
□ 前端有錯誤處理（catch / toast 提示）
□ 新增的檔案已加入 git（未被 .gitignore 誤排除）
□ config.json / positions.db / .env 沒有被加入 git
```

---

## Phase 6 — Commit

使用語義化 commit message：

```
格式：
<type>: <summary>

[body — 說明 why，不是 what]

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

| type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修 Bug |
| `refactor` | 重構（不改行為） |
| `test` | 新增/修改測試 |
| `docs` | 文件、SKILL.md |
| `style` | 純 UI/CSS 調整 |
| `chore` | 依賴、設定更新 |

```bash
git add <具體檔案>        # 不使用 git add -A
git commit -m "..."
git push
```

> ⚠️ **不允許在測試失敗的狀態下 commit。**

---

## 完整流程圖

```
需求確認（Phase 1）
  ↓
介面設計（Phase 2）—— 有衝突? → 重新設計
  ↓
實作（Phase 3）
  ↓
跑測試（Phase 4）—— 有失敗? → 修復 → 重跑
  ↓
自我審查（Phase 5）—— 有問題? → 修復
  ↓
Commit & Push（Phase 6）
```

---

## 常見衝突類型與解法

| 衝突類型 | 症狀 | 解法 |
|----------|------|------|
| 策略方法簽名變更 | test_scanner.py fake_analyze 缺參數 | 更新 mock 函式加入新參數 |
| 新增 API 路由 | 與現有路由 path 相同 | 改用不同路徑或 HTTP method |
| format_for_api 欄位變更 | 前端 `s.xxx` 讀到 undefined | 同步更新 renderScan() |
| DOM id 重複 | JS 操作錯誤元素 | grep 確認 id 唯一性 |
| CSS class 衝突 | 樣式被 Tabler 覆蓋 | 加 `!important` 或提高 specificity |
| 策略未登錄 REGISTRY | `/api/scan?strategy=xxx` 回 400 | 在 strategies/__init__.py 加入 |
