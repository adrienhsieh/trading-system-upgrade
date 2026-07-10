"""
THSR Monitor Service - 高鐵票券自動監控 / 自動搶票 業務層
核心職責：
1. 管理監控任務的生命週期 (啟動、停止、查詢)
2. 持久化儲存監控狀態
3. 觸發通知事件

Tab 2 擴充（結合 thsr-ticket-monitor 的「監控通知」與 THSR-Sniper 的「精準時間自動下單」）：
- mode="watch"     : 找到符合條件的座位只發通知，由使用者自行完成訂票（沿用原本行為）
- mode="auto_book" : 到了指定的開賣時間（例如當日凌晨 00:00）後，自動重複嘗試「查詢 → 驗證碼辨識 →
                      篩選車次(時間區間/早鳥) → 選車 → 帶身分證/手機送出」直到訂到票或超過時間預算
"""
import logging
import time
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
import sqlite3
from pathlib import Path

_logger = logging.getLogger(__name__)

class MonitorStatus(Enum):
    """監控狀態列舉"""
    IDLE = "idle"              # 未監控
    RUNNING = "running"        # 正在監控 / 等待開賣時間
    PAUSED = "paused"          # 已暫停
    COMPLETED = "completed"    # 已完成（找到座位 / 已自動訂到票）
    FAILED = "failed"          # 失敗

# 新增欄位一覽（供 create_task / DB schema 對照）：
#   mode                 : "watch" | "auto_book"
#   personal_id          : 訂票人身分證字號（auto_book 模式必填）
#   phone                : 訂票人手機（auto_book 模式必填）
#   adult_num/child_num/disabled_num/elder_num/college_num : 各類票數
#   seat_class           : "0" 標準車廂 / "1" 商務車廂
#   seat_prefer          : "0" 無偏好 / "1" 靠窗 / "2" 靠走道（對照 THSR訂票流程與參數整理.md 的 seatCon:seatRadioGroup 真實合法值）
#   ticket_type_pref     : "any" 不限 / "early_bird" 只挑有早鳥優惠的車次
#   time_window_start/time_window_end : 期望的出發時間區間，格式 "HH:MM"
#   connected_seats      : 是否要求多張票座位相連（見下方說明的實務限制）
#   release_at           : 指定自動搶票的觸發時間（ISO 字串），到這個時間才會開始狂送請求；為 None 則立即開始
#   max_duration_minutes : 觸發後最多嘗試多久（分鐘），逾時仍未成功則標記 FAILED
NEW_FIELDS = [
    ("mode", "TEXT", "'watch'"),
    ("personal_id", "TEXT", "''"),
    ("phone", "TEXT", "''"),
    ("adult_num", "INTEGER", "1"),
    ("child_num", "INTEGER", "0"),
    ("disabled_num", "INTEGER", "0"),
    ("elder_num", "INTEGER", "0"),
    ("college_num", "INTEGER", "0"),
    ("seat_class", "TEXT", "'0'"),
    ("seat_prefer", "TEXT", "'0'"),
    ("ticket_type_pref", "TEXT", "'any'"),
    ("time_window_start", "TEXT", "''"),
    ("time_window_end", "TEXT", "''"),
    ("connected_seats", "INTEGER", "0"),
    ("release_at", "TEXT", "NULL"),
    ("max_duration_minutes", "INTEGER", "20"),
]

@dataclass
class MonitorTask:
    """監控任務數據模型"""
    task_id: str                # 唯一標識
    username: str               # 用戶名
    start_station: str          # 起始站
    end_station: str            # 終點站
    search_date: str            # 查詢日期 (YYYY/MM/DD)
    search_time: str            # 查詢時間 (600A, 630P 等，需符合 param_schema.py 的合法列舉值)
    status: str = "idle"        # 狀態
    created_at: str = None      # 建立時間
    updated_at: str = None      # 更新時間
    notification_email: str = None  # 通知郵箱
    notification_line: bool = True  # 是否通知 LINE
    check_interval: int = 90    # 檢查間隔（秒，watch 模式使用）
    max_retries: int = 999      # 最大重試次數
    retries_count: int = 0      # 當前重試次數
    last_check: Optional[str] = None  # 最後檢查時間
    result_data: Optional[str] = None  # 結果數據 (JSON)
    error_msg: Optional[str] = None    # 錯誤訊息
    # ── Tab 2（自動搶票）新增欄位 ──────────────────────────────
    mode: str = "watch"
    personal_id: str = ""
    phone: str = ""
    adult_num: int = 1
    child_num: int = 0
    disabled_num: int = 0
    elder_num: int = 0
    college_num: int = 0
    seat_class: str = "0"
    seat_prefer: str = "0"
    ticket_type_pref: str = "any"
    time_window_start: str = ""
    time_window_end: str = ""
    connected_seats: int = 0
    release_at: Optional[str] = None
    max_duration_minutes: int = 20

