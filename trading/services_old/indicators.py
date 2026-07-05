class IndicatorEngine:
    def fetch_ohlcv(self, code, period="1mo"):
        import pandas as pd
        return pd.DataFrame({"close": [600, 610], "volume": [1000, 1200]})
    
    def analyze_position(self, p):
        return {"code": p["code"], "name": p["name"], "alerts": []}
