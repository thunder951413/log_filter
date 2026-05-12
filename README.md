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

LogFilter 的核心价值是把"人工翻日志"变成"规则化过滤、流程化查看、可复用沉淀、可 AI 辅助分析"的本地日志排查工作台。

- **提升日志排查效率**：通过保留关键字、屏蔽关键字、配置组和临时关键字快速缩小日志范围，避免在大日志中逐行查找。
- **沉淀可复用分析规则**：把常见问题场景保存为配置文件和配置文件组，遇到类似问题时可以直接复用。
- **适合大日志本地分析**：使用异步过滤、临时文件、行索引和滚动窗口分片加载，降低大文件一次性渲染带来的性能压力。
- **支持问题对比定位**：对两份日志使用同一规则过滤后进行左右对比，便于比较正常/异常日志、不同设备日志或不同版本日志。
- **让日志更容易理解**：通过关键字注释、流程视图和序列流程，把零散日志还原成更接近业务流程的视图。
- **降低工具使用门槛**：提供可视化页面和桌面应用形态，减少对命令行过滤工具的依赖。
- **连接 AI 辅助分析**：可选择关键日志片段并携带配置组、日志文件、关联配置文件和选中行数等上下文交给 AI 分析，辅助定位原因并沉淀经验。

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

或使用启动脚本：

```bash
./run_app.sh
```

浏览器访问：

```text
http://127.0.0.1:8052
```

### Electron 桌面壳运行

```bash
npm ci
npm run electron:start
```

## 核心能力

### 日志过滤

- 从 `logs/` 目录选择 `.txt` / `.log` / `.text` 日志文件进行分析
- 支持"保留关键字"和"屏蔽关键字"两类规则，适合快速收敛大日志中的有效片段
- 支持临时关键字，不需要写入长期配置即可临时追加保留或屏蔽条件
- 支持按配置文件组批量加载规则，例如 `COMMON`、`TCL`、`ROKU` 等问题场景
- 支持过滤结果、源文件、高亮显示、注释、流程视图五种展示模式
- 支持关键字高亮、全局搜索上一个/下一个、行号跳转、快速回到顶部/底部
- 支持选择日志行并发送到 AI 分析入口，便于围绕具体错误片段继续定位
- 后台异步过滤，前端通过进度条轮询任务状态
- 过滤后端支持自动选择 `rg` (ripgrep) > `grep` > `findstr` > PowerShell > Python 流式回退

### 大日志处理

- 过滤任务在后台线程中异步执行，页面通过进度条轮询任务状态
- 过滤结果先写入 `temp/` 临时文件，并生成行偏移索引，避免一次性把大文件全部渲染到页面
- 结果视图使用滚动窗口分片加载（虚拟滚动），适合查看较大的过滤结果
- 自动检测文件编码，并优先使用字节级匹配降低逐行解码开销
- 支持过滤后高亮缓存（`HighlightCache`，LRU + SHA1 键），减少重复渲染开销

### 日志对比

- 支持选择两份日志文件，使用同一组过滤规则先过滤再对比
- 支持按配置文件组加载对比规则
- 支持设置"忽略行首 N 个字符"，用于跳过时间戳、线程号等易变前缀
- 提供左右分栏的差异视图和同步滚动开关（`compare_sync.js`），便于对比两次运行或两台设备的差异

### 流程视图与关键字注释

- 支持为关键字维护说明文本，在日志视图中辅助理解关键事件
- 支持在 `flows.json` 中维护配对流程，例如开始关键字和结束关键字
- 支持维护序列流程，例如 `step1 -> step2 -> step3`，用于检查关键事件顺序
- 内置正则生成器，可从多个关键字生成"同时包含""任一包含""按顺序包含"等规则

### 配置管理

- 关键字按 15 个分类维护（`string_data.json`），支持新增、删除和分类筛选
- 规则可保存为 `configs/*.json` 配置文件（18 个现有配置），支持加载、删除
- 配置文件组保存在 `config_groups/config_groups.json`，可把多个配置组合成一个分析场景（COMMON / TCL / ROKU）
- 支持区分保留字符串与过滤字符串，方便把常用排除项固化进配置
- 临时关键字保存在 `temp_keywords.json`，适合短期复用但不污染正式配置

### 日志管理

