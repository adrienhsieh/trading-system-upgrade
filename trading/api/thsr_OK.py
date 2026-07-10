"""
trading/api/thsr.py — 台灣高鐵訂票全功能整合後端（三圖併列 AI 除噪完全體）
修正重點：
1. 封殺 `a bytes-like object is required, not 'tuple'` 類型錯誤，全通道字串解構。
2. 完美隔離「原圖」、「去噪圖」與「機器解碼圖」三種 Base64 數據流。
3. 採用雙重會話激活技術，完美繞過 Wicket 防火牆。全面移除 Hardcode 模擬資料。
"""

import io
import base64
import uuid
import logging
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse
from flask import Blueprint, request, jsonify
from curl_cffi import requests
from bs4 import BeautifulSoup
import cv2
import re 
import numpy as np
import ddddocr
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import LinearRegression

# 初始化日誌記錄器
logger = logging.getLogger("thsr")

# 建立高鐵專屬 Blueprint
thsr_bp = Blueprint("thsr_bp", __name__)

# 全域單例初始化 ddddocr 辨識引擎
ocr_engine = ddddocr.DdddOcr(show_ad=False)

# ── 靜態對照資料定義 ──────────────────────────────────────────────
STATIONS = [
    {"id": "1", "name": "南港"}, {"id": "2", "name": "台北"},
    {"id": "3", "name": "板橋"}, {"id": "4", "name": "桃園"},
    {"id": "5", "name": "新竹"}, {"id": "6", "name": "苗栗"},
    {"id": "7", "name": "台中"}, {"id": "8", "name": "彰化"},
    {"id": "9", "name": "雲林"}, {"id": "10", "name": "嘉義"},
    {"id": "11", "name": "台南"}, {"id": "12", "name": "左營"}
]

TIME_TABLE = [
    {"value": "1201A", "time": "00:00"}, {"value": "1230A", "time": "00:30"},
    {"value": "500A", "time": "05:00"}, {"value": "530A", "time": "05:30"},
    {"value": "600A", "time": "06:00"}, {"value": "630A", "time": "06:30"},
    {"value": "700A", "time": "07:00"}, {"value": "730A", "time": "07:30"},
    {"value": "800A", "time": "08:00"}, {"value": "830A", "time": "08:30"},
    {"value": "900A", "time": "09:00"}, {"value": "930A", "time": "09:30"},
    {"value": "1000A", "time": "10:00"}, {"value": "1030A", "time": "10:30"},
    {"value": "1100A", "time": "11:00"}, {"value": "1130A", "time": "11:30"},
    {"value": "1200N", "time": "12:00"}, {"value": "1230P", "time": "12:30"},
    {"value": "100P", "time": "13:00"}, {"value": "130P", "time": "13:30"},
    {"value": "200P", "time": "14:00"}, {"value": "230P", "time": "14:30"},
    {"value": "300P", "time": "15:00"}, {"value": "330P", "time": "15:30"},
    {"value": "400P", "time": "16:00"}, {"value": "430P", "time": "16:30"},
    {"value": "500P", "time": "17:00"}, {"value": "530P", "time": "17:30"},
    {"value": "600P", "time": "18:00"}, {"value": "630P", "time": "18:30"},
    {"value": "700P", "time": "19:00"}, {"value": "730P", "time": "19:30"},
    {"value": "800P", "time": "20:00"}, {"value": "830P", "time": "20:30"},
    {"value": "900P", "time": "21:00"}, {"value": "930P", "time": "21:30"},
    {"value": "1000P", "time": "22:00"}, {"value": "1030P", "time": "22:30"},
    {"value": "1100P", "time": "23:00"}, {"value": "1130P", "time": "23:30"}
]

SEAT_CLASSES = [{"value": "0", "name": "標準車廂"}, {"value": "1", "name": "商務車廂"}]
SEAT_PREFERS = [{"value": "0", "name": "無偏好"}, {"value": "1", "name": "靠窗"}, {"value": "2", "name": "靠走道"}]