ALL_COLUMNS = [
    "task_id", "username", "start_station", "end_station", "search_date", "search_time",
    "status", "created_at", "updated_at", "notification_email", "notification_line",
    "check_interval", "max_retries", "retries_count", "last_check", "result_data", "error_msg",
    "mode", "personal_id", "phone", "adult_num", "child_num", "disabled_num", "elder_num",
    "college_num", "seat_class", "seat_prefer", "ticket_type_pref", "time_window_start",
    "time_window_end", "connected_seats", "release_at", "max_duration_minutes",
]

class THSRMonitorDB:
    """監控任務數據庫層"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "db" / "thsr_monitor.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化數據庫表，並自動把舊版資料庫升級到新欄位（Tab 2 用）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS monitor_tasks (
                    task_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    start_station TEXT NOT NULL,
                    end_station TEXT NOT NULL,
                    search_date TEXT NOT NULL,
                    search_time TEXT NOT NULL,
                    status TEXT DEFAULT 'idle',
                    created_at TEXT,
                    updated_at TEXT,
                    notification_email TEXT,
                    notification_line INTEGER DEFAULT 1,
                    check_interval INTEGER DEFAULT 90,
                    max_retries INTEGER DEFAULT 999,
                    retries_count INTEGER DEFAULT 0,
                    last_check TEXT,
                    result_data TEXT,
                    error_msg TEXT,
                    UNIQUE(username, start_station, end_station, search_date, search_time)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS monitor_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT,  -- 'check', 'found', 'notification_sent', 'error'
                    event_data TEXT,
                    timestamp TEXT,
                    FOREIGN KEY(task_id) REFERENCES monitor_tasks(task_id)
                )
            """)
            conn.commit()

            # 🆕 自動遷移：幫既有（Tab 1 時代建立）的資料庫補上 Tab 2 需要的新欄位。
            # 用 try/except 逐欄新增，欄位已存在時 SQLite 會丟 OperationalError，直接忽略即可。
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(monitor_tasks)").fetchall()}
            for col_name, col_type, default_sql in NEW_FIELDS:
                if col_name in existing_cols:
                    continue
                try:
                    conn.execute(
                        f"ALTER TABLE monitor_tasks ADD COLUMN {col_name} {col_type} DEFAULT {default_sql}"
                    )
                    _logger.info(f"🆙 已為 monitor_tasks 資料表新增欄位: {col_name}")
                except sqlite3.OperationalError as e:
                    _logger.debug(f"欄位 {col_name} 遷移略過（可能已存在）: {e}")
            conn.commit()
    
    def create_task(self, task: MonitorTask) -> bool:
        """創建監控任務"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                now = datetime.now().isoformat()
                task.created_at = now
                task.updated_at = now
                values = {
                    **asdict(task),
                    "notification_line": int(bool(task.notification_line)),
                    "connected_seats": int(bool(task.connected_seats)),
                }
                cols = ALL_COLUMNS
                placeholders = ", ".join(["?"] * len(cols))
                conn.execute(
                    f"INSERT INTO monitor_tasks ({', '.join(cols)}) VALUES ({placeholders})",
                    [values[c] for c in cols],
                )
                conn.commit()
            _logger.info(f"✓ 監控任務已創建: {task.task_id}")
            return True
        except sqlite3.IntegrityError:
            _logger.warning(f"⚠️ 監控任務已存在: {task.task_id}")
            return False
        except Exception as e:
            _logger.error(f"❌ 創建任務失敗: {e}")
            return False
    
    def update_task_status(self, task_id: str, status: str, **kwargs) -> bool:
        """更新任務狀態"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                updates = ["status = ?", "updated_at = ?"]
                values = [status, datetime.now().isoformat()]
                
                allowed = {
                    'error_msg', 'result_data', 'retries_count', 'last_check',
                }
                for key, value in kwargs.items():
                    if key in allowed:
                        updates.append(f"{key} = ?")
                        values.append(value)
                
                values.append(task_id)
                query = f"UPDATE monitor_tasks SET {', '.join(updates)} WHERE task_id = ?"
                conn.execute(query, values)
                conn.commit()
            return True
        except Exception as e:
            _logger.error(f"❌ 更新任務狀態失敗: {e}")
            return False
    
    def get_task(self, task_id: str) -> Optional[MonitorTask]:
        """查詢單個任務"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM monitor_tasks WHERE task_id = ?",
                    (task_id,)
                )
                row = cursor.fetchone()
                if row:
                    return self._row_to_task(row)
            return None
        except Exception as e:
            _logger.error(f"❌ 查詢任務失敗: {e}")
            return None

    def _row_to_task(self, row) -> MonitorTask:
        """把 sqlite3.Row 轉成 MonitorTask，只挑 dataclass 認得的欄位，避免舊/新 schema 欄位增減時炸掉"""
        d = dict(row)
        field_names = {f for f in MonitorTask.__dataclass_fields__.keys()}
        filtered = {k: v for k, v in d.items() if k in field_names}
        return MonitorTask(**filtered)
    
    def get_user_tasks(self, username: str, status: str = None) -> List[MonitorTask]:
        """查詢用戶的所有任務"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                if status:
                    cursor = conn.execute(
                        "SELECT * FROM monitor_tasks WHERE username = ? AND status = ?",
                        (username, status)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM monitor_tasks WHERE username = ? ORDER BY updated_at DESC",
                        (username,)
                    )
                return [self._row_to_task(row) for row in cursor.fetchall()]
        except Exception as e:
            _logger.error(f"❌ 查詢用戶任務失敗: {e}")
            return []
    
    def get_active_tasks(self) -> List[MonitorTask]:
        """查詢所有活躍任務（RUNNING 狀態）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM monitor_tasks WHERE status = ?",
                    (MonitorStatus.RUNNING.value,)
                )
                return [self._row_to_task(row) for row in cursor.fetchall()]
        except Exception as e:
            _logger.error(f"❌ 查詢活躍任務失敗: {e}")
            return []
    
    def delete_task(self, task_id: str) -> bool:
        """刪除監控任務"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM monitor_tasks WHERE task_id = ?", (task_id,))
                conn.execute("DELETE FROM monitor_history WHERE task_id = ?", (task_id,))
                conn.commit()
            _logger.info(f"✓ 監控任務已刪除: {task_id}")
            return True
        except Exception as e:
            _logger.error(f"❌ 刪除任務失敗: {e}")
            return False
    
    def log_event(self, task_id: str, event_type: str, event_data: str = None):
        """記錄監控事件"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO monitor_history (task_id, event_type, event_data, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (task_id, event_type, event_data, datetime.now().isoformat()))
                conn.commit()
        except Exception as e:
            _logger.error(f"❌ 記錄事件失敗: {e}")

class THSRMonitorService:
    """高鐵監控 / 自動搶票服務 - 業務邏輯層"""
    
    def __init__(self, db_path: str = None):
        self.db = THSRMonitorDB(db_path)
        self.active_workers: Dict[str, 'MonitorWorker'] = {}
        self._lock = threading.Lock()
        
    def start_monitoring(self, username: str, start_station: str, end_station: str,
                         search_date: str, search_time: str, **kwargs) -> Dict[str, Any]:
        """使用 **kwargs 接收所有監控參數，避免參數不匹配"""
        task_id = kwargs.get('task_id')
        if task_id is None:
            ts = datetime.now().strftime("%H%M%S")
            task_id = f"{username}_{start_station}_{end_station}_{search_date}_{search_time}_{ts}".replace("/", "")

        # 模式驗證
        mode = kwargs.get('mode', 'watch')
        if mode not in ("watch", "auto_book"):
            return {"ok": False, "error": "mode 必須是 watch 或 auto_book"}

        # 將參數傳遞給 MonitorTask，使用字典解構
        # 確保 MonitorTask 的屬性名稱與傳入的 key 一致
        task_data = {
            "task_id": task_id,
            "username": username,
            "start_station": start_station,
            "end_station": end_station,
            "search_date": search_date,
            "search_time": search_time,
            **kwargs  # 自動帶入所有額外參數（mode, personal_id, phone 等）
        }
        
        task = MonitorTask(**task_data)
    
    #def start_monitoring(self, username: str, start_station: str, end_station: str,
    #                    search_date: str, search_time: str, task_id: str = None,
    #                    notification_email: str = None, notification_line: bool = True,
    #                    mode: str = "watch", personal_id: str = "", phone: str = "",
    #                    adult_num: int = 1, child_num: int = 0, disabled_num: int = 0,
    #                    elder_num: int = 0, college_num: int = 0, seat_class: str = "0",
    #                    seat_prefer: str = "0", ticket_type_pref: str = "any",
    #                    time_window_start: str = "", time_window_end: str = "",
    #                    connected_seats: bool = False, release_at: str = None,
    #                    max_duration_minutes: int = 20, check_interval: int = 90) -> Dict[str, Any]:
    #    """啟動監控 / 自動搶票任務"""
    #    if task_id is None:
    #        ts = datetime.now().strftime("%H%M%S")
    #        task_id = f"{username}_{start_station}_{end_station}_{search_date}_{search_time}_{ts}".replace("/", "")
    #
    #    if mode not in ("watch", "auto_book"):
    #        return {"ok": False, "error": "mode 必須是 watch 或 auto_book"}
    #
    #    if mode == "auto_book":
    #        if not personal_id or len(personal_id) != 10:
    #            return {"ok": False, "error": "自動搶票模式需要正確的10碼身分證字號"}
    #        if phone and (len(phone) != 10 or not phone.startswith("09")):
    #            return {"ok": False, "error": "手機號碼格式錯誤（應為 09 開頭的10碼）"}
    #
    #    # 檢查是否已有相同的監控任務在運行
    #    existing = self.db.get_task(task_id)
    #    if existing and existing.status == MonitorStatus.RUNNING.value:
    #        return {
    #            "ok": False,
    #            "error": "此路線已有監控任務在執行中",
    #            "task_id": task_id
    #        }
    #    
    #    # 創建新任務
    #    task = MonitorTask(
    #        task_id=task_id,
    #        username=username,
    #        start_station=start_station,
    #        end_station=end_station,
    #        search_date=search_date,
    #        search_time=search_time,
    #        notification_email=notification_email,
    #        notification_line=notification_line,
    #        check_interval=check_interval,
    #        mode=mode,
    #        personal_id=personal_id,
    #        phone=phone,
    #        adult_num=adult_num,
    #        child_num=child_num,
    #        disabled_num=disabled_num,
    #        elder_num=elder_num,
    #        college_num=college_num,
    #        seat_class=seat_class,
    #        seat_prefer=seat_prefer,
    #        ticket_type_pref=ticket_type_pref,
    #        time_window_start=time_window_start,
    #        time_window_end=time_window_end,
    #        connected_seats=int(bool(connected_seats)),
    #        release_at=release_at,
    #        max_duration_minutes=max_duration_minutes,
    #    )
        
        if not self.db.create_task(task):
            return {
                "ok": False,
                "error": "無法創建監控任務",
                "task_id": task_id
            }
        
        # 更新狀態為 RUNNING
        self.db.update_task_status(task_id, MonitorStatus.RUNNING.value)
        
        # 導入監控工作線程（避免循環導入）
        from .monitor_worker import MonitorWorker
        
        # 啟動監控線程
        with self._lock:
            if task_id not in self.active_workers:
                worker = MonitorWorker(task, self.db)
                worker.start()
                self.active_workers[task_id] = worker
        
        _logger.info(f"🚀 已啟動{'自動搶票' if mode == 'auto_book' else '監控'}任務: {task_id}")
        self.db.log_event(task_id, "monitor_started", f"{start_station} → {end_station} ({mode})")
        
        return {
            "ok": True,
            "message": "自動搶票任務已啟動" if mode == "auto_book" else "監控任務已啟動",
            "task_id": task_id,
            "status": MonitorStatus.RUNNING.value
        }
    
    def stop_monitoring(self, task_id: str) -> Dict[str, Any]:
        """停止監控任務"""
        task = self.db.get_task(task_id)
        if not task:
            return {"ok": False, "error": "任務不存在"}
        
        with self._lock:
            if task_id in self.active_workers:
                worker = self.active_workers[task_id]
                worker.stop()
                del self.active_workers[task_id]
        
        self.db.update_task_status(task_id, MonitorStatus.PAUSED.value)
        _logger.info(f"⏹️ 已停止監控任務: {task_id}")
        self.db.log_event(task_id, "monitor_stopped")
        
        return {"ok": True, "message": "監控任務已停止", "task_id": task_id}
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """查詢任務狀態"""
        task = self.db.get_task(task_id)
        if not task:
            return {"ok": False, "error": "任務不存在"}
        
        return {
            "ok": True,
            "task": asdict(task)
        }
    
    def get_user_monitoring_tasks(self, username: str) -> Dict[str, Any]:
        """查詢用戶所有監控任務"""
        tasks = self.db.get_user_tasks(username)
        return {
            "ok": True,
            "tasks": [asdict(t) for t in tasks],
            "count": len(tasks)
        }
    
    def delete_task(self, task_id: str) -> Dict[str, Any]:
        """刪除監控任務"""
        # 先停止正在運行的監控
        self.stop_monitoring(task_id)
        
        if self.db.delete_task(task_id):
            return {"ok": True, "message": "任務已刪除"}
        else:
            return {"ok": False, "error": "無法刪除任務"}
