# AI 日志分析功能设计

## 功能概述

在日志过滤结果中，用户选择若干行错误日志（或配置自动错误规则），调用大模型在源码中定位日志输出位置，并分析可能的错误原因。

---

## 整体流程

```
过滤后的日志 → 选择/自动提取错误行 → 构造初始 Prompt → Agentic Loop (LLM 自主调用工具搜索源码/读取文件) → 展示分析结果
```

### 两种实现模式对比

| 模式 | 流程 | 优点 | 缺点 |
|------|------|------|------|
| **单次调用** | 预搜索源码 → 拼接上下文 → 一次 LLM 调用 | 实现简单，Token 可控 | 搜索不准时分析质量差，无法追问 |
| **Agentic Loop** | LLM 自主调用工具（搜索/读文件），多轮迭代 | 分析深度高，可自主探索源码 | Token 消耗不可控，实现复杂 |

**推荐方案**: 采用 Agentic Loop 模式，同时设置最大迭代次数和 Token 上限来控制成本。

---

## 需要实现的模块

### 1. LLM 配置管理

**目标**: 持久化存储用户的 OpenAI 兼容 API 配置。

**需要实现**:

- 新增配置文件 `llm_config.json`，结构如下：

```json
{
  "api_base": "https://api.openai.com/v1",
  "api_key": "sk-xxx",
  "model": "gpt-4o",
  "max_tokens": 4096,
  "temperature": 0.2,
  "source_code_dirs": ["/path/to/project/src"]
}
```

- 新增配置加载/保存函数：`load_llm_config()` / `save_llm_config(config)`
- UI：在「日志管理」Tab 或新增「AI 设置」区域中提供配置表单
  - API Base URL 输入框
  - API Key 输入框（密码类型）
  - Model 名称输入框
  - 源码搜索路径（支持多个目录，逗号分隔或列表管理）
  - 保存/测试连接按钮

**注意事项**:

- API Key 必须脱敏显示，仅展示末 4 位
- 配置文件加入 `.gitignore`，避免密钥泄露

---

### 2. 日志行选择机制

**目标**: 从过滤结果中选择需要分析的日志行。

**需要实现**:

- **手动选择模式**:
  - 在过滤结果视图中，每行日志前增加复选框（checkbox）
  - 支持全选/反选当前页
  - 支持拖拽选择连续行范围
  - 选中行高亮标识
  - 新增 `dcc.Store(id="selected-log-lines-store")` 存储选中行数据

- **自动提取模式**:
  - 新增 `error_patterns.json` 配置文件，预设常见错误日志模式：

  ```json
  {
    "patterns": [
      {"name": "Android Crash", "regex": "AndroidRuntime|FATAL EXCEPTION|backtrace", "lines_context": 5},
      {"name": "ANR", "regex": "ANR in |Reason:", "lines_context": 10},
      {"name": "Memory Error", "regex": "OutOfMemory|low_memory|oom_kill", "lines_context": 3},
      {"name": "Generic Error", "regex": "(?i)\\berror\\b|\\bfatal\\b|\\bcrash\\b|\\bpanic\\b", "lines_context": 3}
    ],
    "auto_extract_enabled": false
  }
  ```

  - 自动提取逻辑：对过滤结果逐行匹配 error_patterns，命中则自动选中该行及上下文行
  - UI：提供「自动提取错误」按钮 + 开关，一键选中匹配行

**选中行数据结构**:

```python
{
  "lines": [
    {
      "line_number": 1234,       # 在过滤结果中的行号
      "source_line_number": 5678, # 在源日志文件中的行号
      "content": "01-01 12:00:00.000 123 456 E PlayerInterface: player.stop failed",
      "timestamp": "01-01 12:00:00.000",
      "tag": "PlayerInterface",
      "level": "E"
    }
  ],
  "log_file": "test.log",
  "session_id": "abc123"
}
```

---

### 3. 日志关键信息提取

