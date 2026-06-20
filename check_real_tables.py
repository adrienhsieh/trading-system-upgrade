# check_real_tables.py
from sqlalchemy import create_engine, inspect

dbs = {
    "intelligence": "sqlite:///./intelligence.db",
    "ohlcv_cache":   "sqlite:///./ohlcv_cache.db",
    "positions":    "sqlite:///./positions.db",
    "trading_system":"sqlite:///./trading_system.db"
}

print("\n==================================================")
print("     🔍 正在探測四大交易資料庫的真實資料表結構...")
print("==================================================")

for db_name, db_url in dbs.items():
    try:
        engine = create_engine(db_url)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"\n📂 檔案: 【 {db_name}.db 】 內含資料表:")
        if not tables:
            print("   ⚠️  (此資料庫內目前沒有任何資料表)")
        for t in tables:
            columns = inspector.get_columns(t)
            col_names = [col['name'] for col in columns]
            print(f"   🔹 表名: {t}")
            print(f"      ↳ 實際欄位: {', '.join(col_names)}")
    except Exception as e:
        print(f"   ❌ 讀取 {db_name}.db 失敗: {e}")
        
print("\n==================================================")
