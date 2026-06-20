"""
app.py — Flask 應用程式進入點
路由分散於 trading/api/ Blueprint 模組；服務單例統一由 trading/services/container.py 管理。
啟動方式：python run.py
"""
import logging
import os
from pathlib import Path

from flask import Flask, send_from_directory
from flask_cors import CORS

from trading.api import register_blueprints
from trading.api.extensions import limiter
from trading.exceptions import TradingSystemError
# ── 💡 關鍵新增：引入 SQLite 初始化與背景後台啟動工具 ──
from trading.services.config_db import init_db
from trading.api.admin_ui import init_admin_web_ui

# ── backward-compat：讓 run.py 可以繼續 from app import config_mgr, ... ──
from trading.services.container import container as _container
config_mgr      = _container.config_mgr
pos_mgr         = _container.pos_mgr
ind_engine      = _container.ind_engine
scanner         = _container.scanner
market_svc      = _container.market_svc
news_agg        = _container.news_agg
intel_daemon    = _container.intel_daemon
coverage_reader = _container.coverage_reader

BASE_DIR = Path(__file__).parent
_logger  = logging.getLogger("trading.app")

# ── 💡 關鍵新增：在 Flask 啟動前，自動建立 SQLite 資料表（如果不存在的話） ──
try:
    init_db()
    _logger.info("SQLite 網頁獨立設定資料庫初始化成功。")
except Exception as e:
    _logger.error("SQLite 初始化失敗: %s", e, exc_info=True)

#── Flask 應用 ─────────────────────────────────────────────────    
app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")

# 💡 關鍵修正：在實例化 app 後立刻加入 secret_key，解決 Session 的 500 報錯
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "trading_system_opus_secure_key_2026")

_allowed_origin = os.environ.get("CORS_ORIGIN", "http://localhost:8787")
CORS(app, resources={r"/api/*": {"origins": [_allowed_origin]}})
limiter.init_app(app)

register_blueprints(app)


from trading.api.admin_ui import init_admin_web_ui
init_admin_web_ui(app)

# ── Flask 應用 ─────────────────────────────────────────────────
#app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
#_allowed_origin = os.environ.get("CORS_ORIGIN", "http://localhost:8787")
#CORS(app, resources={r"/api/*": {"origins": [_allowed_origin]}})
#limiter.init_app(app)
#
#register_blueprints(app)
#from trading.api.admin_ui import init_admin_web_ui
#init_admin_web_ui(app)

# ── 💡 關鍵新增：一鍵背景驅動獨立的 8i787 資料庫後台 ──
#try:
#    init_admin_web_ui(app)
#except Exception as e:
#    _logger.error("背景 SQLite 後台啟動失敗: %s", e)


# ── 靜態頁面 ───────────────────────────────────────────────────
@app.route("/")
def index():
    real_path = os.path.abspath(os.path.join(str(BASE_DIR), "index.html"))
    print(f"\n📢 [重要情報] 戰情中心目前真正在背景讀取的 index.html 絕對路徑為:\n👉 {real_path}\n")
    
    # 🟢 終極保底大招：建立強制的 Response 物件，並在 Header 中明確宣告不允許任何 Location 轉向
    response = send_from_directory(str(BASE_DIR), "index.html")
    response.headers["Location"] = "" # 強行抹除轉向目標
    response.status_code = 200        # 強制鎖定為 200 成功狀態碼，不允許 301/302
    return response

#@app.route("/")
#def index():
#    # 🟢 終極現形記：直接在 Python 控制台與網頁上，強制列印出 Flask 真正讀取的 index.html 精確資料夾路徑！
#    real_path = os.path.abspath(os.path.join(str(BASE_DIR), "index.html"))
#    print(f"\n📢 [重要情報] 戰情中心目前真正在背景讀取的 index.html 絕對路記為:\n👉 {real_path}\n")
#    
#    return send_from_directory(str(BASE_DIR), "index.html")

@app.route("/mockup")
def mockup():
    return send_from_directory(str(BASE_DIR / "docs"), "mockup-recorder.html")


# ── Security headers ──────────────────────────────────────────

@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


# ── 全域 error handler ────────────────────────────────────────

@app.errorhandler(TradingSystemError)
def handle_trading_error(e: TradingSystemError):
    _logger.error("TradingSystemError: %s", e, exc_info=True)
    return __import__("flask").jsonify({"ok": False, "error": "系統發生錯誤，請稍後再試"}), 500


@app.errorhandler(500)
def handle_500(e):
    _logger.error("Unhandled 500: %s", e, exc_info=True)
    return __import__("flask").jsonify({"ok": False, "error": "內部伺服器錯誤"}), 500


# ── 直接執行（開發用） ─────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"\n⚔️  戰情指揮中心（開發模式已啟動雙 Port 物理隔離架構）")
    print(f"   👉 交易系統主首頁 (100% 釋放歸還): http://localhost:{port}/")
    print(f"   👉 獨立資料庫管理後台 (絕不轉圈圈): http://localhost:{port}/admin\n")
    print("   正式啟動請使用：python app.py 或是 python run.py")
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