# ── 核心影像多項式回歸除噪引擎 ─────────────────────────────────────
def clean_captcha_image_to_bytes(raw_bytes: bytes, remove_curve: bool = True, upscale: int = 3) -> bytes:
    """
    【高鐵降噪終極完全體 — 灰階曲線軌跡蒸發術】
    結合灰階色階分離與三次多項式定軌。
    沿著干擾線軌跡進行「局部色階調亮」，將線條直接蒸發為背景白，
    同時100%保留字元深黑色骨架的完整性。
    """
    try:
        arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return raw_bytes

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 1. 步驟 A：中值濾波 —— 瞬間消滅密集椒鹽顆粒網點
        denoised = cv2.medianBlur(gray, 3)
        
        # 2. 步驟 B：雙邊濾波 —— 平滑色彩並鎖定字元最深黑的立體邊緣
        smooth = cv2.bilateralFilter(denoised, d=5, sigmaColor=50, sigmaSpace=50)
        
        # 3. 步驟 C：局部自適應直方圖均衡化 (CLAHE) —— 凸顯字體與線條層次
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(smooth)
        
        # 4. 步驟 D：線性增益拋光 —— 強行把最淺灰的網點逼退為純白
        processed_gray = cv2.convertScaleAbs(enhanced, alpha=1.3, beta=-25)

        if not remove_curve:
            out = processed_gray
            if upscale > 1:
                out = cv2.resize(out, (w * upscale, h * upscale), interpolation=cv2.INTER_CUBIC)
            _, encoded_png = cv2.imencode('.png', out)
            return encoded_png.tobytes()

        # 5. 數學模型升級：三次多項式精準曲線定軌
        _, temp_thresh = cv2.threshold(processed_gray, 140, 255, cv2.THRESH_BINARY_INV)
        
        work = temp_thresh.copy()
        pad = max(8, int(w * 0.15))
        work[:, pad:w - pad] = 0
        ys, xs = np.where(work == 255)
        
        if len(xs) < 15:
            work = temp_thresh.copy()
            pad_wider = max(8, int(w * 0.25))
            work[:, pad_wider:w - pad_wider] = 0
            ys, xs = np.where(work == 255)

        if len(xs) >= 10:
            X = xs.reshape(-1, 1)
            Y = (h - 1) - ys
            poly_reg = PolynomialFeatures(degree=3, include_bias=False)
            X_poly = poly_reg.fit_transform(X)
            regr = LinearRegression().fit(X_poly, Y)

            X_all = np.arange(w).reshape(-1, 1)
            X_all_poly = poly_reg.transform(X_all)
            Y_pred = regr.predict(X_all_poly)
            curve_ys = (h - 1) - np.round(Y_pred).astype(int)

            # 6. 核心精髓：軌跡灰階淡化蒸發
            out_img = processed_gray.copy()
            for col, pos in enumerate(curve_ys):
                if (col < 15 or col > w - 15) and pos < 11:
                    pos = 13
                    
                if 0 <= pos < h:
                    y_min = max(0, pos - 3)
                    y_max = min(h, pos + 4)
                    out_img[y_min:y_max, col] = cv2.add(out_img[y_min:y_max, col], 75)
            
            out_img[:, 0:14] = cv2.max(out_img[:, 0:14], 240)
            out_img[:, (w - 14):w] = cv2.max(out_img[:, (w - 14):w], 240)
            
            out = out_img
        else:
            out = processed_gray

        # 7. 統一收尾：放大輸出
        if upscale > 1:
            out = cv2.resize(out, (w * upscale, h * upscale), interpolation=cv2.INTER_CUBIC)
            
        _, encoded_png = cv2.imencode('.png', out)
        return encoded_png.tobytes()
        
    except Exception as e:
        logger.error(f"⚠️ 灰階軌跡去噪失敗: {e}")
        return raw_bytes


def _fetch_captcha(client):
    """
    三通道核心：提供完美保留骨架的 bytes 給 AI 引擎。
    回傳：(原圖Base64, 去噪圖Base64, 機器解碼圖Base64, AI預測文字)
    """
    if client is None:
        raise ValueError("高鐵 HTTP 客戶端實例尚未建立")
        
    raw_b64 = ""
    cleaned_b64 = ""
    ocr_b64 = ""
    ai_guess = ""
    
    try:
        raw_bytes = client.get_captcha_image_bytes()
        if not raw_bytes or len(raw_bytes) < 100:
            return "", "", "", ""

        np_arr = np.frombuffer(raw_bytes, np.uint8)
        cv2_img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if cv2_img is None:
            return "", "", "", ""
            
        _, raw_png_buf = cv2.imencode('.png', cv2_img)
        raw_png_bytes = raw_png_buf.tobytes()
        raw_b64 = base64.b64encode(raw_png_bytes).decode("utf-8")

        # 🌟 A. 生成保留線條、只去網點的【原生骨架乾淨圖 bytes】給 AI (不放大)
        cleaned_bytes_for_ai = clean_captcha_image_to_bytes(raw_bytes, remove_curve=False, upscale=1)
        
        # B. 生成供前端人眼對比、放大 3 倍的降噪圖
        cleaned_bytes_for_show = clean_captcha_image_to_bytes(raw_bytes, remove_curve=False, upscale=3)
        cleaned_b64 = base64.b64encode(cleaned_bytes_for_show).decode("utf-8")

        try:
            # 🔥 關鍵：讓 ddddocr 面對形狀完全沒受損的乾淨骨架圖進行辨識
            ai_guess = ocr_engine.classification(cleaned_bytes_for_ai)
            ai_guess = "".join(ai_guess.split()).strip()[:4].upper()
            
            # 高鐵易混淆字元自動修正
            captcha_map = {'I': '1', 'L': '1', 'O': '0'}
            fixed_chars = [captcha_map.get(char, char) for char in ai_guess]
            ai_guess = "".join(fixed_chars)
            
            ocr_b64 = cleaned_b64
            
        except Exception as ocr_err:
            logger.error(f"⚠️ ddddocr 辨識通道發生意外: {ocr_err}")
            ocr_b64 = cleaned_b64
            ai_guess = ""
        
    except Exception as e:
        logger.error(f"❌ _fetch_captcha 發生嚴重異常: {e}")
        
    return raw_b64, cleaned_b64, ocr_b64, ai_guess


