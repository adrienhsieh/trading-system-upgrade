---
name: ict-analysis
description: ICT 策略個股分析或掃描。當使用者說「ICT 分析 2330」、「用 ICT 看 XXXX」或 Telegram 收到 /ICT、/掃描ICT 指令時，使用此 Skill。計算 6 個 ICT 信號並給出進場建議。
---

# ICT 策略分析 Skill

## 觸發情境

- Telegram 指令：`/ICT 2330`
- Telegram 指令：`/掃描ICT`（掃描候選清單）
- 對話：「幫我用 ICT 看一下 2330」

---

## 架構對應

```
/ICT 2330
  └─ TelegramBot._cmd_analyze_ict("2330")   # trading/telegram/bot.py
       ├─ StockScanner.analyze_one_ict()     # trading/scanner.py
       │    ├─ IndicatorEngine.fetch_ohlcv()  # trading/indicators.py
       │    ├─ IndicatorEngine.compute_ict()
       │    └─ IndicatorEngine.calc_entry_params_ict()
       └─ 格式化並回傳 Markdown 字串

/掃描ICT
  └─ TelegramBot._cmd_scan_ict()
       └─ StockScanner.run_scan_ict()
```

---

## ICT 六大信號

| 信號 | 說明 | 計算方式 |
|------|------|---------|
| `bullish_ob` | 多頭 Order Block | 近 30 根內，最後一根跌棒後有突破，且現價站上該 OB 高點 |
| `fvg_present` | Fair Value Gap | 近 15 根內存在 3 棒跳空（candle[i-2].high < candle[i].low），且未被回填 |
| `bos` | Break of Structure | 收盤突破近 5–25 根（不含最後 2 根）的最高點 |
| `liquidity_sweep` | 流動性掃除後反轉 | 近 5 根內曾跌破前段擺動低點，但最新收盤已收回低點上方 |
| `discount_zone` | 折扣區 | 現價 < 近 20 根區間的中點（均衡價），適合買進 |
| `ote_zone` | OTE 回檔區 | 在近期擺動低→高的 61.8%–78.6% Fibonacci 回檔區間內 |

---

## 進場建議門檻

| 得分 | 結論 |
|------|------|
| 5–6 分 | ✅ ICT 強烈信號，可考慮進場 |
| 3–4 分 | 🟡 ICT 部分符合，等待確認 |
| 0–2 分 | ❌ ICT 條件不足，暫不進場 |

---

## 進場參數計算（calc_entry_params_ict）

```python
entry    = 現收盤價
stop     = OB 低點 * 0.99（若無 OB 則用區間低點 * 0.99）
target   = 近期結構高點（若無則用 entry + risk_per * 2）
shares   = (capital * risk_pct / 100) / risk_per
```

---

## 輸出格式

```
🧠 *ICT 分析：2330 台積電*
━━━━━━━━━━━━━━━━━━━━
📊 *價格結構*
  收盤價    `1810.0`
  區間高點  `1880.0`
  區間低點  `1750.0`
  均衡價    `1815.0`
  OB 區間   `1760.0` – `1790.0`
  FVG 區間  `1800.0` – `1820.0`
  OTE 區間  `1788.0` – `1768.0`
  結構高點  `1875.0`
━━━━━━━━━━━━━━━━━━━━
✅ 通過信號（4/6）
  ✓ Fair Value Gap（不平衡）
  ✓ Break of Structure
  ✓ 折扣區（低於均衡價）
  ✓ OTE 回檔區（61.8–78.6%）
❌ 未通過
  ✗ 多頭 Order Block
  ✗ 流動性掃除後反轉
━━━━━━━━━━━━━━━━━━━━
📋 *進場參數*（資金 4,529,594 元 ｜ 風險 2%）
  進場價  `1810.0`
  停損價  `1732.5`
  目標價  `1875.0`
  建議股數 `1,162` 股
  曝險金額 `90,635` 元
━━━━━━━━━━━━━━━━━━━━
🟡 *ICT 部分符合，等待確認*
⚠️ 技術指標僅供參考，非投資建議
```

---

## 與趨勢策略的差異

| 維度 | 趨勢策略 | ICT 策略 |
|------|-------------|---------|
| 核心邏輯 | 均線多頭排列 + ADX + MACD | 機構訂單流 + 價格結構 |
| 進場時機 | 趨勢延伸買進 | 回檔至 OB/FVG/OTE 買進 |
| 停損依據 | 擺動低點 + ATR | OB 低點或區間低點 |
| 目標依據 | 2:1 風報比 | 結構高點 |
| 所需資料量 | 最少 65 根 | 最少 30 根 |

---

## 實作位置

| 方法 | 檔案 |
|------|------|
| `TelegramBot._cmd_analyze_ict()` | `trading/telegram/bot.py` |
| `TelegramBot._cmd_scan_ict()` | `trading/telegram/bot.py` |
| `StockScanner.analyze_one_ict()` | `trading/scanner.py` |
| `StockScanner.run_scan_ict()` | `trading/scanner.py` |
| `IndicatorEngine.compute_ict()` | `trading/indicators.py` |
| `IndicatorEngine.calc_entry_params_ict()` | `trading/indicators.py` |
