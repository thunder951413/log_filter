# LogFilter 架构文档

> 面向开发者与 AI 助手的快速参考，帮助理解项目结构与模块职责。

## 项目定位

本地日志分析桌面工具。Python (Dash) 提供分析能力，Electron 打包为桌面应用，支持 macOS / Windows / Linux。

## 整体架构

```
用户交互
    │
    ▼  ┌─────────────────────────────────────────────┐
    │   Electron 桌面壳 (electron/main.js)           │
    │   - 启动 Python 后端子进程                      │
    │   - 创建 BrowserWindow 加载 http://127.0.0.1:8052 │
    │   - 自动更新 (electron-updater)                │
    │   - 文件拖拽、启动等待页、失败提示页            │
    └───┴─────────────────┬───────────────────────────┘
                          │ spawn + HTTP wait (最多90s)
    ┌─────────────────────▼───────────────────────────┐
    │   Python 后端 (app.py, 端口 8052)               │
    │                                                  │
    │   ┌─ Dash Web 界面 (SPA) ──────────────────┐    │
    │   │  日志管理 | 配置管理 | 日志过滤 | 对比  │    │
    │   │      ┌─ 过滤结果(5种视图) ──┐           │    │
    │   │      │ 滚动窗口分片加载      │           │    │
    │   │      └──────────────────────┘           │    │
    │   └─────────────────────────────────────────┘    │
    │                                                  │
    │   ├─ HighlightCache (LRU 高亮缓存)               │
    │   ├─ SearchMatchCache (搜索缓存)                  │
    │   ├─ 过滤引擎 (rg/grep/findstr/pwsh/Python)       │
    │   ├─ 流程分析 (flows.json 配对/序列)              │
    │   └─ freecode_bridge/ (AI Agentic Loop)           │
    │       ├─ FreeCodeCliClient (子进程通信)            │
    │       └─ FreeCodeWebBridge (会话管理)              │
    └─────────────────────────────────────────────────┘
                          │
    ┌─────────────────────▼───────────────────────────┐
    │   前端增强 (assets/ *.js)                        │
    │   rolling.js        ─ 虚拟滚动窗口              │
    │   search_jump.js    ─ 搜索与跳转                │
    │   chat_window.js    ─ AI 聊天浮动窗口           │
    │   ai_keyword_path_chat.js ─ AI 关键字路径分析    │
    │   log_context_menu.js ─ 右键菜单                │
    │   compare_sync.js   ─ 对比同步滚动              │
    │   toast.js          ─ Toast 通知系统            │
    └─────────────────────────────────────────────────┘
```

## 关键模块

### `app.py` — 主应用 (~10200 行)

单体式 Dash 应用，承载全部后端逻辑：

| 功能区 | 说明 |
|--------|------|
| `LOG_PREFIX_PATTERNS` | 预编译日志前缀正则，支持多种日志格式 |
| `HighlightCache` | LRU 高亮缓存，SHA1 键 + 有限采样避免大文本哈希 |
| `SearchMatchCache` | 搜索匹配 LRU 缓存 |
| 日志加载 | 支持拖拽导入、大文件流式加载、自动编码检测 |
| 关键字过滤 | 保留/排除关键字，多配置切换，异步后台过滤 |
| 四种过滤后端 | 按优先级自动选择：rg > grep > findstr > PowerShell > Python |
| 流程分析 | 基于 `flows.json` 的配对起止 + 序列步骤检测（仅 AI 分析时触发） |
| AI 流程状态分析 | 后台线程 + 前端轮询架构，实时流式显示 AI 交互过程（prompt、工具调用、响应生成） |
| 配置管理 | `configs/` (18个) + `config_groups/` 多场景规则复用 |
| AI 分析 | 通过 `freecode_bridge` 调用 LLM 进行源码定位和错误分析 |
| 可视化流程图 | 将 AI 分析的流程数据渲染为卡片式流程图，颜色标识状态（绿=正常，红=异常，黄=警告） |
| API 接口 | 滚动窗口 (`/api/get-log-window`)、聊天 SSE (`/api/free-code/chat/<session>/stream`) |

### `freecode_bridge/` — AI CLI 集成

| 文件 | 职责 |
|------|------|
| `free_code_cli_client.py` | 与 `freecode-cli` 子进程通信（JSON over stdin/stdout） |
| `web_bridge.py` | 会话管理：每个 web session 对应一个 CLI 进程 |
| `__init__.py` | 模块入口，可选导入 `api_server` |

核心类：

| 类 | 职责 |
|------|------|
| `FreeCodeCliClient` | CLI 子进程管理、发送/接收消息、stdout/stderr 分离 |
| `FreeCodeWebBridge` | 多会话管理，线程安全，session_id → client 映射 |
| `WebBridgeSession` | session_id → client 映射和锁保护 |

AI Agent 拥有 4 个工具：
- `search_source_code` — 在源码目录搜索关键字
- `read_source_file` — 读取源码文件内容
- `list_directory` — 列出目录结构
- `grep_source_code` — 在源码中 grep 匹配