- 支持拖拽或点击上传日志文件
- 上传文件统一保存到 `logs/` 目录
- 文件列表展示文件名、大小、修改时间，并提供选择和删除操作
- 支持配置外部程序路径，可从页面调用外部编辑器或查看器打开当前日志

### AI 日志分析

- **行选择模式**：过滤结果页支持进入行选择模式（勾选日志行），将选中的日志片段作为分析上下文
- **Agentic Loop**：LLM 可自主调用 4 个工具（`search_source_code`、`read_source_file`、`list_directory`、`grep_source_code`）进行多轮迭代分析
- **AI 聊天浮动窗口**（`chat_window.js/css`）：右下角悬浮窗口，支持拖拽、缩放、最小化、SSE 流式打字机效果
- **AI 关键字路径聊天**（`ai_keyword_path_chat.js`）：独立的 AI 聊天模态框，用于探索代码中的日志关键字，支持自动分析、针对性分析、关键字配置生成
- **AI 流程状态分析**：在过滤结果页的「流程视图」tab 中，基于已过滤日志和配置组，通过 AI 自动识别业务流程运行状态。后台线程实时流式交互，前端轮询展示 AI 的 prompt 发送、工具调用、响应生成全过程。分析完成后以可视化流程图展示（绿色=正常、红色=异常、黄色=警告），支持查看完整交互日志（prompt + 原始响应）。
- **本地 CLI 桥接**：通过 `freecode_bridge/` 与 `freecode-cli` 子进程通信（JSON over stdin/stdout）
- **技能沉淀**：支持为配置文件组生成/维护专用 skill，把历史分析经验沉淀为可复用知识

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

## UI 布局

应用为 Dash 单页应用 (SPA)，使用 `dash-bootstrap-components` 构建响应式布局，包含以下主要 Tab 页面：

| Tab | 功能 | 关键组件 |
|-----|------|---------|
| 日志管理 | 上传/删除/选择日志文件 | 文件列表 + 拖拽上传区 + 外部程序配置 |
| 配置管理 | 编辑关键字分类、配置文件、配置组 | 关键字编辑器 + 分类选择器 + JSON 预览 |
| 日志过滤 | 核心过滤功能 | 文件选择器 + 配置组选择器 + 关键字输入 + 过滤按钮 + 进度条 |
| 日志对比 | 双栏日志对比 | 左右文件选择器 + 配置组选择器 + 差异视图 |

过滤结果包含 5 种展示模式（子 Tabs 切换）：过滤结果、源文件、高亮显示、注释、流程视图。

## 前端增强模块

| 文件 | 功能 |
|------|------|
| `rolling.js` | 虚拟滚动窗口，分片加载日志行，debounce 监听，中心行持久化 |
| `search_jump.js` | 全局搜索（LRU 缓存 40 个结果）、行号跳转、快捷键 |
| `chat_window.js/css` | AI 聊天浮动窗口，SSE 流式响应，附件系统，工作目录管理 |
| `ai_keyword_path_chat.js` | AI 关键字路径聊天模态框，配置生成 |
| `log_context_menu.js/css` | 日志视图右键菜单（Chat / Copy） |
| `compare_sync.js` | 日志对比双栏同步滚动 |
| `toast.js/css` | Toast 通知系统 |
| `log_selection.css` | 日志行选择模式样式 |
| `flow_chart.css` | AI 流程分析可视化流程图样式 |

## 典型使用流程

1. 在「日志管理」中上传 `.txt`、`.log` 或 `.text` 日志文件。
2. 在「配置管理」中维护关键字、保存配置文件，并按问题场景组合成配置文件组。
3. 回到「日志过滤」，选择日志文件和配置文件组。
4. 如有需要，通过「临时关键字」追加一次性的保留或屏蔽条件。
5. 点击「过滤」，在过滤结果中搜索、跳转、查看高亮命中内容。
6. 切换到「源文件」「注释」「流程视图」辅助定位上下文。
7. 需要对比时进入「日志对比」，选择两份日志并使用同一规则生成差异视图。
8. 需要进一步定位时，选择关键日志行并触发 AI 分析（聊天窗口或关键字路径分析）。

## 项目结构

