---
name: market-filter
description: 快查台股大盤濾網狀態（是否站上 20EMA），並顯示美股概況。當使用者說「濾網狀態」、「大盤有沒有站上均線」或 Telegram 收到 /濾網 指令時，使用此 Skill。
---

# 大盤濾網 Skill

## 觸發情境

- Telegram 指令：`/濾網`
- 對話：「台股現在站上 20EMA 嗎？」、「目前濾網狀況」

---

## 架構對應

```
/濾網 → TelegramBot._cmd_filter()
          └─ MarketService.get_data()  # trading/market.py
```

---

## 核心概念

「大盤濾網」是趨勢跟隨交易的基礎過濾條件：
- ✅ 台股站上 20EMA → 市場趨勢偏多，可積極找買點
- ❌ 台股低於 20EMA → 市場趨勢偏空，謹慎或觀望

---

## 輸出格式

```
🔎 *大盤濾網*
━━━━━━━━━━━━━━━━━━━━
台股加權指數
  現值   `19,850`
  20EMA  `19,200`

✅ 站上 20EMA（多頭趨勢）
→ 市場偏多，可積極找進場機會

🌐 美股參考
  NASDAQ  `18,234`  +0.45%
  S&P500  `5,120`   -0.12%
━━━━━━━━━━━━━━━━━━━━
```

或（空頭時）：

```
❌ 低於 20EMA（空頭趨勢）
→ 市場偏空，建議觀望或謹慎操作
```

---

## 與掃描的關係

- `/掃描` 在執行前會自動顯示濾網狀態
- 大盤低於 EMA20 時，掃描結果僅供參考，建議謹慎
- `IndicatorEngine.compute()` 中的 `ema_arrangement` 信號同樣要求個股站上均線

---

## 實作位置

| 方法 | 檔案 |
|------|------|
| `TelegramBot._cmd_filter()` | `trading/telegram/bot.py` |
| `MarketService.get_data()` | `trading/market.py` |
