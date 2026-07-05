"""
test_integration.py — 整合測試腳本
同時測試 positions.py 與 api_prediction.py 是否能正常透過 container 運作
"""

import sqlite3
from flask import Flask
from trading.api.positions import positions_bp
from trading.api.api_prediction import api_prediction
from trading.api.utils import generate_token
from trading.config import ConfigManager
from trading.services.container import container


def setup_test_user_db():
    conn = sqlite3.connect("db/user_test_data.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_strategy_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        strategy_id TEXT NOT NULL,
        weight INTEGER DEFAULT 1,
        is_enabled INTEGER DEFAULT 1
    );
    """)
    cursor.execute("INSERT INTO user_strategy_configs (strategy_id, weight, is_enabled) VALUES ('opening_volume_pulse', 1, 1)")
    cursor.execute("INSERT INTO user_strategy_configs (strategy_id, weight, is_enabled) VALUES ('big_order_flow', 2, 1)")
    conn.commit()
    conn.close()


def run_flask_test():
    app = Flask(__name__)
    app.register_blueprint(positions_bp)
    app.register_blueprint(api_prediction)
    client = app.test_client()

    # 生成 JWT Token
    cfg = ConfigManager().load()
    token = generate_token(user_id="test", api_key=cfg["api_key"])
    headers = {"Authorization": f"Bearer {token}"}

    # 測試 positions API
    print("\n=== 測試 /api/positions GET ===")
    resp = client.get("/api/positions", headers=headers)
    print("狀態碼:", resp.status_code)
    print("回應:", resp.json)

    # 測試 prediction API
    print("\n=== 測試 /api/prediction/stream ===")
    resp = client.get("/api/prediction/stream?ticker=2330&user_id=test", headers=headers)
    print("狀態碼:", resp.status_code)
    print("回應:", resp.json)


if __name__ == "__main__":
    setup_test_user_db()
    run_flask_test()
