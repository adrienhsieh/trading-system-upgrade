"""
trading/api/utils.py — JWT 憑證簽發、解密與 API 驗證高階工具（安全整合版）
"""

import os
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify, g

from trading.config import FLASK_SECRET_KEY




def get_jwt_secret():
    """確保全域密鑰與 Flask App 秘密鎖絕對同步"""
    return os.getenv("FLASK_SECRET_KEY", "super-secret-key-change-me")



def validate_code(code=None):
    """相容舊版驗證邏輯，固定回傳 True"""
    return True


def get_jwt_secret():
    """確保全域密鑰與 Flask App 秘密鎖絕對同步"""
    return FLASK_SECRET_KEY


def verify_jwt_token(token):
    """供系統其他模組動態驗證憑證合法性"""
    try:
        secret = get_jwt_secret()
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except Exception:
        return None


import jwt
import datetime
from trading.config import ConfigManager

def generate_token(user_id: str, api_key: str):
    """
    生成 JWT Token
    """
    cfg = ConfigManager().load()
    secret_key = cfg.get("flask_secret_key", "default_secret")

    payload = {
        "user_id": user_id,
        "user_api_key": api_key,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)  # 有效期 1 小時
    }

    return jwt.encode(payload, secret_key, algorithm="HS256")


#def generate_token(user_id, api_key):
#    """生成 JWT Token，使用全域同步高強度密鑰"""
#    now = datetime.now(timezone.utc)
#    payload = {
#        'exp': now + timedelta(hours=int(os.getenv("JWT_EXPIRY_HOURS", 24))),
#        'iat': now,
#        'user_id': user_id,
#        'user_api_key': api_key
#    }
#    secret = get_jwt_secret()
#    return jwt.encode(payload, secret, algorithm='HS256')


def jwt_required(f):
    """API 驗證裝飾器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({"error": "未提供憑證，請先登入"}), 401

        parts = auth_header.split(" ")
        if len(parts) != 2:
            return jsonify({"error": "憑證格式錯誤"}), 401

        token = parts[1]
        try:
            secret = get_jwt_secret()
            payload = jwt.decode(token, secret, algorithms=['HS256'])

            # 注入 Context
            g.current_user_id = payload['user_id']
            g.current_user_api_key = payload['user_api_key']

        except jwt.ExpiredSignatureError:
            return jsonify({"error": "憑證已過期，請重新登入"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "無效的憑證，拒絕存取"}), 401

        return f(*args, **kwargs)
    return decorated

        
import jwt
from trading.config import ConfigManager

def verify_token(token: str):
    """
    驗證 JWT Token，成功時回傳 payload，失敗時回傳 None
    """
    cfg = ConfigManager().load()
    secret_key = cfg.get("flask_secret_key", "default_secret")

    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None