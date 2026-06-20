# 戰情指揮中心 — Claude 工作規則

## 專案簡介

台股技術分析交易管理系統。核心套件在 `trading/`，Flask API 在 `app.py`，前端在 `index.html`，Telegram Bot 在 `trading/telegram/`。

策略識別鍵：`trend`（趨勢策略）、`ict`（ICT 策略）。REGISTRY 在 `trading/strategies/__init__.py`。

---

## 強制規則

1. **修改前先 Read**：任何檔案修改前必須先讀取當前內容。
2. **測試不得失敗**：每次實作後執行 `python -m unittest discover tests/`，不允許在紅燈狀態繼續或 commit。
3. **雙通道一致性**：新增使用者可見功能時，必須同時確認 Web 與 Telegram 是否都需要支援（參考 feature-parity SKILL）。
4. **不改 REGISTRY key**：`"trend"` / `"ict"` / `"fundamental"` 是 API 對外介面，不得更名。
5. **不 commit secrets**：`config.json` / `positions.db` / `.env` 不得進入 git。

---

## 常用指令

| 操作 | 指令 |
|------|------|
| 啟動應用程式 | `python run.py` |
| 執行所有測試 | `python -m unittest discover tests/` |
| 執行單一測試檔 | `python -m unittest tests/test_xxx.py` |
| 執行單一測試案例 | `python -m unittest tests.test_xxx.TestClass.test_method` |

---

## 架構摘要

- **`run.py`** 是唯一啟動入口：載入 `.env` → `import app` → 從 `container` 取得服務單例 → 建立 `TelegramBot` + `TradingScheduler` → `intel_daemon.start()` → `Flask.run()`
- **`app.py`**（76 行）：設定 Flask + CORS + Limiter，呼叫 `register_blueprints(app)` 掛載所有路由。不含任何路由邏輯。
- **`trading/api/`**：7 個 Blueprint 模組（positions / scan / config / backtest / market / intelligence / watchlist），各自負責對應路由群組。`auth.py` 提供 `require_auth` decorator。
- **`trading/services/container.py`**：`ServiceContainer` 全系統唯一服務容器，lazy-init + 執行緒安全。Flask Blueprint 與 Telegram Bot 均透過 `container.xxx` 存取同一份服務實例。
- **Telegram Bot** 透過 constructor injection 取得所有服務，不自行建立服務實例。
- **三個 SQLite 資料庫**：`positions.db`（持倉）、`intelligence.db`（新聞/X討論/摘要）、`ohlcv_cache.db`（K線快取）。
- **策略 REGISTRY**：`trading/strategies/__init__.py`，鍵名 `"trend"` / `"ict"` / `"fundamental"` 是 API 對外介面。新增策略繼承 `BaseStrategy` 後加入 REGISTRY。
- **詳細說明**：[docs/architecture.md](docs/architecture.md) | [docs/strategies.md](docs/strategies.md)

---

## SKILLs（自動載入）

@mnt/skills/user/dev-workflow/SKILL.md

@mnt/skills/user/feature-parity/SKILL.md

@mnt/skills/user/run-tests/SKILL.md

@mnt/skills/user/stock-analysis/SKILL.md

@mnt/skills/user/ict-analysis/SKILL.md

@mnt/skills/user/portfolio-scan/SKILL.md

@mnt/skills/user/portfolio-stats/SKILL.md

@mnt/skills/user/position-management/SKILL.md

@mnt/skills/user/position-sizing/SKILL.md

@mnt/skills/user/risk-exposure/SKILL.md

@mnt/skills/user/market-overview/SKILL.md

@mnt/skills/user/market-filter/SKILL.md

@mnt/skills/user/news-briefing/SKILL.md

@mnt/skills/user/daily-report/SKILL.md

@mnt/skills/user/watchlist-manage/SKILL.md

@.claude/skills/frontend-design/SKILL.md
