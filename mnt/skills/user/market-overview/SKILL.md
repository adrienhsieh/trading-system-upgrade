---
name: market-overview
description: 查看大盤狀況：台股 EMA20、美股指數、匯率。當使用者說「大盤怎樣」、「美股如何」、「現在市場」或 Telegram 收到 /大盤 指令時，使用此 Skill。
---

# 大盤總覽 Skill

## 觸發情境

- Telegram 指令：`/大盤`
- 對話：「大盤怎麼樣？」、「美股昨天漲跌？」

---

## 架構對應

```
/大盤 → TelegramBot._cmd_market()
          └─ MarketService.get_data()      # trading/market.py
               └─ yfinance（^TWII, ^IXIC, ^GSPC, USDTWD=X）
```

`MarketService` 有 5 分鐘快取（TTL=300），背景執行緒每 5 分鐘自動刷新。

---

## 輸出格式

```
📈 *大盤總覽*
━━━━━━━━━━━━━━━━━━━━
🇹🇼 台股加權指數
  現值   `19,850`
  20EMA  `19,200`  ✅ 站上均線
  日漲跌  +0.82%

🇺🇸 美股（昨收）
  NASDAQ  `18,234`  +0.45%
  S&P500  `5,120`   -0.12%

💱 匯率
  USD/TWD  `31.85`
━━━━━━━━━━━━━━━━━━━━
```

---

## 關鍵欄位說明

| 欄位 | 說明 |
|------|------|
| `market_above_ema20` | 台股是否站上 20EMA（True/False） |
| `ema20_tw` | 台股加權指數 20 日 EMA 值 |
| `nasdaq.price` | NASDAQ 最新收盤價 |
| `nasdaq.change_pct` | NASDAQ 日漲跌幅 % |
| `sp500.price` | S&P500 最新收盤價 |
| `sp500.change_pct` | S&P500 日漲跌幅 % |

---

## 實作位置

| 方法 | 檔案 |
|------|------|
| `TelegramBot._cmd_market()` | `trading/telegram/bot.py` |
| `MarketService.get_data()` | `trading/market.py` |
| `MarketService.refresh()` | `trading/market.py` |
