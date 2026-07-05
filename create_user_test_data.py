import sqlite3

conn = sqlite3.connect("db/user_test_data.db")
cursor = conn.cursor()

# 建立策略設定表
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_strategy_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    weight INTEGER DEFAULT 1,
    is_enabled INTEGER DEFAULT 1
);
""")

# 插入測試策略
cursor.execute("INSERT INTO user_strategy_configs (strategy_id, weight, is_enabled) VALUES ('opening_volume_pulse', 1, 1)")
cursor.execute("INSERT INTO user_strategy_configs (strategy_id, weight, is_enabled) VALUES ('big_order_flow', 2, 1)")

conn.commit()
conn.close()
print("✅ 測試用使用者策略資料庫已建立")
