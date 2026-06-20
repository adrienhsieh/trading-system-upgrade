---
name: portfolio-scan
description: 掃描候選清單或全市場，找出符合技術條件的個股。當使用者說「掃描」、「幫我找進場股」或 Telegram 收到 /掃描、/掃描全市場 指令時，使用此 Skill。
---

# 候選掃描 Skill

## 觸發情境

- Telegram 指令：`/掃描`、`/掃描全市場`
- 對話：「幫我掃描今天有哪些可以進場的股票」

---

## 架構對應

```
/掃描     → TelegramBot._cmd_scan()
/掃描全市場 → TelegramBot._cmd_scan_full()
               ├─ StockScanner.run_scan()        # trading/scanner.py
               │    ├─ StockScanner.analyze_one()
               │    └─ IndicatorEngine.compute() # trading/indicators.py
               └─ StockScanner.format_for_api()
```

---

## 執行步驟

### /掃描（自訂清單）

1. 從 `ConfigManager.load()` 讀取 `scan_candidates`
2. 若清單為空，提示用 `/加入` 新增
3. 呼叫 `StockScanner.run_scan(candidates, capital, risk_pct)` 並行分析
4. 格式化輸出符合條件的個股（score >= 3）

### /掃描全市場

1. 呼叫 `StockScanner.get_stock_map()` 取得全台上市股清單（上市 ~1079 + 上櫃 ~879）
2. 使用 SSE（Server-Sent Events）串流回傳進度（網頁端），`ThreadPoolExecutor(max_workers=2)` 避免 rate limit
3. Telegram 端分批（每批 100 檔，`max_workers=4`，批次間 2s 間隔）推播進度與結果

### ⚡ 電子股篩選（僅 Web）

Web UI 的 `⚡ 電子股` toggle 按鈕啟用後，改呼叫 `StockScanner.get_tech_stock_map()`：
- 依 TWSE `t187ap03_L` 產業別（含關鍵字：半導體、電腦、光電、通訊、電子、資訊、科技）篩選
- TPEX 股票以代號範圍（3000–3699、4900–4999、5200–5399、6200–6999）作為備援
- URL 參數：`/api/scan/full?filter=tech`

---

## 輸出格式

```
🔍 *掃描結果*（共 3 筆）
━━━━━━━━━━━━━━━━━━━━
1. 台積電 2330  ⭐ 5/6
   進場 920 ｜ 停損 880 ｜ 目標 1020
   ✓ 均線排列 ✓ ADX>25 ✓ MACD紅柱

2. 鴻海 2317  ⭐ 4/6
   進場 103 ｜ 停損 98 ｜ 目標 115
   ✓ 均線排列 ✓ 三線齊揚 ✓ 爆量
━━━━━━━━━━━━━━━━━━━━
```

---

## 候選清單管理

| 指令 | 功能 |
|------|------|
| `/清單` | 查看現有候選清單 |
| `/加入 2330 2317` | 加入代號 |
| `/移除 2330` | 移除代號 |

---

## 實作位置

| 方法 | 檔案 |
|------|------|
| `TelegramBot._cmd_scan()` | `trading/telegram/bot.py` |
| `TelegramBot._cmd_scan_full()` | `trading/telegram/bot.py` |
| `StockScanner.run_scan()` | `trading/scanner.py` |
| `StockScanner.analyze_one()` | `trading/scanner.py` |
| `StockScanner.get_stock_map()` | `trading/scanner.py` |
| `StockScanner.get_tech_stock_map()` | `trading/scanner.py` |
