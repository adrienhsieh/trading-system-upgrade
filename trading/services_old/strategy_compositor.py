import sqlite3
from datetime import datetime

class StrategyCompositor:
    def __init__(self, user_db_conn):
        self.user_db = user_db_conn
        self.global_conn = sqlite3.connect("db/ohlcv_cache.db", timeout=15.0)
        self.global_conn.row_factory = sqlite3.Row

    def calculate_prediction(self, ticker):
        user_cursor = self.user_db.cursor()
        user_cursor.execute("SELECT strategy_id, weight FROM user_strategy_configs WHERE is_enabled = 1")
        active_strategies = user_cursor.fetchall()

        if not active_strategies:
            return {"score": 0, "status": "未開啟任何預測策略"}

        total_score = 0
        total_weight = 0
        details = []

        for strat in active_strategies:
            strat_id = strat['strategy_id']
            weight = strat['weight']

            if strat_id == "opening_volume_pulse":
                score, msg = self._calc_opening_pulse(ticker)
            elif strat_id == "big_order_flow":
                score, msg = self._calc_big_order_flow(ticker)
            else:
                score, msg = (0, f"策略 {strat_id} 尚未實作")

            total_score += score * weight
            total_weight += weight
            details.append(msg)

        final_score = total_score / total_weight if total_weight > 0 else 0
        return {
            "ticker": ticker,
            "prediction_score": round(final_score, 2),
            "strategy_details": details,
            "calculated_at": datetime.now().strftime("%H:%M:%S")
        }

    def _calc_opening_pulse(self, ticker):
        global_cursor = self.global_conn.cursor()
        global_cursor.execute("""
            SELECT SUM(volume) as vol FROM intraday_ticks 
            WHERE ticker = ? ORDER BY id DESC LIMIT 5
        """, (ticker,))
        res = global_cursor.fetchone()
        current_vol = res['vol'] if res and res['vol'] else 0
        if current_vol > 500:
            return (100, f"開盤量能脈衝突破 (量: {current_vol}) -> 看漲")
        return (0, "量能平穩")

    def _calc_big_order_flow(self, ticker):
        global_cursor = self.global_conn.cursor()
        global_cursor.execute("""
            SELECT AVG(volume) as avg_vol FROM intraday_ticks 
            WHERE ticker = ? ORDER BY id DESC LIMIT 20
        """, (ticker,))
        res = global_cursor.fetchone()
        avg_vol = res['avg_vol'] if res and res['avg_vol'] else 0
        if avg_vol > 2000:
            return (80, f"大戶買賣力道顯著 (均量: {avg_vol}) -> 偏多")
        return (20, "大戶力道平穩")
