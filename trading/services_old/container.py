# trading/services/container.py

from trading.services.market import MarketService
from trading.services.news import NewsAggregator
from trading.services.ohlcv import OhlcvDaemon
from trading.services.coverage import CoverageReader
from trading.services.intel import IntelligenceDaemon


class Container:
    def __init__(self):
        # 初始化各個服務
        self.market_svc = MarketService()
        self.news_agg = NewsAggregator()
        self.ohlcv_daemon = OhlcvDaemon()
        self.coverage_reader = CoverageReader()
        self.intel_daemon = IntelligenceDaemon()

    def start_all(self):
        """一次啟動所有服務"""
        self.market_svc.start()
        self.news_agg.start()
        self.ohlcv_daemon.start()
        self.coverage_reader.start()
        self.intel_daemon.start()

    def stop_all(self):
        """一次停止所有服務"""
        self.market_svc.stop()
        self.news_agg.stop()
        self.ohlcv_daemon.stop()
        self.coverage_reader.stop()
        self.intel_daemon.stop()


# 建立全域 container 物件
container = Container()
