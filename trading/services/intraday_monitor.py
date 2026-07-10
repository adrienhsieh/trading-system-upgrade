"""
trading/services/intraday_monitor.py — 盤中即時監控 Daemon（獨立背景作業）

🚀 高併發穩定優化防禦版：
  1. 引入多執行緒分組抓取（Thread Pool Executor），每 5 檔一組平行請求，完美應對多股監控。
  2. 2 秒極速 Timeout 機制與完整瀏覽器偽裝 Headers，防範證交所 WAF 防火牆斷線。
  3. 安全容錯數值轉換（_safe_float），優雅處理開盤前與暫停交易字串 "-"。
  4. 籌碼回填快照機制：快照生成時自動關聯 SQLite 最新法人籌碼，解決前端畫面顯示 "--" 的問題。
"""
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests

from trading.logger import get_logger

logger = get_logger("intraday_monitor")

BASE_DIR = Path(__file__).parent.parent.parent
DEFAULT_DB_PATH = BASE_DIR / "db" / "intraday_monitor.db"

MARKET_OPEN  = (9, 0)
MARKET_CLOSE = (13, 30)

TWSE_TICK_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
FINMIND_URL   = "https://api.finmindtrade.com/api/v4/data"

CHANNEL_FAILURE_THRESHOLD = 3
DEFAULT_STRATEGY_WEIGHTS  = {"trend": 40, "ict": 30, "fundamental": 30}


# ── 輔助工具函數 ───────────────────────────────────────────────

def _safe_float(val, default=0.0) -> float:
    """安全地將回傳值轉為 float，自動處理 '-', None 及千分位逗號。"""
    if val is None:
        return default
    clean_val = str(val).replace(",", "").strip()
    if clean_val == "" or clean_val == "-":
        return default
    try:
        return float(clean_val)
    except (ValueError, TypeError):
        return default


def is_market_hours(now: Optional[datetime] = None) -> bool:
    """判斷目前是否為台股盤中時間（測試環境預設回傳 True 開啟全天候監控）。"""
    return True


def compute_predicted_price(code: str, ohlcv_db, snapshot: dict, weights: dict) -> Optional[dict]:
    """結合使用者勾選的策略權重，運算「策略綜合預測價」。"""
    import pandas as pd
    from trading.strategies import REGISTRY

    if ohlcv_db is None:
        return None
    df = ohlcv_db.load(code, days=250)
    if df is None or df.empty or len(df) < 30:
        return None

    current_price = float(snapshot.get("price") or df["close"].iloc[-1])
    if current_price <= 0:
        return None

    today = date.today().isoformat()
    if str(df.index[-1])[:10] != today:
        new_row = pd.DataFrame(
            [[current_price, current_price, current_price, current_price, snapshot.get("volume", 0)]],
            columns=["open", "high", "low", "close", "volume"],
            index=pd.to_datetime([today]),
        )
        df = pd.concat([df, new_row])

    total_weight = sum(max(0, w) for w in weights.values()) or 1
    composite = 0.0
    detail: dict = {}
    atr_val = None

    for strat_name, w in weights.items():
        if w <= 0:
            continue
        strat = REGISTRY.get(strat_name)
        if strat is None:
            continue
        try:
            res = strat.compute(df, code)
        except Exception as e:
            logger.warning("策略 %s 運算失敗: %s", strat_name, e)
            res = None
        if not res:
            continue
        total_enabled = res.get("total_enabled") or 1
        ratio = res.get("score", 0) / total_enabled
        signed = 2 * ratio - 1
        composite += w * signed
        detail[strat_name] = {"score": res.get("score"), "total": total_enabled, "ratio": round(ratio, 3)}
        if atr_val is None and "atr" in res:
            atr_val = res["atr"]

    if not detail:
        return None

    composite = composite / total_weight

    if atr_val is None:
        from trading.indicators import IndicatorEngine as IE
        atr_val = float(IE._atr(df["high"], df["low"], df["close"], 14).iloc[-1])

    k = 1.0
    predicted_close = current_price * (1 + composite * k * (atr_val / current_price))
    band = 0.3 * atr_val
    predicted_open = current_price
    predicted_high = max(predicted_open, predicted_close) + band
    predicted_low  = min(predicted_open, predicted_close) - band

    return {
        "open":  round(predicted_open, 2),
        "high":  round(predicted_high, 2),
        "low":   round(predicted_low, 2),
        "close": round(predicted_close, 2),
        "composite_score": round(composite, 4),
        "detail": detail,
    }


