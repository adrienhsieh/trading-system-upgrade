"""
THSR Monitor API Blueprint
高鐵監控 API 路由

Endpoints:
  POST   /api/thsr/monitor - 啟動監控
  GET    /api/thsr/monitor/:task_id - 查詢監控狀態
  GET    /api/thsr/monitor/user/:username - 查詢用戶所有監控任務
  DELETE /api/thsr/monitor/:task_id - 停止並刪除監控
"""
import logging
from flask import Blueprint, request, jsonify
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

thsr_monitor_bp = Blueprint('thsr_monitor', __name__, url_prefix='/api/thsr/monitor')

@thsr_monitor_bp.route('', methods=['POST'])
@require_auth
def start_monitor(current_user):
    """啟動高鐵座位監控
    
    Request Body:
    {
        "start_station": "2",     # 起始站代碼
        "end_station": "9",       # 終點站代碼
        "search_date": "2026/07/10",  # 日期
        "search_time": "600P",    # 時間
        "notification_email": "user@example.com",  # 可選
        "notification_line": true  # 可選，預設 true
    }
    """
    try:
        data = request.get_json()
        
        # 驗證必填字段
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
            notification_line=data.get('notification_line', True)
        )
        
        status_code = 200 if result['ok'] else 400
        return jsonify(result), status_code
    
    except Exception as e:
        _logger.error(f"❌ 啟動監控失敗: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@thsr_monitor_bp.route('/<task_id>', methods=['GET'])
@require_auth
def get_monitor_status(current_user, task_id):
    """查詢監控任務狀態"""
    try:
        monitor_svc = get_monitor_service()
        result = monitor_svc.get_task_status(task_id)
        
        status_code = 200 if result['ok'] else 404
        return jsonify(result), status_code
    
    except Exception as e:
        _logger.error(f"❌ 查詢監控狀態失敗: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@thsr_monitor_bp.route('/user/<username>', methods=['GET'])
@require_auth
def get_user_monitoring_tasks(current_user, username):
    """查詢用戶所有監控任務"""
    try:
        # 只允許用戶查詢自己的任務
        if current_user != username:
            return jsonify({"ok": False, "error": "無權查詢他人的監控任務"}), 403
        
        monitor_svc = get_monitor_service()
        result = monitor_svc.get_user_monitoring_tasks(username)
        
        return jsonify(result), 200
    
    except Exception as e:
        _logger.error(f"❌ 查詢用戶監控任務失敗: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@thsr_monitor_bp.route('/<task_id>', methods=['DELETE'])
@require_auth
def stop_monitor(current_user, task_id):
    """停止並刪除監控任務"""
    try:
        monitor_svc = get_monitor_service()
        
        # 驗證權限
        task = monitor_svc.db.get_task(task_id)
        if not task:
            return jsonify({"ok": False, "error": "任務不存在"}), 404
        
        if task.username != current_user:
            return jsonify({"ok": False, "error": "無權刪除他人的任務"}), 403
        
        result = monitor_svc.delete_task(task_id)
        
        status_code = 200 if result['ok'] else 400
        return jsonify(result), status_code
    
    except Exception as e:
        _logger.error(f"❌ 停止監控失敗: {e}")
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
