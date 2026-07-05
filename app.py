# -*- coding: utf-8 -*-
import os
import time
import platform
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from trading.services.container import container
from trading.api.auth import require_auth
from trading.strategies.compositor import StrategyEngine
from trading.api.api_system import api_system

# ── 建立 Flask App ─────────────────────────────
app = Flask(__name__, static_folder="static", static_url_path="")
engine = StrategyEngine()

# ── 註冊 Blueprint ─────────────────────────────
app.register_blueprint(api_system)

# ── API Key 設定 ─────────────────────────────
API_KEY = os.environ.get("API_KEY", "test-token")

# ── 首頁顯示 index.html ─────────────────────────────
@app.route("/")
def index_page():
    return send_from_directory(".", "index.html")

# ── 市場行情 ─────────────────────────────
@app.route("/api/market")
@require_auth
def api_market():
    return jsonify({"ok": True, "market": container.market_svc.get_data()})

# ── 個股資訊 ─────────────────────────────
@app.route("/api/stock_info/<code>")
@require_auth
def api_stock_info(code):
    try:
        data = container.market_svc.get_stock_info(code)
        if not data:
            return jsonify({"ok": False, "error": f"Stock {code} not found"}), 404
        return jsonify({"ok": True, "code": code, "info": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ── 持股部位 ─────────────────────────────
@app.route("/api/positions")
@require_auth
def api_positions():
    return jsonify({
        "ok": True,
        "positions": [
            {"code": "2330", "name": "台積電", "shares": 100, "avg_price": 600},
            {"code": "2303", "name": "聯電", "shares": 200, "avg_price": 45}
        ]
    })

# ── 投資報告 ─────────────────────────────
@app.route("/api/report")
@require_auth
def api_report():
    return jsonify({
        "ok": True,
        "report": {
            "date": "2026-07-03",
            "summary": "目前持股以台積電、聯電為主，市場趨勢偏多。",
            "risk": "中低"
        }
    })

# ── 預測計算 ─────────────────────────────
@app.route("/api/predict/calculate", methods=["POST"])
@require_auth
def api_predict_calculate():
    try:
        payload = request.get_json(force=True) or {}
        code = payload.get("code", "2330")
        strategy = payload.get("strategy", "ict")

        df = pd.DataFrame({
            "open": [600, 605, 610],
            "high": [610, 615, 620],
            "low": [595, 600, 605],
            "close": [605, 610, 615]
        })

        result = engine.run(strategy, df, code)
        return jsonify({"ok": True, "code": code, "strategy": strategy, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

# ── 系統狀態 API ─────────────────────────────
@app.route("/api/system/info")
def api_system_info():
    return jsonify({
        "ok": True,
        "version": "1.0.0",
        "uptime": round(time.time() - container.start_time, 2),
        "platform": platform.system(),
        "api_key": API_KEY,
        "services": {
            "market": "running",
            "news": "running",
            "ohlcv": "running",
            "coverage": "running",
            "intel": "running"
        }
    })

# ── 啟動 Flask ─────────────────────────────
if __name__ == "__main__":
    container.start_time = time.time()
    container.start_all()
    print(f"🚀 Trading System 啟動成功，API Key = {API_KEY}")
    app.run(host="0.0.0.0", port=8080, debug=True)