**目标**: 从选中的日志行中提取结构化信息，用于构造 LLM Prompt。

**需要实现**:

- 日志行解析器，利用已有的 `LOG_PREFIX_PATTERNS` 正则提取：
  - **时间戳**: 日志发生时间
  - **Tag/Module**: 日志标签（如 `PlayerInterface`、`DtvkitTvInput`）
  - **日志级别**: V/D/I/W/E/F
  - **日志正文**: 去掉前缀后的核心消息
- 关键字符串提取：从日志正文中提取有意义的标识符
  - 函数名（如 `player.stop`、`STB_CiKeysApply`）
  - 错误码（如 `errno=12`、`0xDEADBEEF`）
  - 状态信息（如 `failed`、`timeout`、`rejected`）
- 上下文聚合：将相邻选中行合并为一个分析单元，保留上下文关联

```python
def extract_log_analysis_context(selected_lines, log_file_path):
    """从选中行提取分析上下文"""
    return {
        "summary": "3 errors in PlayerInterface module",
        "entries": [...],
        "keywords": ["player.stop", "failed", "PlayerInterface"],
        "tags": ["PlayerInterface"],
        "time_range": "12:00:00 - 12:00:05"
    }
```

---

### 4. Agentic Loop — LLM 自主工具调用（核心）

**目标**: 让 LLM 像 Cursor / Claude Code 一样，自主决定搜索什么、读取什么文件，多轮迭代直到完成分析。

**背景**: Cursor 等 AI IDE 的核心机制是 **Tool Use + Agentic Loop**：
- 给 LLM 定义一组工具（搜索源码、读取文件、列出目录等）
- LLM 在每轮回复中可以选择调用工具（`tool_calls`）
- 后端执行工具，将结果作为 `tool` 角色消息追加到对话历史
- 再次调用 LLM，直到 LLM 不再调用工具（回复纯文本），循环结束

```
┌─────────────────────────────────────────────────────────┐
│                    Agentic Loop                          │
│                                                         │
│  messages = [system_prompt, user_log_context]           │
│                                                         │
│  while iteration < MAX_ITERATIONS:                      │
│    ┌──────────────┐                                     │
│    │  调用 LLM    │ ← messages                          │
│    └──────┬───────┘                                     │
│           │                                             │
│     ┌─────┴─────┐                                      │
│     │ 有tool_calls?│                                    │
│     └─────┬─────┘                                      │
│       Yes │      No → 返回最终文本，循环结束              │
│           ↓                                             │
│    ┌──────────────┐                                     │
│    │ 执行工具函数  │ (搜索/读文件/列目录)                  │
│    └──────┬───────┘                                     │
│           │                                             │
│    ┌──────────────┐                                     │
│    │ 追加tool消息  │ → messages 继续循环                  │
│    └──────────────┘                                     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

#### 4.1 工具定义（Tool Definitions）

LLM 可调用的工具，通过 OpenAI `tools` 参数传入：

```python
ANALYSIS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_source_code",
            "description": "在源码目录中搜索关键字。支持按 Tag、函数名、日志文本搜索。返回匹配的文件路径和行号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键字，如函数名、日志Tag、错误信息片段"
                    },
                    "search_type": {
                        "type": "string",
                        "enum": ["keyword", "regex", "tag"],
                        "description": "搜索类型：keyword=普通关键字, regex=正则表达式, tag=按日志Tag名搜索"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大返回结果数，默认20",
                        "default": 20
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_source_file",
            "description": "读取源码文件的指定行范围。用于查看搜索结果中感兴趣的文件上下文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "源码文件的绝对路径"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（从1开始），默认1"
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号，默认start_line+50"
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出源码目录的文件和子目录结构。用于了解项目代码组织方式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir_path": {
                        "type": "string",
                        "description": "目录路径，不传则列出配置的源码根目录"
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "最大递归深度，默认2",
                        "default": 2
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep_source_code",
            "description": "在源码中用正则表达式搜索，返回匹配行及上下文。适合精确搜索日志输出语句（如 LOGE、ALOGE 等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "正则表达式模式"
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "上下文行数，默认5",
                        "default": 5
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大返回结果数，默认10",
                        "default": 10
                    }
                },
                "required": ["pattern"]
            }
        }
    }
]
```

#### 4.2 工具执行引擎（Tool Execution Engine）

后端执行 LLM 请求的工具调用，返回结果：

```python
import subprocess
import os

