@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set BACKEND_PORT=8052
set PAKE_APP_NAME=LogFilter.exe
set LOG_FILE=start_app.log

echo ================================================= > %LOG_FILE%
echo LogFilter 应用启动脚本 >> %LOG_FILE%
echo ================================================= >> %LOG_FILE%

echo [启动] 正在启动 LogFilter 应用...
echo [启动] 正在启动 LogFilter 应用... >> %LOG_FILE%

echo [启动] 正在启动 Python 后端服务器...
echo [启动] 正在启动 Python 后端服务器... >> %LOG_FILE%

if not exist "app.py" (
    echo [错误] 找不到 app.py 文件
    echo [错误] 找不到 app.py 文件 >> %LOG_FILE%
    pause
    exit /b 1
)

start /B python app.py > backend.log 2>&1
set BACKEND_PID=%ERRORLEVEL%

echo [启动] 后端进程已启动
echo [启动] 后端进程已启动 >> %LOG_FILE%

echo [启动] 等待后端服务器就绪 (端口 %BACKEND_PORT%)...
echo [启动] 等待后端服务器就绪 (端口 %BACKEND_PORT%)... >> %LOG_FILE%

set /a COUNT=0
:WAIT_LOOP
if %COUNT% GEQ 30 (
    echo [错误] 等待后端服务器超时
    echo [错误] 等待后端服务器超时 >> %LOG_FILE%
    taskkill /F /IM python.exe >nul 2>&1
    pause
    exit /b 1
)

netstat -ano | findstr ":%BACKEND_PORT%" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [启动] 后端服务器已就绪！
    echo [启动] 后端服务器已就绪！ >> %LOG_FILE%
    goto START_APP
)

timeout /t 1 /nobreak >nul
set /a COUNT+=1
goto WAIT_LOOP

:START_APP
echo [启动] 正在查找 pake 应用...
echo [启动] 正在查找 pake 应用... >> %LOG_FILE%

if exist "%PAKE_APP_NAME%" (
    set APP_PATH=%PAKE_APP_NAME%
) else if exist "%LOCALAPPDATA%\Programs\LogFilter\%PAKE_APP_NAME%" (
    set APP_PATH=%LOCALAPPDATA%\Programs\LogFilter\%PAKE_APP_NAME%
) else if exist "%USERPROFILE%\Desktop\%PAKE_APP_NAME%" (
    set APP_PATH=%USERPROFILE%\Desktop\%PAKE_APP_NAME%
) else (
    echo [错误] 找不到 %PAKE_APP_NAME%
    echo [错误] 找不到 %PAKE_APP_NAME% >> %LOG_FILE%
    echo [提示] 请确保已使用 pake 打包应用，并放在正确的位置
    echo [提示] 请确保已使用 pake 打包应用，并放在正确的位置 >> %LOG_FILE%
    taskkill /F /IM python.exe >nul 2>&1
    pause
    exit /b 1
)

echo [启动] 找到应用: !APP_PATH!
echo [启动] 找到应用: !APP_PATH! >> %LOG_FILE%

echo [启动] 正在启动应用...
echo [启动] 正在启动应用... >> %LOG_FILE%

start "" "!APP_PATH!"

echo ================================================= >> %LOG_FILE%
echo [完成] 应用已成功启动！ >> %LOG_FILE%
echo [完成] 按 Ctrl+C 停止应用 >> %LOG_FILE%
echo ================================================= >> %LOG_FILE%

echo =================================================
echo [完成] 应用已成功启动！
echo [完成] 按 Ctrl+C 停止应用
echo =================================================

:WAIT_LOOP_APP
timeout /t 1 /nobreak >nul
goto WAIT_LOOP_APP

:CLEANUP
echo [停止] 正在关闭后端服务器...
echo [停止] 正在关闭后端服务器... >> %LOG_FILE%

taskkill /F /IM python.exe >nul 2>&1

echo [停止] 后端服务器已关闭
echo [停止] 后端服务器已关闭 >> %LOG_FILE%

echo [停止] 应用已停止
echo [停止] 应用已停止 >> %LOG_FILE%

endlocal