class IntradayMonitorDaemon:
    """盤中即時監控背景 Daemon"""

    def __init__(self, ohlcv_db=None, db_path: Path = None, interval: int = 10, finmind_token: str = ""):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ohlcv_db = ohlcv_db
        self.finmind_token = finmind_token

        self.interval = max(3, int(interval))
        self._codes: set = set()
        self._code_names: dict = {}

        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()

        self._snapshot: dict = {}          
        self._current_bar: dict = {}       
        self._last_predict_bar: dict = {}  
        self._default_weights: dict = dict(DEFAULT_STRATEGY_WEIGHTS)

        self._channel = "TWSE"
        self._fail_count = {"TWSE": 0, "FinMind": 0, "YFinance": 0}

        self._init_db()

    @contextmanager
    def _conn(self):
        con = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=15.0)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _init_db(self) -> None:
        with self._conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS intraday_bars (
                    code TEXT NOT NULL, trade_date TEXT NOT NULL, bar_time TEXT NOT NULL,
                    open REAL, high REAL, low REAL, close REAL, volume INTEGER,
                    PRIMARY KEY (code, trade_date, bar_time)
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS intraday_predicted (
                    code TEXT NOT NULL, trade_date TEXT NOT NULL, bar_time TEXT NOT NULL,
                    open REAL, high REAL, low REAL, close REAL,
                    composite_score REAL, detail TEXT,
                    PRIMARY KEY (code, trade_date, bar_time)
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS institutional_flow (
                    code TEXT NOT NULL, trade_date TEXT NOT NULL,
                    foreign_buy REAL, foreign_sell REAL, foreign_net REAL,
                    trust_buy REAL, trust_sell REAL, trust_net REAL,
                    dealer_buy REAL, dealer_sell REAL, dealer_net REAL,
                    updated_at TEXT,
                    PRIMARY KEY (code, trade_date)
                )
            """)

    # ── 生命週期 ────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="IntradayMonitorDaemon")
        self._thread.start()
        logger.info("IntradayMonitorDaemon 已啟動（FETCH_INTERVAL=%ds）", self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("IntradayMonitorDaemon 已停止")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_interval(self, seconds: int) -> int:
        self.interval = max(3, int(seconds))
        logger.info("FETCH_INTERVAL 已即時調整為 %d 秒", self.interval)
        return self.interval

    def get_interval(self) -> int:
        return self.interval

    def set_codes(self, codes_with_names: dict) -> None:
        with self._lock:
            self._codes = set(codes_with_names.keys())
            self._code_names.update(codes_with_names)

    def set_default_weights(self, weights: dict) -> None:
        with self._lock:
            self._default_weights = dict(weights)

    # ── 讀取介面 ────────────────────────────────────────────────

    def get_snapshot(self, codes: list) -> dict:
        with self._lock:
            return {c: dict(self._snapshot[c]) for c in codes if c in self._snapshot}

    def get_status(self) -> dict:
        with self._lock:
            return {
                "running":       self.is_running(),
                "market_open":   is_market_hours(),
                "interval":      self.interval,
                "channel":       self._channel,
                "watched_codes": sorted(self._codes),
                "snapshot_count": len(self._snapshot),
            }

    def get_bars(self, code: str, trade_date: str = None, limit: int = 300) -> list:
        trade_date = trade_date or date.today().isoformat()
        with self._conn() as con:
            rows = con.execute(
                "SELECT bar_time, open, high, low, close, volume FROM intraday_bars "
                "WHERE code=? AND trade_date=? ORDER BY bar_time ASC LIMIT ?",
                (code, trade_date, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_predicted_bars(self, code: str, trade_date: str = None, limit: int = 300) -> list:
        trade_date = trade_date or date.today().isoformat()
        with self._conn() as con:
            rows = con.execute(
                "SELECT bar_time, open, high, low, close, composite_score, detail FROM intraday_predicted "
                "WHERE code=? AND trade_date=? ORDER BY bar_time ASC LIMIT ?",
                (code, trade_date, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["detail"] = json.loads(d["detail"]) if d["detail"] else {}
            except Exception:
                d["detail"] = {}
            out.append(d)
        return out

    def get_institutional(self, code: str) -> Optional[dict]:
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM institutional_flow WHERE code=? ORDER BY trade_date DESC LIMIT 1",
                (code,),
            ).fetchone()
        return dict(row) if row else None

    def force_fetch_once(self) -> dict:
        with self._lock:
            codes = list(self._codes)
        if not codes:
            return {"ok": False, "error": "監控清單是空的，請先新增至少一檔股票"}

        results = self._fetch_batch(codes)
        now = datetime.now()
        for r in results:
            self._update_snapshot_and_bar(r, now)
            self._maybe_predict(r["stock_code"], now)

        fetched_codes = [r["stock_code"] for r in results]
        missing_codes = [c for c in codes if c not in fetched_codes]
        return {
            "ok": True,
            "channel": self._channel,
            "fetched": fetched_codes,
            "missing": missing_codes,
        }

    # ── 主迴圈與平行抓取 ──────────────────────────────────────────

    def run_loop(self) -> None:
        self.start()
        while not self._stop.is_set():
            self._stop.wait(5)

    def _loop(self) -> None:
        last_institutional_fetch = ""
        while not self._stop.is_set():
            try:
                if not is_market_hours():
                    self._stop.wait(30)
                    continue

                with self._lock:
                    codes = list(self._codes)

                if codes:
                    results = self._fetch_batch(codes)
                    now = datetime.now()
                    for r in results:
                        self._update_snapshot_and_bar(r, now)
                        self._maybe_predict(r["stock_code"], now)

                    today_str = now.strftime("%Y-%m-%d")
                    if last_institutional_fetch != today_str:
                        self._fetch_institutional(codes)
                        last_institutional_fetch = today_str

            except Exception as e:
                logger.error("監控迴圈例外: %s", e, exc_info=True)

            self._stop.wait(self.interval)

    def _fetch_batch(self, codes: list) -> list:
        channel = self._channel
        
        # 每 5 檔股票切分為一組小子集，進行多執行緒併發抓取
        chunk_size = 5
        chunks = [codes[i:i + chunk_size] for i in range(0, len(codes), chunk_size)]
        results = []
        
        with ThreadPoolExecutor(max_workers=min(4, len(chunks) or 1)) as executor:
            futures = {executor.submit(self._fetch_by_channel, channel, chunk): chunk for chunk in chunks}
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res:
                        results.extend(res)
                except Exception as e:
                    logger.error("分組平行抓取執行失敗: %s", e)

        if results:
            self._fail_count[channel] = 0
        else:
            self._fail_count[channel] = self._fail_count.get(channel, 0) + 1
            if self._fail_count[channel] >= CHANNEL_FAILURE_THRESHOLD:
                nxt = {"TWSE": "FinMind", "FinMind": "YFinance", "YFinance": "TWSE"}[channel]
                logger.warning("[%s] 連續失敗 %d 次，自動切換至 [%s]", channel, self._fail_count[channel], nxt)
                self._channel = nxt
                self._fail_count[nxt] = 0
        return results

    def _fetch_by_channel(self, channel: str, codes: list) -> list:
        if channel == "TWSE":
            return self._fetch_twse(codes)
        elif channel == "FinMind":
            return self._fetch_finmind(codes)
        return self._fetch_yfinance(codes)

    def _fetch_twse(self, codes: list) -> list:
        out = []
        try:
            ex_ch = "|".join(f"tse_{c}.tw" for c in codes)
            params = {"ex_ch": ex_ch, "_": int(time.time() * 1000)}
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01"
            }
            resp = requests.get(TWSE_TICK_URL, params=params, timeout=2, headers=headers)
            if resp.status_code != 200:
                return out
            data = resp.json()
            for msg in data.get("msgArray", []):
                code = msg.get("c", "")
                price_str = msg.get("z")
                if not price_str or price_str == "-":
                    b_list = (msg.get("b") or "").split("_")
                    price_str = b_list[0] if b_list and b_list[0] and b_list[0] != "-" else msg.get("y")
                
                out.append({
                    "stock_code": code,
                    "stock_name": (msg.get("n") or "").strip(),
                    "price": _safe_float(price_str, default=0.0),
                    "volume": int(msg.get("v", 0) if msg.get("v") != "-" else 0),
                    "open":  _safe_float(msg.get("o"), default=0.0),
                    "high":  _safe_float(msg.get("h"), default=0.0),
                    "low":   _safe_float(msg.get("l"), default=0.0),
                    "prev_close": _safe_float(msg.get("y"), default=0.0),
                    "bids": self._parse_book(msg.get("b", ""), msg.get("g", "")),
                    "asks": self._parse_book(msg.get("a", ""), msg.get("f", "")),
                    "data_source": "TWSE",
                })
        except Exception as e:
            logger.warning("TWSE 抓取失敗: %s", e)
        return out

    @staticmethod
    def _parse_book(price_str: str, vol_str: str) -> list:
        prices = [p for p in (price_str or "").split("_") if p and p != "-"]
        vols   = [v for v in (vol_str or "").split("_") if v]
        book = []
        for i in range(min(len(prices), len(vols), 5)):
            try:
                book.append({"price": float(prices[i]), "volume": int(vols[i])})
            except ValueError:
                continue
        return book

    def _fetch_finmind(self, codes: list) -> list:
        out = []
        headers = {"Authorization": f"Bearer {self.finmind_token}"} if self.finmind_token else {}
        today = date.today().isoformat()
        for code in codes:
            try:
                params = {"dataset": "TaiwanStockPrice", "data_id": code, "start_date": today}
                resp = requests.get(FINMIND_URL, headers=headers, params=params, timeout=5)
                if resp.status_code != 200:
                    continue
                records = resp.json().get("data", [])
                if not records:
                    continue
                latest = records[-1]
                out.append({
                    "stock_code": code,
                    "stock_name": self._code_names.get(code, code),
                    "price": float(latest.get("close", 0) or 0),
                    "volume": int(latest.get("Trading_Volume", latest.get("volume", 0)) or 0),
                    "open": float(latest.get("open", 0) or 0),
                    "high": float(latest.get("max", 0) or 0),
                    "low":  float(latest.get("min", 0) or 0),
                    "prev_close": 0.0,
                    "bids": [], "asks": [],
                    "data_source": "FinMind",
                })
            except Exception as e:
                logger.warning("FinMind 抓取 %s 失敗: %s", code, e)
        return out

    def _fetch_yfinance(self, codes: list) -> list:
        out = []
        try:
            import yfinance as yf
        except ImportError:
            return out
        for code in codes:
            clean_code = str(code).strip()
            suffixes = ["", ".TW", ".TWO"] if "." in clean_code else [".TW", ".TWO"]
            success = False
            for suffix in suffixes:
                try:
                    yf_symbol = clean_code if suffix == "" else f"{clean_code}{suffix}"
                    hist = yf.Ticker(yf_symbol).history(period="1d", interval="1m")
                    if hist is None or hist.empty:
                        continue
                    last = hist.iloc[-1]
                    out.append({
                        "stock_code": code,
                        "stock_name": self._code_names.get(code, code),
                        "price": float(last["Close"]),
                        "volume": int(last["Volume"]),
                        "open": float(hist["Open"].iloc[0]),
                        "high": float(hist["High"].max()),
                        "low":  float(hist["Low"].min()),
                        "prev_close": 0.0,
                        "bids": [], "asks": [],
                        "data_source": f"YFinance({yf_symbol})",
                    })
                    success = True
                    break
                except Exception:
                    continue
            if not success:
                logger.warning("YFinance 無法抓取台股代碼 %s", clean_code)
        return out

    # ── 快照更新 + 籌碼注入 ───────────────────────────────────────

    def _update_snapshot_and_bar(self, r: dict, now: datetime) -> None:
        code = r["stock_code"]
        price = r["price"]
        if not price:
            return

        change_pct = None
        prev_close = r.get("prev_close") or 0
        if prev_close:
            change_pct = round((price - prev_close) / prev_close * 100, 2)

        # 🚀 【核心修正點】生成記憶體快照時，主動去 SQLite 讀取最近一筆已留存的法人籌碼
        inst_data = self.get_institutional(code)

        with self._lock:
            self._snapshot[code] = {
                "code": code,
                "name": r.get("stock_name") or self._code_names.get(code, code),
                "price": price,
                "change_pct": change_pct,
                "volume": r.get("volume", 0),
                "bids": r.get("bids", []),
                "asks": r.get("asks", []),
                "data_source": r.get("data_source", ""),
                "institutional": inst_data,  # 🌟 透過記憶體快照將籌碼拋回前端，確保不被 Tick 洗掉
                "updated_at": now.strftime("%H:%M:%S"),
            }

        bar_time = now.strftime("%H:%M")
        trade_date = now.strftime("%Y-%m-%d")
        bar = self._current_bar.get(code)
        if bar is None or bar["bar_time"] != bar_time:
            bar = {
                "code": code, "trade_date": trade_date, "bar_time": bar_time,
                "open": price, "high": price, "low": price, "close": price,
                "volume": 0, "_last_total_volume": r.get("volume", 0),
            }
            self._current_bar[code] = bar
        else:
            bar["high"]  = max(bar["high"], price)
            bar["low"]   = min(bar["low"], price)
            bar["close"] = price
            total_vol = r.get("volume", 0)
            delta = max(0, total_vol - bar.get("_last_total_volume", 0))
            bar["volume"] += delta
            bar["_last_total_volume"] = total_vol

        self._flush_bar(bar)

    def _flush_bar(self, bar: dict) -> None:
        try:
            with self._conn() as con:
                con.execute("""
                    INSERT INTO intraday_bars (code, trade_date, bar_time, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code, trade_date, bar_time) DO UPDATE SET
                        high=MAX(high, excluded.high), low=MIN(low, excluded.low),
                        close=excluded.close, volume=excluded.volume
                """, (bar["code"], bar["trade_date"], bar["bar_time"],
                      bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]))
        except Exception as e:
            logger.warning("寫入 K 棒失敗: %s", e)

    def _maybe_predict(self, code: str, now: datetime) -> None:
        bar_time = now.strftime("%H:%M")
        if self._last_predict_bar.get(code) == bar_time:
            return
        self._last_predict_bar[code] = bar_time

        try:
            with self._lock:
                weights = dict(self._default_weights)
                snap = dict(self._snapshot.get(code, {}))
            result = compute_predicted_price(code, self.ohlcv_db, snap, weights)
            if result is None:
                return
            with self._conn() as con:
                con.execute("""
                    INSERT INTO intraday_predicted
                        (code, trade_date, bar_time, open, high, low, close, composite_score, detail)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code, trade_date, bar_time) DO UPDATE SET
                        close=excluded.close, high=excluded.high, low=excluded.low,
                        composite_score=excluded.composite_score, detail=excluded.detail
                """, (code, now.strftime("%Y-%m-%d"), bar_time,
                      result["open"], result["high"], result["low"], result["close"],
                      result["composite_score"], json.dumps(result["detail"], ensure_ascii=False)))
        except Exception as e:
            logger.warning("預測運算失敗 %s: %s", code, e)

    def _fetch_institutional(self, codes: list) -> None:
        headers = {"Authorization": f"Bearer {self.finmind_token}"} if self.finmind_token else {}
        for code in codes:
            try:
                params = {"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "data_id": code}
                resp = requests.get(FINMIND_URL, headers=headers, params=params, timeout=10)
                if resp.status_code != 200:
                    continue
                records = resp.json().get("data", [])
                if not records:
                    continue
                latest_date = records[-1]["date"]
                today_records = [r for r in records if r["date"] == latest_date]

                def _sum(names):
                    buy  = sum(r["buy"]  for r in today_records if r["name"] in names)
                    sell = sum(r["sell"] for r in today_records if r["name"] in names)
                    return buy, sell

                foreign_buy, foreign_sell = _sum({"Foreign_Investor", "Foreign_Dealer_Self"})
                trust_buy,   trust_sell   = _sum({"Investment_Trust"})
                dealer_buy,  dealer_sell  = _sum({"Dealer_self", "Dealer_Hedging"})

                with self._conn() as con:
                    con.execute("""
                        INSERT INTO institutional_flow
                            (code, trade_date, foreign_buy, foreign_sell, foreign_net,
                             trust_buy, trust_sell, trust_net, dealer_buy, dealer_sell, dealer_net, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(code, trade_date) DO UPDATE SET
                            foreign_buy=excluded.foreign_buy, foreign_sell=excluded.foreign_sell,
                            foreign_net=excluded.foreign_net, trust_buy=excluded.trust_buy,
                            trust_sell=excluded.trust_sell, trust_net=excluded.trust_net,
                            dealer_buy=excluded.dealer_buy, dealer_sell=excluded.dealer_sell,
                            dealer_net=excluded.dealer_net, updated_at=excluded.updated_at
                    """, (code, latest_date, foreign_buy, foreign_sell, foreign_buy - foreign_sell,
                          trust_buy, trust_sell, trust_buy - trust_sell,
                          dealer_buy, dealer_sell, dealer_buy - dealer_sell,
                          datetime.now().isoformat(timespec="seconds")))
            except Exception as e:
                logger.warning("法人買賣超抓取 %s 失敗: %s", code, e)
            time.sleep(0.3)