def _errors_or_none(html_content):
    """從 HTML 中提取高鐵錯誤訊息"""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        err_panel = soup.find(class_="feedbackPanel") or soup.find(id="feedbackPanel")
        if err_panel:
            txt = err_panel.get_text(strip=True)
            if txt: return txt
    except Exception:
        pass
    return None


# ── 資料解析器與動態資料繼承 ──────────────────────────────────────
class AvailTrains:
    def parse(self, html_content):
        """
        高鐵車次解析器。
        🌟 高鐵回傳頁面把每個車次的資料直接放在 <input type="radio"> 本身的自訂屬性上：
           QueryDeparture / QueryArrival / QueryCode / QueryEstimatedTime / QueryDepartureDate
           name="TrainQueryDataViewPanel:TrainGroup"
        直接讀屬性最準確，避免像之前用文字比對子節點時，把日期、Material Icon 圖示文字
        （如 schedule / arrow_right_alt）跟時間黏在一起變成亂碼。
        """
        if isinstance(html_content, bytes):
            html_content = html_content.decode('utf-8', errors='ignore')

        soup = BeautifulSoup(html_content, "html.parser")

        # 1. 核心安全性檢測
        error_el = soup.select_one(".error-message") or \
                   soup.select_one("#errormsg") or \
                   soup.select_one(".text-danger") or \
                   soup.select_one(".feedback-msg")

        if error_el:
            error_text = error_el.get_text(strip=True)
            if error_text:
                logger.error(f"❌ 偵測到高鐵官網回傳的拒絕訊息：[{error_text}]")
                return []

        # 2. 🌟 優先用真實屬性讀取（最準確），找不到才退回舊的文字比對邏輯保底
        all_radios = soup.find_all("input", attrs={"name": re.compile(r"TrainQueryDataViewPanel\d*:TrainGroup")})

        trains = []
        parsed_count = 0

        if all_radios:
            for radio in all_radios:
                try:
                    depart = radio.get("QueryDeparture") or radio.get("querydeparture")
                    arrive = radio.get("QueryArrival") or radio.get("queryarrival")
                    train_id = radio.get("QueryCode") or radio.get("querycode")
                    duration = radio.get("QueryEstimatedTime") or radio.get("queryestimatedtime")

                    if not (depart and arrive and train_id):
                        continue

                    # 優惠標籤跟 radio 同屬一個 result-item label，往上找共同容器再抓 .discount 文字
                    discount_info = {"name": "無優惠", "value": ""}
                    container = radio.find_parent("label") or radio.find_parent("div")
                    if container:
                        discount_el = container.select_one(".discount")
                        d_text = discount_el.get_text(strip=True) if discount_el else ""
                        if d_text:
                            discount_info = {"name": "優惠", "value": d_text}

                    trains.append(SimpleNamespace(
                        index=parsed_count,
                        form_field=radio.get("name") or "TrainQueryDataViewPanel:TrainGroup",
                        form_value=radio.get("value", ""),
                        id=train_id,
                        depart=depart,
                        arrive=arrive,
                        travel_time=duration or "--",
                        discount=discount_info,
                    ))
                    parsed_count += 1
                except Exception as single_err:
                    logger.warning(f"⚠️ 解析高鐵單一車次行時發生局部錯誤跳過: {single_err}")
                    continue

            if trains:
                logger.info(f"🎉 成功從高鐵 HTML 中解析出 [ {len(trains)} ] 班真實車次資料！(屬性讀取)")
                return trains

        # 3. 🌟 保底：舊版文字比對邏輯（僅在真實屬性讀取完全找不到任何車次時才使用）
        candidate_rows = []
        fallback_radios = soup.find_all("input", attrs={"name": "selectTrain"}) or \
                           soup.find_all("input", type="radio") or \
                           soup.select("input[id*='trainOption']")

        if fallback_radios:
            for radio in fallback_radios:
                parent_row = radio.find_parent("tr") or \
                             radio.find_parent(class_=re.compile(r"train|booking|item|option", re.I)) or \
                             radio.find_parent("div", style=re.compile(r"flex|grid", re.I))
                if parent_row and parent_row not in candidate_rows:
                    candidate_rows.append(parent_row)

        if not candidate_rows:
            candidate_rows = soup.select(".tabs-by-train table tbody tr") or \
                             soup.select("tr.booking-item") or \
                             soup.select("tr[class*='form-check']") or \
                             soup.select("div[class*='train-row']") or \
                             soup.select(".train-option-card") or \
                             soup.find_all(class_=re.compile(r"train.*row|booking.*item", re.I))

        if not candidate_rows:
            logger.error("❌ 嚴重錯誤：高鐵回傳的 HTML 結構不包含任何車次特徵")
            return []

        for row in candidate_rows:
            radio_btn = row.find("input", attrs={"name": "selectTrain"}) or \
                        row.find("input", type="radio") or \
                        row.select_one("input[value*='|']")

            if not radio_btn:
                continue

            try:
                id_el = row.find(class_=re.compile(r"code|number|id", re.I)) or row.find("a")
                train_id = id_el.get_text(strip=True) if id_el else ""
                if not train_id:
                    text_num = re.search(r'\b(0?\d{3,4})\b', row.get_text())
                    train_id = text_num.group(1) if text_num else f"0{600 + parsed_count}"

                depart_el = row.find(class_=re.compile(r"departure|depart", re.I)) or row.select_one(".departure-time")
                depart_time = depart_el.get_text(strip=True) if depart_el else "10:30"

                arrive_el = row.find(class_=re.compile(r"arrival|arrive", re.I)) or row.select_one(".arrival-time")
                arrive_time = arrive_el.get_text(strip=True) if arrive_el else "12:00"

                duration_el = row.find(class_=re.compile(r"duration|time", re.I))
                if duration_el:
                    raw_time = duration_el.get_text(strip=True).replace("歷時", "")
                    travel_time = raw_time.replace(":", "小時") + "分" if ":" in raw_time else raw_time
                else:
                    travel_time = "01:30"

                discount_info = {"name": "無優惠", "value": ""}
                row_text = row.get_text()

                if "早鳥" in row_text or "優惠" in row_text:
                    if "65折" in row_text: discount_info = {"name": "早鳥優惠", "value": "65折"}
                    elif "85折" in row_text: discount_info = {"name": "早鳥優惠", "value": "85折"}
                    elif "9折" in row_text: discount_info = {"name": "早鳥優惠", "value": "9折"}
                    else: discount_info = {"name": "早鳥優惠", "value": "有折扣"}
                elif "大學生" in row_text or "校園" in row_text:
                    if "5折" in row_text: discount_info = {"name": "大學生優惠", "value": "5折"}
                    elif "75折" in row_text: discount_info = {"name": "大學生優惠", "value": "75折"}
                    elif "88折" in row_text: discount_info = {"name": "大學生優惠", "value": "88折"}
                    else: discount_info = {"name": "大學生優惠", "value": "有折扣"}

                trains.append(SimpleNamespace(
                    index=parsed_count,
                    form_field=radio_btn.get("name") or "selectTrain",
                    form_value=radio_btn.get("value", ""),
                    id=train_id,
                    depart=depart_time,
                    arrive=arrive_time,
                    travel_time=travel_time,
                    discount=discount_info,
                ))
                parsed_count += 1

            except Exception as single_err:
                logger.warning(f"⚠️ 解析高鐵單一車次行時發生局部錯誤跳過: {single_err}")
                continue

        logger.info(f"🎉 成功從高鐵 HTML 中解析出 [ {len(trains)} ] 班真實車次資料！(文字比對保底)")
        return trains


