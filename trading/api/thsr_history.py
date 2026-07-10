"""
trading/api/thsr_history.py — 高鐵「訂位紀錄查詢」與「取消訂位」（Tab 3）

對照 THSR訂票流程與參數整理.md 第 2、3 節的真實欄位實作：

  查詢（HistoryForm）：
    typesofid              取票識別碼證件類型（0=身分證 1=護照/居留證/入出境許可證號）
    rocId                   證件號碼
    orderId                 訂位代號（8碼）
    divCaptcha:securityCode 驗證碼

  取消（先走一個 GET 連結，再送一個表單）：
    Step A：查詢結果頁上的「取消訂位」是 Wicket 的 ILinkListener（超連結 GET），
            不是表單提交，要從結果頁 HTML 動態抓出這個連結的網址再訪問它。
    Step B：抵達 HistoryDetailsCancelForm 後，勾選 agree + 送出 SubmitButton。
    成功文字：「訂位代號 {PNR} 取消訂位成功！」

⚠️ 高鐵首頁本身同時有「訂票」跟「訂位查詢／取消」兩個分頁（Wicket Tab 元件切換）。
分頁連結本身帶的 wicket:interface 編號每次連線都不同，不能寫死，所以這裡走跟
YourThsrHttpClient 一樣的原則：先 GET 首頁建立 session，再從首頁 HTML 動態找出
「訂位查詢」分頁連結並跟著點過去，抓真正的 HistoryForm action 網址、隱藏欄位、
驗證碼網址。如果高鐵改版導致這個連結特徵抓不到，會丟出清楚的錯誤訊息，
提醒需要對照當下真實頁面調整比對關鍵字（而不是默默送出錯的網址）。
"""
import re
import logging
from urllib.parse import urljoin, urlparse
from types import SimpleNamespace

from flask import Blueprint, request, jsonify, g
from curl_cffi import requests
from bs4 import BeautifulSoup

from trading.api.thsr import (
    YourThsrHttpClient, _fetch_captcha, _errors_or_none, STATIONS,
)
from thsr_ticket.records.booking_db import get_booking_db

logger = logging.getLogger("thsr_history")

thsr_history_bp = Blueprint("thsr_history_bp", __name__)


def require_auth(f):
    return f


def _current_username() -> str:
    return getattr(g, "current_username", "") or "default"


