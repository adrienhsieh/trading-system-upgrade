"""
trading/api/__init__.py — Blueprint 匯總與統一註冊
"""
from trading.api.positions import positions_bp
from trading.api.scan import scan_bp
from trading.api.config_bp import config_bp
from trading.api.backtest import backtest_bp
from trading.api.market import market_bp
from trading.api.intelligence import intelligence_bp
from trading.api.watchlist import watchlist_bp
from trading.api.predict import predict_bp
from trading.api.user_config import user_setting_bp
from trading.api.api_system import api_system
from trading.api.auth import api_auth
from trading.api.intraday import intraday_bp
from trading.api.fundamentals import fundamentals_bp
from trading.api.thsr import thsr_bp
from trading.api.thsr_monitor_api import thsr_monitor_bp  # ✨ 高鐵背景監控（新增）
from trading.api.thsr_history import thsr_history_bp  # ✨ 高鐵訂位查詢／取消（新增）


def register_blueprints(app) -> None:
    """將所有 Blueprint 掛載至 Flask app。
    
    順序說明：
    1. auth - 認證必須優先（middleware）
    2. 業務 API - positions, scan, market, ...
    3. 高鐵相關 - thsr（手動）→ thsr_monitor（自動監控）→ thsr_history（查詢／取消）
    """
    app.register_blueprint(api_auth)          # 認證優先
    app.register_blueprint(positions_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(backtest_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(intelligence_bp)
    app.register_blueprint(watchlist_bp)
    app.register_blueprint(predict_bp)
    app.register_blueprint(user_setting_bp)
    app.register_blueprint(api_system)
    app.register_blueprint(intraday_bp)
    app.register_blueprint(fundamentals_bp)
    app.register_blueprint(thsr_bp)           # 手動訂票
    app.register_blueprint(thsr_monitor_bp)   # 背景自動監控 ✅
    app.register_blueprint(thsr_history_bp)   # 訂位查詢／取消 ✅