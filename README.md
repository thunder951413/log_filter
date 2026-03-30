# LogFilter

[![Build and Release](https://github.com/thunder951413/log_filter/actions/workflows/build.yml/badge.svg)](https://github.com/thunder951413/log_filter/actions/workflows/build.yml)
[![GitHub release](https://img.shields.io/github/v/release/thunder951413/log_filter)](https://github.com/thunder951413/log_filter/releases)
[![Platforms](https://img.shields.io/badge/platforms-macOS%20%7C%20Windows%20%7C%20Linux-blue)](https://github.com/thunder951413/log_filter/releases)

LogFilter 是一个面向本地日志分析场景的桌面工具，使用 Python + Dash 提供分析能力，并通过 Electron 打包为 macOS / Windows / Linux 桌面应用。

它适合处理体积较大的日志文件、复用关键字过滤规则、按问题场景管理配置，并把原本依赖浏览器访问的分析工具整理成更容易分发和使用的桌面程序。

## 为什么用 LogFilter

- 快速过滤日志中的关键信息，减少人工翻找
- 通过配置文件复用常见分析规则
- 支持配置组，适合 CI、播放链路、业务模块等不同场景
- 支持桌面端拖拽导入日志文件
- 支持 GitHub Actions 自动构建和发布多平台安装包

## 快速开始

### 直接下载桌面版

前往 [Releases](https://github.com/thunder951413/log_filter/releases) 下载对应平台产物：

- macOS：`LogFilter-macOS.zip`
- Windows：`LogFilter-Windows.zip`
- Linux：`LogFilter-Linux.tar.gz`

解压后即可运行。

### 本地源码运行

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

启动应用：

```bash
python app.py
```

浏览器访问：

```text
http://127.0.0.1:8052
```



## 核心能力

### 日志分析

- 支持关键字保留与排除
- 支持多套规则配置切换
- 支持日志拖拽导入

### 配置管理

- 支持 `configs/` 下多配置文件管理
- 支持 `config_groups/` 分组组织配置
- 适合把同一类问题场景固化为可复用分析模板

### 桌面打包

- Python 后端负责 Dash 页面与日志分析逻辑
- Electron 主进程负责启动后端、创建窗口和桌面能力
- PyInstaller + electron-builder 负责生成桌面发行包

## 桌面版说明

桌面版采用 Electron + Python 双进程架构：

- Electron 主进程启动本地后端服务
- Python 后端提供 Web 界面和分析能力
- 桌面窗口在后端就绪后再加载页面

首次启动桌面版时，后端初始化可能需要一段时间。当前版本已增加启动等待页和失败提示页，避免后端未就绪时直接出现白屏。

## 本地打包

### 安装依赖

```bash
npm ci
pip install -r requirements.txt
pip install pyinstaller
```

### 打包命令

```bash
# macOS
npm run pack:mac

# Windows
npm run pack:win

# Linux
npm run pack:linux

# 所有平台
npm run pack:all

# 仅检查打包命令，不实际执行
npm run pack:dry
```

## 自动构建发布

仓库已配置 GitHub Actions 自动构建工作流：

- 推送标签 `v*` 时自动构建并发布
- 支持在 Actions 页面手动触发

工作流入口：

- [Build and Release](https://github.com/thunder951413/log_filter/actions/workflows/build.yml)

构建输出：

- macOS 安装包
- Windows 安装包
- Linux 安装包

相关核心文件：

- `.github/workflows/build.yml`
- `scripts/pack.js`
- `electron/main.js`

## 项目结构

```text
log_filter_web/
├── app.py
├── electron/
│   ├── main.js
│   └── preload.js
├── scripts/
│   └── pack.js
├── assets/
├── configs/
├── config_groups/
├── requirements.txt
└── package.json
```

## 技术栈

- Python
- Dash
- Electron
- PyInstaller
- electron-builder
- GitHub Actions

## 常见问题

### 启动后白屏

通常表示桌面端后端服务尚未完成启动。如果持续失败，请查看应用日志并反馈错误信息。

### 端口 8052 被占用

可以先检查占用进程：

```bash
lsof -i :8052
```

### Windows 下 npm / npx 调用失败

打包脚本已对 Windows 的 shell 调用做兼容处理，核心逻辑位于 `scripts/pack.js`。

## License

如需许可证信息，请查看仓库根目录中的 LICENSE 文件。
