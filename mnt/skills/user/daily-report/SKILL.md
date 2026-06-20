---
name: daily-report
description: 產生盤前早報或收盤報告，推播持倉技術警示。當使用者說「今天報告」、「盤前摘要」、或 Telegram 收到 /報告、/測試早報、/測試收盤 指令時，使用此 Skill。排程也會在 08:30 / 13:30 自動推播。
---

# 每日報告 Skill

## 觸發情境

- Telegram 指令：`/報告`、`/測試早報`、`/測試收盤`
- 自動排程：08:30 盤前早報、13:30 收盤報告
- 對話：「幫我看今天的報告」

---

## 架構對應

```
/報告      → TelegramBot._cmd_report()
/測試早報  → TelegramBot.build_morning_report()
/測試收盤  → TelegramBot.build_close_report()

TradingScheduler._loop()               # trading/telegram/scheduler.py
  ├─ 08:30 → bot.build_morning_report() + push_to_all()
  └─ 13:30 → bot.build_close_report()  + push_to_all()
```

---

## 盤前早報（build_morning_report）

包含：
1. 大盤狀態（台股 EMA20 是否站穩）
2. 美股昨日收盤（NASDAQ、S&P500）
3. 當前持倉列表（代號、名稱、進場價、停損價）

輸出範例：
```
🌅 *盤前早報*
━━━━━━━━━━━━━━━━━━━━
📊 大盤狀況
  台股 20EMA：19,200  ✅ 站上均線
  NASDAQ  18,234 (+0.45%)
  S&P500   5,120 (-0.12%)

📋 持倉列表（2 筆）
  2330 台積電｜進場 900｜停損 850
  2317 鴻海  ｜進場 100｜停損 92
━━━━━━━━━━━━━━━━━━━━
祝交易順利！
```

---

## 收盤報告（build_close_report）

包含：
1. 每筆持倉的現價、日漲跌、浮動損益
2. 停損或目標接近警示

輸出範例：
```
🌆 *收盤報告*
━━━━━━━━━━━━━━━━━━━━
📊 持倉損益
  2330 台積電  920.0 (+2.22%)  浮盈 +22,000
  ⚠️ 接近停損：2317 鴻海  93.0 (停損 92)
━━━━━━━━━━━━━━━━━━━━
```

---

## 實作位置

| 方法 | 檔案 |
|------|------|
| `TelegramBot._cmd_report()` | `trading/telegram/bot.py` |
| `TelegramBot.build_morning_report()` | `trading/telegram/bot.py` |
| `TelegramBot.build_close_report()` | `trading/telegram/bot.py` |
| `TradingScheduler._loop()` | `trading/telegram/scheduler.py` |
