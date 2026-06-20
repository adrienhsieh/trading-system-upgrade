---
name: run-tests
description: 每次開發完成後，執行完整 unit test 並驗證是否有錯誤。當使用者說「跑測試」、「跑 unit test」、「幫我驗證」、「測試看看」，或任何新功能/重構完成後，使用此 Skill。
---

# Unit Test 驗證 Skill

## 觸發情境

- 使用者說：「跑一下測試」、「幫我驗證」、「有沒有壞掉」
- 每次新增功能、重構、修 bug 完成後**自動執行**

---

## 執行步驟

### Step 1 — 執行全部測試

```bash
cd trading_system/
.venv\Scripts\python.exe -m unittest discover tests/ 2>&1 | grep -E "^(Ran|OK|FAIL|ERROR)"
```

### Step 2 — 判斷結果

| 輸出 | 代表 |
|------|------|
| `OK` | ✅ 全部通過，可以 commit |
| `FAIL` | ❌ 有測試失敗，必須修復 |
| `ERROR` | ❌ 有執行期錯誤，必須修復 |

### Step 3 — 失敗時定位問題

```bash
python -m unittest tests/test_xxx.py -v 2>&1 | grep -A 15 "FAIL\|ERROR"
```

### Step 4 — 回報結果

成功時：
```
✅ 444 tests, 0 failures — 可以 commit
```

失敗時：
```
❌ 444 tests, 2 failures
  - TestXxx.test_yyy: AssertionError ...
  → 修復 trading/xxx.py 第 N 行
```

---

## 常見失敗原因與修復方式

| 原因 | 解法 |
|------|------|
| 新增了方法參數但測試的 mock 簽名未更新 | 更新測試的 `def fake_xxx(...)` 加上新參數 |
| 邏輯從 A 類移至 B 類，patch 對象不對 | 改 patch `B.method` 而非 `A.method` |
| 刪除了方法但測試還在呼叫 | 刪除或更新對應測試 |
| 新功能沒有測試 | 在對應 `test_xxx.py` 補充測試案例 |

---

## 測試檔案對應

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

**合計：444 個測試案例**

---

## 開發流程規範

```
實作新功能
  ↓
執行 run-tests Skill
  ↓
✅ 全部通過？ → git commit & push
❌ 有失敗？   → 修復 → 再跑一次
```

> ⚠️ 不允許在測試失敗的狀態下 commit。
