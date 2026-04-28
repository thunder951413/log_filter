# LogFilter 架构文档

> 面向开发者与 AI 助手的快速参考，帮助理解项目结构与模块职责。

## 项目定位

本地日志分析桌面工具。Python (Dash) 提供分析能力，Electron 打包为桌面应用，支持 macOS / Windows / Linux。

## 整体架构

```
┌─────────────────────────────────────────────┐
│  Electron 主进程 (electron/main.js)         │
│  - 启动 Python 后端子进程                    │
│  - 创建 BrowserWindow 加载 http://127.0.0.1:8052 │
│  - 自动更新 (electron-updater)              │
└──────────────┬──────────────────────────────┘
               │ spawn + HTTP wait
┌──────────────▼──────────────────────────────┐
│  Python 后端 (app.py, 端口 8052)            │
│  - Dash Web 界面                             │
│  - 日志加载 / 关键字过滤 / 流程分析          │
│  - 高亮缓存 (HighlightCache)                │
│  - free-code CLI 桥接 (freecode_bridge/)     │
│  - AI 日志分析 (Agentic Loop)               │
└─────────────────────────────────────────────┘
```

## 关键模块

### `app.py` — 主应用 (~9700 行)

单体式 Dash 应用，承载全部后端逻辑：

| 功能区 | 说明 |
|--------|------|
| `LOG_PREFIX_PATTERNS` | 预编译日志前缀正则，支持多种日志格式 |
| `HighlightCache` | LRU 高亮缓存，SHA1 键 + 有限采样避免大文本哈希 |
| 日志加载 | 支持拖拽导入、大文件流式加载 |
| 关键字过滤 | 保留/排除关键字，多配置切换 |
| 流程分析 | 基于 `flows.json` 的配对起止 + 序列步骤检测 |
| 配置管理 | `configs/` + `config_groups/` 多场景规则复用 |
| AI 分析 | 通过 `freecode_bridge` 调用 LLM 进行源码定位和错误分析 |

### `freecode_bridge/` — AI CLI 集成

| 文件 | 职责 |
|------|------|
| `free_code_cli_client.py` | 与 `freecode-cli` 子进程通信（JSON over stdin/stdout） |
| `web_bridge.py` | 会话管理：每个 web session 对应一个 CLI 进程 |
| `__init__.py` | 模块入口，可选导入 `api_server` |

核心类：
- `FreeCodeCliClient` — CLI 子进程管理、发送/接收消息
- `FreeCodeWebBridge` — 多会话管理，线程安全
- `WebBridgeSession` — session_id → client 映射

### `electron/` — 桌面壳

| 文件 | 职责 |
|------|------|
| `main.js` | Electron 主进程：启动 Python、创建窗口、自动更新、日志 |
| `preload.js` | 预加载脚本，暴露 IPC 接口给渲染进程 |

关键行为：
- 端口默认 8052，可通过环境变量 `LOG_FILTER_PORT` 覆盖
- 启动时轮询后端就绪（最多 180 次 × 500ms = 90s）
- Linux 下禁用沙箱兼容模式

### `assets/` — 前端增强

| 文件 | 功能 |
|------|------|
| `chat_window.js/css` | AI 聊天窗口界面 |
| `rolling.js` | 日志流式/滚动加载 |
| `search_jump.js` | 搜索跳转 |
| `log_context_menu.js/css` | 右键上下文菜单 |
| `compare_sync.js` | 日志对比同步滚动 |
| `toast.js/css` | 通知提示组件 |

### `scripts/` — 构建

| 文件 | 职责 |
|------|------|
| `pack.js` | 多平台打包：PyInstaller 打 Python + electron-builder 打 Electron |
| `setup_conda.sh` | Conda 环境配置 |

## 配置文件

| 文件 | 用途 |
|------|------|
| `settings.json` | 上下文行数 (`lines_before/after`)、预取阈值 (`prefetch_threshold`) |
| `flows.json` | 流程分析规则：`paired`（起止配对）+ `sequences`（有序步骤序列） |
| `keyword_annotations.json` | 关键字标注数据 |
| `string_data.json` | 字符串数据 |
| `external_program_config.json` | 外部程序配置 |
| `configs/` | 日志过滤规则配置文件目录 |
| `config_groups/` | 配置分组目录（CI、播放链路、业务模块等场景） |

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

```
用户拖拽日志文件
  → app.py 加载并解析（按 LOG_PREFIX_PATTERNS 拆行）
  → 关键字过滤（保留/排除规则来自当前配置）
  → HighlightCache 缓存高亮结果
  → 前端 rolling.js 流式渲染
  → 用户选择错误行 → chat_window.js 发送
  → freecode_bridge 启动/复用 CLI session
  → CLI Agentic Loop 调用 LLM 分析
  → 结果回传展示
```

## 构建与发布

```bash
# 本地打包
npm run pack:mac    # macOS DMG + ZIP
npm run pack:win    # Windows NSIS
npm run pack:linux  # Linux tar.gz

# CI 自动构建
# 推送 v* 标签 → GitHub Actions → 多平台产物发布
```

## 已知关注点

- `app.py` 单文件 ~9700 行，维护成本高，建议按功能区拆分
- `freecode-cli` 二进制 ~220MB，显著增加分发体积
- `FEATURE_AI_ANALYSIS.md` 描述完整 AI 分析方案设计，需对照确认实现进度
- 仓库中存在大量 macOS 资源 fork 文件 (`._*`)，建议加入 `.gitignore`
