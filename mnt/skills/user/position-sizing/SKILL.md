---
name: position-sizing
description: 根據資金、風險比例、進場價與停損價計算建議股數。當使用者說「計算股數」、「買多少股」、「部位計算」或 Telegram 收到 /計算 指令時，使用此 Skill。
---

# 部位計算 Skill

## 觸發情境

- Telegram 指令：`/計算 2330 920 880`
- 對話：「台積電進場 920 停損 880，我應該買多少股？」

---

## 架構對應

```
/計算 → TelegramBot._cmd_sizing(args)
          └─ 使用 ConfigManager.load() 取得 total_capital 與 risk_pct
               └─ IndicatorEngine.calc_entry_params()  # trading/indicators.py
```

---

## 執行步驟

### Step 1 — 解析參數

格式：`/計算 代號 進場價 停損價`

| 參數 | 說明 | 必填 |
|------|------|------|
| 代號 | 4 位數股票代號 | ✅ |
| 進場價 | 計畫買入價格 | ✅ |
| 停損價 | 停損觸發價格 | ✅ |

若未提供參數，回傳說明：
```
用法：/計算 代號 進場價 停損價
範例：/計算 2330 920 880
```

### Step 2 — 計算邏輯

```python
risk_amount = total_capital * risk_pct / 100
risk_per_share = entry - stop
shares = int(risk_amount / risk_per_share / 1000) * 1000  # 取整張
total_cost = shares * entry
total_risk  = shares * risk_per_share
target = entry + (entry - stop) * 2  # 2:1 風報比
```

---

## 輸出格式

```
📐 *部位計算：2330*
━━━━━━━━━━━━━━━━━━━━
資金：1,000,000 元 ｜ 風險：2.00%

  進場價  `920`
  停損價  `880`（每股風險 40 元）
  目標價  `1,000`（2:1 風報比）

  建議股數  `500` 股（0.5 張）
  曝險金額  `20,000` 元（2.00%）
  建倉成本  `460,000` 元
━━━━━━━━━━━━━━━━━━━━
⚠️ 僅供計算參考，非投資建議
```

---

## 錯誤處理

| 狀況 | 回傳訊息 |
|------|----------|
| 停損 >= 進場 | `❌ 停損價必須低於進場價` |
| 非數字價格 | `❌ 請輸入有效的價格數字` |
| 缺少參數 | 顯示用法說明 |

---

## 實作位置

| 方法 | 檔案 |
|------|------|
| `TelegramBot._cmd_sizing()` | `trading/telegram/bot.py` |
| `TelegramBot._sizing_help()` | `trading/telegram/bot.py` |
| `IndicatorEngine.calc_entry_params()` | `trading/indicators.py` |
| `ConfigManager.risk_pct` | `trading/config.py` |
