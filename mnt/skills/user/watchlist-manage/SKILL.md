---
name: watchlist-manage
description: 管理候選掃描清單：查看、新增、移除股票代號。當使用者說「加入觀察清單」、「移除清單」、「清單有哪些」或 Telegram 收到 /清單、/加入、/移除 指令時，使用此 Skill。
---

# 候選清單管理 Skill

## 觸發情境

- Telegram 指令：`/清單`、`/加入`、`/移除`
- 對話：「把 2330 加到掃描清單」、「移除 2317」、「候選清單有哪些」

---

## 架構對應

```
/清單 → TelegramBot._cmd_watchlist_show()
/加入 → TelegramBot._cmd_watchlist_add(args)
/移除 → TelegramBot._cmd_watchlist_remove(args)
          ├─ ConfigManager.load()          # trading/config.py
          ├─ ConfigManager.save()
          └─ StockScanner.get_stock_map()  # 取得股票名稱
```

---

## 執行步驟

### /清單

1. 呼叫 `ConfigManager.load()` 讀取 `scan_candidates`
2. 呼叫 `StockScanner.get_stock_map()` 取得名稱對照
3. 格式化輸出清單

輸出範例：
```
📋 *候選清單*（共 3 檔）
━━━━━━━━━━━━━━━━━━━━
  2330 台積電
  2317 鴻海
  2454 聯發科
━━━━━━━━━━━━━━━━━━━━
使用 /掃描 一次分析所有候選股
```

---

### /加入

格式：`/加入 代號 [代號2 ...]`

範例：`/加入 2330 2317 2454`

- 每個代號必須是 4 位數字
- 已在清單中的代號會提示「已存在」
- 非 4 位數的代號會提示格式錯誤

輸出範例：
```
✅ 已加入 2 個代號，清單共 5 檔
新增：2330、2317
略過（已在清單）：2454
```

---

### /移除

格式：`/移除 代號 [代號2 ...]`

範例：`/移除 2330`

- 不在清單中的代號會提示「不在清單中」

輸出範例：
```
✅ 已移除 1 個代號，清單剩 4 檔
移除：2330
不在清單：9999
```

---

## 實作位置

| 方法 | 檔案 |
|------|------|
| `TelegramBot._cmd_watchlist_show()` | `trading/telegram/bot.py` |
| `TelegramBot._cmd_watchlist_add()` | `trading/telegram/bot.py` |
| `TelegramBot._cmd_watchlist_remove()` | `trading/telegram/bot.py` |
| `ConfigManager.update()` | `trading/config.py` |
