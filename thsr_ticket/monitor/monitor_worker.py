"""
Monitor Worker - 背景監控 / 自動搶票 線程

結合兩種模式：
- mode == "watch"     ：比照 thsr-ticket-monitor，定期查詢，找到符合條件的車次就發通知，不自動購票。
- mode == "auto_book" ：比照 THSR-Sniper，等到指定的開賣時間（release_at，例如當日凌晨 00:00）
                        後開始高頻嘗試，自動完成「驗證碼辨識 → 篩選車次(時間區間/早鳥) → 選車 →
                        帶身分證/手機送出訂票」，訂到票或超過時間預算為止。

🛠️ 修正重大問題：舊版 _check_seat_availability() 只是 `random.random() < 0.1` 的假實作，
從未真的呼叫高鐵網站，等於這個監控功能完全不會運作。現在改為直接重用
trading/api/thsr.py 裡「Tab 1 手動訂票」已經在用、真的能連上高鐵官網並用 ddddocr
自動解驗證碼的 YourThsrHttpClient / AvailTrains / ConfirmTrain / ConfirmTicket / BookingResult，
避免整套邏輯重寫兩次、也避免兩份程式碼日後行為兜不起來。
"""
import logging
import time
import threading
import random
import json
import os   
import base64
from types import SimpleNamespace
from typing import Optional, List, Dict, Any
from datetime import datetime

_logger = logging.getLogger(__name__)


class RateLimiter:
    """適應性速率限制器 - 防止被高鐵官網阻擋（watch 模式使用）"""
    
    def __init__(self, base_interval: int = 90):
        self.base_interval = base_interval
        self.warning_count = 0
        self.last_check_time = None
        self._lock = threading.Lock()
    
    def detect_rate_limit(self, response_html: str) -> bool:
        """檢測是否觸發限流
        🛠️ 修正重大 Bug：先前的關鍵字清單裡有「請稍候」，但這其實是高鐵「每一個頁面」
        都固定存在的載入動畫文字（<div id="loading">...<span>請稍候...</span></div>），
        不是限流才會出現的訊息。結果每一次查詢都被誤判成「偵測到限流」而直接跳過，
        導致自動搶票／監控功能永遠無法成功送出查詢。已移除這個會 100% 誤判的關鍵字。
        剩下這幾個關鍵字目前尚未有實際被高鐵限流時的真實頁面可比對驗證，
        如果之後真的遇到限流，建議把當時的完整回應內容存下來，
        以便比對出真正專屬於限流訊息、不會跟正常頁面重疊的關鍵字。"""
        if not response_html:
            return False
        
        patterns = [
            '系統繁忙', '超過查詢限制',
            '暫時無法提供', '請稍後再試'
        ]
        
        html_lower = response_html.lower()
        for pattern in patterns:
            if pattern in html_lower:
                self.warning_count += 1
                _logger.warning(f"⚠️ 偵測到限流信號 (warning #{self.warning_count}): {pattern}")
                return True
        return False
    
    def calculate_interval(self) -> int:
        """計算自適應延遲間隔"""
        with self._lock:
            base = self.base_interval
            penalty = min(self.warning_count * 60, 300)
            jitter = random.randint(-10, 10)
            return max(30, base + penalty + jitter)
    
    def reset_warnings(self):
        """重置警告計數（成功查詢時）"""
        with self._lock:
            if self.warning_count > 0:
                self.warning_count -= 1


def _parse_hhmm(text: str) -> Optional[int]:
    """把 'HH:MM' 字串轉成分鐘數，解析失敗回傳 None"""
    try:
        text = (text or "").strip()
        h, m = text.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _time_in_window(depart_str: str, window_start: str, window_end: str) -> bool:
    """判斷車次出發時間是否落在使用者指定的時間區間內；區間留空代表不限制"""
    if not window_start and not window_end:
        return True
    depart_min = _parse_hhmm(depart_str)
    if depart_min is None:
        return True  # 解析不到時間就不過濾，避免誤刪車次
    start_min = _parse_hhmm(window_start) if window_start else 0
    end_min = _parse_hhmm(window_end) if window_end else 24 * 60 - 1
    if start_min is None:
        start_min = 0
    if end_min is None:
        end_min = 24 * 60 - 1
    return start_min <= depart_min <= end_min


