#!/usr/bin/env python3
import subprocess
import time
import socket
import sys
import os
import signal
import atexit
from datetime import datetime

BACKEND_PORT = 8052
PAKE_APP_NAME = "LogFilter"
BACKEND_PROCESS = None
LOG_FILE = "start_app.log"

def log(message):
    """记录日志到文件和控制台"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"
    print(log_message)
    
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_message + "\n")
    except Exception as e:
        print(f"写入日志失败: {e}")

def check_port(port):
    """检查端口是否被占用"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0
    except Exception as e:
        log(f"检查端口 {port} 失败: {e}")
        return False

def find_pake_app():
    """查找 pake 打包的应用"""
    platform = sys.platform
    
    if platform == 'darwin':
        app_paths = [
            f"{PAKE_APP_NAME}.app",
            os.path.expanduser(f"~/Applications/{PAKE_APP_NAME}.app"),
            f"/Applications/{PAKE_APP_NAME}.app"
        ]
        for path in app_paths:
            if os.path.exists(path):
                return path
    elif platform == 'win32':
        app_paths = [
            f"{PAKE_APP_NAME}.exe",
            os.path.expanduser(f"~/AppData/Local/{PAKE_APP_NAME}/{PAKE_APP_NAME}.exe")
        ]
        for path in app_paths:
            if os.path.exists(path):
                return path
    elif platform.startswith('linux'):
        app_paths = [
            PAKE_APP_NAME,
            f"./{PAKE_APP_NAME}",
            os.path.expanduser(f"~/.local/bin/{PAKE_APP_NAME}")
        ]
        for path in app_paths:
            if os.path.exists(path):
                return path
    
    return None

def cleanup():
    """清理函数：关闭后端进程"""
    global BACKEND_PROCESS
    if BACKEND_PROCESS and BACKEND_PROCESS.poll() is None:
        log("正在关闭后端服务器...")
        try:
            BACKEND_PROCESS.terminate()
            BACKEND_PROCESS.wait(timeout=5)
            log("后端服务器已关闭")
        except subprocess.TimeoutExpired:
            log("后端服务器未响应，强制关闭...")
            BACKEND_PROCESS.kill()
            BACKEND_PROCESS.wait()
        except Exception as e:
            log(f"关闭后端服务器失败: {e}")

def signal_handler(signum, frame):
    """信号处理函数"""
    log(f"收到信号 {signum}，正在清理...")
    cleanup()
    sys.exit(0)

def start_backend():
    """启动 Python 后端服务器"""
    global BACKEND_PROCESS
    
    log("正在启动 Python 后端服务器...")
    
    # 检查 app.py 是否存在
    if not os.path.exists("app.py"):
        log("错误: 找不到 app.py 文件")
        return False
    
    # 检查端口是否已被占用
    if check_port(BACKEND_PORT):
        log(f"警告: 端口 {BACKEND_PORT} 已被占用")
        response = input("是否继续启动? (y/n): ")
        if response.lower() != 'y':
            return False
    
    try:
        # 启动后端进程
        BACKEND_PROCESS = subprocess.Popen(
            [sys.executable, "app.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        log(f"后端进程已启动 (PID: {BACKEND_PROCESS.pid})")
        return True
        
    except Exception as e:
        log(f"启动后端服务器失败: {e}")
        return False

def wait_backend_ready():
    """等待后端服务器就绪"""
    log(f"等待后端服务器就绪 (端口 {BACKEND_PORT})...")
    
    for i in range(30):
        if check_port(BACKEND_PORT):
            log("后端服务器已就绪！")
            return True
        time.sleep(1)
        
        # 检查后端进程是否异常退出
        if BACKEND_PROCESS.poll() is not None:
            log(f"后端服务器异常退出 (退出码: {BACKEND_PROCESS.returncode})")
            return False
    
    log("等待后端服务器超时")
    return False

def start_pake_app():
    """启动 pake 应用"""
    log("正在查找 pake 应用...")
    
    app_path = find_pake_app()
    if not app_path:
        log(f"错误: 找不到 {PAKE_APP_NAME} 应用")
        log("请确保已使用 pake 打包应用，并放在正确的位置")
        return False
    
    log(f"找到应用: {app_path}")
    
    try:
        platform = sys.platform
        if platform == 'darwin':
            subprocess.run(['open', app_path])
        elif platform == 'win32':
            subprocess.Popen([app_path], shell=True)
        elif platform.startswith('linux'):
            subprocess.Popen([app_path])
        
        log("应用已启动")
        return True
        
    except Exception as e:
        log(f"启动应用失败: {e}")
        return False

def monitor_backend():
    """监控后端进程，输出日志"""
    if not BACKEND_PROCESS:
        return
    
    try:
        for line in iter(BACKEND_PROCESS.stdout.readline, ''):
            if line:
                line = line.strip()
                if line:
                    log(f"[后端] {line}")
    except Exception as e:
        log(f"读取后端输出失败: {e}")

def main():
    """主函数"""
    log("=" * 50)
    log("LogFilter 应用启动脚本")
    log("=" * 50)
    
    # 注册清理函数
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动后端
    if not start_backend():
        log("启动失败")
        return 1
    
    # 等待后端就绪
    if not wait_backend_ready():
        log("后端启动失败")
        cleanup()
        return 1
    
    # 启动 pake 应用
    if not start_pake_app():
        log("应用启动失败")
        cleanup()
        return 1
    
    log("=" * 50)
    log("应用已成功启动！")
    log("按 Ctrl+C 停止应用")
    log("=" * 50)
    
    # 监控后端进程
    try:
        while BACKEND_PROCESS.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        log("\n收到中断信号，正在停止...")
    finally:
        cleanup()
    
    log("应用已停止")
    return 0

if __name__ == '__main__':
    sys.exit(main())
