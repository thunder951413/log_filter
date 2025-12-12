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
from datetime import datetime

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
        """生成缓存键（优化版本，处理时间戳变化）"""
        # 优化：对文本进行预处理，移除时间戳等变化内容
        processed_text = self._preprocess_text(text)
        
        # 使用处理后的文本内容、选中的字符串和配置数据的哈希作为键
        text_hash = hashlib.md5(processed_text.encode('utf-8')).hexdigest()
        strings_hash = hashlib.md5(str(selected_strings).encode('utf-8')).hexdigest()
        data_hash = hashlib.md5(json.dumps(data, sort_keys=True).encode('utf-8')).hexdigest()
        return f"{text_hash}:{strings_hash}:{data_hash}"
    
    def _preprocess_text(self, text):
        """预处理文本，移除时间戳等变化内容"""
        if not text:
            return ""
        
        lines = text.split('\n')
        processed_lines = []
        
        for line in lines:
            # 移除常见时间戳格式
            processed_line = self._remove_timestamps(line)
            processed_lines.append(processed_line)
        
        return '\n'.join(processed_lines)
    
    def _remove_timestamps(self, line):
        """移除行中的时间戳和进程信息"""
        # 常见日志前缀模式
        log_prefix_patterns = [
            # Android/系统日志格式: 10-19 20:38:49.474   455   504 I DTV_LOG : 
            r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+\d+\s+\d+\s+[A-Z]\s+\w+\s*:\s*',
            # 简化的系统日志格式: 10-19 20:38:49.474   455   504 I : 
            r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+\d+\s+\d+\s+[A-Z]\s*:\s*',
            # 带标签的系统日志: 10-19 20:38:49.474   455   504 I TAG : 
            r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+\d+\s+\d+\s+[A-Z]\s+\w+\s*:\s*',
            # 标准系统日志: 10-19 20:38:49.474 I/TAG : 
            r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+[A-Z]/\w+\s*:\s*',
            # ISO 8601格式: 2024-01-15 10:30:25
            r'^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?\s+',
            # 简写格式: 01-15 10:30:25
            r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+',
            # 时间格式: 10:30:25
            r'^\d{2}:\d{2}:\d{2}\s+',
            # 日志级别格式: [INFO] [2024-01-15 10:30:25]
            r'^\[\w+\]\s*\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]\s+',
            # Unix时间戳: [1705307425]
            r'^\[\d{10,13}\]\s+',
        ]
        
        for pattern in log_prefix_patterns:
            # 使用正则表达式移除匹配的前缀
            import re
            match = re.match(pattern, line)
            if match:
                # 返回移除前缀后的内容
                return line[match.end():].strip()
        
        # 如果没有匹配的模式，返回原行
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
_SOURCE_PREVIEW_LINES = 2000  # 源文件tab预览行数上限
_UI_BUSY_STORE_ID = "ui-busy-store"


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
app = dash.Dash(
    __name__, 
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    assets_folder=os.path.join(base_path, "assets")
)

# 配置Dash使用标准JSON序列化，避免orjson问题
try:
    import json as std_json
    # 尝试禁用orjson
    import os
    os.environ['DASH_SERIALIZER'] = 'json'
except:
    pass

# 数据存储文件路径
DATA_FILE = 'string_data.json'
ANNOTATIONS_FILE = 'keyword_annotations.json'
FLOWS_CONFIG_FILE = 'flows.json'

# 获取所有配置文件
CONFIG_DIR = os.path.join(os.getcwd(), 'configs')
# 临时关键字配置放在项目根目录，便于随应用启动/刷新自动加载
TEMP_KEYWORDS_FILE = os.path.join(os.getcwd(), 'temp_keywords.json')
# 外部程序配置
EXTERNAL_PROGRAM_CONFIG_FILE = os.path.join(os.getcwd(), 'external_program_config.json')

# 日志文件目录
LOG_DIR = 'logs'

# 临时文件目录（用于存储过滤结果）
TEMP_DIR = 'temp'

# ... (existing code)