### `electron/` — 桌面壳

| 文件 | 职责 |
|------|------|
| `main.js` | Electron 主进程：启动 Python、创建窗口、自动更新、日志、文件拖拽 |
| `preload.js` | 预加载脚本，暴露 IPC 接口给渲染进程 (contextBridge) |

关键行为：
- 端口默认 8052，可通过环境变量 `LOG_FILTER_PORT` 覆盖
- 启动时轮询后端就绪（最多 180 次 × 500ms = 90s）
- Linux 下禁用沙箱兼容模式
- 启动等待页 + 启动失败提示页，避免白屏
- 支持 macOS 文件拖拽到 Dock 图标

### `assets/` — 前端增强

| 文件 | 行数 | 功能 |
|------|------|------|
| `rolling.js` | 610 | 虚拟滚动窗口：分片加载、debounce 监听、预取、中心行持久化 |
| `search_jump.js` | 290 | 全局搜索（LRU 40条缓存）、行号跳转、Enter/快捷键 |
| `chat_window.js` | 798 | AI 聊天浮动窗口：拖拽、缩放、最小化、SSE 流式打字机 |
| `chat_window.css` | 486 | 聊天窗口样式（毛玻璃效果） |
| `ai_keyword_path_chat.js` | 394 | AI 关键字路径聊天模态框：自动分析、配置生成 |
| `log_context_menu.js` | 157 | 日志视图右键菜单（Chat / Copy） |
| `log_context_menu.css` | 78 | 右键菜单样式 |
| `compare_sync.js` | 103 | 日志对比双栏同步滚动 |
| `toast.js` | 189 | Toast 通知系统（成功/错误/信息/警告） |
| `toast.css` | 137 | Toast 样式 |
| `log_selection.css` | 58 | 日志行选择模式样式（勾选模式） |
| `flow_chart.css` | 85 | AI 流程分析可视化流程图样式 + 加载动画 |

关键前端机制：
- **虚拟滚动**：仅加载可见区域行，`/api/get-log-window` 后端分片，120ms debounce
- **SSE 流式**：AI 聊天通过 `EventSource` 实现打字机效果
- **localStorage**：会话持久化（聊天历史、窗口状态、中心行位置）

### `scripts/` — 构建

| 文件 | 职责 |
|------|------|
| `pack.js` | 多平台打包：PyInstaller 打 Python + electron-builder 打 Electron |
| `setup_conda.sh` | Conda 环境配置 |
| `trigger_github_build.sh` | 触发 GitHub Actions 构建 |

## 配置文件

| 文件 | 用途 |
|------|------|
| `settings.json` | 上下文行数 (`lines_before/after`)、预取阈值 (`prefetch_threshold`) |
| `flows.json` | 流程分析规则：`paired`（起止配对）+ `sequences`（有序步骤序列） |
| `string_data.json` | 关键字分类数据（15 个分类） |
| `keyword_annotations.json` | 关键字标注数据（关键字 → 说明文本） |
| `temp_keywords.json` | 临时关键字持久化 |
| `user_selections.json` | 用户选择状态持久化 |
| `external_program_config.json` | 外部程序路径配置 |
| `configs/*.json` | 日志过滤规则配置文件目录（18 个现有配置） |
| `config_groups/config_groups.json` | 配置分组（COMMON / TCL / ROKU） |

## 依赖

### Python (`requirements.txt`)
- `dash` + `dash-bootstrap-components` — Web 框架
- `plotly` + `pandas` — 数据可视化
- `openai>=1.0.0` — AI 分析能力

### Node (`package.json`)
- `electron ^39.2.5` — 桌面壳
- `electron-builder ^24.9.1` — 打包
- `electron-log ^5.4.3` — 日志
- `electron-updater ^6.6.2` — 自动更新

## 数据流

### 日志过滤流
```
日志文件 → app.py 按 LOG_PREFIX_PATTERNS 正则拆分为日志行
         → 关键字过滤 (keep/filter 规则 → 多后端自动选择)
         → HighlightCache 缓存高亮结果 (SHA1 键 + 有限采样)
         → 结果写入 temp/ 临时文件 + 生成行偏移索引
         → 前端 rolling.js 通过 /api/get-log-window 分片请求
         → 虚拟滚动窗口渲染可见区域
```

### AI 分析流
```
用户选中错误行 → 行选择模式 (勾选)
         → 点击 AI 分析 → chat_window.js 发送请求
         → Dash 回调 → freecode_bridge 创建/复用 CLI session
         → freecode-cli 子进程启动 Agentic Loop
         → LLM 自主调用 search_source_code / read_source_file 等工具
         → 多轮迭代分析 → SSE 流式回传前端 (打字机效果)
         → 用户可追问 → 保持 session 上下文
```