# 工具名 → 执行函数 的映射
TOOL_HANDLERS = {
    "search_source_code": execute_search_source_code,
    "read_source_file":   execute_read_source_file,
    "list_directory":     execute_list_directory,
    "grep_source_code":   execute_grep_source_code,
}

def execute_tool_call(tool_name: str, tool_args: dict, config: dict) -> str:
    """执行单个工具调用，返回结果字符串"""
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = handler(tool_args, config)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


def execute_search_source_code(args: dict, config: dict) -> dict:
    """利用已有 ripgrep 基础设施搜索源码"""
    query = args["query"]
    search_type = args.get("search_type", "keyword")
    max_results = args.get("max_results", 20)
    source_dirs = config.get("source_code_dirs", [])

    results = []
    for src_dir in source_dirs:
        if not os.path.isdir(src_dir):
            continue
        # 复用 _get_rg_command() 构建搜索命令
        rg_cmd = _get_rg_command()
        if not rg_cmd:
            # fallback to grep
            ...
        cmd = [rg_cmd, "--line-number", "--max-count", str(max_results)]
        if search_type == "regex":
            cmd.extend(["-e", query])
        else:
            cmd.extend(["-F", query])
        cmd.extend(["--type-add", "source:*.{c,h,cpp,java,kt,py,js,ts,rs,go}"])
        cmd.extend(["--type", "source", src_dir])

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            for line in proc.stdout.strip().split("\n")[:max_results]:
                if ":" in line:
                    file_path, line_no, content = line.split(":", 2)
                    results.append({
                        "file": file_path,
                        "line": int(line_no),
                        "content": content.strip()
                    })
        except subprocess.TimeoutExpired:
            results.append({"error": f"Search timeout in {src_dir}"})

    return {"results": results, "total": len(results)}


def execute_read_source_file(args: dict, config: dict) -> dict:
    """读取源码文件指定行范围"""
    file_path = args["file_path"]
    start_line = args.get("start_line", 1)
    end_line = args.get("end_line", start_line + 50)

    # 安全检查：文件路径必须在配置的源码目录内
    source_dirs = config.get("source_code_dirs", [])
    real_path = os.path.realpath(file_path)
    if not any(real_path.startswith(os.path.realpath(d)) for d in source_dirs):
        return {"error": "Access denied: file is outside configured source directories"}

    # 限制读取行数，避免 Token 爆炸
    max_lines = 100
    end_line = min(end_line, start_line + max_lines - 1)

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        selected = lines[start_line - 1:end_line]
        return {
            "file": file_path,
            "start_line": start_line,
            "end_line": start_line + len(selected) - 1,
            "total_lines": len(lines),
            "content": "".join(selected)
        }
    except Exception as e:
        return {"error": str(e)}


def execute_list_directory(args: dict, config: dict) -> dict:
    """列出目录结构"""
    dir_path = args.get("dir_path") or config.get("source_code_dirs", ["."])[0]
    max_depth = args.get("max_depth", 2)

    # 安全检查
    source_dirs = config.get("source_code_dirs", [])
    real_path = os.path.realpath(dir_path)
    if not any(real_path.startswith(os.path.realpath(d)) for d in source_dirs):
        return {"error": "Access denied: directory is outside configured source directories"}

    entries = []
    for root, dirs, files in os.walk(dir_path):
        depth = root.replace(dir_path, "").count(os.sep)
        if depth >= max_depth:
            dirs[:] = []  # 不再递归
            continue
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), dir_path)
            if any(f.endswith(ext) for ext in [".c",".h",".cpp",".java",".kt",".py",".js"]):
                entries.append(rel)
    return {"directory": dir_path, "entries": entries[:100]}