# ── 高鐵「訂位查詢／取消」專用連線客戶端 ──────────────────────────────
class ThsrHistoryClient(YourThsrHttpClient):
    """延續 YourThsrHttpClient 的 session bootstrap（建立 cookies），
    但額外動態切換到「訂位查詢」分頁，取得 HistoryForm 真正的 action 網址與驗證碼。"""

    def __init__(self):
        super().__init__()
        self._switch_to_history_tab()

    def _switch_to_history_tab(self):
        try:
            resp = self.session.get(self.base_url, impersonate="chrome120", timeout=20)
            soup = BeautifulSoup(resp.text, "html.parser")

            link = None
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                href = a["href"]
                if any(k in text for k in ("訂位查詢", "取消訂位", "查詢/取消", "訂位紀錄", "History", "history")) or \
                   any(k in href for k in ("History", "history", "query")):
                    link = a
                    break

            if link is None:
                raise RuntimeError(
                    "在高鐵首頁 HTML 中找不到「訂位查詢」分頁的連結特徵。"
                    "高鐵網站可能已改版，請開啟瀏覽器開發者工具確認目前真實的連結文字/href後，"
                    "更新 thsr_history.py 的 _switch_to_history_tab() 比對關鍵字。"
                )

            domain_root = f"{urlparse(self.base_url).scheme}://{urlparse(self.base_url).netloc}"
            history_url = urljoin(domain_root + "/", link["href"])
            resp2 = self.session.get(history_url, impersonate="chrome120", timeout=20)

            next_action, hidden_fields = self._extract_form_context(resp2.text)
            if next_action:
                self.form_action_url = next_action
                self.hidden_fields = hidden_fields

            soup2 = BeautifulSoup(resp2.text, "html.parser")
            captcha_img = soup2.find("img", src=lambda x: x and ("passCode" in x or "divCaptcha" in x)) or \
                          soup2.find("img", id=re.compile(r"captcha", re.I))
            if captcha_img and captcha_img.get("src"):
                raw_src = captcha_img["src"]
                self.captcha_url = raw_src if raw_src.startswith("http") else urljoin(domain_root + "/", raw_src)

        except Exception as e:
            raise RuntimeError(f"無法切換至高鐵「訂位查詢」頁面：{e}")

    def submit_history_query(self, params):
        url = self.form_action_url or urljoin(self.base_url, "?wicket:interface=:0:HistoryForm::IFormSubmitListener::")
        merged = {**self.hidden_fields, **params}
        resp = self.session.post(url, data=merged, impersonate="chrome120", timeout=20)
        next_action, hidden_fields = self._extract_form_context(resp.text)
        if next_action:
            self.form_action_url = next_action
            self.hidden_fields = hidden_fields
        return resp

    def follow_cancel_link(self, html_content):
        """從查詢結果頁裡找出「取消訂位」的 ILinkListener 連結並直接 GET 它（超連結，不是表單提交）"""
        soup = BeautifulSoup(html_content, "html.parser")
        link = soup.find("a", href=re.compile(r"CancelSeatsButton.*ILinkListener", re.I)) or \
               soup.find("a", string=re.compile(r"取消訂位"))
        if not link or not link.get("href"):
            raise RuntimeError("找不到「取消訂位」連結，這筆訂位可能已經取消過、已搭乘完畢，或已超過可取消時限")
        domain_root = f"{urlparse(self.base_url).scheme}://{urlparse(self.base_url).netloc}"
        cancel_url = urljoin(domain_root + "/", link["href"])
        resp = self.session.get(cancel_url, impersonate="chrome120", timeout=20)
        next_action, hidden_fields = self._extract_form_context(resp.text)
        if next_action:
            self.form_action_url = next_action
            self.hidden_fields = hidden_fields
        return resp

    def submit_cancel_confirm(self, params):
        url = self.form_action_url or urljoin(self.base_url, "?wicket:interface=:0:HistoryDetailsCancelForm::IFormSubmitListener::")
        merged = {**self.hidden_fields, **params}
        return self.session.post(url, data=merged, impersonate="chrome120", timeout=20)


# ── 查詢結果解析器 ──────────────────────────────────────────────────
class HistoryResult:
    """訂位查詢結果頁解析。跟訂票完成頁共用大部分 CSS selector（見 THSR訂票流程與參數整理.md 第4節）"""

    def parse(self, html_content):
        soup = BeautifulSoup(html_content, "html.parser")

        pnr_el = soup.select_one(".pnr-code")
        if not pnr_el or not pnr_el.get_text(strip=True):
            return None

        r = SimpleNamespace()
        r.id = pnr_el.get_text(strip=True)

        seat_el = soup.select_one(".seat-label")
        r.seat = seat_el.get_text(strip=True) if seat_el else ""

        code_el = soup.select_one("[id^='setTrainCode']")
        dep_el = soup.select_one("[id^='setTrainDeparture']")
        arr_el = soup.select_one("[id^='setTrainArrival']")
        r.train_id = code_el.get_text(strip=True) if code_el else ""
        r.depart_time = dep_el.get_text(strip=True) if dep_el else ""
        r.arrival_time = arr_el.get_text(strip=True) if arr_el else ""

        depart_stn_el = soup.select_one(".departure-stn")
        arrive_stn_el = soup.select_one(".arrival-stn")
        date_el = soup.select_one(".date")
        r.start_station = depart_stn_el.get_text(strip=True) if depart_stn_el else ""
        r.dest_station = arrive_stn_el.get_text(strip=True) if arrive_stn_el else ""
        r.date = date_el.get_text(strip=True) if date_el else ""

        status_el = soup.select_one(".payment-status")
        r.payment_status = status_el.get_text(" ", strip=True) if status_el else ""

        price_el = soup.select_one("[id^='InfoPrice']")
        r.price = price_el.get("price") if price_el and price_el.get("price") else (price_el.get_text(strip=True) if price_el else "")

        # 頁面上找得到「取消訂位」連結，代表這筆訂位目前狀態允許取消
        cancel_link = soup.find("a", href=re.compile(r"CancelSeatsButton.*ILinkListener", re.I)) or \
                      soup.find("a", string=re.compile(r"取消訂位"))
        r.cancellable = cancel_link is not None
        return r