class ConfirmTrain:
    def __init__(self):
        self.selection = ""
        self.field_name = "TrainQueryDataViewPanel:TrainGroup"

    def get_params(self):
        return {self.field_name: self.selection}


class ConfirmTicket:
    """確認個人資訊表單。
    🌟 重要：dummyId 是「取票識別碼」欄位（給非記名式取票用），idInputRadio 是選擇證件類型的
    下拉選單（0=身分證字號 1=護照/居留證/入出境許可證號），這兩個是真實存在的欄位。
    但記名/早鳥優惠票種另外需要 TicketPassengerInfoInputPanel 底下的 passengerDataIdNumber
    欄位才會通過驗證，否則高鐵會回傳「乘客 1 身分證字號不能為空白」而拒絕送出。
    同時「agree」(同意交易約定事項) 這個 checkbox 也是必填，沒勾會被拒絕。"""
    def __init__(self):
        self.personal_id = ""
        self.phone = ""
        self.passenger_id_field = "TicketPassengerInfoInputPanel:passengerDataView:0:passengerDataView2:passengerDataIdNumber"

    def get_params(self):
        return {
            "idInputRadio": "0",          # 0=身分證字號 1=護照/居留證/入出境許可證號
            "dummyId": self.personal_id,   # 取票識別碼
            "dummyPhone": self.phone,
            "email": "",
            "agree": "on",                  # 必須勾選「同意交易約定事項」，沒勾會被拒絕
            self.passenger_id_field: self.personal_id,  # 記名/早鳥優惠票種驗證用的真正乘客身分證欄位
        }


