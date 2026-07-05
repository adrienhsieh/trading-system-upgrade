"""
trading/services/container.py — 依賴注入容器
全系統服務單例由此統一管理，lazy-init，執行緒安全。
"""
import os
import threading


class ServiceContainer:
    """Lazy-init 服務容器。所有服務皆在首次存取時建立。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._config_mgr     = None
        self._pos_mgr        = None
        self._ind_engine     = None
        self._scanner        = None
        self._market_svc     = None
        self._news_agg       = None
        self._ohlcv_db       = None
        self._intel_daemon   = None
        self._ohlcv_daemon   = None
        self._coverage_reader = None

    # ── 服務屬性（雙重鎖定，確保執行緒安全） ──────────────────────

    @property
    def config_mgr(self):
        if self._config_mgr is None:
            with self._lock:
                if self._config_mgr is None:
                    from trading.config import ConfigManager
                    self._config_mgr = ConfigManager()
        return self._config_mgr

    @property
    def pos_mgr(self):
        if self._pos_mgr is None:
            with self._lock:
                if self._pos_mgr is None:
                    from trading.positions import PositionManager
                    self._pos_mgr = PositionManager()
        return self._pos_mgr

    @property
    def ind_engine(self):
        if self._ind_engine is None:
            with self._lock:
                if self._ind_engine is None:
                    from trading.indicators import IndicatorEngine
                    self._ind_engine = IndicatorEngine()
        return self._ind_engine

    @property
    def scanner(self):
        if self._scanner is None:
            with self._lock:
                if self._scanner is None:
                    from trading.scanner import StockScanner
                    self._scanner = StockScanner(self.ind_engine)
        return self._scanner

    @property
    def market_svc(self):
        if self._market_svc is None:
            with self._lock:
                if self._market_svc is None:
                    from trading.market import MarketService
                    self._market_svc = MarketService()
        return self._market_svc

    @property
    def news_agg(self):
        if self._news_agg is None:
            with self._lock:
                if self._news_agg is None:
                    from trading.news import NewsAggregator
                    self._news_agg = NewsAggregator()
        return self._news_agg

    @property
    def ohlcv_db(self):
        if self._ohlcv_db is None:
            with self._lock:
                if self._ohlcv_db is None:
                    from trading.ohlcv_db import OHLCVDatabase
                    self._ohlcv_db = OHLCVDatabase()
        return self._ohlcv_db

    @property
    def ohlcv_daemon(self):
        if self._ohlcv_daemon is None:
            # 在 lock 外取得依賴，避免 deadlock（Lock 不可重入）
            db = self.ohlcv_db
            sc = self.scanner
            with self._lock:
                if self._ohlcv_daemon is None:
                    from trading.ohlcv_daemon import OHLCVDaemon
                    self._ohlcv_daemon = OHLCVDaemon(
                        ohlcv_db=db,
                        scanner=sc,
                    )
        return self._ohlcv_daemon

    @property
    def intel_daemon(self):
        if self._intel_daemon is None:
            with self._lock:
                if self._intel_daemon is None:
                    from trading.intelligence import IntelligenceDaemon
                    self._intel_daemon = IntelligenceDaemon(
                        groq_key=os.environ.get("GROQ_API_KEY", ""),
                        xai_key=os.environ.get("XAI_API_KEY", ""),
                    )
        return self._intel_daemon

    @property
    def coverage_reader(self):
        if self._coverage_reader is None:
            with self._lock:
                if self._coverage_reader is None:
                    from trading.coverage import CoverageReader
                    import logging
                    reader = CoverageReader()
                    try:
                        reader.reload()
                    except Exception as e:
                        logging.getLogger("trading.container").warning(
                            "coverage_reader 載入失敗（忽略）: %s", e
                        )
                    self._coverage_reader = reader
        return self._coverage_reader


# 全系統共用的唯一容器實例
container = ServiceContainer()
