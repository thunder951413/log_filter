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

## 主要价值

LogFilter 的核心价值是把“人工翻日志”变成“规则化过滤、流程化查看、可复用沉淀、可 AI 辅助分析”的本地日志排查工作台。

- **提升日志排查效率**：通过保留关键字、屏蔽关键字、配置组和临时关键字快速缩小日志范围，避免在大日志中逐行查找。
- **沉淀可复用分析规则**：把常见问题场景保存为配置文件和配置文件组，遇到类似问题时可以直接复用。
- **适合大日志本地分析**：使用异步过滤、临时文件、行索引和滚动窗口分片加载，降低大文件一次性渲染带来的性能压力。
- **支持问题对比定位**：对两份日志使用同一规则过滤后进行左右对比，便于比较正常/异常日志、不同设备日志或不同版本日志。
- **让日志更容易理解**：通过关键字注释、流程视图和序列流程，把零散日志还原成更接近业务流程的视图。
- **降低工具使用门槛**：提供可视化页面和桌面应用形态，减少对命令行过滤工具的依赖。
- **连接 AI 辅助分析**：可选择关键日志片段并携带配置组、日志文件、上下文等信息交给 AI 分析，辅助定位原因并沉淀经验。

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

### 日志过滤

- 从 `logs/` 目录选择 `.txt` / `.log` / `.text` 日志文件进行分析
- 支持“保留关键字”和“屏蔽关键字”两类规则，适合快速收敛大日志中的有效片段
- 支持临时关键字，不需要写入长期配置即可临时追加保留或屏蔽条件
- 支持按配置文件组批量加载规则，例如 `COMMON`、`TCL`、`ROKU` 等问题场景
- 支持过滤结果、源文件、注释、流程视图四种展示模式
- 支持关键字高亮、全局搜索上一个/下一个、行号跳转、快速回到顶部/底部
- 支持选择日志行并发送到 AI 分析入口，便于围绕具体错误片段继续定位

### 大日志处理

- 过滤任务在后台线程中异步执行，页面通过进度条轮询任务状态
- 过滤结果先写入 `temp/` 临时文件，并生成行偏移索引，避免一次性把大文件全部渲染到页面
- 结果视图使用滚动窗口分片加载，适合查看较大的过滤结果
- 自动检测文件编码，并优先使用字节级匹配降低逐行解码开销
- 支持过滤后高亮缓存，减少重复渲染开销
- 过滤后端支持自动选择 `rg`、`grep`、`findstr`、PowerShell，外部工具不可用时回退到 Python 流式过滤

### 日志对比

- 支持选择两份日志文件，使用同一组过滤规则先过滤再对比
- 支持按配置文件组加载对比规则
- 支持设置“忽略行首 N 个字符”，用于跳过时间戳、线程号等易变前缀
- 提供左右分栏的差异视图和同步滚动开关，便于对比两次运行或两台设备的差异

### 流程视图与关键字注释

- 支持为关键字维护说明文本，在日志视图中辅助理解关键事件
- 支持在 `flows.json` 中维护配对流程，例如开始关键字和结束关键字
- 支持维护序列流程，例如 `step1 -> step2 -> step3`，用于检查关键事件顺序
- 内置正则生成器，可从多个关键字生成“同时包含”“任一包含”“按顺序包含”等规则

### 配置管理

- 关键字按分类维护，支持新增、删除和分类筛选
- 规则可保存为 `configs/*.json` 配置文件，并支持加载、删除
- 配置文件组保存在 `config_groups/config_groups.json`，可把多个配置组合成一个分析场景
- 支持区分保留字符串与过滤字符串，方便把常用排除项固化进配置
- 临时关键字保存在 `temp_keywords.json`，适合短期复用但不污染正式配置

### 日志管理

- 支持拖拽或点击上传日志文件
- 上传文件统一保存到 `logs/` 目录
- 文件列表展示文件名、大小、修改时间，并提供选择和删除操作
- 支持配置外部程序路径，可从页面调用外部编辑器或查看器打开当前日志

### AI 日志分析

- 过滤结果页支持进入行选择模式，将选中的日志片段作为分析上下文
- 分析请求会携带当前视图、配置文件组、日志文件、关联配置文件和选中行数等上下文
- 可通过本地 `freecode_bridge/` 和 `freecode-cli` 调用 FreeCode 进行日志分析
- 支持为配置文件组生成/维护专用 skill，把历史分析经验沉淀为可复用知识
- LLM 相关配置保存在本地配置文件中，API Key 按脱敏方式展示

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

## 典型使用流程

1. 在「日志管理」中上传 `.txt`、`.log` 或 `.text` 日志文件。
2. 在「配置管理」中维护关键字、保存配置文件，并按问题场景组合成配置文件组。
3. 回到「日志过滤」，选择日志文件和配置文件组。
4. 如有需要，通过「临时关键字」追加一次性的保留或屏蔽条件。
5. 点击「过滤」，在过滤结果中搜索、跳转、查看高亮命中内容。
6. 切换到「源文件」「注释」「流程视图」辅助定位上下文。
7. 需要对比时进入「日志对比」，选择两份日志并使用同一规则生成差异视图。
8. 需要进一步定位时，选择关键日志行并触发 AI 分析。

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
log_filter/
├── app.py
├── assets/
├── configs/
├── config_groups/
│   └── config_groups.json
├── electron/
│   ├── main.js
│   └── preload.js
├── freecode_bridge/
├── logs/
├── scripts/
│   └── pack.js
├── temp/
├── flows.json
├── keyword_annotations.json
├── string_data.json
├── temp_keywords.json
├── external_program_config.json
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
