# LogFilter 应用启动指南

## 概述

本指南介绍如何使用 `start_app.py` 脚本启动 LogFilter 应用。该脚本会自动：
1. 启动 Python 后端服务器
2. 等待服务器就绪
3. 启动 pake 打包的前端应用
4. 管理进程生命周期（关闭时自动清理）

## 前置条件

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 使用 pake 打包应用

如果还没有打包应用，需要先使用 pake 打包：

```bash
# 方法1：先启动后端，然后打包
python app.py
# 在另一个终端执行
pake http://localhost:8052 --name LogFilter

# 方法2：打包时指定更多选项
pake http://localhost:8052 --name LogFilter --icon icon.png
```

打包完成后，你会得到：
- **macOS**: `LogFilter.app`
- **Windows**: `LogFilter.exe`
- **Linux**: `LogFilter`

将打包好的应用放在以下任一位置：
- 项目根目录
- `~/Applications/` (macOS)
- `/Applications/` (macOS)
- `~/AppData/Local/LogFilter/` (Windows)
- `~/.local/bin/` (Linux)

## 使用方法

### 启动应用

```bash
python start_app.py
```

或者（如果已添加执行权限）：

```bash
./start_app.py
```

### 停止应用

在运行脚本的终端中按 `Ctrl+C`，脚本会自动：
1. 关闭 pake 应用
2. 停止 Python 后端服务器
3. 清理所有进程

## 功能特性

### 1. 自动端口检测

脚本会自动检测端口 8052 是否被占用。如果被占用，会提示你是否继续。

### 2. 进程管理

- 自动启动和停止后端进程
- 监控后端进程状态
- 异常退出时自动清理

### 3. 日志记录

所有操作都会记录到 `start_app.log` 文件中，包括：
- 启动/停止时间
- 进程 PID
- 错误信息
- 后端输出

### 4. 跨平台支持

支持以下平台：
- macOS
- Windows
- Linux

## 故障排除

### 问题1：找不到 pake 应用

**错误信息**: `错误: 找不到 LogFilter 应用`

**解决方案**:
1. 确认已使用 pake 打包应用
2. 检查应用是否在正确的位置
3. 检查应用名称是否为 `LogFilter`

### 问题2：端口被占用

**错误信息**: `警告: 端口 8052 已被占用`

**解决方案**:
1. 检查是否有其他实例正在运行
2. 使用 `lsof -i :8052` (macOS/Linux) 或 `netstat -ano | findstr :8052` (Windows) 查找占用端口的进程
3. 终止占用端口的进程

### 问题3：后端启动失败

**错误信息**: `后端服务器异常退出`

**解决方案**:
1. 检查 `start_app.log` 查看详细错误信息
2. 确认 Python 依赖已正确安装
3. 手动运行 `python app.py` 检查是否有错误

### 问题4：应用无法启动

**错误信息**: `启动应用失败`

**解决方案**:
1. 确认 pake 应用文件存在且可执行
2. 检查应用权限（macOS 可能需要允许运行）
3. 查看 `start_app.log` 获取详细错误信息

## 高级配置

### 修改端口

如果需要修改后端端口，编辑 `start_app.py`：

```python
BACKEND_PORT = 8052  # 修改为你需要的端口
```

同时需要修改 `app.py` 中的端口配置。

### 修改应用名称

如果使用了不同的应用名称，编辑 `start_app.py`：

```python
PAKE_APP_NAME = "YourAppName"  # 修改为你的应用名称
```

### 禁用日志记录

如果不需要日志记录，可以注释掉日志写入代码：

```python
# 注释掉日志文件写入
# with open(LOG_FILE, "a", encoding="utf-8") as f:
#     f.write(log_message + "\n")
```

## 开发模式

如果只是开发测试，可以分别启动后端和前端：

```bash
# 终端1：启动后端
python app.py

# 终端2：打开浏览器访问
open http://localhost:8052
```

## 更新日志

- **v1.0** (2026-03-19)
  - 初始版本
  - 支持自动启动后端和前端
  - 进程管理和日志记录
  - 跨平台支持

## 技术支持

如有问题，请查看：
1. `start_app.log` 日志文件
2. Python 后端的输出
3. pake 应用的错误信息