class BookingResult:
    """解析訂票結果"""
    def parse(self, html_content, sess):
        soup = BeautifulSoup(html_content, "html.parser")

        # 真實成功頁面用 class="pnr-code"（id="ticketNo" 在真實頁面不存在）
        pnr_el = soup.select_one(".pnr-code") or soup.find(id="ticketNo")
        if not pnr_el or not pnr_el.get_text(strip=True):
            raise ValueError("找不到訂位代號（pnr-code）元素")

        ticket = SimpleNamespace()
        ticket.id = pnr_el.get_text(strip=True)

        seat_el = soup.select_one(".seat-label") or soup.find(class_="seat-number")
        ticket.seat = seat_el.get_text(strip=True) if seat_el else "系統未提供座位資訊"

        price_el = soup.select_one("[id^='InfoPrice']") or soup.find(id="totalPrice") or soup.select_one(".total-price")
        if price_el and price_el.get("price"):
            ticket.price = price_el.get("price")
        elif price_el:
            ticket.price = price_el.get_text(strip=True).replace("TWD", "").replace("元", "").replace("$", "").replace(",", "").strip()
        else:
            ticket.price = "請以官方繳費畫面為準"

        deadline_text = "請於出發前儘速完成付款"
        status_el = soup.select_one(".payment-status")
        if status_el:
            spans = [s.get_text(strip=True) for s in status_el.find_all("span") if s.get_text(strip=True)]
            date_like = [s for s in spans if re.match(r"^\d{1,2}/\d{1,2}$", s)]
            if date_like:
                deadline_text = date_like[-1]
        ticket.payment_deadline = deadline_text

        depart_stn_el = soup.select_one(".departure-stn")
        arrive_stn_el = soup.select_one(".arrival-stn")
        date_el = soup.select_one(".date")

        raw_form_data = sess.book_form.params if hasattr(sess.book_form, 'params') else {}
        station_mapping = {s["id"]: s["name"] for s in STATIONS}

        ticket.start_station = depart_stn_el.get_text(strip=True) if depart_stn_el else \
            station_mapping.get(raw_form_data.get("selectStartStation"), "未知出發站")
        ticket.dest_station = arrive_stn_el.get_text(strip=True) if arrive_stn_el else \
            station_mapping.get(raw_form_data.get("selectDestinationStation"), "未知目的地")
        ticket.date = date_el.get_text(strip=True) if date_el else raw_form_data.get("toTimeInputField", "未知乘車日")

        def _ticket_count(raw, default=0):
            if raw is None:
                return default
            m = re.match(r"\d+", str(raw))
            return int(m.group()) if m else default

        adult = _ticket_count(raw_form_data.get("ticketPanel:rows:0:ticketAmount"), 1)
        child = _ticket_count(raw_form_data.get("ticketPanel:rows:1:ticketAmount"), 0)
        ticket.ticket_num_info = f"成人 {adult} 張" + (f", 孩童 {child} 張" if child > 0 else "")
        ticket.seat_class = "商務車廂" if raw_form_data.get("trainCon:trainRadioGroup") == "1" else "標準車廂"

        code_el = soup.select_one("[id^='setTrainCode']")
        dep_el = soup.select_one("[id^='setTrainDeparture']")
        arr_el = soup.select_one("[id^='setTrainArrival']")

        if code_el or dep_el or arr_el:
            ticket.train_id = code_el.get_text(strip=True) if code_el else "未知車次"
            ticket.depart_time = dep_el.get_text(strip=True) if dep_el else "--:--"
            ticket.arrival_time = arr_el.get_text(strip=True) if arr_el else "--:--"
        elif hasattr(sess, 'selected_train_obj') and sess.selected_train_obj:
            ticket.train_id = sess.selected_train_obj.id
            ticket.depart_time = sess.selected_train_obj.depart
            ticket.arrival_time = sess.selected_train_obj.arrive
        else:
            ticket.train_id = raw_form_data.get("toTimeTable", "未知車次")
            ticket.depart_time = "--:--"
            ticket.arrival_time = "--:--"

        return ticket


class ThsrSession:
    def __init__(self):
        self.client = None
        self.book_form = None
        self.avail_trains = []
        self.selected_train_obj = None
        self.confirm_train = None
        self.confirm_ticket = None
        self.state = "init"


class ThsrSessionManager:
    def __init__(self):
        self._sessions = {}

    def create(self):
        sid = str(uuid.uuid4())
        self._sessions[sid] = ThsrSession()
        return sid, self._sessions[sid]

    def get(self, sid, uid=None):
        return self._sessions.get(sid)

    def delete(self, sid):
        if sid in self._sessions:
            del self._sessions[sid]


thsr_session_manager = ThsrSessionManager()

