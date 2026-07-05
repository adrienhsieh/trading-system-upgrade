import os
import re
import json
import requests

BASE_DIR = "D:/SourceCode/Web/Python/trading-system-upgrade"
JS_DIR = os.path.join(BASE_DIR, "static/js")
BASE_URL = "http://127.0.0.1:8080"

# 1. 掃描後端路由
def scan_routes(base_dir=BASE_DIR):
    routes = []
    pattern = re.compile(r'@.*route\(["\'](.*?)["\']')
    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.endswith(".py"):
                try:
                    with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                        content = f.read()
                        matches = pattern.findall(content)
                        routes.extend(matches)
                except Exception as e:
                    print(f"讀取 {file} 時發生錯誤: {e}")
    routes = sorted(set(routes))
    with open("routes.json", "w", encoding="utf-8") as f:
        json.dump(routes, f, indent=2, ensure_ascii=False)
    print("✅ 已產生 routes.json")
    return routes

# 2. 修正前端 JS 呼叫
def fix_js_routes(routes, js_dir=JS_DIR):
    if not os.path.exists(js_dir):
        print("⚠️ 找不到 static/js 目錄，跳過前端修正")
        return
    for file in os.listdir(js_dir):
        if file.endswith(".js"):
            file_path = os.path.join(js_dir, file)
            try:
                content = open(file_path, "r", encoding="utf-8").read()
                # 範例修正：prediction → predict
                content = content.replace("/api/prediction/test", "/api/predict/test")
                content = content.replace("/api/prediction/stream", "/api/predict/stream")
                open(file_path, "w", encoding="utf-8").write(content)
                print("🔧 已修正:", file_path)
            except Exception as e:
                print(f"修正 {file} 時發生錯誤: {e}")

# 3. 驗證 API
def check_api(routes, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    for ep in routes:
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

if __name__ == "__main__":
    # 取得路由
    routes = scan_routes()
    # 修正前端 JS
    fix_js_routes(routes)
    # 測試 API
    token = None
    if os.path.exists("token.txt"):
        token = open("token.txt", "r", encoding="utf-8").read().strip()
    check_api(routes, token)
