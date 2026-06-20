import datetime
import time
import requests
import yfinance as yf
from urllib3.util import Retry
from requests.adapters import HTTPAdapter


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

    def _get_price_from_openfind(self) -> float:
        """備援一: 獨立且完全寫死的 Yahoo 即時報價 API 端點"""
        # 直接寫死完整的 URL 列表，徹底杜絕任何變數拼接或取代引發的網址黏貼錯誤
        urls_to_try = [
            f"https://yahoo.com{self.stock_id}.TW?interval=1m&range=1d",
            f"https://yahoo.com{self.stock_id}.TWO?interval=1m&range=1d"
        ]
        
        for url in urls_to_try:
            try:
                # 獨立的 session 請求，不共用任何類別內的外部設定
                response = requests.get(url, headers=self.headers, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    
                    # 解析 Yahoo 的標準 JSON 陣列結構
                    if "chart" in data and data["chart"].get("result"):
                        result_list = data["chart"]["result"]
                        if len(result_list) > 0:
                            meta = result_list[0].get("meta", {})
                            price = meta.get("regularMarketPrice")
                            if price and price > 0:
                                market_type = "上市" if ".TW" in url else "上櫃"
                                print(f"[Yahoo 備援 API] 成功識別為 {market_type} 股票，取得價格: {price}")
                                return float(price)
            except Exception as e:
                # 這裡僅印出純粹的錯誤，不對網址進行二次加工
                print(f"嘗試請求網路端點失敗: {e}")
                continue
                
        raise RuntimeError("OpenFind (Yahoo API) 備援方案完全無法取得資料")
        
    def _test_pure_yahoo_api(stock_id):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        urls = [
            f"https://yahoo.com{stock_id}.TW?interval=1m&range=1d",
            f"https://yahoo.com{stock_id}.TWO?interval=1m&range=1d"
        ]
        for url in urls:
            print(f"正在發送請求至: {url}")
            try:
                res = requests.get(url, headers=headers, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
                    return f"測試成功！最新股價為: {price}"
            except Exception as e:
                print(f"該網址失敗: {e}")
        return "測試失敗，無法取得資料"
    #def _get_price_from_openfind(self) -> float:
    #    """備援一: 自訂第三方 API (使用 httpbin 進行實體測試模擬)"""
    #    # 我們利用 httpbin.org 的 json 服務，動態餵給它我們想要的價格（例如 915.0）
    #    mock_price = 915.0
    #    url = f"https://httpbin.org" 
    #    
    #    try:
    #        response = requests.get(url, headers=self.headers, timeout=5)
    #        if response.status_code == 200:
    #            # 為了符合你原本寫的 ["price"] 結構，我們在這裡做個 mock 映射
    #            # 實務上這裡會是：return float(response.json()["price"])
    #            print(f"[OpenFind 模擬] 收到外部 API 回傳成功")
    #            return mock_price
    #    except Exception as e:
    #        print(f"OpenFind 網路請求失敗: {e}")
    #        pass
    #    raise RuntimeError("OpenFind API 無法取得資料")    

    def _get_price_from_yfinance(self) -> float:
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
        # 嘗試 TWSE
        try:
            price = self._get_price_from_twse()
            print(f"[TWSE] 成功取得 {self.stock_id} 目前股價: {price}")
            return price
        except Exception as e:
            print(f"[警告] TWSE 獲取失敗: {e}，切換至 OpenFind 備援...")

        # 嘗試 OpenFind
        try:
            price = self._get_price_from_openfind()
            print(f"[OpenFind] 成功取得 {self.stock_id} 目前股價: {price}")
            return price
        except Exception as e:
            print(f"[警告] OpenFind 獲取失敗: {e}，切換至 yfinance 備援...")

        # 嘗試 yfinance
        try:
            price = self._get_price_from_yfinance()
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

        # 1. 如果股價創買入以來新高，更新最高股價與動態停損停利點
        if current_price > self.highest_price:
            self.highest_price = current_price
            new_stop = self.highest_price * (1 - self.trailing_pct)
            if new_stop > self.current_dynamic_stop:
                self.current_dynamic_stop = new_stop

        # 2. 檢查是否跌破動態停損停利點
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


# --- 模擬執行範例 ---
#if __name__ == "__main__":
#    # 建立系統執行實例 (以台積電 2330 為例，假設買入價 900 元)
#    system = RobustDynamicStopSystem(
#        stock_id="2330", 
#        buy_price=900.0, 
#        stop_loss_pct=0.05, 
#        trailing_pct=0.05
#    )
#    print(f"系統啟動：初始停損點設為：{system.current_dynamic_stop} 元")
#    print("-" * 50)
#
#    # 模擬主程式定時迴圈
#    for i in range(3):
#        try:
#            status = system.update_and_check()
#            print(
#                f"當前股價: {status['current_price']} | 歷史最高: {status['highest_price']} | 當前出場守備點: {status['current_dynamic_stop']:.2f}"
#            )
#            if status["triggered"]:
#                print(f"🚨🚨 出場訊號觸發!! 原因: {status['reason']} 🚨🚨")
#                break
#        except Exception as e:
#            print(f"主迴圈異常: {e}")
#        time.sleep(2)
#
# --- 專門測試 Openfind 備援機制的入口 ---
if __name__ == "__main__":
    # 單獨測試台積電
    _test_pure_yahoo_api("2330")
    # 建立系統執行實例 (假設買入價 900 元)
    system = RobustDynamicStopSystem(
        stock_id="2330", 
        buy_price=900.0, 
        stop_loss_pct=0.05, 
        trailing_pct=0.05
    )
    
    print("====== 開始測試 OpenFind 備援機制 ======")
    try:
        # 直接越過 TWSE 主控，單獨呼叫 OpenFind 的抓取方法
        price = system._get_price_from_openfind()
        print(f"【測試成功】OpenFind 成功解析出價格: {price} 元")
        
        # 模擬將此價格帶入動態停損點計算
        system.highest_price = price
        status = system.update_and_check()
        print(f"當前試算狀態: {status}")
        
    except Exception as e:
        print(f"【測試失敗】OpenFind 拋出異常: {e}")