@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo =================================================
echo LogFilter 依赖安装脚本
echo =================================================
echo.

echo [检查] 检查 Python 是否已安装...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未找到 Python
    echo [提示] 请先安装 Python 3.10 或更高版本
    echo [下载] https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [成功] Python 已安装
python --version
echo.

echo [检查] 检查 requirements.txt 是否存在...
if not exist "requirements.txt" (
    echo [错误] 找不到 requirements.txt 文件
    pause
    exit /b 1
)

echo [成功] 找到 requirements.txt
echo.

echo [安装] 正在安装 Python 依赖包...
echo [安装] 这可能需要几分钟时间，请耐心等待...
echo.

pip install -r requirements.txt

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [错误] 依赖安装失败
    echo [提示] 请检查网络连接或尝试使用国内镜像源：
    echo [命令] pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    pause
    exit /b 1
)

echo.
echo [成功] 依赖安装完成！
echo.

echo [检查] 检查是否需要安装 pake...
pake --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [成功] pake 已安装
    pake --version
    echo.
    echo [提示] 如果需要重新打包应用，请运行：
    echo [命令] pake http://localhost:8052 --name LogFilter
) else (
    echo [信息] pake 未安装
    echo [提示] 如果需要打包应用，请先安装 pake：
    echo [命令] winget install tw93.pake
    echo [下载] https://github.com/tw93/pake
)

echo.
echo =================================================
echo [完成] 所有依赖已安装完成！
echo [完成] 现在可以运行 start_app.bat 启动应用
echo =================================================
echo.

pause
