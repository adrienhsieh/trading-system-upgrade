---
name: risk-exposure
description: 顯示所有持倉的風險曝露分析，包含每筆的風險金額與總資金佔比。當使用者說「風險狀況」、「曝險多少」或 Telegram 收到 /風險 指令時，使用此 Skill。
---

# 風險曝露 Skill

## 觸發情境

- Telegram 指令：`/風險`
- 對話：「我的風險狀況怎樣？」、「曝險佔多少資金？」

---

## 架構對應

```
/風險 → TelegramBot._cmd_risk()
          ├─ PositionManager.load_all()      # trading/positions.py
          └─ PositionManager.risk_summary()  # 計算各持倉風險
```

---

## 計算邏輯

每筆持倉的風險金額：
```
risk_amount = (entry - stop) * shares
```

總風險金額佔資金比：
```
total_risk_pct = sum(risk_amounts) / total_capital * 100
```

---

## 輸出格式

```
⚠️ *風險曝露分析*
━━━━━━━━━━━━━━━━━━━━
總資金：1,000,000 元

1. 台積電 2330
   進場 900 → 停損 850（-50 元/股）
   股數 1,000 → 風險 50,000 元（5.00%）

2. 鴻海 2317
   進場 103 → 停損 98（-5 元/股）
   股數 2,000 → 風險 10,000 元（1.00%）

━━━━━━━━━━━━━━━━━━━━
📊 總風險：60,000 元（6.00%）
建議單次交易風險不超過總資金 2%
```

---

## 風險警示規則

| 狀況 | 顯示 |
|------|------|
| 單筆 > 2% | ⚠️ 警示（超過建議比例） |
| 總風險 > 10% | 🚨 高風險警示 |
| 連虧 >= 3 次 | 自動降為 1% 風險模式 |

---

## 實作位置

| 方法 | 檔案 |
|------|------|
| `TelegramBot._cmd_risk()` | `trading/telegram/bot.py` |
| `PositionManager.risk_summary()` | `trading/positions.py` |
| `ConfigManager.risk_pct` | `trading/config.py` |