def _nearest_time_table_value(window_start: str, fallback: str) -> str:
    """依照使用者填的時間區間起點，找出最接近且不晚於它的高鐵官方合法查詢時間代碼；
    找不到就沿用任務原本的 search_time"""
    if not window_start:
        return fallback
    try:
        from trading.api.thsr import TIME_TABLE
    except Exception:
        return fallback
    target_min = _parse_hhmm(window_start)
    if target_min is None:
        return fallback
    best_value, best_diff = fallback, None
    for entry in TIME_TABLE:
        entry_min = _parse_hhmm(entry["time"])
        if entry_min is None:
            continue
        diff = target_min - entry_min
        if diff < 0:  # 只挑不晚於期望時間的班次起點，確保區間內的車次都查得到
            continue
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_value = entry["value"]
    return best_value


class MonitorWorker(threading.Thread):
    """監控 / 自動搶票 工作線程"""
    
    def __init__(self, task, db, daemon=True):
        super().__init__(daemon=daemon)
        self.task = task
        self.db = db
        self.should_stop = False
        self.rate_limiter = RateLimiter(task.check_interval)
    
    def stop(self):
        """停止監控"""
        self.should_stop = True
    
    def run(self):
        """主監控 / 搶票循環"""
        _logger.info(f"🤖 [Worker {self.task.task_id}] 已啟動 (mode={self.task.mode})")

        try:
            if not self._wait_until_release():
                return  # 被中途停止

            if self.task.mode == "auto_book":
                self._run_auto_book_loop()
            else:
                self._run_watch_loop()
        except Exception as e:
            _logger.error(f"❌ [Worker {self.task.task_id}] 未預期例外: {e}", exc_info=True)
            self.db.update_task_status(self.task.task_id, "failed", error_msg=str(e))

        _logger.info(f"🛑 [Worker {self.task.task_id}] 已停止")

    # ────────────────────────────────────────────────────────────
    # 開賣時間等待（凌晨自動搶票的核心：時間一到才開始狂送請求）
    # ────────────────────────────────────────────────────────────
    def _wait_until_release(self) -> bool:
        """若使用者有指定 release_at（例如當日凌晨 00:00），就精準睡到那個時間點。
        回傳 False 代表等待期間被使用者停止了任務。"""
        if not self.task.release_at:
            return True
        try:
            release_dt = datetime.fromisoformat(self.task.release_at)
        except Exception:
            _logger.warning(f"⚠️ release_at 格式錯誤，忽略排程直接開始: {self.task.release_at}")
            return True

        while not self.should_stop:
            now = datetime.now()
            remaining = (release_dt - now).total_seconds()
            if remaining <= 0:
                _logger.info(f"⏰ [Worker {self.task.task_id}] 開賣時間已到，開始搶票！")
                return True
            # 越接近開賣時間，睡眠切得越細，確保時間一到立刻行動（不要睡過頭）
            sleep_for = 1 if remaining < 5 else min(remaining, 20)
            time.sleep(sleep_for)
        return False

    # ────────────────────────────────────────────────────────────
    # watch 模式：定期查詢，找到符合條件座位只發通知（比照 thsr-ticket-monitor）
    # ────────────────────────────────────────────────────────────
    def _run_watch_loop(self):
        while not self.should_stop:
            try:
                # 🛠️ 修正：_search_and_filter_once() 現在回傳 (matched, client)，不是 (matched, raw_html)
                matched_train, _client = self._search_and_filter_once()

                self.db.update_task_status(
                    self.task.task_id, "running",
                    last_check=datetime.now().isoformat(),
                    retries_count=self.task.retries_count + 1,
                )
                self.task.retries_count += 1

                if matched_train:
                    _logger.info(f"🎉 [Worker {self.task.task_id}] 找到符合條件的座位！")
                    self._handle_watch_found(matched_train)
                    return

                interval = self.rate_limiter.calculate_interval()
                _logger.info(f"⏳ [Worker {self.task.task_id}] 查無符合條件車次，{interval}秒後重試...")
                for _ in range(interval):
                    if self.should_stop:
                        return
                    time.sleep(1)

            except Exception as e:
                _logger.error(f"❌ [Worker {self.task.task_id}] 查詢出錯: {e}")
                self.db.update_task_status(self.task.task_id, "failed", error_msg=str(e))
                return

    # ────────────────────────────────────────────────────────────
    # auto_book 模式：開賣瞬間高頻嘗試，自動完成整個訂票流程（比照 THSR-Sniper）
    # ────────────────────────────────────────────────────────────
    #def _run_auto_book_loop(self):
    #    deadline = time.time() + max(1, self.task.max_duration_minutes) * 60
    #    attempt = 0
    #
    #    while not self.should_stop and time.time() < deadline:
    #        attempt += 1
    #        try:
    #            self.db.update_task_status(
    #                self.task.task_id, "running",
    #                last_check=datetime.now().isoformat(),
    #                retries_count=attempt,
    #            )
    #            ticket_info = self._attempt_full_booking_cycle()
    #            if ticket_info:
    #                self._handle_auto_book_success(ticket_info)
    #                return
    #        except Exception as e:
    #            _logger.warning(f"⚠️ [Worker {self.task.task_id}] 第 {attempt} 次搶票嘗試失敗: {e}")
    #
    #        # 開賣瞬間人潮眾多，間隔要短，但仍加入抖動避免看起來像固定頻率的機器人
    #        time.sleep(random.uniform(2.5, 6.0))
    #
    #    if not self.should_stop:
    #        _logger.error(f"❌ [Worker {self.task.task_id}] 已超過 {self.task.max_duration_minutes} 分鐘仍未搶到票")
    #        self.db.update_task_status(
    #            self.task.task_id, "failed",
    #            error_msg=f"已嘗試 {attempt} 次，超過 {self.task.max_duration_minutes} 分鐘時間預算仍未成功",
    #        )
    #        self.db.log_event(self.task.task_id, "auto_book_timeout", f"attempts={attempt}")
    #        self._notify(
    #            title="😢 自動搶票逾時",
    #            message=(
    #                f"很抱歉，{self.task.search_date} {self.task.start_station}→{self.task.end_station} "
    #                f"已嘗試 {attempt} 次仍未搶到符合條件的座位，任務已停止。"
    #            ),
    #        )

    # ────────────────────────────────────────────────────────────
    # 共用：建立一次高鐵連線 + 查詢 + 篩選（watch / auto_book 都會用到）
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def _fmt_ticket(count, suffix) -> str:
        """高鐵票種欄位格式為「數量+字母後綴」，例如 1 張全票要送 '1F' 而不是 '1'。
        比照 trading/api/thsr.py 的 thsr_start() 內同名邏輯，避免兩邊格式兜不起來。"""
        try:
            n = int(count)
        except (TypeError, ValueError):
            n = 0
        n = max(0, min(10, n))
        return f"{n}{suffix}"

    def _build_search_params(self) -> dict:
        """比照 trading/api/thsr.py 的 thsr_start()，組出查詢表單參數。
        🛠️ 修正：先前這裡的票數欄位少了高鐵要求的字母後綴（1F/1H/1W/1E/1P），
        座位偏好用的是舊版錯誤代碼 radio17，車廂/座位偏好也對調搞混，
        已對照 THSR訂票流程與參數整理.md 記錄的真實表單欄位全部修正。
        另外新增 trainTypeContainer:typesoftrain：使用者若選「只要早鳥優惠車次」，
        直接請高鐵伺服器端就地過濾只回傳早鳥車次，比之前用 HTML 文字比對「早鳥」字樣可靠得多。"""
        search_time_value = _nearest_time_table_value(self.task.time_window_start, self.task.search_time)
        train_type_val = "1" if self.task.ticket_type_pref == "early_bird" else "0"
        return {
            "tripCon:typesoftrip": "0",  # 單程
            "bookingMethod": "radio31",   # 依時間查詢
            "selectStartStation": self.task.start_station,
            "selectDestinationStation": self.task.end_station,
            "toTimeTable": search_time_value,
            "toTimeInputField": self.task.search_date,
            "ticketPanel:rows:0:ticketAmount": self._fmt_ticket(self.task.adult_num, "F"),
            "ticketPanel:rows:1:ticketAmount": self._fmt_ticket(self.task.child_num, "H"),
            "ticketPanel:rows:2:ticketAmount": self._fmt_ticket(self.task.disabled_num, "W"),
            "ticketPanel:rows:3:ticketAmount": self._fmt_ticket(self.task.elder_num, "E"),
            "ticketPanel:rows:4:ticketAmount": self._fmt_ticket(self.task.college_num, "P"),
            "ticketPanel:rows:5:ticketAmount": self._fmt_ticket(0, "T"),
            "trainCon:trainRadioGroup": str(self.task.seat_class or "0"),      # 車廂：0=標準 1=商務
            "seatCon:seatRadioGroup": str(self.task.seat_prefer or "0"),      # 座位偏好：0=無偏好 1=靠窗 2=靠走道
            "trainTypeContainer:typesoftrain": train_type_val,                 # 0=所有車次 1=限定早鳥
        }

    def _filter_trains(self, trains: List) -> Optional[Any]:
        """依「時間區間」篩選，回傳第一班符合條件的車次（依出發時間排序取最早）。
        🛠️ 修正：trains 現在是 AvailTrains().parse() 回傳的 SimpleNamespace 列表（不是 dict），
        改用屬性存取 t.depart 而非 t.get("depart")；同時早鳥篩選已改由 _build_search_params()
        的 trainTypeContainer:typesoftrain 直接請高鐵伺服器端過濾，這裡不再需要重複用文字比對。"""
        candidates = [t for t in trains if _time_in_window(getattr(t, "depart", ""), self.task.time_window_start, self.task.time_window_end)]
        if not candidates:
            return None
        candidates.sort(key=lambda t: (_parse_hhmm(getattr(t, "depart", "")) if _parse_hhmm(getattr(t, "depart", "")) is not None else 9999))
        return candidates[0]

    def _run_auto_book_loop(self):
        deadline = time.time() + max(1, self.task.max_duration_minutes) * 60
        attempt = 0

        # while 迴圈開始 (縮排 8 格)
        while not self.should_stop and time.time() < deadline:
            sleep_time = random.uniform(5.0, 15.0) # 隨機停頓 5 到 15 秒
            _logger.info(f"模擬人類行為，冷卻 {sleep_time:.2f} 秒...")
            time.sleep(sleep_time)
            attempt += 1
            try:
                # 執行查詢邏輯
                ticket_info = self._attempt_full_booking_cycle()
                if ticket_info:
                    self._handle_auto_book_success(ticket_info)
                    return
            except Exception as e:
                error_msg = str(e)
                _logger.warning(f"⚠️ [Worker {self.task.task_id}] 第 {attempt} 次嘗試失敗: {error_msg}")
                
                # 若偵測到「限流」或「請稍候」，強制冷卻 5 分鐘
                if "限流" in error_msg or "請稍候" in error_msg:
                    _logger.warning("🚫 觸發限流，強制冷卻 300 秒...")
                    time.sleep(300) 
                
                # 這裡的 continue 必須有 16 格縮排，確保它在 except 區塊內
                continue 

            # 正常間隔
            #time.sleep(random.uniform(3.5, 8.0))

        # 結束處理
        if not self.should_stop:
            self._handle_timeout(attempt)

    def _search_and_filter_once(self):
        from trading.api.thsr import YourThsrHttpClient, AvailTrains, _fetch_captcha, _errors_or_none

        client = YourThsrHttpClient()
        params = self._build_search_params()

        # 獲取驗證碼數據
        raw_b64, cleaned_b64, ocr_b64, ai_guess = _fetch_captcha(client)
        
        # --- 除錯功能：儲存辨識失敗的圖片 ---
        if not ai_guess or len(ai_guess) != 4:
            try:
                # 建立除錯目錄 (若不存在)
                debug_dir = "captcha_debug"
                if not os.path.exists(debug_dir):
                    os.makedirs(debug_dir)
                
                # 檔名格式：failed_captcha_20260710111500.png
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = os.path.join(debug_dir, f"failed_captcha_{timestamp}.png")
                
                # 將 Base64 轉為圖片並儲存 (假設 ocr_b64 為 base64 字串)
                with open(filename, "wb") as f:
                    f.write(base64.b64decode(ocr_b64))
                
                _logger.warning(f"[Worker {self.task.task_id}] 辨識失敗，圖片已儲存至: {filename}")
            except Exception as e:
                _logger.error(f"除錯圖片儲存失敗: {e}")

            return None, None

        params["homeCaptcha:securityCode"] = ai_guess
        resp = client.submit_booking_form(params)

        # 2. 檢查限流 (若觸發會拋出 RuntimeError，會被外層 except 捕獲)
        if self.rate_limiter.detect_rate_limit(resp.text if hasattr(resp, "text") else ""):
            raise RuntimeError("偵測到高鐵限流訊息，本輪跳過")

        # 3. 檢查系統錯誤
        errors = _errors_or_none(resp.content)
        if errors:
            _logger.debug(f"[Worker {self.task.task_id}] 查詢未通過：{errors}")
            return None, None

        # 4. 解析車次並篩選
        trains = AvailTrains().parse(resp.content)
        matched = self._filter_trains(trains)
        
        if matched is not None:
            # 修正：使用 setattr 處理 SimpleNamespace 的動態屬性
            setattr(matched, "_client", client)
            return matched, client
            
        return None, None

    # ────────────────────────────────────────────────────────────
    # auto_book 專用：查詢→選車→送出乘客資料 一次完整走完
    # ────────────────────────────────────────────────────────────
    def _attempt_full_booking_cycle(self) -> Optional[Dict[str, Any]]:
        from trading.api.thsr import ConfirmTrain, ConfirmTicket, BookingResult, _errors_or_none

        matched, client = self._search_and_filter_once()
        if not matched or client is None:
            return None

        # 🛠️ 修正：matched 是 SimpleNamespace，沒有 .pop()（那是 dict 的方法）。
        # 直接用屬性存取拿出剛才暫存的 client 即可。
        confirm_train = ConfirmTrain()
        confirm_train.selection = matched.form_value
        confirm_train.field_name = getattr(matched, "form_field", None) or confirm_train.field_name
        train_resp = client.submit_train(confirm_train.get_params())
        errors = _errors_or_none(train_resp.content)
        if errors:
            _logger.debug(f"[Worker {self.task.task_id}] 選車失敗（可能已被搶走）：{errors}")
            return None

        confirm_ticket = ConfirmTicket()
        confirm_ticket.personal_id = self.task.personal_id
        confirm_ticket.phone = self.task.phone
        ticket_resp = client.submit_ticket(confirm_ticket.get_params())
        errors = _errors_or_none(ticket_resp.content)
        if errors:
            _logger.debug(f"[Worker {self.task.task_id}] 送出乘客資料失敗：{errors}")
            return None

        # BookingResult.parse 需要一個看起來像 ThsrSession 的物件，這裡用 SimpleNamespace 組一個輕量版本即可。
        # 🛠️ 修正：params 的 key 要跟 trading/api/thsr.py 的 BookingResult.parse() 實際讀取的欄位一致
        # （trainCon:trainRadioGroup 用來判斷商務/標準車廂），先前這裡沒有帶這個欄位，車廂顯示永遠是預設值。
        fake_book_form = SimpleNamespace(params={
            "selectStartStation": self.task.start_station,
            "selectDestinationStation": self.task.end_station,
            "toTimeInputField": self.task.search_date,
            "ticketPanel:rows:0:ticketAmount": self._fmt_ticket(self.task.adult_num, "F"),
            "ticketPanel:rows:1:ticketAmount": self._fmt_ticket(self.task.child_num, "H"),
            "trainCon:trainRadioGroup": str(self.task.seat_class or "0"),
        })
        fake_train_obj = SimpleNamespace(id=matched.id, depart=matched.depart, arrive=matched.arrive)
        fake_sess = SimpleNamespace(book_form=fake_book_form, selected_train_obj=fake_train_obj)

        ticket = BookingResult().parse(ticket_resp.content, fake_sess)
        return {
            "booking_id": ticket.id,
            "payment_deadline": ticket.payment_deadline,
            "seat_class": ticket.seat_class,
            "ticket_num_info": ticket.ticket_num_info,
            "start_station": ticket.start_station,
            "dest_station": ticket.dest_station,
            "train_id": ticket.train_id,
            "depart_time": ticket.depart_time,
            "arrival_time": ticket.arrival_time,
            "date": ticket.date,
            "seat": ticket.seat,
            "price": ticket.price,
        }

    # ────────────────────────────────────────────────────────────
    # 結果處理
    # ────────────────────────────────────────────────────────────
    def _handle_watch_found(self, matched_train):
        # 🛠️ 修正：matched_train 現在是 SimpleNamespace（見 _search_and_filter_once），
        # 不是 dict，改用屬性存取並用 vars() 取代 .items() 來序列化成 JSON。
        train_dict = {k: v for k, v in vars(matched_train).items() if k != "_client"}
        result_data = json.dumps({"matched_train": train_dict}, ensure_ascii=False)
        self.db.update_task_status(self.task.task_id, "completed", result_data=result_data)
        self.db.log_event(self.task.task_id, "seat_found", f"{self.task.start_station}→{self.task.end_station} {matched_train.depart}")

        discount = getattr(matched_train, "discount", {}) or {}
        note = f"（{discount.get('name')} {discount.get('value')}）" if discount.get("name") and discount.get("name") != "無優惠" else ""
        self._notify(
            title="🎉 您的高鐵監控找到座位了！",
            message=(
                f"日期：{self.task.search_date}\n"
                f"路線：{self.task.start_station} → {self.task.end_station}\n"
                f"車次出發時間：{matched_train.depart}（車次 {matched_train.id}）{note}\n"
                f"請立即前往高鐵訂票頁面完成購票！（此為監控通知模式，系統不會自動幫您購票）"
            ),
        )
        self.db.log_event(self.task.task_id, "notification_sent")

    def _handle_auto_book_success(self, ticket_info: Dict[str, Any]):
        self.db.update_task_status(
            self.task.task_id, "completed",
            result_data=json.dumps(ticket_info, ensure_ascii=False),
        )
        self.db.log_event(self.task.task_id, "auto_book_success", json.dumps(ticket_info, ensure_ascii=False))

        # 🆕 自動搶票成功，跟 Tab 1 手動訂票一樣存一筆本地紀錄，
        # 讓 Tab 3（訂位查詢／取消）可以直接看到這筆自動搶到的票，不用手動輸入訂位代號查詢。
        try:
            from thsr_ticket.records.booking_db import get_booking_db
            get_booking_db().save_booking(
                booking_id=ticket_info.get("booking_id"),
                username=self.task.username,
                source="auto_book",
                personal_id=self.task.personal_id,
                phone=self.task.phone,
                start_station=ticket_info.get("start_station"),
                dest_station=ticket_info.get("dest_station"),
                travel_date=ticket_info.get("date"),
                train_id=ticket_info.get("train_id"),
                depart_time=ticket_info.get("depart_time"),
                arrival_time=ticket_info.get("arrival_time"),
                seat=ticket_info.get("seat"),
                seat_class=ticket_info.get("seat_class"),
                ticket_num_info=ticket_info.get("ticket_num_info"),
                price=ticket_info.get("price"),
                payment_deadline=ticket_info.get("payment_deadline"),
            )
        except Exception as e:
            _logger.error(f"⚠️ 自動搶票成功，但寫入本地紀錄資料庫失敗: {e}")

        self._notify(
            title="🎉 自動搶票成功！",
            message=(
                f"訂位代號：{ticket_info.get('booking_id')}\n"
                f"車次：{ticket_info.get('train_id')} {ticket_info.get('depart_time')}→{ticket_info.get('arrival_time')}\n"
                f"座位：{ticket_info.get('seat')}\n"
                f"票數：{ticket_info.get('ticket_num_info')}\n"
                f"車廂：{ticket_info.get('seat_class')}\n"
                f"票價：{ticket_info.get('price')}\n"
                f"繳費期限：{ticket_info.get('payment_deadline')}\n"
                f"請盡速依繳費期限完成付款！"
            ),
        )
        self.db.log_event(self.task.task_id, "notification_sent")

    def _notify(self, title: str, message: str):
        from .notification import NotificationService
        notif_svc = NotificationService()
        if self.task.notification_line:
            notif_svc.send_line_notification(username=self.task.username, message=f"{title}\n{message}", task_id=self.task.task_id)
        if self.task.notification_email:
            notif_svc.send_email_notification(email=self.task.notification_email, subject=title, body=message, task_id=self.task.task_id)
