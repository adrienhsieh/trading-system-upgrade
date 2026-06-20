# trading/api/user_config.py
from flask import Blueprint, request, jsonify
from trading.services.config_db import SessionLocal, UserPageConfig, DEFAULT_MODULE_CONFIGS

# 🟢 核心修正：改用獨立的 URL 前綴 /api/user_page_config，徹底避開大總管設定的干擾
user_setting_bp = Blueprint("user_page_settings", __name__, url_prefix="/api/user_page_config")

@user_setting_bp.route("", methods=["GET"])
def get_user_page_config():
    user_id = request.args.get("user_id")
    module_id = request.args.get("module_id")
    
    if not user_id or not module_id:
        return jsonify({"ok": False, "error": "缺少參數 user_id 或 module_id"}), 400
        
    db = SessionLocal()
    try:
        record = db.query(UserPageConfig).filter(
            UserPageConfig.user_id == user_id,
            UserPageConfig.module_id == module_id
        ).first()
        
        if record:
            return jsonify({"ok": True, "data": record.configs})
        # 查無紀錄時，發放系統預設值
        return jsonify({"ok": True, "data": DEFAULT_MODULE_CONFIGS.get(module_id, {})})
    finally:
        db.close()

@user_setting_bp.route("/save", methods=["POST"])
def save_user_page_config():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    module_id = data.get("module_id")
    configs = data.get("configs")
    
    if not user_id or not module_id or configs is None:
        return jsonify({"ok": False, "error": "資料欄位不完整"}), 400
        
    db = SessionLocal()
    try:
        record = db.query(UserPageConfig).filter(
            UserPageConfig.user_id == user_id,
            UserPageConfig.module_id == module_id
        ).first()
        
        if record:
            record.configs = configs
        else:
            new_record = UserPageConfig(user_id=user_id, module_id=module_id, configs=configs)
            db.add(new_record)
            
        db.commit()
        return jsonify({"ok": True, "message": "儲存成功"})
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        db.close()
