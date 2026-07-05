## gen_token.py — 生成 JWT Token
#from trading.api.utils import generate_token
#from trading.config import ConfigManager
#
#def main():
#    cfg = ConfigManager().load()
#    token = generate_token(user_id="test", api_key=cfg["api_key"])
#    print("\n=== 生成的 JWT Token ===\n")
#    print(token)
#    print("\n請將上面的 Token 複製到批次檔或 curl 指令裡使用。\n")
#
#if __name__ == "__main__":
#    main()
#

# gen_token.py — 生成 JWT Token 並存到 token.txt
from trading.api.utils import generate_token
from trading.config import ConfigManager
import os

def main():
    cfg = ConfigManager().load()
    token = generate_token(user_id="test", api_key=cfg["api_key"])

    # 將 Token 存到檔案
    with open("token.txt", "w", encoding="utf-8") as f:
        f.write(token)

    print("\n=== 生成的 JWT Token ===\n")
    print(token)
    print("\n已將 Token 存到 token.txt，可以直接在批次檔或其他程式裡讀取。\n")

if __name__ == "__main__":
    main()