def execute_grep_source_code(args: dict, config: dict) -> dict:
    """正则搜索源码，返回上下文"""
    pattern = args["pattern"]
    context_lines = args.get("context_lines", 5)
    max_results = args.get("max_results", 10)
    source_dirs = config.get("source_code_dirs", [])

    results = []
    for src_dir in source_dirs:
        rg_cmd = _get_rg_command()
        if not rg_cmd:
            continue
        cmd = [
            rg_cmd, "--line-number", "-e", pattern,
            "-C", str(context_lines),
            "--max-count", str(max_results),
            "--type-add", "source:*.{c,h,cpp,java,kt,py,js,ts,rs,go}",
            "--type", "source", src_dir
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            results.append({"file": src_dir, "matches": proc.stdout[:5000]})
        except subprocess.TimeoutExpired:
            results.append({"error": "grep timeout"})

    return {"results": results}
```

#### 4.3 Agentic Loop 主循环

```python
from openai import OpenAI

def run_agentic_analysis(log_context: dict, config: dict, session_id: str) -> dict:
    """
    运行 Agentic Loop：LLM 自主调用工具分析日志

    Args:
        log_context: 从选中日志行提取的上下文（模块3产出）
        config: LLM 配置（api_base, api_key, model, source_code_dirs 等）
        session_id: 会话ID，用于任务状态追踪

    Returns:
        {
            "analysis": "最终分析文本（Markdown）",
            "tool_calls_log": [...],  # 工具调用记录
            "iterations": 5,
            "total_tokens": 12345,
            "duration_seconds": 12.5
        }
    """
    client = OpenAI(base_url=config["api_base"], api_key=config["api_key"])
    max_iterations = config.get("max_iterations", 10)

    # 构造初始消息
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_initial_user_message(log_context)}
    ]

    tool_calls_log = []
    total_tokens = 0
    start_time = time.time()

    for iteration in range(max_iterations):
        # 调用 LLM
        response = client.chat.completions.create(
            model=config["model"],
            messages=messages,
            tools=ANALYSIS_TOOLS,
            temperature=config.get("temperature", 0.2),
            max_tokens=config.get("max_tokens", 4096),
            stream=True  # 流式，前端可逐步展示
        )

        # 收集流式响应
        assistant_message, tool_calls = collect_streaming_response(response)
        total_tokens += response.usage.total_tokens if response.usage else 0

        # 追加 assistant 消息到历史
        messages.append(assistant_message)

        # 如果没有工具调用，循环结束
        if not tool_calls:
            break

        # 执行每个工具调用，追加结果到消息历史
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            tool_result = execute_tool_call(tool_name, tool_args, config)

            # 记录工具调用日志（用于前端展示）
            tool_calls_log.append({
                "iteration": iteration + 1,
                "tool": tool_name,
                "args": tool_args,
                "result_preview": str(tool_result)[:500]
            })

            # 更新任务进度（用于前端轮询）
            _update_analysis_task(session_id, phase="analyzing",
                                  iteration=iteration + 1,
                                  last_tool=f"{tool_name}({tool_args})")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result
            })

    # 提取最终分析文本
    final_content = messages[-1].get("content", "") if messages[-1]["role"] == "assistant" else ""
    duration = time.time() - start_time

    return {
        "analysis": final_content,
        "tool_calls_log": tool_calls_log,
        "iterations": iteration + 1,
        "total_tokens": total_tokens,
        "duration_seconds": round(duration, 1)
    }
```

#### 4.4 System Prompt 设计

参考 Cursor 的设计原则（XML 标签分区、明确工具使用指引、防止过早停止）：

```xml
<identity>
你是一位资深的嵌入式/Android 系统日志分析专家，擅长通过日志定位源码问题。
</identity>