```text
log_filter/
├── app.py                          # Dash 后端主程序
├── app.spec                        # PyInstaller 打包规格
├── log_filter_server.spec          # 服务端打包规格
├── requirements.txt                # Python 依赖
├── package.json                    # Node.js + Electron 配置
│
├── electron/
│   ├── main.js                     # Electron 主进程
│   └── preload.js                  # 预加载脚本
│
├── assets/                         # 前端增强脚本和样式
│   ├── rolling.js                  # 虚拟滚动窗口
│   ├── search_jump.js              # 全局搜索与行跳转
│   ├── chat_window.js              # AI 聊天浮动窗口
│   ├── chat_window.css             # 聊天窗口样式
│   ├── ai_keyword_path_chat.js     # AI 关键字路径聊天
│   ├── log_context_menu.js         # 日志右键菜单
│   ├── log_context_menu.css        # 右键菜单样式
│   ├── compare_sync.js             # 日志对比同步滚动
│   ├── toast.js                    # Toast 通知系统
│   ├── toast.css                   # Toast 样式
│   └── log_selection.css           # 日志行选择样式
│
├── freecode_bridge/                # AI CLI 桥接层
│   ├── __init__.py
│   ├── free_code_cli_client.py     # CLI 子进程通信
│   └── web_bridge.py               # Web 会话管理
│
├── configs/                        # 日志过滤规则配置 (18个)
├── config_groups/
│   └── config_groups.json          # 配置文件组
├── logs/                           # 日志文件存放目录
├── temp/                           # 过滤结果临时文件
├── scripts/
│   ├── pack.js                     # 多平台打包脚本
│   ├── trigger_github_build.sh     # 触发 GitHub Actions 构建
│   └── setup_conda.sh              # Conda 环境配置
├── settings.json                   # 应用设置
├── flows.json                      # 流程分析规则
├── string_data.json                # 关键字分类数据 (15类)
├── keyword_annotations.json        # 关键字注释
├── temp_keywords.json              # 临时关键字
├── user_selections.json            # 用户选择持久化
├── external_program_config.json    # 外部编辑器路径
├── run_app.sh                      # 直接运行脚本
├── activate_venv.sh                # 激活虚拟环境
└── install_deps.bat                # Windows 依赖安装
```

## 技术栈

### 后端 (Python)
| 技术 | 用途 |
|------|------|
| Python 3.10+ | 主开发语言 |
| Dash 2.x | Web 框架（Flask + React） |
| dash-bootstrap-components | UI 组件库 |
| Plotly | 数据可视化 |
| Pandas | 数据处理 |
| OpenAI >=1.0.0 | AI 分析 (LLM 调用) |
| PyInstaller | Python 打包为单文件可执行 |

### 前端 (浏览器)
| 技术 | 用途 |
|------|------|
| Dash 自动生成 | 核心 UI |
| 原生 JavaScript (vanilla JS) | 所有 assets/*.js 为手写原生 JS |
| CSS3 | 现代化 UI（毛玻璃效果、动画） |
| Fetch API | 与后端 HTTP 通信 |
| SSE (Server-Sent Events) | AI 聊天流式响应 |
| ResizeObserver / MutationObserver | DOM 变化监听 |
| localStorage | 会话持久化 |

### 桌面壳 (Electron)
| 技术 | 用途 |
|------|------|
| Electron 39.x | 桌面应用壳 |
| electron-builder 24.x | 多平台打包 |
| electron-updater 6.x | 自动更新 |
| electron-log 5.x | 日志系统 |

### 构建与 CI/CD
| 技术 | 用途 |
|------|------|
| npm | Node.js 包管理 |
| pip | Python 包管理 |
| PyInstaller | Python → 单文件可执行 |
| electron-builder | Electron → 桌面安装包 |
| GitHub Actions | 自动构建/发布 |

### AI 集成
| 技术 | 用途 |
|------|------|
| freecode-cli | 本地 LLM CLI 工具 |
| OpenAI SDK | LLM 调用（兼容 OpenAI API） |
| Agentic Loop | LLM 自主工具调用（4 个工具） |

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

## 常见问题

### 启动后白屏

通常表示桌面端后端服务尚未完成启动。如果持续失败，请查看应用日志并反馈错误信息。

### 端口 8052 被占用

可以先检查占用进程：

```bash
lsof -i :8052
```

可通过环境变量 `LOG_FILTER_PORT` 覆盖默认端口。

### Windows 下 npm / npx 调用失败

打包脚本已对 Windows 的 shell 调用做兼容处理，核心逻辑位于 `scripts/pack.js`。

## License

如需许可证信息，请查看仓库根目录中的 LICENSE 文件。