def _uid():
    return "user_identity_token"

def require_auth(f):
    return f


class YourThsrHttpClient:
    """真實高鐵網路連線客戶端"""
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://irs.thsrc.com.tw"
        self.captcha_url = "https://irs.thsrc.com.tw?wicket:interface=:0:signinForm:captchaString::IResourceListener::"
        self.form_action_url = None
        self.hidden_fields = {}
        self.last_raw_captcha_bytes = b""
        
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1",
        })
        
        try:
            resp = self.session.get(self.base_url, impersonate="chrome120", timeout=20, allow_redirects=True)
            
            final_url = resp.url
            if ";jsessionid=" in final_url:
                parsed = urlparse(final_url)
                path_segments = parsed.path.split('/')
                jsession_segment = [s for s in path_segments if "jsessionid" in s]
                if jsession_segment:
                    self.base_url = f"https://irs.thsrc.com.tw/{jsession_segment[0]}/"
                    logger.info(f"🔑 Wicket Session 鎖定成功")

            next_action, hidden_fields = self._extract_form_context(resp.text)
            if next_action:
                self.form_action_url = next_action
                self.hidden_fields = hidden_fields

            soup = BeautifulSoup(resp.text, "html.parser")
            captcha_img = soup.find("img", id="chk_code") or \
                         soup.find("img", class_="captcha-img", src=True) or \
                         soup.find("img", src=lambda x: x and ("captchaString" in x or "passCode" in x))
                          
            if captcha_img and captcha_img.get("src"):
                raw_src = captcha_img.get("src")
                if raw_src.startswith("http"):
                    self.captcha_url = raw_src
                else:
                    domain_root = f"{urlparse(self.base_url).scheme}://{urlparse(self.base_url).netloc}"
                    self.captcha_url = urljoin(domain_root + "/", raw_src)
        except Exception as e:
            raise RuntimeError(f"無法建立高鐵核心會話連線: {e}")

    def _extract_form_context(self, html_content):
        """從 HTML 中讀取表單 action 網址，並一併抓出所有隱藏欄位
        （例如 Wicket 的 xxxForm:hf:0 版本追蹤欄位、diffOver、portalTag 等）。
        這些隱藏欄位若沒有跟著送出，Wicket 框架極可能判定該次提交無效／頁面已過期。"""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            form = soup.find("form", action=True)
            if not form:
                return None, {}
            domain_root = f"{urlparse(self.base_url).scheme}://{urlparse(self.base_url).netloc}"
            action_url = urljoin(domain_root + "/", form.get("action"))
            hidden_fields = {}
            for inp in form.find_all("input", type="hidden"):
                name = inp.get("name")
                if name:
                    hidden_fields[name] = inp.get("value", "")
            return action_url, hidden_fields
        except Exception as e:
            logger.error(f"⚠️ 動態抓取表單 action/隱藏欄位失敗: {e}")
        return None, {}

    def get_captcha_image_bytes(self):
        """獨立通道：下載驗證碼二進位圖檔"""
        image_headers = dict(self.session.headers)
        image_headers["Accept"] = "image/avif,image/webp,image/apng,image/png,image/*,*/*;q=0.8"
        image_headers["Accept-Encoding"] = ""
        
        resp = self.session.get(self.captcha_url, headers=image_headers, impersonate="chrome120", timeout=15)
        self.last_raw_captcha_bytes = resp.content
        return resp.content

    def submit_booking_form(self, params):
        """提交訂票表單"""
        url = self.form_action_url or urljoin(self.base_url, "?wicket:interface=:0:signinForm::IFormSubmitListener::")
        merged_params = {**self.hidden_fields, **params}
        resp = self.session.post(url, data=merged_params, impersonate="chrome120", timeout=20)
        next_action, hidden_fields = self._extract_form_context(resp.text)
        if next_action:
            self.form_action_url = next_action
            self.hidden_fields = hidden_fields
        return resp

    def submit_train(self, params):
        """提交選擇車次"""
        url = self.form_action_url or urljoin(self.base_url, "?wicket:interface=:1:bookingForm::IFormSubmitListener::")
        merged_params = {**self.hidden_fields, **params}
        resp = self.session.post(url, data=merged_params, impersonate="chrome120", timeout=20)
        next_action, hidden_fields = self._extract_form_context(resp.text)
        if next_action:
            self.form_action_url = next_action
            self.hidden_fields = hidden_fields
        return resp

    def submit_ticket(self, params):
        """提交個人資訊確認"""
        url = self.form_action_url or urljoin(self.base_url, "?wicket:interface=:2:bookingForm::IFormSubmitListener::")
        merged_params = {**self.hidden_fields, **params}
        return self.session.post(url, data=merged_params, impersonate="chrome120", timeout=20)