def _is_cancel_success(html_content) -> bool:
    text = BeautifulSoup(html_content, "html.parser").get_text()
    return "取消訂位成功" in text


# ── Session 管理（跟 thsr.py 的 ThsrSessionManager 分開，狀態機不同） ──────
class HistorySession:
    def __init__(self):
        self.client = None
        self.last_query_html = None
        self.last_result = None
        self.state = "init"


_history_sessions = {}


def _create_session():
    import uuid
    sid = str(uuid.uuid4())
    _history_sessions[sid] = HistorySession()
    return sid, _history_sessions[sid]


def _get_session(sid):
    return _history_sessions.get(sid)


def _delete_session(sid):
    _history_sessions.pop(sid, None)


# ── 路由 ────────────────────────────────────────────────────────────
@thsr_history_bp.route("/api/thsr/history/my-bookings", methods=["GET"])
@require_auth
def my_bookings():
    """列出目前使用者在本系統（不論 Tab1 手動或 Tab2 自動搶票）訂過的票，
    讓使用者不用每次都手動輸入身分證字號/訂位代號就能查詢/取消。"""
    username = _current_username()
    records = get_booking_db().get_user_bookings(username)
    return jsonify({"ok": True, "bookings": records})


@thsr_history_bp.route("/api/thsr/history/records/<booking_id>", methods=["GET"])
@require_auth
def booking_record_detail(booking_id):
    """查詢單一筆本地訂票紀錄的完整明細（不連線高鐵，純讀本地資料庫；
    要查詢高鐵目前最新狀態請用 /api/thsr/history/start 走真正的官網查詢流程）。"""
    record = get_booking_db().get_booking(booking_id)
    if not record:
        return jsonify({"ok": False, "error": "找不到這筆訂票紀錄"}), 404
    if record.get("username") != _current_username():
        return jsonify({"ok": False, "error": "無權查看這筆紀錄"}), 403
    return jsonify({"ok": True, "booking": record})


@thsr_history_bp.route("/api/thsr/history/records/<booking_id>", methods=["PATCH", "POST"])
@require_auth
def booking_record_update(booking_id):
    """更新一筆本地訂票紀錄（維護用途，例如手動修正聯絡電話、備註目前狀態等）。
    只會更新白名單內的欄位，booking_id / username / created_at 不會被這個 API 變更。"""
    db = get_booking_db()
    record = db.get_booking(booking_id)
    if not record:
        return jsonify({"ok": False, "error": "找不到這筆訂票紀錄"}), 404
    if record.get("username") != _current_username():
        return jsonify({"ok": False, "error": "無權修改這筆紀錄"}), 403

    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"ok": False, "error": "沒有提供任何要更新的欄位"}), 400

    ok = db.update_booking(booking_id, **data)
    if not ok:
        return jsonify({"ok": False, "error": "更新失敗，請確認欄位名稱是否正確"}), 400
    return jsonify({"ok": True, "booking": db.get_booking(booking_id)})


