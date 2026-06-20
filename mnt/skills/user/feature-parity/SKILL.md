---
name: feature-parity
description: 確保每個新功能在 Web 與 Telegram 都可使用。新增功能時強制執行雙通道 check-list，並提供 Telegram 指令實作範本。
---

# 功能雙通道一致性 SOP

> 適用場景：新增任何使用者可見功能（分析、掃描、回測、報告等）

---

## 現有功能對照表

| 功能 | Web | Telegram | 狀態 |
|------|-----|----------|------|
| 持倉管理 | 持倉戰情 tab | `/持倉` `/新增` `/刪除` | ✅ 一致 |
| 損益 / 風險摘要 | 持倉戰情 tab | `/績效` `/風險` | ✅ 一致 |
| 持倉技術警示 | 每日分析 tab | `/報告` | ✅ 一致 |
| 趨勢策略掃描（候選清單） | 台股掃描 tab | `/掃描` | ✅ 一致 |
| 趨勢策略掃描（全市場） | 台股掃描 tab（SSE） | `/掃描全市場` | ✅ 一致 |
| 全市場掃描電子股篩選 | 台股掃描 tab（⚡ 電子股 toggle） | ❌ 無 | ⚠️ 僅 Web |
| ICT 策略掃描 | 台股掃描 tab | `/掃描ICT` | ✅ 一致 |
| 個股趨勢分析 | 台股掃描 → 個股 | `/分析 代號` | ✅ 一致 |
| 個股 ICT 分析 | 台股掃描 → 個股 | `/ICT 代號` | ✅ 一致 |
| K 線圖 | 持倉 → 📈 按鈕 | ❌ 無 | ⚠️ 僅 Web |
| 回測系統 | 回測 tab | `/回測 代號 [策略] [週期]` | ✅ 一致 |
| 大盤行情 | 市場數據（首頁） | `/大盤` | ✅ 一致 |
| 大盤濾網 | 市場數據（首頁） | `/濾網` | ✅ 一致 |
| 財經新聞 | 財經情報 tab | `/新聞` | ✅ 一致 |
| 部位計算 | 台股掃描（建議內嵌） | `/計算 代號 進場 停損` | ✅ 一致 |
| 候選清單管理 | 設定 → scan_candidates | `/清單` `/加入` `/移除` | ✅ 一致 |
| AI 新聞情緒（Groq） | 財經情報 tab → ⚡ 分析 | `/AI情報` | ✅ 一致 |
| X/Twitter 市場討論 | 財經情報 tab → X 市場討論 | `/X情報` | ✅ 一致 |
| 每日 AI 情報摘要 | 財經情報 tab → 每日情報摘要 | `/情報摘要` | ✅ 一致 |
| 觀察名單管理 | 觀察名單 tab | `/wlist` `/wladd` `/wldel` | ✅ 一致 |
| 觀察名單分析 | 觀察名單 tab → 分析 | `/wlscan` | ✅ 一致 |
| 基本面分析 | 台股掃描 → 個股 | `/fund 代號` | ✅ 一致 |
| OHLCV 本地快取管理 | `GET /api/ohlcv/stats`、`POST /api/ohlcv/update` | ❌ 無 | ⚠️ 僅 Web API（內部功能，無需 UI） |

---

## 新功能雙通道 Check-list

```
□ Web API 端點已實作（app.py）
□ Web UI 已實作（index.html）
□ Telegram 指令是否有對應需求？
    □ 是 → 完成以下全部步驟
    □ 否（純視覺/圖表功能）→ 在對照表標記「⚠️ 僅 Web」並記錄原因

Telegram 實作步驟：
□ 在 bot.py 的 BotCommand 清單加入新指令（set_my_commands）
□ 在 _dispatch() 的 elif 區塊加入路由
□ 實作對應的 _cmd_xxx() 方法（文字格式輸出）
□ 在 /說明 的長版與短版訊息加入指令說明
□ 在本 SKILL 的對照表更新狀態為 ✅
□ 在 tests/test_telegram_bot.py 新增測試
```