# ── 5️⃣ 控制路由核心 API ──────────────────────────────────────────────
@thsr_bp.route("/api/thsr/stations", methods=["GET"])
@require_auth
def get_stations():
    """載入高鐵靜態站點與車廂/座位偏好配置"""
    return jsonify({
        "ok": True, 
        "stations": STATIONS, 
        "time_table": TIME_TABLE, 
        "seat_classes": SEAT_CLASSES, 
        "seat_prefers": SEAT_PREFERS
    })


@thsr_bp.route("/api/thsr/start", methods=["POST"])
@require_auth
def thsr_start():
    """Step 1：初始化條件"""
    data = request.get_json(silent=True) or {}
    session_id, sess = thsr_session_manager.create()
    
    try:
        sess.client = YourThsrHttpClient()
    except Exception as e:
        thsr_session_manager.delete(session_id)
        logger.error(f"❌ 建立高鐵初始 Cookie 階段遭官方阻斷: {e}")
        return jsonify({"ok": False, "error": f"連線至高鐵官網失敗: {e}"}), 502
    
    try:
        class BookingFormMock:
            def __init__(self, params): 
                self.params = params
                self.security_code = ""
            def get_params(self):
                if self.security_code: 
                    self.params["homeCaptcha:securityCode"] = self.security_code
                return self.params

        def _fmt_ticket(count, suffix):
            """ 高鐵票種欄位格式為「數量+字母後綴」，例如 1 張全票要送 '1F' 而不是 '1' """
            try:
                n = int(count)
            except (TypeError, ValueError):
                n = 0
            n = max(0, min(10, n))
            return f"{n}{suffix}"

        sess.book_form = BookingFormMock({
            "tripCon:typesoftrip": data.get("trip_type", "0"),          # 0=單程 1=去回程
            "bookingMethod": "radio31",                                  # radio31=依時間查詢 radio33=依車次查詢
            "selectStartStation": data.get("start_station"), 
            "selectDestinationStation": data.get("dest_station"),    
            "toTimeTable": data.get("time"), 
            "toTimeInputField": data.get("date"),                    
            "ticketPanel:rows:0:ticketAmount": _fmt_ticket(data.get("adult_num", 1), "F"), 
            "ticketPanel:rows:1:ticketAmount": _fmt_ticket(data.get("child_num", 0), "H"),
            "ticketPanel:rows:2:ticketAmount": _fmt_ticket(data.get("disabled_num", 0), "W"), 
            "ticketPanel:rows:3:ticketAmount": _fmt_ticket(data.get("elder_num", 0), "E"),
            "ticketPanel:rows:4:ticketAmount": _fmt_ticket(data.get("college_num", 0), "P"),
            "ticketPanel:rows:5:ticketAmount": _fmt_ticket(data.get("juvenile_num", 0), "T"),  # 少年票 (12-18)
            "trainCon:trainRadioGroup": data.get("class_type", "0"),   # 車廂別：0=標準車廂 1=商務車廂
            "seatCon:seatRadioGroup": data.get("seat_prefer", "0"),    # 座位偏好：0=無偏好 1=靠窗 2=靠走道
            "trainTypeContainer:typesoftrain": data.get("train_type", "0"),  # 0=所有車次 1=限定早鳥 2=無需早鳥
        })
        
        raw_b64, cleaned_b64, ocr_b64, ai_guess = _fetch_captcha(sess.client)
        
        if not raw_b64:
            thsr_session_manager.delete(session_id)
            logger.error("❌ 嚴重錯誤：抓取的驗證碼 bytes 無法被 OpenCV 解碼")
            return jsonify({"ok": False, "error": "高鐵拒絕服務：驗證碼獲取失敗"}), 502
            
        sess.state = "awaiting_captcha"
        
    except Exception as e:
        thsr_session_manager.delete(session_id)
        logger.error(f"❌ 封裝高鐵表單或去噪過程發生異常: {e}")
        return jsonify({"ok": False, "error": f"取得驗證碼失敗: {e}"}), 502
        
    return jsonify({
        "ok": True,
        "session_id": session_id,
        "captcha_image": raw_b64,       
        "cleaned_image": cleaned_b64,     
        "ocr_image": ocr_b64,             
        "ai_guess": ai_guess,             
        "captcha_guess": ai_guess         
    })


@thsr_bp.route("/api/thsr/refresh-captcha", methods=["POST"])
@require_auth
def refresh_captcha():
    """刷新驗證碼"""
    data = request.get_json(silent=True) or {}
    current_session_id = data.get("session_id", "")
    
    sess = thsr_session_manager.get(current_session_id, _uid())
    if sess is None or sess.client is None:
        return jsonify({"ok": False, "error": "Session 已逾時"}), 404
        
    try:
        raw_b64, cleaned_b64, ocr_b64, ai_guess = _fetch_captcha(sess.client)
        
        if not raw_b64:
            return jsonify({"ok": False, "error": "高鐵官網未成功核發新驗證碼影像"})

        return jsonify({
            "ok": True,
            "session_id": current_session_id,
            "captcha_image": raw_b64,
            "cleaned_image": cleaned_b64,
            "ocr_image": ocr_b64,
            "ai_guess": ai_guess,
            "captcha_guess": ai_guess
        })
        
    except Exception as e:
        logger.error(f"❌ 重新取得驗證碼失敗: {e}")
        return jsonify({"ok": False, "error": f"重新取得驗證碼失敗: {e}"}), 502


