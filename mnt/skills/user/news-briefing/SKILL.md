---
name: news-briefing
description: 查看最新台股財經新聞（含連結）。當使用者說「最新新聞」、「有什麼新聞」或 Telegram 收到 /新聞 指令時，使用此 Skill。
---

# 財經新聞 Skill

## 觸發情境

- Telegram 指令：`/新聞`
- 對話：「幫我看最新新聞」、「有什麼財經消息」

---

## 架構對應

```
/新聞 → TelegramBot._cmd_news()
          └─ NewsAggregator.fetch()        # trading/news.py
               └─ concurrent RSS 抓取（requests + xml.etree）
```

---

## 新聞來源

`NewsAggregator` 預設抓取以下 RSS feeds：

| 來源 | 類型 |
|------|------|
| 鉅亨網台股 | 台股新聞 |
| Yahoo 財經台灣 | 台股新聞 |
| 工商時報 | 財經新聞 |
| 中央社財經 | 財經新聞 |

每個 feed 最多取 3–4 則，合計去重後回傳最新 10 則。

---

## 輸出格式

```
📰 *最新財經新聞*
━━━━━━━━━━━━━━━━━━━━
1. [台積電法說會公布 Q2 展望看好](https://...)
   🕐 2024-01-15 14:30

2. [Fed 維持利率不變，台幣升值](https://...)
   🕐 2024-01-15 13:00
...
━━━━━━━━━━━━━━━━━━━━
```

---

## 錯誤處理

| 狀況 | 回傳訊息 |
|------|----------|
| 所有 feed 失敗 | `⏳ 暫時無法取得新聞，請稍後再試` |
| 部分 feed 失敗 | 正常顯示成功的部分 |

---

## 實作位置

| 方法 | 檔案 |
|------|------|
| `TelegramBot._cmd_news()` | `trading/telegram/bot.py` |
| `NewsAggregator.fetch()` | `trading/news.py` |
| `NewsAggregator._parse_feed()` | `trading/news.py` |