<tools>
你可以使用以下工具来探索源码：
- search_source_code: 按关键字搜索源码，找到日志输出点
- read_source_file: 读取源码文件，查看上下文逻辑
- list_directory: 了解项目代码结构
- grep_source_code: 用正则精确搜索（如搜索 LOGE、ALOGE 等日志宏）
</tools>

<guidelines>
- 在给出最终分析前，务必先使用工具搜索和阅读相关源码，不要凭空猜测
- 如果首次搜索结果不够，尝试不同的搜索关键字（如函数名变体、Tag名、错误信息片段）
- 每次调用工具前，先简要说明你想要查找什么
- 如果对分析结果不完全确定，继续使用工具收集更多信息
- 源码路径必须在配置的源码目录范围内
</guidelines>

<output_format>
最终分析结果请使用以下 Markdown 格式：

### 源码定位
- 文件路径及行号，以及日志输出语句

### 代码逻辑分析
- 该段代码的执行流程和意图

### 可能的错误原因
1. 原因一（附依据）
2. 原因二（附依据）

### 建议排查方向
- 具体的排查步骤
</output_format>
```

#### 4.5 用户追问机制（多轮对话）

分析完成后，用户可以继续追问，LLM 可以继续使用工具深入分析：

```python
def continue_agentic_analysis(session_id: str, user_message: str, config: dict) -> dict:
    """
    在已有分析会话上追加用户追问，LLM 可继续调用工具

    实现方式：从 _analysis_tasks 中取出该 session 的 messages 历史，
    追加用户消息，继续运行 agentic loop
    """
    task = _get_analysis_task(session_id)
    if not task:
        return {"error": "Session not found"}

    # 追加用户追问到已有消息历史
    task["messages"].append({"role": "user", "content": user_message})

    # 继续运行 agentic loop（同 run_agentic_analysis 的循环逻辑）
    ...
