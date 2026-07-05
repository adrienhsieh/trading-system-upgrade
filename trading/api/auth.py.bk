"""
trading/api/auth.py — API 認證與輸入驗證輔助
"""
import functools
import hmac
import re

from flask import jsonify, request

def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        # 🟢 關鍵修正：換成新網址前綴 /api/user_page_config 的白名單放行
        if request.path.startswith("/api/user_page_config"):
            return f(*args, **kwargs)

        key      = request.headers.get("X-API-Key") or request.args.get("key", "")
        expected = _get_api_key()
        if not expected or not hmac.compare_digest(key, expected):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

def _get_api_key() -> str:
    """讀取 api_key。支援 TRADING_CONFIG_PATH env var 覆寫（測試用）。"""
    import json
    import os
    from pathlib import Path
    try:
        cfg_path_env = os.environ.get("TRADING_CONFIG_PATH", "")
        # trading/api/auth.py → trading/api/ → trading/ → project root
        default_path = Path(__file__).parent.parent.parent / "config.json"
        cfg_path = Path(cfg_path_env) if cfg_path_env else default_path
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                return json.load(f).get("api_key", "")
    except Exception:
        pass
    return ""


def require_auth(f):
    """裝飾器：驗證 X-API-Key header 或 key query param。"""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        # 🟢 關鍵新增：如果是網頁設定相關的 API 路由，直接跳過驗證放行
        # 未來這部分的安全性將會交給您專屬的網頁登入 Token 驗證器處理
        if request.path.startswith("/api/config"):
            return f(*args, **kwargs)

        key      = request.headers.get("X-API-Key") or request.args.get("key", "")
        expected = _get_api_key()
        if not expected or not hmac.compare_digest(key, expected):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def validate_code(code: str):
    """驗證股票代號為 4 位數字；不合格時回傳 400 Response，否則回傳 None。"""
    if not re.match(r'^\d{4}$', code):
        return jsonify({"ok": False, "error": f"無效股票代號：{code}（需為 4 位數字）"}), 400
    return None


def validate_number(val, name: str):
    """嘗試將 val 轉為 float；失敗時回傳 400 Response，否則回傳 None。"""
    try:
        float(val)
        return None
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": f"欄位 {name} 需為數字"}), 400
