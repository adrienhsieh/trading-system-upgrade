import time
from flask import Blueprint, jsonify, request
from datetime import datetime
from trading.api.utils import verify_token

api_system = Blueprint("api_system", __name__)

# ── 啟動時間（用來計算 uptime） ──
_start_time = time.time()

# ── 健康檢查 ───────────────────────────────
@api_system.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

# ── Token 驗證 ─────────────────────────────
@api_system.route("/api/token/verify", methods=["GET"])
def token_verify():
    auth_header = request.headers.get("Authorization", None)
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "缺少或格式錯誤的 Authorization header"}), 401

    token = auth_header.split(" ")[1]
    payload = verify_token(token)
    if not payload:
        return jsonify({"error": "無效或過期的 Token"}), 401

    return jsonify({
        "status": "valid",
        "user_id": payload.get("user_id"),
        "user_api_key": payload.get("user_api_key"),
        "issued_at": payload.get("iat"),
        "expires_at": payload.get("exp")
    })

# ── 系統資訊 ───────────────────────────────
@api_system.route("/api/system/info", methods=["GET"])
def system_info():
    uptime_seconds = int(time.time() - _start_time)
    uptime_str = f"{uptime_seconds // 3600}h {uptime_seconds % 3600 // 60}m {uptime_seconds % 60}s"

    return jsonify({
        "version": "1.0.0",   # 可以改成讀取 config 或 git commit hash
        "uptime": uptime_str,
        "services": [
            "pos_mgr",
            "ind_engine",
            "scanner",
            "market_svc",
            "news_agg",
            "intel_daemon",
            "coverage_reader"
        ]
    })

# ── 策略參數 ───────────────────────────────
@api_system.route("/api/strategy_params", methods=["GET"])
def strategy_params():
    return jsonify({
        "params": {
            "risk_level": "medium",
            "max_positions": 10,
            "stop_loss": 0.05,
            "take_profit": 0.1,
            "rebalance_interval": "daily"
        }
    })
