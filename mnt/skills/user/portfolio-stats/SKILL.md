---
name: portfolio-stats
description: 顯示所有持倉的損益統計，包含浮動損益、最佳/最差持倉。當使用者說「績效如何」、「我的損益」、「統計持倉」或 Telegram 收到 /績效 指令時，使用此 Skill。
---

# 持倉績效統計 Skill

## 觸發情境

- Telegram 指令：`/績效`
- 對話：「我的持倉績效怎樣？」、「目前浮動損益多少？」

---

## 架構對應

```
/績效 → TelegramBot._cmd_stats()
          ├─ PositionManager.load_all()   # trading/positions.py
          └─ yfinance.Ticker 批次取得現價
```

---

## 計算邏輯

```python
for each active position:
    current_price = yf.Ticker(f"{code}.TW").history(period="2d")["Close"].iloc[-1]
    pnl = (current_price - entry) * shares
    pnl_pct = (current_price - entry) / entry * 100

total_pnl = sum(all pnl)
best_pos  = max by pnl_pct
worst_pos = min by pnl_pct
```

---

## 輸出格式

```
📊 *持倉績效統計*
━━━━━━━━━━━━━━━━━━━━
持倉數：3 筆（active）

  2330 台積電   920.0  +22,000（+2.22%）
  2317 鴻海      93.5   -1,000（-1.00%）
  2454 聯發科  1,050.0  +15,000（+1.50%）

━━━━━━━━━━━━━━━━━━━━
總浮動損益：+36,000 元
🏆 最佳：台積電 2330（+2.22%）
📉 最差：鴻海 2317（-1.00%）
```

---

## 錯誤處理

| 狀況 | 回傳訊息 |
|------|----------|
| 無持倉 | `📭 目前無持倉` |
| 無法取得現價 | 顯示「N/A」並繼續統計其他持倉 |

---

## 實作位置

| 方法 | 檔案 |
|------|------|
| `TelegramBot._cmd_stats()` | `trading/telegram/bot.py` |
| `PositionManager.load_all()` | `trading/positions.py` |