@thsr_history_bp.route("/api/thsr/history/records/<booking_id>", methods=["DELETE"])
@require_auth
def booking_record_delete(booking_id):
    """刪除一筆本地訂票紀錄。
    ⚠️ 這只會刪除本地備忘紀錄，不會連線去高鐵官網取消訂位——如果票還沒真的取消，
    請先透過查詢/取消訂位功能完成官方取消，再刪除這筆本地紀錄，
    否則系統紀錄跟高鐵官網的實際訂位狀態會對不起來。"""
    db = get_booking_db()
    record = db.get_booking(booking_id)
    if not record:
        return jsonify({"ok": False, "error": "找不到這筆訂票紀錄"}), 404
    if record.get("username") != _current_username():
        return jsonify({"ok": False, "error": "無權刪除這筆紀錄"}), 403

    warning = None
    if record.get("status") == "booked":
        warning = "這筆訂位在高鐵官網可能仍然有效，刪除本地紀錄前建議先完成官方取消訂位，否則你會忘記自己還有一筆有效訂位。"

    ok = db.delete_booking(booking_id)
    if not ok:
        return jsonify({"ok": False, "error": "刪除失敗"}), 400
    return jsonify({"ok": True, "warning": warning})


@thsr_history_bp.route("/api/thsr/history/start", methods=["POST"])
@require_auth
def history_start():
    """建立查詢用 session + 取得驗證碼"""
    session_id, sess = _create_session()
    try:
        sess.client = ThsrHistoryClient()
    except Exception as e:
        _delete_session(session_id)
        logger.error(f"❌ 建立高鐵「訂位查詢」連線失敗: {e}")
        return jsonify({"ok": False, "error": f"連線至高鐵訂位查詢頁面失敗: {e}"}), 502

    try:
        raw_b64, cleaned_b64, ocr_b64, ai_guess = _fetch_captcha(sess.client)
        if not raw_b64:
            _delete_session(session_id)
            return jsonify({"ok": False, "error": "高鐵拒絕服務：驗證碼獲取失敗"}), 502
        sess.state = "awaiting_captcha"
    except Exception as e:
        _delete_session(session_id)
        return jsonify({"ok": False, "error": f"取得驗證碼失敗: {e}"}), 502

    return jsonify({
        "ok": True,
        "session_id": session_id,
        "captcha_image": raw_b64,
        "cleaned_image": cleaned_b64,
        "ocr_image": ocr_b64,
        "captcha_guess": ai_guess,
    })


@thsr_history_bp.route("/api/thsr/history/refresh-captcha", methods=["POST"])
@require_auth
def history_refresh_captcha():
    data = request.get_json(silent=True) or {}
    sess = _get_session(data.get("session_id", ""))
    if sess is None or sess.client is None:
        return jsonify({"ok": False, "error": "Session 已逾時"}), 404
    try:
        raw_b64, cleaned_b64, ocr_b64, ai_guess = _fetch_captcha(sess.client)
        if not raw_b64:
            return jsonify({"ok": False, "error": "高鐵官網未成功核發新驗證碼影像"})
        return jsonify({
            "ok": True,
            "captcha_image": raw_b64,
            "cleaned_image": cleaned_b64,
            "ocr_image": ocr_b64,
            "captcha_guess": ai_guess,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"重新取得驗證碼失敗: {e}"}), 502


