"""
trading/scanner.py — 股票掃描器
整合 TWSE + TPEX API，並支援技術面、ICT、基本面策略分析。
"""

import concurrent.futures
import threading
import time
import requests
import urllib3
from typing import Optional
from trading.logger import get_logger
from trading.constants import STOCK_CACHE_TTL, INDUSTRY_CACHE_TTL, SCAN_WORKERS, REQUEST_TIMEOUT
from trading.indicators import IndicatorEngine
from trading.strategies import get_strategy

logger = get_logger("scanner")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class StockScanner:
    TWSE_API_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    TPEX_API_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
    TWSE_INDUSTRY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"

    TECH_INDUSTRY_KEYWORDS = frozenset(["半導體", "電腦", "光電", "通訊", "電子", "資訊", "科技"])

    def __init__(self, indicator_engine: IndicatorEngine = None):
        self.indicator_engine = indicator_engine or IndicatorEngine()
        self._stock_cache = {}
        self._stock_cache_time = 0.0
        self._industry_cache = {}
        self._industry_cache_time = 0.0
        self._cache_lock = threading.RLock()

    # ── 股票代號表 ─────────────────────────────────────────────
    def get_stock_map(self) -> dict:
        with self._cache_lock:
            if self._stock_cache and time.time() - self._stock_cache_time < STOCK_CACHE_TTL:
                return self._stock_cache

        stock_map = {}
        try:
            r = requests.get(self.TWSE_API_URL, headers={"Accept": "application/json"}, timeout=REQUEST_TIMEOUT, verify=False)
            for item in r.json():
                code = str(item.get("Code", "")).strip()
                name = str(item.get("Name", "")).strip()
                if code.isdigit() and len(code) == 4:
                    stock_map[code] = name or code
            logger.info("TWSE API 取得 %d 檔", len(stock_map))
        except Exception as e:
            logger.warning("TWSE API 失敗: %s", e)

        try:
            r = requests.get(self.TPEX_API_URL, headers={"Accept": "application/json"}, timeout=REQUEST_TIMEOUT, verify=False)
            for item in r.json():
                code = str(item.get("SecuritiesCompanyCode", "")).strip()
                name = str(item.get("CompanyName", "")).strip()
                if code.isdigit() and len(code) == 4 and code not in stock_map:
                    stock_map[code] = name or code
            logger.info("TPEX API 取得 %d 檔", len(stock_map))
        except Exception as e:
            logger.warning("TPEX API 失敗: %s", e)

        with self._cache_lock:
            self._stock_cache = stock_map
            self._stock_cache_time = time.time()
        return stock_map

    def get_all_tw_stocks(self) -> list:
        return list(self.get_stock_map().keys())

    def get_stock_name(self, code: str) -> str:
        return self.get_stock_map().get(code, code)

    # ── 產業別資料 ─────────────────────────────────────────────
    @staticmethod
    def _is_tech_by_code(code: str) -> bool:
        try:
            n = int(code)
        except ValueError:
            return False
        return (3000 <= n <= 3699 or 4900 <= n <= 4999 or 5200 <= n <= 5399 or 6200 <= n <= 6999)

    def _fetch_industry_map(self) -> dict:
        with self._cache_lock:
            if self._industry_cache and time.time() - self._industry_cache_time < INDUSTRY_CACHE_TTL:
                return self._industry_cache

        result = {}
        try:
            r = requests.get(self.TWSE_INDUSTRY_URL, headers={"Accept": "application/json"}, timeout=REQUEST_TIMEOUT, verify=False)
            for item in r.json():
                code = str(item.get("公司代號", "")).strip()
                ind = str(item.get("產業別", "")).strip()
                if code and ind:
                    result[code] = ind
            logger.info("TWSE 產業別取得 %d 筆", len(result))
        except Exception as e:
            logger.warning("TWSE 產業別失敗: %s", e)

        sm = self._stock_cache or {}
        for code in sm:
            if code not in result and self._is_tech_by_code(code):
                result[code] = "電子"

        with self._cache_lock:
            self._industry_cache = result
            self._industry_cache_time = time.time()
        return result

    def get_tech_stock_map(self) -> dict:
        sm = self.get_stock_map()
        ind = self._fetch_industry_map()
        return {code: name for code, name in sm.items() if any(kw in ind.get(code, "") for kw in self.TECH_INDUSTRY_KEYWORDS)}

    # ── 個股分析 ─────────────────────────────────────────────
    def analyze_one(self, code: str, capital: float, risk_pct: float, strategy: str = "trend", name: str = "") -> Optional[dict]:
        strat = get_strategy(strategy)
        df = self.indicator_engine.fetch_ohlcv(code)
        if df is None or len(df) < strat.min_bars:
            return None
        try:
            ind = strat.compute(df, code=code)
            if ind is None:
                return None
            params = strat.calc_entry_params(ind, capital, risk_pct)
            return {"code": code, "name": name or self.get_stock_name(code), "score": ind["score"], "ind": ind, "params": params, "strategy": strategy}
        except Exception as e:
            logger.debug("%s %s 失敗: %s", strategy.upper(), code, e)
            return None

    def run_scan(self, candidates: list, capital: float, risk_pct: float = 2.0, strategy: str = "trend", max_workers: int = SCAN_WORKERS) -> list:
        sm = self.get_stock_map()
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(self.analyze_one, c, capital, risk_pct, strategy, sm.get(c, "")): c for c in candidates}
            for f in concurrent.futures.as_completed(futs):
                r = f.result()
                if r:
                    results.append(r)
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    # ICT 快捷方法
    def analyze_one_ict(self, code, capital, risk_pct, name=""):
        return self.analyze_one(code, capital, risk_pct, strategy="ict", name=name)

    def run_scan_ict(self, candidates, capital, risk_pct=2.0, max_workers=SCAN_WORKERS):
        return self.run_scan(candidates, capital, risk_pct, strategy="ict", max_workers=max_workers)

    # API 格式化
    def format_for_api(self, results: list, strategy: str = "trend") -> list:
        # 這裡保留你之前的完整 format_for_api 實作
        ...
