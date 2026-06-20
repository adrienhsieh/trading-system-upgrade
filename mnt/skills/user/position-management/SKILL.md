---
name: position-management
description: 管理持倉記錄：新增、查看、刪除。當使用者說「新增持倉」、「刪除持倉」、「查看持倉」、或 Telegram 收到 /新增、/刪除、/持倉 指令時，使用此 Skill。
---

# 持倉管理 Skill

## 觸發情境

- Telegram 指令：`/持倉`、`/新增`、`/刪除`
- 對話：「幫我新增一筆持倉」、「刪除 2330」、「我的持倉狀況」

---

## 架構對應

```
/持倉  → TelegramBot._cmd_positions()     # trading/telegram/bot.py
/新增  → TelegramBot._cmd_add(args)        # trading/telegram/bot.py
/刪除  → TelegramBot._cmd_delete(args)     # trading/telegram/bot.py
          ├─ PositionManager.load_all()    # trading/positions.py
          ├─ PositionManager.create()
          ├─ PositionManager.delete()
          └─ yfinance.Ticker (現價查詢)
```

---

## 執行步驟

### /持倉

1. 呼叫 `PositionManager.load_all()` 取得所有持倉
2. 以 `yfinance.Ticker("{code}.TW").history(period="2d")` 取得現價
3. 計算浮動損益 `(現價 - 進場價) * 股數`
4. 格式化輸出每筆持倉：代號、名稱、現價、損益%、狀態

輸出範例：
```
📊 *持倉總覽*
━━━━━━━━━━━━━━━━━━━━
1. 台積電 2330
   進場 900 ｜ 現價 `920` (+2.22%)
   浮盈 +22,000 元 ｜ 狀態：active
   停損 850 ｜ 目標 1050
```

---

### /新增

格式：`/新增 代號 名稱 進場價 停損價 股數 [目標價]`

範例：`/新增 2330 台積電 900 850 1000 1050`

| 參數 | 說明 | 必填 |
|------|------|------|
| 代號 | 4 位數股票代號 | ✅ |
| 名稱 | 股票名稱 | ✅ |
| 進場價 | 買入價格 | ✅ |
| 停損價 | 停損觸發價 | ✅ |
| 股數 | 買入股數 | ✅ |
| 目標價 | 獲利目標（可選） | ❌ |

---

### /刪除

格式：`/刪除 代號`

範例：`/刪除 2330`

- 會先查詢是否有該代號的 active 持倉
- 找到後呼叫 `PositionManager.delete(id)` 刪除

---

## 錯誤處理

| 狀況 | 回傳訊息 |
|------|----------|
| 無持倉 | `📭 目前無持倉` |
| 格式錯誤 | `格式：/新增 代號 名稱 進場 停損 股數 [目標]` |
| 找不到代號 | `❌ 找不到持倉代號 XXXX` |

---

## 實作位置

| 方法 | 檔案 |
|------|------|
| `TelegramBot._cmd_positions()` | `trading/telegram/bot.py` |
| `TelegramBot._cmd_add()` | `trading/telegram/bot.py` |
| `TelegramBot._cmd_delete()` | `trading/telegram/bot.py` |
| `PositionManager.create()` | `trading/positions.py` |
| `PositionManager.delete()` | `trading/positions.py` |
