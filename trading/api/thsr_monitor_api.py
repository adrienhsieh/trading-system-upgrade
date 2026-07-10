"""
THSR Monitor / Auto-Booking API Blueprint
高鐵監控 & 自動搶票 API 路由（Tab 2）

Endpoints:
  POST   /api/thsr/monitor - 啟動監控或自動搶票任務
  GET    /api/thsr/monitor/<task_id> - 查詢任務狀態
  GET    /api/thsr/monitor/user/<username> - 查詢用戶所有任務
  DELETE /api/thsr/monitor/<task_id> - 停止並刪除任務

🛠️ 修正重大 Bug：舊版路由函式簽章寫成 def start_monitor(current_user)，
但專案裡真正的 @require_auth（trading/api/auth.py）並不會把 current_user 當參數注入，
而是把登入者寫進 flask.g.current_username。照舊版寫法，Flask 呼叫這些路由時一律會少一個
必要參數，等於整個 Blueprint 的每一支 API 呼叫都會直接 500 壞掉。現在改用專案裡其他
Blueprint（如 positions.py）一致的慣例：從 g.current_username 取得登入者。
"""
import logging
from flask import Blueprint, request, jsonify, g
from trading.api.auth import require_auth
from thsr_ticket.monitor import THSRMonitorService

_logger = logging.getLogger(__name__)

# 全域單例
_monitor_service = None

def get_monitor_service() -> THSRMonitorService:
    """延遲初始化監控服務"""
    global _monitor_service
    if _monitor_service is None:
        _monitor_service = THSRMonitorService()
    return _monitor_service

def _current_username() -> str:
    return getattr(g, "current_username", "") or "default"

thsr_monitor_bp = Blueprint('thsr_monitor', __name__, url_prefix='/api/thsr/monitor')

@thsr_monitor_bp.route('', methods=['POST'])
@require_auth
def start_monitor():
    """啟動高鐵座位監控 / 自動搶票

    Request Body（watch 模式範例）：
    {
        "start_station": "2", "end_station": "9",
        "search_date": "2026/07/10", "search_time": "600A",
        "notification_email": "user@example.com", "notification_line": true
    }

    Request Body（auto_book 自動搶票模式，額外欄位）：
    {
        "mode": "auto_book",
        "personal_id": "A123456789", "phone": "0912345678",
        "adult_num": 2, "child_num": 0, "disabled_num": 0, "elder_num": 0, "college_num": 0,
        "seat_class": "0", "seat_prefer": "1",
        "ticket_type_pref": "early_bird",
        "time_window_start": "08:00", "time_window_end": "10:00",
        "connected_seats": true,
        "release_at": "2026-07-10T00:00:00",
        "max_duration_minutes": 20
    }
    """
    try:
        data = request.get_json() or {}
        current_user = _current_username()

        required = ['start_station', 'end_station', 'search_date', 'search_time']
        for field in required:
            if field not in data:
                return jsonify({"ok": False, "error": f"缺少必填字段: {field}"}), 400

        monitor_svc = get_monitor_service()
        result = monitor_svc.start_monitoring(
            username=current_user,
            start_station=data['start_station'],
            end_station=data['end_station'],
            search_date=data['search_date'],
            search_time=data['search_time'],
            notification_email=data.get('notification_email'),
            notification_line=data.get('notification_line', True),
            mode=data.get('mode', 'watch'),
            personal_id=(data.get('personal_id') or '').strip().upper(),
            phone=(data.get('phone') or '').strip(),
            adult_num=int(data.get('adult_num', 1) or 0),
            child_num=int(data.get('child_num', 0) or 0),
            disabled_num=int(data.get('disabled_num', 0) or 0),
            elder_num=int(data.get('elder_num', 0) or 0),
            college_num=int(data.get('college_num', 0) or 0),
            seat_class=str(data.get('seat_class', '0')),
            # 🛠️ 修正：預設值曾誤用舊版錯誤代碼 radio17；高鐵表單真正合法的
            # seatCon:seatRadioGroup 值是 "0"(無偏好)/"1"(靠窗)/"2"(靠走道)，
            # 對照 THSR訂票流程與參數整理.md 修正，並與 monitor_service.py 的預設值保持一致。
            seat_prefer=str(data.get('seat_prefer', '0')),
            ticket_type_pref=data.get('ticket_type_pref', 'any'),
            time_window_start=data.get('time_window_start', ''),
            time_window_end=data.get('time_window_end', ''),
            connected_seats=bool(data.get('connected_seats', False)),
            release_at=data.get('release_at'),
            max_duration_minutes=int(data.get('max_duration_minutes', 20) or 20),
            check_interval=int(data.get('check_interval', 90) or 90),
        )
        
        status_code = 200 if result['ok'] else 400
        return jsonify(result), status_code
    
    except Exception as e:
        _logger.error(f"❌ 啟動監控失敗: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500

@thsr_monitor_bp.route('/<task_id>', methods=['GET'])
@require_auth
def get_monitor_status(task_id):
    """查詢監控任務狀態"""
    try:
        monitor_svc = get_monitor_service()
        result = monitor_svc.get_task_status(task_id)
        
        status_code = 200 if result['ok'] else 404
        return jsonify(result), status_code
    
    except Exception as e:
        _logger.error(f"❌ 查詢監控狀態失敗: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500

@thsr_monitor_bp.route('/user/<username>', methods=['GET'])
@require_auth
def get_user_monitoring_tasks(username):
    """查詢用戶所有監控任務"""
    try:
        current_user = _current_username()
        # 只允許用戶查詢自己的任務
        if current_user != username:
            return jsonify({"ok": False, "error": "無權查詢他人的監控任務"}), 403
        
        monitor_svc = get_monitor_service()
        result = monitor_svc.get_user_monitoring_tasks(username)
        
        return jsonify(result), 200
    
    except Exception as e:
        _logger.error(f"❌ 查詢用戶監控任務失敗: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500

@thsr_monitor_bp.route('/<task_id>', methods=['DELETE'])
@require_auth
def stop_monitor(task_id):
    """停止並刪除監控任務"""
    try:
        current_user = _current_username()
        monitor_svc = get_monitor_service()
        
        task = monitor_svc.db.get_task(task_id)
        if not task:
            return jsonify({"ok": False, "error": "任務不存在"}), 404
        
        if task.username != current_user:
            return jsonify({"ok": False, "error": "無權刪除他人的任務"}), 403
        
        result = monitor_svc.delete_task(task_id)
        
        status_code = 200 if result['ok'] else 400
        return jsonify(result), status_code
    
    except Exception as e:
        _logger.error(f"❌ 停止監控失敗: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500

@thsr_monitor_bp.route('/health', methods=['GET'])
def health_check():
    """健康檢查端點"""
    monitor_svc = get_monitor_service()
    active_tasks = monitor_svc.db.get_active_tasks()
    
    return jsonify({
        "ok": True,
        "status": "healthy",
        "active_monitors": len(active_tasks),
        "active_workers": len(monitor_svc.active_workers)
    }), 200
