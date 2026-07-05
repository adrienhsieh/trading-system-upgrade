@echo off
REM test_prediction.bat — 自動生成 JWT Token、檢查健康狀態並測試 API

REM 呼叫 gen_token.py 生成 Token 並存到 token.txt
python gen_token.py >nul

REM 從 token.txt 讀取 Token
set /p TOKEN=<token.txt

echo.
echo === 使用的 JWT Token ===
echo %TOKEN%

REM 設定測試 URL
set "URL_HEALTH=http://localhost:5000/api/health"
set "URL_TEST=http://localhost:5000/api/prediction/test?ticker=2330&user_id=test"
set "URL_STREAM=http://localhost:5000/api/prediction/stream?ticker=2330&user_id=test"

echo.
echo === 檢查 /api/health ===
curl "%URL_HEALTH%"

echo.
echo === 測試 /api/prediction/test ===
curl -H "Authorization: Bearer %TOKEN%" "%URL_TEST%"

echo.
echo === 測試 /api/prediction/stream ===
curl -H "Authorization: Bearer %TOKEN%" --no-buffer "%URL_STREAM%"

echo.
pause