### AI 流程状态分析流（实时流式）
```
用户点击「AI 流程状态分析」按钮
         → start_ai_flow_analysis callback
             → 验证过滤结果存在
             → 保存过滤日志到 temp/ai_flow_input_{uuid}.txt
             → 初始化 _ai_flow_tasks 任务记录
             → 启动 _ai_flow_worker 后台线程
             → 启用 dcc.Interval (500ms)   ← 立即返回
         
后台线程 (_ai_flow_worker):
         → bridge.ensure_session(task_id)
         → session.client.send_text(prompt)
         → 循环 read_event():
             → system(init)     → 记录事件
             → system(can_use_tool) → 记录工具调用事件
             → assistant_partial   → 记录增量文本事件
             → assistant          → 记录完整响应事件
             → result             → 标记完成

前端轮询 (poll_ai_flow_progress):
         → 每 500ms 读取 _ai_flow_tasks
         → _render_ai_flow_events() 渲染新事件到实时日志面板
         → status == "done":
             → parse_ai_flow_response() 解析 JSON
             → render_flow_chart() 渲染可视化流程图
             → 保存交互日志到 ai-flow-interaction-log store
             → 显示「交互日志」按钮，可打开 modal 查看完整 prompt + 响应
```

### 日志对比流
```
日志 A + 日志 B → 分别应用同一过滤规则
         → 左右分栏渲染结果
         → compare_sync.js 监听滚动事件
         → 同步/异步模式切换
         → 忽略行首 N 字符 (跳过时间戳等前缀)
```

## UI 布局

应用为 Dash 单页应用 (SPA)，使用 `dash-bootstrap-components` 构建：

### 主 Tab 页
| Tab | 关键 UI 组件 |
|-----|-------------|
| 日志管理 | 文件列表 + 拖拽上传区 + 外部程序配置 |
| 配置管理 | 关键字编辑器 + 分类选择器 + JSON 预览 |
| 日志过滤 | 文件选择器 + 配置组选择器 + 关键字输入 + 过滤按钮 + 进度条 |
| 日志对比 | 左右文件选择器 + 配置组选择器 + 差异视图 |

### 过滤结果子视图 (5 种)
| 视图 | 说明 |
|------|------|
| 过滤结果 | 高亮命中的过滤后内容（滚动窗口） |
| 源文件 | 原始日志文件内容 |
| 高亮显示 | 仅高亮命中的行 |
| 注释 | 带关键字注释的日志 |
| 流程视图 | AI 流程状态分析入口。默认显示提示文案，点击「AI 流程状态分析」触发实时分析。分析过程中实时展示 AI 交互日志（prompt 发送、工具调用、流式响应），完成后渲染为可视化流程图（彩色状态标识），可通过「交互日志」按钮查看完整 prompt + 原始响应 |

## UI 逻辑细节

### 虚拟滚动 (rolling.js)
- 客户端仅渲染可见区域，`/api/get-log-window` 返回指定范围行
- debounce 120ms 监听滚动事件
- 预取阈值：接近窗口边缘时自动请求下一块
- 中心行持久化：跨 DOM 重渲染保持位置 (`__savedCentersBySession`)
- 后端返回 HTML 片段，关键字用黄色背景标记

### AI 聊天 (chat_window.js)
- FAB 按钮：点击展开/收起
- 浮动窗口：可拖拽、缩放、最小化
- SSE 流式：`/api/free-code/chat/<session>/stream`
- 附件系统：选中日志片段作为分析上下文
- 工作目录管理：可切换 free-code 的工作目录

### AI 关键字路径分析 (ai_keyword_path_chat.js)
- 独立模态框，专门用于探索代码中的日志关键字
- 三种模式：自动分析、针对性分析、关键字配置生成
- 生成的配置通过隐藏 input 同步回 Dash 回调

## 构建与发布

```bash
# 本地打包
npm run pack:mac    # macOS DMG + ZIP
npm run pack:win    # Windows NSIS
npm run pack:linux  # Linux tar.gz

# CI 自动构建
# 推送 v* 标签 → GitHub Actions → 多平台产物发布
```

### 打包流程
1. PyInstaller 打包 `app.py` → `log_filter_server` 可执行
2. electron-builder 打包 Electron + PyInstaller 产物
3. extraResources 携带服务端到 `dist/`

## 已知关注点

- `app.py` 单文件 ~10900 行，维护成本高，建议按功能区拆分
- `freecode-cli` 二进制 ~220MB，显著增加分发体积
- `FEATURE_AI_ANALYSIS.md` 描述完整 AI 分析方案设计，需对照确认实现进度
- 仓库中存在大量 macOS 资源 fork 文件 (`._*`)，建议加入 `.gitignore`
- 前端增强模块使用原生 JS，与 Dash 回调体系通过隐藏 input / localStorage 桥接
- 全局变量管理较松散（`chatStates`、`activeJobTimers` 等挂载在 `window` 对象上）
- AI 流程状态分析的后台任务通过 `_ai_flow_tasks` 全局字典管理（带锁），worker 线程使用 `session.client.read_event()` 流式读取 AI 事件
- `dcc.Interval` 500ms 轮询存在最大 500ms 的显示延迟，可通过调整 `_AI_FLOW_PROGRESS_INTERVAL_MS` 优化响应速度
