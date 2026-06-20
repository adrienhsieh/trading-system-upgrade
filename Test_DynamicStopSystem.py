import datetime
import time
import requests
import yfinance as yf
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
import twstock

class RobustDynamicStopSystem:
    def __init__(
        self,
        stock_id: str,
        buy_price: float,
        stop_loss_pct: float = 0.05,
        trailing_pct: float = 0.05,
    ):
        self.stock_id = stock_id
        self.buy_price = buy_price
        self.stop_loss_pct = stop_loss_pct
        self.trailing_pct = trailing_pct
        
        # 初始狀態紀錄
        self.highest_price = buy_price
        self.initial_stop_loss = buy_price * (1 - stop_loss_pct)
        self.current_dynamic_stop = self.initial_stop_loss
        
        # 模擬瀏覽器 Headers 避免被封鎖
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def _get_price_from_twse(self) -> float:
        """主線: 從 TWSE 臺灣證券交易所正式即時 API 抓取 (支援上市與上櫃)"""
        # 1. 建立正確的查詢參數 (即時 API 同時查詢上市 tse 與上櫃 otc)
        ex_ch = f"tse_{self.stock_id}.tw|otc_{self.stock_id}.tw"
        
        # 2. 修正為正確的證交所「基本市況報導網站」即時 API 網址
        base_url = "https://mis.twse.com.tw"
        api_url = f"{base_url}/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1"
        
        session = requests.Session()
        # 設定重試策略：重試 3 次，每次間隔時間遞增
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        
        try:
            # 3. 證交所 API 限制: 必須先訪問首頁或索引頁取得 Session/Cookie
            session.get(f"{base_url}/stock/index.jsp", headers=self.headers, timeout=5)
            
            # 4. 發送真正的 API 請求
            response = session.get(api_url, headers=self.headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"TWSE API 網路連線或 DNS 解析失敗: {e}")

        try:
            data = response.json()
        except ValueError:
            raise RuntimeError("TWSE 回傳資料非 JSON 格式")

        if "msgArray" in data and len(data["msgArray"]) > 0:
            # 篩選出真正有回傳股票名稱或價格資料的節點
            valid_infos = [item for item in data["msgArray"] if item.get("n") or item.get("z")]
            if not valid_infos:
                raise RuntimeError(f"找不到代號 {self.stock_id} 的上市或上櫃股票資料")
            
            info = valid_infos[0]
            
            # 優先順序 1: 'z' 當盤成交價
            price_str = info.get("z")
            if price_str and price_str != "-":
                return float(price_str)
                
            # 優先順序 2: 'o' 開盤價 (適用於剛開盤僅有撮合但未成交時)
            if info.get("o") and info["o"] != "-":
                return float(info["o"])
                
            # 優先順序 3: 'y' 昨收價 (適用於盤前、試撮或剛開盤無交易量)
            if info.get("y") and info["y"] != "-":
                return float(info["y"])
                
            raise RuntimeError("TWSE 回傳資料格式異常或目前無法取得價格")
        else:
            raise RuntimeError(f"TWSE msgArray 為空，找不到代號 {self.stock_id}")

    def _get_price_from_twstock(self) -> float:
        """備援一: 改用第三方開源 twstock 套件獲取台股即時股價"""
        try:
            # 1. 呼叫 twstock 的即時資料介面
            # 它會自動處理上市(.TW)與上櫃(.TWO)的判斷，完全不用人工拼接網址
            rt_data = twstock.realtime.get(self.stock_id)
            
            # 2. 檢查 API 是否成功回傳資料
            if rt_data and rt_data.get("success"):
                info = rt_data.get("info", {})
                realtime_dict = rt_data.get("realtime", {})
                
                # 優先順序 1: 最新成交價 (latest_trade_price)
                price = realtime_dict.get("latest_trade_price")
                if price and price != "-":
                    print(f"[twstock 備援] 成功取得 {info.get('name')} 最新成交價: {price}")
                    return float(price)
                
                # 優先順序 2: 開盤價 (open)
                price_open = realtime_dict.get("open")
                if price_open and price_open != "-":
                    print(f"[twstock 備援] 成功取得 {info.get('name')} 開盤價: {price_open}")
                    return float(price_open)
                    
        except Exception as e:
            print(f"twstock 備援獲取失敗: {e}")
            pass
            
        raise RuntimeError("twstock 備援方案完全無法取得資料")
    def get_price_from_yfinance(self) -> float:
        """備援二: 從 Yahoo Finance 獲取最新即時現價"""
        for suffix in [".TW", ".TWO"]:
            ticker_str = f"{self.stock_id}{suffix}"
            ticker = yf.Ticker(ticker_str)
            try:
                price = ticker.fast_info["lastPrice"]
                if price and price > 0:
                    return float(price)
            except Exception:
                pass
            
            try:
                data = ticker.history(period="1d")
                if not data.empty:
                    return float(data["Close"].iloc[-1])
            except Exception:
                pass
                
        raise RuntimeError("yfinance 無法取得資料")

    def fetch_current_price(self) -> float:
        """多重備援價格獲取主控中心"""
        try:
            price = self._get_price_from_twse()
            print(f"[TWSE] 成功取得 {self.stock_id} 目前股價: {price}")
            return price
        except Exception as e:
            print(f"[警告] TWSE 獲取失敗: {e}，切換至 twstock 備援...")

        try:
            price = self._get_price_from_twstock()
            print(f"[twstock] 成功取得 {self.stock_id} 目前股價: {price}")
            return price
        except Exception as e:
            print(f"[警告] twstock 獲取失敗: {e}，切換至 yfinance 備援...")

        try:
            price = self.get_price_from_yfinance()
            print(f"[yfinance] 成功取得 {self.stock_id} 目前股價: {price}")
            return price
        except Exception as e:
            print(f"[錯誤] 所有備援機制皆失效，無法取得 {self.stock_id} 股價!")
            raise e

    def update_and_check(self) -> dict:
        """更新最高價、計算動態停損停利點，並檢查是否觸發出場訊號"""
        current_price = self.fetch_current_price()
        triggered = False
        signal_reason = ""

        if current_price > self.highest_price:
            self.highest_price = current_price
            new_stop = self.highest_price * (1 - self.trailing_pct)
            if new_stop > self.current_dynamic_stop:
                self.current_dynamic_stop = new_stop

        if current_price <= self.current_dynamic_stop:
            triggered = True
            if current_price < self.buy_price:
                signal_reason = "觸發初始停損機制"
            else:
                signal_reason = "利潤回檔，觸發動態停利機制"

        return {
            "current_price": current_price,
            "highest_price": self.highest_price,
            "current_dynamic_stop": self.current_dynamic_stop,
            "triggered": triggered,
            "reason": signal_reason,
        }
    def _get_price_from_yfinance(self) -> float:
        """備援二: 從 Yahoo Finance 獲取最新即時現價 (優化穩定版)"""
        for suffix in [".TW", ".TWO"]:
            ticker_str = f"{self.stock_id}{suffix}"
            ticker = yf.Ticker(ticker_str)
            
            # 【優化 1】優先嘗試獲取最新的盤中即時微觀歷史資料 (1分鐘K線)
            try:
                # 抓取今天(1d)內、每1分鐘(1m)一根的最新報價
                data = ticker.history(period="1d", interval="1m")
                if not data.empty:
                    # 拿最後一根 K 線的收盤價，這就是當前最接近的即時現價
                    latest_price = data["Close"].iloc[-1]
                    if latest_price and latest_price > 0:
                        print(f"[yfinance 備援] 成功透過歷史即時 K 線獲取 {ticker_str} 價格")
                        return float(latest_price)
            except Exception as e:
                print(f"yfinance 歷史 K 線嘗試失敗 ({ticker_str}): {e}")
                pass
            
            # 【優化 2】老牌 info 欄位作為安全備份
            try:
                # currentPrice 適用於盤中，regularMarketPrice 適用於盤後
                info = ticker.info
                price = info.get("currentPrice") or info.get("regularMarketPrice")
                if price and price > 0:
                    print(f"[yfinance 備援] 成功透過 Info 屬性獲取 {ticker_str} 價格")
                    return float(price)
            except Exception:
                pass

            # 【優化 3】原本的 fast_info 作為最後防線
            try:
                price = ticker.fast_info.get("lastPrice") or ticker.fast_info.get("regularMarketPrice")
                if price and price > 0:
                    print(f"[yfinance 備援] 成功透過 fast_info 獲取 {ticker_str} 價格")
                    return float(price)
            except Exception:
                pass
                
        raise RuntimeError("yfinance 所有管道皆無法取得資料")

# --- 測試進入點 ---
if __name__ == "__main__":
    # 1. 建立系統執行實例測試類別方法
    system = RobustDynamicStopSystem(
        stock_id="2330", 
        buy_price=900.0, 
        stop_loss_pct=0.05, 
        trailing_pct=0.05
    )
    
    print("====== 開始測試 twstock 備援機制 ======")
    try:
        # 直接呼叫修正後的 twstock 備援抓取方法
        price = system._get_price_from_twstock()
        print(f"【測試成功】twstock 成功解析出價格: {price} 元")
        
        system.highest_price = price
        status = system.update_and_check()
        print(f"當前試算狀態: {status}")
        
    except Exception as e:
        print(f"【測試失敗】twstock 拋出異常: {e}")
        
    # 2. 先執行外部獨立測試
    print("====== 開始測試 yfinance 備援機制 ======")
    try:
        # 【修正】加上 system. 並且補上正確的函數底線名稱
        price = system._get_price_from_yfinance()
        print(f"【測試成功】yfinance 成功解析出價格: {price} 元")
        
        system.highest_price = price
        status = system.update_and_check()
        print(f"當前試算狀態: {status}")
        
    except Exception as e:
        print(f"【測試失敗】yfinance 拋出異常: {e}")
