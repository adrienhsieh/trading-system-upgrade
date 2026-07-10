"""
thsr_ticket/records/booking_db.py — 高鐵訂票成功紀錄資料庫

不論是 Tab 1（手動訂票，trading/api/thsr.py 的 confirm()）還是 Tab 2（自動搶票，
thsr_ticket/monitor/monitor_worker.py 的 _handle_auto_book_success()），只要真的
訂票成功、拿到高鐵回傳的 PNR 訂位代號，都會呼叫這裡的 save_booking() 存一筆紀錄。

有了這份本地紀錄，Tab 3（訂位查詢／取消）就能：
  1. 不必每次都手動重新輸入身分證字號 + 訂位代號，直接列出「我訂過的票」讓使用者點選
  2. 對每一筆紀錄提供「查詢最新狀態」「取消訂位」的捷徑按鈕
  3. 取消成功後同步在本地標記 status='cancelled'，往後列表就能一眼看出哪些還有效

⚠️ 這份資料庫只是「本地備忘紀錄」，不是訂位狀態的權威來源——高鐵官網才是。
查詢/取消永遠會即時連線官網確認最新狀態，本地紀錄只是拿來省略重複輸入、
以及方便使用者一次看到自己名下的所有訂票，不會單獨依賴本地資料判斷訂位是否仍然有效。
"""
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

_logger = logging.getLogger(__name__)

_FIELDS = [
    "booking_id", "username", "source", "personal_id", "phone",
    "start_station", "dest_station", "travel_date", "train_id",
    "depart_time", "arrival_time", "seat", "seat_class",
    "ticket_num_info", "price", "payment_deadline", "status",
    "created_at", "cancelled_at",
]


class BookingRecordDB:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "db" / "thsr_bookings.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    booking_id TEXT PRIMARY KEY,   -- 高鐵訂位代號 (PNR)，例如 03532489
                    username TEXT NOT NULL,
                    source TEXT NOT NULL,          -- 'manual'（Tab1手動） 或 'auto_book'（Tab2自動搶票）
                    personal_id TEXT NOT NULL,      -- 取票身分證字號／證件號碼（查詢/取消訂位都需要）
                    phone TEXT,
                    start_station TEXT,
                    dest_station TEXT,
                    travel_date TEXT,
                    train_id TEXT,
                    depart_time TEXT,
                    arrival_time TEXT,
                    seat TEXT,
                    seat_class TEXT,
                    ticket_num_info TEXT,
                    price TEXT,
                    payment_deadline TEXT,
                    status TEXT DEFAULT 'booked',   -- 'booked' / 'cancelled'
                    created_at TEXT,
                    cancelled_at TEXT
                )
            """)
            conn.commit()

    def save_booking(self, **kwargs) -> bool:
        """儲存一筆成功訂票的紀錄。booking_id 是高鐵回傳的訂位代號，若已存在則覆蓋更新。"""
        try:
            kwargs.setdefault("status", "booked")
            kwargs.setdefault("created_at", datetime.now().isoformat())
            kwargs.setdefault("cancelled_at", None)
            values = [kwargs.get(f) for f in _FIELDS]
            with sqlite3.connect(self.db_path) as conn:
                placeholders = ", ".join(["?"] * len(_FIELDS))
                conn.execute(
                    f"INSERT OR REPLACE INTO bookings ({', '.join(_FIELDS)}) VALUES ({placeholders})",
                    values,
                )
                conn.commit()
            _logger.info(f"💾 已儲存訂票紀錄: {kwargs.get('booking_id')} ({kwargs.get('source')})")
            return True
        except Exception as e:
            _logger.error(f"❌ 儲存訂票紀錄失敗: {e}")
            return False

    def get_user_bookings(self, username: str) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT * FROM bookings WHERE username = ? ORDER BY created_at DESC", (username,)
                )
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            _logger.error(f"❌ 查詢用戶訂票紀錄失敗: {e}")
            return []

    def get_booking(self, booking_id: str) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            _logger.error(f"❌ 查詢訂票紀錄失敗: {e}")
            return None

    def mark_cancelled(self, booking_id: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE bookings SET status = 'cancelled', cancelled_at = ? WHERE booking_id = ?",
                    (datetime.now().isoformat(), booking_id),
                )
                conn.commit()
            return True
        except Exception as e:
            _logger.error(f"❌ 標記取消狀態失敗: {e}")
            return False

    # 允許被手動更新的欄位白名單，避免呼叫端不小心覆寫 booking_id / username / created_at 等關鍵欄位
    _UPDATABLE_FIELDS = [
        "personal_id", "phone", "start_station", "dest_station", "travel_date",
        "train_id", "depart_time", "arrival_time", "seat", "seat_class",
        "ticket_num_info", "price", "payment_deadline", "status",
    ]

    def update_booking(self, booking_id: str, **fields) -> bool:
        """更新一筆本地紀錄的部分欄位（維護用途，例如手動修正備註資料、
        或把查詢到的最新狀態同步回本地紀錄）。只允許白名單內的欄位被更新，
        booking_id / username / created_at 不可透過這個方法變更。"""
        updates = {k: v for k, v in fields.items() if k in self._UPDATABLE_FIELDS}
        if not updates:
            _logger.warning(f"⚠️ update_booking({booking_id}) 沒有任何合法欄位可更新，略過")
            return False
        try:
            set_clause = ", ".join([f"{k} = ?" for k in updates])
            values = list(updates.values()) + [booking_id]
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(f"UPDATE bookings SET {set_clause} WHERE booking_id = ?", values)
                conn.commit()
                if cur.rowcount == 0:
                    _logger.warning(f"⚠️ update_booking({booking_id}) 找不到對應紀錄")
                    return False
            _logger.info(f"✏️ 已更新訂票紀錄 {booking_id}：{list(updates.keys())}")
            return True
        except Exception as e:
            _logger.error(f"❌ 更新訂票紀錄失敗: {e}")
            return False

    def delete_booking(self, booking_id: str) -> bool:
        """從本地紀錄裡刪除一筆資料。
        ⚠️ 這只會刪除「本地備忘紀錄」，不會連線去高鐵官網取消訂位——
        如果票還沒真的取消，請先用查詢/取消訂位功能完成官方取消，再刪除這筆本地紀錄，
        否則你會忘記自己其實還有一筆有效訂位。"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("DELETE FROM bookings WHERE booking_id = ?", (booking_id,))
                conn.commit()
                if cur.rowcount == 0:
                    _logger.warning(f"⚠️ delete_booking({booking_id}) 找不到對應紀錄")
                    return False
            _logger.info(f"🗑️ 已刪除本地訂票紀錄 {booking_id}")
            return True
        except Exception as e:
            _logger.error(f"❌ 刪除訂票紀錄失敗: {e}")
            return False


_singleton: Optional[BookingRecordDB] = None


def get_booking_db() -> BookingRecordDB:
    global _singleton
    if _singleton is None:
        _singleton = BookingRecordDB()
    return _singleton
