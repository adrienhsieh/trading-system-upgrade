---
name: stock-analysis
description: 分析台股個股是否符合進場條件。當使用者說「分析 XXXX」、「幫我看 XXXX」、「XXXX 可以進場嗎」、「XXXX 怎麼樣」、「查 XXXX」，或 Telegram 收到 /分析 指令時，使用此 Skill。會計算 6 個技術信號並給出進場建議。
---

# 台股個股進場條件分析 Skill

## 觸發情境

- Telegram 指令：`/分析 2330` 或 `/分析 2330 台積電`
- 對話：「幫我看一下 3583」、「2330 可以進場嗎？」

---

## 架構對應

本 Skill 的邏輯實作於 `trading/telegram/bot.py` 的 `TelegramBot._cmd_analyze()` 方法。

```
使用者輸入 /分析 2330
  └─ TelegramBot._handle_message()        # trading/telegram/bot.py
       └─ TelegramBot._cmd_analyze("2330")
            ├─ ConfigManager.load()        # trading/config.py
            ├─ StockScanner.analyze_one()  # trading/scanner.py
            │    ├─ IndicatorEngine.fetch_ohlcv()  # trading/indicators.py
            │    ├─ IndicatorEngine.compute()
            │    └─ IndicatorEngine.calc_entry_params()
            └─ 格式化並回傳 Markdown 字串
```

---

## 執行步驟

### Step 1 — 解析股票代號

從使用者輸入取得 4 位數股票代號（第一個參數）。
若未提供代號，回傳格式說明：

```
用法：/分析 [股票代號]
範例：/分析 2330
```

---

### Step 2 — 呼叫分析函式

```python
# trading/telegram/bot.py — TelegramBot._cmd_analyze()

cfg      = self.config_mgr.load()
capital  = cfg["total_capital"]
risk_pct = 1.0 if cfg.get("consecutive_losses", 0) >= 3 else 2.0

result = self.scanner.analyze_one(code, capital, risk_pct)
```

- `result` 為 `None` 表示資料不足（上市未滿 65 個交易日、或代號錯誤）
- `result` 包含 `ind`（指標字典）和 `params`（進場參數字典）

---

### Step 3 — 判斷進場建議

| 得分 | 結論 |
|------|------|
| 5–6 分 | ✅ 強烈符合，可考慮進場 |
| 3–4 分 | 🟡 部分符合，等待更多確認 |
| 0–2 分 | ❌ 條件不足，暫不進場 |

額外檢查：
- `ema_arrangement` 必須為 True（均線多頭排列是基本條件）
- 若 `adx < 20`：補充說明「趨勢偏弱」

---

### Step 4 — 格式化輸出

使用以下 Telegram Markdown 格式回傳：

```
🔍 *個股分析：{code} {name}*
━━━━━━━━━━━━━━━━━━━━
📊 技術指標
  收盤價  `{close}`
  20EMA   `{ema20}`
  ADX     `{adx}`   ATR `{atr}`

✅ 通過信號（{score}/6）
  {通過的信號列表，每項一行，用 ✓ 開頭}

❌ 未通過
  {未通過的信號列表，每項一行，用 ✗ 開頭}

━━━━━━━━━━━━━━━━━━━━
📋 進場參數（資金 {capital} 元 ｜ 風險 {risk_pct}%）
  進場價  `{entry}`
  停損價  `{stop}`
  目標價  `{target}`
  建議股數 `{shares}` 股（{shares//1000:.1f} 張）
  曝險金額 `{total_risk:,}` 元

━━━━━━━━━━━━━━━━━━━━
{進場建議結論}
⚠️ 技術指標僅供參考，非投資建議
```

**信號中文對照：**
- `ema_arrangement` → 均線排列（收 > EMA5 > EMA20 > EMA60）
- `slopes_up`       → 三線齊揚（三條均線同步向上）
- `adx_above_25`    → ADX > 25（趨勢強度足夠）
- `macd_positive`   → MACD 紅柱（動能向上）
- `volume_spike`    → 爆量（成交量 > 20日均量）
- `ema_crossover`   → 5 穿 20（近期黃金交叉）

---

### Step 5 — 錯誤處理

| 狀況 | 回傳訊息 |
|------|----------|
| `result` 為 None | `❌ {code} 無法分析：資料不足（上市未滿 65 日或代號錯誤）` |
| 網路錯誤 | `⏳ 分析失敗，請稍後再試` |
| 非 4 位數代號 | `❌ 請輸入正確的台股代號（4 位數字）` |

---

## Telegram Bot 整合位置

| 項目 | 檔案 | 方法 |
|------|------|------|
| 指令路由 | `trading/telegram/bot.py` | `TelegramBot._handle_message()` |
| 指令實作 | `trading/telegram/bot.py` | `TelegramBot._cmd_analyze()` |
| 指令選單 | `trading/telegram/bot.py` | `TelegramBot.setup_commands()` |
| 指標計算 | `trading/indicators.py` | `IndicatorEngine.compute()` |
| 進場參數 | `trading/indicators.py` | `IndicatorEngine.calc_entry_params()` |
| 掃描分析 | `trading/scanner.py` | `StockScanner.analyze_one()` |