# 外部程序配置管理
def load_external_program_config():
    if os.path.exists(EXTERNAL_PROGRAM_CONFIG_FILE):
        try:
            with open(EXTERNAL_PROGRAM_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Loading external program config failed: {e}")
    return {"path": ""}

def save_external_program_config(path):
    try:
        with open(EXTERNAL_PROGRAM_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({"path": path}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Saving external program config failed: {e}")
        return False

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

def ensure_log_dir():
    """确保日志目录存在"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

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
                if file.endswith('.json'):
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
            mtime = os.path.getmtime(LOG_DIR)
            if _log_files_cache["mtime"] == mtime and _log_files_cache["data"] is not None:
                return _log_files_cache["data"]
            log_files = [
                file for file in os.listdir(LOG_DIR)
                if file.endswith(('.txt', '.log', '.text'))
            ]
            _log_files_cache["mtime"] = mtime
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
def _init_filter_task(session_id, log_path, keep_strings, filter_strings, selected_strings):
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
        }


def _update_filter_task(session_id, **kwargs):
    with _filter_tasks_lock:
        if session_id not in _filter_tasks:
            return
        _filter_tasks[session_id].update(kwargs)


def _get_filter_task(session_id):
    with _filter_tasks_lock:
        return _filter_tasks.get(session_id, {}).copy()


def _estimate_total_lines(log_path):
    try:
        size = os.path.getsize(log_path)
        # 粗略估计：假设平均 100 字节/行
        return max(1, size // 100)
    except Exception:
        return None


def _filter_worker(session_id, log_path, keep_strings, filter_strings, index_every=500):
    try:
        # print(f"[过滤线程] start session={session_id}, log_path={log_path}")
        # print(f"[过滤线程] keep_strings={keep_strings}, filter_strings={filter_strings}")
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

        with open(log_path, 'rb') as src, open(temp_file_path, 'wb') as dst:
            for raw_line in src:
                text_line = None
                if keep_bytes_regex:
                    if not keep_bytes_regex.search(raw_line):
                        continue
                elif keep_regex:
                    try:
                        text_line = raw_line.decode(encoding)
                    except UnicodeDecodeError:
                        text_line = raw_line.decode(encoding, errors='replace')
                    if not keep_regex.search(text_line):
                        continue

                if filter_bytes_regex:
                    if filter_bytes_regex.search(raw_line):
                        continue
                elif filter_regex:
                    if text_line is None:
                        try:
                            text_line = raw_line.decode(encoding)
                        except UnicodeDecodeError:
                            text_line = raw_line.decode(encoding, errors='replace')
                    if filter_regex.search(text_line):
                        continue

                dst.write(raw_line)
                line_count += 1
                if line_count % index_every == 1:
                    offsets.append([line_count, current_offset])
                current_offset += len(raw_line)

                if not _get_filter_task(session_id) or _get_filter_task(session_id).get("status") != "running":
                    raise RuntimeError("任务已取消")

                if not _get_filter_task(session_id).get("first_ready") and line_count >= _FILTER_CHUNK_LINES:
                    _update_filter_task(session_id, first_ready=True)
                    print(f"[过滤线程] session={session_id} 首片就绪, 行数={line_count}")

                if line_count % 500 == 0:
                    _update_filter_task(session_id, done_lines=line_count)
                    # print(f"[过滤线程] session={session_id} 进度行数={line_count}")

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
    ensure_log_dir()
    # 确保文件名是字符串类型，并正确处理空格
    if not isinstance(log_filename, str):
        log_filename = str(log_filename)
    # 使用os.path.join正确处理路径，包括文件名中的空格
    return os.path.join(LOG_DIR, log_filename)

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

def _format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"

def _create_file_list_table(log_files):
    if not log_files:
        return html.Div("暂无上传的文件", className="text-muted text-center p-3")
    
    # 预处理文件信息以便排序
    file_info_list = []
    today = datetime.now().date()
    
    for file in log_files:
        # Ensure file name is string and handle spaces
        if not isinstance(file, str):
            file = str(file)
            
        file_path = os.path.join(LOG_DIR, file)
        if not os.path.exists(file_path):
            continue
            
        try:
            stat = os.stat(file_path)
            file_size = stat.st_size
            mtime = stat.st_mtime
            mtime_dt = datetime.fromtimestamp(mtime)
            
            file_info_list.append({
                "name": file,
                "size": file_size,
                "mtime": mtime,
                "mtime_dt": mtime_dt
            })
        except Exception:
            continue
    
    # 按修改时间降序排序（最新的在最上面）
    file_info_list.sort(key=lambda x: x["mtime"], reverse=True)
    
    rows = []
    for info in file_info_list:
        file = info["name"]
        file_size = info["size"]
        file_mtime = info["mtime_dt"].strftime('%Y-%m-%d %H:%M:%S')
        
        # 判断是否是当天上传/修改的文件
        row_class = ""
        if info["mtime_dt"].date() == today:
            row_class = "table-warning"  # Bootstrap 警告色（浅黄）
        
        rows.append(html.Tr([
            html.Td(file, className="align-middle"),
            html.Td(_format_size(file_size), className="align-middle"),
            html.Td(file_mtime, className="align-middle"),
            html.Td(
                [
                    dbc.Button(
                        "重命名", 
                        id={"type": "rename-file-btn", "index": file}, 
                        color="secondary", 
                        size="sm",
                        outline=True,
                        className="me-2"
                    ),
                    dbc.Button(
                        "删除", 
                        id={"type": "delete-file-btn", "index": file}, 
                        color="danger", 
                        size="sm",
                        outline=True
                    )
                ], 
                className="align-middle"
            )
        ], className=row_class))
    
    return dbc.Table(
        [
            html.Thead(html.Tr([
                html.Th("文件名"), 
                html.Th("大小"), 
                html.Th("修改时间"), 
                html.Th("操作", style={"width": "180px"})
            ])),
            html.Tbody(rows)
        ],
        hover=True,
        striped=True,
        bordered=True,
        responsive=True,
        className="mb-0"
    )

# 初始数据
data = load_data()

# 确保配置目录存在
ensure_config_dir()
# 加载外部程序配置
ext_prog_config = load_external_program_config()

# 应用布局
app.layout = html.Div([
    # Toast通知容器
    html.Div(id="toast-container", className="toast-container"),
    dcc.Store(id="group-selected-files-store", data=[]),
    dcc.Store(id="filter-session-store", data=""),
    dcc.Store(id="filter-first-chunk-ready", data=False),
    dcc.Interval(id="filter-progress-interval", interval=_FILTER_PROGRESS_INTERVAL_MS, disabled=True),
    dcc.Store(id=_UI_BUSY_STORE_ID, data=False),
    dcc.Location(id="url", refresh=False),
    
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
                    dbc.Tab(label="配置管理", tab_id="tab-2"),
                    dbc.Tab(label="日志管理", tab_id="tab-3"),
                    dbc.Tab(label="关键字注释(开发中)", tab_id="tab-4")
                ], id="main-tabs", active_tab="tab-1")
            ], width=12)
        ], className="mb-4"),
        
        # Tab1内容 - 日志过滤
        html.Div(id="tab-1-content", children=[
            # 右上角固定按钮区域
            html.Div([
                html.Div([
                    html.Div([
                        dcc.Dropdown(
                            id="log-file-selector",
                            placeholder="选择日志文件...",
                            options=[],
                            clearable=False,
                            style={"width": "250px", "fontSize": "12px", "textAlign": "left"}
                        )
                    ], className="d-inline-block me-2 align-middle"),
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
                                                    html.Div(id="log-filter-results", style={"maxHeight": "calc(100vh - 300px)", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px", "fontFamily": "monospace", "fontSize": "12px"}),
                                                    html.Div([
                                                        dbc.Progress(id="filter-progress-bar", value=0, striped=True, animated=True, className="my-2", style={"height": "8px", "minWidth": "200px"}),
                                                        html.Div(id="filter-progress-text", className="small text-muted mb-1")
                                                    ], id="filter-progress-footer", className="mt-1", style={"display": "none"})
                                                ]),
                                                dbc.Tab(label="源文件", tab_id="source", children=[
                                                    html.Div(id="log-source-results", style={"maxHeight": "calc(100vh - 300px)", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px", "fontFamily": "monospace", "fontSize": "12px"})
                                                ]),
                                                dbc.Tab(label="高亮显示", tab_id="highlight", children=[
                                                    html.Div(id="log-highlight-results", style={"maxHeight": "calc(100vh - 300px)", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px", "fontFamily": "monospace", "fontSize": "12px"})
                                                ]),
                                                dbc.Tab(label="注释", tab_id="annotation", children=[
                                                    html.Div(id="log-annotation-results", style={"maxHeight": "calc(100vh - 300px)", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px", "fontFamily": "monospace", "fontSize": "12px"})
                                                ]),
                                                dbc.Tab(label="流程视图", tab_id="flows", children=[
                                                    html.Div(id="log-flows-results", style={"maxHeight": "calc(100vh - 300px)", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px", "fontFamily": "monospace", "fontSize": "12px"})
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
                                                dbc.Button(id="log-view-ready-signal-btn", style={"display": "none"})
                                            ], className="d-flex align-items-center gap-2 justify-content-start")
                                        ], width=6),
                                        dbc.Col([
                                            html.Div([
                                                dbc.InputGroup([
                                                    dbc.Button("查找上一个", id="global-search-prev-btn", color="secondary"),
                                                    dbc.Input(id="global-search-input", type="text", placeholder="搜索关键字...", debounce=True, list="search-suggestions"),
                                                    html.Datalist(id="search-suggestions", children=[]),
                                                    dbc.Button("查找/下一个", id="global-search-btn", color="info")
                                                ], size="sm", className="me-2", style={"maxWidth": "420px"}),
                                                dbc.InputGroup([
                                                    dbc.Input(id="jump-line-input", type="number", placeholder="行号", min=1, step=1),
                                                    dbc.Button("跳转", id="jump-line-btn", color="primary")
                                                ], size="sm", style={"maxWidth": "220px"})
                                            ], className="d-flex justify-content-end align-items-center gap-2")
                                        ], width=6)
                                    ], className="w-100")
                                ], width=12)
                                    ])
                                ], width=12)
                            ], className="mb-3"),
                        ])
                    ])
                ], width=12)
            ], className="mb-4"),
        ], style={"display": "block"}),
        
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
                                        html.Div(id="selected-strings-container", style={"maxHeight": "calc(100vh - 250px)", "overflowY": "auto"})
                                    ], width=6),
                                    
                                    # 右侧：已保存的字符串
                                    dbc.Col([
                                        html.H4("已保存的字符串", className="card-title"),
                                        dcc.Dropdown(
                                            id="category-filter",
                                            options=[{"label": "所有分类", "value": "all"}] + 
                                                    [{"label": cat, "value": cat} for cat in data["categories"].keys()],
                                            value="all",
                                            clearable=False
                                        ),
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
                                        html.Div(id="saved-strings-container", style={"maxHeight": "375px", "overflowY": "auto", "marginTop": "10px"}),
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
                                        html.Span('拖拽文件到此处或点击选择文件', className="fw-bold")
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
                                    multiple=False,
                                    accept='.txt,.log'
                                ),
                                html.Div(id='upload-status', className="text-center small")
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
        dcc.Store(id='data-store', data=load_data()),
        dcc.Store(id='filtered-result-store', data=''),
        dcc.Store(id='source-result-store', data=''),
        dcc.Store(id='selected-strings', data=[]),
        dcc.Store(id='filter-tab-strings-store', data=[]),  # 日志过滤tab专用的字符串存储
        dcc.Store(id='selected-log-file', data=''),
        dcc.Store(id='string-type-store', data='keep'),  # 存储字符串类型选择，默认为"keep"
        dcc.Store(id='selected-config-files', data=[]),  # 存储选中的配置文件列表（支持多选）
        dcc.Store(id='temp-keywords-store', data=load_temp_keywords_from_file()),  # 存储临时关键字列表（支持保留/屏蔽）
        dcc.Store(id='keyword-annotations-store', data=load_annotations()),  # 存储关键字注释映射
        dcc.Store(id='flows-config-store', data=load_flows_config()),  # 存储流程关键字配置
        dcc.Store(id='rename-target-file', data=''),  # 存储待重命名的文件
        
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
        
    ], fluid=True)
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


# 文件选择后，标记 UI 正在忙（禁用分组按钮等）
@app.callback(
    Output(_UI_BUSY_STORE_ID, "data"),
    [Input("log-file-selector", "value")],
    prevent_initial_call=True
)
def mark_ui_busy_on_file_change(selected_log_file):
    if selected_log_file:
        return True
    return False



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
        files = get_log_files()
        options = [{"label": f, "value": f} for f in files]
        if target not in files:
            options.append({"label": target, "value": target})
        return options, target, html.Script("if(window.showToast) window.showToast('已打开日志', 'success');")
    except Exception:
        return dash.no_update, dash.no_update, html.Script("if(window.showToast) window.showToast('打开日志失败', 'error');")

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



# 过滤按钮加载状态控制回调
@app.callback(
    [Output("filter-loading-spinner", "spinner_style"),
     Output("filter-btn-text", "children"),
     Output("execute-filter-btn", "disabled")],
    [Input("execute-filter-btn", "n_clicks")],
    [State("filter-loading-spinner", "spinner_style")],
    prevent_initial_call=True
)
def toggle_filter_loading(n_clicks, current_style):
    if n_clicks:
        # 显示加载状态
        return {"display": "inline-block", "marginLeft": "5px"}, "处理中...", True
    return current_style, "过滤", False

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
     Output("filter-progress-footer", "style", allow_duplicate=True),
     Output("filter-loading-spinner", "spinner_style", allow_duplicate=True),
     Output("filter-btn-text", "children", allow_duplicate=True),
     Output("execute-filter-btn", "disabled", allow_duplicate=True),
     Output("execute-filter-btn", "color", allow_duplicate=True),
     Output("filter-session-store", "data"),
     Output("filter-progress-interval", "disabled", allow_duplicate=True),
     Output("filter-progress-interval", "n_intervals", allow_duplicate=True),
     Output("filter-first-chunk-ready", "data")],
    [Input("execute-filter-btn", "n_clicks")],
    [State("filter-tab-strings-store", "data"),
     State("temp-keywords-store", "data"),
     State("log-file-selector", "value"),
     State("main-tabs", "active_tab")],
    prevent_initial_call=True
)
def execute_filter_command(n_clicks, filter_tab_strings, temp_keywords, selected_log_file, active_tab):
    # 只有在日志过滤tab激活时才处理回调
    if active_tab != "tab-1" or not n_clicks:
        return (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update, dash.no_update)
    
    # 先清空旧任务，避免残留状态影响新一轮过滤
    _clear_all_filter_tasks(delete_files=False)
    
    # 执行过滤命令，包含临时关键字
    session_id, filtered_result = execute_filter_logic(filter_tab_strings, temp_keywords, selected_log_file)
    try:
        print(f"[过滤UI] 启动过滤 session={session_id}, n_clicks={n_clicks}")
    except Exception:
        pass
    
    # 启动进度轮询，首片尚未就绪；重置存储、启用interval、按钮置忙，并重置 interval 计数
    return (
        filtered_result,                # log-filter-results 显示进度组件
        "",                             # filtered-result-store 清空
        0,                              # 重置底部进度条
        "",                             # 重置进度文字
        {"display": "block"},           # 展示底部进度条区域
        {"display": "inline-block", "marginLeft": "5px"},  # spinner 显示
        "处理中...",                    # 按钮文案
        True,                           # 按钮禁用
        "success",                      # 按钮颜色设为绿色
        session_id or "",               # 会话
        False,                          # interval 启用 (disabled=False)
        0,                              # 重置轮询计数
        False                           # 首片未就绪
    )


# 客户端回调：选择文件后立即禁用过滤按钮并显示等待
app.clientside_callback(
    """
    function(value) {
        if (value) {
            return [true, "secondary", "等待后端刷新...", "badge bg-warning text-dark ms-2"];
        }
        return [window.dash_clientside.no_update, window.dash_clientside.no_update, window.dash_clientside.no_update, window.dash_clientside.no_update];
    }
    """,
    [Output("execute-filter-btn", "disabled", allow_duplicate=True),
     Output("execute-filter-btn", "color", allow_duplicate=True),
     Output("log-view-status-bar", "children", allow_duplicate=True),
     Output("log-view-status-bar", "className", allow_duplicate=True)],
    Input("log-file-selector", "value"),
    prevent_initial_call=True
)


# 选择文件后加载其他Tab内容
@app.callback(
    [Output("log-source-results", "children"),
     Output("log-highlight-results", "children"),
     Output("log-annotation-results", "children"),
     Output("log-flows-results", "children"),
     Output("source-result-store", "data"),
     Output("log-filter-results", "children", allow_duplicate=True),
     Output(_UI_BUSY_STORE_ID, "data", allow_duplicate=True)],
    [Input("log-file-selector", "value")],
    [State("filter-tab-strings-store", "data"),
     State("temp-keywords-store", "data"),
     State("keyword-annotations-store", "data"),
     State("main-tabs", "active_tab")],
    prevent_initial_call=True
)
def load_tab_contents_on_file_select(selected_log_file, filter_tab_strings, temp_keywords, annotations_map, active_tab):
    if not selected_log_file:
        return "", "", "", "", "", "", False
        
    # 源文件视图使用滚动窗口，便于查找/跳转
    source_command, source_result = execute_source_logic(selected_log_file, filter_tab_strings, temp_keywords)
    
    # 高亮模式
    highlight_result = ""
    highlight_strings = load_highlight_config()
    if highlight_strings:
        _, highlight_result = execute_filter_logic(highlight_strings, [], selected_log_file)
    else:
        highlight_result = html.P("未找到highlight配置文件或配置为空", className="text-warning text-center")
        
    # 注释模式
    annotation_component = build_annotation_extract_display_by_matching(selected_log_file, annotations_map)
    
    # 流程视图
    flows_component = build_flows_display(selected_log_file)
    
    # 过滤按钮状态已由客户端回调和rolling.js处理，此处无需重复设置
    return source_result, highlight_result, annotation_component, flows_component, source_result, "", False

 

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
                "offsets": offsets
            }, idx_file, ensure_ascii=False)
    except Exception as e:
        print(f"[过滤] 构建索引失败: {e}")
    return line_count


def _escape_shell_pattern(pattern: str) -> str:
    """简单转义单引号，供shell/grep使用"""
    return pattern.replace("'", "'\"'\"'")


def _build_patterns(keep_strings, filter_strings):
    keep_parts = [re.escape(s) for s in keep_strings or [] if s]
    filter_parts = [re.escape(s) for s in filter_strings or [] if s]
    keep_pattern = "|".join(keep_parts) if keep_parts else ""
    filter_pattern = "|".join(filter_parts) if filter_parts else ""
    return keep_pattern, filter_pattern


def _stream_filter_to_temp_unix(log_path, temp_file_path, idx_path, keep_pattern, filter_pattern, encoding, index_every):
    """使用系统 grep 过滤（类 Unix）"""
    # 构建管道：grep keep | grep -v filter
    if keep_pattern:
        cmd = f"grep -a -i -E '{_escape_shell_pattern(keep_pattern)}' \"{log_path}\""
    else:
        cmd = f"cat \"{log_path}\""
    if filter_pattern:
        cmd += f" | grep -a -i -E -v '{_escape_shell_pattern(filter_pattern)}'"
    cmd += f" > \"{temp_file_path}\""
    print(f"[过滤] 使用系统 grep 执行: {cmd}")
    result = subprocess.run(cmd, shell=True)
    # grep 无匹配时返回码 1，视为正常
    if result.returncode not in (0, 1):
        raise RuntimeError(f"系统过滤失败，返回码 {result.returncode}")
    line_count = _build_temp_index(temp_file_path, idx_path, encoding, index_every=index_every)
    print(f"[过滤] 完成，输出: {temp_file_path}, 行数: {line_count}")
    return temp_file_path, idx_path, line_count, encoding


def _stream_filter_to_temp_windows(log_path, temp_file_path, idx_path, keep_pattern, filter_pattern, index_every):
    """使用 PowerShell Select-String 过滤（Windows）"""
    # 使用简单匹配，默认不区分大小写
    ps_cmd = f"Get-Content -Path \"{log_path}\""
    if keep_pattern:
        ps_cmd += f" | Select-String -SimpleMatch -CaseSensitive:$false -Pattern '{keep_pattern}'"
    if filter_pattern:
        ps_cmd += f" | Select-String -SimpleMatch -CaseSensitive:$false -NotMatch -Pattern '{filter_pattern}'"
    ps_cmd += f" | Out-File -FilePath \"{temp_file_path}\" -Encoding utf8"
    full_cmd = f'powershell -NoProfile -Command "{ps_cmd}"'
    print(f"[过滤] 使用PowerShell过滤: {full_cmd}")
    result = subprocess.run(full_cmd, shell=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"PowerShell 过滤失败，返回码 {result.returncode}")
    # 输出为utf-8
    encoding = "utf-8"
    line_count = _build_temp_index(temp_file_path, idx_path, encoding, index_every=index_every)
    print(f"[过滤] 完成，输出: {temp_file_path}, 行数: {line_count}")
    return temp_file_path, idx_path, line_count, encoding


def stream_filter_to_temp(log_path, keep_regex, filter_regex, keep_strings, filter_strings, session_id=None, index_every=500):
    """使用系统 grep/PowerShell 过滤日志到临时文件，并生成索引"""
    ensure_temp_dir()
    temp_file_path = get_temp_file_path(session_id)
    idx_path = get_temp_index_path(temp_file_path)
    keep_pattern, filter_pattern = _build_patterns(keep_strings, filter_strings)
    encoding = detect_file_encoding(log_path)
    
    if os.name == "nt":
        return _stream_filter_to_temp_windows(log_path, temp_file_path, idx_path, keep_pattern, filter_pattern, index_every)
    else:
        return _stream_filter_to_temp_unix(log_path, temp_file_path, idx_path, keep_pattern, filter_pattern, encoding, index_every)


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


def execute_filter_logic(selected_strings, temp_keywords, selected_log_file):
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
    _init_filter_task(session_id, log_path, keep_strings, filter_strings, all_strings)
    thread = threading.Thread(target=_filter_worker, args=(session_id, log_path, keep_strings, filter_strings))
    thread.daemon = True
    thread.start()
    
    progress_component = html.Div([
        html.Div(id="filter-partial-display")
    ])
    
    # 返回 session_id 用于前端轮询
    return session_id, progress_component


# 过滤进度轮询
@app.callback(
    [Output("filter-progress-bar", "value", allow_duplicate=True),
     Output("filter-progress-text", "children", allow_duplicate=True),
     Output("filter-partial-display", "children", allow_duplicate=True),
     Output("filter-progress-inline", "children", allow_duplicate=True),
     Output("filter-progress-footer", "style", allow_duplicate=True),
     Output("filter-progress-interval", "disabled", allow_duplicate=True),
     Output("filter-session-store", "data", allow_duplicate=True),
     Output("filter-first-chunk-ready", "data", allow_duplicate=True),
     Output("log-filter-results", "children", allow_duplicate=True),
     Output("filtered-result-store", "data", allow_duplicate=True),
     Output("filter-loading-spinner", "spinner_style", allow_duplicate=True),
     Output("filter-btn-text", "children", allow_duplicate=True),
     Output("execute-filter-btn", "disabled", allow_duplicate=True)],
    [Input("filter-progress-interval", "n_intervals")],
    [State("filter-session-store", "data"),
     State("main-tabs", "active_tab")],
    prevent_initial_call=True
)
def poll_filter_progress(n_intervals, session_id, active_tab):
    spinner_hide = {"display": "none", "marginLeft": "5px"}
    progress_footer_show = {"display": "block"}
    progress_footer_hide = {"display": "none"}
    if active_tab != "tab-1" or not session_id:
        print(f"[进度] 跳过轮询 active_tab={active_tab} session_id={session_id}")
        return (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, True,
                dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update, dash.no_update)
    
    task = _get_filter_task(session_id)
    if not task:
        print(f"[进度] session={session_id} 未找到任务(可能是旧轮询)，暂不停止轮询")
        return (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update, dash.no_update, dash.no_update,
                dash.no_update, dash.no_update, dash.no_update, dash.no_update)
    
    # 错误处理
    if task.get("status") == "error":
        err_div = html.Div([
            html.P("过滤失败:", className="text-danger"),
            html.Pre(task.get("error"), className="text-danger small")
        ])
        print(f"[进度] session={session_id} 状态=error, err={task.get('error')}")
        return (0, "过滤失败", err_div, "", progress_footer_show, True, "", True, err_div, err_div,
                spinner_hide, "过滤", False)
    
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
        return (percent if percent is not None else 1, progress_text, partial_display, "", progress_footer_show, False, session_id, True,
                dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update)
    
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
        return (100, "完成", dash.no_update, inline_progress, progress_footer_hide, True, "", "",
                final_display, final_display, spinner_hide, "过滤", False)
    
    # 仍在进行，但未到首片
    inline_progress = ""  # 不再显示顶部内联进度条
    return (percent, progress_text, dash.no_update, inline_progress, progress_footer_show, False, session_id, dash.no_update,
            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update)

def execute_source_logic(selected_log_file, selected_strings=None, temp_keywords=None):
    """执行源文件逻辑，包含临时关键字"""
    # 本地方式显示源文件
    if not selected_log_file:
        return "", html.P("请选择日志文件", className="text-danger text-center")
    log_path = get_log_path(selected_log_file)
    if os.name == 'nt':
        full_command = f"powershell -NoProfile -Command \"Get-Content -Path \"{log_path}\"\""
    else:
        full_command = f"cat \"{log_path}\""
    
    # 合并选中的字符串和临时关键字
    normalized_temp_keywords = normalize_temp_keywords(temp_keywords)
    all_strings = []
    if selected_strings:
        all_strings.extend(selected_strings)
    all_strings.extend(normalized_temp_keywords)
    
    # 执行命令：源文件页面的滚动、跳转与搜索基于原始日志生成的临时文件
    try:
        session_id = hashlib.md5(full_command.encode()).hexdigest()
    except Exception:
        session_id = None
    if all_strings:
        data = load_data()  # 加载当前数据
        result_display = execute_command(full_command, all_strings, data, save_to_temp=True, session_id=session_id)
    else:
        result_display = execute_command(full_command, save_to_temp=True, session_id=session_id)
    
    return full_command, result_display


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

def _run_command_capture_text(full_command):
    """执行命令并返回解码后的文本（最佳努力解码）"""
    try:
        result = subprocess.run(full_command, shell=True, capture_output=True, text=False, timeout=30)
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

def build_annotation_match_command(selected_log_file, annotations_map):
    """构建使用所有注释关键字匹配日志的命令"""
    if not selected_log_file:
        return ""
    log_path = get_log_path(selected_log_file)
    keywords = [str(k) for k in (annotations_map or {}).keys() if str(k)]
    if not keywords:
        if os.name == 'nt':
            return f"powershell -NoProfile -Command \"Get-Content -Path \"{log_path}\"\""
        return f"cat \"{log_path}\""
    escaped = [re.escape(k) for k in keywords]
    pattern = escaped[0] if len(escaped) == 1 else f"({'|'.join(escaped)})"
    if os.name == 'nt':
        p = pattern.replace("'", "''")
        return f"powershell -NoProfile -Command \"Get-Content -Path \"{log_path}\" | Select-String -Pattern '{p}' | ForEach-Object {{ $_.Line }}\""
    return f"grep -E '{pattern}' \"{log_path}\""

def build_annotation_extract_display_by_matching(selected_log_file, annotations_map):
    """使用所有注释关键字匹配日志并显示对应注释列表"""
    if not selected_log_file:
        return html.P("请选择日志文件", className="text-danger text-center")
    if not annotations_map:
        return html.P("未设置关键字注释", className="text-muted")
    cmd = build_annotation_match_command(selected_log_file, annotations_map)
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

def build_flows_display(selected_log_file):
    """基于流程配置构建括号缩进的流程视图"""
    try:
        if not selected_log_file:
            return html.P("请选择日志文件", className="text-danger text-center")

        cfg = load_flows_config()
        paired_defs = cfg.get('paired', []) or []
        seq_defs = cfg.get('sequences', []) or []

        if not paired_defs and not seq_defs:
            return html.P("未找到流程配置（configs/flows.json），请先配置 paired 或 sequences", className="text-muted text-center")

        # 为不同流程名称分配不同颜色
        flow_names = []
        for p in paired_defs:
            n = str((p or {}).get('name') or '').strip()
            if n:
                flow_names.append(n)
        for s in seq_defs:
            n = str((s or {}).get('name') or '').strip()
            if n:
                flow_names.append(n)
        # 去重保持顺序
        flow_names = list(dict.fromkeys(flow_names))
        flow_colors = get_category_colors(flow_names)

        log_path = get_log_path(selected_log_file)
        if not os.path.exists(log_path):
            return html.P(f"日志文件不存在: {selected_log_file}", className="text-danger text-center")

        # 读取日志文本（尝试多种编码）
        def read_text(path):
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'iso-8859-1']
            for enc in encodings:
                try:
                    with open(path, 'r', encoding=enc, errors='replace') as f:
                        return f.readlines()
                except Exception:
                    continue
            with open(path, 'r', encoding='latin-1', errors='replace') as f:
                return f.readlines()

        lines = read_text(log_path)

        # 辅助：仅去除时间戳前缀（保留标签/级别等字符前缀）
        prefix_patterns = [
            # 仅时间戳（YYYY-MM-DD 或 MM-DD + 时间）
            r'^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?\s+',
            r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+',
            r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+',
            r'^\d{2}:\d{2}:\d{2}\.\d{3}\s+',
            r'^\d{2}:\d{2}:\d{2}\s+',
            # 括号/方括号形式的纯时间戳
            r'^\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?\]\s+',
            r'^\[\d{10,13}\]\s+'
        ]

        def strip_prefix(s: str) -> str:
            for p in prefix_patterns:
                m = re.match(p, s)
                if m:
                    return s[m.end():].rstrip('\n')
            return s.rstrip('\n')

        # 配对流程：栈管理
        stack = []  # 每项: {name, end, start_line}

        # 序列流程：每个定义维护当前索引
        seq_states = {}
        for seq in seq_defs:
            name = str(seq.get('name') or '').strip()
            steps = seq.get('steps') or []
            if not name or not isinstance(steps, list) or not steps:
                continue
            seq_states[name] = {
                'steps': steps,
                'idx': 0
            }

        out_lines = []

        for raw in lines:
            line = raw.rstrip('\n')
            show_line = strip_prefix(line)
            # 序列/配对匹配：优先对去前缀后的可读内容匹配，未命中则回退到原始整行
            def _matches(keyword):
                return _flow_keyword_matches(show_line, keyword) or _flow_keyword_matches(line, keyword)
            if not show_line:
                continue

            # 1) 处理配对型流程（先检查end，再检查start）
            if paired_defs:
                # 结束关键词
                for p in paired_defs:
                    name = str(p.get('name') or '').strip()
                    end_kw = str(p.get('end') or '').strip()
                    if not name or not end_kw:
                        continue
                    if end_kw and _matches(end_kw):
                        matched_index = None
                        for i in range(len(stack) - 1, -1, -1):
                            if stack[i]['name'] == name:
                                matched_index = i
                                break
                        if matched_index is None:
                            out_lines.append(f"! 未匹配的结束: {name} | {show_line}")
                        else:
                            for j in range(len(stack) - 1, matched_index, -1):
                                miss_name = stack[j]['name']
                                indent = '  ' * j
                                out_lines.append(f"{indent}! {miss_name} 缺少结束")
                                stack.pop()
                            level = matched_index
                            indent = '  ' * level
                            out_lines.append(f"{indent}- {name} END | {show_line}")
                            stack.pop()

                # 开始关键词
                for p in paired_defs:
                    name = str(p.get('name') or '').strip()
                    start_kw = str(p.get('start') or '').strip()
                    if not name or not start_kw:
                        continue
                    if start_kw and _matches(start_kw):
                        level = len(stack)
                        indent = '  ' * level
                        out_lines.append(f"{indent}+ {name} START | {show_line}")
                        stack.append({'name': name, 'end': str(p.get('end') or '').strip(), 'start_line': show_line})

            # 2) 处理序列型流程
            if seq_states:
                for name, state in seq_states.items():
                    steps = state['steps']
                    idx = state['idx']
                    if 0 <= idx < len(steps):
                        expected = str(steps[idx])
                        if expected and _matches(expected):
                            indent = '  ' * idx
                            out_lines.append(f"{indent}* {name} [{idx+1}/{len(steps)}] {expected} | {show_line}")
                            state['idx'] += 1
                            continue
                    first = str(steps[0]) if steps else ''
                    if first and _matches(first) and idx > 0:
                        missing = steps[idx:]
                        if missing:
                            indent = '  ' * idx
                            out_lines.append(f"{indent}! {name} 缺少: {' -> '.join(missing)}")
                        out_lines.append(f"* {name} [1/{len(steps)}] {first} | {show_line}")
                        state['idx'] = 1

        # 文件结束后的收尾
        for i, item in enumerate(stack):
            indent = '  ' * i
            out_lines.append(f"{indent}! {item['name']} 缺少结束")

        for name, state in seq_states.items():
            idx = state['idx']
            steps = state['steps']
            if 0 < idx < len(steps):
                missing = steps[idx:]
                indent = '  ' * idx
                out_lines.append(f"{indent}! {name} 缺少: {' -> '.join(missing)}")

        if not out_lines:
            return html.P("未匹配到流程相关记录", className="text-muted text-center")

        # 按行渲染：为未匹配/缺失项加红色，为不同流程添加专属颜色标识
        line_components = []
        for ln in out_lines:
            is_error = ln.strip().startswith('! ')
            style = {
                'whiteSpace': 'pre',
                'fontFamily': 'monospace',
                'fontSize': '12px'
            }
            if is_error:
                # Bootstrap danger 红色系
                style.update({'color': '#d9534f', 'fontWeight': 'bold'})
            else:
                # 解析流程名称以应用对应颜色
                flow_name = None
                try:
                    stripped = ln.lstrip()
                    if stripped:
                        marker = stripped[0]
                        body = stripped[2:] if len(stripped) > 2 else ''
                        if marker in ['+', '-']:
                            # "+ {name} START | ..." 或 "- {name} END | ..."
                            flow_name = body.split(' ', 1)[0] if body else None
                        elif marker == '*':
                            # "* {name} [i/n] step | ..."
                            flow_name = body.split(' [', 1)[0] if body else None
                except Exception:
                    flow_name = None

                if flow_name and flow_name in flow_colors:
                    # 使用左侧彩色边框标识不同流程
                    style.update({'borderLeft': f"4px solid {flow_colors[flow_name]}", 'paddingLeft': '6px'})

            line_components.append(html.Div(ln, style=style))

        return html.Div(line_components)
    except Exception as e:
        print(f"构建流程视图失败: {e}")
        return html.P(f"构建流程视图失败: {e}", className="text-danger text-center")


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

def get_file_line_count(file_path):
    """获取文件的总行数"""
    try:
        print(f"[滚动窗口] 开始计算文件行数: {file_path}")
        with open(file_path, 'rb') as f:
            count = sum(1 for _ in f)
        print(f"[滚动窗口] 文件总行数: {count}")
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
        print(f"[滚动窗口] 读取文件行范围: {file_path}, 行 {start_line} - {end_line}")
        if start_line > end_line:
            return "", encoding or "utf-8"
        
        idx_path = get_temp_index_path(file_path)
        has_index = os.path.exists(idx_path)
        
        # 加载索引信息（如果存在）
        idx_encoding = None
        offsets = []
        if has_index:
            try:
                with open(idx_path, 'r', encoding='utf-8') as idx_file:
                    idx_data = json.load(idx_file)
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
        print(f"[滚动窗口] 返回内容长度: {len(result_text)} 字符，使用编码 {detected_encoding}，索引 {'命中' if has_index else '未命中'}")
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
        # save_to_temp 为 True 时改为流式写入临时文件，避免一次性加载大输出
        if save_to_temp:
            ensure_temp_dir()
            if session_id is None:
                session_id = hashlib.md5((full_command + str(time.time())).encode()).hexdigest()
            temp_file_path = get_temp_file_path(session_id)
            
            line_count = 0
            sample_bytes = b""
            last_chunk_ended_newline = True
            proc = None
            stderr_bytes = b""
            
            try:
                proc = subprocess.Popen(
                    full_command,
                    shell=True,
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
            full_command,
            shell=True,
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
     Output("tab-2-content", "style"),
     Output("tab-3-content", "style"),
     Output("tab-4-content", "style")],
    [Input("main-tabs", "active_tab")]
)
def toggle_tab_visibility(active_tab):
    """切换标签页的显示/隐藏，而不是重新渲染内容，以保留状态"""
    if active_tab == "tab-1":
        return {"display": "block"}, {"display": "none"}, {"display": "none"}, {"display": "none"}
    elif active_tab == "tab-2":
        return {"display": "none"}, {"display": "block"}, {"display": "none"}, {"display": "none"}
    elif active_tab == "tab-3":
        return {"display": "none"}, {"display": "none"}, {"display": "block"}, {"display": "none"}
    elif active_tab == "tab-4":
        return {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "block"}
    
    # 默认显示tab-1
    return {"display": "block"}, {"display": "none"}, {"display": "none"}, {"display": "none"}

# 日志管理tab的回调函数

# 文件上传处理
@app.callback(
    [Output('upload-status', 'children'),
     Output('uploaded-files-list', 'children')],
    [Input('upload-log-file', 'contents')],
    [State('upload-log-file', 'filename'),
     State('upload-log-file', 'last_modified')],
    prevent_initial_call=True
)
def handle_file_upload(contents, filename, last_modified):
    if contents is None:
        return dash.no_update, dash.no_update
    
    try:
        # 确保logs目录存在
        ensure_log_dir()
        
        # 解析文件内容
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        
        # 保存文件到logs目录
        # 确保文件名是字符串类型，并正确处理空格
        if not isinstance(filename, str):
            filename = str(filename)
        file_path = os.path.join(LOG_DIR, filename)
        with open(file_path, 'wb') as f:
            f.write(decoded)
        
        # 更新文件列表
        log_files = get_log_files()
        file_list_table = _create_file_list_table(log_files)
        
        # 返回成功状态
        status = dbc.Alert(f"文件 '{filename}' 已成功上传到logs目录！", color="success", dismissable=True)
        return status, file_list_table
        
    except Exception as e:
        error_status = dbc.Alert(f"文件上传失败: {str(e)}", color="danger", dismissable=True)
        return error_status, dash.no_update

# 删除文件操作
@app.callback(
    Output('uploaded-files-list', 'children', allow_duplicate=True),
    [Input({'type': 'delete-file-btn', 'index': ALL}, 'n_clicks')],
    prevent_initial_call=True
)
def delete_log_file(n_clicks):
    # Determine which button was clicked
    ctx = callback_context
    if not ctx.triggered:
        return dash.no_update

    # If all n_clicks are None or 0, return
    if all(x is None for x in n_clicks):
        return dash.no_update
        
    # Get the button ID
    # Use rsplit to split from the right, ensuring we only split off the property name (n_clicks)
    # This handles cases where the filename in the ID contains dots
    button_id_str = ctx.triggered[0]['prop_id'].rsplit('.', 1)[0]
    
    try:
        button_id_dict = json.loads(button_id_str)
        filename = button_id_dict['index']
        
        # 确保文件名是字符串类型，并正确处理空格
        if not isinstance(filename, str):
            filename = str(filename)
            
        file_path = os.path.join(LOG_DIR, filename)
        
        if os.path.exists(file_path):
            os.remove(file_path)
            
        # 更新文件列表
        log_files = get_log_files()
        return _create_file_list_table(log_files)
            
    except Exception as e:
        # 如果出错，暂不处理，或者返回原列表
        print(f"Delete error: {e}")
        return dash.no_update

# 页面加载时初始化文件列表
@app.callback(
    [Output('uploaded-files-list', 'children', allow_duplicate=True),
     Output('external-program-path-input', 'value')],
    [Input('main-tabs', 'active_tab')],
    prevent_initial_call='initial_duplicate'
)
def initialize_file_list(active_tab):
    if active_tab == "tab-3":
        log_files = get_log_files()
        ext_config = load_external_program_config()
        return _create_file_list_table(log_files), ext_config.get("path", "")
    
    return dash.no_update, dash.no_update

# 重命名文件回调：打开模态框和取消
@app.callback(
    [Output("rename-file-modal", "is_open", allow_duplicate=True),
     Output("rename-target-file", "data"),
     Output("rename-file-input", "value")],
    [Input({"type": "rename-file-btn", "index": ALL}, "n_clicks"),
     Input("rename-file-cancel-btn", "n_clicks")],
    [State("rename-file-modal", "is_open")],
    prevent_initial_call=True
)
def toggle_rename_modal(rename_clicks, cancel_click, is_open):
    ctx = callback_context
    if not ctx.triggered:
        return is_open, dash.no_update, dash.no_update
        
    # Check if the trigger value is valid (not None)
    # This prevents the modal from opening when components are re-rendered (value is None)
    trigger_value = ctx.triggered[0].get("value")
    if trigger_value is None:
        return is_open, dash.no_update, dash.no_update
        
    # Use rsplit to split from the right, ensuring we only split off the property name (n_clicks)
    # This handles cases where the filename in the ID contains dots
    trigger_id = ctx.triggered[0]["prop_id"].rsplit(".", 1)[0]
    
    # 检查是否是重命名按钮点击
    if "rename-file-btn" in trigger_id:
        try:
            button_id_dict = json.loads(trigger_id)
            filename = button_id_dict['index']
            return True, filename, filename
        except Exception as e:
            return is_open, dash.no_update, dash.no_update
            
    # 取消按钮点击，关闭模态框
    if "rename-file-cancel-btn" in trigger_id:
        return False, dash.no_update, dash.no_update
        
    return is_open, dash.no_update, dash.no_update

# 执行重命名操作
@app.callback(
    [Output('uploaded-files-list', 'children', allow_duplicate=True),
     Output('toast-container', 'children', allow_duplicate=True),
     Output("rename-file-modal", "is_open", allow_duplicate=True)],
    [Input("rename-file-confirm-btn", "n_clicks")],
    [State("rename-target-file", "data"),
     State("rename-file-input", "value")],
    prevent_initial_call=True
)
def execute_rename(n_clicks, target_filename, new_filename):
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update
        
    if not target_filename or not new_filename:
        return dash.no_update, html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('文件名不能为空', 'warning');
            }}
        """), True
        
    # 如果文件名没有变化
    if target_filename == new_filename:
        return dash.no_update, dash.no_update, False
        
    try:
        old_path = os.path.join(LOG_DIR, target_filename)
        new_path = os.path.join(LOG_DIR, new_filename)
        
        # 检查原文件是否存在
        if not os.path.exists(old_path):
             return dash.no_update, html.Script(f"""
                if (typeof window.showToast === 'function') {{
                    window.showToast('原文件不存在', 'error');
                }}
            """), False # 关闭模态框，因为原文件都没了
            
        # 检查新文件名是否已存在
        if os.path.exists(new_path):
            return dash.no_update, html.Script(f"""
                if (typeof window.showToast === 'function') {{
                    window.showToast('文件名 {new_filename} 已存在', 'error');
                }}
            """), True # 保持打开，让用户修改
            
        # 重命名文件
        os.rename(old_path, new_path)
        
        # 更新文件列表
        log_files = get_log_files()
        return _create_file_list_table(log_files), html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('文件已重命名为 {new_filename}', 'success');
            }}
        """), False # 成功，关闭模态框
        
    except Exception as e:
        return dash.no_update, html.Script(f"""
            if (typeof window.showToast === 'function') {{
                window.showToast('重命名失败: {str(e)}', 'error');
            }}
        """), True

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


# API端点：获取日志窗口
@app.server.route('/api/get-log-window', methods=['POST'])
def get_log_window():
    """获取临时文件的指定行范围"""
    try:
        from flask import request, jsonify
        import json as std_json
        
        print(f"[API端点] 收到获取日志窗口请求")
        data = request.get_json()
        print(f"[API端点] 请求数据: {data}")
        
        session_id = data.get('session_id')
        start_line = int(data.get('start_line', 1))
        end_line = int(data.get('end_line', 500))
        
        print(f"[API端点] 解析参数 - session_id: {session_id}, start_line: {start_line}, end_line: {end_line}")
        
        if not session_id:
            print(f"[API端点] 错误: 缺少session_id")
            return jsonify({'success': False, 'error': '缺少session_id'})
        
        # 获取临时文件路径
        temp_file_path = get_temp_file_path(session_id)
        print(f"[API端点] 临时文件路径: {temp_file_path}")
        
        if not os.path.exists(temp_file_path):
            print(f"[API端点] 错误: 临时文件不存在: {temp_file_path}")
            return jsonify({'success': False, 'error': f'临时文件不存在: {temp_file_path}'})
        
        # 获取文件总行数
        total_lines = get_file_line_count(temp_file_path)
        print(f"[API端点] 文件总行数: {total_lines}")
        
        # 获取指定行范围
        print(f"[API端点] 开始读取行范围: {start_line} - {end_line}")
        content, encoding = get_file_lines_range(temp_file_path, start_line, end_line)
        print(f"[API端点] 读取完成，内容长度: {len(content)}, 编码: {encoding}")

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
        print(f"[API端点] 返回成功响应，内容长度: {len(content)}")
        
        # 使用标准json模块序列化，然后返回
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

        total_lines = get_file_line_count(temp_file_path)
        if start_line < 1:
            start_line = 1
        if start_line > total_lines:
            # 起始位置超过末尾，直接返回未找到
            return jsonify({'success': True, 'match_line': None, 'total_lines': total_lines})

        # 行扫描查找
        match_line = None
        try:
            # 尝试以utf-8读取，失败则回退latin-1
            try_encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'iso-8859-1']
            opened = False
            for enc in try_encodings:
                try:
                    f = open(temp_file_path, 'r', encoding=enc, errors='replace')
                    opened = True
                    break
                except Exception:
                    continue
            if not opened:
                f = open(temp_file_path, 'r', encoding='latin-1', errors='replace')

            with f:
                for idx, line in enumerate(f, start=1):
                    if idx < start_line:
                        continue
                    if case_sensitive:
                        if keyword in line:
                            match_line = idx
                            break
                    else:
                        if keyword.lower() in line.lower():
                            match_line = idx
                            break
        except Exception as e:
            return jsonify({'success': False, 'error': f'搜索失败: {str(e)}'})

        return jsonify({
            'success': True,
            'match_line': match_line,
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

        total_lines = get_file_line_count(temp_file_path)
        if from_line <= 1:
            # 顶部以上没有内容
            return jsonify({'success': True, 'match_line': None, 'total_lines': total_lines})

        match_line = None
        try:
            try_encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'iso-8859-1']
            opened = False
            for enc in try_encodings:
                try:
                    f = open(temp_file_path, 'r', encoding=enc, errors='replace')
                    opened = True
                    break
                except Exception:
                    continue
            if not opened:
                f = open(temp_file_path, 'r', encoding='latin-1', errors='replace')

            with f:
                # 顺序遍历并记录最后一个不超过 from_line-1 的匹配
                for idx, line in enumerate(f, start=1):
                    if idx >= from_line:
                        break
                    if case_sensitive:
                        if keyword in line:
                            match_line = idx
                    else:
                        if keyword.lower() in line.lower():
                            match_line = idx
        except Exception as e:
            return jsonify({'success': False, 'error': f'搜索失败: {str(e)}'})

        return jsonify({'success': True, 'match_line': match_line, 'total_lines': total_lines})
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
     Input("config-file-selector", "options")],
    prevent_initial_call=True
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

# 同步前端滚动窗口Ready状态到Dash状态
@app.callback(
    [Output("execute-filter-btn", "disabled", allow_duplicate=True),
     Output("execute-filter-btn", "color", allow_duplicate=True),
     Output("log-view-status-bar", "children", allow_duplicate=True),
     Output("log-view-status-bar", "className", allow_duplicate=True)],
    [Input("log-view-ready-signal-btn", "n_clicks")],
    prevent_initial_call=True
)
def sync_log_view_ready_state(n_clicks):
    if n_clicks:
        return False, "success", "Ready", "badge bg-success ms-2"
    return dash.no_update, dash.no_update, dash.no_update, dash.no_update

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
    
    if not path:
        return dbc.Alert("请输入有效的程序路径", color="warning", dismissable=True)
        
    if save_external_program_config(path):
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
         return html.Script("if(window.showToast) window.showToast('请先选择一个日志文件', 'warning');")
    
    config = load_external_program_config()
    program_path = config.get("path")
    
    if not program_path:
         return html.Script("if(window.showToast) window.showToast('未配置外部程序路径，请在日志管理中配置', 'warning');")
         
    log_path = get_log_path(selected_log_file)
    if not os.path.exists(log_path):
         return html.Script(f"if(window.showToast) window.showToast('日志文件不存在: {selected_log_file}', 'error');")
         
    try:
        # 使用 shlex to properly split command string (handle quotes/spaces)
        import shlex
        args = shlex.split(program_path)
        cmd = args + [log_path]
        
        print(f"Executing external program: {cmd}")
        subprocess.Popen(cmd)
            
        return html.Script(f"if(window.showToast) window.showToast('已请求使用外部程序打开: {selected_log_file}', 'success');")
    except FileNotFoundError:
         return html.Script(f"if(window.showToast) window.showToast('找不到外部程序: {args[0]}', 'error');")
    except Exception as e:
         print(f"External program error: {e}")
         return html.Script(f"if(window.showToast) window.showToast('打开失败: {str(e)}', 'error');")

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
