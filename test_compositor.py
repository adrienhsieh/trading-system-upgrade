import sqlite3
from trading.services.container import StrategyCompositor

# 連線到測試用的使用者資料庫
user_db = sqlite3.connect("db/user_test_data.db")
user_db.row_factory = sqlite3.Row

# 建立 StrategyCompositor 實例
compositor = StrategyCompositor(user_db)

# 測試計算預測分數
result = compositor.calculate_prediction("2330")
print("📊 預測結果：", result)