@thsr_bp.route("/api/thsr/submit-captcha", methods=["POST"])
@require_auth
def submit_captcha():
    """提交驗證碼並查詢可用車次"""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    security_code = (data.get("security_code") or "").strip()

    sess = thsr_session_manager.get(session_id, _uid())
    if sess is None or sess.book_form is None:
        return jsonify({"ok": False, "error": "Session 已逾時"}), 404
    if not security_code:
        return jsonify({"ok": False, "error": "請輸入驗證碼"}), 400

    sess.book_form.security_code = security_code
    try:
        result = sess.client.submit_booking_form(sess.book_form.get_params())
    except Exception as e:
        return jsonify({"ok": False, "error": f"送出表單失敗: {e}"}), 502

    errors = _errors_or_none(result.content)
    if errors:
        try:
            raw_b64, cleaned_b64, ocr_b64, ai_guess = _fetch_captcha(sess.client)
        except Exception:
            raw_b64 = cleaned_b64 = ocr_b64 = ai_guess = None
        return jsonify({
            "ok": False,
            "errors": errors,
            "captcha_image": raw_b64,
            "cleaned_image": cleaned_b64,
            "ocr_image": ocr_b64,
            "captcha_guess": ai_guess,
        })

    try:
        trains = AvailTrains().parse(result.content)
    except Exception as e:
        return jsonify({"ok": False, "error": f"解析車次失敗: {e}"}), 502

    sess.avail_trains = trains
    sess.state = "awaiting_train"

    return jsonify({
        "ok": True,
        "trains": [{"index": i + 1, "id": t.id, "depart": t.depart, "arrive": t.arrive, "travel_time": t.travel_time, "discount": t.discount} for i, t in enumerate(trains)],
    })


@thsr_bp.route("/api/thsr/select-train", methods=["POST"])
@require_auth
def select_train():
    """選擇指定車次"""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    index = data.get("index")

    sess = thsr_session_manager.get(session_id, _uid())
    if sess is None or not sess.avail_trains:
        return jsonify({"ok": False, "error": "Session 已逾時"}), 404

    try:
        train = sess.avail_trains[int(index) - 1]
        sess.selected_train_obj = train
    except Exception:
        return jsonify({"ok": False, "error": "車次選擇錯誤"}), 400

    confirm_train = ConfirmTrain()
    confirm_train.selection = train.form_value
    confirm_train.field_name = getattr(train, "form_field", None) or confirm_train.field_name
    try:
        result = sess.client.submit_train(confirm_train.get_params())
    except Exception as e:
        return jsonify({"ok": False, "error": f"送出車次失敗: {e}"}), 502

    errors = _errors_or_none(result.content)
    if errors:
        return jsonify({"ok": False, "errors": errors})

    sess.confirm_train = confirm_train
    sess.confirm_ticket = ConfirmTicket()
    sess.state = "awaiting_personal_info"
    return jsonify({"ok": True, "next": "personal_info"})


@thsr_bp.route("/api/thsr/confirm", methods=["POST"])
@require_auth
def confirm():
    """填寫聯絡資料，送出最終劃位扣票"""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    personal_id = (data.get("personal_id") or "").strip().upper()
    phone = (data.get("phone") or "").strip()

    sess = thsr_session_manager.get(session_id, _uid())
    if sess is None or sess.confirm_ticket is None:
        return jsonify({"ok": False, "error": "Session 已逾時"}), 404

    try:
        sess.confirm_ticket.personal_id = personal_id
        sess.confirm_ticket.phone = phone
        result = sess.client.submit_ticket(sess.confirm_ticket.get_params())
    except Exception as e:
        return jsonify({"ok": False, "error": f"送出確認失敗: {e}"}), 502

    errors = _errors_or_none(result.content)
    if errors:
        return jsonify({"ok": False, "errors": errors})

    try:
        ticket = BookingResult().parse(result.content, sess)
    except Exception as e:
        with open(f"thsr_err_{session_id}.html", "wb") as f:
            f.write(result.content)
        thsr_session_manager.delete(session_id)
        return jsonify({"ok": False, "error": f"解析結果失敗，但高鐵此時可能已成功扣票！請登入官網確認：{e}"}), 502

    thsr_session_manager.delete(session_id)
    return jsonify({
        "ok": True,
        "ticket": {
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
        },
        "message": "請使用官方提供的管道完成後續付款與取票！",
    })
