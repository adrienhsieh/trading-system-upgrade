"""
trading/api/__init__.py — Blueprint 匯總與統一註冊
"""
from trading.api.positions   import positions_bp
from trading.api.scan        import scan_bp
from trading.api.config_bp   import config_bp
from trading.api.backtest    import backtest_bp
from trading.api.market      import market_bp
from trading.api.intelligence import intelligence_bp
from trading.api.watchlist    import watchlist_bp
# 🔴 1. 引入我們全新建立的台股預測路由模組
from trading.api.predict      import predict_bp
from trading.api.user_config import user_setting_bp

def register_blueprints(app) -> None:
    """將所有 Blueprint 掛載至 Flask app。"""
    app.register_blueprint(positions_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(backtest_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(intelligence_bp)
    app.register_blueprint(watchlist_bp)
    # 🔴 2. 將台股 15 大因子加權預測藍圖掛載至 Flask
    app.register_blueprint(predict_bp)
    app.register_blueprint(user_setting_bp)