```

**UI 交互**:

```
┌─ AI 分析结果 ──────────────────────────────────────┐
│                                                     │
│  [LLM 分析结果 Markdown 渲染...]                     │
│                                                     │
│  ┌─ 工具调用过程（可折叠）───────────────────────┐  │
│  │ 🔍 search_source_code("PlayerInterface")     │  │
│  │    → 找到 3 个文件                            │  │
│  │ 📄 read_source_file("player_interface.c")    │  │
│  │    → 读取 245-295 行                          │  │
│  │ 🔍 grep_source_code("LOGE.*player.stop")      │  │
│  │    → 找到 1 个匹配                            │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌─ 追问输入框 ─────────────────────────────────┐  │
│  │ [输入追问...]                    [发送]        │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  Token: 1,234 | 耗时: 8.5s | 迭代: 5轮 | 模型: gpt-4o│
└─────────────────────────────────────────────────────┘
```

#### 4.6 安全与成本控制

| 控制项 | 默认值 | 说明 |
|--------|--------|------|
| `max_iterations` | 10 | Agentic Loop 最大迭代次数 |
| `max_tokens_per_call` | 4096 | 单次 LLM 调用最大 Token |
| `max_total_tokens` | 32768 | 单次分析总 Token 上限（超出则强制停止） |
| `max_file_read_lines` | 100 | 单次 read_source_file 最大行数 |
| `max_search_results` | 20 | 单次搜索最大返回结果数 |
| `source_dir_whitelist` | 配置目录 | 工具只能访问配置的源码目录，防止路径遍历 |
| `tool_timeout` | 10s | 单个工具执行超时 |

**依赖**:

```
# requirements.txt 新增
openai>=1.0.0
```

---

### 6. 分析结果展示与交互

**目标**: 在 UI 中展示 LLM 分析结果、工具调用过程，支持用户追问。

**需要实现**:

- **新增 Tab**: 在显示模式 Tabs 中新增「AI 分析」Tab（与"过滤结果"/"源文件"/"高亮显示"并列）
- **结果展示区域**:
  - **Markdown 渲染区域**: LLM 最终分析结果（`dcc.Markdown` 或前端 marked.js 渲染）
  - **工具调用过程面板**（可折叠）:
    - 展示 LLM 每一轮调用了什么工具、参数是什么、结果摘要
    - 搜索结果可点击跳转（调用外部程序打开对应源码文件+行号）
  - **统计信息**: Token 用量、分析耗时、迭代轮数、模型名

- **交互功能**:
  - 「开始分析」按钮：触发选中行 → 提取上下文 → Agentic Loop 全流程
  - 「停止分析」按钮：强制中断 Agentic Loop
  - 「重新分析」按钮：清空历史，重新开始
  - 「复制分析结果」按钮
  - **追问输入框**: 用户可输入追问，LLM 在已有上下文上继续分析（可继续调用工具）

- **实时进度展示**:
  - 分析过程中显示当前状态：`正在搜索源码...` / `正在读取文件...` / `正在分析...`
  - 使用 `dcc.Interval` 轮询后端任务状态，逐步更新展示
  - 工具调用过程实时追加到面板中

- **分析历史**（可选，存入 `analysis_history.json`）

---

### 7. 后端异步任务管理

**目标**: LLM 调用为耗时操作，需要异步任务管理机制。

**需要实现**:

- 参考已有的过滤任务管理（`_filter_tasks` / `_filter_tasks_lock`），实现类似模式：
  - `_analysis_tasks` 字典 + 线程锁
  - 任务状态：`pending` → `extracting` → `analyzing` → `completed` / `failed` / `cancelled`
  - `analyzing` 阶段包含多轮迭代，每轮更新 `iteration` 和 `last_tool`
  - 进度轮询回调（复用 `dcc.Interval` 机制）
  - 支持强制取消（设置 `cancelled` 标志，agentic loop 中每轮检查）

```python
_analysis_tasks = {}
_analysis_tasks_lock = threading.Lock()

def _init_analysis_task(session_id, selected_lines, log_file):
    task = {
        "session_id": session_id,
        "phase": "pending",       # pending / extracting / analyzing / completed / failed / cancelled
        "iteration": 0,
        "last_tool": "",
        "messages": [],           # 完整对话历史（支持追问）
        "tool_calls_log": [],     # 工具调用记录
        "analysis_result": "",    # 最终分析文本
        "total_tokens": 0,
        "duration_seconds": 0,
        "error": ""
    }
    with _analysis_tasks_lock:
        _analysis_tasks[session_id] = task
    return task

def _run_analysis_task(session_id):
    """在后台线程中执行完整分析流程"""
    # 1. 提取日志关键信息 (phase: extracting)
    # 2. 运行 Agentic Loop (phase: analyzing)
    #    - 每轮迭代检查 cancelled 标志
    #    - 每轮更新 iteration, last_tool
    # 3. 更新任务状态和结果 (phase: completed / failed)
