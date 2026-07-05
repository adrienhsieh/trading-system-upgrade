import os
import time
import sqlite3
import requests
import pandas as pd
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== 系統設定 ====================
STOCK_TARGETS = ["2330", "2317"]
FETCH_INTERVAL = 5

FINMIND_TOKEN = "你的FinMind Token"
TWSE_TICK_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
FINMIND_TICK_URL = "https://api.finmindtrade.com/api/v4/data"

TWSE_FAILURE_THRESHOLD = 3
FINMIND_FAILURE_THRESHOLD = 3

twse_failure_count = 0
finmind_failure_count = 0
current_channel = "TWSE"

# ==================== 輔助函式 ====================
def create_session_with_retry():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# ==================== 三通道擷取 ====================
def fetch_by_specific_channel(channel_name, targets) -> list:
    now = datetime.now()
    sys_date = now.strftime("%Y-%m-%d")
    sys_time = now.strftime("%H:%M:%S")
    output_list = []
    session = create_session_with_retry()

    if channel_name == "TWSE":
        try:
            ex_ch_list = [f"tse_{code}.tw" for code in targets]
            params = {"ex_ch": "|".join(ex_ch_list), "_": int(time.time() * 1000)}
            response = session.get(TWSE_TICK_URL, params=params, timeout=8)
            if response.status_code == 200:
                data = response.json()
                if "msgArray" in data and data["msgArray"]:
                    for msg in data["msgArray"]:
                        stock_code = msg.get("c")
                        price_str = msg.get("z")
                        if not price_str or price_str == "-":
                            b_list = msg.get("b", "").split("_")
                            price_str = b_list[0] if b_list and b_list[0] and b_list[0] != "-" else msg.get("y")
                        output_list.append({
                            "query_date": sys_date,
                            "query_time": sys_time,
                            "stock_code": stock_code,
                            "data_source": "TWSE_Official",
                            "price": float(price_str) if price_str else 0.0,
                            "volume": int(msg.get("v", 0)) if msg.get("v") else 0
                        })
        except Exception as e:
            print(f"❌ TWSE 擷取異常: {e}")

    elif channel_name == "FinMind":
        try:
            headers = {"Authorization": f"Bearer {FINMIND_TOKEN}"} if FINMIND_TOKEN else {}
            for stock_code in targets:
                params = {"dataset": "TaiwanStockPrice", "data_id": stock_code, "start_date": sys_date}
                response = session.get(FINMIND_TICK_URL, headers=headers, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    records = data.get("data", [])
                    if not records:
                        params["start_date"] = (pd.Timestamp(sys_date) - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
                        records = session.get(FINMIND_TICK_URL, headers=headers, params=params, timeout=10).json().get("data", [])
                    if records:
                        latest = records[-1]
                        output_list.append({
                            "query_date": sys_date,
                            "query_time": sys_time,
                            "stock_code": stock_code,
                            "data_source": "FinMind_API",
                            "price": float(latest.get("close", 0)),
                            "volume": int(latest.get("volume", 0))
                        })
        except Exception as e:
            print(f"❌ FinMind 擷取異常: {e}")

    elif channel_name == "YFinance":
        try:
            import yfinance as yf
            for stock_code in targets:
                ticker = yf.Ticker(f"{stock_code}.TW")
                hist = ticker.history(period="1d")
                if hist.empty:
                    hist = ticker.history(period="5d")
                if not hist.empty:
                    latest = hist.iloc[-1]
                    output_list.append({
                        "query_date": sys_date,
                        "query_time": sys_time,
                        "stock_code": stock_code,
                        "data_source": "YFinance_Fallback",
                        "price": float(latest['Close']),
                        "volume": int(latest['Volume'])
                    })
        except Exception as e:
            print(f"❌ YFinance 擷取異常: {e}")

    return output_list

# ==================== 熔斷邏輯 ====================
def fetch_market_data_batch(targets) -> list:
    global twse_failure_count, finmind_failure_count, current_channel
    output_list = fetch_by_specific_channel(current_channel, targets)

    if current_channel == "TWSE":
        if output_list:
            twse_failure_count = 0
        else:
            twse_failure_count += 1
            if twse_failure_count >= TWSE_FAILURE_THRESHOLD:
                current_channel = "FinMind"
                print("🚨 TWSE 連續失敗，自動切換至 FinMind")
    elif current_channel == "FinMind":
        if output_list:
            finmind_failure_count = 0
        else:
            finmind_failure_count += 1
            if finmind_failure_count >= FINMIND_FAILURE_THRESHOLD:
                current_channel = "YFinance"
                print("🚨 FinMind 連續失敗，自動切換至 YFinance")

    return output_list

# ==================== 全域快取庫寫入 ====================
class GlobalStorageManager:
    @classmethod
    def save_ticks_to_cache(cls, batch_results: list):
        if not batch_results:
            return
        conn = sqlite3.connect("db/ohlcv_cache.db", timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        cursor = conn.cursor()
        try:
            for item in batch_results:
                cursor.execute("""
                    INSERT INTO intraday_ticks (timestamp, ticker, data_source, price, volume)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    f"{item['query_date']} {item['query_time']}",
                    item['stock_code'],
                    item['data_source'],
                    item['price'],
                    item['volume']
                ))
            conn.commit()
            print(f"🤖 [Worker] 成功同步 {len(batch_results)} 筆 Tick 數據至全域快取庫。")
        except Exception as e:
            conn.rollback()
            print(f"❌ [Worker] 寫入失敗: {e}")
        finally:
            conn.close()

# ==================== 測試入口 ====================
if __name__ == "__main__":
    targets = STOCK_TARGETS
    batch_results = fetch_market_data_batch(targets)
    GlobalStorageManager.save_ticks_to_cache(batch_results)
