# -*- coding: utf-8 -*-
import dash
from dash import dcc, html, Input, Output, State, ALL, MATCH, callback_context
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import json
import os
import sys
import shutil
import subprocess
import re
import base64
import hashlib
import time
import threading
import io
import zipfile
import tarfile
import tempfile
import uuid
from bisect import bisect_left
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# 预编译正则模式，避免在循环中重复编译
LOG_PREFIX_PATTERNS = [
    re.compile(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+\d+\s+\d+\s+[A-Z]\s+\w+\s*:\s*'),
    re.compile(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+\d+\s+\d+\s+[A-Z]\s*:\s*'),
    re.compile(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+[A-Z]/\w+\s*:\s*'),
    re.compile(r'^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?\s+'),
    re.compile(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+'),
    re.compile(r'^\d{2}:\d{2}:\d{2}\s+'),
    re.compile(r'^\[\w+\]\s*\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]\s+'),
    re.compile(r'^\[\d{10,13}\]\s+'),
]

# 高亮缓存系统
class HighlightCache:
    def __init__(self, max_size=100):
        self.cache = {}
        self.max_size = max_size
        self.access_order = []
        # 缓存统计信息
        self.hits = 0
        self.misses = 0
        self.total_requests = 0
    
    def get_cache_key(self, text, selected_strings, data):
        """生成缓存键（稳定且高效：有限采样 + 结构化哈希）"""
        if not text:
            text_part = ""
        else:
            # 仅采样头尾有限长度，避免对超大文本全量哈希
            head = text[:200]
            tail = text[-200:] if len(text) > 200 else ""
            text_part = f"{len(text)}:{head}:{tail}"

        # 规范化选中字符串和数据结构，以内容为准生成稳定哈希
        try:
            # selected_strings 可能是 list/dict，统一转为 JSON 字符串（有序）
            strings_norm = json.dumps(selected_strings, sort_keys=True, ensure_ascii=False)
        except TypeError:
            # 遇到不可序列化对象时退化为 str 表示
            strings_norm = str(selected_strings)

        try:
            data_norm = json.dumps(data, sort_keys=True, ensure_ascii=False)
        except TypeError:
            data_norm = str(data)

        key_source = "|".join([text_part, strings_norm, data_norm])
        key_hash = hashlib.sha1(key_source.encode("utf-8")).hexdigest()
        return key_hash
    
    def _preprocess_text(self, text):
        """预处理文本，移除时间戳等变化内容"""
        if not text:
            return ""
        
        lines = text.split('\n')
        processed_lines = []
        
        for line in lines:
            # 使用预编译的正则进行匹配
            processed_line = self._remove_timestamps(line)
            processed_lines.append(processed_line)
        
        return '\n'.join(processed_lines)
    
    def _remove_timestamps(self, line):
        """使用预编译正则移除行中的时间戳和进程信息"""
        for pattern in LOG_PREFIX_PATTERNS:
            match = pattern.match(line)
            if match:
                return line[match.end():].strip()
        return line
    
    def get(self, key):
        """从缓存中获取结果"""
        self.total_requests += 1
        
        if key in self.cache:
            # 更新访问顺序
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
            self.hits += 1
            return self.cache[key]
        
        self.misses += 1
        return None
    
    def put(self, key, value):
        """将结果存入缓存"""
        # 如果缓存已满，移除最久未使用的项
        if len(self.cache) >= self.max_size:
            oldest_key = self.access_order.pop(0)
            del self.cache[oldest_key]
        
        self.cache[key] = value
        self.access_order.append(key)
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.access_order.clear()
        # 重置统计信息
        self.hits = 0
        self.misses = 0
        self.total_requests = 0
    
    def get_stats(self):
        """获取缓存统计信息"""
        hit_rate = (self.hits / self.total_requests * 100) if self.total_requests > 0 else 0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total_requests": self.total_requests,
            "hit_rate": round(hit_rate, 2),
            "cache_size": len(self.cache),
            "max_size": self.max_size
        }

# 全局高亮缓存实例
highlight_cache = HighlightCache(max_size=50)  # 最多缓存50个结果


class SearchMatchCache:
    def __init__(self, max_size=40):
        self.cache = {}
        self.access_order = []
        self.max_size = max_size
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            value = self.cache.get(key)
            if value is None:
                return None
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
            return value

    def put(self, key, value):
        with self.lock:
            if key in self.cache:
                self.cache[key] = value
                if key in self.access_order:
                    self.access_order.remove(key)
                self.access_order.append(key)
                return
            if len(self.cache) >= self.max_size and self.access_order:
                oldest_key = self.access_order.pop(0)
                self.cache.pop(oldest_key, None)
            self.cache[key] = value
            self.access_order.append(key)


search_match_cache = SearchMatchCache(max_size=40)

# 会话高亮信息（供滚动窗口分片高亮使用）
highlight_session_info = {}
_temp_keywords_cache = {"mtime": None, "data": None}
_data_cache = {"mtime": None, "data": None}
_config_groups_cache = {"mtime": None, "data": None}
_config_files_cache = {"mtime": None, "data": None}
_log_files_cache = {"mtime": None, "data": None}
_highlight_combo_cache = {"order": [], "map": {}, "max": 30}
_filter_tasks = {}
_filter_tasks_lock = threading.Lock()
_FILTER_CHUNK_LINES = 200  # 首片行数（更快首屏）
_FILTER_PROGRESS_INTERVAL_MS = 800  # 前端轮询间隔

_ai_flow_tasks = {}
_ai_flow_tasks_lock = threading.Lock()
_AI_FLOW_PROGRESS_INTERVAL_MS = 500
_SOURCE_PREVIEW_LINES = 2000  # 源文件tab预览行数上限
_UI_BUSY_STORE_ID = "ui-busy-store"
_windows_powershell_runtime_cache = None
AI_KEYWORD_MAX_CANDIDATES = 120
AI_KEYWORD_DEFAULT_PATH_DISCUSSION_PROMPT = """请分析当前源码工程中适合做日志关键字过滤的功能流程。

当前阶段请先和我讨论，不要直接输出配置文件或 JSON。

请重点扫描代码中的日志打印点，并围绕某个具体业务流程梳理：
1. 流程入口、核心模块、关键函数、状态流转和主要分支。
2. 正常流程中的关键步骤日志，例如开始、参数校验、状态切换、关键事件、成功完成等。
3. 异常流程中的关键日志，例如错误码、失败原因、重试、超时、资源不存在、状态不一致、权限/网络/IO 异常等。
4. 实际会出现在日志里的稳定关键字，例如 tag、模块名、函数名、事件名、状态名、错误码、协议名、业务对象名等。

后续会基于你的讨论生成 keep/filter 关键字：
- keep 关键字应该帮助保留目标流程相关日志，优先选择能稳定命中关键步骤、状态变化和异常路径的具体字符串。
- filter 关键字应该帮助排除无关噪声日志，尤其要识别循环、轮询、心跳、定时器、周期性状态上报、重复统计、频繁 debug 打印等会反复出现但不利于定位流程的内容。
- 如果某些日志虽然属于同一模块但属于后台循环、缓存刷新、状态轮询、重复探测或无关异步任务，也请明确指出它们更适合作为 filter 候选。
- 避免过泛关键字，例如 error、failed、start、stop、init，除非它们和具体 tag/模块/状态组合后足够特异。

请输出自然语言分析，建议按“流程概述 / keep 候选线索 / filter 噪声线索 / 需要用户确认的问题”组织。"""

AI_KEYWORD_DEFAULT_TARGET_ANALYSIS_PROMPT = """你是 log_filter 的代码流程日志关键字分析助手。

用户会提供一个需要重点分析的代码线索，可能是已有日志打印、tag、函数名、类名、状态名、事件名或错误码。

请围绕这个线索在源码中做针对性分析：
1. 搜索并定位该线索出现的位置，以及它所在的函数、类、模块和调用上下文。
2. 分析它前后的业务流程，包括进入该点之前的关键步骤、触发条件、状态变化，以及之后可能继续执行的分支。
3. 提取围绕该流程的 keep 关键字线索：能稳定命中目标流程前后关键步骤、状态流转、重要事件和异常路径的日志 tag、函数名、状态名、错误码、事件名、业务对象名等。
4. 提取围绕该流程的 filter 噪声线索：循环、轮询、心跳、定时器、周期性状态上报、重复统计、频繁 debug 打印、缓存刷新、后台异步任务、无关模块或无关分支等反复出现但不利于定位该流程的内容。
5. 如果某个关键字可能过泛，请说明风险，并给出更具体的组合线索。

请输出自然语言分析，不要生成配置文件 JSON。建议按“定位结果 / 前置流程 / 后续流程 / keep 关键字线索 / filter 噪声线索 / 需要确认的问题”组织。"""


def _parse_shell_version(version_text):
    if not version_text:
        return None
    match = re.search(r'(\d+)(?:\.(\d+))?', str(version_text).strip())
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2) or 0))


def _detect_windows_powershell_runtime():
    global _windows_powershell_runtime_cache
    if _windows_powershell_runtime_cache is not None:
        return _windows_powershell_runtime_cache

    runtime = {
        "cmd": None,
        "version": None,
        "version_text": "",
        "meets_minimum": False,
        "error": ""
    }

    if os.name != "nt":
        _windows_powershell_runtime_cache = runtime
        return runtime

    for shell_cmd in ("pwsh", "powershell"):
        if not shutil.which(shell_cmd):
            continue
        try:
            result = subprocess.run(
                [shell_cmd, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            version_text = (result.stdout or "").strip()
            version = _parse_shell_version(version_text)
            runtime = {
                "cmd": shell_cmd,
                "version": version,
                "version_text": version_text,
                "meets_minimum": bool(version and version >= (5, 1)),
                "error": "" if result.returncode == 0 else (result.stderr or "").strip()
            }
            break
        except Exception as exc:
            runtime = {
                "cmd": shell_cmd,
                "version": None,
                "version_text": "",
                "meets_minimum": False,
                "error": str(exc)
            }

    _windows_powershell_runtime_cache = runtime
    return runtime


def _can_use_windows_powershell(min_version=(5, 1)):
    runtime = _detect_windows_powershell_runtime()
    version = runtime.get("version")
    return bool(runtime.get("cmd") and version and version >= min_version)


def _powershell_fallback_reason(min_version=(5, 1)):
    runtime = _detect_windows_powershell_runtime()
    if runtime.get("cmd") and runtime.get("version_text"):
        return f"{runtime['cmd']} {runtime['version_text']} < {min_version[0]}.{min_version[1]}"
    if runtime.get("cmd"):
        return f"{runtime['cmd']} version unknown"
    if runtime.get("error"):
        return runtime["error"]
    return "powershell unavailable"


def _normalize_filter_backend_preference(value):
    normalized = str(value or "auto").strip().lower()
    if normalized in {"auto", "rg", "grep", "findstr", "powershell"}:
        return normalized
    return "auto"


def _can_use_windows_findstr():
    return os.name == "nt" and bool(shutil.which("findstr"))


def _get_bundled_rg_path():
    if os.name != "nt":
        return None
    candidates = []
    if RUNTIME_RESOURCES_DIR:
        candidates.append(os.path.join(RUNTIME_RESOURCES_DIR, "tools", "rg", "rg.exe"))
    executable_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidates.append(os.path.abspath(os.path.join(executable_dir, os.pardir, "tools", "rg", "rg.exe")))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "ripgrep", "windows-x64", "rg.exe"))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _get_rg_command():
    bundled_rg = _get_bundled_rg_path()
    if bundled_rg:
        return bundled_rg
    return shutil.which("rg")


def _get_rg_runtime_info():
    bundled_rg = _get_bundled_rg_path()
    if bundled_rg:
        return {"available": True, "source": "内置", "path": bundled_rg}
    path_rg = shutil.which("rg")
    if path_rg:
        return {"available": True, "source": "PATH", "path": path_rg}
    return {"available": False, "source": "未检测到", "path": ""}


def _get_filter_backend_runtime_info(preferred_backend="auto"):
    preferred_backend = _normalize_filter_backend_preference(preferred_backend)
    resolved_backend = None
    resolve_error = ""
    try:
        resolved_backend = _resolve_filter_backend(preferred_backend)
    except Exception as e:
        resolve_error = str(e)

    if os.name == "nt":
        runtime = _detect_windows_powershell_runtime()
        return {
            "preferred_backend": preferred_backend,
            "resolved_backend": resolved_backend,
            "resolve_error": resolve_error,
            "rg": _get_rg_runtime_info(),
            "findstr": _can_use_windows_findstr(),
            "powershell": bool(runtime.get("cmd") and runtime.get("meets_minimum"))
        }

    return {
        "preferred_backend": preferred_backend,
        "resolved_backend": resolved_backend,
        "resolve_error": resolve_error,
        "rg": _get_rg_runtime_info(),
        "grep": bool(shutil.which("grep"))
    }


def _get_filter_backend_selector_options():
    options = [{"label": "自动", "value": "auto"}]
    if os.name == "nt":
        options.extend([
            {"label": "rg", "value": "rg", "disabled": not bool(_get_rg_command())},
            {"label": "findstr", "value": "findstr", "disabled": not _can_use_windows_findstr()},
            {
                "label": "pwsh",
                "value": "powershell",
                "disabled": not bool(_detect_windows_powershell_runtime().get("cmd") and _detect_windows_powershell_runtime().get("meets_minimum"))
            }
        ])
    else:
        options.extend([
            {"label": "rg", "value": "rg", "disabled": not bool(_get_rg_command())},
            {"label": "grep", "value": "grep", "disabled": not bool(shutil.which("grep"))}
        ])
    return options


def _resolve_filter_backend(preferred_backend="auto"):
    preferred_backend = _normalize_filter_backend_preference(preferred_backend)
    if os.name == "nt":
        runtime = _detect_windows_powershell_runtime()
        availability = {
            "rg": bool(_get_rg_command()),
            "findstr": _can_use_windows_findstr(),
            "powershell": bool(runtime.get("cmd") and runtime.get("meets_minimum"))
        }
        if preferred_backend == "auto":
            for backend_name in ("rg", "findstr", "powershell"):
                if availability.get(backend_name):
                    return backend_name
            return "python"
        if preferred_backend == "powershell":
            if availability["powershell"]:
                return "powershell"
            raise RuntimeError(f"Windows PowerShell 不可用: {_powershell_fallback_reason()}")
        if preferred_backend in ("rg", "findstr"):
            if availability.get(preferred_backend):
                return preferred_backend
            raise RuntimeError(f"未找到可用的 {preferred_backend}")
        return "python"

    availability = {
        "rg": bool(_get_rg_command()),
        "grep": bool(shutil.which("grep"))
    }
    if preferred_backend == "auto":
        for backend_name in ("rg", "grep"):
            if availability.get(backend_name):
                return backend_name
        return "python"
    if preferred_backend in ("rg", "grep"):
        if availability.get(preferred_backend):
            return preferred_backend
        raise RuntimeError(f"未找到可用的 {preferred_backend}")
    return "python"


def _clear_filter_task(session_id, delete_files=False):
    """删除指定session的任务记录，可选删除临时文件"""
    with _filter_tasks_lock:
        task = _filter_tasks.pop(session_id, None)
    if delete_files and task:
        try:
            temp_file = task.get("temp_file")
            idx_file = task.get("idx_file")
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
            if idx_file and os.path.exists(idx_file):
                os.remove(idx_file)
        except Exception:
            pass


def _clear_all_filter_tasks(delete_files=False):
    """清空所有任务，避免状态残留"""
    with _filter_tasks_lock:
        sessions = list(_filter_tasks.keys())
    for sid in sessions:
        _clear_filter_task(sid, delete_files=delete_files)

# 初始化 Dash 应用，使用 Bootstrap 主题
base_path = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
RUNTIME_BASE_DIR = os.environ.get("LOG_FILTER_RUNTIME_DIR") or os.getcwd()
RUNTIME_RESOURCES_DIR = os.environ.get("LOG_FILTER_RESOURCES_DIR") or ""
RUNTIME_LOG_DIR = os.path.join(RUNTIME_BASE_DIR, "runtime_logs")
BACKEND_RUNTIME_LOG_FILE = os.path.join(RUNTIME_LOG_DIR, "backend.log")
DEFAULT_FILTER_BACKEND = "auto"


class _TeeStream:
    def __init__(self, *streams):
        self.streams = [stream for stream in streams if stream]
        self.encoding = getattr(self.streams[0], "encoding", "utf-8") if self.streams else "utf-8"
        self.errors = getattr(self.streams[0], "errors", "replace") if self.streams else "replace"
        self._log_filter_tee = True

    def write(self, data):
        for stream in self.streams:
            try:
                stream.write(data)
            except Exception:
                pass
        return len(data)

    def flush(self):
        for stream in self.streams:
            try:
                stream.flush()
            except Exception:
                pass

    def isatty(self):
        for stream in self.streams:
            try:
                if stream.isatty():
                    return True
            except Exception:
                continue
        return False


_runtime_log_stream = None


def _setup_runtime_logging():
    global _runtime_log_stream
    try:
        os.makedirs(RUNTIME_LOG_DIR, exist_ok=True)
        _runtime_log_stream = open(BACKEND_RUNTIME_LOG_FILE, "a", encoding="utf-8", buffering=1)
    except Exception:
        return

    if not getattr(sys.stdout, "_log_filter_tee", False):
        sys.stdout = _TeeStream(sys.stdout, _runtime_log_stream)
    if not getattr(sys.stderr, "_log_filter_tee", False):
        sys.stderr = _TeeStream(sys.stderr, _runtime_log_stream)


def _get_runtime_log_files():
    candidates = [
        ("backend.log", BACKEND_RUNTIME_LOG_FILE),
        ("electron-main.log", os.path.join(RUNTIME_LOG_DIR, "electron-main.log")),
        ("start_app.log", os.path.join(RUNTIME_BASE_DIR, "start_app.log"))
    ]
    seen = set()
    existing_files = []
    for arcname, file_path in candidates:
        if not file_path or file_path in seen:
            continue
        seen.add(file_path)
        if os.path.isfile(file_path):
            existing_files.append((arcname, file_path))
    return existing_files


def _build_runtime_logs_export():
    runtime_log_files = _get_runtime_log_files()
    if not runtime_log_files:
        raise FileNotFoundError("没有可导出的运行日志")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"logfilter_runtime_logs_{timestamp}.zip"
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for arcname, file_path in runtime_log_files:
            zip_file.write(file_path, arcname=arcname)
        zip_file.writestr(
            "runtime-info.txt",
            "\n".join([
                f"generated_at={datetime.now().isoformat()}",
                f"runtime_base_dir={RUNTIME_BASE_DIR}",
                f"runtime_log_dir={RUNTIME_LOG_DIR}",
                "files=" + ", ".join([arcname for arcname, _ in runtime_log_files])
            ])
        )
    return zip_buffer.getvalue(), archive_name, [arcname for arcname, _ in runtime_log_files]


_setup_runtime_logging()
app = dash.Dash(
    __name__, 
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    assets_folder=os.path.join(base_path, "assets")
)

# 配置Dash序列化性能
import os
try:
    import orjson
    # 如果安装了 orjson，强制 Dash 使用更快的序列化器
    os.environ['DASH_SERIALIZER'] = 'orjson'
    print("[性能] 已启用 orjson 序列化器")
except ImportError:
    # 回退到标准 json，但设置环境变量以统一行为
    os.environ['DASH_SERIALIZER'] = 'json'
    print("[性能] 未找到 orjson，使用标准 json 序列化")

# 数据存储文件路径
DATA_FILE = 'string_data.json'
ANNOTATIONS_FILE = 'keyword_annotations.json'
FLOWS_CONFIG_FILE = 'flows.json'
ALLOWED_LOG_EXTENSIONS = ('.txt', '.log', '.text')
ALLOWED_ARCHIVE_EXTENSIONS = ('.zip', '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz', '.7z')

# 获取所有配置文件
CONFIG_DIR = os.path.join(os.getcwd(), 'configs')
# 临时关键字配置放在项目根目录，便于随应用启动/刷新自动加载
TEMP_KEYWORDS_FILE = os.path.join(os.getcwd(), 'temp_keywords.json')
# 外部程序配置
EXTERNAL_PROGRAM_CONFIG_FILE = os.path.join(os.getcwd(), 'external_program_config.json')
# LLM 分析配置
LLM_CONFIG_FILE = os.path.join(os.getcwd(), 'llm_config.json')
FREE_CODE_DEFAULT_ROOT = PROJECT_DIR  # bridge 和 cli 现在都放在 log_filter 目录下
FREE_CODE_CHAT_API_PREFIX = '/api/free-code'
FREE_CODE_DEFAULT_CWD = os.path.abspath(
    os.environ.get('LOG_FILTER_FREE_CODE_CWD') or PROJECT_DIR
)
FREE_CODE_CHAT_TIMEOUT = float(os.environ.get('LOG_FILTER_FREE_CODE_TIMEOUT', '180'))
FREE_CODE_CHAT_EXTRA_ARGS = [
    arg.strip()
    for arg in os.environ.get('LOG_FILTER_FREE_CODE_ARGS', '').split()
    if arg.strip()
]

# 日志文件目录
LOG_DIR = 'logs'

# 临时文件目录（用于存储过滤结果）
TEMP_DIR = 'temp'

# ... (existing code)

# 通用 JSON 配置文件读写
def _load_json_config(file_path, default=None):
    """读取 JSON 配置文件，失败返回 default"""
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Loading config failed ({file_path}): {e}")
    return default if default is not None else {}

def _save_json_config(file_path, data):
    """保存 JSON 配置文件，返回是否成功"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Saving config failed ({file_path}): {e}")
        return False

# 外部程序配置管理
def load_external_program_config():
    return _load_json_config(EXTERNAL_PROGRAM_CONFIG_FILE, default={"path": ""})

def save_external_program_config(path):
    return _save_json_config(EXTERNAL_PROGRAM_CONFIG_FILE, {"path": str(path or "").strip()})

# LLM 分析配置管理
_LLM_CONFIG_DEFAULT = {
    "api_base": "",
    "api_key": "",
    "model": "",
    "max_tokens": 4096,
    "temperature": 0.2,
    "max_iterations": 10,
    "max_total_tokens": 32768,
    "source_code_dirs": []
}

def load_llm_config():
    """加载 LLM 配置，缺失字段用默认值填充"""
    saved = _load_json_config(LLM_CONFIG_FILE, default={})
    merged = dict(_LLM_CONFIG_DEFAULT)
    merged.update(saved)
    return merged

def save_llm_config(config):
    """保存 LLM 配置"""
    # 只保留已知字段，避免写入无关数据
    cleaned = {k: config.get(k, _LLM_CONFIG_DEFAULT.get(k)) for k in _LLM_CONFIG_DEFAULT}
    return _save_json_config(LLM_CONFIG_FILE, cleaned)

def mask_api_key(key):
    """API Key 脱敏：仅显示末4位"""
    if not key or len(key) <= 4:
        return "****" if key else ""
    return "*" * (len(key) - 4) + key[-4:]


def _normalize_free_code_extra_args(extra_args):
    """归一化 free-code CLI 额外参数配置"""
    if isinstance(extra_args, str):
        values = extra_args.split()
    elif isinstance(extra_args, (list, tuple)):
        values = extra_args
    else:
        values = []
    return [str(value).strip() for value in values if str(value).strip()]


def _allow_free_code_tools(event):
    """自动放行工具权限请求，便于本地日志分析使用"""
    request = event.get("request") or {}
    if request.get("subtype") != "can_use_tool":
        return None
    return {
        "behavior": "allow",
        "updatedInput": request.get("input", {}),
    }


_free_code_bridges = {}
_free_code_bridge_lock = threading.Lock()


def _normalize_free_code_cwd(cwd_value=None):
    """规范化 free-code 工作目录，允许前端动态传入。"""
    raw_cwd = cwd_value
    if raw_cwd is None or str(raw_cwd).strip() == "":
        raw_cwd = FREE_CODE_DEFAULT_CWD

    normalized = os.path.abspath(os.path.expanduser(str(raw_cwd).strip()))
    if not os.path.isdir(normalized):
        raise RuntimeError(f"free-code 工作目录不存在: {normalized}")
    return normalized


def _get_free_code_runtime_config(cwd_value=None):
    """解析 free-code 运行时配置，便于按不同 cwd 复用 bridge。"""
    free_code_root = os.path.abspath(
        os.environ.get('LOG_FILTER_FREE_CODE_ROOT') or FREE_CODE_DEFAULT_ROOT
    )
    # bridge 文件现在放在 freecode_bridge 子目录下
    python_bridge_dir = os.path.join(free_code_root, 'freecode_bridge')
    if not os.path.isdir(python_bridge_dir):
        raise RuntimeError(
            f"未找到 free-code Python bridge 目录: {python_bridge_dir}"
        )

    if python_bridge_dir not in sys.path:
        sys.path.insert(0, python_bridge_dir)

    try:
        from web_bridge import FreeCodeWebBridge
    except ImportError as exc:
        raise RuntimeError(
            f"导入 free-code bridge 失败，请确认目录有效: {python_bridge_dir}"
        ) from exc

    cli_path = os.environ.get('LOG_FILTER_FREE_CODE_CLI') or None
    # cli 现在放在 freecode-cli（或 free-code/cli）
    if not cli_path:
        for cli_name in ['freecode-cli', 'free-code/cli', 'cli']:
            candidate = os.path.join(free_code_root, cli_name)
            if os.path.isfile(candidate):
                cli_path = candidate
                break

    cli_cwd = _normalize_free_code_cwd(cwd_value)
    extra_args = _normalize_free_code_extra_args(FREE_CODE_CHAT_EXTRA_ARGS)

    return {
        "bridge_cls": FreeCodeWebBridge,
        "free_code_root": free_code_root,
        "python_bridge_dir": python_bridge_dir,
        "cli_path": cli_path,
        "cwd": cli_cwd,
        "extra_args": extra_args,
    }


def _resolve_free_code_bridge(cwd_value=None):
    """延迟加载 free-code bridge，并按工作目录缓存独立实例。"""
    runtime = _get_free_code_runtime_config(cwd_value)
    bridge_key = (
        runtime["cli_path"] or "",
        runtime["cwd"],
        tuple(runtime["extra_args"]),
    )

    with _free_code_bridge_lock:
        bridge = _free_code_bridges.get(bridge_key)
        if bridge is None:
            bridge = runtime["bridge_cls"](
                cli_path=runtime["cli_path"],
                cwd=runtime["cwd"],
                extra_args=runtime["extra_args"],
                auto_permission_handler=_allow_free_code_tools,
            )
            _free_code_bridges[bridge_key] = bridge
        return bridge


def _close_free_code_session_everywhere(session_id):
    """关闭指定 session，不要求调用方知道它最初绑定的 cwd。"""
    with _free_code_bridge_lock:
        bridges = list(_free_code_bridges.values())

    for bridge in bridges:
        try:
            bridge.get_session(session_id)
        except KeyError:
            continue
        bridge.close_session(session_id)
        return True
    return False


def _build_free_code_chat_message(message, attachments, analysis_context=None):
    """把日志附件拼入用户消息，交给 free-code 做统一分析"""
    user_message = str(message or "").strip()
    if not user_message:
        raise ValueError("message must be a non-empty string")

    normalized_attachments = []
    if isinstance(attachments, list):
        for index, item in enumerate(attachments, start=1):
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                label = str(item.get("label") or f"日志片段 {index}").strip()
            else:
                text = str(item or "").strip()
                label = f"日志片段 {index}"
            if text:
                normalized_attachments.append((label, text))

    sections = [user_message]
    if isinstance(analysis_context, dict) and analysis_context:
        config_group = str(analysis_context.get("config_group") or "").strip()
        display_mode = str(analysis_context.get("display_mode") or "filtered").strip() or "filtered"
        mode_label = "过滤结果" if display_mode == "filtered" else "源文件"
        skill_name = str(analysis_context.get("skill_name") or "").strip()
        config_files = analysis_context.get("config_files") or []
        if not isinstance(config_files, list):
            config_files = []
        sections.extend([
            "",
            "以下是来自 log_filter 的分析上下文：",
            "",
            f"- 当前视图: {mode_label}",
            f"- 配置文件组: {config_group or '未提供'}",
            f"- 对应 skill 名称: {skill_name or '未提供'}",
            f"- 日志文件: {str(analysis_context.get('selected_log_file') or '').strip() or '未提供'}",
            f"- 选中行数: {analysis_context.get('selected_line_count') or 0}",
        ])
        if config_files:
            sections.append(f"- 关联配置文件: {', '.join(str(item) for item in config_files)}")
        if display_mode == "filtered":
            sections.append("- 说明: 当前选中的日志来自过滤结果 tab，已经经过该配置组过滤。")
        if skill_name:
            sections.append(f"- 要求: 分析前优先调用名为 `{skill_name}` 的 skill。")

    if not normalized_attachments:
        return "\n".join(sections).strip()

    sections.extend(["", "以下是来自 log_filter 的附加日志片段，请结合上下文一起分析：", ""])
    for label, text in normalized_attachments:
        sections.append(f"## {label}")
        sections.append(text)
        sections.append("")
    return "\n".join(sections).strip()


def extract_text_from_chat_event(event):
    if not isinstance(event, dict):
        return ""
    if event.get("type") == "assistant_partial":
        return str(event.get("delta") or "")
    message = event.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = str(block.get("text") or "")
            if text:
                parts.append(text)
    return "".join(parts)

def ensure_temp_dir():
    """确保临时目录存在"""
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)

def ensure_config_dir():
    """确保配置目录存在；首次运行从随包默认配置拷贝到可写目录"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
        default_dir = os.path.join(base_path, 'configs')
        if os.path.exists(default_dir):
            for f in os.listdir(default_dir):
                src = os.path.join(default_dir, f)
                dst = os.path.join(CONFIG_DIR, f)
                if os.path.isfile(src) and not os.path.exists(dst):
                    shutil.copy(src, dst)

# 配置文件组目录
CONFIG_GROUPS_DIR = os.path.join(os.getcwd(), 'config_groups')

def ensure_config_groups_dir():
    """确保配置文件组目录存在；首次运行从随包默认配置拷贝到可写目录"""
    if not os.path.exists(CONFIG_GROUPS_DIR):
        os.makedirs(CONFIG_GROUPS_DIR)
        default_path = os.path.join(base_path, 'config_groups', 'config_groups.json')
        target_path = os.path.join(CONFIG_GROUPS_DIR, 'config_groups.json')
        if os.path.exists(default_path) and not os.path.exists(target_path):
            shutil.copy(default_path, target_path)

def get_config_groups_path():
    """获取配置文件组定义的路径"""
    ensure_config_groups_dir()
    return os.path.join(CONFIG_GROUPS_DIR, "config_groups.json")

def load_config_groups():
    """加载配置文件组定义（带mtime缓存）"""
    path = get_config_groups_path()
    if not os.path.exists(path):
        return {}
    try:
        mtime = os.path.getmtime(path)
        if _config_groups_cache["mtime"] == mtime and _config_groups_cache["data"] is not None:
            return _config_groups_cache["data"]
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            _config_groups_cache["mtime"] = mtime
            _config_groups_cache["data"] = data
            return data
    except Exception as e:
        print(f"加载配置文件组失败: {e}")
        return {}

def save_config_groups(groups):
    """保存配置文件组定义"""
    path = get_config_groups_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(groups, f, ensure_ascii=False, indent=2)
        _config_groups_cache["mtime"] = os.path.getmtime(path)
        _config_groups_cache["data"] = groups
        return True
    except Exception as e:
        print(f"保存配置文件组失败: {e}")
        return False


FREE_CODE_PROJECT_SKILLS_DIR = os.path.join(
    FREE_CODE_DEFAULT_ROOT,
    ".freecode",
    "skill",
)
LOG_FILTER_SKILL_PREFIX = "log-filter-group"
SKILL_DRAFT_FILENAME = "draft.md"
SKILL_METADATA_FILENAME = "metadata.json"
SKILL_CONFIG_START_MARKER = "<!-- LOG_FILTER_CONFIG_FILES_START -->"
SKILL_CONFIG_END_MARKER = "<!-- LOG_FILTER_CONFIG_FILES_END -->"
SKILL_OBSERVATION_START_MARKER = "<!-- LOG_FILTER_OBSERVATIONS_START -->"
SKILL_OBSERVATION_END_MARKER = "<!-- LOG_FILTER_OBSERVATIONS_END -->"
SKILL_MAX_AUTO_OBSERVATIONS = 8
SKILL_ANALYSIS_EXCERPT_LIMIT = 1800
LOG_SELECTION_MAX_LINES = 200


def ensure_free_code_project_skills_dir():
    os.makedirs(FREE_CODE_PROJECT_SKILLS_DIR, exist_ok=True)


def _slugify_ascii(text):
    normalized = str(text or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "group"


def get_config_group_skill_name(group_name):
    raw_name = str(group_name or "").strip()
    if not raw_name:
        raise ValueError("配置文件组名称不能为空")
    slug = _slugify_ascii(raw_name)
    digest = hashlib.sha1(raw_name.encode("utf-8")).hexdigest()[:8]
    return f"{LOG_FILTER_SKILL_PREFIX}-{slug}-{digest}"


def get_config_group_skill_dir(group_name):
    ensure_free_code_project_skills_dir()
    return os.path.join(FREE_CODE_PROJECT_SKILLS_DIR, get_config_group_skill_name(group_name))


def get_config_group_skill_paths(group_name):
    skill_dir = get_config_group_skill_dir(group_name)
    return {
        "skill_dir": skill_dir,
        "skill_md": os.path.join(skill_dir, "SKILL.md"),
        "draft_md": os.path.join(skill_dir, SKILL_DRAFT_FILENAME),
        "metadata_json": os.path.join(skill_dir, SKILL_METADATA_FILENAME),
    }


def _render_skill_config_files_markdown(config_files):
    values = [str(item).strip() for item in (config_files or []) if str(item).strip()]
    if not values:
        return "- 暂无关联配置文件"
    return "\n".join(f"- `{item}`" for item in values)


def _trim_analysis_excerpt(text, limit=SKILL_ANALYSIS_EXCERPT_LIMIT):
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n...[截断]"


def _normalize_observation_entry(item):
    if not isinstance(item, dict):
        return None
    updated_at = str(item.get("updated_at") or "").strip() or datetime.now().isoformat()
    display_mode = str(item.get("display_mode") or "").strip() or "filtered"
    line_count = item.get("selected_line_count")
    try:
        line_count = int(line_count or 0)
    except (TypeError, ValueError):
        line_count = 0
    line_numbers = item.get("selected_lines") or []
    if not isinstance(line_numbers, list):
        line_numbers = []
    normalized_lines = []
    for value in line_numbers[:30]:
        try:
            normalized_lines.append(int(value))
        except (TypeError, ValueError):
            continue
    return {
        "updated_at": updated_at,
        "display_mode": display_mode,
        "selected_log_file": str(item.get("selected_log_file") or "").strip(),
        "selected_line_count": line_count,
        "selected_lines": normalized_lines,
        "analysis_excerpt": _trim_analysis_excerpt(item.get("analysis_excerpt") or ""),
    }


def _render_skill_observations_markdown(observations):
    normalized = []
    for item in observations or []:
        entry = _normalize_observation_entry(item)
        if entry:
            normalized.append(entry)
    if not normalized:
        return "- 暂无自动沉淀观察"

    chunks = []
    for entry in normalized[:SKILL_MAX_AUTO_OBSERVATIONS]:
        display_mode = "过滤结果" if entry["display_mode"] == "filtered" else "源文件"
        line_numbers = ", ".join(str(v) for v in entry["selected_lines"][:12]) or "未记录"
        chunks.extend([
            f"### {entry['updated_at']}",
            f"- 视图来源: {display_mode}",
            f"- 日志文件: `{entry['selected_log_file'] or '未知日志'}`",
            f"- 选中行数: {entry['selected_line_count']}",
            f"- 行号: {line_numbers}",
            "- 分析摘要:",
            "",
            "```text",
            entry["analysis_excerpt"] or "无摘要",
            "```",
            "",
        ])
    return "\n".join(chunks).strip()


def _replace_marked_section(content, start_marker, end_marker, body, fallback_title):
    text = str(content or "").rstrip()
    body_text = str(body or "").strip()
    replacement = f"{start_marker}\n{body_text}\n{end_marker}"
    if start_marker in text and end_marker in text:
        pattern = re.compile(
            re.escape(start_marker) + r"[\s\S]*?" + re.escape(end_marker),
            re.MULTILINE,
        )
        return pattern.sub(replacement, text, count=1)

    appendix = f"\n\n## {fallback_title}\n{replacement}"
    return (text + appendix).strip()


def _build_default_skill_content(group_name, skill_name, config_files):
    config_block = _render_skill_config_files_markdown(config_files)
    observation_block = _render_skill_observations_markdown([])
    return (
        f"---\n"
        f"name: {skill_name}\n"
        f"description: 分析来自 log_filter 配置组“{group_name}”的日志，并持续沉淀复用经验。\n"
        f"---\n\n"
        f"# 配置组技能：{group_name}\n\n"
        f"这个 skill 服务于 log_filter 中的配置文件组 `{group_name}`，用于分析该组相关日志并沉淀稳定结论。\n\n"
        f"## 使用方式\n"
        f"- 当上下文表明日志来自配置组 `{group_name}` 时优先使用本 skill。\n"
        f"- 如果当前视图是“过滤结果”，表示日志已经过该配置组过滤，需要按过滤后的上下文理解问题。\n"
        f"- 输出时给出问题定位、证据链、风险判断和下一步建议。\n\n"
        f"## 关联配置文件\n"
        f"{SKILL_CONFIG_START_MARKER}\n"
        f"{config_block}\n"
        f"{SKILL_CONFIG_END_MARKER}\n\n"
        f"## 分析准则\n"
        f"1. 先识别当前日志是过滤结果还是源文件视图。\n"
        f"2. 结合配置组关联的配置文件理解过滤条件与关注点。\n"
        f"3. 提炼可复用的模式、误报特征和排查路径。\n"
        f"4. 把新增经验沉淀到“自动沉淀观察”或补充到上方规则中。\n\n"
        f"## 领域知识\n"
        f"- 在这里维护该配置组的稳定规则、常见模块关系和故障模式。\n\n"
        f"## 自动沉淀观察\n"
        f"{SKILL_OBSERVATION_START_MARKER}\n"
        f"{observation_block}\n"
        f"{SKILL_OBSERVATION_END_MARKER}\n"
    )


def _apply_managed_skill_sections(content, group_name, skill_name, config_files, observations):
    text = str(content or "").strip()
    if not text:
        text = _build_default_skill_content(group_name, skill_name, config_files)
    text = _replace_marked_section(
        text,
        SKILL_CONFIG_START_MARKER,
        SKILL_CONFIG_END_MARKER,
        _render_skill_config_files_markdown(config_files),
        "关联配置文件",
    )
    text = _replace_marked_section(
        text,
        SKILL_OBSERVATION_START_MARKER,
        SKILL_OBSERVATION_END_MARKER,
        _render_skill_observations_markdown(observations),
        "自动沉淀观察",
    )
    return text.rstrip() + "\n"


def _read_text_file_if_exists(file_path):
    if not os.path.exists(file_path):
        return ""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def _save_skill_metadata(file_path, metadata):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def load_config_group_skill_bundle(group_name):
    group_name = str(group_name or "").strip()
    if not group_name:
        raise ValueError("配置文件组名称不能为空")

    paths = get_config_group_skill_paths(group_name)
    config_groups = load_config_groups()
    config_files = config_groups.get(group_name, [])
    skill_name = get_config_group_skill_name(group_name)
    metadata = _load_json_config(paths["metadata_json"], default={}) or {}
    observations = metadata.get("observations") or []
    normalized_observations = []
    for item in observations:
        entry = _normalize_observation_entry(item)
        if entry:
            normalized_observations.append(entry)

    published_exists = os.path.exists(paths["skill_md"])
    draft_exists = os.path.exists(paths["draft_md"])
    published_content = _read_text_file_if_exists(paths["skill_md"])
    draft_content = _read_text_file_if_exists(paths["draft_md"]) or published_content

    published_content = _apply_managed_skill_sections(
        published_content,
        group_name,
        skill_name,
        config_files,
        normalized_observations,
    )
    draft_content = _apply_managed_skill_sections(
        draft_content,
        group_name,
        skill_name,
        config_files,
        normalized_observations,
    )

    now_iso = datetime.now().isoformat()
    metadata.setdefault("config_group", group_name)
    metadata.setdefault("skill_name", skill_name)
    metadata.setdefault("created_at", now_iso)
    metadata["config_files"] = config_files
    metadata["observations"] = normalized_observations[:SKILL_MAX_AUTO_OBSERVATIONS]
    metadata["observation_count"] = len(metadata["observations"])
    metadata.setdefault("updated_at", now_iso)
    metadata.setdefault("draft_updated_at", metadata["updated_at"])
    metadata.setdefault("published_at", metadata["updated_at"] if published_exists else "")
    metadata.setdefault("last_analysis_at", "")

    return {
        "group_name": group_name,
        "skill_name": skill_name,
        "paths": paths,
        "config_files": config_files,
        "metadata": metadata,
        "published_exists": published_exists,
        "draft_exists": draft_exists,
        "published_content": published_content,
        "draft_content": draft_content,
        "has_unpublished_changes": draft_content.strip() != published_content.strip(),
    }


def save_config_group_skill_content(group_name, content, publish=False):
    bundle = load_config_group_skill_bundle(group_name)
    paths = bundle["paths"]
    os.makedirs(paths["skill_dir"], exist_ok=True)

    now_iso = datetime.now().isoformat()
    normalized_content = _apply_managed_skill_sections(
        content,
        bundle["group_name"],
        bundle["skill_name"],
        bundle["config_files"],
        bundle["metadata"].get("observations") or [],
    )
    with open(paths["draft_md"], "w", encoding="utf-8") as f:
        f.write(normalized_content)

    metadata = dict(bundle["metadata"])
    metadata["updated_at"] = now_iso
    metadata["draft_updated_at"] = now_iso
    if publish:
        with open(paths["skill_md"], "w", encoding="utf-8") as f:
            f.write(normalized_content)
        metadata["published_at"] = now_iso

    _save_skill_metadata(paths["metadata_json"], metadata)
    return load_config_group_skill_bundle(group_name)


def auto_update_config_group_skill(group_name, analysis_context, analysis_text):
    group_name = str(group_name or "").strip()
    analysis_excerpt = _trim_analysis_excerpt(analysis_text)
    if not group_name or not analysis_excerpt:
        return None

    bundle = load_config_group_skill_bundle(group_name)
    metadata = dict(bundle["metadata"])
    observations = list(metadata.get("observations") or [])
    now_iso = datetime.now().isoformat()
    selected_lines = analysis_context.get("selected_lines") if isinstance(analysis_context, dict) else []
    if not isinstance(selected_lines, list):
        selected_lines = []
    normalized_lines = []
    for value in selected_lines[:30]:
        try:
            normalized_lines.append(int(value))
        except (TypeError, ValueError):
            continue

    observations.insert(0, {
        "updated_at": now_iso,
        "display_mode": str((analysis_context or {}).get("display_mode") or "filtered"),
        "selected_log_file": str((analysis_context or {}).get("selected_log_file") or "").strip(),
        "selected_line_count": len(normalized_lines),
        "selected_lines": normalized_lines,
        "analysis_excerpt": analysis_excerpt,
    })
    metadata["observations"] = observations[:SKILL_MAX_AUTO_OBSERVATIONS]
    metadata["observation_count"] = len(metadata["observations"])
    metadata["updated_at"] = now_iso
    metadata["draft_updated_at"] = now_iso
    metadata["published_at"] = now_iso
    metadata["last_analysis_at"] = now_iso

    paths = bundle["paths"]
    os.makedirs(paths["skill_dir"], exist_ok=True)
    base_content = bundle["draft_content"] or bundle["published_content"]
    updated_content = _apply_managed_skill_sections(
        base_content,
        bundle["group_name"],
        bundle["skill_name"],
        bundle["config_files"],
        metadata["observations"],
    )
    with open(paths["draft_md"], "w", encoding="utf-8") as f:
        f.write(updated_content)
    with open(paths["skill_md"], "w", encoding="utf-8") as f:
        f.write(updated_content)
    _save_skill_metadata(paths["metadata_json"], metadata)
    return load_config_group_skill_bundle(group_name)


def _normalize_selected_line_numbers(line_numbers, *, max_count=LOG_SELECTION_MAX_LINES):
    if not isinstance(line_numbers, list):
        return []
    normalized = []
    seen = set()
    for value in line_numbers:
        try:
            line_no = int(value)
        except (TypeError, ValueError):
            continue
        if line_no <= 0 or line_no in seen:
            continue
        seen.add(line_no)
        normalized.append(line_no)
        if len(normalized) >= max_count:
            break
    normalized.sort()
    return normalized


def read_selected_lines_from_source_log(selected_log_file, line_numbers):
    if not selected_log_file or not line_numbers:
        return []

    log_path = get_log_path(selected_log_file)
    if not os.path.exists(log_path):
        return []

    target_lines = set(line_numbers)
    max_line = max(target_lines)
    encoding = detect_file_encoding(log_path)
    result = []
    try:
        with open(log_path, "r", encoding=encoding, errors="replace") as f:
            for current_line, raw_line in enumerate(f, start=1):
                if current_line > max_line:
                    break
                if current_line not in target_lines:
                    continue
                content = raw_line.rstrip("\n")
                parsed = _parse_log_line(content)
                result.append({
                    "line_number": current_line,
                    "content": content,
                    "timestamp": parsed.get("timestamp", ""),
                    "tag": parsed.get("tag", ""),
                    "level": parsed.get("level", ""),
                    "message": parsed.get("message", ""),
                })
    except Exception as e:
        print(f"读取源文件选中日志失败: {e}")
        return []
    return result


def _format_line_entries_as_attachment(display_mode, line_entries):
    mode_label = "过滤结果" if display_mode == "filtered" else "源文件"
    lines = [f"[{entry.get('line_number')}] {entry.get('content', '')}" for entry in line_entries]
    return {
        "label": f"{mode_label}选中日志 ({len(line_entries)}行)",
        "text": "\n".join(lines).strip(),
    }


def build_log_analysis_request_payload(group_name, display_mode, selected_log_file, session_id, selected_lines):
    group_name = str(group_name or "").strip()
    display_mode = str(display_mode or "filtered").strip() or "filtered"
    selected_log_file = str(selected_log_file or "").strip()
    session_id = str(session_id or "").strip()
    normalized_lines = _normalize_selected_line_numbers(selected_lines)
    if not normalized_lines:
        raise ValueError("请先选择日志行")
    if not selected_log_file:
        raise ValueError("请先选择日志文件")

    if display_mode == "filtered":
        if not session_id:
            raise ValueError("过滤结果尚未准备好，请先执行过滤")
        line_entries = read_selected_lines_from_temp(session_id, normalized_lines)
    else:
        line_entries = read_selected_lines_from_source_log(selected_log_file, normalized_lines)

    if not line_entries:
        raise ValueError("未读取到选中的日志内容")

    config_groups = load_config_groups()
    config_files = config_groups.get(group_name, []) if group_name else []
    skill_name = get_config_group_skill_name(group_name) if group_name else ""
    mode_label = "过滤结果" if display_mode == "filtered" else "源文件"

    message = (
        "请分析我在 log_filter 网页中选中的日志，并给出结论、证据链、风险判断和下一步建议。\n"
        f"- 当前视图: {mode_label}\n"
        f"- 日志文件: {selected_log_file}\n"
        f"- 配置文件组: {group_name or '未选择'}\n"
        f"- 对应 skill 名称: {skill_name or '无'}\n"
        f"- 选中行数: {len(line_entries)}\n"
        "要求:\n"
        "1. 如果提供了对应 skill，请优先调用该 skill 再分析。\n"
        "2. 如果当前视图是过滤结果，明确说明这些日志已经经过配置组过滤。\n"
        "3. 输出可复用的新经验点，便于分析结束后回写 skill。\n"
        "4. 回答中保留配置文件组名与视图来源。"
    )

    analysis_context = {
        "config_group": group_name,
        "config_files": config_files,
        "skill_name": skill_name,
        "display_mode": display_mode,
        "selected_log_file": selected_log_file,
        "selected_lines": [entry["line_number"] for entry in line_entries],
        "selected_line_count": len(line_entries),
        "filtered_result": display_mode == "filtered",
        "auto_update_skill": bool(group_name),
    }
    return {
        "message": message,
        "attachments": [_format_line_entries_as_attachment(display_mode, line_entries)],
        "analysis_context": analysis_context,
    }


def serialize_config_group_skill_bundle(bundle):
    metadata = dict(bundle.get("metadata") or {})
    paths = dict(bundle.get("paths") or {})
    return {
        "group_name": bundle.get("group_name"),
        "skill_name": bundle.get("skill_name"),
        "config_files": list(bundle.get("config_files") or []),
        "published_exists": bool(bundle.get("published_exists")),
        "draft_exists": bool(bundle.get("draft_exists")),
        "has_unpublished_changes": bool(bundle.get("has_unpublished_changes")),
        "draft_content": bundle.get("draft_content", ""),
        "published_content": bundle.get("published_content", ""),
        "metadata": metadata,
        "paths": {
            "skill_dir": paths.get("skill_dir", ""),
            "skill_md": paths.get("skill_md", ""),
            "draft_md": paths.get("draft_md", ""),
        },
    }

def ensure_log_dir():
    """确保日志目录存在"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

def get_log_dir_path():
    ensure_log_dir()
    return os.path.abspath(LOG_DIR)

def _normalize_log_relative_path(filename, require_file=False):
    value = str(filename or "").strip()
    if not value:
        raise ValueError("路径不能为空")
    if "\x00" in value:
        raise ValueError("路径包含非法字符")
    if os.path.isabs(value):
        raise ValueError("路径不能是绝对路径")

    parts = []
    for part in value.replace("\\", "/").split("/"):
        part = part.strip()
        if not part:
            continue
        if part in {".", ".."}:
            raise ValueError("路径不能包含 . 或 ..")
        cleaned = re.sub(r'[\x00-\x1f<>:"|?*]+', "_", part).strip(" .")
        if not cleaned:
            raise ValueError("路径包含无效名称")
        parts.append(cleaned)

    if not parts:
        raise ValueError("路径无效")
    if require_file and len(parts[-1]) == 0:
        raise ValueError("文件名无效")
    return "/".join(parts)

def _normalize_log_filename(filename):
    return _normalize_log_relative_path(filename, require_file=True)

def _normalize_log_dirname(dirname):
    normalized = _normalize_log_relative_path(dirname)
    if normalized.lower().endswith(ALLOWED_LOG_EXTENSIONS):
        raise ValueError("目录名不能使用日志文件扩展名")
    return normalized

def _ensure_allowed_log_extension(filename):
    normalized = _normalize_log_filename(filename)
    if not normalized.lower().endswith(ALLOWED_LOG_EXTENSIONS):
        allowed_text = "、".join(ALLOWED_LOG_EXTENSIONS)
        raise ValueError(f"仅支持 {allowed_text} 文件")
    return normalized

def _resolve_log_file_path(filename, must_exist=False, allowed_extensions=None):
    normalized = _normalize_log_filename(filename)
    if allowed_extensions and not normalized.lower().endswith(tuple(ext.lower() for ext in allowed_extensions)):
        allowed_text = "、".join(allowed_extensions)
        raise ValueError(f"仅支持 {allowed_text} 文件")
    log_dir = get_log_dir_path()
    file_path = os.path.abspath(os.path.join(log_dir, normalized))
    if os.path.commonpath([log_dir, file_path]) != log_dir:
        raise ValueError("日志路径无效")
    if must_exist and not os.path.exists(file_path):
        raise FileNotFoundError(f"日志文件不存在: {normalized}")
    return normalized, file_path

def _resolve_log_dir_path(dirname, must_exist=False):
    normalized = _normalize_log_dirname(dirname)
    log_dir = get_log_dir_path()
    dir_path = os.path.abspath(os.path.join(log_dir, normalized))
    if os.path.commonpath([log_dir, dir_path]) != log_dir:
        raise ValueError("日志目录路径无效")
    if must_exist and not os.path.isdir(dir_path):
        raise FileNotFoundError(f"日志目录不存在: {normalized}")
    return normalized, dir_path

def _build_available_log_filename(filename):
    normalized = _ensure_allowed_log_extension(filename)
    parent = os.path.dirname(normalized)
    stem, ext = os.path.splitext(os.path.basename(normalized))
    candidate = normalized
    counter = 1
    while True:
        _, candidate_path = _resolve_log_file_path(candidate, allowed_extensions=ALLOWED_LOG_EXTENSIONS)
        if not os.path.exists(candidate_path):
            return candidate, candidate_path
        candidate_name = f"{stem}_{counter}{ext}"
        candidate = os.path.join(parent, candidate_name) if parent else candidate_name
        counter += 1

def _has_allowed_archive_extension(filename):
    value = str(filename or "").lower()
    return value.endswith(ALLOWED_ARCHIVE_EXTENSIONS)

def _sanitize_import_filename(filename):
    value = re.sub(r'[\x00-\x1f<>:"|?*\\/]+', "_", str(filename or "").strip())
    value = value.strip(" .")
    return value or "log.log"

def _sanitize_import_relative_path(path_value):
    try:
        return _normalize_log_relative_path(path_value, require_file=True)
    except Exception:
        return _sanitize_import_filename(os.path.basename(str(path_value or "")))

def _copy_log_file_to_logs(src_path, display_name=None):
    if not os.path.isfile(src_path):
        return None
    name = _sanitize_import_relative_path(display_name) if display_name else _sanitize_import_filename(os.path.basename(src_path))
    if not name.lower().endswith(ALLOWED_LOG_EXTENSIONS):
        return None
    filename, dest_path = _build_available_log_filename(name)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    shutil.copy2(src_path, dest_path)
    return filename.replace(os.sep, "/")

def _iter_log_files_in_dir(dir_path):
    for root, dirs, files in os.walk(dir_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in files:
            if filename.startswith(".") or not filename.lower().endswith(ALLOWED_LOG_EXTENSIONS):
                continue
            file_path = os.path.join(root, filename)
            if os.path.isfile(file_path):
                rel_path = os.path.relpath(file_path, dir_path)
                yield file_path, rel_path

def _import_log_dir(dir_path, prefix=""):
    imported = []
    for file_path, rel_path in _iter_log_files_in_dir(dir_path):
        display_name = _sanitize_import_relative_path(os.path.join(prefix, rel_path) if prefix else rel_path)
        copied = _copy_log_file_to_logs(file_path, display_name)
        if copied:
            imported.append(copied)
    return imported

def _safe_zip_members(zip_file):
    for info in zip_file.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/")
        parts = [part for part in name.split("/") if part]
        if not parts or any(part == ".." for part in parts):
            continue
        if parts[-1].startswith(".") or not parts[-1].lower().endswith(ALLOWED_LOG_EXTENSIONS):
            continue
        yield info, os.path.join(*parts)

def _safe_tar_members(tar_file):
    for member in tar_file.getmembers():
        if not member.isfile():
            continue
        name = member.name.replace("\\", "/")
        parts = [part for part in name.split("/") if part]
        if not parts or any(part == ".." for part in parts):
            continue
        if parts[-1].startswith(".") or not parts[-1].lower().endswith(ALLOWED_LOG_EXTENSIONS):
            continue
        yield member, os.path.join(*parts)

def _find_7z_command():
    for candidate in ("7z", "7za", "7zr"):
        tool = shutil.which(candidate)
        if tool:
            return tool
    return None

def _import_archive_file(archive_path):
    archive_name = _sanitize_import_filename(os.path.basename(archive_path))
    imported = []
    with tempfile.TemporaryDirectory(prefix="log_filter_archive_") as temp_dir:
        lower_name = archive_name.lower()
        if lower_name.endswith(".zip"):
            with zipfile.ZipFile(archive_path) as zip_file:
                for info, rel_path in _safe_zip_members(zip_file):
                    target_path = os.path.join(temp_dir, rel_path)
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with zip_file.open(info) as src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        elif lower_name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
            with tarfile.open(archive_path, "r:*") as tar_file:
                for member, rel_path in _safe_tar_members(tar_file):
                    target_path = os.path.join(temp_dir, rel_path)
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    src = tar_file.extractfile(member)
                    if src is None:
                        continue
                    with src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        elif lower_name.endswith(".7z"):
            tool = _find_7z_command()
            if not tool:
                raise ValueError("未找到 7z/7za/7zr，无法解压 7z 文件")
            result = subprocess.run(
                [tool, "x", "-y", f"-o{temp_dir}", archive_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "").strip()
                raise ValueError(f"7z 解压失败: {detail[:300]}")
        else:
            raise ValueError(f"不支持的压缩包类型: {archive_name}")
        imported = _import_log_dir(temp_dir, prefix=os.path.splitext(archive_name)[0])
    return imported

def import_log_source_path(source_path):
    if not source_path:
        return []
    source_path = os.path.abspath(str(source_path))
    if os.path.isdir(source_path):
        return _import_log_dir(source_path, prefix=os.path.basename(source_path))
    if os.path.isfile(source_path):
        if str(source_path).lower().endswith(ALLOWED_LOG_EXTENSIONS):
            copied = _copy_log_file_to_logs(source_path)
            return [copied] if copied else []
        if _has_allowed_archive_extension(source_path):
            return _import_archive_file(source_path)
    return []

def _parse_external_program_command(value):
    import shlex
    raw_value = str(value or "").strip()
    if not raw_value:
        raise ValueError("请输入有效的程序路径")
    try:
        args = shlex.split(raw_value)
    except ValueError:
        raise ValueError("外部程序路径格式无效")
    if not args:
        raise ValueError("请输入有效的程序路径")
    program = args[0]
    resolved_program = program if os.path.isabs(program) else shutil.which(program)
    if not resolved_program or not os.path.exists(resolved_program):
        raise ValueError(f"找不到外部程序: {program}")
    args[0] = resolved_program
    return raw_value, args

def _toast_script(message, level):
    return html.Script(
        f"if(window.showToast) window.showToast({json.dumps(str(message), ensure_ascii=False)}, {json.dumps(level)});"
    )


def _make_log_view_ui_state(phase="idle"):
    normalized_phase = str(phase or "idle")
    state = {
        "phase": normalized_phase,
        "button_disabled": False,
        "button_color": "success",
        "button_text": "过滤",
        "status_text": "Ready",
        "status_class": "badge bg-secondary ms-3",
        "spinner_style": {"display": "none", "marginLeft": "5px"}
    }
    if normalized_phase == "loading_file":
        state.update({
            "button_disabled": True,
            "button_color": "secondary",
            "status_text": "加载中...",
            "status_class": "badge bg-warning text-dark ms-3"
        })
    elif normalized_phase in {"source_ready", "filter_done"}:
        state.update({
            "button_disabled": False,
            "button_color": "success",
            "status_text": "Ready",
            "status_class": "badge bg-success ms-3"
        })
    elif normalized_phase in {"filter_running", "filter_partial_ready"}:
        state.update({
            "button_disabled": True,
            "button_color": "success",
            "button_text": "处理中...",
            "status_text": "处理中...",
            "status_class": "badge bg-info text-dark ms-3",
            "spinner_style": {"display": "inline-block", "marginLeft": "5px"}
        })
    elif normalized_phase == "error":
        state.update({
            "button_disabled": False,
            "button_color": "danger",
            "status_text": "错误",
            "status_class": "badge bg-danger ms-3"
        })
    return state

def get_annotations_path():
    """获取关键字注释文件的完整路径（优先可写目录，回退到随包默认）"""
    writable_path = os.path.join(os.path.dirname(DATA_FILE) or os.getcwd(), ANNOTATIONS_FILE)
    if os.path.exists(writable_path):
        return writable_path
    return os.path.join(base_path, ANNOTATIONS_FILE)

def load_annotations():
    """加载关键字注释映射 {keyword: note}"""
    try:
        annotations_path = get_annotations_path()
        if os.path.exists(annotations_path):
            with open(annotations_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        return {}
    except Exception as e:
        print(f"加载关键字注释失败: {e}")
        return {}

def save_annotations(annotations_map):
    """保存关键字注释映射到文件"""
    try:
        annotations_path = get_annotations_path()
        with open(annotations_path, 'w', encoding='utf-8') as f:
            json.dump(annotations_map or {}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存关键字注释失败: {e}")

def get_config_files():
    """获取configs目录下的所有配置文件（不包含.json后缀，带mtime缓存）"""
    ensure_config_dir()
    try:
        if os.path.exists(CONFIG_DIR):
            mtime = os.path.getmtime(CONFIG_DIR)
            if _config_files_cache["mtime"] == mtime and _config_files_cache["data"] is not None:
                return _config_files_cache["data"]
            config_files = []
            for file in os.listdir(CONFIG_DIR):
                if file.endswith('.json') and not file.startswith('.'):
                    config_files.append(file[:-5])  # 去掉.json后缀
            config_files = sorted(config_files)
            _config_files_cache["mtime"] = mtime
            _config_files_cache["data"] = config_files
            return config_files
    except Exception as e:
        print(f"获取配置文件列表失败: {e}")
    return []
# 从环境变量获取 URL 前缀
url_base = os.environ.get('DASH_URL_BASE_PATHNAME', '/')


def get_log_files():
    url_base_pathname=url_base,
    """获取logs目录中的所有文本文件列表（带mtime缓存）"""
    ensure_log_dir()
    try:
        if os.path.exists(LOG_DIR):
            signature = []
            for root, dirs, files in os.walk(LOG_DIR):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                try:
                    signature.append((os.path.relpath(root, LOG_DIR), os.path.getmtime(root)))
                except OSError:
                    pass
                for file in files:
                    if file.lower().endswith(ALLOWED_LOG_EXTENSIONS):
                        file_path = os.path.join(root, file)
                        try:
                            signature.append((os.path.relpath(file_path, LOG_DIR), os.path.getmtime(file_path)))
                        except OSError:
                            pass
            signature = tuple(sorted(signature))
            if _log_files_cache["mtime"] == signature and _log_files_cache["data"] is not None:
                return _log_files_cache["data"]
            log_files = []
            for root, dirs, files in os.walk(LOG_DIR):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for file in files:
                    if file.lower().endswith(ALLOWED_LOG_EXTENSIONS):
                        rel_path = os.path.relpath(os.path.join(root, file), LOG_DIR)
                        log_files.append(rel_path.replace(os.sep, "/"))
            log_files = sorted(log_files, key=lambda item: item.lower())
            _log_files_cache["mtime"] = signature
            _log_files_cache["data"] = log_files
            return log_files
    except Exception as e:
        print(f"获取日志列表失败: {e}")
    return []

def get_config_path(config_name):
    """获取配置文件的完整路径"""
    ensure_config_dir()
    return os.path.join(CONFIG_DIR, f"{config_name}.json")

def get_flows_config_path():
    """获取流程配置文件的完整路径（优先可写目录，回退到随包默认）"""
    writable_path = os.path.join(os.getcwd(), FLOWS_CONFIG_FILE)
    if os.path.exists(writable_path):
        return writable_path
    return os.path.join(base_path, FLOWS_CONFIG_FILE)

def load_flows_config():
    """加载流程配置，支持两种类型：
    - paired: [{"name": str, "start": str, "end": str}]
    - sequences: [{"name": str, "steps": [str, ...]}]
    若文件不存在或格式错误，返回空配置。
    """
    try:
        path = get_flows_config_path()
        if not os.path.exists(path):
            return {"paired": [], "sequences": []}
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            paired = data.get('paired') if isinstance(data, dict) else []
            sequences = data.get('sequences') if isinstance(data, dict) else []
            if not isinstance(paired, list):
                paired = []
            if not isinstance(sequences, list):
                sequences = []
            return {"paired": paired, "sequences": sequences}
    except Exception as e:
        print(f"加载流程配置失败: {e}")
        return {"paired": [], "sequences": []}

def save_flows_config(flows):
    """保存流程配置到文件"""
    try:
        ensure_config_dir()
        path = get_flows_config_path()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(flows or {"paired": [], "sequences": []}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存流程配置失败: {e}")

def get_default_config_path():
    """获取默认配置文件的完整路径"""
    ensure_config_dir()
    return os.path.join(CONFIG_DIR, "default.json")

def save_default_config(selected_strings):
    """保存选中的字符串到默认配置文件"""
    default_config_path = get_default_config_path()
    
    # 按分类和类型组织选中的字符串
    categorized_strings = {}
    
    # 加载当前数据以获取分类信息
    current_data = load_data()
    
    for item in selected_strings:
        if isinstance(item, dict):
            string_text = item["text"]
            string_type = item["type"]
            
            # 查找字符串所属的分类
            for category, strings in current_data["categories"].items():
                if string_text in strings:
                    # 创建分类（如果不存在）
                    if category not in categorized_strings:
                        categorized_strings[category] = {"keep": [], "filter": []}
                    
                    # 添加字符串到相应类型
                    categorized_strings[category][string_type].append(string_text)
                    break
        else:
            # 处理旧格式的字符串（不带类型信息）
            string_text = item
            
            # 查找字符串所属的分类
            for category, strings in current_data["categories"].items():
                if string_text in strings:
                    # 创建分类（如果不存在）
                    if category not in categorized_strings:
                        categorized_strings[category] = {"keep": [], "filter": []}
                    
                    # 默认为保留字符串
                    categorized_strings[category]["keep"].append(string_text)
                    break
    
    # 保存到默认配置文件
    with open(default_config_path, 'w', encoding='utf-8') as f:
        json.dump(categorized_strings, f, ensure_ascii=False, indent=2)


# ------------------- 异步过滤任务 -------------------
def _init_filter_task(session_id, log_path, keep_strings, filter_strings, selected_strings, preferred_backend="auto"):
    with _filter_tasks_lock:
        _filter_tasks[session_id] = {
            "status": "running",
            "log_path": log_path,
            "temp_file": get_temp_file_path(session_id),
            "idx_file": None,
            "encoding": None,
            "done_lines": 0,
            "total_lines": None,
            "first_ready": False,
            "finished": False,
            "error": None,
            "keep_strings": keep_strings,
            "filter_strings": filter_strings,
            "selected_strings": selected_strings,
            "backend": "",
            "preferred_backend": _normalize_filter_backend_preference(preferred_backend),
        }


def _update_filter_task(session_id, **kwargs):
    with _filter_tasks_lock:
        if session_id not in _filter_tasks:
            return
        _filter_tasks[session_id].update(kwargs)


def _get_filter_task(session_id):
    with _filter_tasks_lock:
        return _filter_tasks.get(session_id, {}).copy()


# ---- AI 流程分析任务管理 ----

def _init_ai_flow_task(task_id):
    with _ai_flow_tasks_lock:
        _ai_flow_tasks[task_id] = {
            "status": "running",
            "events": [],
            "displayed_count": 0,
            "prompt": "",
            "input_file": "",
            "response_text": "",
            "error": None,
            "config_group": "",
            "config_files": "",
        }

def _get_ai_flow_task(task_id):
    with _ai_flow_tasks_lock:
        return _ai_flow_tasks.get(task_id, {}).copy()

def _append_ai_flow_event(task_id, event):
    with _ai_flow_tasks_lock:
        if task_id in _ai_flow_tasks:
            _ai_flow_tasks[task_id].setdefault("events", []).append(event)

def _update_ai_flow_task(task_id, **kwargs):
    with _ai_flow_tasks_lock:
        if task_id in _ai_flow_tasks:
            _ai_flow_tasks[task_id].update(kwargs)

def _clear_ai_flow_task(task_id):
    with _ai_flow_tasks_lock:
        _ai_flow_tasks.pop(task_id, None)


def _ai_flow_worker(task_id, prompt, input_file, config_group, config_files):
    """后台线程：执行 AI 流程分析，实时记录事件"""
    try:
        runtime = _get_free_code_runtime_config(None)
        bridge = _resolve_free_code_bridge(runtime["cwd"])
        session = bridge.ensure_session(task_id)

        _append_ai_flow_event(task_id, {"type": "prompt", "content": prompt, "ts": time.time()})
        session.client.send_text(prompt)

        while True:
            event = session.client.read_event(timeout=60)
            etype = event.get("type")

            if etype == "system":
                _append_ai_flow_event(task_id, {
                    "type": "system", "subtype": event.get("subtype"),
                    "content": event, "ts": time.time()
                })
            elif etype == "assistant_partial":
                delta = str(event.get("delta") or "")
                if delta:
                    _append_ai_flow_event(task_id, {
                        "type": "text", "content": delta, "ts": time.time()
                    })
            elif etype == "assistant":
                text = extract_text_from_chat_event(event)
                if text:
                    _append_ai_flow_event(task_id, {
                        "type": "text", "content": text, "ts": time.time()
                    })
            elif etype == "result":
                _append_ai_flow_event(task_id, {"type": "done", "ts": time.time()})
                break
            elif etype == "error":
                err = event.get("error", "未知错误")
                _append_ai_flow_event(task_id, {"type": "error", "content": err, "ts": time.time()})
                _update_ai_flow_task(task_id, status="error", error=err)
                return

        # 收集完整响应
        all_events = _get_ai_flow_task(task_id).get("events", [])
        parts = []
        for e in all_events:
            if e.get("type") == "text":
                parts.append(e["content"])
        full_text = "".join(parts).strip()
        _update_ai_flow_task(task_id, status="done", response_text=full_text)
    except Exception as e:
        err_msg = str(e)
        _append_ai_flow_event(task_id, {"type": "error", "content": err_msg, "ts": time.time()})
        _update_ai_flow_task(task_id, status="error", error=err_msg)


def _render_ai_flow_events(events, start_from=0):
    """将 AI 流程事件列表渲染为 HTML"""
    chunks = []
    for i in range(start_from, len(events)):
        e = events[i]
        etype = e.get("type", "")
        ts = e.get("ts", 0)
        time_str = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else ""

        if etype == "prompt":
            chunks.append(html.Div([
                html.Small(f"[{time_str}] ", style={"color": "#999"}),
                html.Span("发送 Prompt", style={"fontWeight": 600, "color": "#005c99"}),
            ], style={"padding": "4px 8px", "background": "#e8f4fd", "borderLeft": "3px solid #005c99", "marginBottom": "2px", "borderRadius": "3px", "fontSize": "12px"}))

        elif etype == "system":
            subtype = e.get("subtype", "")
            if subtype == "init":
                chunks.append(html.Div([
                    html.Small(f"[{time_str}] ", style={"color": "#999"}),
                    html.Span("系统初始化", style={"color": "#666"}),
                ], style={"padding": "2px 8px", "fontSize": "12px", "color": "#888"}))
            elif subtype == "can_use_tool":
                req = e.get("content", {}).get("request", {})
                tool_input = req.get("input", {})
                tool_name = tool_input.get("tool", "?")
                args = tool_input.get("arguments", {})
                args_str = "; ".join(f"{k}={v}" for k, v in args.items())[:120]
                chunks.append(html.Div([
                    html.Small(f"[{time_str}] ", style={"color": "#999"}),
                    html.Span(f"🔧 使用工具: {tool_name}", style={"fontWeight": 600, "color": "#e67e22"}),
                    html.Span(f" {args_str}", style={"color": "#999", "fontSize": "11px"}),
                ], style={"padding": "2px 8px 2px 24px", "fontSize": "12px"}))

        elif etype == "text":
            text = e.get("content", "")
            preview = text[:200].replace("\n", " ")
            chunks.append(html.Div([
                html.Small(f"[{time_str}] ", style={"color": "#999"}),
                html.Span(preview, style={"color": "#333"}),
                html.Span("…" if len(text) > 200 else "", style={"color": "#999"}),
            ], style={"padding": "2px 8px 2px 24px", "fontSize": "12px", "fontFamily": "monospace", "lineHeight": "1.5"}))

        elif etype == "done":
            chunks.append(html.Div([
                html.Span("✓ 分析完成", style={"fontWeight": 600, "color": "#28a745"}),
            ], style={"padding": "4px 8px", "background": "#d4edda", "borderLeft": "3px solid #28a745", "marginTop": "4px", "borderRadius": "3px", "fontSize": "12px"}))

        elif etype == "error":
            err = e.get("content", "未知错误")
            chunks.append(html.Div([
                html.Small(f"[{time_str}] ", style={"color": "#999"}),
                html.Span(f"✗ 错误: {err}", style={"color": "#dc3545", "fontWeight": 600}),
            ], style={"padding": "4px 8px", "background": "#f8d7da", "borderLeft": "3px solid #dc3545", "marginTop": "4px", "borderRadius": "3px", "fontSize": "12px"}))

    return chunks


# ---- 过滤后端信息 ----

def _format_filter_backend_text(backend=None, preferred_backend="auto", pending=False):
    info = _get_filter_backend_runtime_info(preferred_backend)
    preferred_backend = info.get("preferred_backend") or "auto"
    resolved_backend = info.get("resolved_backend")

    if pending:
        text = "当前工具: 检测中"
        if preferred_backend != "auto":
            text += f"（偏好 {preferred_backend}）"
    elif backend:
        text = f"当前工具: {backend}"
        if preferred_backend != "auto":
            text += f"（偏好 {preferred_backend}）"
    else:
        if preferred_backend == "auto":
            text = f"当前工具: 自动 → {(resolved_backend or 'python')}"
        else:
            text = f"当前工具: {preferred_backend}"
            if resolved_backend and resolved_backend != preferred_backend:
                text += f" → {resolved_backend}"

    if os.name == "nt":
        rg_info = info.get("rg") or {}
        detail_parts = [
            f"rg: {rg_info.get('source') or '未检测到'}",
            f"findstr: {'可用' if info.get('findstr') else '不可用'}",
            f"PowerShell: {'可用' if info.get('powershell') else '不可用'}"
        ]
    else:
        rg_info = info.get("rg") or {}
        detail_parts = [
            f"rg: {rg_info.get('source') or '未检测到'}",
            f"grep: {'可用' if info.get('grep') else '不可用'}"
        ]

    resolve_error = info.get("resolve_error")
    if resolve_error:
        detail_parts.append(f"回退原因: {resolve_error}")
    return f"{text} · " + " · ".join(detail_parts)


def _estimate_total_lines(log_path):
    try:
        size = os.path.getsize(log_path)
        # 粗略估计：假设平均 100 字节/行
        return max(1, size // 100)
    except Exception:
        return None


def _filter_worker(session_id, log_path, keep_strings, filter_strings, preferred_backend="auto", index_every=500):
    try:
        temp_file_path = get_temp_file_path(session_id)
        idx_path = get_temp_index_path(temp_file_path)
        encoding = detect_file_encoding(log_path)
        keep_bytes_regex, filter_bytes_regex = _compile_byte_patterns(keep_strings, filter_strings, encoding=encoding)
        keep_regex, filter_regex = _compile_patterns(keep_strings, filter_strings)

        total_lines_est = _estimate_total_lines(log_path)
        _update_filter_task(session_id, temp_file=temp_file_path, idx_file=idx_path, encoding=encoding, total_lines=total_lines_est)

        line_count = 0
        offsets = []
        current_offset = 0
        write_buffer = []
        write_buffer_size = 0
        MAX_BUFFER_SIZE = 64 * 1024  # 64KB 缓冲区

        # 预先获取任务状态，减少循环内锁竞争
        task_info = _get_filter_task(session_id)
        if not task_info:
            return

        try:
            temp_file_path, idx_path, line_count, output_encoding, backend = stream_filter_to_temp(
                log_path,
                keep_regex,
                filter_regex,
                keep_strings,
                filter_strings,
                session_id=session_id,
                index_every=index_every,
                preferred_backend=preferred_backend
            )
            _update_filter_task(
                session_id,
                temp_file=temp_file_path,
                idx_file=idx_path,
                encoding=output_encoding,
                done_lines=line_count,
                first_ready=True,
                finished=True,
                status="finished",
                backend=backend
            )
            print(f"[过滤线程] session={session_id} 使用外部预处理完成，行数={line_count}")
            return
        except Exception as external_error:
            print(f"[过滤] 外部预处理不可用，回退 Python 流式过滤: {external_error}")
            _update_filter_task(session_id, backend="python-fallback")

        with open(log_path, 'rb') as src, open(temp_file_path, 'wb') as dst:
            for raw_line in src:
                # 1. 优先处理字节级过滤 (最快)
                if filter_bytes_regex and filter_bytes_regex.search(raw_line):
                    continue
                
                # 2. 只有在需要时才解码一次
                text_line = None
                if filter_regex:
                    try:
                        text_line = raw_line.decode(encoding)
                    except UnicodeDecodeError:
                        text_line = raw_line.decode(encoding, errors='replace')
                    if filter_regex.search(text_line):
                        continue

                # 3. 处理保留逻辑
                if keep_bytes_regex:
                    if not keep_bytes_regex.search(raw_line):
                        continue
                elif keep_regex:
                    if text_line is None:
                        try:
                            text_line = raw_line.decode(encoding)
                        except UnicodeDecodeError:
                            text_line = raw_line.decode(encoding, errors='replace')
                    if not keep_regex.search(text_line):
                        continue

                # 4. 写入缓冲区
                write_buffer.append(raw_line)
                write_buffer_size += len(raw_line)
                
                line_count += 1
                if line_count % index_every == 1:
                    offsets.append([line_count, current_offset])
                current_offset += len(raw_line)

                # 5. 批量刷新到磁盘
                if write_buffer_size >= MAX_BUFFER_SIZE:
                    dst.writelines(write_buffer)
                    write_buffer = []
                    write_buffer_size = 0

                # 6. 减少状态更新频率，降低锁开销
                if line_count % 1000 == 0:
                    task_now = _get_filter_task(session_id)
                    if not task_now or task_now.get("status") != "running":
                        raise RuntimeError("任务已取消")
                    _update_filter_task(session_id, done_lines=line_count)

                if line_count == _FILTER_CHUNK_LINES:
                    # 首片就绪逻辑保持
                    dst.writelines(write_buffer) # 立即刷新首片
                    write_buffer = []
                    write_buffer_size = 0
                    _update_filter_task(session_id, first_ready=True)

            # 循环结束后的最终刷新
            if write_buffer:
                dst.writelines(write_buffer)

        # 写索引
        try:
            with open(idx_path, 'w', encoding='utf-8') as idx_file:
                json.dump({
                    "encoding": encoding,
                    "index_every": index_every,
                    "offsets": offsets
                }, idx_file, ensure_ascii=False)
        except Exception as e:
            print(f"[过滤] 写入索引失败: {e}")

        _update_filter_task(session_id, done_lines=line_count, finished=True, first_ready=True, status="finished")
        print(f"[过滤线程] session={session_id} 完成，行数={line_count}")
    except Exception as e:
        print(f"[过滤] 异步过滤失败: {e}")
        _update_filter_task(session_id, error=str(e), status="error", finished=True)
    finally:
        # 确保任务最终标记为完成，防止进度条卡住
        try:
            task = _get_filter_task(session_id)
            if task and not task.get("finished"):
                print(f"[过滤线程] session={session_id} finally块触发完成状态更新")
                _update_filter_task(session_id, finished=True, status="finished" if task.get("status") != "error" else "error")
        except Exception as e:
            print(f"[过滤] finally块更新状态失败: {e}")


def _read_partial_lines(file_path, encoding, max_lines):
    """读取临时文件前 max_lines 行"""
    lines = []
    try:
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            for _ in range(max_lines):
                line = f.readline()
                if not line:
                    break
                lines.append(line)
    except Exception as e:
        print(f"[过滤] 读取部分结果失败: {e}")
    return "".join(lines)
    
    return len(selected_strings)

def load_default_config():
    """从默认配置文件加载选中的字符串"""
    default_config_path = get_default_config_path()
    
    if not os.path.exists(default_config_path):
        return []
    
    try:
        with open(default_config_path, 'r', encoding='utf-8') as f:
            saved_selections = json.load(f)
        
        # 从保存的选择中提取所有字符串
        loaded_strings = []
        
        for category, content in saved_selections.items():
            if isinstance(content, dict):
                # 处理保留字符串
                if "keep" in content:
                    for string_text in content["keep"]:
                        loaded_strings.append({
                            "text": string_text,
                            "type": "keep"
                        })
                
                # 处理过滤字符串
                if "filter" in content:
                    for string_text in content["filter"]:
                        loaded_strings.append({
                            "text": string_text,
                            "type": "filter"
                        })
            else:
                # 处理旧格式的配置文件
                for string_text in content:
                    loaded_strings.append({
                        "text": string_text,
                        "type": "keep"  # 默认为保留字符串
                    })
        
        return loaded_strings
    except Exception as e:
        print(f"加载默认配置文件时出错: {e}")
        return []

def load_highlight_config():
    """从highlight配置文件加载选中的字符串"""
    highlight_config_path = os.path.join(CONFIG_DIR, "highlight.json")
    
    if not os.path.exists(highlight_config_path):
        return []
    
    try:
        with open(highlight_config_path, 'r', encoding='utf-8') as f:
            saved_selections = json.load(f)
        
        # 从保存的选择中提取所有字符串
        loaded_strings = []
        
        for category, content in saved_selections.items():
            if isinstance(content, dict):
                # 处理保留字符串
                if "keep" in content:
                    for string_text in content["keep"]:
                        loaded_strings.append({
                            "text": string_text,
                            "type": "keep"
                        })
                
                # 处理过滤字符串
                if "filter" in content:
                    for string_text in content["filter"]:
                        loaded_strings.append({
                            "text": string_text,
                            "type": "filter"
                        })
            else:
                # 处理旧格式的配置文件
                for string_text in content:
                    loaded_strings.append({
                        "text": string_text,
                        "type": "keep"  # 默认为保留字符串
                    })
        
        return loaded_strings
    except Exception as e:
        print(f"加载highlight配置文件时出错: {e}")
        return []

def has_highlight_config():
    """检查是否存在highlight配置文件"""
    highlight_config_path = os.path.join(CONFIG_DIR, "highlight.json")
    return os.path.exists(highlight_config_path)

def has_default_config():
    """检查是否存在默认配置文件"""
    default_config_path = get_default_config_path()
    return os.path.exists(default_config_path)

def load_rolling_config():
    """加载滚动窗口配置参数

    优先从根目录的 settings.json 读取；若不存在则回退到 configs/rolling.json。

    返回包含以下键的字典（若文件不存在或无效则返回默认值）：
    - lines_before: 加载中心行之前的行数
    - lines_after: 加载中心行之后的行数
    - prefetch_threshold: 当距离窗口边缘小于该行数时触发新请求
    """
    try:
        defaults = {
            "lines_before": 250,           # 约等于原先500窗口的前半
            "lines_after": 249,            # 约等于原先500窗口的后半
            "prefetch_threshold": 125      # 约等于原先 windowSize/4
        }

        # 根目录 settings.json（打包后位于 base_path）
        root_settings_path = os.path.join(base_path, "settings.json")

        cfg = None
        if os.path.exists(root_settings_path):
            with open(root_settings_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)

        if cfg is None:
            return defaults

        lines_before = int(cfg.get("lines_before", defaults["lines_before"]))
        lines_after = int(cfg.get("lines_after", defaults["lines_after"]))
        prefetch_threshold = int(cfg.get("prefetch_threshold", defaults["prefetch_threshold"]))
        return {
            "lines_before": max(0, lines_before),
            "lines_after": max(0, lines_after),
            "prefetch_threshold": max(1, prefetch_threshold)
        }
    except Exception as e:
        print(f"加载滚动配置失败: {e}")
        return {
            "lines_before": 250,
            "lines_after": 249,
            "prefetch_threshold": 125
        }

def get_log_path(log_filename):
    """获取日志文件的完整路径"""
    _, file_path = _resolve_log_file_path(log_filename, allowed_extensions=ALLOWED_LOG_EXTENSIONS)
    return file_path

# 加载已保存的数据
def load_data():
    """加载分类数据，带简单mtime缓存减少重复IO"""
    try:
        if os.path.exists(DATA_FILE):
            mtime = os.path.getmtime(DATA_FILE)
            if _data_cache["mtime"] == mtime and _data_cache["data"] is not None:
                return _data_cache["data"]
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                _data_cache["data"] = json.load(f)
                _data_cache["mtime"] = mtime
                return _data_cache["data"]
    except Exception as e:
        print(f"加载数据失败: {e}")
    # 回退到随包的默认数据（只读）
    packaged_path = os.path.join(base_path, DATA_FILE)
    if os.path.exists(packaged_path):
        with open(packaged_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"categories": {}}

# 保存数据
def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        _data_cache["data"] = data
        _data_cache["mtime"] = os.path.getmtime(DATA_FILE)
    except Exception:
        pass

def get_all_keywords_from_data(data):
    """从数据对象中提取所有关键字列表"""
    keywords = []
    if isinstance(data, dict) and "categories" in data:
        for _, strings in data["categories"].items():
            for s in strings:
                if isinstance(s, str):
                    keywords.append(s)
    # 去重并按字母排序（不区分大小写）
    return sorted(list(dict.fromkeys(keywords)), key=lambda x: x.lower())

# 保存用户选择状态
def save_user_selections(selected_log_file, selected_strings, selected_config_files=None):
    # 加载当前的选择状态以保留其他字段
    current_selections = load_user_selections()
    
    selections = {
        "selected_log_file": selected_log_file,
        "selected_strings": selected_strings,
        "last_updated": datetime.now().isoformat()
    }
    
    # 保留现有的selected_config_files，除非提供了新的值
    if selected_config_files is not None:
        selections["selected_config_files"] = selected_config_files
    elif "selected_config_files" in current_selections:
        selections["selected_config_files"] = current_selections["selected_config_files"]
    else:
        selections["selected_config_files"] = []
    
    # 保留其他可能存在的字段
    for key, value in current_selections.items():
        if key not in selections:
            selections[key] = value
    
    selections_file = os.path.join(os.path.dirname(DATA_FILE), "user_selections.json")
    with open(selections_file, 'w', encoding='utf-8') as f:
        json.dump(selections, f, ensure_ascii=False, indent=2)

# 加载用户选择状态
def load_user_selections():
    selections_file = os.path.join(os.path.dirname(DATA_FILE), "user_selections.json")
    if os.path.exists(selections_file):
        try:
            with open(selections_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:  # 确保文件不为空
                    return json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"加载用户选择状态时出错: {e}")
            # 如果文件损坏，删除并重新创建
            os.remove(selections_file)
    
    # 返回默认值
    return {
        "selected_log_file": "",
        "selected_strings": [],
        "last_updated": ""
    }

# 临时关键字存储：保留/屏蔽统一结构
def normalize_temp_keywords(keywords):
    """标准化临时关键字结构，支持保留与屏蔽"""
    normalized = []
    seen = set()
    for kw in keywords or []:
        if isinstance(kw, dict):
            text = kw.get("text", "")
            kw_type = kw.get("type", "keep")
        else:
            text = str(kw)
            kw_type = "keep"
        if not text:
            continue
        text = text.strip()
        kw_type = "filter" if kw_type == "filter" else "keep"
        key = (kw_type, text)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"text": text, "type": kw_type})
    return normalized

def load_temp_keywords_from_file():
    """从配置文件加载临时关键字，默认空列表"""
    try:
        if os.path.exists(TEMP_KEYWORDS_FILE):
            mtime = os.path.getmtime(TEMP_KEYWORDS_FILE)
            if _temp_keywords_cache["mtime"] == mtime and _temp_keywords_cache["data"] is not None:
                return _temp_keywords_cache["data"]
            with open(TEMP_KEYWORDS_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            normalized = normalize_temp_keywords(raw)
            _temp_keywords_cache["data"] = normalized
            _temp_keywords_cache["mtime"] = mtime
            return normalized
    except Exception as e:
        print(f"加载临时关键字配置失败: {e}")
    return []

def save_temp_keywords_to_file(keywords):
    """将临时关键字保存到配置文件"""
    try:
        normalized = normalize_temp_keywords(keywords)
        with open(TEMP_KEYWORDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
        _temp_keywords_cache["data"] = normalized
        _temp_keywords_cache["mtime"] = os.path.getmtime(TEMP_KEYWORDS_FILE)
    except Exception as e:
        print(f"保存临时关键字配置失败: {e}")

def _safe_config_name(value, fallback="AI_KEYWORDS"):
    name = str(value or "").strip()
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", "_", name).strip("._ ")
    return name or fallback

def _extract_json_payload(text):
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
    raise ValueError("AI 返回内容不是有效 JSON")

def _collect_free_code_final_text(events):
    partial_fragments = []
    assistant_text = ""
    for event in events or []:
        event_type = event.get("type")
        if event_type == "assistant_partial":
            text = str(event.get("delta") or "")
            if text:
                partial_fragments.append(text)
        elif event_type == "assistant":
            text = extract_text_from_chat_event(event)
            if text:
                assistant_text = text
    return "".join(partial_fragments).strip() or assistant_text.strip()

def _read_ai_keyword_log_line(log_file, line_number):
    try:
        line_no = int(line_number or 0)
    except (TypeError, ValueError):
        return ""
    if line_no <= 0 or not log_file:
        return ""
    try:
        path = log_file if os.path.isabs(str(log_file)) else get_log_path(str(log_file))
        if not os.path.exists(path):
            return ""
        encoding = detect_file_encoding(path)
        with open(path, "r", encoding=encoding, errors="replace") as f:
            for current_line, raw_line in enumerate(f, start=1):
                if current_line == line_no:
                    return raw_line.rstrip("\r\n")
                if current_line > line_no:
                    break
    except Exception:
        return ""
    return ""

def _normalize_ai_paths(payload):
    paths = payload.get("paths") if isinstance(payload, dict) else []
    if not isinstance(paths, list):
        return []
    normalized = []
    for idx, item in enumerate(paths[:50]):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("id") or f"path_{idx + 1}").strip()
        if not name:
            continue
        normalized.append({
            "id": str(item.get("id") or _safe_config_name(name, f"path_{idx + 1}")),
            "name": name,
            "description": str(item.get("description") or "").strip(),
            "entry_points": item.get("entry_points") if isinstance(item.get("entry_points"), list) else [],
            "log_clues": item.get("log_clues") if isinstance(item.get("log_clues"), list) else [],
        })
    return normalized

def _normalize_ai_keyword_candidates(payload):
    categories = payload.get("categories") if isinstance(payload, dict) else {}
    if not isinstance(categories, dict):
        return []
    candidates = []
    seen = set()
    for category, content in categories.items():
        if not isinstance(content, dict):
            continue
        category_name = str(category or "AI").strip() or "AI"
        for keyword_type in ("keep", "filter"):
            values = content.get(keyword_type) or []
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, dict):
                    text = str(value.get("text") or "").strip()
                    reason = str(value.get("reason") or "").strip()
                    source = str(value.get("source") or "").strip()
                    confidence = value.get("confidence")
                else:
                    text = str(value or "").strip()
                    reason = ""
                    source = ""
                    confidence = None
                if len(text) < 2:
                    continue
                key = (category_name, keyword_type, text.lower())
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({
                    "id": len(candidates),
                    "category": category_name,
                    "type": keyword_type,
                    "text": text,
                    "reason": reason,
                    "source": source,
                    "confidence": confidence,
                })
                if len(candidates) >= AI_KEYWORD_MAX_CANDIDATES:
                    return candidates
    return candidates

def _build_ai_logic_paths_prompt(data_path):
    return f"""你是 log_filter 的代码逻辑路径分析助手。

请分析以下 free-code 工作目录中的项目结构和主要功能逻辑路径：

free-code 工作目录/源码根目录：
{data_path}

要求：
1. 你可以读取和搜索该目录下代码。
2. 找出适合后续从日志链生成关键字组的功能逻辑路径。
3. 只输出 JSON，不要输出 Markdown。
4. JSON 格式必须为：
{{
  "paths": [
    {{
      "id": "stable_ascii_id",
      "name": "逻辑路径名称",
      "description": "这条逻辑路径负责什么",
      "entry_points": ["入口函数/文件/模块"],
      "log_clues": ["可能出现在日志中的模块名/函数名/tag"]
    }}
  ]
}}"""

def _build_ai_logic_path_chat_prompt(data_path, chat_history, user_message):
    history_text = "\n".join(
        f"{item.get('role', 'user')}: {item.get('content', '')}"
        for item in (chat_history or [])[-12:]
        if isinstance(item, dict)
    )
    return f"""你是 log_filter 的代码逻辑路径讨论助手。

free-code 工作目录/源码根目录：
{data_path}

已有对话：
{history_text or "暂无"}

用户新消息：
{user_message}

请结合源码分析能力和用户目标继续讨论，帮助用户明确哪些功能逻辑路径适合后续生成日志关键字组。回答可以是自然语言，不要生成最终 JSON。"""

def _build_ai_logic_paths_from_chat_prompt(data_path, chat_history):
    history_text = "\n".join(
        f"{item.get('role', 'user')}: {item.get('content', '')}"
        for item in (chat_history or [])
        if isinstance(item, dict)
    )
    return f"""你是 log_filter 的代码逻辑路径提取助手。

free-code 工作目录/源码根目录：
{data_path}

以下是用户和模型关于代码逻辑路径的讨论内容：
{history_text}

请基于上面的讨论内容和你对源码的理解，生成后续用于日志关键字组生成的功能逻辑路径。

要求：
1. 你可以继续读取和搜索该目录下代码来确认路径。
2. 只输出 JSON，不要输出 Markdown。
3. JSON 格式必须为：
{{
  "paths": [
    {{
      "id": "stable_ascii_id",
      "name": "逻辑路径名称",
      "description": "这条逻辑路径负责什么",
      "entry_points": ["入口函数/文件/模块"],
      "log_clues": ["可能出现在日志中的模块名/函数名/tag"]
    }}
  ]
}}"""

def _build_ai_keyword_prompt(data_path, selected_path, relation, log_file, line_number, log_line_text):
    path_json = json.dumps(selected_path or {}, ensure_ascii=False, indent=2)
    return f"""你是 log_filter 的关键字组生成助手。

当前 free-code 工作目录/源码根目录：
{data_path}

用户选择的功能逻辑路径：
{path_json}

用户说明该日志和逻辑路径的关系：
{relation or "未提供"}

用户指定的日志位置：
- 文件: {log_file or "未提供"}
- 行号: {line_number or "未提供"}
- 日志内容: {log_line_text or "未提供"}

任务：
1. 阅读/搜索代码，定位该功能逻辑会涉及的日志打印点、模块、函数、状态、事件、错误码。
2. 生成适合 log_filter 固定字符串匹配的关键字。
3. keep 表示保留关键字，filter 表示屏蔽噪声关键字。
4. 不要生成过泛关键字，如 error、failed、start、stop、init。
5. 不要生成只在代码中存在但不会出现在日志里的内部符号，除非它会被日志打印。
6. 每个关键字给出 source、confidence、reason。
7. 只输出 JSON，不要输出 Markdown。

JSON 格式必须为：
{{
  "categories": {{
    "分类名": {{
      "keep": [
        {{"text": "关键字", "source": "code|log|both", "confidence": 0.9, "reason": "为什么保留"}}
      ],
      "filter": [
        {{"text": "噪声关键字", "source": "code|log|both", "confidence": 0.7, "reason": "为什么屏蔽"}}
      ]
    }}
  }}
}}"""

def _run_free_code_json_task(cwd, prompt, timeout=None):
    runtime = _get_free_code_runtime_config(cwd)
    bridge = _resolve_free_code_bridge(runtime["cwd"])
    session_id = f"ai-keyword-{uuid.uuid4()}"
    events = bridge.ask(session_id, prompt, timeout=timeout or FREE_CODE_CHAT_TIMEOUT)
    final_text = _collect_free_code_final_text(events)
    if not final_text:
        raise ValueError("AI 未返回可解析内容")
    return _extract_json_payload(final_text), final_text

def _run_free_code_text_task(cwd, prompt, timeout=None):
    runtime = _get_free_code_runtime_config(cwd)
    bridge = _resolve_free_code_bridge(runtime["cwd"])
    session_id = f"ai-keyword-chat-{uuid.uuid4()}"
    events = bridge.ask(session_id, prompt, timeout=timeout or FREE_CODE_CHAT_TIMEOUT)
    final_text = _collect_free_code_final_text(events)
    if not final_text:
        raise ValueError("AI 未返回内容")
    return final_text

def _render_ai_paths(paths):
    if not paths:
        return html.Div("暂无分析结果", className="text-muted")
    rows = []
    for item in paths:
        rows.append(html.Tr([
            html.Td(html.Code(item.get("id", ""), className="small")),
            html.Td(item.get("name", ""), className="small"),
            html.Td(item.get("description", ""), className="small"),
            html.Td(", ".join(str(v) for v in item.get("log_clues", [])[:8]), className="small"),
        ]))
    return dbc.Table([
        html.Thead(html.Tr([html.Th("ID"), html.Th("路径"), html.Th("说明"), html.Th("日志线索")])),
        html.Tbody(rows)
    ], bordered=True, hover=True, size="sm", responsive=True)

def _render_ai_path_chat(messages):
    if not messages:
        return html.Div("请描述你希望分析的功能、模块或日志场景。", className="text-muted")
    children = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "")
        is_user = role == "user"
        children.append(
            html.Div([
                html.Div("用户" if is_user else "AI", className="fw-bold small mb-1"),
                html.Div(content, style={"whiteSpace": "pre-wrap"})
            ], className=("p-2 rounded mb-2 bg-primary text-white ms-auto" if is_user else "p-2 rounded mb-2 bg-light border"),
               style={"maxWidth": "85%"})
        )
    return html.Div(children)

def _render_ai_keyword_candidates(candidates):
    if not candidates:
        return html.Div("暂无候选关键字", className="text-muted")
    rows = []
    for item in candidates:
        badge_color = "success" if item.get("type") == "keep" else "danger"
        rows.append(html.Tr([
            html.Td(dbc.Checkbox(id={"type": "ai-keyword-candidate-check", "index": item["id"]}, value=True)),
            html.Td(dbc.Badge(item.get("type"), color=badge_color)),
            html.Td(item.get("category", ""), className="small"),
            html.Td(html.Code(item.get("text", ""), className="small")),
            html.Td(str(item.get("confidence") or ""), className="small"),
            html.Td(item.get("source", ""), className="small"),
            html.Td(item.get("reason", ""), className="small"),
        ]))
    return dbc.Table([
        html.Thead(html.Tr([html.Th("选择"), html.Th("类型"), html.Th("分类"), html.Th("关键字"), html.Th("置信度"), html.Th("来源"), html.Th("原因")])),
        html.Tbody(rows)
    ], bordered=True, hover=True, size="sm", responsive=True)

def _save_ai_keyword_group(group_name, config_name, candidates):
    group_name = str(group_name or "").strip()
    if not group_name:
        raise ValueError("请设置关键字组名")
    config_name = _safe_config_name(config_name or group_name)
    config_data = {}
    for item in candidates or []:
        category = str(item.get("category") or "AI").strip() or "AI"
        keyword_type = "filter" if item.get("type") == "filter" else "keep"
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        config_data.setdefault(category, {"keep": [], "filter": []})
        if text not in config_data[category][keyword_type]:
            config_data[category][keyword_type].append(text)
    if not config_data:
        raise ValueError("没有可保存的关键字")
    config_path = get_config_path(config_name)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)
    groups = load_config_groups()
    current_files = groups.get(group_name, [])
    if not isinstance(current_files, list):
        current_files = []
    if config_name not in current_files:
        current_files.append(config_name)
    groups[group_name] = current_files
    if not save_config_groups(groups):
        raise ValueError("保存配置文件组失败")
    _config_files_cache["mtime"] = None
    _config_files_cache["data"] = None
    return config_name, group_name, len(candidates)

def _normalize_ai_keyword_config_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("AI 返回内容必须是 JSON 对象")
    group_name = str(payload.get("group_name") or payload.get("group") or "").strip()
    raw_config_name = payload.get("config_name")
    if raw_config_name is None:
        raw_config_name = payload.get("config")
    config_name = str(raw_config_name if isinstance(raw_config_name, str) else group_name).strip()
    config_data = payload.get("config_data")
    if config_data is None:
        config_data = payload.get("categories")
    if config_data is None:
        config_data = payload.get("config")
    if not group_name:
        raise ValueError("JSON 缺少 group_name")
    if not isinstance(config_data, dict):
        raise ValueError("JSON 缺少 config_data/categories 对象")

    normalized = {}
    for category, values in config_data.items():
        category_name = str(category or "AI").strip() or "AI"
        if not isinstance(values, dict):
            continue
        keep_values = values.get("keep") or []
        filter_values = values.get("filter") or []
        if not isinstance(keep_values, list):
            keep_values = []
        if not isinstance(filter_values, list):
            filter_values = []
        keep_items = []
        filter_items = []
        for item in keep_values:
            text = str(item.get("text") if isinstance(item, dict) else item).strip()
            if text and text not in keep_items:
                keep_items.append(text)
        for item in filter_values:
            text = str(item.get("text") if isinstance(item, dict) else item).strip()
            if text and text not in filter_items:
                filter_items.append(text)
        if keep_items or filter_items:
            normalized[category_name] = {"keep": keep_items, "filter": filter_items}
    if not normalized:
        raise ValueError("配置中没有有效 keep/filter 关键字")
    return group_name, _safe_config_name(config_name or group_name), normalized

def _save_ai_keyword_config_payload(payload):
    group_name, config_name, config_data = _normalize_ai_keyword_config_payload(payload)
    config_path = get_config_path(config_name)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)
    groups = load_config_groups()
    current_files = groups.get(group_name, [])
    if not isinstance(current_files, list):
        current_files = []
    if config_name not in current_files:
        current_files.append(config_name)
    groups[group_name] = current_files
    if not save_config_groups(groups):
        raise ValueError("保存配置文件组失败")
    _config_files_cache["mtime"] = None
    _config_files_cache["data"] = None
    return {
        "group_name": group_name,
        "config_name": config_name,
        "config_path": config_path,
        "category_count": len(config_data),
        "keyword_count": sum(len(v.get("keep", [])) + len(v.get("filter", [])) for v in config_data.values()),
    }

def _render_ai_keyword_config_review(payload):
    try:
        group_name, config_name, config_data = _normalize_ai_keyword_config_payload(payload)
    except Exception:
        return html.Div("暂无 AI 生成的关键字配置", className="text-muted")
    rows = []
    for category, values in config_data.items():
        for keyword_type in ("keep", "filter"):
            badge_color = "success" if keyword_type == "keep" else "danger"
            for text in values.get(keyword_type, []):
                index = json.dumps({"category": category, "type": keyword_type, "text": text}, ensure_ascii=False)
                rows.append(html.Tr([
                    html.Td(dbc.Checkbox(id={"type": "ai-keyword-review-check", "index": index}, value=True)),
                    html.Td(category, className="small"),
                    html.Td(dbc.Badge(keyword_type, color=badge_color)),
                    html.Td(html.Code(text, className="small")),
                ]))
    if not rows:
        return html.Div("暂无有效 keep/filter 关键字", className="text-muted")
    return dbc.Table([
        html.Thead(html.Tr([html.Th("保留"), html.Th("分类"), html.Th("类型"), html.Th("关键字")])),
        html.Tbody(rows)
    ], bordered=True, hover=True, size="sm", responsive=True)

def _format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"

def _get_log_directories():
    ensure_log_dir()
    directories = []
    try:
        for root, dirs, _files in os.walk(LOG_DIR):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for dirname in dirs:
                rel_path = os.path.relpath(os.path.join(root, dirname), LOG_DIR)
                directories.append(rel_path.replace(os.sep, "/"))
    except Exception:
        pass
    return sorted(directories, key=lambda item: item.lower())

def _normalize_log_manager_dir(dirname):
    if not dirname:
        return ""
    normalized = _normalize_log_dirname(dirname)
    return normalized.replace("\\", "/")

def _join_log_manager_path(current_dir, child_name):
    current_dir = _normalize_log_manager_dir(current_dir)
    child_name = _normalize_log_relative_path(child_name)
    return f"{current_dir}/{child_name}" if current_dir else child_name

def _parent_log_manager_dir(current_dir):
    current_dir = _normalize_log_manager_dir(current_dir)
    parent = os.path.dirname(current_dir).replace("\\", "/")
    return "" if parent in {".", "/"} else parent

def _build_log_manager_breadcrumbs(current_dir):
    current_dir = _normalize_log_manager_dir(current_dir)
    crumbs = [
        dbc.Button(
            [html.I(className="bi bi-house-door me-1"), "logs"],
            id="log-dir-root-btn",
            color="link",
            size="sm",
            className="p-0 text-decoration-none"
        )
    ]
    if not current_dir:
        return html.Div(crumbs, className="d-flex align-items-center gap-2")

    accum = []
    for part in current_dir.split("/"):
        accum.append(part)
        path_value = "/".join(accum)
        crumbs.append(html.Span("/", className="text-muted small"))
        crumbs.append(
            dbc.Button(
                part,
                id={"type": "enter-log-dir-btn", "index": path_value},
                color="link",
                size="sm",
                className="p-0 text-decoration-none"
            )
        )
    return html.Div(crumbs, className="d-flex align-items-center gap-2 flex-wrap")

def _create_file_list_table(log_files, current_dir=""):
    try:
        current_dir = _normalize_log_manager_dir(current_dir)
    except Exception:
        current_dir = ""
    log_dirs = _get_log_directories()
    entries = []
    today = datetime.now().date()

    for dirname in log_dirs:
        dirname = str(dirname or "").replace("\\", "/")
        parent = os.path.dirname(dirname).replace("\\", "/")
        if parent == ".":
            parent = ""
        if parent != current_dir:
            continue
        try:
            _, dir_path = _resolve_log_dir_path(dirname, must_exist=True)
            stat = os.stat(dir_path)
            entries.append({
                "name": os.path.basename(dirname),
                "path": dirname,
                "kind": "dir",
                "size": None,
                "mtime": stat.st_mtime,
                "mtime_dt": datetime.fromtimestamp(stat.st_mtime),
            })
        except Exception:
            continue

    for file in log_files:
        file = str(file or "").replace("\\", "/")
        parent = os.path.dirname(file).replace("\\", "/")
        if parent == ".":
            parent = ""
        if parent != current_dir:
            continue
        try:
            _, file_path = _resolve_log_file_path(file, allowed_extensions=ALLOWED_LOG_EXTENSIONS)
            if not os.path.exists(file_path):
                continue
            stat = os.stat(file_path)
            entries.append({
                "name": os.path.basename(file),
                "path": file,
                "kind": "file",
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "mtime_dt": datetime.fromtimestamp(stat.st_mtime),
            })
        except Exception:
            continue

    entries.sort(key=lambda item: (item["kind"] != "dir", item["name"].lower()))

    toolbar = html.Div([
        html.Div([
            dbc.Button(
                [html.I(className="bi bi-arrow-left-short me-1"), "上级"],
                id="log-dir-up-btn",
                color="secondary",
                outline=True,
                size="sm",
                disabled=not bool(current_dir),
                className="me-2"
            ),
            _build_log_manager_breadcrumbs(current_dir)
        ], className="d-flex align-items-center flex-wrap gap-2"),
        html.Div(
            f"{len(entries)} 项",
            className="text-muted small"
        )
    ], className="d-flex align-items-center justify-content-between px-3 py-2 border-bottom bg-white")

    if not entries:
        return html.Div([
            toolbar,
            html.Div([
                html.I(className="bi bi-folder2-open", style={"fontSize": "2rem", "color": "#94a3b8"}),
                html.Div("当前目录为空", className="fw-semibold mt-2"),
                html.Div("可以创建目录、上传日志，或拖入外部文件夹。", className="text-muted small mt-1")
            ], className="text-center py-5")
        ], className="log-manager-panel")

    rows = []
    for info in entries:
        entry_path = info["path"]
        filename = info["name"]
        file_size = info["size"]
        file_mtime = info["mtime_dt"].strftime('%Y-%m-%d %H:%M:%S')
        is_dir = info["kind"] == "dir"
        row_class = "log-manager-row"
        if info["mtime_dt"].date() == today:
            row_class += " log-manager-row-recent"

        rows.append(html.Tr([
            html.Td(
                dbc.Button(
                    [
                        html.I(className=("bi bi-folder-fill" if is_dir else "bi bi-file-earmark-text") + " me-2"),
                        html.Span(filename, className="fw-semibold")
                    ],
                    id={"type": "enter-log-dir-btn", "index": entry_path} if is_dir else {"type": "log-file-name-static", "index": entry_path},
                    color="link",
                    size="sm",
                    disabled=not is_dir,
                    className="p-0 text-decoration-none log-manager-name"
                ) if is_dir else html.Div([
                    html.I(className="bi bi-file-earmark-text me-2 text-secondary"),
                    html.Span(filename, className="fw-semibold")
                ], className="d-flex align-items-center"),
                className="align-middle"
            ),
            html.Td("目录" if is_dir else _format_size(file_size), className="align-middle text-muted small"),
            html.Td(file_mtime, className="align-middle text-muted small"),
            html.Td(
                [
                    dbc.Button(
                        [html.I(className="bi bi-pencil-square"), html.Span("重命名", className="ms-1")],
                        id={"type": "rename-dir-btn" if is_dir else "rename-file-btn", "index": entry_path},
                        color="secondary",
                        size="sm",
                        outline=True,
                        className="me-2"
                    ),
                    dbc.Button(
                        [html.I(className="bi bi-trash"), html.Span("删除", className="ms-1")],
                        id={"type": "delete-dir-btn" if is_dir else "delete-file-btn", "index": entry_path},
                        color="danger",
                        size="sm",
                        outline=True
                    )
                ],
                className="align-middle"
            )
        ], className=row_class))

    table = dbc.Table([
        html.Thead(html.Tr([
            html.Th("名称"),
            html.Th("大小", style={"width": "120px"}),
            html.Th("修改时间", style={"width": "180px"}),
            html.Th("操作", style={"width": "190px"})
        ])),
        html.Tbody(rows)
    ], hover=True, responsive=True, className="mb-0 log-manager-table")

    return html.Div([toolbar, table], className="log-manager-panel")

def _create_log_picker_browser(log_files, current_dir="", selected_file=""):
    try:
        current_dir = _normalize_log_manager_dir(current_dir)
    except Exception:
        current_dir = ""

    selected_file = str(selected_file or "").replace("\\", "/")
    log_dirs = _get_log_directories()
    entries = []

    for dirname in log_dirs:
        dirname = str(dirname or "").replace("\\", "/")
        parent = os.path.dirname(dirname).replace("\\", "/")
        if parent == ".":
            parent = ""
        if parent != current_dir:
            continue
        try:
            _, dir_path = _resolve_log_dir_path(dirname, must_exist=True)
            stat = os.stat(dir_path)
            entries.append({
                "name": os.path.basename(dirname),
                "path": dirname,
                "kind": "dir",
                "size": None,
                "mtime_dt": datetime.fromtimestamp(stat.st_mtime),
            })
        except Exception:
            continue

    for file in log_files:
        file = str(file or "").replace("\\", "/")
        parent = os.path.dirname(file).replace("\\", "/")
        if parent == ".":
            parent = ""
        if parent != current_dir:
            continue
        try:
            _, file_path = _resolve_log_file_path(file, allowed_extensions=ALLOWED_LOG_EXTENSIONS)
            if not os.path.exists(file_path):
                continue
            stat = os.stat(file_path)
            entries.append({
                "name": os.path.basename(file),
                "path": file,
                "kind": "file",
                "size": stat.st_size,
                "mtime_dt": datetime.fromtimestamp(stat.st_mtime),
            })
        except Exception:
            continue

    entries.sort(key=lambda item: (item["kind"] != "dir", item["name"].lower()))

    crumbs = [
        dbc.Button(
            [html.I(className="bi bi-house-door me-1"), "logs"],
            id="log-picker-root-btn",
            color="link",
            size="sm",
            className="p-0 text-decoration-none"
        )
    ]
    if current_dir:
        accum = []
        for part in current_dir.split("/"):
            accum.append(part)
            path_value = "/".join(accum)
            crumbs.append(html.Span("/", className="text-muted small"))
            crumbs.append(
                dbc.Button(
                    part,
                    id={"type": "log-picker-enter-dir-btn", "index": path_value},
                    color="link",
                    size="sm",
                    className="p-0 text-decoration-none"
                )
            )

    toolbar = html.Div([
        html.Div([
            dbc.Button(
                [html.I(className="bi bi-arrow-left-short me-1"), "上级"],
                id="log-picker-up-btn",
                color="secondary",
                outline=True,
                size="sm",
                disabled=not bool(current_dir),
                className="me-2"
            ),
            html.Div(crumbs, className="d-flex align-items-center gap-2 flex-wrap")
        ], className="d-flex align-items-center flex-wrap gap-2"),
        html.Div(f"{len(entries)} 项", className="text-muted small")
    ], className="d-flex align-items-center justify-content-between px-3 py-2 border-bottom bg-white")

    if not entries:
        return html.Div([
            toolbar,
            html.Div([
                html.I(className="bi bi-folder2-open", style={"fontSize": "2rem", "color": "#94a3b8"}),
                html.Div("当前目录为空", className="fw-semibold mt-2")
            ], className="text-center py-5")
        ], className="log-manager-panel")

    rows = []
    for info in entries:
        is_dir = info["kind"] == "dir"
        path_value = info["path"]
        is_selected = path_value == selected_file
        row_class = "log-manager-row"
        if is_selected:
            row_class += " log-picker-row-selected"

        name_cell = dbc.Button(
            [
                html.I(className=("bi bi-folder-fill" if is_dir else "bi bi-file-earmark-text") + " me-2"),
                html.Span(info["name"], className="fw-semibold")
            ],
            id={"type": "log-picker-enter-dir-btn", "index": path_value} if is_dir else {"type": "log-picker-select-file-btn", "index": path_value},
            color="link",
            size="sm",
            className="p-0 text-decoration-none log-manager-name"
        )

        rows.append(html.Tr([
            html.Td(name_cell, className="align-middle"),
            html.Td("目录" if is_dir else _format_size(info["size"]), className="align-middle text-muted small"),
            html.Td(info["mtime_dt"].strftime('%Y-%m-%d %H:%M:%S'), className="align-middle text-muted small"),
            html.Td(
                "" if is_dir else (
                    dbc.Badge("当前", color="success", pill=True) if is_selected else html.Span("点击名称选择", className="text-muted small")
                ),
                className="align-middle text-end"
            )
        ], className=row_class))

    return html.Div([
        toolbar,
        dbc.Table([
            html.Thead(html.Tr([
                html.Th("名称"),
                html.Th("大小", style={"width": "120px"}),
                html.Th("修改时间", style={"width": "180px"}),
                html.Th("", style={"width": "96px"})
            ])),
            html.Tbody(rows)
        ], hover=True, responsive=True, className="mb-0 log-manager-table")
    ], className="log-manager-panel")

# 初始数据
data = load_data()

# 确保配置目录存在
ensure_config_dir()
# 加载外部程序配置
ext_prog_config = load_external_program_config()
# 加载 LLM 分析配置
llm_config = load_llm_config()

# 应用布局
app.layout = html.Div([
    # Toast通知容器
    html.Div(id="toast-container", className="toast-container"),
    dcc.Store(id="group-selected-files-store", data=[]),
    dcc.Store(id="log-manager-current-dir-store", data=""),
    dcc.Store(id="log-picker-current-dir-store", data=""),
    dcc.Store(id="llm-source-dirs-store", data=llm_config.get("source_code_dirs", [])),
    dcc.Store(id="selected-log-lines-store", data=[]),
    dcc.Store(id="chat-selected-text-store", data=""),
    dcc.Store(id="ai-keyword-paths-store", data=[]),
    dcc.Store(id="ai-keyword-candidates-store", data=[]),
    dcc.Store(id="ai-keyword-path-chat-store", data=[]),
    dcc.Store(id="ai-keyword-path-chat-pending-store", data=None),
    dcc.Store(id="ai-keyword-generated-config-store", data={}),
    dcc.Textarea(id="ai-keyword-generated-config-sync-input", value="", style={"display": "none"}),
    dcc.Interval(id="ai-keyword-path-chat-pending-interval", interval=300, disabled=True, max_intervals=0),
    html.Div(id="chat-selected-text-input", style={"display": "none"}, children=""),
    dcc.Input(id="selected-lines-sync-input", type="text", value="", style={"display": "none"}),
    html.Div(id="log-analysis-context-json", style={"display": "none"}, children="{}"),
    dcc.Store(id="filter-session-store", data=""),
    dcc.Store(id="filter-first-chunk-ready", data=False),
    dcc.Store(id="ai-flow-analysis-trigger", data=0),
    dcc.Store(id="ai-flow-interaction-log", data={}),
    dcc.Interval(id="filter-progress-interval", interval=_FILTER_PROGRESS_INTERVAL_MS, disabled=True),
    dcc.Store(id="compare-session-store", data={"a": "", "b": ""}),
    dcc.Interval(id="compare-progress-interval", interval=_FILTER_PROGRESS_INTERVAL_MS, disabled=True),
    dcc.Store(id=_UI_BUSY_STORE_ID, data=_make_log_view_ui_state("idle")),
    dcc.Location(id="url", refresh=False),
    dcc.Download(id="runtime-log-download"),
    html.Button(id="export-runtime-logs-btn", style={"display": "none"}),
    
    dbc.Container([
        # 状态提示 - 隐藏原始状态栏，使用toast通知
        dbc.Row([
            dbc.Col([
                dbc.Alert(id="status-alert", is_open=False, dismissable=True, duration=4000, style={"display": "none"})
            ], width=12)
        ], style={"display": "none"}),
        
        # Tab导航
        dbc.Row([
            dbc.Col([
                dbc.Tabs([
                    dbc.Tab(label="日志过滤", tab_id="tab-1"),
                    dbc.Tab(label="日志对比", tab_id="tab-compare"),
                    dbc.Tab(label="AI生成关键字", tab_id="tab-ai-keywords"),
                    dbc.Tab(label="日志管理", tab_id="tab-3"),
                    dbc.Tab(label="配置管理", tab_id="tab-2"),
                    dbc.Tab(label="关键字注释(开发中)", tab_id="tab-4")
                ], id="main-tabs", active_tab="tab-1")
            ], width=12)
        ], className="mb-4"),
        
        # Tab1内容 - 日志过滤
        html.Div(id="tab-1-content", children=[
            # 顶部居中的当前日志文件名
            html.Div([
                html.Span(
                    id="selected-log-file-display",
                    className="selected-log-file-display small",
                    children="FILE: 未选择日志"
                )
            ], className="position-fixed", style={"top": "20px", "left": "50%", "transform": "translateX(-50%)", "zIndex": 1000, "maxWidth": "calc(100vw - 520px)"}),

            # 右上角固定按钮区域
            html.Div([
                html.Div([
                    html.Div([
                        dcc.Dropdown(
                            id="log-file-selector",
                            placeholder="选择日志文件...",
                            options=[],
                            clearable=False,
                            style={"display": "none"}
                        ),
                        dbc.Button(
                            [html.I(className="bi bi-folder2-open me-1"), html.Span("选择日志文件")],
                            id="open-log-picker-btn",
                            color="primary",
                            size="sm",
                            outline=True,
                            className="me-2"
                        )
                    ], className="d-inline-flex align-items-center me-2 align-middle"),
                    html.Div([
                        dcc.Dropdown(
                            id="log-filter-config-group-selector",
                            placeholder="配置文件组",
                            style={"width": "120px", "fontSize": "12px", "textAlign": "left"},
                            clearable=True
                        )
                    ], className="d-inline-block me-2 align-middle"),
                    dbc.Button(
                        "🔍 临时关键字", 
                        id="temp-keyword-drawer-toggle", 
                        color="secondary", 
                        size="sm"
                    ),
                    dbc.Button(
                        html.I(className="bi bi-box-arrow-up-right"), 
                        id="open-external-btn", 
                        color="secondary", 
                        size="sm",
                        className="ms-2",
                        title="使用外部程序打开当前日志"
                    ),
                    dbc.Popover([
                        dbc.PopoverHeader("添加临时关键字"),
                        dbc.PopoverBody([
                            html.Div([
                                html.Small("临时关键字（保留）", className="text-muted"),
                            ], className="mb-1"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Input(id="temp-keyword-text", placeholder="输入关键字...", size="sm"),
                                ], width=8, className="pe-1"),
                                dbc.Col([
                                    dbc.Button("添加", id="temp-keyword-add-btn", color="primary", size="sm", className="w-100")
                                ], width=4, className="ps-1")
                            ], className="g-0 align-items-center mb-2"),
                            html.Div([
                                html.Small("临时反向关键字（屏蔽）", className="text-muted"),
                            ], className="mb-1"),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Input(id="temp-exclude-keyword-text", placeholder="输入要屏蔽的关键字...", size="sm"),
                                ], width=8, className="pe-1"),
                                dbc.Col([
                                    dbc.Button("屏蔽", id="temp-exclude-keyword-add-btn", color="danger", size="sm", className="w-100")
                                ], width=4, className="ps-1")
                            ], className="g-0 align-items-center"),
                            html.Hr(className="my-2"),
                            html.Div([
                                html.Small("当前临时关键字", className="text-muted d-block mb-1"),
                                html.Div(id="temp-keywords-popover-display", className="d-flex flex-wrap gap-1")
                            ])
                        ])
                    ],
                    id="temp-keyword-popover",
                    target="temp-keyword-drawer-toggle",
                    trigger="legacy",
                    placement="bottom",
                    style={"maxWidth": "800px"}
                    )
                ], className="d-flex align-items-center justify-content-end"),
                

            ], className="position-fixed", style={"top": "20px", "right": "20px", "zIndex": 1000, "maxWidth": "600px"}),
            

            # 日志过滤结果
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            # 左侧：配置文件选择器和相关按钮
                            dbc.Row([
                                dbc.Col([
                                    html.Div([
                                        html.Div([
                                            html.Button(
                                                [html.I(className="bi bi-chevron-down me-2"), "配置文件"],
                                                id="config-files-toggle",
                                                className="btn btn-link text-decoration-none p-0 text-start",
                                                style={"color": "#333", "fontWeight": "bold"}
                                            ),
                                            html.Span(id="log-view-status-bar", className="badge bg-secondary ms-3", style={"minWidth": "60px"}, children="Ready"),
                                        ], className="d-flex align-items-center"),
                                        html.Div([
                                            dbc.Button("清除选择", id="clear-config-selection-btn", color="danger", size="sm", className="me-2"),
                                            html.Div([
                                                dbc.Button([
                                                    html.Span("过滤", id="filter-btn-text"),
                                                    dbc.Spinner(size="sm", color="light", id="filter-loading-spinner", spinner_style={"display": "none", "marginLeft": "5px"})
                                                ], id="execute-filter-btn", color="success", size="sm"),
                                                dcc.Loading(
                                                    id="filter-loading",
                                                    type="circle",
                                                    children=html.Div(id="filter-loading-output"),
                                                    style={"display": "none"}
                                                )
                                            ], style={"display": "inline-block"})
                                        ], className="d-flex align-items-center")
                                    ], className="d-flex justify-content-between align-items-center mb-2"),
                                    dbc.Collapse(
                                        html.Div(id="config-files-container", className="border rounded p-2", style={"maxHeight": "150px", "overflowY": "auto", "fontSize": "11px"}),
                                        id="config-files-collapse",
                                        is_open=True
                                    ),
                                    # 显示模式切换 Tabs
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Tabs([
                                                dbc.Tab(label="过滤结果", tab_id="filtered", children=[
                                                    html.Div(id="log-filter-results", style={"minHeight": "calc(100vh - 430px)", "maxHeight": "calc(100vh - 300px)", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px", "fontFamily": "monospace", "fontSize": "12px"}),
                                                    html.Div([
                                                        dbc.Progress(id="filter-progress-bar", value=0, striped=True, animated=True, className="my-2", style={"height": "8px", "minWidth": "200px"}),
                                                        html.Div(id="filter-progress-text", className="small text-muted mb-1")
                                                    ], id="filter-progress-footer", className="mt-1", style={"display": "none"})
                                                ]),
                                                dbc.Tab(label="源文件", tab_id="source", children=[
                                                    html.Div(id="log-source-results", style={"minHeight": "calc(100vh - 430px)", "maxHeight": "calc(100vh - 300px)", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px", "fontFamily": "monospace", "fontSize": "12px"})
                                                ]),
                                                dbc.Tab(label="注释", tab_id="annotation", children=[
                                                    html.Div(id="log-annotation-results", style={"minHeight": "calc(100vh - 430px)", "maxHeight": "calc(100vh - 300px)", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px", "fontFamily": "monospace", "fontSize": "12px"})
                                                ]),
                                                dbc.Tab(label="流程视图", tab_id="flows", children=[
                                                    html.Div([
                                                        dbc.Row([
                                                            dbc.Col([
                                                                dbc.Button("AI 流程状态分析", id="ai-flow-analysis-btn", color="primary", size="sm", className="me-2"),
                                                                dbc.Button("交互日志", id="ai-flow-log-btn", color="secondary", outline=True, size="sm", style={"display": "none"}),
                                                                html.Span(id="ai-flow-analysis-status", className="text-muted small ms-2"),
                                                            ], width=12)
                                                        ], className="mb-2"),
                                                        html.Div(id="ai-flow-analysis-live-log", style={
                                                            "maxHeight": "300px", "overflowY": "auto",
                                                            "backgroundColor": "#fafafa", "padding": "6px",
                                                            "border": "1px solid #e0e0e0", "borderRadius": "4px",
                                                            "fontFamily": "monospace", "fontSize": "12px",
                                                            "marginBottom": "8px", "display": "none"
                                                        }),
                                                        dcc.Loading(
                                                            html.Div(id="ai-flow-analysis-results", className="mb-2"),
                                                            type="dot", color="#0d6efd",
                                                            parent_style={"minHeight": "40px"}
                                                        ),
                                                        dcc.Interval(id="ai-flow-progress-interval", interval=500, disabled=True),
                                                        dbc.Modal([
                                                            dbc.ModalHeader(dbc.ModalTitle("AI 流程分析交互日志"), close_button=True),
                                                            dbc.ModalBody(id="ai-flow-log-body", style={"maxHeight": "70vh", "overflowY": "auto", "fontSize": "12px"}),
                                                            dbc.ModalFooter(dbc.Button("关闭", id="ai-flow-log-close-btn", className="ms-auto"))
                                                        ], id="ai-flow-log-modal", size="xl", scrollable=True, is_open=False),
                                                        html.Hr(style={"margin": "4px 0"}),
                                                        html.Div(id="log-flows-results", style={"minHeight": "calc(100vh - 500px)", "maxHeight": "calc(100vh - 380px)", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px", "fontFamily": "monospace", "fontSize": "12px"})
                                                    ])
                                                ])
                                            ], id="display-mode-tabs", active_tab="filtered")
                                        ], width=12)
                                    ], className="mb-2"),
                                    # 右侧工具（关键字搜索、行跳转）
                                    dbc.Row([
                                        dbc.Col([
                                    dbc.Row([
                                        dbc.Col([
                                            html.Div([
                                                dbc.Button("top", id="quick-top-btn", color="secondary", outline=True, size="sm"),
                                                html.Span("( - / - / - )", id="log-window-line-status", className="text-muted mx-2"),
                                                dbc.Button("bottom", id="quick-bottom-btn", color="secondary", outline=True, size="sm"),
                                                html.Div(id="filter-progress-inline", style={"minWidth": "200px", "minHeight": "12px"}),
                                                dbc.Button(id="log-view-ready-signal-btn", style={"display": "none"}),
                                                dbc.Button("🖱 选择行", id="toggle-selection-mode-btn", color="secondary", outline=True, size="sm", title="点击切换行选择模式（用于AI分析）", style={"display": "none"}),
                                                html.Span(id="selected-lines-count", className="selected-lines-count", style={"display": "none"}),
                                                dbc.Button("清除选择", id="clear-selection-btn", color="warning", outline=True, size="sm", style={"display": "none"}),
                                                dbc.Button("AI分析所选日志", id="analyze-selected-logs-btn", color="primary", size="sm", title="把当前选中的日志和配置文件组上下文发送给 free-code 分析", style={"display": "none"})
                                            ], className="d-flex align-items-center gap-2 justify-content-start")
                                        ], width=6),
                                        dbc.Col([
                                            html.Div([
                                                dcc.Dropdown(
                                                    id="filter-backend-selector",
                                                    options=_get_filter_backend_selector_options(),
                                                    value=DEFAULT_FILTER_BACKEND,
                                                    clearable=False,
                                                    searchable=False,
                                                    style={"width": "110px", "fontSize": "12px", "textAlign": "left"}
                                                ),
                                                dbc.InputGroup([
                                                    dbc.Button("查找上一个", id="global-search-prev-btn", color="secondary"),
                                                    dbc.Input(id="global-search-input", type="text", placeholder="搜索关键字...", debounce=True, list="search-suggestions"),
                                                    html.Datalist(id="search-suggestions", children=[]),
                                                    dbc.Button("查找/下一个", id="global-search-btn", color="info")
                                                ], size="sm", className="me-2", style={"maxWidth": "420px"}),
                                                html.Span("( - / - )", id="search-hit-status", className="text-muted small", style={"minWidth": "90px", "textAlign": "center"}),
                                                dbc.InputGroup([
                                                    dbc.Input(id="jump-line-input", type="number", placeholder="行号", min=1, step=1),
                                                    dbc.Button("跳转", id="jump-line-btn", color="primary")
                                                ], size="sm", style={"maxWidth": "220px"})
                                            ], className="d-flex justify-content-end align-items-center gap-2")
                                        ], width=6)
                                    ], className="w-100"),
                                ], width=12)
                                    ], style={"marginTop": "auto"})
                                ], width=12, style={"display": "flex", "flexDirection": "column", "minHeight": "calc(100vh - 230px)"})
                            ], className="mb-3"),
                        ])
                    ])
                ], width=12)
            ], className="mb-4"),
        ], style={"display": "block"}),

        # Tab-compare内容 - 日志对比
        html.Div(id="tab-compare-content", children=[
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    dcc.Dropdown(
                                        id="compare-log-file-a-selector",
                                        placeholder="选择日志A...",
                                        options=[],
                                        clearable=False,
                                        style={"fontSize": "12px", "textAlign": "left"}
                                    )
                                ], width=2),
                                dbc.Col([
                                    dcc.Dropdown(
                                        id="compare-log-file-b-selector",
                                        placeholder="选择日志B...",
                                        options=[],
                                        clearable=False,
                                        style={"fontSize": "12px", "textAlign": "left"}
                                    )
                                ], width=2),
                                dbc.Col([
                                    dcc.Dropdown(
                                        id="compare-config-group-selector",
                                        placeholder="配置文件组",
                                        style={"fontSize": "12px", "textAlign": "left"},
                                        clearable=True
                                    )
                                ], width=2),
                                dbc.Col([
                                    dbc.InputGroup([
                                        dbc.InputGroupText("忽略行首", style={"fontSize": "11px", "padding": "2px 6px"}),
                                        dbc.Input(
                                            id="compare-ignore-prefix-length",
                                            type="number",
                                            min=0,
                                            max=200,
                                            value=0,
                                            placeholder="0",
                                            style={"fontSize": "11px", "width": "50px", "padding": "2px 6px", "textAlign": "center"}
                                        ),
                                        dbc.InputGroupText("字符", style={"fontSize": "11px", "padding": "2px 6px"}),
                                        dbc.Input(
                                            id="compare-prefix-measure-input",
                                            type="text",
                                            placeholder="粘贴文本测长度",
                                            style={"fontSize": "11px", "width": "100px", "padding": "2px 6px"}
                                        ),
                                        dbc.InputGroupText(id="compare-prefix-measure-length", children="0", style={"fontSize": "11px", "padding": "2px 6px", "minWidth": "30px", "backgroundColor": "#e9ecef"})
                                    ], size="sm")
                                ], width=4, className="d-flex align-items-center"),
                                dbc.Col([
                                    dbc.Button("清除", id="compare-clear-config-selection-btn", color="danger", size="sm", className="me-2"),
                                    dbc.Button([
                                        html.Span("过滤并对比", id="compare-btn-text"),
                                        dbc.Spinner(size="sm", color="light", id="compare-loading-spinner", spinner_style={"display": "none", "marginLeft": "5px"})
                                    ], id="compare-execute-btn", color="primary", size="sm")
                                ], width=2, className="d-flex align-items-center justify-content-end")
                            ], className="mb-2"),

                            dbc.Collapse(
                                html.Div(id="compare-config-files-container", className="border rounded p-2", style={"maxHeight": "150px", "overflowY": "auto", "fontSize": "11px"}),
                                id="compare-config-files-collapse",
                                is_open=True
                            ),

                            dbc.Row([
                                dbc.Col([
                                    html.Div([
                                        html.Div("日志A", className="small text-muted"),
                                        dbc.Progress(id="compare-progress-a", value=0, striped=True, animated=True, style={"height": "8px"}),
                                        html.Div(id="compare-progress-text-a", className="small text-muted mt-1")
                                    ])
                                ], width=6),
                                dbc.Col([
                                    html.Div([
                                        html.Div("日志B", className="small text-muted"),
                                        dbc.Progress(id="compare-progress-b", value=0, striped=True, animated=True, style={"height": "8px"}),
                                        html.Div(id="compare-progress-text-b", className="small text-muted mt-1")
                                    ])
                                ], width=6)
                            ], id="compare-progress-container", className="mt-3", style={"display": "none"}),

                            html.Hr(className="my-3"),
                            html.Div([
                                html.Span(id="compare-diff-summary", className="small text-muted"),
                                html.Span([
                                    dbc.Checkbox(
                                        id="compare-sync-scroll-switch",
                                        label="同步滚动",
                                        value=True,
                                        style={"fontSize": "11px"},
                                        input_class_name="compare-sync-checkbox"
                                    )
                                ], className="ms-3"),
                            ], className="d-flex align-items-center mb-2"),
                            # Beyond Compare 风格的左右对比布局（初始等待状态）
                            html.Div([
                                html.Div([
                                    html.Div([
                                        html.Div([
                                            html.Strong("日志A", className="me-2")
                                        ], style={"flex": "1", "padding": "8px 12px", "backgroundColor": "#e9ecef", "borderRight": "1px solid #dee2e6", "fontFamily": "sans-serif"}),
                                        html.Div([
                                            html.Strong("日志B", className="me-2")
                                        ], style={"flex": "1", "padding": "8px 12px", "backgroundColor": "#e9ecef", "fontFamily": "sans-serif"})
                                    ], style={"display": "flex", "borderBottom": "2px solid #dee2e6"}),
                                    html.Div([
                                        html.Div("请选择日志文件并点击「过滤并对比」", style={"flex": "1", "padding": "40px 20px", "textAlign": "center", "color": "#999", "borderRight": "2px solid #dee2e6"}),
                                        html.Div("请选择日志文件并点击「过滤并对比」", style={"flex": "1", "padding": "40px 20px", "textAlign": "center", "color": "#999"})
                                    ], style={"display": "flex", "minHeight": "200px"})
                                ], style={"border": "1px solid #dee2e6", "borderRadius": "5px", "overflow": "hidden"})
                            ], id="compare-diff-results")
                        ])
                    ])
                ], width=12)
            ])
        ], style={"display": "none"}),

        html.Div(id="tab-ai-keywords-content", children=[
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("AI 自动生成关键字组", className="mb-0")),
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("free-code 工作目录/源码根目录:"),
                                    dbc.Input(id="ai-keyword-data-path-input", type="text", value=FREE_CODE_DEFAULT_CWD, placeholder="指定到可分析代码的源码根目录，例如 /home/user/project")
                                ], width=9),
                                dbc.Col([
                                    dbc.Label("操作:", className="d-block"),
                                    dbc.Button("讨论功能逻辑路径", id="ai-keyword-analyze-path-btn", color="primary", className="w-100")
                                ], width=3)
                            ], className="g-2 mb-3"),
                            dbc.Modal([
                                dbc.ModalHeader(dbc.ModalTitle("和 AI 讨论并生成关键字配置")),
                                dbc.ModalBody([
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Button("分析", id="ai-keyword-path-chat-auto-btn", color="primary", size="sm", className="me-2"),
                                            dbc.Button("修改默认提示词", id="ai-keyword-path-prompt-toggle-btn", color="secondary", outline=True, size="sm")
                                        ], width=12)
                                    ], className="mb-2"),
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Input(id="ai-keyword-target-analysis-input", type="text", placeholder="输入已有日志打印、tag、函数名、状态名或错误码等")
                                        ], width=9),
                                        dbc.Col([
                                            dbc.Button("针对性分析", id="ai-keyword-target-analysis-btn", color="info", size="sm", className="w-100")
                                        ], width=3)
                                    ], className="g-2 mb-2"),
                                    dbc.Collapse(
                                        html.Div([
                                            dbc.Label("通用分析默认提示词:", className="small fw-bold"),
                                            dbc.Textarea(id="ai-keyword-path-default-prompt-input", value=AI_KEYWORD_DEFAULT_PATH_DISCUSSION_PROMPT, style={"height": "160px"}),
                                            dbc.Label("针对性分析默认提示词:", className="small fw-bold mt-2"),
                                            dbc.Textarea(id="ai-keyword-target-default-prompt-input", value=AI_KEYWORD_DEFAULT_TARGET_ANALYSIS_PROMPT, style={"height": "180px"})
                                        ]),
                                        id="ai-keyword-path-prompt-collapse",
                                        is_open=False,
                                        className="mb-3"
                                    ),
                                    html.Div(id="ai-keyword-path-chat-container", className="border rounded p-2 mb-3", style={"height": "420px", "overflowY": "auto", "backgroundColor": "#fff"}),
                                    dbc.Textarea(id="ai-keyword-path-chat-input", placeholder="描述你想分析的功能、模块、日志场景，或继续追问...", style={"height": "90px"}),
                                    html.Div(id="ai-keyword-status", className="small text-muted mt-2")
                                ]),
                                dbc.ModalFooter([
                                    dbc.Button("发送", id="ai-keyword-path-chat-send-btn", color="primary", className="me-2"),
                                    dbc.Button("生成配置文件", id="ai-keyword-path-chat-generate-btn", color="success", className="me-2"),
                                    dbc.Button("关闭", id="ai-keyword-path-chat-close-btn", color="secondary")
                                ])
                            ], id="ai-keyword-path-chat-modal", is_open=False, size="xl", backdrop="static")
                            ,
                            html.Hr(),
                            html.H5("AI 生成的关键字配置审核", className="mb-3"),
                            html.Div(id="ai-keyword-generated-config-summary", className="small text-muted mb-2"),
                            html.Div(id="ai-keyword-generated-config-container", className="border rounded p-2 mb-3", style={"maxHeight": "420px", "overflowY": "auto"}),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("关键字组名:"),
                                    dbc.Input(id="ai-keyword-review-group-name-input", type="text", placeholder="AI 生成后自动填入")
                                ], width=4),
                                dbc.Col([
                                    dbc.Label("配置文件名（不含 .json）:"),
                                    dbc.Input(id="ai-keyword-review-config-name-input", type="text", placeholder="AI 生成后自动填入")
                                ], width=4),
                                dbc.Col([
                                    dbc.Label("保存:", className="d-block"),
                                    dbc.Button("保存勾选关键字到配置文件", id="ai-keyword-review-save-btn", color="primary", className="w-100")
                                ], width=4)
                            ], className="g-2")
                        ])
                    ])
                ], width=12)
            ])
        ], style={"display": "none"}),
        
        # Tab2内容 - 配置管理
        html.Div(id="tab-2-content", children=[
            # 关键字管理控件
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.Button(
                                [html.I(className="bi bi-chevron-down me-2"), "关键字管理"],
                                id="keyword-management-toggle",
                                className="btn btn-link text-decoration-none w-100 text-start"
                            )
                        ]),
                        dbc.Collapse(
                            dbc.CardBody([
                                # 添加字符串部分
                                html.H5("添加新字符串", className="mb-3"),
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Label("字符串内容:"),
                                        dbc.Textarea(id="keyword-input-string", placeholder="输入要分类的字符串...", style={"height": "30px"})
                                    ], width=12, className="mb-3"),
                                    dbc.Col([
                                        dbc.Label("分类:"),
                                        dbc.Input(
                                            id="keyword-input-category",
                                            placeholder="输入分类名称...",
                                            type="text",
                                            list="keyword-category-suggestions"
                                        ),
                                        html.Datalist(
                                            id="keyword-category-suggestions",
                                            children=[]
                                        )
                                    ], width=12, className="mb-3"),
                                    dbc.Col([
                                        dbc.Button("添加字符串", id="keyword-add-string-btn", color="primary", className="w-100")
                                    ], width=12)
                                ], className="mb-4 p-3 border rounded"),
                                
                                # 管理现有字符串部分
                                html.H5("管理现有字符串", className="mb-3"),
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Label("选择分类:"),
                                        dcc.Dropdown(
                                            id="keyword-category-filter",
                                            placeholder="选择分类查看字符串...",
                                            clearable=True
                                        )
                                    ], width=12, className="mb-3"),
                                    dbc.Col([
                                        html.Div(id="keyword-strings-container", className="border rounded p-3", style={"maxHeight": "300px", "overflowY": "auto"})
                                    ], width=12)
                                ], className="mb-4 p-3 border rounded")
                            ]),
                            id="keyword-management-collapse",
                            is_open=True
                        )
                    ])
                ], width=12)
            ], className="mb-4"),
            

            # 配置文件管理选项
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.Button(
                                [html.I(className="bi bi-chevron-down me-2"), "配置文件管理"],
                                id="config-management-toggle",
                                className="btn btn-link text-decoration-none w-100 text-start"
                            )
                        ]),
                        dbc.Collapse(
                            dbc.CardBody([
                                # 选中的字符串和已保存的字符串区域（并排布局）
                                dbc.Row([
                                    # 左侧：选中的字符串
                                    dbc.Col([
                                        html.H4("选中的字符串", className="card-title"),
                                        dbc.Button("清除选择", id={"type": "clear-selection-btn", "index": "main"}, color="danger", size="sm", className="mb-2"),
                                        html.Div(id="selected-strings-container", style={"maxHeight": "calc(100vh - 250px)", "overflowY": "auto", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px"})
                                    ], width=6),
                                    
                                    # 右侧：已保存的字符串
                                    dbc.Col([
                                        html.H4("已保存的字符串", className="card-title"),
                                        dbc.Row([
                                            dbc.Col([
                                                dcc.Dropdown(
                                                    id="category-filter",
                                                    options=[{"label": "所有分类", "value": "all"}] + 
                                                            [{"label": cat, "value": cat} for cat in data["categories"].keys()],
                                                    value="all",
                                                    clearable=False,
                                                    placeholder="选择分类"
                                                ),
                                            ], width=12),
                                        ], className="mb-2"),
                                        html.Div(className="mt-2 mb-2", children=[
                                            dbc.Label("字符串类型:", className="me-2"),
                                            dbc.RadioItems(
                                                id="string-type-radio",
                                                options=[
                                                    {"label": "保留字符串", "value": "keep"},
                                                    {"label": "过滤字符串", "value": "filter"}
                                                ],
                                                value="keep",
                                                inline=True
                                            )
                                        ]),
                                        html.Div(id="saved-strings-container", style={"maxHeight": "400px", "overflowY": "auto", "marginTop": "10px", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px"}),
                                        html.Div(id="duplicate-strings-container", className="mt-3")
                                    ], width=6)
                                ]),
                                
                                # 保存至配置文件功能区域
                                html.Hr(),
                                html.H4("保存至配置文件", className="mt-4 mb-3"),
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Label("配置名称:"),
                                        dbc.Input(
                                            id="config-name-input",
                                            type="text",
                                            placeholder="输入配置文件名（不含.json后缀）",
                                            className="mb-2"
                                        )
                                    ], width=3),
                                    dbc.Col([
                                        dbc.Label("选择配置文件:"),
                                        dcc.Dropdown(
                                            id="config-file-selector",
                                            placeholder="选择要加载或删除的配置文件...",
                                            clearable=True
                                        )
                                    ], width=3),
                                    dbc.Col([
                                        dbc.Label("操作:", className="d-block"),
                                        dbc.Button("保存配置", id="save-config-btn", color="primary", className="w-100 mb-2"),
                                        dbc.Button("加载配置", id="load-config-btn", color="success", className="w-100 mb-2")
                                    ], width=3),
                                    dbc.Col([
                                        dbc.Label("管理:", className="d-block"),
                                        dbc.Button("删除配置", id="delete-config-btn", color="danger", className="w-100")
                                    ], width=3)
                                ], className="mt-3")
                            ]),
                            id="config-management-collapse",
                            is_open=True
                        )
                    ])
                ], width=12)
            ], className="mb-4"),
            
            # 配置文件组管理选项
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.Button(
                                [html.I(className="bi bi-chevron-down me-2"), "配置文件组管理"],
                                id="config-groups-management-toggle",
                                className="btn btn-link text-decoration-none w-100 text-start"
                            )
                        ]),
                        dbc.Collapse(
                            dbc.CardBody([
                                # 配置文件组选择和配置文件多选
                                dbc.Row([
                                    # 可用的配置文件（多选）
                                    dbc.Col([
                                        html.H4("可用的配置文件", className="card-title"),
                                        html.Div(id="available-configs-for-group", className="border rounded p-2 d-flex flex-wrap gap-2", style={"maxHeight": "300px", "overflowY": "auto"})
                                    ], width=12)
                                ]),
                                
                                # 创建/管理配置文件组
                                html.Hr(),
                                html.H4("创建/管理配置文件组", className="mt-4 mb-3"),
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Label("配置文件组名称:"),
                                        dbc.Input(
                                            id="config-group-name-input",
                                            type="text",
                                            placeholder="输入配置文件组名称",
                                            className="mb-2"
                                        )
                                    ], width=3),
                                    dbc.Col([
                                        dbc.Label("选择配置文件组:"),
                                        dcc.Dropdown(
                                            id="config-group-selector",
                                            placeholder="选择要加载或删除的配置文件组...",
                                            clearable=True
                                        )
                                    ], width=3),
                                    dbc.Col([
                                        dbc.Label("操作:", className="d-block"),
                                        dbc.Button("保存组", id="save-config-group-btn", color="primary", className="w-100 mb-2"),
                                        dbc.Button("加载组", id="load-config-group-btn", color="success", className="w-100 mb-2")
                                    ], width=3),
                                    dbc.Col([
                                        dbc.Label("管理:", className="d-block"),
                                        dbc.Button("删除组", id="delete-config-group-btn", color="danger", className="w-100")
                                    ], width=3)
                                ], className="mt-3")
                            ]),
                            id="config-groups-management-collapse",
                            is_open=True
                        )
                    ])
                ], width=12)
            ], className="mb-4"),


        ], style={"display": "none"}),
        
        # Tab4内容 - 关键字注释
        html.Div(id="tab-4-content", children=[
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H5("关键字注释", className="mb-0")
                        ]),
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("关键字:"),
                                    dbc.Input(
                                        id="annotation-keyword-input",
                                        type="text",
                                        placeholder="输入关键字..."
                                    )
                                ], width=4),
                                dbc.Col([
                                    dbc.Label("注释内容:"),
                                    dbc.Input(
                                        id="annotation-text-input",
                                        type="text",
                                        placeholder="为该关键字添加注释..."
                                    )
                                ], width=6),
                                dbc.Col([
                                    dbc.Label("操作:", className="d-block"),
                                    dbc.Button("保存注释", id="annotation-save-btn", color="primary", className="w-100 mb-2")
                                ], width=2)
                            ], className="mt-2"),
                            dbc.Row([
                                dbc.Col([
                                    html.Div(id="keyword-annotations-list", className="border rounded p-3 mt-3", style={"maxHeight": "300px", "overflowY": "auto"})
                                ], width=12)
                            ]),

                            html.Hr(className="mt-4 mb-4"),

                            html.H5("流程关键字设置", className="mb-3"),

                            # 配对流程设置
                            dbc.Row([
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardHeader([html.Span("配对关键字（起始/结束）")]),
                                        dbc.CardBody([
                                            dbc.Row([
                                                dbc.Col([
                                                    dbc.Label("流程名称:"),
                                                    dbc.Input(id="paired-name", type="text", placeholder="如: 播放流程")
                                                ], width=3),
                                                dbc.Col([
                                                    dbc.Label("开始关键字:"),
                                                    dbc.Input(id="paired-start", type="text", placeholder="如: StartPlayback")
                                                ], width=4),
                                                dbc.Col([
                                                    dbc.Label("结束关键字:"),
                                                    dbc.Input(id="paired-end", type="text", placeholder="如: StopPlayback")
                                                ], width=4),
                                                dbc.Col([
                                                    dbc.Label("操作:", className="d-block"),
                                                    dbc.Button("添加", id="paired-add-btn", color="primary", className="w-100")
                                                ], width=1)
                                            ], className="g-2"),
                                            html.Div(id="paired-list-container", className="border rounded p-3 mt-3", style={"maxHeight": "240px", "overflowY": "auto"})
                                        ])
                                    ])
                                ], width=12)
                            ], className="mb-4"),

                            # 序列流程设置
                            dbc.Row([
                                dbc.Col([
                                    dbc.Card([
                                        dbc.CardHeader([html.Span("序列关键字（1 -> 2 -> 3）")]),
                                        dbc.CardBody([
                                            dbc.Row([
                                                dbc.Col([
                                                    dbc.Label("流程名称:"),
                                                    dbc.Input(id="seq-name", type="text", placeholder="如: 开机流程")
                                                ], width=3),
                                                dbc.Col([
                                                    dbc.Label("步骤（使用 -> 或 换行 分隔）:"),
                                                    dbc.Textarea(id="seq-steps-text", placeholder="步骤1 -> 步骤2 -> 步骤3\n或每行一个步骤", style={"height": "80px"})
                                                ], width=8),
                                                dbc.Col([
                                                    dbc.Label("操作:", className="d-block"),
                                                    dbc.Button("添加", id="seq-add-btn", color="success", className="w-100")
                                                ], width=1)
                                            ], className="g-2"),
                                            html.Div(id="sequences-list-container", className="border rounded p-3 mt-3", style={"maxHeight": "240px", "overflowY": "auto"})
                                        ])
                                    ])
                                ], width=12)
                            ]),

                            html.Hr(className="mt-4 mb-4"),

                            # 正则生成器
                            dbc.Card([
                                dbc.CardHeader([html.Span("正则生成器")]),
                                dbc.CardBody([
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Label("输入关键字（空格或换行分隔）:"),
                                            dbc.Textarea(id="regex-input-keywords", placeholder="例如: STB_CINotifyPinEvent slot program", style={"height": "80px"})
                                        ], width=12)
                                    ], className="mb-2"),
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Label("生成模式:"),
                                            dbc.RadioItems(
                                                id="regex-mode",
                                                options=[
                                                    {"label": "同时包含（lookahead）", "value": "and_lookahead"},
                                                    {"label": "任一包含（OR）", "value": "or"},
                                                    {"label": "按顺序包含（token1.*token2.*…）", "value": "ordered_lookahead"}
                                                ],
                                                value="and_lookahead",
                                                inline=True
                                            )
                                        ], width=12)
                                    ], className="mb-2"),
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Checklist(
                                                id="regex-options",
                                                options=[
                                                    {"label": "添加 re: 前缀", "value": "prefix"},
                                                    {"label": "对关键字进行转义", "value": "escape"}
                                                ],
                                                value=["escape"],
                                                inline=True
                                            )
                                        ], width=12)
                                    ], className="mb-2"),
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Button("生成", id="regex-generate-btn", color="primary")
                                        ], width="auto"),
                                        dbc.Col([
                                            dbc.Input(id="regex-output", type="text", readonly=True, placeholder="生成的正则将在此显示")
                                        ], width=True)
                                    ])
                                ])
                            ])
                        ])
                    ])
                ], width=12)
            ], className="mb-4")
        ], style={"display": "none"}),
        
        # Tab3内容 - 日志管理
        html.Div(id="tab-3-content", children=[
            dbc.Container([
                dbc.Row([
                    dbc.Col([
                        html.H4("日志管理", className="mb-4"),
                    ])
                ]),
                
                # 文件上传区域
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader([
                                html.Div([
                                    html.I(className="bi bi-cloud-upload me-2"),
                                    html.Span("日志文件上传")
                                ], className="d-flex align-items-center")
                            ]),
                            dbc.CardBody([
                                dcc.Upload(
                                    id='upload-log-file',
                                    children=html.Div([
                                        html.I(className="bi bi-upload me-2", style={"fontSize": "1.5rem"}),
                                        html.Span('拖拽日志/压缩包到此处或点击选择文件', className="fw-bold"),
                                        html.Small('支持 .txt/.log/.text、.zip/.tar/.7z；文件夹请直接拖入应用窗口', className="text-muted mt-2")
                                    ], className="d-flex flex-column align-items-center justify-content-center"),
                                    style={
                                        'width': '100%',
                                        'height': '120px',
                                        'lineHeight': '60px',
                                        'borderWidth': '2px',
                                        'borderStyle': 'dashed',
                                        'borderRadius': '10px',
                                        'textAlign': 'center',
                                        'cursor': 'pointer',
                                        'borderColor': '#dee2e6',
                                        'backgroundColor': '#f8f9fa',
                                        'transition': 'all 0.3s'
                                    },
                                    className="upload-area mb-3",
                                    multiple=True,
                                    accept='.txt,.log,.text,.zip,.tar,.tgz,.tar.gz,.tar.bz2,.tbz2,.tar.xz,.txz,.7z'
                                ),
                                html.Div(id='upload-status', className="text-center small")
                            ])
                        ], className="mb-4 shadow-sm")
                    ], width=12)
                ]),

                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader([
                                html.Div([
                                    html.I(className="bi bi-folder-plus me-2"),
                                    html.Span("日志目录")
                                ], className="d-flex align-items-center")
                            ]),
                            dbc.CardBody([
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Label("新建目录:"),
                                        dbc.Input(
                                            id="new-log-dir-input",
                                            type="text",
                                            placeholder="例如: board_a/issue_20260520"
                                        )
                                    ], width=8),
                                    dbc.Col([
                                        dbc.Label("操作:", className="d-block invisible"),
                                        dbc.Button("创建目录", id="create-log-dir-btn", color="primary", className="w-100")
                                    ], width=2),
                                    dbc.Col([
                                        dbc.Label("状态:", className="d-block invisible"),
                                        html.Div(id="create-log-dir-status", className="mt-2")
                                    ], width=2)
                                ])
                            ])
                        ], className="mb-4 shadow-sm")
                    ], width=12)
                ]),

                # 外部程序配置区域
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader([
                                html.Div([
                                    html.I(className="bi bi-gear me-2"),
                                    html.Span("外部程序设置")
                                ], className="d-flex align-items-center")
                            ]),
                            dbc.CardBody([
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Label("外部程序路径:"),
                                        dbc.Input(
                                            id="external-program-path-input",
                                            type="text",
                                            placeholder="输入外部程序绝对路径 (例如: /usr/bin/vim 或 C:\\Windows\\notepad.exe)",
                                            value=ext_prog_config.get("path", "")
                                        )
                                    ], width=8),
                                    dbc.Col([
                                        dbc.Label("操作:", className="d-block invisible"),
                                        dbc.Button("保存配置", id="save-external-program-btn", color="primary", className="w-100")
                                    ], width=2),
                                    dbc.Col([
                                        dbc.Label("状态:", className="d-block invisible"),
                                        html.Div(id="external-program-save-status", className="mt-2")
                                    ], width=2)
                                ])
                            ])
                        ], className="mb-4 shadow-sm")
                    ], width=12)
                ]),

                # 文件列表区域
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader([
                                html.Div([
                                    html.I(className="bi bi-list-ul me-2"),
                                    html.Span("已上传的文件")
                                ], className="d-flex align-items-center")
                            ]),
                            dbc.CardBody([
                                html.Div(id='uploaded-files-list', className="table-responsive")
                            ], className="p-0")
                        ], className="shadow-sm")
                    ], width=12)
                ])
            ], fluid=True, className="p-0")
        ], style={"display": "none"}),
        
        # 抽屉组件 - 移到主布局中，确保所有tab都能访问
        dbc.Offcanvas(
            [
                html.H4("字符串管理", className="mt-3 mb-4"),
                
                # 添加字符串部分
                html.H5("添加新字符串", className="mb-3"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("字符串内容:"),
                        dbc.Textarea(id="input-string", placeholder="输入要分类的字符串...", style={"height": "30px"})
                    ], width=12, className="mb-3"),
                    dbc.Col([
                        dbc.Label("分类:"),
                        dbc.Input(
                            id="input-category",
                            placeholder="输入分类名称...",
                            type="text",
                            list="category-suggestions"
                        ),
                        html.Datalist(
                            id="category-suggestions",
                            children=[]
                        )
                    ], width=12, className="mb-3"),
                    dbc.Col([
                        dbc.Button("添加字符串", id="add-string-btn", color="primary", className="w-100")
                    ], width=12)
                ], className="mb-4 p-3 border rounded"),
                
                # 管理现有字符串部分
                html.H5("管理现有字符串", className="mb-3"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("选择分类:"),
                        dcc.Dropdown(
                            id="drawer-category-filter",
                            placeholder="选择分类查看字符串...",
                            clearable=True
                        )
                    ], width=12, className="mb-3"),
                    dbc.Col([
                        html.Div(id="drawer-strings-container", className="border rounded p-3", style={"maxHeight": "300px", "overflowY": "auto"})
                    ], width=12)
                ], className="mb-4 p-3 border rounded")
            ],
            id="keyword-drawer",
            placement="end",
            is_open=False,
            style={"width": "66.67%"}
        ),
        
        # 存储组件 - 移到主布局中，确保所有tab都能访问
        html.Div(id="filter-backend-display", style={"display": "none"}),
        dcc.Store(id='data-store', data=load_data()),
        dcc.Store(id='filtered-result-store', data=''),
        dcc.Store(id='source-result-store', data=''),
        dcc.Store(id='selected-strings', data=[]),
        dcc.Store(id='filter-tab-strings-store', data=[]),  # 日志过滤tab专用的字符串存储
        dcc.Store(id='compare-tab-strings-store', data=[]),
        dcc.Store(id='selected-log-file', data=''),
        dcc.Store(id='string-type-store', data='keep'),  # 存储字符串类型选择，默认为"keep"
        dcc.Store(id='selected-config-files', data=[]),  # 存储选中的配置文件列表（支持多选）
        dcc.Store(id='compare-selected-config-files', data=[]),
        dcc.Store(id='temp-keywords-store', data=load_temp_keywords_from_file()),  # 存储临时关键字列表（支持保留/屏蔽）
        dcc.Store(id='keyword-annotations-store', data=load_annotations()),  # 存储关键字注释映射
        dcc.Store(id='flows-config-store', data=load_flows_config()),  # 存储流程关键字配置
        dcc.Store(id='rename-target-file', data=''),  # 存储待重命名的文件
        dcc.Store(id='rename-target-kind', data='file'),  # file / dir

        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("选择日志文件"), close_button=True),
                dbc.ModalBody(
                    html.Div(id="log-picker-browser", className="log-picker-browser"),
                    style={"maxHeight": "72vh", "overflowY": "auto", "backgroundColor": "#f8fafc"}
                ),
                dbc.ModalFooter(
                    dbc.Button("关闭", id="close-log-picker-btn", color="secondary", outline=True, className="ms-auto")
                ),
            ],
            id="log-picker-modal",
            is_open=False,
            size="xl",
            centered=True,
        ),
        
        # 重命名文件模态框
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("重命名文件")),
                dbc.ModalBody(
                    [
                        dbc.Label("新文件名:"),
                        dbc.Input(id="rename-file-input", type="text"),
                    ]
                ),
                dbc.ModalFooter(
                    [
                        dbc.Button("取消", id="rename-file-cancel-btn", className="ms-auto", outline=True),
                        dbc.Button("确认", id="rename-file-confirm-btn", color="primary", className="ms-2"),
                    ]
                ),
            ],
            id="rename-file-modal",
            is_open=False,
        ),
        
    ], fluid=True),
    # 浮动 Chat 窗口 — DeepSeek 对话风格
    html.Div([
        # 标题栏
        html.Div([
            html.Div([
                html.Span("✦", className="chat-win-logo"),
                html.Span("AI Chat", className="chat-win-title-text"),
            ], className="chat-win-title-group"),
            html.Div([
                html.Button("—", id="chat-win-minimize-btn", className="chat-win-btn", n_clicks=0),
                html.Button("✕", id="chat-win-close-btn", className="chat-win-btn", n_clicks=0),
            ], className="chat-win-btns")
        ], id="chat-win-header", className="chat-win-header"),
        # 对话消息区
        html.Div(id="log-chat-results", className="chat-win-body", children=[
            html.Div([
                html.Div([
                    html.Span("✦", className="chat-msg-avatar chat-msg-avatar-ai"),
                    html.Span("AI", className="chat-msg-name"),
                ], className="chat-msg-header"),
                html.Div("你好！选中日志文本后点击 Chat，我会帮你分析问题。", className="chat-msg-bubble chat-msg-bubble-ai"),
            ], className="chat-msg chat-msg-ai")
        ]),
        # 输入区
        html.Div([
            html.Div([
                dcc.Input(
                    id="chat-cwd-input",
                    className="chat-cwd-input",
                    type="text",
                    placeholder="设置 free-code 工作目录，例如 /Users/surfing/tools/log_filter",
                ),
                html.Button("应用", id="chat-cwd-apply-btn", className="chat-cwd-btn", n_clicks=0),
            ], className="chat-cwd-row"),
            html.Div(id="chat-attachments", className="chat-attachments"),
            html.Div([
                html.Textarea(id="chat-input", className="chat-input", placeholder="输入消息，Shift+Enter 换行...", rows=1),
                html.Button("↑", id="chat-send-btn", className="chat-send-btn", n_clicks=0),
            ], className="chat-input-row"),
            html.Div("就绪，可直接和 free-code 对话", id="chat-status", className="chat-status"),
        ], className="chat-input-area"),
        html.Div(className="chat-win-resize-handle", id="chat-win-resize-handle"),
    ], id="chat-win", className="chat-win chat-win-hidden"),
    # 浮动 Chat 打开按钮（窗口关闭后显示）
    html.Button("AI", id="chat-win-open-btn", className="chat-win-fab", n_clicks=0)
])

# 初始化数据存储
@app.callback(
    Output("data-store", "data", allow_duplicate=True),
    [Input("main-tabs", "active_tab")],
    prevent_initial_call="initial_duplicate"
)
def initialize_data_store(active_tab):
    # 当页面加载或tab切换时初始化数据
    if active_tab:
        return load_data()
    return dash.no_update

# 单向同步：从string-type-radio更新到string-type-store
@app.callback(
    Output("string-type-store", "data"),
    [Input("string-type-radio", "value")],
    prevent_initial_call=True
)
def sync_string_type_to_store(radio_value):
    # 当radio值改变时，更新store
    if radio_value:
        return radio_value
    return dash.no_update

# 当切换到tab-2时，从store恢复radio的值
@app.callback(
    Output("string-type-radio", "value"),
    [Input("main-tabs", "active_tab")],
    [State("string-type-store", "data")],
    prevent_initial_call=True
)
def restore_string_type_from_store(active_tab, store_value):
    # 只在切换到tab-2时，从store恢复radio的值
    if active_tab == "tab-2" and store_value:
        return store_value
    return dash.no_update


# 页面加载时自动恢复之前的选择
@app.callback(
    Output("log-file-selector", "value"),
    [Input("data-store", "data"),
     Input("main-tabs", "active_tab")],  # 添加tab切换作为触发
    [State("log-file-selector", "options")],
    prevent_initial_call='initial_duplicate'  # 允许初始调用
)
def restore_previous_selections(data_store_data, active_tab, log_file_options):
    # 用户要求去掉启动时自动恢复，直接返回不更新
    return dash.no_update

# 页面加载时恢复字符串选择
@app.callback(
    Output("selected-strings", "data", allow_duplicate=True),
    [Input("selected-log-file", "data"),
     Input("main-tabs", "active_tab"),
     Input("data-store", "data")],  # 添加数据存储作为输入
    prevent_initial_call='initial_duplicate'  # 使用特殊值允许初始调用和重复输出
)
def restore_string_selections(selected_log_file, active_tab, data_store_data):
    # 用户要求去掉启动时自动恢复，直接返回不更新
    return dash.no_update

# 页面加载时恢复配置文件选择
@app.callback(
    Output("selected-config-files", "data", allow_duplicate=True),
    [Input("data-store", "data"),
     Input("main-tabs", "active_tab")],
    prevent_initial_call='initial_duplicate'  # 使用特殊值允许初始调用和重复输出
)
def restore_config_selections(data_store_data, active_tab):
    # 用户要求去掉启动时自动恢复，直接返回不更新
    return dash.no_update

@app.callback(
    [Output("selected-log-file-display", "children"),
     Output("selected-log-file-display", "title")],
    [Input("log-file-selector", "value")]
)
def render_selected_log_file_display(selected_log_file):
    if not selected_log_file:
        return "FILE: 未选择日志", ""
    return f"FILE: {selected_log_file}", selected_log_file

@app.callback(
    [Output("log-picker-modal", "is_open", allow_duplicate=True),
     Output("log-picker-current-dir-store", "data", allow_duplicate=True),
     Output("log-picker-browser", "children", allow_duplicate=True)],
    [Input("open-log-picker-btn", "n_clicks")],
    [State("log-file-selector", "value")],
    prevent_initial_call=True
)
def open_log_picker(n_clicks, selected_log_file):
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update
    current_dir = ""
    if selected_log_file:
        try:
            selected_log_file = _normalize_log_filename(selected_log_file)
            current_dir = os.path.dirname(selected_log_file).replace("\\", "/")
            if current_dir == ".":
                current_dir = ""
        except Exception:
            current_dir = ""
    log_files = get_log_files()
    return True, current_dir, _create_log_picker_browser(log_files, current_dir, selected_log_file)

@app.callback(
    Output("log-picker-modal", "is_open", allow_duplicate=True),
    [Input("close-log-picker-btn", "n_clicks")],
    prevent_initial_call=True
)
def close_log_picker(n_clicks):
    if n_clicks:
        return False
    return dash.no_update

@app.callback(
    [Output("log-picker-current-dir-store", "data"),
     Output("log-picker-browser", "children")],
    [Input({"type": "log-picker-enter-dir-btn", "index": ALL}, "n_clicks"),
     Input("log-picker-up-btn", "n_clicks"),
     Input("log-picker-root-btn", "n_clicks")],
    [State("log-picker-current-dir-store", "data"),
     State("log-file-selector", "value")],
    prevent_initial_call=True
)
def navigate_log_picker(enter_clicks, up_clicks, root_clicks, current_dir, selected_log_file):
    ctx = callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update

    trigger = ctx.triggered[0]
    if not trigger.get("value"):
        return dash.no_update, dash.no_update

    target_dir = current_dir or ""
    trigger_id = trigger["prop_id"].rsplit(".", 1)[0]
    try:
        if trigger_id == "log-picker-up-btn":
            target_dir = _parent_log_manager_dir(current_dir)
        elif trigger_id == "log-picker-root-btn":
            target_dir = ""
        else:
            target_dir = _normalize_log_manager_dir(json.loads(trigger_id)["index"])
    except Exception:
        target_dir = ""

    log_files = get_log_files()
    return target_dir, _create_log_picker_browser(log_files, target_dir, selected_log_file)

@app.callback(
    [Output("log-file-selector", "value", allow_duplicate=True),
     Output("log-picker-modal", "is_open", allow_duplicate=True)],
    [Input({"type": "log-picker-select-file-btn", "index": ALL}, "n_clicks")],
    prevent_initial_call=True
)
def select_log_from_picker(select_clicks):
    ctx = callback_context
    if not ctx.triggered or not any(select_clicks or []):
        return dash.no_update, dash.no_update
    trigger = ctx.triggered[0]
    if not trigger.get("value"):
        return dash.no_update, dash.no_update
    try:
        trigger_id = trigger["prop_id"].rsplit(".", 1)[0]
        selected_file = _normalize_log_filename(json.loads(trigger_id)["index"])
        return selected_file, False
    except Exception:
        return dash.no_update, dash.no_update

# 控制配置文件管理区域折叠/展开的回调
@app.callback(
    Output("config-management-collapse", "is_open"),
    [Input("config-management-toggle", "n_clicks")],
    [State("config-management-collapse", "is_open")],
    prevent_initial_call=True
)
def toggle_config_management(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open


# 控制配置文件区域折叠/展开的回调
@app.callback(
    Output("config-files-collapse", "is_open"),
    [Input("config-files-toggle", "n_clicks")],
    [State("config-files-collapse", "is_open")],
    prevent_initial_call=True
)
def toggle_config_files(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open


# 文件选择后，标记过滤页 UI 正在加载
@app.callback(
    Output(_UI_BUSY_STORE_ID, "data", allow_duplicate=True),
    [Input("log-file-selector", "value")],
    prevent_initial_call=True
)
def mark_ui_busy_on_file_change(selected_log_file):
    if selected_log_file:
        return _make_log_view_ui_state("loading_file")
    return _make_log_view_ui_state("idle")



# 添加字符串回调
@app.callback(
    [Output("data-store", "data"),
     Output("input-string", "value"),
     Output("input-category", "value")],
    [Input("add-string-btn", "n_clicks")],
    [State("input-string", "value"),
     State("input-category", "value"),
     State("data-store", "data")],
    prevent_initial_call=True
)
def add_string(n_clicks, input_string, input_category, data):
    if n_clicks and input_string and input_category:
        # 去除分类名称前后空格，确保唯一性
        input_category = input_category.strip()
        
        # 如果分类不存在，创建新分类
        if input_category not in data["categories"]:
            data["categories"][input_category] = []
        
        # 添加字符串到分类
        data["categories"][input_category].append(input_string)
        
        # 保存数据
        save_data(data)
        
        # 更新全局data变量
        globals()['data'] = load_data()
        
        return (
            data,
            "",  # 清空输入字符串
            input_category  # 保留分类名称
        )
    
    return data, "", ""

# 关键字管理控件的分类建议回调
@app.callback(
    Output("keyword-category-suggestions", "children"),
    [Input("data-store", "data")]
)
def update_keyword_category_suggestions(data):
    if not data or "categories" not in data:
        return []
    
    # 返回所有分类作为建议选项
    return [html.Option(value=cat) for cat in data["categories"].keys()]

# 全局搜索输入框的关键字建议回调
@app.callback(
    Output("search-suggestions", "children"),
    [Input("data-store", "data")]
)
def update_search_suggestions(data):
    keywords = get_all_keywords_from_data(data)
    return [html.Option(value=k) for k in keywords]

# 关键字管理控件的添加字符串回调
@app.callback(
    [Output("data-store", "data", allow_duplicate=True),
     Output("keyword-input-string", "value"),
     Output("keyword-input-category", "value")],
    [Input("keyword-add-string-btn", "n_clicks")],
    [State("keyword-input-string", "value"),
     State("keyword-input-category", "value"),
     State("data-store", "data")],
    prevent_initial_call=True
)
def keyword_add_string(n_clicks, input_string, input_category, data):
    if n_clicks and input_string and input_category:
        # 去除分类名称前后空格，确保唯一性
        input_category = input_category.strip()
        
        # 如果分类不存在，创建新分类
        if input_category not in data["categories"]:
            data["categories"][input_category] = []
        
        # 添加字符串到分类
        data["categories"][input_category].append(input_string)
        
        # 保存数据
        save_data(data)
        
        # 更新全局data变量
        globals()['data'] = load_data()
        
        return (
            data,
            "",  # 清空输入字符串
            input_category  # 保留分类名称
        )
    
    return dash.no_update, "", ""

# 关键字管理控件的分类选项更新回调
@app.callback(
    Output("keyword-category-filter", "options"),
    [Input("data-store", "data")]
)
def update_keyword_category_options(data):
    if not data or "categories" not in data:
        return []
    
    # 返回所有分类作为选项
    return [{"label": cat, "value": cat} for cat in data["categories"].keys()]

# 关键字管理控件的字符串显示回调
@app.callback(
    Output("keyword-strings-container", "children"),
    [Input("data-store", "data"),
     Input("keyword-category-filter", "value")]
)
def update_keyword_strings(data, selected_category):
    if not data or "categories" not in data or not selected_category:
        return html.P("请选择分类查看字符串", className="text-muted text-center")
    
    if selected_category not in data["categories"]:
        return html.P("该分类不存在", className="text-muted text-center")
    
    strings = data["categories"][selected_category]
    
    if not strings:
        return html.P("该分类中没有字符串", className="text-muted text-center")
    
    # 创建字符串按钮列表
    string_elements = []
    string_elements.append(html.P("点击字符串可直接删除", className="text-muted small mb-2"))
    
    # 使用flex布局创建紧凑的按钮显示
    string_buttons = []
    for i, string in enumerate(strings):
        string_buttons.append(
            dbc.Button(
                string, 
                id={"type": "keyword-string-btn", "index": f"{selected_category}-{i}"},
                color="danger", 
                outline=True,
                size="sm",
                className="m-1",
                style={"whiteSpace": "nowrap", "flexShrink": 0}
            )
        )
    
    # 使用d-flex和flex-wrap实现多列布局
    string_elements.append(
        html.Div(
            string_buttons,
            className="d-flex flex-wrap gap-2",
            style={"minHeight": "50px"}
        )
    )
    
    return string_elements

# 关键字管理控件的删除字符串回调
@app.callback(
    [Output("data-store", "data", allow_duplicate=True),
     Output("keyword-strings-container", "children", allow_duplicate=True),
     Output("keyword-category-filter", "options", allow_duplicate=True),
     Output("saved-strings-container", "children", allow_duplicate=True),
     Output("category-filter", "options", allow_duplicate=True)],
    [Input({"type": "keyword-string-btn", "index": dash.ALL}, "n_clicks")],
    [State({"type": "keyword-string-btn", "index": dash.ALL}, "id"),
     State("keyword-category-filter", "value"),
     State("data-store", "data")],
    prevent_initial_call=True
)
def delete_keyword_string(n_clicks, button_ids, selected_category, data):
    # 检查是否有按钮被点击
    if not any(n_clicks):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    # 找出被点击的按钮
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    # 找出被点击的按钮索引
    clicked_index = None
    for i, clicks in enumerate(n_clicks):
        if clicks is not None and clicks > 0:
            clicked_index = i
            break
    
    if clicked_index is None:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    # 获取被点击按钮的ID
    button_id = button_ids[clicked_index]
    if "index" not in button_id:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    # 解析按钮ID获取分类和索引
    try:
        category_index = button_id["index"].split("-")
        if len(category_index) != 2:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        
        category = category_index[0]
        index = int(category_index[1])
        
        # 删除字符串
        if category in data["categories"] and 0 <= index < len(data["categories"][category]):
            data["categories"][category].pop(index)
            
            # 如果分类为空，删除该分类
            if not data["categories"][category]:
                del data["categories"][category]
            
            # 保存数据
            save_data(data)
            
            # 更新全局data变量
            globals()['data'] = load_data()
            
            # 更新关键字管理控件中的字符串显示
            if selected_category in data["categories"] and data["categories"][selected_category]:
                strings = data["categories"][selected_category]
                string_elements = []
                string_elements.append(html.P("点击字符串可直接删除", className="text-muted small mb-2"))
                
                # 使用flex布局创建紧凑的按钮显示
                string_buttons = []
                for i, string in enumerate(strings):
                    string_buttons.append(
                        dbc.Button(
                            string, 
                            id={"type": "keyword-string-btn", "index": f"{selected_category}-{i}"},
                            color="danger", 
                            outline=True,
                            size="sm",
                            className="m-1",
                            style={"whiteSpace": "nowrap", "flexShrink": 0}
                        )
                    )
                
                # 使用d-flex和flex-wrap实现多列布局
                string_elements.append(
                    html.Div(
                        string_buttons,
                        className="d-flex flex-wrap gap-2",
                        style={"minHeight": "50px"}
                    )
                )
            else:
                # 如果分类被删除或为空，显示提示信息
                string_elements = html.P("该分类中没有字符串", className="text-muted text-center")
            
            # 更新分类选项
            category_options = [{"label": cat, "value": cat} for cat in data["categories"].keys() if data["categories"][cat]]
            
            # 更新主页面中的已保存字符串显示
            main_string_elements = []
            for category, strings in data["categories"].items():
                if strings:  # 只显示非空分类
                    main_string_elements.append(html.H6(category, className="mt-3 mb-2"))
                    
                    # 创建一个包含所有按钮的容器，使用d-flex和flex-wrap确保多列显示
                    button_container = html.Div(
                        className="d-flex flex-wrap gap-2",
                        children=[
                            dbc.Button(
                                string,
                                id={"type": "select-string-btn", "index": f"{category}-{i}"},
                                color="success",  # 默认颜色
                                outline=True,
                                size="sm",
                                style={"whiteSpace": "nowrap", "flexShrink": 0}
                            ) for i, string in enumerate(strings)
                        ]
                    )
                    main_string_elements.append(button_container)
            
            if not main_string_elements:
                main_string_elements = [html.P("没有找到字符串", className="text-muted")]
            
            # 更新配置文件管理中的分类选项
            config_category_options = [{"label": "所有分类", "value": "all"}] + \
                                     [{"label": cat, "value": cat} for cat in data["categories"].keys()]
            
            return data, string_elements, category_options, main_string_elements, config_category_options
        
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    except Exception as e:
        print(f"删除字符串时出错: {e}")
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

# 更新已保存字符串显示
@app.callback(
    [Output("saved-strings-container", "children"),
     Output("category-filter", "options"),
     Output("duplicate-strings-container", "children")],
    [Input("data-store", "data"),
     Input("category-filter", "value"),
     Input("string-type-store", "data"),  # 使用store代替radio
     Input("selected-strings", "data")],  # 添加selected-strings作为输入
    [State("main-tabs", "active_tab")],  # 将active_tab改为State，避免tab切换触发回调
    prevent_initial_call=True
)
def update_saved_strings(data, selected_category, string_type, selected_strings, active_tab):
    # 只有在配置管理tab激活时才处理回调
    if active_tab != "tab-2":
        return dash.no_update, dash.no_update, dash.no_update
    
    if not data or "categories" not in data:
        return [], [{"label": "所有分类", "value": "all"}], []
    
    # 更新分类选项
    category_options = [{"label": "所有分类", "value": "all"}] + \
                      [{"label": cat, "value": cat} for cat in data["categories"].keys()]
    
    # 计算重复关键字
    string_counts = {}
    for cat, strings in data["categories"].items():
        for s in strings:
            if s in string_counts:
                string_counts[s].append(cat)
            else:
                string_counts[s] = [cat]
    
    duplicates = {s: cats for s, cats in string_counts.items() if len(cats) > 1}
    
    duplicate_elements = []
    if duplicates:
        duplicate_elements.append(html.H6("完全一致的关键字 (重复出现)", className="text-danger mt-3 mb-2"))
        dup_buttons = []
        # 排序以保持稳定显示
        for s in sorted(duplicates.keys()):
            cats = duplicates[s]
            dup_buttons.append(
                dbc.Button(
                    s,
                    id={"type": "duplicate-string-btn", "index": f"dup-{s}"},
                    color="danger",
                    outline=True,
                    size="sm",
                    className="m-1",
                    title=f"出现在分类: {', '.join(cats)}",
                    disabled=True  # 暂时禁用点击，只作为展示
                )
            )
        duplicate_elements.append(html.Div(dup_buttons, className="d-flex flex-wrap gap-2"))

    # 根据选择的分类过滤字符串
    if selected_category == "all":
        filtered_categories = data["categories"]
    else:
        filtered_categories = {selected_category: data["categories"].get(selected_category, [])}
    
    # 创建字符串列表
    string_elements = []
    for category, strings in filtered_categories.items():
        if strings:  # 只显示非空分类
            string_elements.append(html.H6(category, className="mt-3 mb-2"))
            
            # 创建一个包含所有按钮的容器，使用d-flex和flex-wrap确保多列显示
            button_container = html.Div(
                className="d-flex flex-wrap gap-2",
                children=[
                    dbc.Button(
                        string,
                        id={"type": "select-string-btn", "index": f"{category}-{i}"},
                        color="success" if string_type == "keep" else "danger",
                        # 根据字符串是否被选中来设置按钮样式
                        outline=not any(s["text"] == string if isinstance(s, dict) else s == string for s in selected_strings) if selected_strings else True,
                        size="sm",
                        style={"whiteSpace": "nowrap", "flexShrink": 0}
                    ) for i, string in enumerate(strings)
                ]
            )
            
            string_elements.append(button_container)
    
    if not string_elements:
        string_elements = [html.P("没有找到字符串", className="text-muted")]
    
    return string_elements, category_options, duplicate_elements

# 更新日志文件选择器选项
@app.callback(
    Output("log-file-selector", "options", allow_duplicate=True),
    [Input("main-tabs", "active_tab")],
    prevent_initial_call='initial_duplicate'  # 使用initial_duplicate允许页面加载时初始化
)
def update_log_file_selector(active_tab):
    # 当页面加载或tab切换时更新选项
    if active_tab:
        log_files = get_log_files()
        options = [{"label": file, "value": file} for file in log_files]
        return options
    return dash.no_update


@app.callback(
    [Output("compare-log-file-a-selector", "options", allow_duplicate=True),
     Output("compare-log-file-b-selector", "options", allow_duplicate=True)],
    [Input("main-tabs", "active_tab")],
    prevent_initial_call='initial_duplicate'
)
def update_compare_log_file_selectors(active_tab):
    if active_tab:
        log_files = get_log_files()
        options = [{"label": file, "value": file} for file in log_files]
        return options, options
    return dash.no_update, dash.no_update

@app.callback(
    [Output("log-file-selector", "options", allow_duplicate=True),
     Output("log-file-selector", "value", allow_duplicate=True),
     Output("toast-container", "children", allow_duplicate=True)],
    [Input("url", "search")],
    prevent_initial_call='initial_duplicate'
)
def open_log_from_query(search):
    if not search:
        return dash.no_update, dash.no_update, dash.no_update
    try:
        from urllib.parse import parse_qs, unquote
        q = parse_qs(search[1:] if search.startswith('?') else search)
        target = unquote((q.get('open') or [''])[0])
        if not target:
            return dash.no_update, dash.no_update, dash.no_update
        target = _normalize_log_filename(target)
        files = get_log_files()
        options = [{"label": f, "value": f} for f in files]
        if target not in files:
            return dash.no_update, dash.no_update, _toast_script("打开的日志文件不存在或名称无效", "error")
        return options, target, _toast_script("已打开日志", "success")
    except Exception as e:
        return dash.no_update, dash.no_update, _toast_script(f"打开日志失败: {str(e)}", "error")


@app.callback(
    [Output("runtime-log-download", "data"),
     Output("toast-container", "children", allow_duplicate=True)],
    Input("export-runtime-logs-btn", "n_clicks"),
    prevent_initial_call=True
)
def export_runtime_logs(export_clicks):
    if not export_clicks:
        return dash.no_update, dash.no_update

    try:
        archive_bytes, archive_name, exported_files = _build_runtime_logs_export()
        print(f"[运行日志] 已导出 {archive_name}: {', '.join(exported_files)}")
        return (
            dcc.send_bytes(archive_bytes, archive_name),
            html.Script(f"if(window.showToast) window.showToast('已导出运行日志（{len(exported_files)} 个文件）', 'success');")
        )
    except Exception as exc:
        print(f"[运行日志] 导出失败: {exc}")
        return dash.no_update, html.Script(f"if(window.showToast) window.showToast('导出运行日志失败: {str(exc)}', 'error');")

# 保存日志文件选择状态
@app.callback(
    Output("selected-log-file", "data"),
    [Input("log-file-selector", "value")],
    [State("selected-strings", "data"),
     State("main-tabs", "active_tab")],  # 添加当前激活的tab状态
    prevent_initial_call=True  # 防止页面加载时触发保存
)
def save_log_file_selection(selected_file, selected_strings, active_tab):
    # 只有在日志过滤tab激活时才处理回调
    if active_tab != "tab-1":
        return dash.no_update
    
    # 只有在用户真正选择文件时才保存，而不是在恢复过程中
    if selected_file is not None and selected_file != "":
        # 保存到文件
        save_user_selections(selected_file, selected_strings)
    
    return selected_file if selected_file else ""

# 选择字符串回调
@app.callback(
    Output("selected-strings", "data", allow_duplicate=True),
    [Input({"type": "select-string-btn", "index": dash.ALL}, "n_clicks"),
     Input({"type": "clear-selection-btn", "index": dash.ALL}, "n_clicks")],
    [State("selected-strings", "data"),
     State("data-store", "data"),
     State("string-type-store", "data"),  # 使用store代替radio
     State("selected-log-file", "data"),
     State("main-tabs", "active_tab")],  # 添加当前激活的tab状态
    prevent_initial_call=True  # 防止页面加载时触发
)
def select_string(select_clicks, clear_clicks, selected_strings, data, string_type, selected_log_file, active_tab):
    ctx = dash.callback_context
    
    # 只有在配置管理tab激活时才处理回调
    if active_tab != "tab-2":
        return dash.no_update
    
    # 检查是否是用户交互触发的
    is_user_interaction = False
    if ctx.triggered:
        trigger_id = ctx.triggered[0]["prop_id"]
        # 如果是按钮点击或用户操作，才认为是用户交互
        if "n_clicks" in trigger_id and ctx.triggered[0]["value"]:
            is_user_interaction = True
    
    # 清除选择
    if ctx.triggered and is_user_interaction:
        button_id = ctx.triggered[0]["prop_id"].rsplit(".", 1)[0]
        
        # 检查是否是清除选择按钮触发的
        if "clear-selection-btn" in button_id:
            # 检查是否有清除按钮被点击
            if clear_clicks and any(clicks is not None and clicks > 0 for clicks in clear_clicks):
                save_user_selections(selected_log_file, [])
                # 同时清除默认配置文件
                save_default_config([])
                return []
    
    # 选择字符串
    if ctx.triggered and ctx.triggered[0]["value"] and is_user_interaction:
        button_id = ctx.triggered[0]["prop_id"].rsplit(".", 1)[0]
        
        # 检查是否是选择字符串按钮触发的
        if "select-string-btn" in button_id:
            button_id = eval(button_id)  # 转换为字典
            category_index = button_id["index"].split("-")
            category = category_index[0]
            index = int(category_index[1])
            
            if category in data["categories"] and index < len(data["categories"][category]):
                selected_string = data["categories"][category][index]
                
                # 为选中的字符串添加类型信息
                string_with_type = {
                    "text": selected_string,
                    "type": string_type  # "keep" 或 "filter"
                }
                
                # 检查是否已经选择
                string_exists = False
                for i, s in enumerate(selected_strings):
                    if isinstance(s, dict) and s["text"] == selected_string:
                        # 更新已存在字符串的类型
                        selected_strings[i] = string_with_type
                        string_exists = True
                        break
                    elif s == selected_string:
                        # 如果是旧格式的字符串，替换为新格式
                        selected_strings[i] = string_with_type
                        string_exists = True
                        break
                
                if not string_exists:
                    selected_strings.append(string_with_type)
    
    # 只有在用户交互时才保存用户选择状态和默认配置文件
    if is_user_interaction:
        save_user_selections(selected_log_file, selected_strings)
        # 自动更新默认配置文件
        if selected_strings:
            save_default_config(selected_strings)
    
    return selected_strings

# 日志过滤tab的状态提示回调 - 更新为Toast系统
@app.callback(
    Output("toast-container", "children"),
    [Input("add-string-btn", "n_clicks")],
    [State("input-string", "value"),
     State("input-category", "value"),
     State("data-store", "data")],
    prevent_initial_call=True
)
def show_add_string_status(add_clicks, input_string, input_category, data):
    if add_clicks and input_string and input_category:
        return html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('成功添加字符串到分类 "{input_category}"', 'success');
            }}
        """)
    elif add_clicks:
        return html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('请输入字符串和分类', 'error');
            }}
        """)
    
    return dash.no_update

# 配置管理tab的状态提示回调 - 更新为Toast系统
@app.callback(
    Output("toast-container", "children", allow_duplicate=True),
    [Input({"type": "select-string-btn", "index": dash.ALL}, "n_clicks"),
     Input({"type": "clear-selection-btn", "index": dash.ALL}, "n_clicks")],
    [State("data-store", "data"),
     State("selected-strings", "data"),
     State("main-tabs", "active_tab")],
    prevent_initial_call=True
)
def show_config_status(select_clicks, clear_clicks, data, selected_strings, active_tab):
    # 只在配置管理tab激活时处理
    if active_tab != 'tab-2':
        return dash.no_update
    
    ctx = dash.callback_context
    
    if not ctx.triggered:
        return dash.no_update

    trigger_id = ctx.triggered[0]["prop_id"].rsplit(".", 1)[0]
    
    # 选择字符串状态
    if "select-string-btn" in trigger_id:
        button_id = eval(trigger_id)  # 转换为字典
        category_index = button_id["index"].split("-")
        category = category_index[0]
        index = int(category_index[1])
        
        if category in data["categories"] and index < len(data["categories"][category]):
            selected_string = data["categories"][category][index]
            
            # 检查是否已经选择
            if selected_string in selected_strings:
                return html.Script(f"""
                    if (typeof window.showToast === 'function') {{
                        window.showToast('该字符串已经被选择', 'warning');
                    }}
                """)
            else:
                return dash.no_update
    
    # 清除选择状态
    if "clear-selection-btn" in trigger_id:
        # 检查是否有清除按钮被点击
        if clear_clicks and any(clicks is not None and clicks > 0 for clicks in clear_clicks):
            return html.Script(f"""
                if (typeof window.showToast === 'function') {{
                    window.showToast('已清除所有选择', 'info');
                }}
            """)
    
    return dash.no_update


# 更新选中字符串显示

# 更新选中字符串显示
@app.callback(
    Output("selected-strings-container", "children"),
    [Input("selected-strings", "data"),
     Input("data-store", "data"),
     Input("main-tabs", "active_tab")],  # 添加当前激活的tab状态
    prevent_initial_call=True  # 防止页面加载时立即触发
)  
def update_selected_strings(selected_strings, data, active_tab):
    # 只有在配置管理tab激活时才处理回调
    if active_tab != "tab-2":
        return dash.no_update
    
    if not selected_strings:
        return [html.P("没有选中的字符串", className="text-muted")]
    
    # 按类型和分类组织选中的字符串
    keep_strings = []
    filter_strings = []
    
    for item in selected_strings:
        # 处理新格式的字符串（带类型信息）
        if isinstance(item, dict):
            string_text = item["text"]
            string_type = item["type"]
            
            # 查找字符串所属的分类
            for category, strings in data["categories"].items():
                if string_text in strings:
                    if string_type == "keep":
                        keep_strings.append((category, string_text))
                    else:
                        filter_strings.append((category, string_text))
                    break
        # 处理旧格式的字符串（不带类型信息）
        else:
            string_text = item
            # 查找字符串所属的分类
            for category, strings in data["categories"].items():
                if string_text in strings:
                    # 默认为保留字符串
                    keep_strings.append((category, string_text))
                    break
    
    # 创建显示元素
    display_elements = []
    
    # 显示保留字符串
    if keep_strings:
        display_elements.append(html.H5("保留字符串", className="text-success mt-3 mb-2"))
        categorized_keep = {}
        for category, string_text in keep_strings:
            if category not in categorized_keep:
                categorized_keep[category] = []
            categorized_keep[category].append(string_text)
        
        for category, strings in categorized_keep.items():
            display_elements.append(html.H6(category, className="mt-2 mb-1"))
            string_buttons = []
            for string_text in strings:
                string_buttons.append(
                    dbc.Button(
                        string_text, 
                        id={"type": "selected-string-btn", "index": string_text},
                        color="success", 
                        size="sm",
                        className="m-1",
                        style={"whiteSpace": "nowrap", "flexShrink": 0}
                    )
                )
            display_elements.append(
                html.Div(
                    string_buttons,
                    className="d-flex flex-wrap gap-2",
                    style={"minHeight": "50px"}
                )
            )
    
    # 显示过滤字符串
    if filter_strings:
        display_elements.append(html.H5("过滤字符串", className="text-danger mt-3 mb-2"))
        categorized_filter = {}
        for category, string_text in filter_strings:
            if category not in categorized_filter:
                categorized_filter[category] = []
            categorized_filter[category].append(string_text)
        
        for category, strings in categorized_filter.items():
            display_elements.append(html.H6(category, className="mt-2 mb-1"))
            string_buttons = []
            for string_text in strings:
                string_buttons.append(
                    dbc.Button(
                        string_text, 
                        id={"type": "selected-string-btn", "index": string_text},
                        color="danger", 
                        size="sm",
                        className="m-1",
                        style={"whiteSpace": "nowrap", "flexShrink": 0}
                    )
                )
            display_elements.append(
                html.Div(
                    string_buttons,
                    className="d-flex flex-wrap gap-2",
                    style={"minHeight": "50px"}
                )
            )
    
    return display_elements

# 点击已选择字符串取消选择的回调
@app.callback(
    Output("selected-strings", "data", allow_duplicate=True),
    [Input({"type": "selected-string-btn", "index": dash.ALL}, "n_clicks")],
    [State({"type": "selected-string-btn", "index": dash.ALL}, "id"),
     State("selected-strings", "data"),
     State("selected-log-file", "data"),
     State("main-tabs", "active_tab")],  # 添加当前激活的tab状态
    prevent_initial_call=True
)
def toggle_selected_string(n_clicks, button_ids, selected_strings, selected_log_file, active_tab):
    # 只有在配置管理tab激活时才处理回调
    if active_tab != "tab-2":
        return dash.no_update
    
    ctx = dash.callback_context
    
    if not ctx.triggered:
        return selected_strings
    
    # 获取触发回调的按钮ID
    triggered_id = ctx.triggered[0]["prop_id"].rsplit(".", 1)[0]
    
    # 检查是否是selected-string-btn触发的
    if "selected-string-btn" in triggered_id:
        # 找出哪个按钮被点击了
        for i, clicks in enumerate(n_clicks):
            if clicks:
                # 获取被点击按钮的ID
                button_id = button_ids[i]
                clicked_string = button_id["index"]
                
                # 如果字符串在已选择列表中，则移除它
                # 处理新格式的字符串（带类型信息）
                new_selected_strings = []
                for item in selected_strings:
                    if isinstance(item, dict):
                        if item["text"] != clicked_string:
                            new_selected_strings.append(item)
                    else:
                        # 处理旧格式的字符串（不带类型信息）
                        if item != clicked_string:
                            new_selected_strings.append(item)
                
                # 保存用户选择状态和默认配置文件
                save_user_selections(selected_log_file, new_selected_strings)
                # 自动更新默认配置文件
                save_default_config(new_selected_strings)
                
                return new_selected_strings
    
    return selected_strings



@app.callback(
    [Output("filter-loading-spinner", "spinner_style"),
     Output("filter-btn-text", "children"),
     Output("execute-filter-btn", "disabled"),
     Output("execute-filter-btn", "color"),
     Output("log-view-status-bar", "children"),
     Output("log-view-status-bar", "className")],
    [Input(_UI_BUSY_STORE_ID, "data")]
)
def render_log_view_ui_state(ui_state):
    ui_state = ui_state or _make_log_view_ui_state("idle")
    return (
        ui_state.get("spinner_style", {"display": "none", "marginLeft": "5px"}),
        ui_state.get("button_text", "过滤"),
        bool(ui_state.get("button_disabled")),
        ui_state.get("button_color", "success"),
        ui_state.get("status_text", "Ready"),
        ui_state.get("status_class", "badge bg-secondary ms-3")
    )

# 关键字注释控件：保存注释
@app.callback(
    Output("keyword-annotations-store", "data", allow_duplicate=True),
    [Input("annotation-save-btn", "n_clicks")],
    [State("annotation-keyword-input", "value"),
     State("annotation-text-input", "value"),
     State("keyword-annotations-store", "data")],
    prevent_initial_call=True
)
def save_keyword_annotation(n_clicks, keyword, note, annotations_map):
    if not n_clicks:
        return dash.no_update
    if not keyword:
        try:
            # 使用Toast提示
            import dash
            dash.clientside_callback  # 占位，避免未使用报警
        except Exception:
            pass
        return dash.no_update
    note_text = (note or "").strip()
    annotations_map = annotations_map or {}
    key_str = str(keyword)

    # 若注释内容为空，则删除已有关键字注释
    if note_text == "":
        if key_str in annotations_map:
            del annotations_map[key_str]
        save_annotations(annotations_map)
        try:
            # Toast（仅打印日志占位）
            print(f"[注释] 已删除: {key_str}")
        except Exception:
            pass
        return annotations_map

    # 否则保存/更新注释
    annotations_map[key_str] = note_text
    save_annotations(annotations_map)
    try:
        # Toast（仅打印日志占位）
        print(f"[注释] 已保存: {key_str} -> {note_text}")
    except Exception:
        pass
    return annotations_map

# 关键字注释控件：列表行删除
@app.callback(
    Output("keyword-annotations-store", "data", allow_duplicate=True),
    [Input({"type": "annotation-del", "index": dash.ALL}, "n_clicks")],
    [State({"type": "annotation-del", "index": dash.ALL}, "id"),
     State("keyword-annotations-store", "data")],
    prevent_initial_call=True
)
def delete_keyword_annotation_row(n_clicks, button_ids, annotations_map):
    if not n_clicks or not any(n_clicks):
        return dash.no_update
    annotations_map = annotations_map or {}
    # 找到被点击的按钮
    for idx, clicks in enumerate(n_clicks):
        if clicks and idx < len(button_ids):
            btn_id = button_ids[idx]
            # index 即为关键字
            kw = btn_id.get("index") if isinstance(btn_id, dict) else None
            if kw and kw in annotations_map:
                del annotations_map[kw]
                save_annotations(annotations_map)
                try:
                    print(f"[注释] 已删除: {kw}")
                except Exception:
                    pass
                break
    return annotations_map

# 关键字注释控件：显示列表
@app.callback(
    Output("keyword-annotations-list", "children"),
    [Input("keyword-annotations-store", "data")]
)
def render_keyword_annotations_list(annotations_map):
    annotations_map = annotations_map or {}
    if not annotations_map:
        return html.P("暂无注释", className="text-muted")
    rows = []
    for kw, note in sorted(annotations_map.items(), key=lambda kv: kv[0].lower()):
        rows.append(html.Tr([
            html.Td(html.Code(kw, className="small")),
            html.Td(note or "", className="small"),
            html.Td(
                dbc.Button(
                    "删除",
                    id={"type": "annotation-del", "index": kw},
                    color="danger",
                    outline=True,
                    size="sm"
                ),
                style={"width": "1%", "whiteSpace": "nowrap"}
            )
        ]))
    
    table_header = html.Thead(html.Tr([html.Th("关键字"), html.Th("注释"), html.Th("操作")]))
    table_body = html.Tbody(rows)
    
    table = dbc.Table(
        [table_header, table_body], 
        bordered=True, 
        hover=True, 
        size="sm", 
        striped=True, 
        className="mb-0"
    )
    return table

# 生成并执行过滤命令的回调 - 仅处理过滤结果
@app.callback(
    [Output("log-filter-results", "children"),
     Output("filtered-result-store", "data"),
     Output("filter-progress-bar", "value", allow_duplicate=True),
     Output("filter-progress-text", "children", allow_duplicate=True),
     Output("filter-backend-display", "children", allow_duplicate=True),
     Output("filter-progress-footer", "style", allow_duplicate=True),
     Output("filter-session-store", "data"),
     Output("filter-progress-interval", "disabled", allow_duplicate=True),
     Output("filter-progress-interval", "n_intervals", allow_duplicate=True),
     Output("filter-first-chunk-ready", "data"),
     Output(_UI_BUSY_STORE_ID, "data", allow_duplicate=True)],
    [Input("execute-filter-btn", "n_clicks")],
    [State("filter-tab-strings-store", "data"),
     State("temp-keywords-store", "data"),
     State("log-file-selector", "value"),
     State("filter-session-store", "data"),
     State("filter-backend-selector", "value"),
     State("main-tabs", "active_tab")],
    prevent_initial_call=True
)
def execute_filter_command(n_clicks, filter_tab_strings, temp_keywords, selected_log_file, previous_session_id, preferred_backend, active_tab):
    # 只有在日志过滤tab激活时才处理回调
    if active_tab != "tab-1" or not n_clicks:
        return (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update)
    
    if previous_session_id:
        _clear_filter_task(previous_session_id, delete_files=False)
    
    preferred_backend = preferred_backend or DEFAULT_FILTER_BACKEND
    # 执行过滤命令，包含临时关键字
    session_id, filtered_result = execute_filter_logic(filter_tab_strings, temp_keywords, selected_log_file, preferred_backend=preferred_backend)
    try:
        print(f"[过滤UI] 启动过滤 session={session_id}, n_clicks={n_clicks}")
    except Exception:
        pass
    
    ui_state = _make_log_view_ui_state("filter_running") if session_id else _make_log_view_ui_state("source_ready" if selected_log_file else "idle")
    # 启动进度轮询，首片尚未就绪；重置存储、启用interval、按钮置忙，并重置 interval 计数
    return (
        filtered_result,                # log-filter-results 显示进度组件
        "",                             # filtered-result-store 清空
        0,                              # 重置底部进度条
        "",                             # 重置进度文字
        _format_filter_backend_text(None, preferred_backend, pending=True) if session_id else _format_filter_backend_text(None, preferred_backend),  # 底部工具显示
        {"display": "block"},           # 展示底部进度条区域
        session_id or "",               # 会话
        False,                          # interval 启用 (disabled=False)
        0,                              # 重置轮询计数
        False,                          # 首片未就绪
        ui_state
    )


@app.callback(
    Output("filter-backend-display", "children", allow_duplicate=True),
    [Input("filter-backend-selector", "value"),
     Input("main-tabs", "active_tab")],
    prevent_initial_call=True
)
def refresh_filter_backend_display(preferred_backend, active_tab):
    if active_tab != "tab-1":
        return dash.no_update
    return _format_filter_backend_text(None, preferred_backend or DEFAULT_FILTER_BACKEND)


# 选择文件后加载其他Tab内容
@app.callback(
    [Output("log-source-results", "children"),
     Output("log-annotation-results", "children"),
     Output("log-flows-results", "children"),
     Output("source-result-store", "data"),
     Output("log-filter-results", "children", allow_duplicate=True),
     Output(_UI_BUSY_STORE_ID, "data")],
    [Input("log-file-selector", "value")],
    [State("filter-tab-strings-store", "data"),
     State("temp-keywords-store", "data"),
     State("keyword-annotations-store", "data"),
     State("main-tabs", "active_tab")],
    prevent_initial_call=True
)
def load_tab_contents_on_file_select(selected_log_file, filter_tab_strings, temp_keywords, annotations_map, active_tab):
    if not selected_log_file:
        return "", "", "", "", "", _make_log_view_ui_state("idle")

    # 源文件视图使用滚动窗口，便于查找/跳转
    source_command, source_result = execute_source_logic(selected_log_file, filter_tab_strings, temp_keywords)

    # 注释模式
    annotation_component = build_annotation_extract_display_by_matching(selected_log_file, annotations_map)

    # 流程视图
    flows_component = build_flows_display(selected_log_file)

    return source_result, annotation_component, flows_component, source_result, "", _make_log_view_ui_state("source_ready")


def find_latest_filter_session():
    """从 temp 目录找到最新的过滤结果文件，返回 session_id"""
    ensure_temp_dir()
    try:
        files = [f for f in os.listdir(TEMP_DIR) if f.startswith("filter_result_") and f.endswith(".txt")]
        if not files:
            return None
        files.sort(key=lambda f: os.path.getmtime(os.path.join(TEMP_DIR, f)), reverse=True)
        latest = files[0]
        sid = latest[len("filter_result_"):-len(".txt")]
        return sid
    except Exception:
        return None


# ---- AI 流程状态分析（实时流式：后台线程 + 前端轮询）----

@app.callback(
    [Output("ai-flow-analysis-trigger", "data"),
     Output("ai-flow-analysis-status", "children"),
     Output("ai-flow-analysis-results", "children", allow_duplicate=True),
     Output("ai-flow-analysis-live-log", "children"),
     Output("ai-flow-analysis-live-log", "style"),
     Output("ai-flow-analysis-btn", "disabled"),
     Output("ai-flow-progress-interval", "disabled"),
     Output("ai-flow-progress-interval", "n_intervals")],
    [Input("ai-flow-analysis-btn", "n_clicks")],
    [State("log-filter-config-group-selector", "value")],
    prevent_initial_call=True
)
def start_ai_flow_analysis(n_clicks, config_group):
    if not n_clicks:
        return (dash.no_update,) * 8

    session_id = find_latest_filter_session()
    if not session_id:
        return 0, html.Span("请先过滤日志", style={"color": "#856404"}), dash.no_update, "", {"display": "none"}, False, True, 0

    filtered_text = read_filtered_log_text(session_id, max_lines=3000)
    if not filtered_text or not filtered_text.strip():
        return 0, html.Span("无过滤数据", style={"color": "#856404"}), dash.no_update, "", {"display": "none"}, False, True, 0

    import uuid
    task_id = f"ai-flow-{uuid.uuid4().hex[:12]}"

    config_files = ""
    if config_group:
        try:
            groups = load_config_groups()
            group_files = groups.get(config_group, [])
            if group_files:
                config_files = ", ".join(group_files)
        except Exception:
            pass

    # 保存输入文件
    input_file = os.path.join(TEMP_DIR, f"ai_flow_input_{uuid.uuid4().hex[:8]}.txt")
    try:
        with open(input_file, 'w', encoding='utf-8') as f:
            f.write(f"# LogFilter AI Flow Analysis Input\n")
            if config_group:
                f.write(f"# 配置组: {config_group}\n")
            if config_files:
                f.write(f"# 关联配置文件: {config_files}\n")
            f.write(f"# 共 {len(filtered_text.splitlines())} 行\n\n")
            f.write(filtered_text)
    except Exception as e:
        print(f"[AI流程] 写入临时文件失败: {e}")
        return 0, html.Span("写入失败", style={"color": "#dc3545"}), dash.no_update, "", {"display": "none"}, False, True, 0

    config_info = f"配置组: {config_group}" if config_group else "未选择配置组"
    if config_files:
        config_info += f"\n关联配置文件: {config_files}"

    prompt = f"""你是一个日志流程分析专家。分析日志文件中的过滤后内容，识别其中的业务流程运行状态，并以 JSON 格式返回。

{config_info}

日志文件路径: {input_file}
请使用 read_source_file 工具读取该文件，然后分析其中的日志内容。

请严格按照以下 JSON 格式返回分析结果，只返回纯 JSON，不要包含 markdown 代码块标记:

{{"flows": [
  {{"name": "流程名称", "status": "normal", "reason": "状态说明",
    "steps": [
      {{"name": "步骤名称", "status": "normal", "detail": "匹配到的日志行摘要(10-30字)"}}
    ]
  }}
]}}

状态取值规则:
- normal: 步骤正常完成，无报错
- abnormal: 步骤出现 error/fail/exception 等错误
- warning: 步骤出现 timeout/warning/retry 等异常但不致命

如果日志中无明显可识别的业务流程，返回 {{"flows": []}}。"""

    # 初始化任务
    _init_ai_flow_task(task_id)
    _update_ai_flow_task(task_id,
        prompt=prompt, input_file=input_file,
        config_group=config_group or "", config_files=config_files)

    # 启动后台线程
    thread = threading.Thread(
        target=_ai_flow_worker,
        args=(task_id, prompt, input_file, config_group, config_files)
    )
    thread.daemon = True
    thread.start()

    live_log_style = {
        "maxHeight": "300px", "overflowY": "auto",
        "backgroundColor": "#fafafa", "padding": "6px",
        "border": "1px solid #e0e0e0", "borderRadius": "4px",
        "fontFamily": "monospace", "fontSize": "12px",
        "marginBottom": "8px"
    }
    return task_id, html.Span([
        html.Span("分析中", className="me-1"),
        html.Span("...", className="animated-dots")
    ], style={"color": "#0d6efd"}), "", "", live_log_style, True, False, 0


@app.callback(
    [Output("ai-flow-analysis-live-log", "children", allow_duplicate=True),
     Output("ai-flow-analysis-results", "children", allow_duplicate=True),
     Output("ai-flow-analysis-status", "children", allow_duplicate=True),
     Output("ai-flow-analysis-btn", "disabled", allow_duplicate=True),
     Output("ai-flow-progress-interval", "disabled", allow_duplicate=True),
     Output("ai-flow-interaction-log", "data", allow_duplicate=True),
     Output("ai-flow-log-btn", "style")],
    [Input("ai-flow-progress-interval", "n_intervals")],
    [State("ai-flow-analysis-trigger", "data")],
    prevent_initial_call=True
)
def poll_ai_flow_progress(n_intervals, task_id):
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    if not task_id or not isinstance(task_id, str) or not task_id.startswith("ai-flow-"):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, True, dash.no_update, dash.no_update

    task = _get_ai_flow_task(task_id)
    if not task:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, True, dash.no_update, dash.no_update

    events = task.get("events", [])
    all_chunks = _render_ai_flow_events(events, start_from=0)

    status = task.get("status")
    log_entry = {}

    if status == "running":
        return all_chunks, dash.no_update, dash.no_update, True, False, dash.no_update, dash.no_update

    elif status == "error":
        err = task.get("error", "未知错误")
        # 构建交互日志 entry
        log_entry = {
            "timestamp": now_str,
            "config_group": task.get("config_group", ""),
            "config_files": task.get("config_files", ""),
            "prompt": task.get("prompt", ""),
            "response": task.get("response_text", ""),
            "input_file": task.get("input_file", ""),
            "status": "error"
        }
        error_display = html.Div([
            html.P("AI 分析失败:", className="text-danger small mb-1"),
            html.Pre(err[:500], style={"fontSize": "11px", "background": "#f5f5f5", "padding": "8px", "borderRadius": "4px"})
        ])
        _clear_ai_flow_task(task_id)
        return all_chunks, error_display, html.Span("分析失败", style={"color": "#dc3545"}), False, True, log_entry, {"display": "inline-block"}

    elif status == "done":
        response_text = task.get("response_text", "")
        prompt_text = task.get("prompt", "")
        input_file = task.get("input_file", "")

        flow_data = parse_ai_flow_response(response_text)
        if flow_data is None:
            log_entry = {
                "timestamp": now_str,
                "config_group": task.get("config_group", ""),
                "config_files": task.get("config_files", ""),
                "prompt": prompt_text,
                "response": response_text,
                "input_file": input_file,
                "status": "format_error"
            }
            _clear_ai_flow_task(task_id)
            result_display = html.Div([
                html.P("AI 返回数据格式异常，显示原始分析结果：", className="text-muted small mb-1"),
                html.Pre(response_text[:2000], style={"fontSize": "11px", "whiteSpace": "pre-wrap", "background": "#f5f5f5", "padding": "8px", "borderRadius": "4px"})
            ])
            return all_chunks, result_display, html.Span("格式异常", style={"color": "#856404"}), False, True, log_entry, {"display": "inline-block"}

        chart = render_flow_chart(flow_data)
        result_count = len(flow_data.get("flows", []))
        log_entry = {
            "timestamp": now_str,
            "config_group": task.get("config_group", ""),
            "config_files": task.get("config_files", ""),
            "prompt": prompt_text,
            "response": response_text,
            "input_file": input_file,
            "status": "ok",
            "flow_count": result_count
        }
        _clear_ai_flow_task(task_id)
        return all_chunks, chart, html.Span([
            html.Span("完成", style={"color": "#28a745", "fontWeight": 600}),
            html.Span(f" — 检测到 {result_count} 个流程", style={"color": "#666"})
        ]), False, True, log_entry, {"display": "inline-block"}

    return dash.no_update, dash.no_update, dash.no_update, dash.no_update, True, dash.no_update, dash.no_update


# ---- 交互日志弹窗 ----

def build_interaction_log_body(log_data):
    """从 store 数据构建交互日志的 Modal body"""
    if not log_data or not isinstance(log_data, dict) or not log_data.get("prompt"):
        return html.Div("暂无交互日志，请先执行 AI 流程状态分析", className="text-muted text-center py-5")

    ts = log_data.get("timestamp", "")
    cg = log_data.get("config_group", "")
    cf = log_data.get("config_files", "")
    inp = log_data.get("input_file", "")
    prompt_text = log_data.get("prompt", "")
    response_text = log_data.get("response", "")
    status = log_data.get("status", "")

    sections = [
        html.Div([
            html.H6("基本信息", className="mb-2", style={"borderBottom": "1px solid #dee2e6", "paddingBottom": "4px"}),
            html.Table([
                html.Tr([html.Td("时间", style={"width": "100px", "color": "#888"}), html.Td(ts)]),
                html.Tr([html.Td("配置组", style={"color": "#888"}), html.Td(cg or "未选择")]),
                html.Tr([html.Td("配置文件", style={"color": "#888"}), html.Td(cf or "无")]),
                html.Tr([html.Td("输入文件", style={"color": "#888"}), html.Td(html.Code(inp, style={"fontSize": "11px"}))]),
                html.Tr([html.Td("状态", style={"color": "#888"}), html.Td(status)]),
            ], style={"fontSize": "13px"}),
        ], className="mb-3"),
    ]

    sections.append(html.Div([
        html.H6("发送给 AI 的 Prompt", className="mb-2", style={"borderBottom": "1px solid #dee2e6", "paddingBottom": "4px"}),
        html.Pre(prompt_text, style={
            "fontSize": "11px", "whiteSpace": "pre-wrap", "wordBreak": "break-all",
            "background": "#f8f9fa", "padding": "12px", "borderRadius": "4px",
            "border": "1px solid #dee2e6", "maxHeight": "400px", "overflowY": "auto"
        }),
    ], className="mb-3"))

    sections.append(html.Div([
        html.H6("AI 返回的原始响应", className="mb-2", style={"borderBottom": "1px solid #dee2e6", "paddingBottom": "4px"}),
        html.Pre(response_text, style={
            "fontSize": "11px", "whiteSpace": "pre-wrap", "wordBreak": "break-all",
            "background": "#f0f8ff", "padding": "12px", "borderRadius": "4px",
            "border": "1px solid #b8daff", "maxHeight": "400px", "overflowY": "auto"
        }),
    ]))

    return html.Div(sections, style={"padding": "4px"})


@app.callback(
    Output("ai-flow-log-modal", "is_open"),
    Output("ai-flow-log-body", "children"),
    [Input("ai-flow-log-btn", "n_clicks"),
     Input("ai-flow-log-close-btn", "n_clicks")],
    [State("ai-flow-log-modal", "is_open"),
     State("ai-flow-interaction-log", "data")],
    prevent_initial_call=True
)
def toggle_interaction_log(open_clicks, close_clicks, is_open, log_data):
    ctx = dash.callback_context
    if not ctx.triggered:
        return is_open, dash.no_update
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger_id == "ai-flow-log-btn":
        body = build_interaction_log_body(log_data)
        return True, body
    elif trigger_id == "ai-flow-log-close-btn":
        return False, dash.no_update
    return is_open, dash.no_update


def _compile_patterns(keep_strings, filter_strings):
    """预编译保留/过滤正则，避免重复编译"""
    keep_regex = None
    filter_regex = None
    if keep_strings:
        escaped = [re.escape(s) for s in keep_strings if s]
        if escaped:
            keep_regex = re.compile("|".join(escaped), re.IGNORECASE)
    if filter_strings:
        escaped = [re.escape(s) for s in filter_strings if s]
        if escaped:
            filter_regex = re.compile("|".join(escaped), re.IGNORECASE)
    return keep_regex, filter_regex

def _compile_byte_patterns(keep_strings, filter_strings, encoding):
    """基于编码预编译字节级正则，避免逐行解码"""
    keep_regex = None
    filter_regex = None
    try:
        if keep_strings:
            escaped = [re.escape(s).encode(encoding, errors='ignore') for s in keep_strings if s]
            if escaped:
                keep_regex = re.compile(b"|".join(escaped), re.IGNORECASE)
        if filter_strings:
            escaped = [re.escape(s).encode(encoding, errors='ignore') for s in filter_strings if s]
            if escaped:
                filter_regex = re.compile(b"|".join(escaped), re.IGNORECASE)
    except Exception as e:
        print(f"[过滤] 编译字节正则失败，回退文本正则: {e}")
    return keep_regex, filter_regex


def _build_temp_index(temp_file_path, idx_path, encoding, index_every=500):
    """为临时文件生成行偏移索引"""
    offsets = []
    current_offset = 0
    line_count = 0
    try:
        with open(temp_file_path, 'rb') as f:
            for raw_line in f:
                line_count += 1
                if line_count % index_every == 1:
                    offsets.append([line_count, current_offset])
                current_offset += len(raw_line)
        with open(idx_path, 'w', encoding='utf-8') as idx_file:
            json.dump({
                "encoding": encoding,
                "index_every": index_every,
                "line_count": line_count,
                "offsets": offsets
            }, idx_file, ensure_ascii=False)
    except Exception as e:
        print(f"[过滤] 构建索引失败: {e}")
    return line_count


def _normalize_filter_terms(values):
    return [str(value) for value in (values or []) if str(value)]


def _powershell_quote(value):
    return "'" + value.replace("'", "''") + "'"


def _build_arg_command(base_args, patterns, log_path=None, invert=False):
    cmd = list(base_args)
    if invert:
        cmd.append("-v")
    for pattern in patterns:
        cmd.extend(["-e", pattern])
    if log_path:
        cmd.append(log_path)
    return cmd


def _build_powershell_encoded_command(script):
    runtime = _detect_windows_powershell_runtime()
    shell_cmd = runtime.get("cmd")
    if not shell_cmd or not runtime.get("meets_minimum"):
        raise RuntimeError(f"Windows PowerShell 不可用: {_powershell_fallback_reason()}")
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return [shell_cmd, "-NoProfile", "-EncodedCommand", encoded]


def _normalize_command_args(command):
    if isinstance(command, (list, tuple)):
        return [str(part) for part in command]
    if not command:
        raise ValueError("命令不能为空")
    import shlex
    return shlex.split(str(command), posix=(os.name != "nt"))


def _build_findstr_command(patterns, log_path=None, invert=False):
    cmd = ["findstr", "/i", "/l"]
    if invert:
        cmd.append("/v")
    for pattern in patterns:
        cmd.append(f"/c:{pattern}")
    if log_path:
        cmd.append(log_path)
    return cmd


def _run_pipeline_to_file(commands, temp_file_path):
    with open(temp_file_path, "wb") as output_file:
        if len(commands) == 1:
            result = subprocess.run(commands[0], stdout=output_file, stderr=subprocess.PIPE)
            stderr_text = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            return [result.returncode], stderr_text

        first = subprocess.Popen(commands[0], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        second = subprocess.Popen(commands[1], stdin=first.stdout, stdout=output_file, stderr=subprocess.PIPE)
        if first.stdout:
            first.stdout.close()
        second_stderr = second.communicate()[1]
        first_stderr = first.communicate()[1]
        stderr_parts = []
        if first_stderr:
            stderr_parts.append(first_stderr.decode("utf-8", errors="replace"))
        if second_stderr:
            stderr_parts.append(second_stderr.decode("utf-8", errors="replace"))
        return [first.returncode, second.returncode], "\n".join(part for part in stderr_parts if part)


def _finalize_filtered_output(temp_file_path, idx_path, encoding, index_every, backend):
    line_count = _build_temp_index(temp_file_path, idx_path, encoding, index_every=index_every)
    print(f"[过滤] 使用 {backend} 完成，输出: {temp_file_path}, 行数: {line_count}")
    return temp_file_path, idx_path, line_count, encoding, backend


def _stream_filter_with_rg(log_path, temp_file_path, idx_path, keep_strings, filter_strings, encoding, index_every):
    rg_cmd = _get_rg_command()
    if not rg_cmd:
        raise RuntimeError("未找到可用的 rg")
    commands = []
    if keep_strings:
        commands.append(_build_arg_command([rg_cmd, "--text", "--no-heading", "--color", "never", "-i", "-F"], keep_strings, log_path=log_path))
    else:
        commands.append([rg_cmd, "--text", "--no-heading", "--color", "never", "^", log_path])
    if filter_strings:
        commands.append(_build_arg_command([rg_cmd, "--text", "--no-heading", "--color", "never", "-i", "-F"], filter_strings, invert=True))
    return_codes, stderr_text = _run_pipeline_to_file(commands, temp_file_path)
    if any(code not in (0, 1) for code in return_codes):
        raise RuntimeError(f"rg 过滤失败: {stderr_text or return_codes}")
    return _finalize_filtered_output(temp_file_path, idx_path, encoding, index_every, "rg")


def _stream_filter_with_grep(log_path, temp_file_path, idx_path, keep_strings, filter_strings, encoding, index_every):
    commands = []
    if keep_strings:
        commands.append(_build_arg_command(["grep", "-a", "-i", "-F"], keep_strings, log_path=log_path))
    else:
        commands.append(["grep", "-a", "-E", "^", log_path])
    if filter_strings:
        commands.append(_build_arg_command(["grep", "-a", "-i", "-F"], filter_strings, invert=True))
    return_codes, stderr_text = _run_pipeline_to_file(commands, temp_file_path)
    if any(code not in (0, 1) for code in return_codes):
        raise RuntimeError(f"grep 过滤失败: {stderr_text or return_codes}")
    return _finalize_filtered_output(temp_file_path, idx_path, encoding, index_every, "grep")


def _stream_filter_with_findstr(log_path, temp_file_path, idx_path, keep_strings, filter_strings, encoding, index_every):
    commands = []
    if keep_strings:
        commands.append(_build_findstr_command(keep_strings, log_path=log_path))
    else:
        commands.append(["cmd", "/d", "/s", "/c", f'type "{log_path}"'])
    if filter_strings:
        commands.append(_build_findstr_command(filter_strings, invert=True))
    return_codes, stderr_text = _run_pipeline_to_file(commands, temp_file_path)
    if any(code not in (0, 1) for code in return_codes):
        raise RuntimeError(f"findstr 过滤失败: {stderr_text or return_codes}")
    return _finalize_filtered_output(temp_file_path, idx_path, encoding, index_every, "findstr")


def _stream_filter_with_powershell(log_path, temp_file_path, idx_path, keep_strings, filter_strings, index_every, shell_cmd):
    keep_array = "@(" + ", ".join(_powershell_quote(pattern) for pattern in keep_strings) + ")" if keep_strings else "@()"
    filter_array = "@(" + ", ".join(_powershell_quote(pattern) for pattern in filter_strings) + ")" if filter_strings else "@()"
    script = "\n".join([
        f"$keepPatterns = {keep_array}",
        f"$filterPatterns = {filter_array}",
        f"$inputPath = {_powershell_quote(log_path)}",
        f"$outputPath = {_powershell_quote(temp_file_path)}",
        "$content = Get-Content -Path $inputPath",
        "if ($keepPatterns.Count -gt 0) { $content = $content | Select-String -SimpleMatch -CaseSensitive:$false -Pattern $keepPatterns }",
        "if ($filterPatterns.Count -gt 0) { $content = $content | Select-String -SimpleMatch -CaseSensitive:$false -NotMatch -Pattern $filterPatterns }",
        "$content | Set-Content -Path $outputPath -Encoding utf8"
    ])
    result = subprocess.run(_build_powershell_encoded_command(script), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode not in (0, 1):
        stderr_text = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        raise RuntimeError(f"{shell_cmd} 过滤失败: {stderr_text or result.returncode}")
    return _finalize_filtered_output(temp_file_path, idx_path, "utf-8", index_every, shell_cmd)


def _copy_source_to_temp(log_path, temp_file_path, idx_path, encoding, index_every):
    shutil.copyfile(log_path, temp_file_path)
    return _finalize_filtered_output(temp_file_path, idx_path, encoding, index_every, "python-copy")


def stream_filter_to_temp(log_path, keep_regex, filter_regex, keep_strings, filter_strings, session_id=None, index_every=500, preferred_backend="auto"):
    ensure_temp_dir()
    temp_file_path = get_temp_file_path(session_id)
    idx_path = get_temp_index_path(temp_file_path)
    encoding = detect_file_encoding(log_path)
    normalized_keep = _normalize_filter_terms(keep_strings)
    normalized_filter = _normalize_filter_terms(filter_strings)

    if not normalized_keep and not normalized_filter:
        return _copy_source_to_temp(log_path, temp_file_path, idx_path, encoding, index_every)

    resolved_backend = _resolve_filter_backend(preferred_backend)

    if resolved_backend == "rg":
        return _stream_filter_with_rg(log_path, temp_file_path, idx_path, normalized_keep, normalized_filter, encoding, index_every)

    if resolved_backend == "grep":
        return _stream_filter_with_grep(log_path, temp_file_path, idx_path, normalized_keep, normalized_filter, encoding, index_every)

    if resolved_backend == "findstr":
        return _stream_filter_with_findstr(log_path, temp_file_path, idx_path, normalized_keep, normalized_filter, encoding, index_every)

    if resolved_backend == "powershell":
        runtime = _detect_windows_powershell_runtime()
        if runtime.get("cmd") and runtime.get("meets_minimum"):
            return _stream_filter_with_powershell(log_path, temp_file_path, idx_path, normalized_keep, normalized_filter, index_every, runtime["cmd"])
        raise RuntimeError(f"Windows PowerShell 版本过低，切换 Python 过滤: {_powershell_fallback_reason()}")

    if resolved_backend == "python":
        raise RuntimeError("切换 Python 过滤")

    raise RuntimeError("未找到可用的外部预处理工具")


def build_rolling_display(temp_file_path, line_count, session_id, selected_strings, data, encoding):
    """基于临时文件构建滚动窗口组件"""
    rolling_cfg = load_rolling_config()
    window_size = rolling_cfg.get('lines_before', 250) + rolling_cfg.get('lines_after', 249) + 1
    initial_content, _ = get_file_lines_range(temp_file_path, 1, min(window_size, line_count), encoding=encoding)
    if selected_strings and data:
        initial_display = highlight_keywords_dash(initial_content, selected_strings, data, flat=True)
    else:
        initial_display = html.Pre(initial_content, className="small")
    
    result_display = html.Div([
        html.Div(),
        html.Div(
            id=f"log-window-{session_id}",
            children=[
                html.Div(className="pad-top", style={"height": "0px"}),
                initial_display,
                html.Div(className="pad-bottom", style={"height": "0px"})
            ],
            style={"backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px", "fontFamily": "monospace", "fontSize": "12px"},
            **{
                "data-session-id": session_id,
                "data-total-lines": line_count,
                "data-window-size": window_size,
                "data-lines-before": rolling_cfg.get('lines_before', 250),
                "data-lines-after": rolling_cfg.get('lines_after', 249),
                "data-prefetch-threshold": rolling_cfg.get('prefetch_threshold', 125),
                "data-initial-loaded": "true"
            }
        ),
        dcc.Store(id=f"temp-file-info-{session_id}", data={
            "file_path": temp_file_path,
            "total_lines": line_count,
            "session_id": session_id,
        }),
        dcc.Store(id=f"current-window-{session_id}", data={
            "start_line": 1,
            "end_line": min(500, line_count),
            "total_lines": line_count
        }),
        html.Div(id=f"rolling-bootstrap-{session_id}"),
    ])
    
    # 记录会话高亮信息，供滚动窗口分片渲染使用
    try:
        keywords_to_highlight = []
        keyword_to_color = {}
        if selected_strings and data and isinstance(data, dict) and "categories" in data:
            categories = sorted(list(data["categories"].keys()))
            if categories:
                category_colors = get_category_colors(categories)
                keyword_to_category = {}
                for category, strings in data["categories"].items():
                    for s in strings:
                        keyword_to_category[s] = category
                for item in selected_strings:
                    if isinstance(item, dict):
                        stext = item.get("text")
                    else:
                        stext = item
                    
                    if stext in keyword_to_category:
                        keywords_to_highlight.append(stext)
                    else:
                        keywords_to_highlight.append(stext)
                        if "Temp" not in category_colors:
                            category_colors["Temp"] = "#ffc107"
                        keyword_to_category[stext] = "Temp"

                # Use shared helper to calculate colors, supporting single-category multi-color mode
                keyword_to_color = calculate_highlight_color_map(selected_strings, keywords_to_highlight, keyword_to_category, category_colors)
        highlight_session_info[session_id] = {
            "keywords": sorted(set(keywords_to_highlight), key=len, reverse=True),
            "colors": keyword_to_color
        }
        print(f"[滚动窗口] 已记录会话高亮信息, session: {session_id}, 关键字数: {len(highlight_session_info[session_id]['keywords'])}")
    except Exception as _e:
        print(f"[滚动窗口] 记录会话高亮信息失败: {_e}")
    
    print(f"[滚动窗口] 滚动窗口组件已创建，session_id: {session_id}")
    return result_display


def execute_filter_logic(selected_strings, temp_keywords, selected_log_file, preferred_backend="auto"):
    """执行过滤逻辑，包含临时关键字（异步流式过滤）"""
    # 合并选中的字符串和临时关键字
    normalized_temp_keywords = normalize_temp_keywords(temp_keywords)
    all_strings = []
    if selected_strings:
        all_strings.extend(selected_strings)
    all_strings.extend(normalized_temp_keywords)
    
    # 提取保留字符串和过滤字符串
    keep_strings = []
    filter_strings = []
    for item in all_strings:
        if isinstance(item, dict):
            if item.get("type") == "keep":
                keep_strings.append(item["text"])
            else:
                filter_strings.append(item["text"])
        else:
            keep_strings.append(item)
    
    if not selected_log_file:
        return "", html.P("请选择日志文件", className="text-danger text-center")
    log_path = get_log_path(selected_log_file)
    data = load_data()
    
    # session_id 基于文件和关键字，保证同配置复用滚动会话
    try:
        session_key = f"{log_path}:{keep_strings}:{filter_strings}:{time.time()}"
        session_id = hashlib.md5(session_key.encode()).hexdigest()
    except Exception:
        session_id = hashlib.md5(str(time.time()).encode()).hexdigest()
    
    # 初始化任务并启动后台线程
    _init_filter_task(session_id, log_path, keep_strings, filter_strings, all_strings, preferred_backend=preferred_backend)
    thread = threading.Thread(target=_filter_worker, args=(session_id, log_path, keep_strings, filter_strings, preferred_backend))
    thread.daemon = True
    thread.start()
    
    progress_component = html.Div([
        html.Div(id="filter-partial-display")
    ])
    
    # 返回 session_id 用于前端轮询
    return session_id, progress_component


def _start_filter_task_for_log(selected_strings, temp_keywords, selected_log_file, session_prefix="", preferred_backend="auto"):
    normalized_temp_keywords = normalize_temp_keywords(temp_keywords)
    all_strings = []
    if selected_strings:
        all_strings.extend(selected_strings)
    all_strings.extend(normalized_temp_keywords)

    keep_strings = []
    filter_strings = []
    for item in all_strings:
        if isinstance(item, dict):
            if item.get("type") == "keep":
                keep_strings.append(item.get("text"))
            else:
                filter_strings.append(item.get("text"))
        else:
            keep_strings.append(item)

    if not selected_log_file:
        return ""

    log_path = get_log_path(selected_log_file)
    try:
        session_key = f"{session_prefix}:{log_path}:{keep_strings}:{filter_strings}:{time.time()}"
        session_id = hashlib.md5(session_key.encode()).hexdigest()
    except Exception:
        session_id = hashlib.md5(str(time.time()).encode()).hexdigest()

    _init_filter_task(session_id, log_path, keep_strings, filter_strings, all_strings, preferred_backend=preferred_backend)
    thread = threading.Thread(target=_filter_worker, args=(session_id, log_path, keep_strings, filter_strings, preferred_backend))
    thread.daemon = True
    thread.start()
    return session_id


def _read_lines_for_diff(file_path, encoding, max_lines=20000):
    lines = []
    total = 0
    truncated = False
    try:
        with open(file_path, 'rb') as f:
            for raw in f:
                total += 1
                if len(lines) < max_lines:
                    try:
                        s = raw.decode(encoding)
                    except Exception:
                        s = raw.decode(encoding, errors='replace')
                    if not s.endswith("\n"):
                        s += "\n"
                    lines.append(s)
                else:
                    truncated = True
    except Exception:
        return [], 0, False
    return lines, total, truncated


def build_side_by_side_diff(a_lines, b_lines, max_display_lines=10000, ignore_prefix_length=0):
    """
    生成 Beyond Compare 风格的左右对比显示
    返回: (left_content, right_content, add_cnt, del_cnt, mod_cnt)
    
    Args:
        a_lines: 日志A的行列表
        b_lines: 日志B的行列表
        max_display_lines: 最大显示行数
        ignore_prefix_length: 对比时忽略每行开头的字符数（用于忽略时间戳等）
    """
    import difflib
    
    # 如果设置了忽略前缀，创建用于比较的行列表（去掉前缀）
    if ignore_prefix_length > 0:
        a_compare = [line[ignore_prefix_length:] if len(line) > ignore_prefix_length else line for line in a_lines]
        b_compare = [line[ignore_prefix_length:] if len(line) > ignore_prefix_length else line for line in b_lines]
    else:
        a_compare = a_lines
        b_compare = b_lines
    
    # 使用 SequenceMatcher 进行行级对比（使用处理后的行进行比较）
    matcher = difflib.SequenceMatcher(None, a_compare, b_compare)
    
    left_rows = []
    right_rows = []
    add_cnt = 0
    del_cnt = 0
    mod_cnt = 0
    
    line_num_a = 0
    line_num_b = 0
    display_count = 0
    
    # 样式定义
    style_normal = {"padding": "1px 8px", "borderBottom": "1px solid #eee", "minHeight": "18px", "whiteSpace": "pre", "display": "flex"}
    style_deleted = {"padding": "1px 8px", "borderBottom": "1px solid #eee", "minHeight": "18px", "whiteSpace": "pre", "display": "flex", "backgroundColor": "#ffdddd"}
    style_added = {"padding": "1px 8px", "borderBottom": "1px solid #eee", "minHeight": "18px", "whiteSpace": "pre", "display": "flex", "backgroundColor": "#ddffdd"}
    style_modified_left = {"padding": "1px 8px", "borderBottom": "1px solid #eee", "minHeight": "18px", "whiteSpace": "pre", "display": "flex", "backgroundColor": "#fff3cd"}
    style_modified_right = {"padding": "1px 8px", "borderBottom": "1px solid #eee", "minHeight": "18px", "whiteSpace": "pre", "display": "flex", "backgroundColor": "#d4edda"}
    style_empty = {"padding": "1px 8px", "borderBottom": "1px solid #eee", "minHeight": "18px", "whiteSpace": "pre", "display": "flex", "backgroundColor": "#f5f5f5"}
    style_line_num = {"color": "#999", "minWidth": "50px", "textAlign": "right", "paddingRight": "8px", "borderRight": "1px solid #ddd", "marginRight": "8px", "userSelect": "none"}
    style_content = {"flex": "1", "overflow": "hidden", "textOverflow": "ellipsis"}
    
    def make_line(line_num, text, row_style, is_empty=False):
        """创建一行的显示"""
        text_display = text.rstrip('\n\r') if text else ""
        return html.Div([
            html.Span(str(line_num) if line_num else "", style=style_line_num),
            html.Span(text_display if not is_empty else "", style=style_content)
        ], style=row_style)
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if display_count >= max_display_lines:
            # 添加截断提示
            left_rows.append(html.Div("... (显示已截断)", style={"padding": "8px", "color": "#999", "textAlign": "center"}))
            right_rows.append(html.Div("... (显示已截断)", style={"padding": "8px", "color": "#999", "textAlign": "center"}))
            break
            
        if tag == 'equal':
            # 相同的行
            for i in range(i2 - i1):
                if display_count >= max_display_lines:
                    break
                line_num_a += 1
                line_num_b += 1
                left_rows.append(make_line(line_num_a, a_lines[i1 + i], style_normal))
                right_rows.append(make_line(line_num_b, b_lines[j1 + i], style_normal))
                display_count += 1
                
        elif tag == 'delete':
            # A中有但B中没有的行（删除）
            for i in range(i2 - i1):
                if display_count >= max_display_lines:
                    break
                line_num_a += 1
                del_cnt += 1
                left_rows.append(make_line(line_num_a, a_lines[i1 + i], style_deleted))
                right_rows.append(make_line(None, "", style_empty, is_empty=True))
                display_count += 1
                
        elif tag == 'insert':
            # B中有但A中没有的行（新增）
            for i in range(j2 - j1):
                if display_count >= max_display_lines:
                    break
                line_num_b += 1
                add_cnt += 1
                left_rows.append(make_line(None, "", style_empty, is_empty=True))
                right_rows.append(make_line(line_num_b, b_lines[j1 + i], style_added))
                display_count += 1
                
        elif tag == 'replace':
            # 修改的行
            # 先处理配对的行
            len_a = i2 - i1
            len_b = j2 - j1
            min_len = min(len_a, len_b)
            
            for i in range(min_len):
                if display_count >= max_display_lines:
                    break
                line_num_a += 1
                line_num_b += 1
                mod_cnt += 1
                left_rows.append(make_line(line_num_a, a_lines[i1 + i], style_modified_left))
                right_rows.append(make_line(line_num_b, b_lines[j1 + i], style_modified_right))
                display_count += 1
            
            # 处理A中多出的行
            for i in range(min_len, len_a):
                if display_count >= max_display_lines:
                    break
                line_num_a += 1
                del_cnt += 1
                left_rows.append(make_line(line_num_a, a_lines[i1 + i], style_deleted))
                right_rows.append(make_line(None, "", style_empty, is_empty=True))
                display_count += 1
            
            # 处理B中多出的行
            for i in range(min_len, len_b):
                if display_count >= max_display_lines:
                    break
                line_num_b += 1
                add_cnt += 1
                left_rows.append(make_line(None, "", style_empty, is_empty=True))
                right_rows.append(make_line(line_num_b, b_lines[j1 + i], style_added))
                display_count += 1
    
    left_content = html.Div(left_rows)
    right_content = html.Div(right_rows)
    
    return left_content, right_content, add_cnt, del_cnt, mod_cnt


# 过滤进度轮询
@app.callback(
    [Output("filter-progress-bar", "value", allow_duplicate=True),
     Output("filter-progress-text", "children", allow_duplicate=True),
     Output("filter-backend-display", "children", allow_duplicate=True),
     Output("filter-partial-display", "children", allow_duplicate=True),
     Output("filter-progress-inline", "children", allow_duplicate=True),
     Output("filter-progress-footer", "style", allow_duplicate=True),
     Output("filter-progress-interval", "disabled", allow_duplicate=True),
     Output("filter-session-store", "data", allow_duplicate=True),
     Output("filter-first-chunk-ready", "data", allow_duplicate=True),
     Output("log-filter-results", "children", allow_duplicate=True),
     Output("filtered-result-store", "data", allow_duplicate=True),
     Output(_UI_BUSY_STORE_ID, "data", allow_duplicate=True)],
    [Input("filter-progress-interval", "n_intervals")],
    [State("filter-session-store", "data"),
     State("main-tabs", "active_tab")],
    prevent_initial_call=True
)
def poll_filter_progress(n_intervals, session_id, active_tab):
    progress_footer_show = {"display": "block"}
    progress_footer_hide = {"display": "none"}
    if active_tab != "tab-1" or not session_id:
        print(f"[进度] 跳过轮询 active_tab={active_tab} session_id={session_id}")
        return (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, True,
                dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update)
    
    task = _get_filter_task(session_id)
    if not task:
        print(f"[进度] session={session_id} 未找到任务(可能是旧轮询)，暂不停止轮询")
        return (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update)
    backend_text = _format_filter_backend_text(task.get("backend"), task.get("preferred_backend"))
    
    # 错误处理
    if task.get("status") == "error":
        err_div = html.Div([
            html.P("过滤失败:", className="text-danger"),
            html.Pre(task.get("error"), className="text-danger small")
        ])
        print(f"[进度] session={session_id} 状态=error, err={task.get('error')}")
        return (0, "过滤失败", backend_text, err_div, "", progress_footer_show, True, "", True, err_div, err_div,
                _make_log_view_ui_state("error"))
    
    done = task.get("done_lines") or 0
    total = task.get("total_lines")
    percent = min(100, int(done / total * 100)) if total else None
    progress_text = f"{done} 行" + (f"/约{total}行" if total else "")
    print(f"[进度] tick session={session_id} status={task.get('status')} done={done} total={total} first_ready={task.get('first_ready')} finished={task.get('finished')} first_chunk={task.get('first_ready')} progress_bar={(percent if percent is not None else 'NA')}")
    
    # 首片就绪但未完成
    if task.get("first_ready") and not task.get("finished"):
        encoding = task.get("encoding") or "utf-8"
        chunk_text = _read_partial_lines(task.get("temp_file"), encoding, _FILTER_CHUNK_LINES)
        data = load_data()
        partial_display = highlight_keywords_dash(chunk_text, task.get("selected_strings"), data)
        print(f"[进度] session={session_id} 首片已就绪，返回部分内容，percent={percent}")
        return (percent if percent is not None else 1, progress_text, backend_text, partial_display, "", progress_footer_show, False, session_id, True,
                dash.no_update, dash.no_update, _make_log_view_ui_state("filter_partial_ready"))
    
    # 完成
    if task.get("finished"):
        temp_file = task.get("temp_file")
        idx_file = task.get("idx_file")
        encoding = task.get("encoding") or "utf-8"
        line_count = done or task.get("total_lines") or 0
        data = load_data()
        selected_strings = task.get("selected_strings")
        # Always use rolling display to ensure search/jump functionality works
        final_display = build_rolling_display(temp_file, line_count, session_id, selected_strings, data, encoding)
        print(f"[进度] session={session_id} 完成，行数={line_count}，停止轮询")
        inline_progress = ""  # 完成后隐藏内联进度条
        return (100, "完成", backend_text, dash.no_update, inline_progress, progress_footer_hide, True, "", "",
                final_display, final_display, _make_log_view_ui_state("filter_done"))
    
    # 仍在进行，但未到首片
    inline_progress = ""  # 不再显示顶部内联进度条
    return (percent, progress_text, backend_text, dash.no_update, inline_progress, progress_footer_show, False, session_id, dash.no_update,
            dash.no_update, dash.no_update, _make_log_view_ui_state("filter_running"))


@app.callback(
    [Output("compare-session-store", "data"),
     Output("compare-progress-interval", "disabled"),
     Output("compare-progress-interval", "n_intervals"),
     Output("compare-loading-spinner", "spinner_style"),
     Output("compare-btn-text", "children"),
     Output("compare-execute-btn", "disabled"),
     Output("compare-progress-a", "value"),
     Output("compare-progress-b", "value"),
     Output("compare-progress-text-a", "children"),
     Output("compare-progress-text-b", "children"),
     Output("compare-diff-summary", "children"),
     Output("compare-diff-results", "children"),
     Output("compare-progress-container", "style"),
     Output("toast-container", "children", allow_duplicate=True)],
    [Input("compare-execute-btn", "n_clicks")],
    [State("compare-tab-strings-store", "data"),
     State("temp-keywords-store", "data"),
     State("compare-log-file-a-selector", "value"),
     State("compare-log-file-b-selector", "value"),
     State("compare-session-store", "data"),
     State("filter-backend-selector", "value"),
     State("main-tabs", "active_tab")],
    prevent_initial_call=True
)
def start_compare(n_clicks, compare_strings, temp_keywords, log_a, log_b, existing_sessions, preferred_backend, active_tab):
    preferred_backend = preferred_backend or DEFAULT_FILTER_BACKEND
    if active_tab != "tab-compare" or not n_clicks:
        return (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update)

    if not log_a or not log_b:
        return (dash.no_update, dash.no_update, dash.no_update,
                {"display": "none", "marginLeft": "5px"}, "过滤并对比", False,
                dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, html.Script("if(window.showToast) window.showToast('请选择两份日志文件', 'warning');"))

    if existing_sessions and isinstance(existing_sessions, dict):
        sid_a = existing_sessions.get("a")
        sid_b = existing_sessions.get("b")
        if sid_a:
            _clear_filter_task(sid_a, delete_files=False)
        if sid_b:
            _clear_filter_task(sid_b, delete_files=False)

    session_a = _start_filter_task_for_log(compare_strings, temp_keywords, log_a, session_prefix="compare:A", preferred_backend=preferred_backend)
    session_b = _start_filter_task_for_log(compare_strings, temp_keywords, log_b, session_prefix="compare:B", preferred_backend=preferred_backend)
    if not session_a or not session_b:
        return (dash.no_update, True, 0,
                {"display": "none", "marginLeft": "5px"}, "过滤并对比", False,
                0, 0, "", "", "", "",
                {"display": "none"}, html.Script("if(window.showToast) window.showToast('启动对比失败', 'error');"))

    return (
        {"a": session_a, "b": session_b},
        False,
        0,
        {"display": "inline-block", "marginLeft": "5px"},
        "处理中...",
        True,
        0,
        0,
        "",
        "",
        "",
        "",
        {"display": "block"},  # 显示进度条
        dash.no_update
    )


@app.callback(
    [Output("compare-progress-a", "value", allow_duplicate=True),
     Output("compare-progress-b", "value", allow_duplicate=True),
     Output("compare-progress-text-a", "children", allow_duplicate=True),
     Output("compare-progress-text-b", "children", allow_duplicate=True),
     Output("compare-diff-summary", "children", allow_duplicate=True),
     Output("compare-diff-results", "children", allow_duplicate=True),
     Output("compare-progress-interval", "disabled", allow_duplicate=True),
     Output("compare-loading-spinner", "spinner_style", allow_duplicate=True),
     Output("compare-btn-text", "children", allow_duplicate=True),
     Output("compare-execute-btn", "disabled", allow_duplicate=True),
     Output("compare-progress-container", "style", allow_duplicate=True)],
    [Input("compare-progress-interval", "n_intervals")],
    [State("compare-session-store", "data"),
     State("compare-log-file-a-selector", "value"),
     State("compare-log-file-b-selector", "value"),
     State("compare-ignore-prefix-length", "value"),
     State("main-tabs", "active_tab")],
    prevent_initial_call=True
)
def poll_compare_progress(n_intervals, sessions, log_a, log_b, ignore_prefix_length, active_tab):
    spinner_hide = {"display": "none", "marginLeft": "5px"}
    progress_hide = {"display": "none"}
    if active_tab != "tab-compare":
        return (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                True, spinner_hide, "过滤并对比", False, progress_hide)

    if not sessions or not isinstance(sessions, dict):
        return (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                True, spinner_hide, "过滤并对比", False, progress_hide)

    sid_a = sessions.get("a")
    sid_b = sessions.get("b")
    if not sid_a or not sid_b:
        return (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                True, spinner_hide, "过滤并对比", False, progress_hide)

    task_a = _get_filter_task(sid_a)
    task_b = _get_filter_task(sid_b)
    if not task_a or not task_b:
        return (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update)

    if task_a.get("status") == "error" or task_b.get("status") == "error":
        err_a = task_a.get("error") if task_a.get("status") == "error" else ""
        err_b = task_b.get("error") if task_b.get("status") == "error" else ""
        msg = "对比失败"
        if err_a or err_b:
            msg = f"对比失败: {err_a or err_b}"
        return (0, 0, "过滤失败", "过滤失败",
                msg, html.Pre(msg, className="small text-danger"),
                True, spinner_hide, "过滤并对比", False, progress_hide)

    def _pct(task):
        done = task.get("done_lines") or 0
        total = task.get("total_lines")
        if total:
            return min(100, int(done / total * 100)), f"{done} 行/约{total}行"
        return (1 if done else 0), f"{done} 行"

    pct_a, txt_a = _pct(task_a)
    pct_b, txt_b = _pct(task_b)

    if task_a.get("finished") and task_b.get("finished"):
        temp_a = task_a.get("temp_file")
        temp_b = task_b.get("temp_file")
        enc_a = task_a.get("encoding") or "utf-8"
        enc_b = task_b.get("encoding") or "utf-8"

        max_lines = 20000
        a_lines, a_total, a_trunc = _read_lines_for_diff(temp_a, enc_a, max_lines=max_lines)
        b_lines, b_total, b_trunc = _read_lines_for_diff(temp_b, enc_b, max_lines=max_lines)

        if not a_lines and not b_lines:
            empty_content = html.Div([
                html.Div([
                    html.Div([
                        html.Strong("日志A", className="me-2"),
                        html.Span(str(log_a or ""), className="text-muted small")
                    ], style={"flex": "1", "padding": "8px 12px", "backgroundColor": "#e9ecef", "borderRight": "1px solid #dee2e6", "fontFamily": "sans-serif"}),
                    html.Div([
                        html.Strong("日志B", className="me-2"),
                        html.Span(str(log_b or ""), className="text-muted small")
                    ], style={"flex": "1", "padding": "8px 12px", "backgroundColor": "#e9ecef", "fontFamily": "sans-serif"})
                ], style={"display": "flex", "borderBottom": "2px solid #dee2e6"}),
                html.Div([
                    html.Div("过滤结果为空", style={"flex": "1", "padding": "20px", "textAlign": "center", "color": "#999", "borderRight": "2px solid #dee2e6"}),
                    html.Div("过滤结果为空", style={"flex": "1", "padding": "20px", "textAlign": "center", "color": "#999"})
                ], style={"display": "flex", "maxHeight": "calc(100vh - 380px)", "border": "1px solid #dee2e6", "borderTop": "none"})
            ], style={"border": "1px solid #dee2e6", "borderRadius": "5px", "overflow": "hidden"})
            return (100, 100, "完成", "完成",
                    "过滤结果为空或读取失败", empty_content,
                    True, spinner_hide, "过滤并对比", False, {"display": "none"})

        # 使用左右对比显示（支持忽略行首指定长度）
        prefix_len = int(ignore_prefix_length) if ignore_prefix_length else 0
        left_content, right_content, add_cnt, del_cnt, mod_cnt = build_side_by_side_diff(
            a_lines, b_lines, ignore_prefix_length=prefix_len
        )

        summary = f"日志A: {a_total}行 | 日志B: {b_total}行 | 新增 {add_cnt} 行 / 删除 {del_cnt} 行 / 修改 {mod_cnt} 行"
        if prefix_len > 0:
            summary += f" | 忽略行首 {prefix_len} 字符"
        if a_trunc or b_trunc:
            summary += f"（单侧最多读取 {max_lines} 行，建议收窄关键字）"

        # 构建完整的左右对比布局
        diff_display = html.Div([
            # 左右对比容器
            html.Div([
                # 左右标题栏
                html.Div([
                    html.Div([
                        html.Strong("日志A", className="me-2"),
                        html.Span(str(log_a or ""), className="text-muted small")
                    ], style={"flex": "1", "padding": "8px 12px", "backgroundColor": "#e9ecef", "borderRight": "1px solid #dee2e6", "fontFamily": "sans-serif"}),
                    html.Div([
                        html.Strong("日志B", className="me-2"),
                        html.Span(str(log_b or ""), className="text-muted small")
                    ], style={"flex": "1", "padding": "8px 12px", "backgroundColor": "#e9ecef", "fontFamily": "sans-serif"})
                ], style={"display": "flex", "borderBottom": "2px solid #dee2e6"}),
                # 左右内容区域（同步滚动）
                html.Div([
                    # 左侧内容
                    html.Div(left_content, id="compare-diff-left", style={
                        "flex": "1",
                        "overflowY": "auto",
                        "overflowX": "auto",
                        "backgroundColor": "#fafafa",
                        "borderRight": "2px solid #dee2e6",
                        "fontFamily": "monospace",
                        "fontSize": "12px",
                        "lineHeight": "1.4"
                    }),
                    # 右侧内容
                    html.Div(right_content, id="compare-diff-right", style={
                        "flex": "1",
                        "overflowY": "auto",
                        "overflowX": "auto",
                        "backgroundColor": "#fafafa",
                        "fontFamily": "monospace",
                        "fontSize": "12px",
                        "lineHeight": "1.4"
                    })
                ], id="compare-diff-content", style={
                    "display": "flex",
                    "maxHeight": "calc(100vh - 380px)",
                    "border": "1px solid #dee2e6",
                    "borderTop": "none"
                })
            ], style={"border": "1px solid #dee2e6", "borderRadius": "5px", "overflow": "hidden"}),
            # 同步滚动的逻辑现已移至 assets/compare_sync.js
        ])

        return (100, 100, "完成", "完成",
                summary, diff_display,
                True, spinner_hide, "过滤并对比", False, {"display": "none"})

    return (pct_a, pct_b, txt_a, txt_b,
            dash.no_update, dash.no_update,
            False, dash.no_update, dash.no_update, dash.no_update, dash.no_update)

def execute_source_logic(selected_log_file, selected_strings=None, temp_keywords=None):
    """执行源文件逻辑，包含临时关键字"""
    # 本地方式显示源文件
    if not selected_log_file:
        return "", html.P("请选择日志文件", className="text-danger text-center")
    log_path = get_log_path(selected_log_file)
    
    # 合并选中的字符串和临时关键字
    normalized_temp_keywords = normalize_temp_keywords(temp_keywords)
    all_strings = []
    if selected_strings:
        all_strings.extend(selected_strings)
    all_strings.extend(normalized_temp_keywords)
    
    try:
        session_key = f"source:{log_path}"
        session_id = hashlib.md5(session_key.encode()).hexdigest()
    except Exception:
        session_id = None

    encoding = detect_file_encoding(log_path)
    temp_file_path = get_temp_file_path(session_id)
    idx_path = get_temp_index_path(temp_file_path)
    temp_file_path, idx_path, line_count, output_encoding, backend = _copy_source_to_temp(
        log_path,
        temp_file_path,
        idx_path,
        encoding,
        500
    )
    data = load_data() if all_strings else None
    result_display = build_rolling_display(temp_file_path, line_count, session_id, all_strings, data, output_encoding)
    return f"{backend}:{log_path}", result_display


def execute_source_preview(selected_log_file, selected_strings=None, temp_keywords=None, max_lines=_SOURCE_PREVIEW_LINES):
    """源文件tab预览：前 max_lines 行，并计算总行数便于跳转/提示"""
    if not selected_log_file:
        return "", html.P("请选择日志文件", className="text-danger text-center")
    log_path = get_log_path(selected_log_file)
    try:
        total_lines = get_file_line_count(log_path)
    except Exception:
        total_lines = None
    preview_end = max_lines if total_lines is None else min(max_lines, total_lines)

    # 合并选中的字符串和临时关键字
    normalized_temp_keywords = normalize_temp_keywords(temp_keywords)
    all_strings = []
    if selected_strings:
        all_strings.extend(selected_strings)
    all_strings.extend(normalized_temp_keywords)

    content_text, encoding = get_file_lines_range(log_path, 1, preview_end)
    if all_strings:
        data = load_data()
        result_display = html.Div([
            html.P(f"预览前 {preview_end} 行" + (f"/共约 {total_lines} 行" if total_lines else ""), className="text-muted small"),
            highlight_keywords_dash(content_text, all_strings, data)
        ])
    else:
        result_display = html.Div([
            html.P(f"预览前 {preview_end} 行" + (f"/共约 {total_lines} 行" if total_lines else ""), className="text-muted small"),
            html.Pre(content_text, className="small")
        ])

    return f"preview:{log_path}", result_display

def _run_command_capture_text(command):
    """执行命令并返回解码后的文本（最佳努力解码）"""
    try:
        result = subprocess.run(_normalize_command_args(command), capture_output=True, text=False, timeout=30)
        output_bytes = result.stdout if result.returncode == 0 else b""
        if not output_bytes:
            return ""
        for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1', 'iso-8859-1']:
            try:
                return output_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
        return output_bytes.decode('latin-1', errors='replace')
    except Exception as e:
        print(f"提取注释执行命令失败: {e}")
        return ""

def _extract_notes_from_text(text, annotations_map):
    """基于注释映射从文本中按行提取注释列表：若注释为空，回退显示关键字本身"""
    if not text or not annotations_map:
        return []
    # 使用全部关键字；若注释为空则使用关键字本身
    keyword_to_note = {}
    for k, v in (annotations_map or {}).items():
        if not str(k):
            continue
        note_text = v if (v is not None and str(v) != "") else str(k)
        keyword_to_note[str(k)] = str(note_text)
    if not keyword_to_note:
        return []
    # 关键字按长度降序，优先匹配长关键字
    sorted_keywords = sorted(keyword_to_note.keys(), key=len, reverse=True)
    notes = []
    for line in text.split('\n'):
        line_str = line.strip()
        if not line_str:
            continue
        matched_note = None
        for kw in sorted_keywords:
            if kw in line_str:
                matched_note = keyword_to_note.get(kw, kw)
                break
        if matched_note is not None:
            notes.append(matched_note)
    return notes


def _extract_annotation_text_python(log_path, annotations_map):
    keywords = [str(k) for k in (annotations_map or {}).keys() if str(k)]
    if not keywords:
        return ""
    lowered_keywords = [kw.lower() for kw in keywords]
    encoding = detect_file_encoding(log_path)
    matched_lines = []
    with open(log_path, 'r', encoding=encoding, errors='replace') as src:
        for line in src:
            line_text = line.rstrip('\n')
            lowered_line = line_text.lower()
            if any(keyword in lowered_line for keyword in lowered_keywords):
                matched_lines.append(line_text)
    return "\n".join(matched_lines)

def build_annotation_match_command(selected_log_file, annotations_map):
    """构建使用所有注释关键字匹配日志的命令"""
    if not selected_log_file:
        return None
    log_path = get_log_path(selected_log_file)
    keywords = [str(k) for k in (annotations_map or {}).keys() if str(k)]
    if not keywords:
        return None
    if os.name == 'nt':
        if not _can_use_windows_powershell():
            return None
        patterns = "@(" + ", ".join(_powershell_quote(keyword) for keyword in keywords) + ")"
        script = "\n".join([
            f"$inputPath = {_powershell_quote(log_path)}",
            f"$patterns = {patterns}",
            "Get-Content -LiteralPath $inputPath | Select-String -SimpleMatch -CaseSensitive:$false -Pattern $patterns | ForEach-Object { $_.Line }"
        ])
        return _build_powershell_encoded_command(script)
    rg_cmd = _get_rg_command()
    if rg_cmd:
        return _build_arg_command([rg_cmd, "--text", "--no-heading", "--color", "never", "-i", "-F"], keywords, log_path=log_path)
    if shutil.which("grep"):
        return _build_arg_command(["grep", "-a", "-i", "-F"], keywords, log_path=log_path)
    return None

def build_annotation_extract_display_by_matching(selected_log_file, annotations_map):
    """使用所有注释关键字匹配日志并显示对应注释列表"""
    if not selected_log_file:
        return html.P("请选择日志文件", className="text-danger text-center")
    if not annotations_map:
        return html.P("未设置关键字注释", className="text-muted")
    log_path = get_log_path(selected_log_file)
    cmd = build_annotation_match_command(selected_log_file, annotations_map)
    if not cmd:
        text = _extract_annotation_text_python(log_path, annotations_map)
    else:
        text = _run_command_capture_text(cmd)
    if not text:
        return html.P("没有匹配到任何日志行", className="text-muted")
    notes = _extract_notes_from_text(text, annotations_map)
    if not notes:
        return html.P("未匹配到注释", className="text-muted")
    content = "\n".join(notes)
    return html.Pre(content, className="small")

def _flow_keyword_matches(line: str, keyword) -> bool:
    """流程关键字匹配：支持字符串、正则、AND 组合。
    支持格式：
      - 普通字符串：子串匹配（不区分大小写）
      - "re:..."：正则 search（不区分大小写）
      - "A && B && C"：同一行需要同时包含所有项（不区分大小写）
      - "all: A B C"：同上，空格分隔多个项
      - 对象 {"regex": "..."} 或 {"allOf": ["A","B",...]}
    """
    try:
        if not keyword:
            return False
        s = line or ""
        # dict 形式
        if isinstance(keyword, dict):
            if 'regex' in keyword and isinstance(keyword['regex'], str):
                pattern = keyword['regex']
                try:
                    return re.search(pattern, s, re.IGNORECASE) is not None
                except Exception:
                    return False
            if 'allOf' in keyword and isinstance(keyword['allOf'], list):
                terms = [str(t).strip().lower() for t in keyword['allOf'] if str(t).strip()]
                ls = s.lower()
                return all(t in ls for t in terms)
            if 'text' in keyword and isinstance(keyword['text'], str):
                return keyword['text'].lower() in s.lower()
            return False

        # 字符串形式
        ks = str(keyword).strip()
        if not ks:
            return False
        # 正则：前缀 re:
        if ks.startswith('re:'):
            pattern = ks[3:].strip()
            try:
                return re.search(pattern, s, re.IGNORECASE) is not None
            except Exception:
                return False
        # AND：使用 && 连接
        if '&&' in ks:
            parts = [p.strip().lower() for p in ks.split('&&') if p.strip()]
            ls = s.lower()
            return all(p in ls for p in parts)
        # AND：使用 all: 前缀 + 空格分隔
        if ks.lower().startswith('all:'):
            rest = ks[4:].strip()
            parts = [p.strip().lower() for p in re.split(r"\s+", rest) if p.strip()]
            ls = s.lower()
            return all(p in ls for p in parts)

        # 默认：子串匹配
        return ks.lower() in s.lower()
    except Exception:
        return False


# ---------- AI 流程状态分析 ----------

def read_filtered_log_text(session_id, max_lines=3000):
    """读取过滤后的日志文本内容用于 AI 分析"""
    if not session_id:
        return None
    temp_file = get_temp_file_path(session_id)
    if not os.path.exists(temp_file):
        return None
    encoding = detect_file_encoding(temp_file)
    try:
        with open(temp_file, 'r', encoding=encoding, errors='replace') as f:
            lines = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                lines.append(line)
            return "".join(lines)
    except Exception as e:
        print(f"[AI流程] 读取过滤结果失败: {e}")
        return None


def ai_analyze_flow_status(filtered_text, config_group, config_files):
    """调用 AI 分析过滤后日志中的流程运行状态。
    返回 dict: {"response": str, "prompt": str, "input_file": str} 或 None"""
    if not filtered_text or not filtered_text.strip():
        return None

    import uuid
    ensure_temp_dir()
    input_file = os.path.join(TEMP_DIR, f"ai_flow_input_{uuid.uuid4().hex[:8]}.txt")
    try:
        with open(input_file, 'w', encoding='utf-8') as f:
            f.write(f"# LogFilter AI Flow Analysis Input\n")
            if config_group:
                f.write(f"# 配置组: {config_group}\n")
            if config_files:
                f.write(f"# 关联配置文件: {config_files}\n")
            f.write(f"# 共 {len(filtered_text.splitlines())} 行\n\n")
            f.write(filtered_text)
    except Exception as e:
        print(f"[AI流程] 写入临时文件失败: {e}")
        return None

    config_info = f"配置组: {config_group}" if config_group else "未选择配置组"
    if config_files:
        config_info += f"\n关联配置文件: {config_files}"

    prompt = f"""你是一个日志流程分析专家。分析日志文件中的过滤后内容，识别其中的业务流程运行状态，并以 JSON 格式返回。

{config_info}

日志文件路径: {input_file}
请使用 read_source_file 工具读取该文件，然后分析其中的日志内容。

请严格按照以下 JSON 格式返回分析结果，只返回纯 JSON，不要包含 markdown 代码块标记:

{{"flows": [
  {{"name": "流程名称", "status": "normal", "reason": "状态说明",
    "steps": [
      {{"name": "步骤名称", "status": "normal", "detail": "匹配到的日志行摘要(10-30字)"}}
    ]
  }}
]}}

状态取值规则:
- normal: 步骤正常完成，无报错
- abnormal: 步骤出现 error/fail/exception 等错误
- warning: 步骤出现 timeout/warning/retry 等异常但不致命

如果日志中无明显可识别的业务流程，返回 {{"flows": []}}。"""
    try:
        response = _run_free_code_text_task(None, prompt, timeout=120)
        return {"response": response, "prompt": prompt, "input_file": input_file}
    except Exception as e:
        print(f"[AI流程] AI 分析调用失败: {e}")
        return None


def _extract_json_block(text):
    """从文本中提取第一个完整的 JSON 对象（支持嵌套大括号）"""
    text = text.strip()
    # 去掉 markdown 代码块包裹
    if text.startswith("```"):
        lines = text.split("\n")
        clean = []
        in_code = False
        for line in lines:
            if line.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                clean.append(line)
        text = "\n".join(clean).strip()
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return None


def parse_ai_flow_response(response_text):
    """解析 AI 返回的流程 JSON 数据"""
    if not response_text or not response_text.strip():
        return None
    block = _extract_json_block(response_text)
    if not block:
        return None
    try:
        data = json.loads(block)
        if isinstance(data, dict) and "flows" in data:
            return data
        return {"flows": []}
    except json.JSONDecodeError:
        return None


def render_flow_chart(flow_data):
    """将 AI 分析的流程数据渲染为可视化流程图"""
    if not flow_data or not isinstance(flow_data, dict):
        return html.Div("AI 分析未返回有效数据", className="text-muted text-center py-3")

    flows = flow_data.get("flows", [])
    if not flows:
        return html.Div("未检测到明显的业务流程", className="text-muted text-center py-3")

    STATUS_MAP = {
        "normal":    {"bg": "#d4edda", "border": "#28a745", "text": "#155724", "badge": "success", "label": "正常"},
        "abnormal":  {"bg": "#f8d7da", "border": "#dc3545", "text": "#721c24", "badge": "danger",  "label": "异常"},
        "warning":   {"bg": "#fff3cd", "border": "#ffc107", "text": "#856404", "badge": "warning", "label": "警告"},
        "unknown":   {"bg": "#e2e3e5", "border": "#6c757d", "text": "#383d41", "badge": "sec",     "label": "未知"},
    }

    def _status_style(s):
        return STATUS_MAP.get(s, STATUS_MAP["unknown"])

    cards = []
    for flow in flows:
        name = flow.get("name", "未知流程") or "未知流程"
        status = flow.get("status", "unknown") or "unknown"
        reason = (flow.get("reason") or "").strip()
        s = _status_style(status)
        steps = flow.get("steps") or []

        step_nodes = []
        for i, step in enumerate(steps):
            sn = (step.get("name") or f"步骤{i+1}").strip()
            ss = (step.get("status") or "unknown").strip()
            sd = (step.get("detail") or "").strip()
            ts = _status_style(ss)

            node = html.Div([
                html.Div(sn, style={"fontWeight": 600, "fontSize": "13px", "lineHeight": "1.3"}),
                html.Div(sd, style={"fontSize": "11px", "color": "#555", "marginTop": "3px",
                                     "maxWidth": "220px", "overflow": "hidden",
                                     "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
                html.Div([
                    html.Span(f"● {ts['label']}", style={"fontSize": "10px", "color": ts["text"]})
                ], style={"marginTop": "4px"})
            ], style={
                "background": ts["bg"],
                "border": f"2px solid {ts['border']}",
                "borderRadius": "10px",
                "padding": "8px 14px",
                "display": "inline-flex",
                "flexDirection": "column",
                "minWidth": "120px",
                "textAlign": "center",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.08)",
            })

            if i < len(steps) - 1:
                step_nodes.append(node)
                step_nodes.append(html.Span("→", style={
                    "fontSize": "22px", "color": "#aaa",
                    "margin": "0 6px", "verticalAlign": "middle",
                    "fontWeight": 300
                }))
            else:
                step_nodes.append(node)

        header_children = [
            html.Span(name, style={"fontWeight": 600, "fontSize": "14px"}),
            html.Span(html.Small(f" ({ts['label']})"), style={"color": ts["text"], "fontSize": "12px", "marginLeft": "6px"}),
        ]
        if reason:
            header_children.append(html.Span(f" — {reason}", style={
                "fontSize": "12px", "color": s["text"], "marginLeft": "10px", "opacity": "0.85"
            }))

        cards.append(html.Div([
            html.Div(header_children, style={
                "background": s["bg"],
                "padding": "8px 14px",
                "borderBottom": f"2px solid {s['border']}",
                "borderRadius": "8px 8px 0 0",
                "display": "flex", "alignItems": "center", "flexWrap": "wrap",
            }),
            html.Div(
                html.Div(step_nodes, style={
                    "display": "flex", "flexWrap": "wrap",
                    "alignItems": "center", "gap": "2px",
                    "padding": "12px 14px"
                }) if steps else
                html.Div("无具体步骤信息", className="text-muted small", style={"padding": "12px 14px"})
            )
        ], style={
            "border": f"1px solid {s['border']}",
            "borderRadius": "8px",
            "marginBottom": "12px",
            "boxShadow": "0 1px 4px rgba(0,0,0,0.06)",
            "overflow": "hidden"
        }))

    return html.Div([
        html.Div(f"共检测到 {len(flows)} 个流程", style={
            "fontSize": "12px", "color": "#888", "marginBottom": "10px"
        }),
        html.Div(cards)
    ])


# ---------- 原有流程视图（基于 flows.json）----------

def build_flows_display(selected_log_file):
    """流程视图：默认显示提示，点击上方 AI 按钮进行分析"""
    return html.Div(
        "点击上方「AI 流程状态分析」按钮进行流程分析",
        className="text-muted text-center py-5",
        style={"fontSize": "13px"}
    )


# ---------- 流程关键字设置 回调 ----------

def _render_paired_list(flows):
    flows = flows or {"paired": [], "sequences": []}
    paired = flows.get('paired') or []
    if not paired:
        return html.P("暂无配对关键字", className="text-muted mb-0")
    rows = []
    for i, item in enumerate(paired):
        name = str((item or {}).get('name') or '')
        start = str((item or {}).get('start') or '')
        end = str((item or {}).get('end') or '')
        rows.append(
            html.Tr([
                html.Td(html.Code(name, className="small")),
                html.Td(html.Code(start, className="small")),
                html.Td(html.Code(end, className="small")),
                html.Td(
                    dbc.Button("删除", id={"type": "paired-del", "index": i}, color="danger", size="sm")
                )
            ])
        )
    return dbc.Table([
        html.Thead(html.Tr([html.Th("名称"), html.Th("开始"), html.Th("结束"), html.Th("操作")])),
        html.Tbody(rows)
    ], bordered=True, hover=True, size="sm", striped=True, className="mb-0")


def _render_sequences_list(flows):
    flows = flows or {"paired": [], "sequences": []}
    sequences = flows.get('sequences') or []
    if not sequences:
        return html.P("暂无序列关键字", className="text-muted mb-0")
    rows = []
    for i, item in enumerate(sequences):
        name = str((item or {}).get('name') or '')
        steps = (item or {}).get('steps') or []
        steps_text = ' -> '.join([str(s) for s in steps])
        rows.append(
            html.Tr([
                html.Td(html.Code(name, className="small")),
                html.Td(html.Div(steps_text, className="small", style={"whiteSpace": "pre-wrap"})),
                html.Td(
                    dbc.Button("删除", id={"type": "seq-del", "index": i}, color="danger", size="sm")
                )
            ])
        )
    return dbc.Table([
        html.Thead(html.Tr([html.Th("名称"), html.Th("步骤"), html.Th("操作")])),
        html.Tbody(rows)
    ], bordered=True, hover=True, size="sm", striped=True, className="mb-0")


@app.callback(
    Output("paired-list-container", "children"),
    [Input("flows-config-store", "data")]
)
def render_paired_list(flows):
    return _render_paired_list(flows)


@app.callback(
    Output("sequences-list-container", "children"),
    [Input("flows-config-store", "data")]
)
def render_sequences_list(flows):
    return _render_sequences_list(flows)


def _parse_steps(text: str):
    if not text:
        return []
    # 支持 '->'、'→'、中文逗号、英文逗号、换行
    parts = re.split(r"\n|->|→|，|,", text)
    steps = [p.strip() for p in parts if p and p.strip()]
    return steps


@app.callback(
    Output("flows-config-store", "data", allow_duplicate=True),
    Output("paired-name", "value", allow_duplicate=True),
    Output("paired-start", "value", allow_duplicate=True),
    Output("paired-end", "value", allow_duplicate=True),
    [Input("paired-add-btn", "n_clicks")],
    [State("paired-name", "value"), State("paired-start", "value"), State("paired-end", "value"), State("flows-config-store", "data")],
    prevent_initial_call=True
)
def add_paired(n_clicks, name, start_kw, end_kw, flows):
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    name = (name or '').strip()
    start_kw = (start_kw or '').strip()
    end_kw = (end_kw or '').strip()
    if not name or not start_kw or not end_kw:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    flows = flows or {"paired": [], "sequences": []}
    paired = flows.get('paired') or []
    paired.append({"name": name, "start": start_kw, "end": end_kw})
    flows['paired'] = paired
    save_flows_config(flows)
    return flows, "", "", ""


@app.callback(
    Output("flows-config-store", "data", allow_duplicate=True),
    [Input({"type": "paired-del", "index": dash.ALL}, "n_clicks")],
    [State({"type": "paired-del", "index": dash.ALL}, "id"), State("flows-config-store", "data")],
    prevent_initial_call=True
)
def delete_paired(n_clicks, ids, flows):
    if not n_clicks or not ids:
        return dash.no_update
    # 找到被点击的按钮索引
    clicked_idx = None
    for i, c in enumerate(n_clicks):
        if c:
            clicked_idx = i
            break
    if clicked_idx is None:
        return dash.no_update
    idx_value = ids[clicked_idx].get('index') if isinstance(ids[clicked_idx], dict) else None
    if idx_value is None:
        return dash.no_update
    flows = flows or {"paired": [], "sequences": []}
    paired = flows.get('paired') or []
    if 0 <= idx_value < len(paired):
        paired.pop(idx_value)
        flows['paired'] = paired
        save_flows_config(flows)
        return flows
    return dash.no_update


@app.callback(
    Output("flows-config-store", "data", allow_duplicate=True),
    Output("seq-name", "value", allow_duplicate=True),
    Output("seq-steps-text", "value", allow_duplicate=True),
    [Input("seq-add-btn", "n_clicks")],
    [State("seq-name", "value"), State("seq-steps-text", "value"), State("flows-config-store", "data")],
    prevent_initial_call=True
)
def add_sequence(n_clicks, name, steps_text, flows):
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update
    name = (name or '').strip()
    steps = _parse_steps(steps_text or '')
    if not name or not steps:
        return dash.no_update, dash.no_update, dash.no_update
    flows = flows or {"paired": [], "sequences": []}
    sequences = flows.get('sequences') or []
    sequences.append({"name": name, "steps": steps})
    flows['sequences'] = sequences
    save_flows_config(flows)
    return flows, "", ""


@app.callback(
    Output("flows-config-store", "data", allow_duplicate=True),
    [Input({"type": "seq-del", "index": dash.ALL}, "n_clicks")],
    [State({"type": "seq-del", "index": dash.ALL}, "id"), State("flows-config-store", "data")],
    prevent_initial_call=True
)
def delete_sequence(n_clicks, ids, flows):
    if not n_clicks or not ids:
        return dash.no_update
    clicked_idx = None
    for i, c in enumerate(n_clicks):
        if c:
            clicked_idx = i
            break
    if clicked_idx is None:
        return dash.no_update
    idx_value = ids[clicked_idx].get('index') if isinstance(ids[clicked_idx], dict) else None
    if idx_value is None:
        return dash.no_update
    flows = flows or {"paired": [], "sequences": []}
    sequences = flows.get('sequences') or []
    if 0 <= idx_value < len(sequences):
        sequences.pop(idx_value)
        flows['sequences'] = sequences
        save_flows_config(flows)
        return flows
    return dash.no_update


# ---------- 正则生成器 回调 ----------

@app.callback(
    Output("regex-output", "value"),
    [Input("regex-generate-btn", "n_clicks")],
    [State("regex-input-keywords", "value"), State("regex-mode", "value"), State("regex-options", "value")],
    prevent_initial_call=True
)
def generate_regex(n_clicks, raw_keywords, mode, options):
    try:
        if not n_clicks:
            return dash.no_update
        text = (raw_keywords or "").strip()
        if not text:
            return ""
        # 分词（空格或换行分隔）
        parts = [p.strip() for p in re.split(r"\s+", text) if p and p.strip()]
        if not parts:
            return ""
        add_prefix = isinstance(options, list) and ("prefix" in options)
        do_escape = not isinstance(options, list) or ("escape" in options)
        tokens = [re.escape(p) if do_escape else p for p in parts]

        pattern = ""
        if mode == "or":
            # (a|b|c)
            pattern = "(" + "|".join(tokens) + ")"
        elif mode == "ordered_lookahead":
            # a.*b.*c （单行匹配）
            pattern = ".*".join(tokens)
        else:
            # and_lookahead: (?=.*a)(?=.*b)(?=.*c)
            pattern = "".join([f"(?=.*{t})" for t in tokens])

        result = f"re:{pattern}" if add_prefix else pattern
        return result
    except Exception as e:
        print(f"生成正则失败: {e}")
        return ""

def get_category_colors(categories):
    """为每个分类生成等间距的独特颜色"""
    import colorsys
    
    category_colors = {}
    num_categories = len(categories)
    
    if num_categories == 0:
        return category_colors
    
    # 使用HSV颜色空间生成等间距的颜色
    # 固定饱和度和亮度，只变化色相
    saturation = 0.8  # 饱和度
    value = 0.9       # 亮度
    
    for i, category in enumerate(categories):
        # 计算等间距的色相值 (0-1之间)
        hue = i / num_categories
        
        # 将HSV转换为RGB
        rgb = colorsys.hsv_to_rgb(hue, saturation, value)
        
        # 将RGB转换为十六进制颜色代码
        hex_color = '#{:02x}{:02x}{:02x}'.format(
            int(rgb[0] * 255),
            int(rgb[1] * 255),
            int(rgb[2] * 255)
        )
        
        category_colors[category] = hex_color
    
    return category_colors

def calculate_highlight_color_map(selected_strings, keywords_to_highlight, keyword_to_category, category_colors):
    """计算会话高亮的颜色映射，支持单分类多色模式"""
    keyword_to_color = {}
    
    # 策略判断：是否启用单分类多色模式
    explicit_cats = set()
    if selected_strings:
        for item in selected_strings:
            if isinstance(item, dict):
                c = item.get("category")
                if c and c not in ["Temp", "Duplicate"]:
                    explicit_cats.add(c)
    
    single_cat_mode = (len(explicit_cats) == 1)
    single_cat_colors = {}
    
    if single_cat_mode:
        single_cat = list(explicit_cats)[0]
        # 获取该分类下的关键字
        single_cat_kws = [kw for kw in keywords_to_highlight if keyword_to_category.get(kw) == single_cat]
        if single_cat_kws:
            unique_kws = sorted(list(set(single_cat_kws)))
            single_cat_colors = get_category_colors(unique_kws)
    
    for kw in keywords_to_highlight:
        # 默认颜色
        color = None
        cat = keyword_to_category.get(kw)
        
        # 尝试单分类多色
        if single_cat_mode and single_cat_colors and cat == list(explicit_cats)[0] and kw in single_cat_colors:
            color = single_cat_colors[kw]
        # 否则使用分类颜色
        elif cat in category_colors:
            color = category_colors[cat]
            
        if color:
            keyword_to_color[kw.lower()] = {
                "bg": color,
                "fg": "#ffffff"
            }
            
    return keyword_to_color

def highlight_keywords(text, selected_strings, data):
    """在文本中高亮显示不同分类的关键字"""
    if not selected_strings or not data or "categories" not in data:
        return text
    
    # 获取所有分类（包括来自配置文件的分类）
    categories = set(data["categories"].keys())
    
    # 从selected_strings中提取额外的分类
    for item in selected_strings:
        if isinstance(item, dict) and "category" in item:
            categories.add(item["category"])
            
    categories = list(categories)
    # 排序以保持颜色稳定性
    categories.sort()
    
    if not categories and not selected_strings:
        return text
    
    # 为每个分类分配颜色
    category_colors = get_category_colors(categories)
    # 构建关键字到分类的映射
    keyword_to_category = {}
    for category, strings in data["categories"].items():
        for string in strings:
            if string not in keyword_to_category:
                keyword_to_category[string] = category
            
    # 从selected_strings中更新映射
    for item in selected_strings:
        if isinstance(item, dict):
            string_text = item["text"]
            if "category" in item:
                keyword_to_category[string_text] = item["category"]
        else:
            string_text = item
            
    # 从选中的字符串中提取需要高亮的关键字
    keywords_to_highlight = []
    for item in selected_strings:
        if isinstance(item, dict):
            string_text = item["text"]
            if "category" in item and string_text not in keyword_to_category:
                keyword_to_category[string_text] = item["category"]
        else:
            string_text = item
        
        # 如果关键字在分类中，或者是临时关键字（不在任何分类中但被选中）
        if string_text in keyword_to_category:
            keywords_to_highlight.append(string_text)
        else:
            # 这是一个临时关键字，给它分配一个默认颜色（例如使用"error"分类的颜色，或者随机颜色）
            # 这里我们简单地将其添加到需要高亮的列表中，并在后面处理颜色
            keywords_to_highlight.append(string_text)
            # 为临时关键字添加默认分类映射，以便后续查找颜色
            # 使用"Temp"作为临时关键字的分类，如果不存在则使用默认颜色
            if "Temp" not in category_colors:
                 # 如果没有Temp分类，使用第一个可用分类的颜色，或者默认颜色
                 category_colors["Temp"] = "#ffc107" # 默认黄色
            keyword_to_category[string_text] = "Temp"
    
    if not keywords_to_highlight:
        return text
    
    # 按长度降序排序，确保长关键字优先匹配
    keywords_to_highlight.sort(key=len, reverse=True)
    
    # -------------------------------------------------------------------------
    # 单一分类多色高亮逻辑
    # -------------------------------------------------------------------------
    # 计算当前实际包含的分类
    active_cats = set()
    for kw in keywords_to_highlight:
        c = keyword_to_category.get(kw)
        if c:
            active_cats.add(c)
            
    real_categories = [c for c in active_cats if c not in ["Temp", "Duplicate"]]

    per_keyword_colors = {}
    
    if len(real_categories) == 1:
        single_cat = real_categories[0]
        # 找出属于该单一分类的关键字
        single_cat_keywords = [
            kw for kw in keywords_to_highlight 
            if keyword_to_category.get(kw) == single_cat
        ]
        if single_cat_keywords:
            unique_kws = sorted(list(set(single_cat_keywords)))
            per_keyword_colors = get_category_colors(unique_kws)

    # 对每个关键字进行高亮处理
    highlighted_text = text
    for keyword in keywords_to_highlight:
        # 优先使用单分类关键字颜色
        color = None
        if keyword in per_keyword_colors:
            color = per_keyword_colors[keyword]
        elif keyword in keyword_to_category:
            category = keyword_to_category[keyword]
            color = category_colors.get(category)
            
        if color:
            # 使用正则表达式进行不区分大小写的匹配
            pattern = re.escape(keyword)
            replacement = f'<span style="background-color: {color}; color: white; padding: 2px 4px; border-radius: 3px; font-weight: bold;">{keyword}</span>'
            
            highlighted_text = re.sub(
                pattern, 
                replacement, 
                highlighted_text, 
                flags=re.IGNORECASE
            )
    
    return highlighted_text

def highlight_keywords_dash(text, selected_strings, data, flat=False):
    """为Dash组件生成高亮显示的组件列表（优化版本）
    flat: 如果为True，返回包含Span和字符串的列表（包裹在Pre中），而不是每行一个Div。
          这对于rolling.js兼容性很重要（rolling.js期望pre直接包含文本/span）。
    """
    start_time = time.time()
    
    if not selected_strings or not data or "categories" not in data:
        result = html.Pre(text, className="small")
        return result
    
    # 性能优化：使用缓存
    cache_key = highlight_cache.get_cache_key(text, selected_strings, data)
    # flat模式使用不同的缓存键
    if flat:
        cache_key += ":flat"
        
    cached_result = highlight_cache.get(cache_key)
    if cached_result:
        return cached_result
    
    # 额外的组合缓存（文件内容 + 关键字列表），减少重复渲染
    def _flatten_strings(strings):
        flat = []
        for item in strings or []:
            if isinstance(item, dict):
                parts = [item.get("type", "keep"), item.get("text", "")]
                if "category" in item:
                    parts.append(item["category"])
                flat.append("|".join(parts))
            else:
                flat.append(str(item))
        return tuple(sorted(flat))

    combo_key = (
        hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest(),
        _flatten_strings(selected_strings),
    )
    combo_cached = _highlight_combo_cache["map"].get(combo_key)
    if combo_cached is not None:
        # LRU bump
        try:
            _highlight_combo_cache["order"].remove(combo_key)
        except ValueError:
            pass
        _highlight_combo_cache["order"].append(combo_key)
        return combo_cached
    
    # 获取所有分类（包括来自配置文件的分类）
    categories = set(data["categories"].keys())
    
    # 从selected_strings中提取额外的分类
    for item in selected_strings:
        if isinstance(item, dict) and "category" in item:
            categories.add(item["category"])
            
    categories = list(categories)
    # 排序以保持颜色稳定性
    categories.sort()

    if not categories and not selected_strings:
        return html.Pre(text, className="small")
    
    # 为每个分类分配颜色
    category_colors = get_category_colors(categories)
    # 添加重复关键字的颜色（偏红色）
    category_colors["Duplicate"] = "#d63031"
    
    # 构建关键字到分类的映射
    keyword_to_category = {}
    for category, strings in data["categories"].items():
        for string in strings:
            keyword_to_category[string] = category
            
    # 从selected_strings中更新映射
    for item in selected_strings:
        if isinstance(item, dict):
            string_text = item["text"]
            if "category" in item:
                keyword_to_category[string_text] = item["category"]
        else:
            string_text = item
            
    # 从选中的字符串中提取需要高亮的关键字
    keywords_to_highlight = []
    for item in selected_strings:
        if isinstance(item, dict):
            string_text = item["text"]
            # 检查是否为重复关键字
            if item.get("count", 1) > 1:
                keyword_to_category[string_text] = "Duplicate"
        else:
            string_text = item
        
        # 临时关键字处理（如果在配置中未找到）
        if string_text not in keyword_to_category:
             if "Temp" not in category_colors:
                 category_colors["Temp"] = "#ffc107" # 默认黄色
             keyword_to_category[string_text] = "Temp"
        
        if string_text in keyword_to_category:
            keywords_to_highlight.append(string_text)
    
    if not keywords_to_highlight:
        result = html.Pre(text, className="small")
        highlight_cache.put(cache_key, result)
        return result
    
    # 按长度降序排序，确保长关键字优先匹配
    keywords_to_highlight.sort(key=len, reverse=True)
    
    
    # -------------------------------------------------------------------------
    # 单一分类多色高亮逻辑
    # -------------------------------------------------------------------------
    # 如果只有一个分类（忽略Temp和Duplicate），则对该分类下的关键字进行多色区分
    # 计算显式选择的分类（基于 selected_strings 中的 dict配置）
    # 忽略临时添加的无分类关键字（Temp）或自动生成的 Duplicate
    explicit_cats = set()
    for item in selected_strings:
        if isinstance(item, dict):
            c = item.get("category")
            if c and c not in ["Temp", "Duplicate"]:
                explicit_cats.add(c)
    
    keyword_color_lookup = {}
    
    # 只要显式选择的分类只有1个，就启用单分类多色模式
    # 即使 keywords_to_highlight 中包含了 Temp 关键字也不影响
    if len(explicit_cats) == 1:
        single_cat = list(explicit_cats)[0]
        # 获取该分类下所有需要高亮的关键字
        single_cat_keywords = [
            kw for kw in keywords_to_highlight 
            if keyword_to_category.get(kw) == single_cat
        ]
        if single_cat_keywords:
            # 为这些关键字生成各自的颜色
            # 使用 set 去重后排序，保证颜色分配一致性
            unique_kws = sorted(list(set(single_cat_keywords)))
            kw_colors = get_category_colors(unique_kws)
            # 更新查找表
            for kw in single_cat_keywords:
                if kw in kw_colors:
                    keyword_color_lookup[kw.lower()] = kw_colors[kw]
    
    # -------------------------------------------------------------------------
    # 常规逻辑（或处理剩余的 Temp/Duplicate/多分类情况）
    # -------------------------------------------------------------------------
    # 补充尚未分配颜色的关键字（多分类情况，或者 Temp/Duplicate）
    for kw in keywords_to_highlight:
        kw_lower = kw.lower()
        if kw_lower not in keyword_color_lookup:
            cat = keyword_to_category.get(kw)
            if cat in category_colors:
                keyword_color_lookup[kw_lower] = category_colors[cat]
    
    # 性能优化：使用单一正则表达式进行匹配
    try:
        # 构建单一正则表达式模式
        pattern_parts = []
        for keyword in keywords_to_highlight:
            escaped_keyword = re.escape(keyword)
            pattern_parts.append(escaped_keyword)
        
        if not pattern_parts:
            result = html.Pre(text, className="small")
            highlight_cache.put(cache_key, result)
            return result
        
        # 创建单一正则表达式（不区分大小写）
        combined_pattern = f"({'|'.join(pattern_parts)})"
        regex = re.compile(combined_pattern, re.IGNORECASE)
        
        # 按行处理文本
        lines = text.split('\n')
        highlighted_lines = []
        flat_elements = [] if flat else None
        
        for line in lines:
            if not line.strip():
                # 空行直接添加
                if flat:
                    flat_elements.append('\n')
                else:
                    highlighted_lines.append(html.Div('\n', style={'whiteSpace': 'pre', 'fontFamily': 'monospace', 'fontSize': '12px'}))
                continue
            
            # 使用单一正则表达式查找所有匹配
            matches = list(regex.finditer(line))
            
            if not matches:
                # 该行没有关键字，直接添加
                if flat:
                    flat_elements.append(line + '\n')
                else:
                    highlighted_lines.append(html.Div(line + '\n', style={'whiteSpace': 'pre', 'fontFamily': 'monospace', 'fontSize': '12px'}))
                continue
            
            # 构建该行的组件
            components = []
            current_pos = 0
            
            for match in matches:
                # 添加匹配前的文本
                if match.start() > current_pos:
                    components.append(line[current_pos:match.start()])
                
                # 获取匹配的关键字和对应的分类颜色
                matched_text = match.group()
                color = keyword_color_lookup.get(matched_text.lower())
                
                if color:
                    # 添加高亮的关键字
                    components.append(
                        html.Span(
                            matched_text,
                            style={
                                'backgroundColor': color,
                                'color': 'white',
                                'padding': '2px 4px',
                                'borderRadius': '3px',
                                'fontWeight': 'bold',
                                'display': 'inline'
                            }
                        )
                    )
                else:
                    # 如果没有找到对应的分类，直接添加文本
                    components.append(matched_text)
                
                current_pos = match.end()
            
            # 添加剩余文本
            if current_pos < len(line):
                components.append(line[current_pos:])
            
            # 添加换行符
            if flat:
                components.append('\n')
                flat_elements.extend(components)
            else:
                components.append('\n')
                # 创建该行的Div组件
                highlighted_lines.append(html.Div(components, style={'whiteSpace': 'pre', 'fontFamily': 'monospace', 'fontSize': '12px'}))
        
        # 返回结果
        if flat:
            result = html.Pre(flat_elements, className="small")
        else:
            result = html.Div(highlighted_lines)
            
        highlight_cache.put(cache_key, result)
        _highlight_combo_cache["map"][combo_key] = result
        _highlight_combo_cache["order"].append(combo_key)
        if len(_highlight_combo_cache["order"]) > _highlight_combo_cache["max"]:
            old_key = _highlight_combo_cache["order"].pop(0)
            _highlight_combo_cache["map"].pop(old_key, None)
        return result
    
    except Exception as e:
        # 如果正则表达式处理失败，回退到简单显示
        print(f"高亮处理失败，使用简单显示: {e}")
        result = html.Pre(text, className="small")
        highlight_cache.put(cache_key, result)
        
        # 性能监控：记录错误处理时间
        end_time = time.time()
        processing_time = end_time - start_time
        print(f"高亮处理失败: {processing_time:.3f}秒")
        
        return result

def get_temp_file_path(session_id=None):
    """获取临时文件路径"""
    ensure_temp_dir()
    if session_id is None:
        session_id = hashlib.md5(str(time.time()).encode()).hexdigest()
    file_path = os.path.join(TEMP_DIR, f"filter_result_{session_id}.txt")
    print(f"[滚动窗口] 生成临时文件路径: {file_path}, session_id: {session_id}")
    return file_path

def get_temp_index_path(temp_file_path):
    """获取临时结果的索引文件路径"""
    return f"{temp_file_path}.idx"

def detect_file_encoding(file_path, default_encoding="utf-8"):
    """读取部分内容推测编码，失败则返回默认编码"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'iso-8859-1']
    try:
        with open(file_path, 'rb') as f:
            sample = f.read(65536)  # 64KB 样本
        for enc in encodings:
            try:
                sample.decode(enc)
                return enc
            except UnicodeDecodeError:
                continue
    except Exception as e:
        print(f"[滚动窗口] 探测编码失败，使用默认编码 {default_encoding}: {e}")
    return default_encoding

def _load_temp_index_metadata(file_path):
    idx_path = get_temp_index_path(file_path)
    if not os.path.exists(idx_path):
        return None
    try:
        with open(idx_path, 'r', encoding='utf-8') as idx_file:
            data = json.load(idx_file)
        if isinstance(data, dict):
            return data
    except Exception as e:
        print(f"[滚动窗口] 读取索引元数据失败: {e}")
    return None


def _get_search_cache_key(file_path, keyword, case_sensitive):
    try:
        stat = os.stat(file_path)
        return (
            os.path.abspath(file_path),
            stat.st_mtime_ns,
            stat.st_size,
            str(keyword or ""),
            bool(case_sensitive)
        )
    except Exception:
        return (
            os.path.abspath(file_path),
            None,
            None,
            str(keyword or ""),
            bool(case_sensitive)
        )


def _get_search_encoding_candidates(file_path, idx_data=None):
    candidates = []
    idx_data = idx_data or {}
    idx_encoding = idx_data.get("encoding")
    if idx_encoding:
        candidates.append(idx_encoding)
    detected = detect_file_encoding(file_path)
    if detected and detected not in candidates:
        candidates.append(detected)
    for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1', 'iso-8859-1']:
        if enc not in candidates:
            candidates.append(enc)
    return candidates


def _can_use_binary_search(keyword, case_sensitive):
    if not keyword:
        return False
    if case_sensitive:
        return True
    return keyword.isascii() or keyword.lower() == keyword.upper()


def _scan_search_matches_binary(file_path, keyword, encodings, case_sensitive, idx_data=None):
    matches = []
    total_lines = int((idx_data or {}).get("line_count") or 0)
    last_error = None
    for enc in encodings:
        try:
            keyword_bytes = str(keyword).encode(enc)
            if not keyword_bytes:
                continue
            regex = re.compile(re.escape(keyword_bytes), 0 if case_sensitive else re.IGNORECASE)
            with open(file_path, 'rb') as f:
                current_total = 0
                for current_total, raw_line in enumerate(f, start=1):
                    if regex.search(raw_line):
                        matches.append(current_total)
                if current_total > 0:
                    total_lines = current_total
            return {
                "matches": matches,
                "total_matches": len(matches),
                "total_lines": total_lines,
                "encoding": enc,
                "mode": "binary"
            }
        except Exception as e:
            matches = []
            last_error = e
            continue
    raise last_error or RuntimeError("二进制搜索初始化失败")


def _scan_search_matches_text(file_path, keyword, encodings, case_sensitive, idx_data=None):
    matches = []
    total_lines = int((idx_data or {}).get("line_count") or 0)
    normalized_keyword = str(keyword or "")
    keyword_probe = normalized_keyword if case_sensitive else normalized_keyword.lower()
    last_error = None
    used_encoding = encodings[0] if encodings else 'utf-8'
    for enc in encodings:
        try:
            used_encoding = enc
            with open(file_path, 'r', encoding=enc, errors='replace') as f:
                current_total = 0
                for current_total, line in enumerate(f, start=1):
                    haystack = line if case_sensitive else line.lower()
                    if keyword_probe in haystack:
                        matches.append(current_total)
                if current_total > 0:
                    total_lines = current_total
            return {
                "matches": matches,
                "total_matches": len(matches),
                "total_lines": total_lines,
                "encoding": used_encoding,
                "mode": "text"
            }
        except Exception as e:
            matches = []
            last_error = e
            continue
    raise last_error or RuntimeError("文本搜索初始化失败")


def _get_search_match_index(file_path, keyword, case_sensitive=False):
    cache_key = _get_search_cache_key(file_path, keyword, case_sensitive)
    cached = search_match_cache.get(cache_key)
    if cached is not None:
        return cached

    idx_data = _load_temp_index_metadata(file_path) or {}
    encoding_candidates = _get_search_encoding_candidates(file_path, idx_data)
    if _can_use_binary_search(str(keyword or ""), case_sensitive):
        result = _scan_search_matches_binary(file_path, keyword, encoding_candidates, case_sensitive, idx_data=idx_data)
    else:
        result = _scan_search_matches_text(file_path, keyword, encoding_candidates, case_sensitive, idx_data=idx_data)
    search_match_cache.put(cache_key, result)
    return result


def get_file_line_count(file_path):
    try:
        idx_data = _load_temp_index_metadata(file_path)
        if idx_data and isinstance(idx_data.get("line_count"), int):
            count = max(0, int(idx_data.get("line_count") or 0))
            return count
        with open(file_path, 'rb') as f:
            count = sum(1 for _ in f)
        return count
    except Exception as e:
        print(f"[滚动窗口] 获取文件行数失败: {e}")
        return 0

def get_file_lines_range(file_path, start_line, end_line, encoding=None):
    """获取文件的指定行范围（1-based index）
    
    Returns:
        tuple: (内容字符串, 检测到的编码)
    """
    try:
        if start_line > end_line:
            return "", encoding or "utf-8"
        
        idx_data = _load_temp_index_metadata(file_path)
        has_index = bool(idx_data)

        idx_encoding = None
        offsets = []
        if has_index:
            try:
                offsets = idx_data.get("offsets", [])
                idx_encoding = idx_data.get("encoding")
            except Exception as e:
                print(f"[滚动窗口] 读取索引失败，回退全文件读取: {e}")
                offsets = []
                has_index = False
        
        # 如果未指定编码，尝试使用索引中的编码或探测
        detected_encoding = encoding or idx_encoding or detect_file_encoding(file_path)
        
        # 使用索引快速定位，减少大文件读取
        start_offset = 0
        start_line_offset = 1
        if has_index and offsets:
            for entry_line, entry_offset in offsets:
                if entry_line <= start_line:
                    start_offset = entry_offset
                    start_line_offset = entry_line
                else:
                    break
        
        lines = []
        current_line_no = start_line_offset
        with open(file_path, 'rb') as f:
            if start_offset:
                f.seek(start_offset)
            while current_line_no <= end_line:
                raw_line = f.readline()
                if not raw_line:
                    break
                try:
                    line_text = raw_line.decode(detected_encoding)
                except UnicodeDecodeError:
                    line_text = raw_line.decode(detected_encoding, errors='replace')
                if current_line_no >= start_line:
                    lines.append(line_text.rstrip('\n'))
                current_line_no += 1
                if current_line_no > end_line:
                    break
        
        result_text = '\n'.join(lines)
        return result_text, detected_encoding
    except Exception as e:
        print(f"[滚动窗口] 读取文件行范围失败: {e}")
        import traceback
        traceback.print_exc()
        return "", 'utf-8'

def execute_command(full_command, selected_strings=None, data=None, save_to_temp=False, session_id=None):
    """执行命令并返回结果显示
    
    Args:
        full_command: 要执行的命令
        selected_strings: 选中的字符串列表（用于高亮）
        data: 数据对象（用于高亮）
        save_to_temp: 是否保存到临时文件（用于大文件）
        session_id: 会话ID（用于临时文件命名）
    """
    def _decode_bytes(data_bytes):
        """使用多种编码解码字节串（最佳努力）"""
        if data_bytes is None:
            return ""
        if isinstance(data_bytes, str):
            return data_bytes
        for encoding in ['utf-8', 'gbk', 'gb2312', 'latin-1', 'iso-8859-1']:
            try:
                return data_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data_bytes.decode('latin-1', errors='replace')
    
    try:
        command_args = _normalize_command_args(full_command)
        # save_to_temp 为 True 时改为流式写入临时文件，避免一次性加载大输出
        if save_to_temp:
            ensure_temp_dir()
            if session_id is None:
                session_id = hashlib.md5((repr(command_args) + str(time.time())).encode()).hexdigest()
            temp_file_path = get_temp_file_path(session_id)
            
            line_count = 0
            sample_bytes = b""
            last_chunk_ended_newline = True
            proc = None
            stderr_bytes = b""
            
            try:
                proc = subprocess.Popen(
                    command_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                with open(temp_file_path, 'wb') as temp_file:
                    for chunk in iter(lambda: proc.stdout.read(65536), b''):
                        temp_file.write(chunk)
                        line_count += chunk.count(b'\n')
                        last_chunk_ended_newline = chunk.endswith(b'\n')
                        if len(sample_bytes) < 65536:
                            needed = 65536 - len(sample_bytes)
                            sample_bytes += chunk[:needed]
                
                stderr_bytes = proc.stderr.read()
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                if proc:
                    proc.kill()
                return html.P("命令执行超时", className="text-warning")
            except Exception as e:
                return html.Div([
                    html.P("执行命令时发生异常:", className="text-danger"),
                    html.P(str(e), className="text-danger small")
                ])
            
            if proc and proc.returncode != 0:
                error_output = _decode_bytes(stderr_bytes)
                return html.Div([
                    html.P("命令执行出错:", className="text-danger"),
                    html.Pre(error_output, className="small text-danger")
                ])
            
            if not os.path.exists(temp_file_path) or os.path.getsize(temp_file_path) == 0:
                return html.Pre("没有找到符合条件的日志行", className="small")
            
            if not last_chunk_ended_newline:
                line_count += 1
            if line_count == 0:
                line_count = 1
            
            rolling_cfg = load_rolling_config()
            window_size = rolling_cfg.get('lines_before', 250) + rolling_cfg.get('lines_after', 249) + 1
            initial_content, initial_encoding = get_file_lines_range(temp_file_path, 1, min(window_size, line_count))
            
            result_display = html.Div([
                html.Div(),
                html.Div(
                    id=f"log-window-{session_id}",
                    children=[html.Pre(initial_content, className="small")],
                    style={"backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px", "fontFamily": "monospace", "fontSize": "12px"},
                    **{
                        "data-session-id": session_id,
                        "data-total-lines": line_count,
                        "data-window-size": window_size,
                        "data-lines-before": rolling_cfg.get('lines_before', 250),
                "data-lines-after": rolling_cfg.get('lines_after', 249),
                "data-prefetch-threshold": rolling_cfg.get('prefetch_threshold', 125)
            }
        ),
        dcc.Store(id=f"temp-file-info-{session_id}", data={
                    "file_path": temp_file_path,
                    "total_lines": line_count,
                    "session_id": session_id,
                }),
                dcc.Store(id=f"current-window-{session_id}", data={
                    "start_line": 1,
                    "end_line": min(500, line_count),
                    "total_lines": line_count
                }),
                html.Div(id=f"rolling-bootstrap-{session_id}"),
            ])
            
            # 记录会话高亮信息，供滚动窗口分片渲染使用
            try:
                keywords_to_highlight = []
                keyword_to_color = {}
                if selected_strings and data and isinstance(data, dict) and "categories" in data:
                    categories = sorted(list(data["categories"].keys()))
                    if categories:
                        category_colors = get_category_colors(categories)
                        keyword_to_category = {}
                        for category, strings in data["categories"].items():
                            for s in strings:
                                keyword_to_category[s] = category
                        for item in selected_strings:
                            if isinstance(item, dict):
                                stext = item.get("text")
                            else:
                                stext = item
                            
                            if stext in keyword_to_category:
                                keywords_to_highlight.append(stext)
                            else:
                                keywords_to_highlight.append(stext)
                                if "Temp" not in category_colors:
                                    category_colors["Temp"] = "#ffc107"
                                keyword_to_category[stext] = "Temp"

                        # Use shared helper to calculate colors, supporting single-category multi-color mode
                        keyword_to_color = calculate_highlight_color_map(selected_strings, keywords_to_highlight, keyword_to_category, category_colors)
                highlight_session_info[session_id] = {
                    "keywords": sorted(set(keywords_to_highlight), key=len, reverse=True),
                    "colors": keyword_to_color
                }
                print(f"[滚动窗口] 已记录会话高亮信息, session: {session_id}, 关键字数: {len(highlight_session_info[session_id]['keywords'])}")
            except Exception as _e:
                print(f"[滚动窗口] 记录会话高亮信息失败: {_e}")
            
            print(f"[滚动窗口] 滚动窗口组件已创建，session_id: {session_id}")
            return result_display
        
        # 非临时文件模式：保持原有逻辑（目前主要兼容未来调用）
        result = subprocess.run(
            command_args,
            capture_output=True,
            text=False,
            timeout=30
        )
        
        if result.returncode == 0:
            output_bytes = result.stdout
            output = _decode_bytes(output_bytes) if output_bytes else "没有找到符合条件的日志行"
            if not output.strip():
                output = "没有找到符合条件的日志行"
            
            line_count = len(output.split('\n'))
            
            if selected_strings and data:
                highlighted_display = highlight_keywords_dash(output, selected_strings, data)
                
                if line_count > 3000:
                    result_display = html.Div([
                        html.P(f"注意：结果包含 {line_count} 行，已启用滚动条", className="text-info mb-2"),
                        html.Div([
                            highlighted_display
                        ])
                    ])
                else:
                    result_display = html.Div([
                        highlighted_display
                    ])
            else:
                if line_count > 3000:
                    result_display = html.Div([
                        html.P(f"注意：结果包含 {line_count} 行，已启用滚动条", className="text-info mb-2"),
                        html.Pre(output, className="small")
                    ])
                else:
                    result_display = html.Pre(output, className="small")
        else:
            error_output = _decode_bytes(result.stderr)
            result_display = html.Div([
                html.P("命令执行出错:", className="text-danger"),
                html.Pre(error_output, className="small text-danger")
            ])
    except subprocess.TimeoutExpired:
        result_display = html.P("命令执行超时", className="text-warning")
    except Exception as e:
        result_display = html.Div([
            html.P("执行命令时发生异常:", className="text-danger"),
            html.P(str(e), className="text-danger small")
        ])
    
    return result_display







# Tab切换回调函数 - 控制显示/隐藏
@app.callback(
    [Output("tab-1-content", "style"),
     Output("tab-compare-content", "style"),
     Output("tab-ai-keywords-content", "style"),
     Output("tab-2-content", "style"),
     Output("tab-3-content", "style"),
     Output("tab-4-content", "style")],
    [Input("main-tabs", "active_tab")]
)
def toggle_tab_visibility(active_tab):
    """切换标签页的显示/隐藏，而不是重新渲染内容，以保留状态"""
    if active_tab == "tab-1":
        return {"display": "block"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}
    elif active_tab == "tab-compare":
        return {"display": "none"}, {"display": "block"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}
    elif active_tab == "tab-ai-keywords":
        return {"display": "none"}, {"display": "none"}, {"display": "block"}, {"display": "none"}, {"display": "none"}, {"display": "none"}
    elif active_tab == "tab-2":
        return {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "block"}, {"display": "none"}, {"display": "none"}
    elif active_tab == "tab-3":
        return {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "block"}, {"display": "none"}
    elif active_tab == "tab-4":
        return {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "block"}
    
    # 默认显示tab-1
    return {"display": "block"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}

@app.callback(
    [Output("ai-keyword-path-chat-modal", "is_open"),
     Output("ai-keyword-path-chat-store", "data", allow_duplicate=True),
     Output("ai-keyword-path-chat-container", "children", allow_duplicate=True),
     Output("toast-container", "children", allow_duplicate=True)],
    [Input("ai-keyword-analyze-path-btn", "n_clicks"),
     Input("ai-keyword-path-chat-close-btn", "n_clicks")],
    [State("ai-keyword-data-path-input", "value"),
     State("ai-keyword-path-chat-modal", "is_open")],
    prevent_initial_call=True
)
def toggle_ai_keyword_path_chat_modal(open_clicks, close_clicks, data_path, is_open):
    ctx = dash.callback_context
    if not ctx.triggered:
        return is_open, dash.no_update, dash.no_update, dash.no_update
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger_id == "ai-keyword-path-chat-close-btn":
        return False, dash.no_update, dash.no_update, dash.no_update
    data_path = str(data_path or "").strip()
    if not data_path:
        return False, [], _render_ai_path_chat([]), _toast_script("请先输入 free-code 工作目录/源码根目录", "warning")
    return True, [], _render_ai_path_chat([]), _toast_script("请在对话框中和 AI 讨论功能逻辑路径", "info")

@app.callback(
    Output("ai-keyword-path-prompt-collapse", "is_open"),
    [Input("ai-keyword-path-prompt-toggle-btn", "n_clicks")],
    [State("ai-keyword-path-prompt-collapse", "is_open")],
    prevent_initial_call=True
)
def toggle_ai_keyword_default_prompt(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open

@app.callback(
    [Output("ai-keyword-path-chat-store", "data", allow_duplicate=True),
     Output("ai-keyword-path-chat-container", "children", allow_duplicate=True),
     Output("ai-keyword-status", "children", allow_duplicate=True),
     Output("toast-container", "children", allow_duplicate=True),
     Output("ai-keyword-path-chat-pending-store", "data", allow_duplicate=True),
     Output("ai-keyword-path-chat-pending-interval", "disabled", allow_duplicate=True)],
    [Input("ai-keyword-path-chat-pending-interval", "n_intervals")],
    [State("ai-keyword-path-chat-pending-store", "data"),
     State("ai-keyword-path-chat-store", "data")],
    prevent_initial_call=True
)
def noop_legacy_ai_keyword_path_chat_pending(n_intervals, pending, chat_history):
    return dash.no_update, dash.no_update, dash.no_update, dash.no_update, None, True

@app.callback(
    [Output("ai-keyword-generated-config-store", "data"),
     Output("ai-keyword-generated-config-summary", "children"),
     Output("ai-keyword-generated-config-container", "children"),
     Output("ai-keyword-review-group-name-input", "value"),
     Output("ai-keyword-review-config-name-input", "value"),
     Output("toast-container", "children", allow_duplicate=True),
     Output("ai-keyword-path-chat-modal", "is_open", allow_duplicate=True)],
    [Input("ai-keyword-generated-config-sync-input", "value")],
    prevent_initial_call=True
)
def sync_ai_keyword_generated_config_from_frontend(raw_value):
    raw_value = str(raw_value or "").strip()
    if not raw_value:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    try:
        payload = json.loads(raw_value)
        group_name, config_name, config_data = _normalize_ai_keyword_config_payload(payload)
        normalized_payload = {
            "group_name": group_name,
            "config_name": config_name,
            "config_data": config_data,
        }
        keyword_count = sum(len(v.get("keep", [])) + len(v.get("filter", [])) for v in config_data.values())
        summary = f"AI 已生成 {len(config_data)} 个分类、{keyword_count} 个关键字。请取消勾选不需要的关键字后保存。"
        return (
            normalized_payload,
            summary,
            _render_ai_keyword_config_review(normalized_payload),
            group_name,
            config_name,
            _toast_script("AI 已生成关键字配置，请审核后保存", "success"),
            False,
        )
    except Exception as exc:
        print(f"[AI关键字] 同步生成配置失败: {exc}")
        return {}, f"生成配置解析失败: {exc}", _render_ai_keyword_config_review({}), "", "", _toast_script(f"生成配置解析失败: {exc}", "error"), True

@app.callback(
    [Output("toast-container", "children", allow_duplicate=True),
     Output("ai-keyword-generated-config-summary", "children", allow_duplicate=True),
     Output("log-filter-config-group-selector", "options", allow_duplicate=True),
     Output("compare-config-group-selector", "options", allow_duplicate=True)],
    [Input("ai-keyword-review-save-btn", "n_clicks")],
    [State({"type": "ai-keyword-review-check", "index": ALL}, "value"),
     State({"type": "ai-keyword-review-check", "index": ALL}, "id"),
     State("ai-keyword-generated-config-store", "data"),
     State("ai-keyword-review-group-name-input", "value"),
     State("ai-keyword-review-config-name-input", "value")],
    prevent_initial_call=True
)
def save_ai_keyword_reviewed_config(n_clicks, checked_values, checkbox_ids, generated_payload, group_name, config_name):
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    config_data = {}
    for checked, checkbox_id in zip(checked_values or [], checkbox_ids or []):
        if not checked:
            continue
        try:
            item = json.loads((checkbox_id or {}).get("index") or "{}")
        except Exception:
            continue
        category = str(item.get("category") or "AI").strip() or "AI"
        keyword_type = "filter" if item.get("type") == "filter" else "keep"
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        config_data.setdefault(category, {"keep": [], "filter": []})
        if text not in config_data[category][keyword_type]:
            config_data[category][keyword_type].append(text)
    if not config_data:
        return _toast_script("请至少保留一个关键字", "warning"), "请至少保留一个关键字", dash.no_update, dash.no_update
    payload = {
        "group_name": str(group_name or (generated_payload or {}).get("group_name") or "").strip(),
        "config_name": str(config_name or (generated_payload or {}).get("config_name") or "").strip(),
        "config_data": config_data,
    }
    try:
        result = _save_ai_keyword_config_payload(payload)
        message = f"已保存配置：configs/{result['config_name']}.json，配置组：{result['group_name']}，关键字数：{result['keyword_count']}"
        config_groups = load_config_groups()
        options = [{'label': name, 'value': name} for name in config_groups.keys()]
        return _toast_script(message, "success"), message, options, options
    except Exception as exc:
        print(f"[AI关键字] 保存审核配置失败: {exc}")
        return _toast_script(f"保存失败: {exc}", "error"), f"保存失败: {exc}", dash.no_update, dash.no_update

# 日志管理tab的回调函数

@app.callback(
    [Output("log-manager-current-dir-store", "data"),
     Output("uploaded-files-list", "children", allow_duplicate=True)],
    [Input({"type": "enter-log-dir-btn", "index": ALL}, "n_clicks"),
     Input("log-dir-up-btn", "n_clicks"),
     Input("log-dir-root-btn", "n_clicks")],
    [State("log-manager-current-dir-store", "data")],
    prevent_initial_call=True
)
def navigate_log_manager(enter_clicks, up_clicks, root_clicks, current_dir):
    ctx = callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update

    trigger = ctx.triggered[0]
    if not trigger.get("value"):
        return dash.no_update, dash.no_update

    target_dir = current_dir or ""
    trigger_id = trigger["prop_id"].rsplit(".", 1)[0]
    try:
        if trigger_id == "log-dir-up-btn":
            target_dir = _parent_log_manager_dir(current_dir)
        elif trigger_id == "log-dir-root-btn":
            target_dir = ""
        else:
            target_dir = _normalize_log_manager_dir(json.loads(trigger_id)["index"])
    except Exception:
        target_dir = ""

    log_files = get_log_files()
    return target_dir, _create_file_list_table(log_files, target_dir)

# 文件上传处理
@app.callback(
    [Output('upload-status', 'children'),
     Output('uploaded-files-list', 'children')],
    [Input('upload-log-file', 'contents')],
    [State('upload-log-file', 'filename'),
     State('upload-log-file', 'last_modified'),
     State("log-manager-current-dir-store", "data")],
    prevent_initial_call=True
)
def handle_file_upload(contents, filename, last_modified, current_dir):
    if contents is None:
        return dash.no_update, dash.no_update
    
    try:
        ensure_log_dir()
        content_items = contents if isinstance(contents, list) else [contents]
        filename_items = filename if isinstance(filename, list) else [filename]
        imported_files = []
        failed_files = []

        for item_contents, item_filename in zip(content_items, filename_items):
            try:
                content_type, content_string = item_contents.split(',', 1)
                decoded = base64.b64decode(content_string)
                item_filename = item_filename or "log.log"

                if _has_allowed_archive_extension(item_filename):
                    suffix = os.path.basename(item_filename)
                    with tempfile.TemporaryDirectory(prefix="log_filter_upload_") as upload_temp_dir:
                        temp_path = os.path.join(upload_temp_dir, _sanitize_import_filename(suffix))
                        with open(temp_path, 'wb') as f:
                            f.write(decoded)
                        imported_files.extend(_import_archive_file(temp_path))
                else:
                    target_name = _join_log_manager_path(current_dir, item_filename) if current_dir else item_filename
                    item_filename, file_path = _build_available_log_filename(target_name)
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    with open(file_path, 'wb') as f:
                        f.write(decoded)
                    imported_files.append(item_filename)
            except Exception as item_error:
                failed_files.append(f"{item_filename}: {item_error}")
        
        log_files = get_log_files()
        file_list_table = _create_file_list_table(log_files, current_dir)

        if imported_files and not failed_files:
            status = dbc.Alert(f"已导入 {len(imported_files)} 个日志文件。", color="success", dismissable=True)
        elif imported_files:
            status = dbc.Alert(f"已导入 {len(imported_files)} 个日志文件，{len(failed_files)} 个文件失败：{'；'.join(failed_files[:3])}", color="warning", dismissable=True)
        else:
            detail = "；".join(failed_files[:3]) if failed_files else "未找到支持的日志文件"
            status = dbc.Alert(f"文件上传失败: {detail}", color="danger", dismissable=True)
        return status, file_list_table
        
    except Exception as e:
        error_status = dbc.Alert(f"文件上传失败: {str(e)}", color="danger", dismissable=True)
        return error_status, dash.no_update

@app.callback(
    [Output("create-log-dir-status", "children"),
     Output("uploaded-files-list", "children", allow_duplicate=True),
     Output("new-log-dir-input", "value")],
    [Input("create-log-dir-btn", "n_clicks")],
    [State("new-log-dir-input", "value"),
     State("log-manager-current-dir-store", "data")],
    prevent_initial_call=True
)
def create_log_directory(n_clicks, dirname, current_dir):
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update

    try:
        target_dir = _join_log_manager_path(current_dir, dirname)
        normalized, dir_path = _resolve_log_dir_path(target_dir, must_exist=False)
        if os.path.exists(dir_path) and not os.path.isdir(dir_path):
            return dbc.Alert("同名文件已存在", color="danger", dismissable=True), dash.no_update, dash.no_update
        os.makedirs(dir_path, exist_ok=True)
        log_files = get_log_files()
        return dbc.Alert(f"已创建目录: {normalized.replace(os.sep, '/')}", color="success", dismissable=True), _create_file_list_table(log_files, current_dir), ""
    except Exception as e:
        return dbc.Alert(f"创建目录失败: {str(e)}", color="danger", dismissable=True), dash.no_update, dash.no_update

# 删除文件操作
@app.callback(
    Output('uploaded-files-list', 'children', allow_duplicate=True),
    [Input({'type': 'delete-file-btn', 'index': ALL}, 'n_clicks'),
     Input({'type': 'delete-dir-btn', 'index': ALL}, 'n_clicks')],
    [State("log-manager-current-dir-store", "data")],
    prevent_initial_call=True
)
def delete_log_file(file_clicks, dir_clicks, current_dir):
    # Determine which button was clicked
    ctx = callback_context
    if not ctx.triggered:
        return dash.no_update

    # If all n_clicks are None or 0, return
    click_values = list(file_clicks or []) + list(dir_clicks or [])
    if not any(click_values):
        return dash.no_update
        
    # Get the button ID
    # Use rsplit to split from the right, ensuring we only split off the property name (n_clicks)
    # This handles cases where the filename in the ID contains dots
    button_id_str = ctx.triggered[0]['prop_id'].rsplit('.', 1)[0]
    
    try:
        button_id_dict = json.loads(button_id_str)
        target_path = button_id_dict['index']
        if button_id_dict.get("type") == "delete-dir-btn":
            _dirname, dir_path = _resolve_log_dir_path(target_path, must_exist=False)
            if os.path.isdir(dir_path):
                shutil.rmtree(dir_path)
        else:
            _filename, file_path = _resolve_log_file_path(target_path, must_exist=False, allowed_extensions=ALLOWED_LOG_EXTENSIONS)
            if os.path.exists(file_path):
                os.remove(file_path)
            
        # 更新文件列表
        log_files = get_log_files()
        return _create_file_list_table(log_files, current_dir)
            
    except Exception as e:
        # 如果出错，暂不处理，或者返回原列表
        print(f"Delete error: {e}")
        return dash.no_update

# 页面加载时初始化文件列表
@app.callback(
    [Output('uploaded-files-list', 'children', allow_duplicate=True),
     Output('external-program-path-input', 'value')],
    [Input('main-tabs', 'active_tab')],
    [State("log-manager-current-dir-store", "data")],
    prevent_initial_call='initial_duplicate'
)
def initialize_file_list(active_tab, current_dir):
    if active_tab == "tab-3":
        log_files = get_log_files()
        ext_config = load_external_program_config()
        return _create_file_list_table(log_files, current_dir), ext_config.get("path", "")
    
    return dash.no_update, dash.no_update

# 重命名文件回调：打开模态框和取消
@app.callback(
    [Output("rename-file-modal", "is_open", allow_duplicate=True),
     Output("rename-target-file", "data"),
     Output("rename-file-input", "value"),
     Output("rename-target-kind", "data")],
    [Input({"type": "rename-file-btn", "index": ALL}, "n_clicks"),
     Input({"type": "rename-dir-btn", "index": ALL}, "n_clicks"),
     Input("rename-file-cancel-btn", "n_clicks")],
    [State("rename-file-modal", "is_open")],
    prevent_initial_call=True
)
def toggle_rename_modal(rename_clicks, rename_dir_clicks, cancel_click, is_open):
    ctx = callback_context
    if not ctx.triggered:
        return is_open, dash.no_update, dash.no_update, dash.no_update
        
    # Check if the trigger value is valid (not None)
    # This prevents the modal from opening when components are re-rendered (value is None)
    trigger_value = ctx.triggered[0].get("value")
    if trigger_value is None:
        return is_open, dash.no_update, dash.no_update, dash.no_update
        
    # Use rsplit to split from the right, ensuring we only split off the property name (n_clicks)
    # This handles cases where the filename in the ID contains dots
    trigger_id = ctx.triggered[0]["prop_id"].rsplit(".", 1)[0]
    
    # 检查是否是重命名按钮点击
    if "rename-file-btn" in trigger_id or "rename-dir-btn" in trigger_id:
        try:
            button_id_dict = json.loads(trigger_id)
            filename = button_id_dict['index']
            kind = "dir" if button_id_dict.get("type") == "rename-dir-btn" else "file"
            return True, filename, filename, kind
        except Exception as e:
            return is_open, dash.no_update, dash.no_update, dash.no_update
            
    # 取消按钮点击，关闭模态框
    if "rename-file-cancel-btn" in trigger_id:
        return False, dash.no_update, dash.no_update, dash.no_update
        
    return is_open, dash.no_update, dash.no_update, dash.no_update

# 执行重命名操作
@app.callback(
    [Output('uploaded-files-list', 'children', allow_duplicate=True),
     Output('toast-container', 'children', allow_duplicate=True),
     Output("rename-file-modal", "is_open", allow_duplicate=True)],
    [Input("rename-file-confirm-btn", "n_clicks")],
    [State("rename-target-file", "data"),
     State("rename-target-kind", "data"),
     State("rename-file-input", "value"),
     State("log-manager-current-dir-store", "data")],
    prevent_initial_call=True
)
def execute_rename(n_clicks, target_filename, target_kind, new_filename, current_dir):
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update
        
    if not target_filename or not new_filename:
        return dash.no_update, _toast_script("文件名不能为空", "warning"), True
        
    # 如果文件名没有变化
    if target_filename == new_filename:
        return dash.no_update, dash.no_update, False
        
    try:
        if target_kind == "dir":
            target_filename, old_path = _resolve_log_dir_path(target_filename, must_exist=False)
            new_filename, new_path = _resolve_log_dir_path(new_filename, must_exist=False)
        else:
            target_filename, old_path = _resolve_log_file_path(target_filename, must_exist=False, allowed_extensions=ALLOWED_LOG_EXTENSIONS)
            new_filename, new_path = _resolve_log_file_path(new_filename, must_exist=False, allowed_extensions=ALLOWED_LOG_EXTENSIONS)
        
        # 检查原文件是否存在
        if not os.path.exists(old_path):
             return dash.no_update, _toast_script("原文件不存在", "error"), False
            
        # 检查新文件名是否已存在
        if os.path.exists(new_path):
            return dash.no_update, _toast_script(f"文件名 {new_filename} 已存在", "error"), True
            
        # 重命名文件
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        os.rename(old_path, new_path)
        
        # 更新文件列表
        log_files = get_log_files()
        label = "目录" if target_kind == "dir" else "文件"
        return _create_file_list_table(log_files, current_dir), _toast_script(f"{label}已重命名为 {new_filename}", "success"), False
        
    except Exception as e:
        return dash.no_update, _toast_script(f"重命名失败: {str(e)}", "error"), True

# 更新配置文件选择器选项
@app.callback(
    Output('config-file-selector', 'options'),
    [Input('main-tabs', 'active_tab')],
    prevent_initial_call='initial_duplicate'
)
def update_config_file_selector(active_tab):
    if active_tab == "tab-2":
        config_files = get_config_files()
        options = [{'label': file, 'value': file} for file in config_files]
        return options
    return dash.no_update

# 加载配置文件回调 - 更新为Toast系统
@app.callback(
    [Output('selected-strings', 'data', allow_duplicate=True),
     Output('toast-container', 'children', allow_duplicate=True)],
    [Input('load-config-btn', 'n_clicks')],
    [State('config-file-selector', 'value'),
     State('selected-log-file', 'data')],
    prevent_initial_call=True
)
def load_configuration(n_clicks, config_name, selected_log_file):
    if n_clicks is None or n_clicks == 0 or not config_name:
        return dash.no_update, html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('请选择要加载的配置文件', 'warning');
            }}
        """)
    
    try:
        config_path = get_config_path(config_name)
        
        if not os.path.exists(config_path):
            return dash.no_update, html.Script(f"""
                if (typeof window.showToast === 'function') {{
                    window.showToast('配置文件 {config_name} 不存在', 'error');
                }}
            """)
        
        # 加载配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            saved_selections = json.load(f)
        
        # 从保存的选择中提取所有字符串
        loaded_strings = []
        
        for category, content in saved_selections.items():
            if isinstance(content, dict):
                # 处理保留字符串
                if "keep" in content:
                    for string_text in content["keep"]:
                        loaded_strings.append({
                            "text": string_text,
                            "type": "keep",
                            "category": category
                        })
                
                # 处理过滤字符串
                if "filter" in content:
                    for string_text in content["filter"]:
                        loaded_strings.append({
                            "text": string_text,
                            "type": "filter",
                            "category": category
                        })
            else:
                # 处理旧格式的配置文件
                # 使用 config_name 作为分类名，确保单一配置文件加载时能被识别为同一分类
                # 去除文件扩展名作为分类名
                cat_name = os.path.splitext(config_name)[0]
                for string_text in content:
                    loaded_strings.append({
                        "text": string_text,
                        "type": "keep",  # 默认为保留字符串
                        "category": cat_name
                    })
        
        # 保存到用户选择状态
        if selected_log_file:
            save_user_selections(selected_log_file, loaded_strings)
        else:
            # 如果当前没有选择日志文件，只保存字符串配置，不覆盖日志文件选择
            current_selections = load_user_selections()
            current_selections["selected_strings"] = loaded_strings
            current_selections["last_updated"] = datetime.now().isoformat()
            selections_file = os.path.join(os.path.dirname(DATA_FILE), "user_selections.json")
            with open(selections_file, 'w', encoding='utf-8') as f:
                json.dump(current_selections, f, ensure_ascii=False, indent=2)
        
        return loaded_strings, html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('成功加载配置文件: {config_name}', 'success');
            }}
        """)
    
    except Exception as e:
        print(f"加载配置文件时出错: {e}")
        return dash.no_update, html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('加载配置文件失败: {str(e)}', 'error');
            }}
        """)

# 删除配置文件回调 - 更新为Toast系统
@app.callback(
    [Output('toast-container', 'children', allow_duplicate=True),
     Output('config-file-selector', 'options', allow_duplicate=True),
     Output('config-name-input', 'value', allow_duplicate=True),
     Output('config-file-selector', 'value', allow_duplicate=True)],
    [Input('delete-config-btn', 'n_clicks')],
    [State('config-name-input', 'value'),
     State('config-file-selector', 'value')],
    prevent_initial_call=True
)
def delete_configuration(n_clicks, config_name_input, config_file_selector):
    if n_clicks is None or n_clicks == 0:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    # 判断配置名称输入框和选择配置文件的下拉框哪个有值
    # 如果都有值则使用配置名称输入框的值来删除配置
    if config_name_input and config_file_selector:
        # 两者都有值，优先使用配置名称输入框的值
        config_name = config_name_input
    elif config_name_input:
        # 只有配置名称输入框有值
        config_name = config_name_input
    elif config_file_selector:
        # 只有下拉框有值
        config_name = config_file_selector
    else:
        # 两者都没有值
        return html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('请填写配置名称或选择要删除的配置文件', 'warning');
            }}
        """), dash.no_update, dash.no_update, dash.no_update
    
    # 验证配置名称
    if not config_name.strip():
        return html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('配置名称不能为空', 'warning');
            }}
        """), dash.no_update, dash.no_update, dash.no_update
    
    try:
        config_path = get_config_path(config_name)
        
        # 检查配置文件是否存在
        if not os.path.exists(config_path):
            return html.Script(f"""
                if (typeof window.showToast === 'function') {{
                    window.showToast('配置文件 '{config_name}' 不存在', 'warning');
                }}
            """), dash.no_update, dash.no_update, dash.no_update
        
        # 删除配置文件
        os.remove(config_path)
        # 失效配置文件缓存
        _config_files_cache["mtime"] = None
        _config_files_cache["data"] = None
        
        # 更新配置文件选择器选项
        config_files = get_config_files()
        options = [{'label': file, 'value': file} for file in config_files]
        
        return html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('配置文件 '{config_name}' 删除成功', 'success');
            }}
        """), options, "", None
        
    except Exception as e:
        print(f"删除配置文件时出错: {e}")
        return html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('删除配置文件失败: {str(e)}', 'error');
            }}
        """), dash.no_update, dash.no_update, dash.no_update

# 保存配置文件回调 - 更新为Toast系统
@app.callback(
    [Output('toast-container', 'children', allow_duplicate=True),
     Output('config-file-selector', 'options', allow_duplicate=True)],
    [Input('save-config-btn', 'n_clicks')],
    [State('config-name-input', 'value'),
     State('config-file-selector', 'value'),
     State('selected-strings', 'data')],
    prevent_initial_call=True
)
def save_configuration(n_clicks, config_name_input, config_file_selector, selected_strings):
    if n_clicks is None or n_clicks == 0:
        return dash.no_update, dash.no_update
    
    # 判断配置名称输入框和选择配置文件的下拉框哪个有值
    # 如果都有值则使用配置名称输入框的值来保存配置
    if config_name_input and config_file_selector:
        # 两者都有值，优先使用配置名称输入框的值
        config_name = config_name_input
    elif config_name_input:
        # 只有配置名称输入框有值
        config_name = config_name_input
    elif config_file_selector:
        # 只有下拉框有值
        config_name = config_file_selector
    else:
        # 两者都没有值
        return html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('请填写配置名称或选择配置文件', 'warning');
            }}
        """), dash.no_update
    
    # 验证配置名称
    if not config_name.strip():
        return html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('配置名称不能为空', 'warning');
            }}
        """), dash.no_update
    
    try:
        config_path = get_config_path(config_name)
        
        # 按分类和类型组织选中的字符串
        categorized_strings = {}
        
        # 加载当前数据以获取分类信息
        current_data = load_data()
        
        for item in selected_strings:
            if isinstance(item, dict):
                string_text = item["text"]
                string_type = item["type"]
                
                # 查找字符串所属的分类
                for category, strings in current_data["categories"].items():
                    if string_text in strings:
                        # 创建分类（如果不存在）
                        if category not in categorized_strings:
                            categorized_strings[category] = {"keep": [], "filter": []}
                        
                        # 添加字符串到相应类型
                        categorized_strings[category][string_type].append(string_text)
                        break
            else:
                # 处理旧格式的字符串（不带类型信息）
                string_text = item
                
                # 查找字符串所属的分类
                for category, strings in current_data["categories"].items():
                    if string_text in strings:
                        # 创建分类（如果不存在）
                        if category not in categorized_strings:
                            categorized_strings[category] = {"keep": [], "filter": []}
                        
                        # 默认为保留字符串
                        categorized_strings[category]["keep"].append(string_text)
                        break
        
        # 保存到配置文件
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(categorized_strings, f, ensure_ascii=False, indent=2)
        # 失效配置文件缓存
        _config_files_cache["mtime"] = None
        _config_files_cache["data"] = None
        
        # 更新配置文件选择器选项
        config_files = get_config_files()
        options = [{'label': file, 'value': file} for file in config_files]
        
        return html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('配置已成功保存为: {config_name}', 'success');
            }}
        """), options
    
    except Exception as e:
        print(f"保存配置文件时出错: {e}")
        return html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('保存配置文件失败: {str(e)}', 'error');
            }}
        """), dash.no_update

# 更新配置文件按钮显示
@app.callback(
    Output('config-files-container', 'children'),
    [Input('main-tabs', 'active_tab'),
     Input('selected-config-files', 'data'),
     Input('log-filter-config-group-selector', 'value')],
    prevent_initial_call='initial_duplicate'
)
def update_config_files_display(active_tab, selected_config_files, selected_group):
    if active_tab == "tab-1":
        all_config_files = get_config_files()
        
        # 根据选择的配置文件组过滤显示
        files_to_display = all_config_files
        if selected_group:
            config_groups = load_config_groups()
            if selected_group in config_groups:
                group_files = config_groups[selected_group]
                # 保持原始排序，但只保留组内文件
                files_to_display = [f for f in all_config_files if f in group_files]
                
                # 如果组内没有有效文件
                if not files_to_display:
                    return html.P(f"配置组 {selected_group} 中没有可用的配置文件", className="text-muted text-center")
        
        if not files_to_display:
            # 如果本来就没有配置文件
            if not all_config_files:
                return html.P("暂无配置文件，请在配置管理页面创建配置文件", className="text-muted text-center")
            return html.Div() # 应该不会执行到这里，除非过滤结果为空且非组原因
        
        # 创建配置文件按钮列表
        config_buttons = []
        for config_file in files_to_display:
            # 检查当前配置文件是否被选中（支持多选）
            is_selected = config_file in selected_config_files
            
            config_buttons.append(
                dbc.Button(
                    config_file,
                    id={"type": "config-file-btn", "index": config_file},
                    color="primary" if is_selected else "outline-primary",
                    size="sm",
                    className="m-1",
                    style={"whiteSpace": "nowrap", "flexShrink": 0},
                    disabled=False  # 具体禁用由外层控制
                )
            )
        
        # 使用d-flex和flex-wrap实现多列布局
        return html.Div(
            config_buttons,
            className="d-flex flex-wrap gap-2",
            style={"minHeight": "50px"}
        )
    
    return dash.no_update

# 处理配置文件选择（支持多选）
@app.callback(
    Output('selected-config-files', 'data'),
    [Input({"type": "config-file-btn", "index": dash.ALL}, 'n_clicks'),
     Input('clear-config-selection-btn', 'n_clicks'),
     Input('log-filter-config-group-selector', 'value')],
    [State('selected-config-files', 'data'),
     State('main-tabs', 'active_tab')],
    prevent_initial_call=True
)
def handle_config_file_selection(config_btn_clicks, clear_click, selected_group, current_selection, active_tab):
    # 只有在日志过滤tab激活时才处理回调
    if active_tab != "tab-1":
        return dash.no_update
        
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update

    # 防御：None 处理
    if current_selection is None:
        current_selection = []
    
    # 如果是配置组选择触发
    if ctx.triggered and ctx.triggered[0]['prop_id'] == 'log-filter-config-group-selector.value':
        # 当切换配置组时，清空当前的选择
        # 用户反馈：在选择配置组的时候，所有配置默认是非选中状态
        
        # 保存配置文件选择状态（只保存配置文件名称，不加载内容，但保留日志文件选择）
        current_selections = load_user_selections()
        save_user_selections(current_selections.get("selected_log_file", ""), [], selected_config_files=[])
        
        return []

    
    # 如果点击了清除按钮
    if ctx.triggered and ctx.triggered[0]['prop_id'] == 'clear-config-selection-btn.n_clicks':
        # 保存空的选择状态，但保留当前的日志文件选择
        current_selections = load_user_selections()
        save_user_selections(current_selections.get("selected_log_file", ""), [], selected_config_files=[])
        return []
    
    # 如果点击了配置文件按钮
    if ctx.triggered and 'config-file-btn' in ctx.triggered[0]['prop_id']:
        trigger_value = ctx.triggered[0].get('value')
        # 如果Dash给了None，尝试从点击列表里推断本次点击的按钮
        if trigger_value is None and isinstance(config_btn_clicks, list):
            for idx, val in enumerate(config_btn_clicks):
                if val is not None and val > 0:
                    trigger_value = val
                    break
            if trigger_value is None:
                return dash.no_update
        # 获取被点击的按钮的index（即配置文件名）
        prop_id = ctx.triggered[0]['prop_id']
        config_file = prop_id.rsplit('.', 1)[0].split('"index":"')[1].split('"')[0]
        
        # 如果配置文件已经在选中列表中，则移除它（取消选择）
        if config_file in current_selection:
            current_selection.remove(config_file)
        else:
            # 否则添加到选中列表中
            current_selection.append(config_file)
        print(f"更新后的选中列表: {current_selection}")
        
        # 保存配置文件选择状态（只保存配置文件名称，不加载内容，但保留日志文件选择）
        current_selections = load_user_selections()
        save_user_selections(current_selections.get("selected_log_file", ""), [], selected_config_files=current_selection)
        
        return current_selection
    
    return dash.no_update


@app.callback(
    Output('compare-config-files-container', 'children'),
    [Input('main-tabs', 'active_tab'),
     Input('compare-selected-config-files', 'data'),
     Input('compare-config-group-selector', 'value')],
    prevent_initial_call='initial_duplicate'
)
def update_compare_config_files_display(active_tab, selected_config_files, selected_group):
    if active_tab != "tab-compare":
        return dash.no_update
    all_config_files = get_config_files()

    files_to_display = all_config_files
    if selected_group:
        config_groups = load_config_groups()
        if selected_group in config_groups:
            group_files = config_groups[selected_group]
            files_to_display = [f for f in all_config_files if f in group_files]
            if not files_to_display:
                return html.P(f"配置组 {selected_group} 中没有可用的配置文件", className="text-muted text-center")

    if not files_to_display:
        if not all_config_files:
            return html.P("暂无配置文件，请在配置管理页面创建配置文件", className="text-muted text-center")
        return html.Div()

    selected_config_files = selected_config_files or []
    config_buttons = []
    for config_file in files_to_display:
        is_selected = config_file in selected_config_files
        config_buttons.append(
            dbc.Button(
                config_file,
                id={"type": "compare-config-file-btn", "index": config_file},
                color="primary" if is_selected else "outline-primary",
                size="sm",
                className="m-1",
                style={"whiteSpace": "nowrap", "flexShrink": 0}
            )
        )

    return html.Div(
        config_buttons,
        className="d-flex flex-wrap gap-2",
        style={"minHeight": "50px"}
    )


@app.callback(
    Output('compare-selected-config-files', 'data'),
    [Input({"type": "compare-config-file-btn", "index": dash.ALL}, 'n_clicks'),
     Input('compare-clear-config-selection-btn', 'n_clicks'),
     Input('compare-config-group-selector', 'value')],
    [State('compare-selected-config-files', 'data'),
     State('main-tabs', 'active_tab')],
    prevent_initial_call=True
)
def handle_compare_config_file_selection(config_btn_clicks, clear_click, selected_group, current_selection, active_tab):
    if active_tab != "tab-compare":
        return dash.no_update

    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update

    if current_selection is None:
        current_selection = []

    if ctx.triggered and ctx.triggered[0]['prop_id'] == 'compare-config-group-selector.value':
        return []

    if ctx.triggered and ctx.triggered[0]['prop_id'] == 'compare-clear-config-selection-btn.n_clicks':
        return []

    if ctx.triggered and 'compare-config-file-btn' in ctx.triggered[0]['prop_id']:
        prop_id = ctx.triggered[0]['prop_id']
        config_file = prop_id.rsplit('.', 1)[0].split('"index":"')[1].split('"')[0]
        if config_file in current_selection:
            current_selection.remove(config_file)
        else:
            current_selection.append(config_file)
        return current_selection

    return dash.no_update


@app.callback(
    [Output('compare-tab-strings-store', 'data', allow_duplicate=True),
     Output('toast-container', 'children', allow_duplicate=True)],
    [Input('compare-selected-config-files', 'data')],
    [State('main-tabs', 'active_tab')],
    prevent_initial_call=True
)
def load_compare_selected_config_files(selected_config_files, active_tab):
    if active_tab != "tab-compare":
        return dash.no_update, dash.no_update

    if not selected_config_files:
        return [], dash.no_update

    try:
        keyword_file_map = {}
        keyword_type_map = {}
        global_keyword_category_map = {}
        loaded_configs = []

        for selected_config_file in selected_config_files:
            config_path = get_config_path(selected_config_file)
            if not os.path.exists(config_path):
                return dash.no_update, html.Script(f"if(window.showToast) window.showToast('配置文件 {selected_config_file} 不存在', 'error');")

            with open(config_path, 'r', encoding='utf-8') as f:
                saved_selections = json.load(f)

            file_keywords = set()
            keyword_category_map_local = {}

            for category, content in saved_selections.items():
                if isinstance(content, dict):
                    if "keep" in content:
                        for string_text in content["keep"]:
                            file_keywords.add((string_text, "keep"))
                            if string_text not in keyword_category_map_local:
                                keyword_category_map_local[string_text] = category
                    if "filter" in content:
                        for string_text in content["filter"]:
                            file_keywords.add((string_text, "filter"))
                            if string_text not in keyword_category_map_local:
                                keyword_category_map_local[string_text] = category
                else:
                    cat_name = os.path.splitext(selected_config_file)[0]
                    for string_text in content:
                        file_keywords.add((string_text, "keep"))
                        if string_text not in keyword_category_map_local:
                            keyword_category_map_local[string_text] = cat_name

            for string_text, string_type in file_keywords:
                if string_text not in keyword_file_map:
                    keyword_file_map[string_text] = set()
                keyword_file_map[string_text].add(selected_config_file)
                keyword_type_map[string_text] = string_type
                if string_text in keyword_category_map_local and string_text not in global_keyword_category_map:
                    global_keyword_category_map[string_text] = keyword_category_map_local[string_text]

            loaded_configs.append(selected_config_file)

        loaded_strings = []
        for string_text, file_set in keyword_file_map.items():
            item = {
                "text": string_text,
                "type": keyword_type_map[string_text],
                "count": len(file_set),
                "files": list(file_set)
            }
            if string_text in global_keyword_category_map:
                item["category"] = global_keyword_category_map[string_text]
            loaded_strings.append(item)

        if len(loaded_configs) == 1:
            message = f"成功加载配置文件: {loaded_configs[0]}"
        else:
            message = f"成功加载 {len(loaded_configs)} 个配置文件: {', '.join(loaded_configs)}"

        return loaded_strings, html.Script(f"if(window.showToast) window.showToast('{message}', 'success');")
    except Exception as e:
        return dash.no_update, html.Script(f"if(window.showToast) window.showToast('加载配置文件失败: {str(e)}', 'error');")

# 为日志过滤tab创建独立的数据存储
# 日志过滤tab的选中字符串存储
app.clientside_callback(
    """
    function(n_clicks) {
        return window.dash_clientside = window.dash_clientside || {};
    }
    """,
    Output('filter-tab-strings-store', 'data'),
    [Input('main-tabs', 'active_tab')],
    prevent_initial_call=True
)

# 加载选中的配置文件（支持多选）- 更新为Toast系统
@app.callback(
    [Output('filter-tab-strings-store', 'data', allow_duplicate=True),
     Output('toast-container', 'children', allow_duplicate=True),
     Output('selected-log-file', 'data', allow_duplicate=True)],  # 添加输出以更新日志文件选择
    [Input('selected-config-files', 'data')],
    [State('selected-log-file', 'data'),
     State('main-tabs', 'active_tab')],
    prevent_initial_call=True
)
def load_selected_config_files(selected_config_files, selected_log_file, active_tab):
    # 只有在日志过滤tab激活时才处理回调
    if active_tab != "tab-1":
        return dash.no_update, dash.no_update, dash.no_update
        
    if not selected_config_files:
        return dash.no_update, dash.no_update, dash.no_update
    
    try:
        # 使用字典跟踪关键字在不同文件中的出现情况
        # key: keyword_text, value: set of filenames
        keyword_file_map = {}
        # 跟踪关键字类型
        keyword_type_map = {}
        # 跟踪关键字分类
        global_keyword_category_map = {}
        
        loaded_configs = []
        
        for selected_config_file in selected_config_files:
            config_path = get_config_path(selected_config_file)
            
            if not os.path.exists(config_path):
                return dash.no_update, html.Script(f"""
                    if (typeof window.showToast === 'function') {{
                        window.showToast('配置文件 {selected_config_file} 不存在', 'error');
                    }}
                """), dash.no_update
            
            # 加载配置文件
            with open(config_path, 'r', encoding='utf-8') as f:
                saved_selections = json.load(f)
            
            # 从该文件中提取所有关键字
            file_keywords = set()
            # 跟踪关键字的分类
            keyword_category_map_local = {}
            
            # 从保存的选择中提取所有字符串
            for category, content in saved_selections.items():
                if isinstance(content, dict):
                    # 处理保留字符串
                    if "keep" in content:
                        for string_text in content["keep"]:
                            file_keywords.add((string_text, "keep"))
                            if string_text not in keyword_category_map_local:
                                keyword_category_map_local[string_text] = category
                    
                    # 处理过滤字符串
                    if "filter" in content:
                        for string_text in content["filter"]:
                            file_keywords.add((string_text, "filter"))
                            if string_text not in keyword_category_map_local:
                                keyword_category_map_local[string_text] = category
                else:
                    # 处理旧格式的配置文件
                    # 使用 config_name 作为分类名，确保单一配置文件加载时能被识别为同一分类
                    cat_name = os.path.splitext(selected_config_file)[0]
                    for string_text in content:
                        file_keywords.add((string_text, "keep"))
                        if string_text not in keyword_category_map_local:
                            keyword_category_map_local[string_text] = cat_name
            
            # 更新全局映射
            for string_text, string_type in file_keywords:
                if string_text not in keyword_file_map:
                    keyword_file_map[string_text] = set()
                keyword_file_map[string_text].add(selected_config_file)
                keyword_type_map[string_text] = string_type
                
                # 保存分类信息
                if string_text in keyword_category_map_local:
                    if string_text not in global_keyword_category_map:
                        global_keyword_category_map[string_text] = keyword_category_map_local[string_text]
            
            loaded_configs.append(selected_config_file)
        
        # 构建最终的 loaded_strings 列表
        loaded_strings = []
        for string_text, file_set in keyword_file_map.items():
            count = len(file_set)
            item = {
                "text": string_text,
                "type": keyword_type_map[string_text],
                "count": count,
                "files": list(file_set)
            }
            if string_text in global_keyword_category_map:
                item["category"] = global_keyword_category_map[string_text]
            loaded_strings.append(item)
            

        
        # 使用保存的日志文件
        effective_log_file = selected_log_file
        
        # 只保存配置文件名称到用户选择状态，保留现有的选择字符串，不保存配置文件内容
        save_user_selections(effective_log_file, [], selected_config_files=selected_config_files)
        
        if len(loaded_configs) == 1:
            message = f"成功加载配置文件: {loaded_configs[0]}"
        else:
            message = f"成功加载 {len(loaded_configs)} 个配置文件: {', '.join(loaded_configs)}"
        
        # 返回加载的字符串和更新后的日志文件选择
        # 注意：这里只更新filter-tab-strings-store的数据，不会自动触发日志显示更新
        return loaded_strings, html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('{message}', 'success');
            }}
        """), effective_log_file
    
    except Exception as e:
        print(f"加载配置文件时出错: {e}")
        return dash.no_update, html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('加载配置文件失败: {str(e)}', 'error');
            }}
        """), dash.no_update



# 监听临时关键字存储变化，更新显示
@app.callback(
    Output('temp-keywords-popover-display', 'children'),
    [Input('temp-keywords-store', 'data')]
)
def update_temp_keywords_display(keywords):
    """根据存储的数据更新临时关键字显示"""
    normalized = normalize_temp_keywords(keywords)
    result = create_temp_keyword_buttons(normalized)
    return result

# 页面加载/刷新时重新从文件载入临时关键字，避免服务端缓存旧数据
@app.callback(
    Output('temp-keywords-store', 'data', allow_duplicate=True),
    [Input('url', 'href')],
    prevent_initial_call="initial_duplicate"
)
def reload_temp_keywords_on_load(_href):
    return load_temp_keywords_from_file()

# 添加临时关键字
@app.callback(
    [Output('temp-keywords-store', 'data'),
     Output('toast-container', 'children', allow_duplicate=True)],
    [Input('temp-keyword-add-btn', 'n_clicks'),
     Input('temp-keyword-text', 'n_submit'),
     Input('temp-exclude-keyword-add-btn', 'n_clicks'),
     Input('temp-exclude-keyword-text', 'n_submit')],
    [State('temp-keyword-text', 'value'),
     State('temp-exclude-keyword-text', 'value'),
     State('temp-keywords-store', 'data')],
    prevent_initial_call=True
)
def add_temp_keyword(n_clicks, n_submit, exclude_clicks, exclude_submit, keyword_text, exclude_keyword_text, existing_keywords):
    # 获取回调上下文
    ctx = dash.callback_context
    
    normalized_keywords = normalize_temp_keywords(existing_keywords)
    
    # 只有在按钮被点击时才处理
    if not ctx.triggered:
        return dash.no_update, dash.no_update
    
    # 检查是否是按钮点击事件
    prop_id = ctx.triggered[0]['prop_id']
    # 判断添加类型
    is_exclude = 'temp-exclude-keyword' in prop_id
    target_text = exclude_keyword_text if is_exclude else keyword_text
    target_text = target_text.strip() if target_text else ""
    
    if not target_text:
        return normalized_keywords, dash.no_update
    
    new_entry = {
        "text": target_text,
        "type": "filter" if is_exclude else "keep"
    }
    
    if any(kw["text"] == new_entry["text"] and kw["type"] == new_entry["type"] for kw in normalized_keywords):
        return normalized_keywords, dash.no_update
    
    normalized_keywords.append(new_entry)
    toast_label = "临时反向关键字" if is_exclude else "临时关键字"
    save_temp_keywords_to_file(normalized_keywords)
    return normalized_keywords, html.Script(f"""
        if (typeof window.showToast === 'function') {{
            window.showToast('已添加{toast_label}: {target_text}', 'success');
        }}
    """)

# 处理临时关键字按钮点击（删除关键字）
@app.callback(
    Output('temp-keywords-store', 'data', allow_duplicate=True),
    [Input({"type": "temp-keyword-btn", "index": dash.ALL}, 'n_clicks')],
    [State('temp-keywords-store', 'data')],
    prevent_initial_call=True
)
def handle_temp_keyword_click(keyword_clicks, current_keywords):
    ctx = dash.callback_context
    
    # 如果没有点击事件，返回无更新
    if not ctx.triggered:
        return dash.no_update
    
    # 获取被点击的关键字
    prop_id = ctx.triggered[0]['prop_id']
    # 检查是否是关键字按钮点击事件
    if 'temp-keyword-btn' in prop_id:
        # 检查按钮是否真的被点击了（n_clicks不为None）
        trigger_value = ctx.triggered[0].get('value')
        
        if trigger_value is None:
            return dash.no_update
            
        # 提取被点击的关键字与类型
        keyword_index = prop_id.rsplit('.', 1)[0].split('"index":"')[1].split('"')[0]
        if ':' in keyword_index:
            kw_type, keyword = keyword_index.split(':', 1)
        else:
            kw_type, keyword = "keep", keyword_index
        
        normalized_keywords = normalize_temp_keywords(current_keywords)
        # 从关键字列表中移除被点击的关键字
        updated_keywords = [
            kw for kw in normalized_keywords
            if not (kw.get("text") == keyword and kw.get("type") == kw_type)
        ]
        save_temp_keywords_to_file(updated_keywords)
        
        # 只返回更新后的关键字列表，显示由存储监听回调更新
        return updated_keywords
    
    return dash.no_update

# 临时关键字变化时自动更新右侧显示结果（已禁用自动过滤，改为手动触发）
# 临时关键字变化时自动更新右侧显示结果（已禁用自动过滤，改为手动触发）
@app.callback(
    Output("log-filter-results", "children", allow_duplicate=True),
    [Input("temp-keywords-store", "data"),
     Input("filter-tab-strings-store", "data")],
    [State("main-tabs", "active_tab"),
     State("log-file-selector", "value")],
    prevent_initial_call=True
)
def auto_update_results_on_temp_keywords(temp_keywords, filter_tab_strings, active_tab, selected_log_file):
    # 只有在日志过滤tab激活时才处理回调
    if active_tab != "tab-1":
        return dash.no_update
    
    # 获取回调上下文，检查触发源
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    
    # 获取触发回调的组件ID
    triggered_id = ctx.triggered[0]["prop_id"].rsplit(".", 1)[0]
    
    # 只有当临时关键字变化时才显示提示信息
    # 配置文件选择变化时不自动更新显示，保持当前过滤结果
    if triggered_id == "temp-keywords-store":
        return dash.no_update
    
    # 对于其他触发源（如配置文件选择），保持当前显示不变
    return dash.no_update

def get_temp_keywords_store():
    """获取临时关键字存储中的当前值"""
    try:
        # 从app的layout中获取存储组件的当前值
        store_component = app.layout.get('temp-keywords-store')
        if store_component and hasattr(store_component, 'data'):
            return store_component.data or []
        return []
    except:
        return []

def create_temp_keyword_buttons(keywords):
    """创建临时关键字按钮列表"""
    normalized = normalize_temp_keywords(keywords)
    
    if not normalized:
        return None
    
    keyword_buttons = []
    for kw in normalized:
        text = kw.get("text", "")
        kw_type = kw.get("type", "keep")
        btn_color = "outline-danger" if kw_type == "filter" else "outline-primary"
        badge_color = "danger" if kw_type == "filter" else "primary"
        badge_label = "屏蔽" if kw_type == "filter" else "保留"
        keyword_buttons.append(
            dbc.Button(
                [
                    html.Span(text, className="me-1"),
                    dbc.Badge(badge_label, color=badge_color, className="ms-1")
                ],
                id={"type": "temp-keyword-btn", "index": f"{kw_type}:{text}"},
                color=btn_color,
                size="sm",
                className="m-1",
                style={"whiteSpace": "nowrap", "flexShrink": 0, "maxWidth": "200px", "overflow": "hidden", "textOverflow": "ellipsis"}
            ),
        )
    
    # 使用d-flex和flex-wrap实现多列布局
    return html.Div(
        keyword_buttons,
        className="d-flex flex-wrap gap-1 justify-content-end",
        style={"width": "100%"}
    )


@app.server.route('/api/import-log-paths', methods=['POST'])
def import_log_paths_api():
    """从 Electron 传入的本地路径导入日志文件、目录或压缩包。"""
    try:
        from flask import request, jsonify
        data = request.get_json(silent=True) or {}
        paths = data.get("paths") or []
        if not isinstance(paths, list):
            return jsonify({"ok": False, "error": "paths 必须是数组"}), 400
        ensure_log_dir()
        imported = []
        failed = []
        for source_path in paths:
            try:
                imported.extend(import_log_source_path(source_path))
            except Exception as exc:
                failed.append({"path": str(source_path), "error": str(exc)})
        return jsonify({
            "ok": bool(imported) and not failed,
            "imported": imported,
            "count": len(imported),
            "failed": failed
        })
    except Exception as exc:
        from flask import jsonify
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.server.route('/api/upload-log-files', methods=['POST'])
def upload_log_files_api():
    """从浏览器拖拽上传日志文件，支持目录拖拽时携带相对路径。"""
    try:
        from flask import request, jsonify
        ensure_log_dir()
        files = request.files.getlist("files")
        relative_paths = request.form.getlist("relative_paths")
        if not files:
            return jsonify({"ok": False, "error": "未收到文件"}), 400

        imported = []
        failed = []
        for index, storage_file in enumerate(files):
            raw_rel_path = relative_paths[index] if index < len(relative_paths) else ""
            display_name = raw_rel_path or storage_file.filename or "log.log"
            try:
                display_name = _sanitize_import_relative_path(display_name)
                if not display_name.lower().endswith(ALLOWED_LOG_EXTENSIONS):
                    continue
                filename, dest_path = _build_available_log_filename(display_name)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                storage_file.save(dest_path)
                imported.append(filename.replace(os.sep, "/"))
            except Exception as exc:
                failed.append({"path": display_name, "error": str(exc)})

        return jsonify({
            "ok": bool(imported) and not failed,
            "imported": imported,
            "count": len(imported),
            "failed": failed
        })
    except Exception as exc:
        from flask import jsonify
        return jsonify({"ok": False, "error": str(exc)}), 500


# API端点：获取日志窗口
@app.server.route('/api/get-log-window', methods=['POST'])
def get_log_window():
    """获取临时文件的指定行范围"""
    try:
        from flask import request, jsonify
        data = request.get_json()
        session_id = data.get('session_id')
        start_line = int(data.get('start_line', 1))
        end_line = int(data.get('end_line', 500))
        if not session_id:
            return jsonify({'success': False, 'error': '缺少session_id'})
        temp_file_path = get_temp_file_path(session_id)
        if not os.path.exists(temp_file_path):
            return jsonify({'success': False, 'error': f'临时文件不存在: {temp_file_path}'})
        total_lines = get_file_line_count(temp_file_path)
        content, encoding = get_file_lines_range(temp_file_path, start_line, end_line)

        # 分片高亮（基于会话记录的关键字和颜色映射）
        is_html = False
        try:
            info = highlight_session_info.get(session_id) if 'session_id' in locals() or 'session_id' in globals() else None
            if not info:
                # 直接从请求中取（更可靠）
                info = highlight_session_info.get(data.get('session_id'))
            
            # 准备高亮关键字和颜色
            keywords_to_highlight = []
            colors_map = {}
            
            # 添加保存的高亮配置
            if info and info.get('keywords'):
                keywords_to_highlight.extend([k for k in info['keywords'] if isinstance(k, str) and k])
                if 'colors' in info:
                    colors_map.update(info['colors'])
            
            # 添加临时搜索关键字
            highlight_keyword = data.get('highlight_keyword')
            if highlight_keyword and isinstance(highlight_keyword, str) and highlight_keyword.strip():
                highlight_keyword = highlight_keyword.strip()
                # 如果关键字不在列表中，添加它
                # 注意：这里简单处理，如果搜索词和已有词重复，优先使用已有的颜色配置
                if highlight_keyword not in keywords_to_highlight:
                    keywords_to_highlight.append(highlight_keyword)
                
                # 为搜索关键字设置特定颜色（如果尚未配置颜色）
                # 使用亮黄色背景，黑色文字，突出显示
                if highlight_keyword.lower() not in colors_map:
                    colors_map[highlight_keyword.lower()] = {'bg': '#ffff00', 'fg': '#000000'}

            if keywords_to_highlight:
                # 构建单个正则（按长度降序，避免子串先匹配）
                # 去重并排序
                unique_keywords = sorted(list(set(keywords_to_highlight)), key=len, reverse=True)
                parts = [re.escape(k) for k in unique_keywords]
                
                if parts:
                    combined = '(' + '|'.join(parts) + ')'
                    regex = re.compile(combined, re.IGNORECASE)

                    def html_escape(s):
                        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

                    # 构造高亮后的HTML字符串
                    out_segments = []
                    for line in content.split('\n'):
                        if not line:
                            out_segments.append('\n')
                            continue
                        last = 0
                        for m in regex.finditer(line):
                            if m.start() > last:
                                out_segments.append(html_escape(line[last:m.start()]))
                            matched = m.group(0)
                            # 获取颜色配置，优先使用精确匹配，否则尝试小写匹配
                            color = colors_map.get(matched) or colors_map.get(matched.lower())
                            bg = (color or {}).get('bg', '#ff8800')
                            fg = (color or {}).get('fg', '#ffffff')
                            out_segments.append(f"<span style=\"background-color:{bg};color:{fg};padding:2px 4px;border-radius:3px;font-weight:bold;\">{html_escape(matched)}</span>")
                            last = m.end()
                        if last < len(line):
                            out_segments.append(html_escape(line[last:]))
                        out_segments.append('\n')
                    content = ''.join(out_segments)
                    is_html = True
        except Exception as _e:
            print(f"[API端点] 分片高亮失败: {_e}")
        
        # 使用标准JSON序列化，避免orjson问题
        response_data = {
            'success': True,
            'content': content,
            'start_line': start_line,
            'end_line': end_line,
            'total_lines': total_lines,
            'encoding': encoding,
            'is_html': is_html
        }
        response = jsonify(response_data)
        return response
    except Exception as e:
        print(f"[API端点] 发生异常: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

# API端点：从指定行开始向下查找关键字（基于会话临时文件）
@app.server.route('/api/search-next', methods=['POST'])
def search_next():
    try:
        from flask import request, jsonify
        data = request.get_json() or {}

        session_id = data.get('session_id')
        keyword = (data.get('keyword') or '').strip()
        start_line = int(data.get('from_line') or 1)
        case_sensitive = bool(data.get('case_sensitive', False))

        if not session_id:
            return jsonify({'success': False, 'error': '缺少session_id'})
        if not keyword:
            return jsonify({'success': False, 'error': '缺少关键字'})

        temp_file_path = get_temp_file_path(session_id)
        if not os.path.exists(temp_file_path):
            return jsonify({'success': False, 'error': f'临时文件不存在: {temp_file_path}'})

        search_index = _get_search_match_index(temp_file_path, keyword, case_sensitive)
        total_lines = search_index.get("total_lines") or get_file_line_count(temp_file_path)
        if start_line < 1:
            start_line = 1
        if start_line > total_lines:
            return jsonify({
                'success': True,
                'match_line': None,
                'match_index': None,
                'cursor_match_index': search_index.get("total_matches", 0),
                'total_matches': search_index.get("total_matches", 0),
                'total_lines': total_lines
            })

        matches = search_index.get("matches") or []
        match_pos = bisect_left(matches, start_line)
        match_line = matches[match_pos] if match_pos < len(matches) else None
        match_index = (match_pos + 1) if match_line is not None else None
        cursor_match_index = match_index if match_index is not None else len(matches)

        return jsonify({
            'success': True,
            'match_line': match_line,
            'match_index': match_index,
            'cursor_match_index': cursor_match_index,
            'total_matches': search_index.get("total_matches", 0),
            'total_lines': total_lines
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# API端点：从指定行开始向上查找关键字（基于会话临时文件）
@app.server.route('/api/search-prev', methods=['POST'])
def search_prev():
    try:
        from flask import request, jsonify
        data = request.get_json() or {}

        session_id = data.get('session_id')
        keyword = (data.get('keyword') or '').strip()
        # from_line 语义：从该行之上开始找（不包含该行），因此遍历到 from_line-1
        from_line = int(data.get('from_line') or 1)
        case_sensitive = bool(data.get('case_sensitive', False))

        if not session_id:
            return jsonify({'success': False, 'error': '缺少session_id'})
        if not keyword:
            return jsonify({'success': False, 'error': '缺少关键字'})

        temp_file_path = get_temp_file_path(session_id)
        if not os.path.exists(temp_file_path):
            return jsonify({'success': False, 'error': f'临时文件不存在: {temp_file_path}'})

        search_index = _get_search_match_index(temp_file_path, keyword, case_sensitive)
        total_lines = search_index.get("total_lines") or get_file_line_count(temp_file_path)
        if from_line <= 1:
            return jsonify({
                'success': True,
                'match_line': None,
                'match_index': None,
                'cursor_match_index': 0,
                'total_matches': search_index.get("total_matches", 0),
                'total_lines': total_lines
            })

        matches = search_index.get("matches") or []
        match_pos = bisect_left(matches, from_line) - 1
        match_line = matches[match_pos] if match_pos >= 0 else None
        match_index = (match_pos + 1) if match_line is not None else None
        cursor_match_index = match_index if match_index is not None else max(0, bisect_left(matches, from_line))

        return jsonify({
            'success': True,
            'match_line': match_line,
            'match_index': match_index,
            'cursor_match_index': cursor_match_index,
            'total_matches': search_index.get("total_matches", 0),
            'total_lines': total_lines
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# API端点：滚动调试（打印中心行与窗口范围）
@app.server.route('/api/scroll-debug', methods=['POST'])
def scroll_debug():
    try:
        from flask import request, jsonify
        data = request.get_json(silent=True) or {}
        session_id = data.get('session_id')
        center_line = data.get('center_line')
        window_start = data.get('window_start')
        window_end = data.get('window_end')
        print(f"[前端滚动窗口][调试] session:{session_id} center:{center_line} window:[{window_start},{window_end}]")
        return jsonify({'ok': True})
    except Exception as e:
        print(f"[前端滚动窗口][调试] 异常: {e}")
        return jsonify({'ok': False})


@app.server.route(f'{FREE_CODE_CHAT_API_PREFIX}/health', methods=['GET'])
def free_code_chat_health():
    from flask import jsonify, request

    try:
        requested_cwd = request.args.get('cwd')
        runtime = _get_free_code_runtime_config(requested_cwd)
        bridge = _resolve_free_code_bridge(runtime['cwd'])
        status = {
            'ok': True,
            'cli_path': getattr(bridge, 'cli_path', ''),
            'cwd': getattr(bridge, 'cwd', ''),
            'extra_args': list(getattr(bridge, 'extra_args', []) or []),
        }
        return jsonify(status)
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.server.route(f'{FREE_CODE_CHAT_API_PREFIX}/config', methods=['GET', 'POST'])
def free_code_chat_config():
    from flask import jsonify, request

    try:
        payload = request.get_json(silent=True) or {}
        requested_cwd = payload.get('cwd') if request.method == 'POST' else request.args.get('cwd')
        runtime = _get_free_code_runtime_config(requested_cwd)
        return jsonify({
            'ok': True,
            'cwd': runtime['cwd'],
            'cli_path': runtime['cli_path'] or '',
            'free_code_root': runtime['free_code_root'],
            'extra_args': runtime['extra_args'],
        })
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400


@app.server.route(f'{FREE_CODE_CHAT_API_PREFIX}/chat/<session_id>/stream', methods=['POST'])
def free_code_chat_stream(session_id):
    from flask import Response, jsonify, request, stream_with_context

    payload = request.get_json(silent=True) or {}
    message = payload.get('message')
    attachments = payload.get('attachments')
    analysis_context = payload.get('analysis_context') if isinstance(payload.get('analysis_context'), dict) else {}
    timeout_value = payload.get('timeout', FREE_CODE_CHAT_TIMEOUT)
    requested_cwd = payload.get('cwd')

    if not isinstance(message, str) or not message.strip():
        return jsonify({'error': 'message must be a non-empty string'}), 400

    try:
        timeout = float(timeout_value)
    except (TypeError, ValueError):
        return jsonify({'error': 'timeout must be a number'}), 400

    try:
        runtime = _get_free_code_runtime_config(requested_cwd)
        bridge = _resolve_free_code_bridge(runtime['cwd'])
        composed_message = _build_free_code_chat_message(message, attachments, analysis_context)
        session = bridge.ensure_session(session_id)
        session.client.send_text(composed_message)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

    @stream_with_context
    def event_stream():
        deadline = time.monotonic() + timeout
        partial_fragments = []
        fallback_final_text = ""
        try:
            while True:
                remaining = max(0.0, deadline - time.monotonic())
                event = session.client.read_event(timeout=remaining)
                event_type = event.get('type')
                if event_type == 'assistant_partial':
                    delta_text = str(event.get('delta') or '')
                    if delta_text:
                        partial_fragments.append(delta_text)
                elif event_type == 'assistant' and not partial_fragments:
                    fallback_final_text = extract_text_from_chat_event(event)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event_type == 'result':
                    final_text = "".join(partial_fragments).strip() or fallback_final_text.strip()
                    if analysis_context.get('auto_update_skill') and analysis_context.get('config_group') and final_text:
                        try:
                            auto_update_config_group_skill(
                                analysis_context.get('config_group'),
                                analysis_context,
                                final_text,
                            )
                        except Exception as exc:
                            print(f"[free-code] 自动更新 skill 失败: {exc}")
                    break
        except Exception as exc:
            error_event = {
                'type': 'error',
                'error': str(exc),
                'session_id': session_id,
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return Response(event_stream(), mimetype='text/event-stream')


@app.server.route(f'{FREE_CODE_CHAT_API_PREFIX}/sessions/<session_id>', methods=['DELETE'])
def free_code_chat_close_session(session_id):
    from flask import jsonify

    try:
        _close_free_code_session_everywhere(session_id)
        return jsonify({'ok': True, 'session_id': session_id})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@app.server.route('/api/ai-keyword/save-config', methods=['POST'])
def ai_keyword_save_config_api():
    from flask import jsonify, request

    try:
        payload = request.get_json(silent=True) or {}
        result = _save_ai_keyword_config_payload(payload)
        return jsonify({'ok': True, **result})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400


# -----------------------------------------------------------------------------
# 配置文件组管理相关回调
# -----------------------------------------------------------------------------

# 控制配置文件组管理区域折叠/展开
@app.callback(
    Output("config-groups-management-collapse", "is_open"),
    [Input("config-groups-management-toggle", "n_clicks")],
    [State("config-groups-management-collapse", "is_open")],
    prevent_initial_call=True
)
def toggle_config_groups_management(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open

# 更新配置文件组管理界面的数据
@app.callback(
    [Output("available-configs-for-group", "children"),
     Output("config-group-selector", "options")],
    [Input("config-groups-management-collapse", "is_open"),
     Input("save-config-group-btn", "n_clicks"),
     Input("delete-config-group-btn", "n_clicks"),
     Input("group-selected-files-store", "data"),
     Input("config-file-selector", "options")]
)
def update_config_group_management_ui(is_open, _save_clicks, _delete_clicks, selected_files, config_file_options):
    # 如果是折叠状态且不是由保存/删除触发的（即只是为了更新UI），则不更新
    # 但如果是刚打开（is_open=True），则需要更新
    ctx = dash.callback_context
    if not ctx.triggered:
        trigger_id = "unknown"
    else:
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == "config-groups-management-collapse" and not is_open:
        return dash.no_update, dash.no_update
        
    # 优先从下拉框选项中获取配置文件列表，以保持一致性
    if config_file_options:
        config_files = [opt['value'] for opt in config_file_options]
    else:
        # 回退到从磁盘读取
        config_files = get_config_files()
    
    # 获取所有配置文件组
    config_groups = load_config_groups()
    
    # 过滤掉 config_groups 自身（如果它被错误地识别为配置文件）
    if "config_groups" in config_files:
        config_files.remove("config_groups")
        
    # 1. 生成可用的配置文件列表 (Button List)
    buttons_list = []
    selected_files = selected_files or []
    
    for config_file in config_files:
        is_selected = config_file in selected_files
        buttons_list.append(
            dbc.Button(
                config_file,
                id={"type": "group-config-file-btn", "index": config_file},
                color="primary" if is_selected else "outline-primary",
                size="sm",
                className="m-1",
                style={"whiteSpace": "nowrap", "flexShrink": 0}
            )
        )
        
    # 2. 更新下拉框选项
    dropdown_options = [{'label': name, 'value': name} for name in config_groups.keys()]
    
    return buttons_list, dropdown_options

# 处理配置文件组管理中的配置文件选择（支持多选）
@app.callback(
    Output("group-selected-files-store", "data"),
    [Input({"type": "group-config-file-btn", "index": dash.ALL}, "n_clicks")],
    [State("group-selected-files-store", "data")],
    prevent_initial_call=True
)
def handle_group_config_file_selection(n_clicks_list, current_selection):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
        
    # 获取被点击的按钮的index（即配置文件名）
    prop_id = ctx.triggered[0]['prop_id']
    if 'group-config-file-btn' not in prop_id:
        return dash.no_update
        
    config_file = prop_id.rsplit('.', 1)[0].split('"index":"')[1].split('"')[0]
    
    current_selection = current_selection or []
    
    # 如果配置文件已经在选中列表中，则移除它（取消选择）
    if config_file in current_selection:
        current_selection.remove(config_file)
    else:
        # 否则添加到选中列表中
        current_selection.append(config_file)
        
    return current_selection

# 当选择配置文件组时，自动填充选中的文件和组名（用于编辑/查看）
@app.callback(
    [Output("group-selected-files-store", "data", allow_duplicate=True),
     Output("config-group-name-input", "value", allow_duplicate=True)],
    [Input("config-group-selector", "value")],
    prevent_initial_call=True
)
def load_group_for_editing(group_name):
    if not group_name:
        return [], ""
    
    config_groups = load_config_groups()
    if group_name in config_groups:
        return config_groups[group_name], group_name
    
    return [], ""

# 保存配置文件组
@app.callback(
    [Output("config-group-name-input", "value", allow_duplicate=True),
     Output("toast-container", "children", allow_duplicate=True)],
    [Input("save-config-group-btn", "n_clicks")],
    [State("config-group-name-input", "value"),
     State("group-selected-files-store", "data")],
    prevent_initial_call=True
)
def save_new_config_group(n_clicks, group_name, selected_files):
    if not n_clicks:
        return dash.no_update, dash.no_update
        
    if not group_name or not group_name.strip():
        return dash.no_update, html.Script("if(window.showToast) window.showToast('请输入配置文件组名称', 'warning');")
        
    if not selected_files:
        return dash.no_update, html.Script("if(window.showToast) window.showToast('请至少选择一个配置文件', 'warning');")
        
    config_groups = load_config_groups()
    
    config_groups[group_name.strip()] = selected_files
    
    if save_config_groups(config_groups):
        return "", html.Script(f"if(window.showToast) window.showToast('配置文件组 \"{group_name}\" 保存成功', 'success');")
    else:
        return dash.no_update, html.Script(f"if(window.showToast) window.showToast('保存失败', 'error');")

# 删除配置文件组
@app.callback(
    [Output("config-group-selector", "value"),
     Output("toast-container", "children", allow_duplicate=True)],
    [Input("delete-config-group-btn", "n_clicks")],
    [State("config-group-selector", "value")],
    prevent_initial_call=True
)
def delete_config_group(n_clicks, group_name):
    if not n_clicks:
        return dash.no_update, dash.no_update
        
    if not group_name:
        return dash.no_update, html.Script("if(window.showToast) window.showToast('请选择要删除的配置文件组', 'warning');")
        
    config_groups = load_config_groups()
    if group_name in config_groups:
        del config_groups[group_name]
        if save_config_groups(config_groups):
            return None, html.Script(f"if(window.showToast) window.showToast('配置文件组 \"{group_name}\" 已删除', 'success');")
        else:
            return dash.no_update, html.Script("if(window.showToast) window.showToast('删除失败', 'error');")
    
    return dash.no_update, html.Script(f"if(window.showToast) window.showToast('配置文件组 \"{group_name}\" 不存在', 'error');")

# 加载配置文件组 (批量加载配置文件)
@app.callback(
    [Output("selected-config-files", "data", allow_duplicate=True),
     Output("toast-container", "children", allow_duplicate=True)],
    [Input("load-config-group-btn", "n_clicks")],
    [State("config-group-selector", "value")],
    prevent_initial_call=True
)
def load_config_group_files(n_clicks, group_name):
    if not n_clicks:
        return dash.no_update, dash.no_update
        
    if not group_name:
        return dash.no_update, html.Script("if(window.showToast) window.showToast('请选择要加载的配置文件组', 'warning');")
        
    config_groups = load_config_groups()
    if group_name in config_groups:
        files_to_load = config_groups[group_name]
        return files_to_load, html.Script(f"if(window.showToast) window.showToast('正在加载组 \"{group_name}\" 中的 {len(files_to_load)} 个配置文件...', 'info');")
        
    return dash.no_update, html.Script(f"if(window.showToast) window.showToast('配置文件组 \"{group_name}\" 不存在', 'error');")

# -----------------------------------------------------------------------------
# 日志过滤Tab中的配置文件组下拉菜单回调
# -----------------------------------------------------------------------------

# 更新日志过滤Tab中的配置文件组下拉菜单选项
@app.callback(
    Output('log-filter-config-group-selector', 'options'),
    [Input('main-tabs', 'active_tab'),
     Input('save-config-group-btn', 'n_clicks'),
     Input('delete-config-group-btn', 'n_clicks')]
)
def update_log_filter_group_selector(active_tab, save_clicks, delete_clicks):
    # 只要Tab切换或组发生变化，就重新加载选项
    config_groups = load_config_groups()
    return [{'label': name, 'value': name} for name in config_groups.keys()]


@app.callback(
    Output('compare-config-group-selector', 'options'),
    [Input('main-tabs', 'active_tab'),
     Input('save-config-group-btn', 'n_clicks'),
     Input('delete-config-group-btn', 'n_clicks')]
)
def update_compare_group_selector(active_tab, save_clicks, delete_clicks):
    config_groups = load_config_groups()
    return [{'label': name, 'value': name} for name in config_groups.keys()]



# 测量文本长度的回调
@app.callback(
    Output('compare-prefix-measure-length', 'children'),
    [Input('compare-prefix-measure-input', 'value')],
    prevent_initial_call=True
)
def measure_prefix_length(text):
    if not text:
        return "0"
    return str(len(text))


# 处理日志过滤Tab中的配置文件组选择
@app.callback(
    Output("toast-container", "children", allow_duplicate=True),
    [Input("log-filter-config-group-selector", "value")],
    prevent_initial_call='initial_duplicate'
)
def apply_config_group_selection(group_name):
    if not group_name:
        # 如果清空选择，可以选择清空配置文件，或者什么都不做
        # 这里选择什么都不做，让用户手动清除
        return dash.no_update
        
    config_groups = load_config_groups()
    if group_name in config_groups:
        # files_to_load = config_groups[group_name]
        # 不再自动选中组内的文件，只显示提示
        return html.Script(f"if(window.showToast) window.showToast('已加载组 \"{group_name}\"', 'success');")
        
    return html.Script(f"if(window.showToast) window.showToast('配置文件组 \"{group_name}\" 不存在', 'error');")


@app.callback(
    [Output("log-analysis-context-json", "children"),
     Output("toast-container", "children", allow_duplicate=True)],
    [Input("analyze-selected-logs-btn", "n_clicks")],
    [State("log-filter-config-group-selector", "value"),
     State("display-mode-tabs", "active_tab"),
     State("log-file-selector", "value"),
     State("filter-session-store", "data"),
     State("selected-log-lines-store", "data")],
    prevent_initial_call=True
)
def analyze_selected_logs_with_skill(n_clicks, group_name, display_mode, selected_log_file, filter_session_id, selected_lines):
    if not n_clicks:
        return dash.no_update, dash.no_update

    if display_mode == "filtered" and not group_name:
        return dash.no_update, _toast_script("过滤结果视图下请先选择配置文件组，再进行 AI 分析", "warning")

    try:
        payload = build_log_analysis_request_payload(
            group_name,
            display_mode,
            selected_log_file,
            filter_session_id,
            selected_lines,
        )
    except Exception as exc:
        return dash.no_update, _toast_script(str(exc), "warning")

    request_payload = {
        "request_id": str(uuid.uuid4()),
        "message": payload["message"],
        "attachments": payload["attachments"],
        "analysis_context": payload["analysis_context"],
    }
    mode_label = "过滤结果" if display_mode == "filtered" else "源文件"
    return json.dumps(request_payload, ensure_ascii=False), _toast_script(
        f"已发送 {mode_label} 中选中的 {payload['analysis_context']['selected_line_count']} 行日志到 free-code 分析",
        "info",
    )

# 同步前端滚动窗口Ready状态到Dash状态
@app.callback(
    Output(_UI_BUSY_STORE_ID, "data", allow_duplicate=True),
    [Input("log-view-ready-signal-btn", "n_clicks")],
    [State(_UI_BUSY_STORE_ID, "data")],
    prevent_initial_call=True
)
def sync_log_view_ready_state(n_clicks, current_ui_state):
    if n_clicks:
        current_phase = (current_ui_state or {}).get("phase")
        if current_phase in {"filter_running", "filter_partial_ready"}:
            return dash.no_update
        return _make_log_view_ui_state("source_ready")
    return dash.no_update

# -----------------------------------------------------------------------------
# 外部程序调用相关回调
# -----------------------------------------------------------------------------

@app.callback(
    Output("external-program-save-status", "children"),
    [Input("save-external-program-btn", "n_clicks")],
    [State("external-program-path-input", "value")],
    prevent_initial_call=True
)
def save_external_program_config_callback(n_clicks, path):
    if not n_clicks:
        return dash.no_update
    
    try:
        normalized_path, _ = _parse_external_program_command(path)
    except ValueError as e:
        return dbc.Alert(str(e), color="warning", dismissable=True)
        
    if save_external_program_config(normalized_path):
        return dbc.Alert("配置保存成功", color="success", dismissable=True)
    else:
        return dbc.Alert("配置保存失败", color="danger", dismissable=True)

@app.callback(
    Output("toast-container", "children", allow_duplicate=True),
    [Input("open-external-btn", "n_clicks")],
    [State("log-file-selector", "value")],
    prevent_initial_call=True
)
def open_external_program_callback(n_clicks, selected_log_file):
    if not n_clicks:
        return dash.no_update
        
    if not selected_log_file:
         return _toast_script("请先选择一个日志文件", "warning")
    
    config = load_external_program_config()
    program_path = config.get("path")
    
    if not program_path:
         return _toast_script("未配置外部程序路径，请在日志管理中配置", "warning")
         
    try:
        _, args = _parse_external_program_command(program_path)
        selected_log_file, log_path = _resolve_log_file_path(selected_log_file, must_exist=True, allowed_extensions=ALLOWED_LOG_EXTENSIONS)
        cmd = args + [log_path]
        
        print(f"Executing external program: {cmd}")
        subprocess.Popen(cmd)
            
        return _toast_script(f"已请求使用外部程序打开: {selected_log_file}", "success")
    except FileNotFoundError:
         return _toast_script(f"找不到外部程序: {args[0]}", "error")
    except Exception as e:
         print(f"External program error: {e}")
         return _toast_script(f"打开失败: {str(e)}", "error")

# -----------------------------------------------------------------------------
# Agentic Loop — LLM 自主工具调用
# -----------------------------------------------------------------------------

# 4.1 工具定义 (OpenAI tools schema)
ANALYSIS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_source_code",
            "description": "在源码目录中搜索包含指定关键词的文件。返回匹配的文件路径和行号。用于定位日志中出现的类名、函数名、错误码等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，如类名、函数名、错误码"
                    },
                    "directory": {
                        "type": "string",
                        "description": "搜索的目录路径，默认搜索所有配置的源码目录"
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "文件名过滤模式，如 '*.java', '*.py', '*.cpp'"
                    }
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_source_file",
            "description": "读取源码文件的指定行范围。用于查看搜索结果中具体文件的内容，理解代码逻辑。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "要读取的文件绝对路径"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（1-indexed），默认1"
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号，默认start_line+50，最多读取200行"
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
            "description": "列出目录下的文件和子目录。用于浏览项目结构，找到相关源码位置。",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "要列出的目录路径"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "文件名过滤模式，如 '*.java'，默认显示所有"
                    }
                },
                "required": ["directory"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep_source_code",
            "description": "使用正则表达式在源码中搜索。比 search_source_code 更灵活，支持正则模式匹配。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "正则表达式搜索模式"
                    },
                    "directory": {
                        "type": "string",
                        "description": "搜索的目录路径"
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "文件名过滤模式"
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "是否区分大小写，默认false"
                    }
                },
                "required": ["pattern"]
            }
        }
    }
]

# 4.2 工具执行引擎

def _validate_source_path(path, allowed_dirs):
    """校验路径是否在允许的源码目录范围内，防止路径遍历"""
    abs_path = os.path.abspath(path)
    for allowed in allowed_dirs:
        abs_allowed = os.path.abspath(allowed)
        if os.path.commonpath([abs_allowed, abs_path]) == abs_allowed:
            return True
    return False


def _run_rg_search(keyword, directory=None, file_pattern=None, regex_mode=False, case_sensitive=False):
    """使用 ripgrep 执行搜索，返回结果字符串"""
    rg_cmd = _get_rg_command()
    if not rg_cmd:
        return "[错误] ripgrep 不可用，无法搜索源码"

    config = load_llm_config()
    source_dirs = config.get("source_code_dirs", [])
    if not source_dirs:
        return "[错误] 未配置源码搜索路径，请在 AI 设置中添加"

    # 确定搜索目录
    search_dir = directory if directory else None
    if search_dir:
        if not _validate_source_path(search_dir, source_dirs):
            return "[错误] 目录不在允许的源码路径范围内"
    else:
        search_dir = source_dirs[0] if len(source_dirs) == 1 else None

    cmd = [rg_cmd, "--no-heading", "--line-number", "--max-count=30"]
    if not case_sensitive:
        cmd.append("-i")
    if file_pattern:
        cmd.extend(["--glob", file_pattern])
    if regex_mode:
        cmd.extend(["-e", keyword])
    else:
        cmd.extend(["-F", keyword])

    try:
        results = []
        dirs_to_search = [search_dir] if search_dir else source_dirs
        for d in dirs_to_search:
            full_cmd = cmd + [d]
            proc = subprocess.run(full_cmd, capture_output=True, text=True, timeout=15, encoding='utf-8', errors='replace')
            if proc.stdout:
                results.append(proc.stdout)
            if proc.returncode == 2 and proc.stderr:
                results.append(f"[rg 错误] {proc.stderr[:200]}")

        combined = "\n".join(results).strip()
        if not combined:
            return "未找到匹配结果"
        # 截断过长输出
        if len(combined) > 3000:
            combined = combined[:3000] + "\n... (结果过多，已截断)"
        return combined
    except subprocess.TimeoutExpired:
        return "[搜索超时，请缩小搜索范围]"
    except Exception as e:
        return f"[搜索异常] {str(e)[:200]}"


def _run_read_file(file_path, start_line=1, end_line=None):
    """读取源码文件的指定行范围"""
    config = load_llm_config()
    source_dirs = config.get("source_code_dirs", [])
    if not _validate_source_path(file_path, source_dirs):
        return "[错误] 文件路径不在允许的源码路径范围内"

    if not os.path.isfile(file_path):
        return f"[错误] 文件不存在: {file_path}"

    max_lines = 200
    start_line = max(1, int(start_line or 1))
    if end_line is None:
        end_line = start_line + 50
    end_line = min(end_line, start_line + max_lines)

    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        total = len(lines)
        end_line = min(end_line, total)
        if start_line > total:
            return f"[错误] 起始行 {start_line} 超出文件总行数 {total}"

        result_lines = []
        for i in range(start_line - 1, end_line):
            result_lines.append(f"{i+1}: {lines[i].rstrip()}")

        output = "\n".join(result_lines)
        if len(output) > 5000:
            output = output[:5000] + "\n... (内容过长，已截断)"
        header = f"文件: {file_path} (行 {start_line}-{end_line} / 共 {total} 行)\n"
        return header + output
    except Exception as e:
        return f"[读取异常] {str(e)[:200]}"


def _run_list_directory(directory, pattern=None):
    """列出目录内容"""
    config = load_llm_config()
    source_dirs = config.get("source_code_dirs", [])
    if not _validate_source_path(directory, source_dirs):
        return "[错误] 目录不在允许的源码路径范围内"

    if not os.path.isdir(directory):
        return f"[错误] 目录不存在: {directory}"

    try:
        entries = sorted(os.listdir(directory))
        dirs = []
        files = []
        for e in entries:
            if e.startswith('.') or e in ('__pycache__', 'node_modules', '.git', 'build', 'dist'):
                continue
            full = os.path.join(directory, e)
            if pattern and not e.endswith(pattern.lstrip('*')):
                continue
            if os.path.isdir(full):
                dirs.append(f"  [DIR]  {e}/")
            else:
                size = os.path.getsize(full)
                files.append(f"  [FILE] {e}  ({size} bytes)")

        output = f"目录: {directory}\n"
        if dirs:
            output += "子目录:\n" + "\n".join(dirs) + "\n"
        if files:
            output += "文件:\n" + "\n".join(files) + "\n"
        if not dirs and not files:
            output += "  (空目录或所有条目被过滤)"

        if len(output) > 3000:
            output = output[:3000] + "\n... (内容过多，已截断)"
        return output
    except Exception as e:
        return f"[列出目录异常] {str(e)[:200]}"


def execute_tool_call(tool_name, tool_args, config):
    """执行 LLM 请求的工具调用，返回结果字符串"""
    try:
        if tool_name == "search_source_code":
            return _run_rg_search(
                keyword=tool_args.get("keyword", ""),
                directory=tool_args.get("directory"),
                file_pattern=tool_args.get("file_pattern")
            )
        elif tool_name == "read_source_file":
            return _run_read_file(
                file_path=tool_args.get("file_path", ""),
                start_line=tool_args.get("start_line", 1),
                end_line=tool_args.get("end_line")
            )
        elif tool_name == "list_directory":
            return _run_list_directory(
                directory=tool_args.get("directory", ""),
                pattern=tool_args.get("pattern")
            )
        elif tool_name == "grep_source_code":
            return _run_rg_search(
                keyword=tool_args.get("pattern", ""),
                directory=tool_args.get("directory"),
                file_pattern=tool_args.get("file_pattern"),
                regex_mode=True,
                case_sensitive=tool_args.get("case_sensitive", False)
            )
        else:
            return f"[错误] 未知工具: {tool_name}"
    except Exception as e:
        return f"[工具执行异常] {tool_name}: {str(e)[:200]}"


# 4.4 System Prompt

def _build_analysis_system_prompt(config):
    """构建 LLM 分析的系统提示"""
    source_dirs = config.get("source_code_dirs", [])
    source_dirs_text = "\n".join(f"  - {d}" for d in source_dirs) if source_dirs else "  (未配置)"

    return f"""<identity>
你是一位专业的日志分析专家，擅长通过日志信息定位源码中的问题并分析根因。
</identity>

<tools>
你可以使用以下工具来搜索和阅读源码：

1. search_source_code(keyword, directory?, file_pattern?)
   - 在源码目录中搜索包含关键词的文件
   - 返回匹配的文件路径和行号
   - 适合搜索类名、函数名、错误码等

2. read_source_file(file_path, start_line?, end_line?)
   - 读取源码文件的指定行范围
   - 默认读取50行，最多200行
   - 用于查看搜索结果中的具体代码

3. list_directory(directory, pattern?)
   - 列出目录下的文件和子目录
   - 用于浏览项目结构

4. grep_source_code(pattern, directory?, file_pattern?, case_sensitive?)
   - 使用正则表达式搜索源码
   - 比关键词搜索更灵活

可搜索的源码目录：
{source_dirs_text}
</tools>

<guidelines>
- 收到日志后，先分析日志中的关键信息：时间戳、Tag、日志级别、函数名、错误码
- 根据关键信息，使用 search_source_code 或 grep_source_code 搜索相关源码
- 找到相关文件后，使用 read_source_file 阅读代码上下文
- **不要过早停止分析**：即使找到了初步位置，也应继续阅读上下文代码来理解完整逻辑
- 如果第一次搜索没有结果，尝试不同的关键词组合
- 分析完成后，给出清晰的结论：
  1. 问题定位：涉及的源码文件和行号
  2. 根因分析：导致日志输出的代码逻辑
  3. 修复建议：可能的解决方案
- 使用 Markdown 格式输出分析结果
</guidelines>

<output_format>
## 问题定位
（涉及的源码文件路径和行号）

## 根因分析
（导致问题的代码逻辑分析）

## 修复建议
（可能的解决方案）
</output_format>"""


# 4.3 Agentic Loop 主循环

import threading
_analysis_tasks = {}
_analysis_tasks_lock = threading.Lock()


def _update_task_state(task_id, updates):
    """线程安全地更新任务状态"""
    with _analysis_tasks_lock:
        if task_id in _analysis_tasks:
            _analysis_tasks[task_id].update(updates)


def run_agentic_analysis(task_id, log_context, config, session_id, on_progress=None):
    """执行 Agentic Loop 分析

    Args:
        task_id: 任务ID
        log_context: 日志上下文信息 dict (selected_lines, parsed_info, etc.)
        config: LLM 配置 dict
        session_id: 过滤会话ID
        on_progress: 进度回调函数 (optional)

    Returns:
        dict: 分析结果 {status, result, tool_calls_log, iterations, ...}
    """
    from openai import OpenAI

    api_base = config.get("api_base", "").strip()
    api_key = config.get("api_key", "").strip()
    model = config.get("model", "").strip()
    max_iterations = min(int(config.get("max_iterations", 10)), 30)
    max_total_tokens = int(config.get("max_total_tokens", 32768))
    temperature = float(config.get("temperature", 0.2))

    if not api_base or not api_key or not model:
        return {"status": "failed", "error": "LLM 配置不完整（API地址/Key/模型）"}

    client = OpenAI(base_url=api_base, api_key=api_key)

    # 构建初始消息
    selected_lines = log_context.get("selected_lines", [])
    log_text = log_context.get("log_text", "")
    parsed_summary = log_context.get("parsed_summary", "")

    user_message = f"""请分析以下日志，在源码中定位问题并分析根因：

## 选中的日志行
```
{log_text}
```

## 解析出的关键信息
{parsed_summary}

请在源码中搜索相关代码，阅读上下文，然后给出详细分析。"""

    system_prompt = _build_analysis_system_prompt(config)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    tool_calls_log = []
    total_tokens_used = 0

    _update_task_state(task_id, {
        "status": "analyzing",
        "phase": "agentic_loop",
        "iterations": 0
    })

    try:
        for iteration in range(max_iterations):
            # 检查是否被取消
            with _analysis_tasks_lock:
                task = _analysis_tasks.get(task_id, {})
                if task.get("cancelled", False):
                    return {"status": "cancelled", "iterations": iteration, "tool_calls_log": tool_calls_log}

            _update_task_state(task_id, {
                "iterations": iteration + 1,
                "current_phase": f"LLM 迭代 {iteration + 1}/{max_iterations}"
            })

            if on_progress:
                on_progress(iteration + 1, max_iterations, "thinking")

            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=ANALYSIS_TOOLS,
                    temperature=temperature,
                    max_tokens=4096
                )
            except Exception as e:
                error_msg = str(e)[:500]
                return {
                    "status": "failed",
                    "error": f"LLM API 调用失败: {error_msg}",
                    "iterations": iteration,
                    "tool_calls_log": tool_calls_log
                }

            # 统计 token 使用
            if hasattr(response, 'usage') and response.usage:
                total_tokens_used += response.usage.total_tokens or 0
                if total_tokens_used > max_total_tokens:
                    # Token 超限，强制结束
                    assistant_content = response.choices[0].message.content or ""
                    messages.append(response.choices[0].message.model_dump())
                    break

            choice = response.choices[0]
            assistant_message = choice.message
            tool_calls = assistant_message.tool_calls

            # 追加 assistant 消息
            messages.append(assistant_message.model_dump())

            if not tool_calls:
                # LLM 没有调用工具，分析完成
                break

            # 执行所有工具调用
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    import json as _json
                    tool_args = _json.loads(tc.function.arguments)
                except Exception:
                    tool_args = {}

                tool_calls_log.append({
                    "iteration": iteration + 1,
                    "tool": tool_name,
                    "args": tool_args
                })

                _update_task_state(task_id, {
                    "current_tool": tool_name,
                    "current_phase": f"执行工具: {tool_name}"
                })

                if on_progress:
                    on_progress(iteration + 1, max_iterations, f"tool: {tool_name}")

                # 执行工具
                tool_result = execute_tool_call(tool_name, tool_args, config)

                tool_calls_log[-1]["result_preview"] = tool_result[:200]

                # 追加工具结果到消息
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result
                })

        # 提取最终分析结果
        final_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                final_content = msg["content"]
                break

        return {
            "status": "completed",
            "result": final_content,
            "iterations": iteration + 1 if tool_calls else iteration,
            "tool_calls_log": tool_calls_log,
            "total_tokens": total_tokens_used,
            "messages": messages  # 保留完整对话历史，用于追问
        }

    except Exception as e:
        return {
            "status": "failed",
            "error": f"分析过程异常: {str(e)[:500]}",
            "iterations": 0,
            "tool_calls_log": tool_calls_log
        }


def continue_agentic_analysis(task_id, follow_up_message, config):
    """在已有分析基础上继续追问

    Args:
        task_id: 原始分析任务ID
        follow_up_message: 用户追问内容
        config: LLM 配置

    Returns:
        dict: 继续分析的结果
    """
    with _analysis_tasks_lock:
        task = _analysis_tasks.get(task_id)
        if not task or task.get("status") != "completed":
            return {"status": "failed", "error": "无法追问：任务不存在或未完成"}
        previous_messages = task.get("result_data", {}).get("messages", [])
        if not previous_messages:
            return {"status": "failed", "error": "无法追问：对话历史丢失"}

    from openai import OpenAI
    api_base = config.get("api_base", "").strip()
    api_key = config.get("api_key", "").strip()
    model = config.get("model", "").strip()
    max_iterations = min(int(config.get("max_iterations", 10)), 30)

    client = OpenAI(base_url=api_base, api_key=api_key)
    messages = list(previous_messages)
    messages.append({"role": "user", "content": follow_up_message})

    tool_calls_log = list(task.get("result_data", {}).get("tool_calls_log", []))
    total_tokens_used = task.get("result_data", {}).get("total_tokens", 0)

    _update_task_state(task_id, {"status": "analyzing", "phase": "follow_up"})

    try:
        for iteration in range(max_iterations):
            with _analysis_tasks_lock:
                if _analysis_tasks.get(task_id, {}).get("cancelled", False):
                    return {"status": "cancelled", "iterations": iteration, "tool_calls_log": tool_calls_log}

            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=ANALYSIS_TOOLS,
                    temperature=float(config.get("temperature", 0.2)),
                    max_tokens=4096
                )
            except Exception as e:
                return {"status": "failed", "error": f"LLM API 调用失败: {str(e)[:500]}"}

            if hasattr(response, 'usage') and response.usage:
                total_tokens_used += response.usage.total_tokens or 0

            choice = response.choices[0]
            assistant_message = choice.message
            tool_calls = assistant_message.tool_calls
            messages.append(assistant_message.model_dump())

            if not tool_calls:
                break

            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    import json as _json
                    tool_args = _json.loads(tc.function.arguments)
                except Exception:
                    tool_args = {}

                tool_calls_log.append({"iteration": f"follow-up-{iteration+1}", "tool": tool_name, "args": tool_args})
                tool_result = execute_tool_call(tool_name, tool_args, config)
                tool_calls_log[-1]["result_preview"] = tool_result[:200]
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})

        final_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                final_content = msg["content"]
                break

        result = {
            "status": "completed",
            "result": final_content,
            "iterations": iteration + 1,
            "tool_calls_log": tool_calls_log,
            "total_tokens": total_tokens_used,
            "messages": messages
        }
        _update_task_state(task_id, {"status": "completed", "result_data": result})
        return result

    except Exception as e:
        return {"status": "failed", "error": f"追问分析异常: {str(e)[:500]}"}

# -----------------------------------------------------------------------------
# 日志行选择相关回调
# -----------------------------------------------------------------------------

@app.callback(
    [Output("toggle-selection-mode-btn", "color"),
     Output("toggle-selection-mode-btn", "outline"),
     Output("toggle-selection-mode-btn", "children"),
     Output("clear-selection-btn", "style"),
     Output("selected-lines-count", "style")],
    [Input("toggle-selection-mode-btn", "n_clicks")],
    prevent_initial_call=True
)
def toggle_selection_mode(n_clicks):
    if not n_clicks:
        return "secondary", True, "🖱 选择行", {"display": "none"}, {"display": "none"}
    # Toggle global selection mode flag
    is_active = getattr(toggle_selection_mode, '_active', False)
    is_active = not is_active
    toggle_selection_mode._active = is_active
    if is_active:
        return "primary", False, "🖱 选择中", {"display": "inline-block"}, {"display": "inline-flex"}
    else:
        return "secondary", True, "🖱 选择行", {"display": "none"}, {"display": "none"}


@app.callback(
    [Output("selected-log-lines-store", "data"),
     Output("selected-lines-count", "children")],
    [Input("clear-selection-btn", "n_clicks")],
    [State("selected-log-lines-store", "data")],
    prevent_initial_call=True
)
def clear_line_selection(n_clicks, current_data):
    if not n_clicks:
        return dash.no_update, dash.no_update
    return [], ""


@app.callback(
    Output("selected-log-lines-store", "data", allow_duplicate=True),
    [Input("selected-lines-sync-input", "value")],
    prevent_initial_call=True
)
def sync_selected_lines_from_frontend(raw_value):
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except Exception:
        return dash.no_update
    return _normalize_selected_line_numbers(parsed)


def read_selected_lines_from_temp(session_id, line_numbers):
    """从临时过滤结果文件中读取指定行的内容和上下文信息

    Args:
        session_id: 过滤会话ID
        line_numbers: 要读取的行号列表（1-indexed，过滤结果中的行号）

    Returns:
        list of dicts: [{line_number, content, source_line_number, ...}]
    """
    if not line_numbers:
        return []

    temp_file = os.path.join(TEMP_DIR, f"filtered_{session_id}.txt")
    if not os.path.exists(temp_file):
        return []

    try:
        with open(temp_file, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
    except Exception as e:
        print(f"读取过滤结果失败: {e}")
        return []

    result = []
    for ln in sorted(line_numbers):
        idx = ln - 1  # 0-indexed
        if 0 <= idx < len(all_lines):
            content = all_lines[idx].rstrip('\n')
            # 尝试提取日志结构化信息
            parsed = _parse_log_line(content)
            result.append({
                "line_number": ln,
                "content": content,
                "timestamp": parsed.get("timestamp", ""),
                "tag": parsed.get("tag", ""),
                "level": parsed.get("level", ""),
                "message": parsed.get("message", "")
            })
    return result


def _parse_log_line(line):
    """解析单行日志，提取时间戳、Tag、级别、正文"""
    # Android logcat 格式: 01-01 12:00:00.000 123 456 E/Tag: message
    m = re.match(r'^(?P<timestamp>\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+\d+\s+\d+\s+(?P<level>[A-Z])/(?P<tag>\w+)\s*:\s*(?P<message>.*)', line)
    if m:
        return m.groupdict()
    # Android logcat 无进程ID: 01-01 12:00:00.000 E/Tag: message
    m = re.match(r'^(?P<timestamp>\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+(?P<level>[A-Z])/(?P<tag>\w+)\s*:\s*(?P<message>.*)', line)
    if m:
        return m.groupdict()
    # 简单时间戳: 01-01 12:00:00 message
    m = re.match(r'^(?P<timestamp>\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(?P<message>.*)', line)
    if m:
        return {**m.groupdict(), "tag": "", "level": ""}
    # ISO 时间戳: 2024-01-01T12:00:00.000Z message
    m = re.match(r'^(?P<timestamp>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}[^ ]*)\s+(?P<message>.*)', line)
    if m:
        return {**m.groupdict(), "tag": "", "level": ""}
    # 无法解析时，整行作为 message
    return {"timestamp": "", "tag": "", "level": "", "message": line}

# -----------------------------------------------------------------------------
# 文本选中 Chat/Copy 上下文菜单回调
# -----------------------------------------------------------------------------

@app.callback(
    [Output("chat-selected-text-store", "data"),
     Output("toast-container", "children", allow_duplicate=True)],
    [Input("chat-selected-text-input", "children")],
    prevent_initial_call=True
)
def on_chat_selected_text(children):
    text = children if isinstance(children, str) else ""
    if not text or not text.strip():
        return dash.no_update, dash.no_update
    return text.strip(), _toast_script(f"已选中 {len(text.strip())} 字符，可用于 AI 分析", "info")

# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    
    # 确保必要的目录存在
    ensure_temp_dir()
    ensure_log_dir()
    ensure_config_dir()
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Log Filter Application')
    parser.add_argument('--port', type=int, default=8052, help='Port to run the application on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind the application to')
    args = parser.parse_args()
    
    app.run(debug=False, port=args.port, host=args.host)