```

---

## UI 布局规划

### 过滤结果区域改造

在现有「显示模式 Tabs」中新增一个 Tab：

```
过滤结果 | 源文件 | 高亮显示 | 注释 | 流程视图 | AI 分析  ← 新增
```

### AI 分析 Tab 内容

```
┌──────────────────────────────────────────────────────────┐
│ [选中行数: 5] [自动提取错误] [开始分析] [停止] [重新分析] │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─ 分析进度 ─────────────────────────────────────────┐  │
│  │ ⏳ 第3轮迭代 | 正在读取文件: player_interface.c     │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─ 工具调用过程（可折叠）────────────────────────────┐  │
│  │ 🔄 第1轮: search_source_code("PlayerInterface")   │  │
│  │    → 找到 3 个文件, 8 处匹配                       │  │
│  │ 🔄 第2轮: read_source_file("player_interface.c")  │  │
│  │    → 读取 245-295 行                               │  │
│  │ 🔄 第3轮: grep_source_code("LOGE.*player.stop")   │  │
│  │    → 找到 1 个匹配 [打开文件]                      │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─ AI 分析结果 ──────────────────────────────────────┐  │
│  │                                                     │  │
│  │  ### 源码定位                                       │  │
│  │  - player_interface.c:245 — LOGE("PlayerInterface" │  │
│  │                                                     │  │
│  │  ### 代码逻辑分析                                   │  │
│  │  该日志位于 player_interface.c 的 stop 流程...      │  │
│  │                                                     │  │
│  │  ### 可能的错误原因                                 │  │
│  │  1. 解码器停止超时...                               │  │
│  │  2. 资源未正确释放...                               │  │
│  │                                                     │  │
│  │  ### 建议排查方向                                   │  │
│  │  - 检查 decoder 状态...                             │  │
│  │                                                     │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─ 追问 ─────────────────────────────────────────────┐  │
│  │ [输入追问，如"这个函数在哪些地方被调用？" ]  [发送] │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Token: 1,234 | 耗时: 8.5s | 迭代: 3轮 | 模型: gpt-4o    │
└──────────────────────────────────────────────────────────┘
```

### AI 设置区域（日志管理 Tab 中新增）

```
┌─ AI 分析设置 ────────────────────────────────────────┐
│                                                       │
│  API 地址: [https://api.openai.com/v1          ]     │
│  API Key:  [sk-****xxxx                         ]     │
│  模型名称: [gpt-4o                             ]     │
│                                                       │
│  源码搜索路径:                                        │
│  [/path/to/project/src                    ] [添加]    │
│  [/path/to/another/src                    ] [删除]    │
│                                                       │
│  [保存配置]  [测试连接]                               │
│                                                       │
└───────────────────────────────────────────────────────┘
```

---

## 新增文件清单

| 文件 | 用途 |
|------|------|
| `llm_config.json` | LLM API 配置（需 gitignore） |
| `error_patterns.json` | 自动错误提取规则 |
| `analysis_history.json` | 分析历史记录（可选） |

## 需修改的现有文件

| 文件 | 修改内容 |
|------|----------|
| `app.py` | 新增 AI 分析相关回调、UI 组件、LLM 调用逻辑 |
| `requirements.txt` | 新增 `openai>=1.0.0` |
| `.gitignore` | 新增 `llm_config.json` |
| `assets/rolling.js` | 支持行选择 checkbox 交互（可选） |

---

## 实现优先级

1. **P0 - LLM 配置管理**: 基础设施，后续所有功能依赖
2. **P0 - 日志行选择**: 手动选择模式，核心交互入口
3. **P0 - Agentic Loop 核心**: 工具定义 + 执行引擎 + 主循环 + System Prompt
4. **P0 - 分析结果展示**: Markdown 渲染 + 工具调用过程 + 进度展示
5. **P1 - 用户追问机制**: 多轮对话，在已有上下文上继续分析
6. **P1 - 自动错误提取**: 便捷功能，手动选择可替代
7. **P2 - 流式响应**: 体验优化，LLM 文本逐步展示
8. **P2 - 分析历史**: 可后续迭代

---

## 安全考虑

- API Key 存储在本地 `llm_config.json`，加入 `.gitignore`
- API Key 在 UI 中脱敏显示
- LLM 请求仅发送日志文本和源码片段，不发送完整源码文件
- 源码搜索路径需校验，防止路径遍历
- 限制单次发送给 LLM 的源码上下文大小（如最多 2000 行），控制 Token 消耗

---

## free-code 通信启动设置与接口

### 启动配置

#### 1. 全局配置常量 (`app.py`)

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| `FREE_CODE_DEFAULT_ROOT` | - | `PROJECT_DIR` | bridge 和 cli 所在目录 |
| `FREE_CODE_DEFAULT_CWD` | `LOG_FILTER_FREE_CODE_CWD` | 项目根目录 | CLI 工作目录 |
| `FREE_CODE_CHAT_TIMEOUT` | `LOG_FILTER_FREE_CODE_TIMEOUT` | 180秒 | 请求超时 |
| `FREE_CODE_CHAT_EXTRA_ARGS` | `LOG_FILTER_FREE_CODE_ARGS` | 空列表 | CLI 额外参数 |
| `FREE_CODE_CLI` | `LOG_FILTER_FREE_CODE_CLI` | - | CLI 可执行文件路径 |

#### 2. CLI 启动参数 (`free_code_cli_client.py`)

```
freecode-cli \
  --print \
  --verbose \
  --input-format stream-json \
  --output-format stream-json \
  --session-id <uuid> \
  [extra_args...]
```

#### 3. 前端本地存储键 (`chat_window.js`)

| Key | 用途 |
|-----|------|
| `log-filter-free-code-chat-session-id` | 会话 ID |
| `log-filter-free-code-chat-cwd` | 工作目录 |
| `log-filter-free-code-chat-size` | 窗口大小 |

---

### HTTP API 接口

前缀: `FREE_CODE_CHAT_API_PREFIX = '/api/free-code'`

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/free-code/health` | GET | 健康检查，返回 CLI 路径、CWD、extra_args |
| `/api/free-code/config` | GET/POST | 获取/设置运行时配置（cwd 等） |
| `/api/free-code/chat/<session_id>/stream` | POST | 流式聊天（SSE 响应） |
| `/api/free-code/sessions/<session_id>` | DELETE | 关闭指定会话 |

---

### Bridge 类接口

#### `FreeCodeWebBridge` (`freecode_bridge/web_bridge.py`)

| 方法 | 说明 |
|------|------|
| `create_session(session_id)` | 创建新会话，启动 CLI 子进程 |
| `get_session(session_id)` | 获取已存在会话 |
| `ensure_session(session_id)` | 获取或创建会话 |
| `ask(session_id, text, timeout, on_event)` | 发送消息并等待响应 |
| `send_text(session_id, text, priority)` | 发送文本消息 |
| `collect_until_result(session_id, timeout)` | 收集事件直到 result |
| `close_session(session_id)` | 关闭指定会话 |
| `close_all()` | 关闭所有会话 |

#### `FreeCodeCliClient` (`freecode_bridge/free_code_cli_client.py`)

| 方法 | 说明 |
|------|------|
| `send_text(text, priority)` | 发送用户文本 |
| `send_user_message(content, priority)` | 发送用户消息 |
| `send_control_request(subtype, **fields)` | 发送控制请求 |
| `send_control_response_success/error()` | 发送控制响应 |
| `allow_tool(request_id)` | 允许工具调用 |
| `read_event(timeout)` | 读取事件 |
| `ask(text, timeout, on_event)` | 发送并收集响应 |
| `close()` | 关闭 CLI 进程 |

---

### 前端 JavaScript API (`window.__chatWin`)

| 方法 | 说明 |
|------|------|
| `show()` / `hide()` | 显示/隐藏窗口 |
| `addMessage(text, role)` | 添加消息 |
| `addUserMessage(text)` / `addAIMessage(text)` | 添加用户/AI 消息 |
| `addAttachment(file)` / `removeAttachment(id)` | 附件管理 |
| `clearMessages()` | 清空消息 |
| `getSessionId()` | 获取会话 ID |
| `getWorkingDirectory()` / `applyWorkingDirectory()` | 工作目录管理 |

---

### 关键文件位置

- `app.py:562-572` — 全局配置常量
- `app.py:8365-8479` — HTTP 接口定义
- `freecode_bridge/web_bridge.py` — Web Bridge 封装
- `freecode_bridge/free_code_cli_client.py` — CLI 子进程通信
- `assets/chat_window.js` — 前端聊天窗口实现
