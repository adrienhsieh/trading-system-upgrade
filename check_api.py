#import requests
#import subprocess
#import re
#import os
#
#BASE_URL = "http://127.0.0.1:8080"
#
#ENDPOINTS = [
#    "/api/positions",       # holdings.js
#    "/api/watchlist",       # watchlist.js
#    "/api/scanner",         # scanner.js
#    "/api/backtest",        # backtest.js
#    "/api/news",            # news.js
#    "/api/intelligence",    # intelligence.js
#    "/api/topic",           # topic.js
#    "/api/settings",        # settings.js
#    "/api/predict/test",    # predict.js
#    "/api/predict/stream"   # predict.js (SSE)
#]
#
#def read_token_file():
#    if os.path.exists("token.txt"):
#        with open("token.txt", "r", encoding="utf-8") as f:
#            content = f.read().strip()
#            match = re.search(r"[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+", content)
#            if match:
#                return match.group(0)
#    return None
#
#def get_token():
#    token = read_token_file()
#    if token:
#        print("從 token.txt 讀取 Token 成功")
#        return token
#
#    print("token.txt 不存在或無效，改用 gen_token.py 生成 Token...")
#    try:
#        result = subprocess.run(
#            ["python", "gen_token.py"],
#            capture_output=True,
#            text=True,
#            check=True
#        )
#        output = result.stdout.strip()
#        match = re.search(r"[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+", output)
#        if match:
#            return match.group(0)
#        else:
#            print("未找到有效的 JWT Token，輸出內容：", output)
#            return None
#    except Exception as e:
#        print("取得 Token 失敗:", e)
#        return None
#
#def check_api(token):
#    headers = {"Authorization": f"Bearer {token}"} if token else {}
#    if token:
#        print(f"使用的 Token: {token[:40]}...")
#    else:
#        print("警告: 未能取得 Token，將嘗試不帶 Token 進行請求。")
#
#    for ep in ENDPOINTS:
#        url = BASE_URL + ep
#        print(f"\n=== 測試 {ep} ===")
#        try:
#            resp = requests.get(url, headers=headers, timeout=5)
#            print(f"狀態碼: {resp.status_code}")
#            try:
#                print("回應 JSON:", resp.json())
#            except Exception:
#                print("回應文字:", resp.text[:200], "...")
#        except Exception as e:
#            print(f"錯誤: {e}")
#
#if __name__ == "__main__":
#    token = get_token()
#    check_api(token)
#

import requests
import json

BASE_URL = "http://127.0.0.1:8080"

def load_routes():
    with open("routes.json", "r", encoding="utf-8") as f:
        return json.load(f)

def check_api(token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    endpoints = load_routes()
    for ep in endpoints:
        url = BASE_URL + ep
        print(f"\n=== 測試 {ep} ===")
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            print(f"狀態碼: {resp.status_code}")
            try:
                print("回應 JSON:", resp.json())
            except Exception:
                print("回應文字:", resp.text[:200], "...")
        except Exception as e:
            print(f"錯誤: {e}")