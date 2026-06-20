@echo off
#:: 開機自動啟動腳本
#:: 放到 Windows 啟動資料夾即可自動執行

#:: 等待網路連線（開機後網路需要幾秒才就緒）
#timeout /t 15 /nobreak > nul

#:: 切換到程式目錄（修改為你的實際路徑）
#cd /d "C:\Users\88698\Desktop\Workspace\trading_system"

#:: 啟動 Flask + Telegram Bot
#start "TradingSystem" pythonw run.py
.\venv\scripts\activate.bat
timeout /t 3
python app.py
exit