---

## Telegram 指令實作範本

### 純文字回報型（最常用）

```python
# 1. 在 set_my_commands() 清單加入
{"command": "xxx",  "description": "功能說明"},

# 2. 在 _dispatch() 加入路由
elif cmd == "/XXX":
    threading.Thread(
        target=lambda: self.send(chat_id, self._cmd_xxx(args)),
        daemon=True,
    ).start()

# 3. 實作方法
def _cmd_xxx(self, args: list) -> str:
    # 從 self.config_mgr / self.scanner / self.pos_mgr 取資料
    # 回傳 Markdown 格式字串
    ...
```

### 長時間運算型（需背景執行 + 進度提示）

```python
def _cmd_xxx_long(self, chat_id: str, args: list) -> None:
    self.send(chat_id, "⏳ 計算中，請稍候...")
    try:
        result = ...  # 耗時操作
        self.send(chat_id, self._fmt_xxx(result))
    except Exception as e:
        self.send(chat_id, f"❌ 失敗：{e}")
```

---

## 回測指令實作規格（已完成）

目前狀態：`✅ 一致`

### 指令設計

```
/回測 代號 [策略] [週期]
範例：
  /回測 2330
  /回測 2330 trend 2y
  /回測 2330,2454 ict 1y
```

### 輸入規則

| 參數 | 預設值 | 可選值 |
|------|--------|--------|
| 代號 | （必填）逗號分隔多檔 | 台股 4 位數字 |
| 策略 | `trend` | `trend` / `ict` |
| 週期 | `2y` | `6mo` `1y` `2y` `3y` `5y` |

### 輸出格式（單檔）

```
🔬 *回測結果 · 2330 · 趨勢策略 · 2年*
━━━━━━━━━━━━━━━━━━━━
交易次數：12 筆（8W / 4L）
勝　　率：66.7%
盈虧　比：2.84
最大回撤：5.2%
總　報酬：+18.2%（+182,400 元）
━━━━━━━━━━━━━━━━━━━━
最近 3 筆交易：
  ✅ 2024-08-12 進 185 → 出 201（+8.6%）
  ✅ 2024-06-03 進 172 → 出 189（+9.9%）
  ❌ 2024-04-15 進 168 → 出 161（-4.2%）
```

### 輸出格式（多檔比較）

```
🔬 *多檔回測比較 · 趨勢策略 · 2年*
━━━━━━━━━━━━━━━━━━━━
代號   報酬    勝率  盈虧比  回撤
2330  +18.2%  66.7%  2.84  5.2%
2454   +6.9%  44.4%  1.65  3.9%
6505   -2.1%  40.0%  0.88  8.3%
━━━━━━━━━━━━━━━━━━━━
```

### 實作位置

| 步驟 | 檔案 | 方法 |
|------|------|------|
| 路由 | `trading/telegram/bot.py` | `_dispatch()` |
| 邏輯 | `trading/telegram/bot.py` | `_cmd_backtest()` |
| 格式化（單檔） | `trading/telegram/bot.py` | `_fmt_backtest_single()` |
| 格式化（多檔） | `trading/telegram/bot.py` | `_fmt_backtest_multi()` |
| 引擎 | `trading/backtest.py` | `BacktestEngine.run()` / `run_multi()` |
| 測試 | `tests/test_telegram_bot.py` | `TestBacktestCmd` |

---

## 不適合 Telegram 的功能（⚠️ 僅 Web）

以下功能因需要視覺互動，只在 Web 實作，Telegram 不需補齊：

| 功能 | 原因 |
|------|------|
| K 線圖 | 需要 Canvas / Lightweight Charts，Telegram 無法渲染互動圖表 |
| 全市場掃描電子股篩選 | UI toggle 功能，Telegram 僅支援全市場掃描不支援動態篩選 |

> 若未來需要，可改為傳送靜態截圖（使用 matplotlib 產生圖片），但不在目前範疇內。
