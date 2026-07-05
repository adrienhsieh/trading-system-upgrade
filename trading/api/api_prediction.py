#import time
#import sqlite3
#import json
#from flask import Blueprint, Response, request
#from trading.services.container import StrategyCompositor
#
#api_prediction = Blueprint('api_prediction', __name__)
#
## 假設有 JWT 驗證工具
#from trading.api.utils import jwt_required
#
#
#@api_prediction.route('/api/prediction/stream', methods=['GET'])
#@jwt_required
#def prediction_stream():
#    """
#    SSE 串流 API：每 5 秒推送一次最新的預測分數
#    """
#    ticker = request.args.get('ticker', '2330')
#    user_id = request.args.get('user_id', 'test')  # 模擬用戶 ID
#
#    # 連線到使用者資料庫
#    user_db = sqlite3.connect(f"db/user_{user_id}_data.db")
#    user_db.row_factory = sqlite3.Row
#
#    # 建立策略組裝器
#    compositor = StrategyCompositor(user_db)
#
#    def generate():
#        while True:
#            result = compositor.calculate_prediction(ticker)
#            yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
#            time.sleep(5)
#
#    return Response(generate(), mimetype="text/event-stream")
#

"""
trading/api/api_prediction.py — 即時預測 API
提供 SSE 串流與測試用 JSON 路由
"""

import sqlite3
from flask import Blueprint, request, jsonify, Response
from trading.api.utils import jwt_required
from trading.services.strategy_compositor import StrategyCompositor
from trading.api.utils import verify_token


api_prediction = Blueprint("api_prediction", __name__)


from datetime import datetime

#from flask import request
#from trading.api.utils import verify_token
#
## ── Token 驗證路由 ───────────────────────────────────────────────
#@api_prediction.route("/api/token/verify", methods=["GET"])
#def verify_token_route():
#    auth_header = request.headers.get("Authorization", None)
#    if not auth_header or not auth_header.startswith("Bearer "):
#        return jsonify({"error": "缺少或格式錯誤的 Authorization header"}), 401
#
#    token = auth_header.split(" ")[1]
#    payload = verify_token(token)
#    if not payload:
#        return jsonify({"error": "無效或過期的 Token"}), 401
#
#    return jsonify({
#        "status": "valid",
#        "user_id": payload.get("user_id"),
#        "user_api_key": payload.get("user_api_key"),
#        "issued_at": payload.get("iat"),
#        "expires_at": payload.get("exp")
#    })    
#    

# ── 原本的 SSE 路由 ───────────────────────────────────────────────
@api_prediction.route("/api/prediction/stream", methods=["GET"])
@jwt_required
def prediction_stream():
    ticker = request.args.get("ticker")
    user_id = request.args.get("user_id")

    if not ticker or not user_id:
        return jsonify({"error": "缺少必要參數"}), 400

    def event_stream():
        user_db = sqlite3.connect(f"db/user_{user_id}_data.db")
        user_db.row_factory = sqlite3.Row
        compositor = StrategyCompositor(user_db)
        result = compositor.calculate_prediction(ticker)
        yield f"data: {result}\n\n"

    return Response(event_stream(), mimetype="text/event-stream")


# ── 新增的測試用 JSON 路由 ───────────────────────────────────────
@api_prediction.route("/api/prediction/test", methods=["GET"])
@jwt_required
def prediction_test():
    ticker = request.args.get("ticker", "2330")
    user_id = request.args.get("user_id", "test")

    user_db = sqlite3.connect(f"db/user_{user_id}_data.db")
    user_db.row_factory = sqlite3.Row
    compositor = StrategyCompositor(user_db)
    result = compositor.calculate_prediction(ticker)

    return jsonify(result)
    
# ── 健康檢查路由 ───────────────────────────────────────────────
@api_prediction.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


#from flask import request
#from trading.api.utils import verify_token

@api_prediction.route("/api/token/verify", methods=["GET"])
def verify_token_route():
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


if __name__ == "__main__":
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(api_prediction)
    # 如果還有 positions_bp 也一起註冊
    from trading.api.positions import positions_bp
    app.register_blueprint(positions_bp)

    app.run(host="0.0.0.0", port=5000, debug=True)