@thsr_history_bp.route("/api/thsr/history/query", methods=["POST"])
@require_auth
def history_query():
    """送出查詢（身分證/護照號碼 + 訂位代號 + 驗證碼），回傳訂位明細"""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    id_type = str(data.get("id_type", "0"))          # 0=身分證 1=護照/居留證/入出境許可證號
    roc_id = (data.get("roc_id") or "").strip().upper()
    order_id = (data.get("order_id") or "").strip().upper()
    security_code = (data.get("security_code") or "").strip()

    sess = _get_session(session_id)
    if sess is None or sess.client is None:
        return jsonify({"ok": False, "error": "Session 已逾時"}), 404
    if not roc_id or not order_id:
        return jsonify({"ok": False, "error": "請輸入證件號碼與訂位代號"}), 400
    if not security_code:
        return jsonify({"ok": False, "error": "請輸入驗證碼"}), 400

    params = {
        "typesofid": id_type,
        "rocId": roc_id,
        "orderId": order_id,
        "divCaptcha:securityCode": security_code,
    }

    try:
        resp = sess.client.submit_history_query(params)
    except Exception as e:
        return jsonify({"ok": False, "error": f"送出查詢失敗: {e}"}), 502

    errors = _errors_or_none(resp.content)
    if errors:
        try:
            raw_b64, cleaned_b64, ocr_b64, ai_guess = _fetch_captcha(sess.client)
        except Exception:
            raw_b64 = cleaned_b64 = ocr_b64 = ai_guess = None
        return jsonify({
            "ok": False, "errors": errors,
            "captcha_image": raw_b64, "cleaned_image": cleaned_b64,
            "ocr_image": ocr_b64, "captcha_guess": ai_guess,
        })

    result = HistoryResult().parse(resp.content)
    if result is None:
        return jsonify({"ok": False, "error": "查無此訂位資料，請確認證件號碼與訂位代號是否正確"}), 404

    sess.last_query_html = resp.content
    sess.last_result = result
    sess.state = "queried"

    return jsonify({
        "ok": True,
        "booking": {
            "booking_id": result.id,
            "start_station": result.start_station,
            "dest_station": result.dest_station,
            "date": result.date,
            "train_id": result.train_id,
            "depart_time": result.depart_time,
            "arrival_time": result.arrival_time,
            "seat": result.seat,
            "price": result.price,
            "payment_status": result.payment_status,
            "cancellable": result.cancellable,
        },
    })


@thsr_history_bp.route("/api/thsr/history/cancel", methods=["POST"])
@require_auth
def history_cancel():
    """取消訂位：先跟隨查詢結果頁的「取消訂位」連結（GET），再送出確認表單（勾選agree）"""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")

    sess = _get_session(session_id)
    if sess is None or sess.client is None or sess.last_query_html is None or sess.last_result is None:
        return jsonify({"ok": False, "error": "請先查詢到訂位資料後才能取消"}), 400
    if not sess.last_result.cancellable:
        return jsonify({"ok": False, "error": "此筆訂位目前無法取消（可能已取消、已搭乘或已超過可取消時限）"}), 400

    booking_id = sess.last_result.id

    try:
        cancel_page_resp = sess.client.follow_cancel_link(sess.last_query_html)
    except Exception as e:
        return jsonify({"ok": False, "error": f"開啟取消訂位頁面失敗: {e}"}), 502

    errors = _errors_or_none(cancel_page_resp.content)
    if errors:
        return jsonify({"ok": False, "errors": errors})

    try:
        confirm_resp = sess.client.submit_cancel_confirm({"agree": "on", "SubmitButton": "下一步"})
    except Exception as e:
        return jsonify({"ok": False, "error": f"送出取消確認失敗: {e}"}), 502

    errors = _errors_or_none(confirm_resp.content)
    if errors:
        return jsonify({"ok": False, "errors": errors})

    if not _is_cancel_success(confirm_resp.content):
        return jsonify({
            "ok": False,
            "error": "高鐵未回傳明確的取消成功訊息，請登入官網確認實際訂位狀態，避免重複操作。",
        }), 502

    # 取消成功，同步更新本地紀錄（如果這筆是本系統訂的票）
    try:
        get_booking_db().mark_cancelled(booking_id)
    except Exception as e:
        logger.error(f"⚠️ 取消訂位成功，但更新本地紀錄狀態失敗: {e}")

    _delete_session(session_id)
    return jsonify({"ok": True, "message": f"訂位代號 {booking_id} 取消訂位成功！"})
