# -*- coding: utf-8 -*-
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import json
import os
import subprocess
import re
import base64
import hashlib
import time
from datetime import datetime

# 高亮缓存系统
class HighlightCache:
    def __init__(self, max_size=100):
        self.cache = {}
        self.max_size = max_size
        self.access_order = []
    
    def get_cache_key(self, text, selected_strings, data):
        """生成缓存键"""
        # 使用文本内容、选中的字符串和配置数据的哈希作为键
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        strings_hash = hashlib.md5(str(selected_strings).encode('utf-8')).hexdigest()
        data_hash = hashlib.md5(json.dumps(data, sort_keys=True).encode('utf-8')).hexdigest()
        return f"{text_hash}:{strings_hash}:{data_hash}"
    
    def get(self, key):
        """从缓存中获取结果"""
        if key in self.cache:
            # 更新访问顺序
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
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

# 全局高亮缓存实例
highlight_cache = HighlightCache(max_size=50)  # 最多缓存50个结果

# 初始化 Dash 应用，使用 Bootstrap 主题
app = dash.Dash(
    __name__, 
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True
)

# 数据存储文件路径
DATA_FILE = 'string_data.json'

# 获取所有配置文件
CONFIG_DIR = 'configs'

# 日志文件目录
LOG_DIR = 'logs'

def ensure_config_dir():
    """确保配置目录存在"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

def ensure_log_dir():
    """确保日志目录存在"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

def get_config_files():
    """获取configs目录下的所有配置文件（不包含.json后缀）"""
    ensure_config_dir()
    config_files = []
    if os.path.exists(CONFIG_DIR):
        for file in os.listdir(CONFIG_DIR):
            if file.endswith('.json'):
                config_files.append(file[:-5])  # 去掉.json后缀
    return sorted(config_files)

def get_log_files():
    """获取logs目录中的所有文本文件列表"""
    ensure_log_dir()
    log_files = []
    if os.path.exists(LOG_DIR):
        for file in os.listdir(LOG_DIR):
            if file.endswith(('.txt', '.log', '.text')):
                log_files.append(file)
    return log_files

def get_config_path(config_name):
    """获取配置文件的完整路径"""
    ensure_config_dir()
    return os.path.join(CONFIG_DIR, f"{config_name}.json")

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

def get_log_path(log_filename):
    """获取日志文件的完整路径"""
    ensure_log_dir()
    return os.path.join(LOG_DIR, log_filename)

# 加载已保存的数据
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"categories": {}}

# 保存数据
def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

# 初始数据
data = load_data()

# 确保配置目录存在
ensure_config_dir()

# 应用布局
app.layout = html.Div([
    # Toast通知容器
    html.Div(id="toast-container", className="toast-container"),
    
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
                    dbc.Tab(label="日志管理", tab_id="tab-3")
                ], id="main-tabs", active_tab="tab-1")
            ], width=12)
        ], className="mb-4"),
        
        # Tab1内容 - 日志过滤
        html.Div(id="tab-1-content", children=[
            # 右上角固定按钮区域
            html.Div([
                dbc.ButtonGroup([
                    dbc.Button(
                        "📁 日志文件", 
                        id="log-file-drawer-toggle", 
                        color="primary", 
                        size="sm",
                        className="me-2"
                    ),
                    dbc.Button(
                        "🔍 临时关键字", 
                        id="temp-keyword-drawer-toggle", 
                        color="secondary", 
                        size="sm"
                    )
                ], className="position-fixed", style={"top": "20px", "right": "20px", "zIndex": 1000}),
                # 当前选择的日志文件名显示区域（悬空显示在按钮下方）
                html.Div([
                    html.Div(
                        id="current-log-file-display",
                        className="border rounded p-2 bg-light text-center",
                        style={
                            "position": "fixed",
                            "top": "70px",
                            "right": "20px",
                            "zIndex": 999,
                            "minWidth": "200px",
                            "maxWidth": "300px",
                            "fontSize": "12px",
                            "boxShadow": "0 2px 10px rgba(0,0,0,0.1)",
                            "borderRadius": "8px",
                            "backgroundColor": "rgba(248, 249, 250, 0.95)",
                            "backdropFilter": "blur(5px)"
                        }
                    )
                ])
            ]),
            
            # 日志文件选择器 Drawer
            dbc.Offcanvas([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("日志文件选择", className="card-title"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("选择日志文件:"),
                                dcc.Dropdown(
                                    id="log-file-selector",
                                    placeholder="从logs目录选择文件...",
                                    options=[],
                                    clearable=False
                                )
                            ], width=12)
                        ])
                    ])
                ])
            ], id="log-file-drawer", title="日志文件选择", placement="end", is_open=False, style={"width": "50%"}),
            
            # 临时关键字 Drawer
            dbc.Offcanvas([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("临时关键字", className="card-title"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("添加临时关键字:"),
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Input(
                                            id="temp-keyword-text",
                                            type="text",
                                            placeholder="输入临时关键字..."
                                        )
                                    ], width=6),
                                    dbc.Col([
                                        dbc.Button("添加", id="temp-keyword-add-btn", color="primary", style={"width": "auto", "minWidth": "60px"})
                                    ], width=6)
                                ], className="mb-2"),
                                # 将已输入的关键字移动到输入框下方
                                dbc.Label("已输入的关键字:", className="mt-3"),
                                html.Div(id="temp-keywords-display", className="border rounded p-2", style={"minHeight": "50px", "backgroundColor": "#f8f9fa"})
                            ], width=12)
                        ])
                    ])
                ])
            ], id="temp-keyword-drawer", title="临时关键字", placement="end", is_open=False, style={"width": "50%"}),

            # 日志过滤结果
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            # 左侧：配置文件选择器和相关按钮
                            dbc.Row([
                                dbc.Col([
                                    html.Div(id="config-files-container", className="border rounded p-2", style={"maxHeight": "150px", "overflowY": "auto", "fontSize": "11px"}),
                                    # 将清除选择和过滤按钮放在一起
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Button("清除选择", id="clear-config-selection-btn", color="danger", size="sm", className="w-100")
                                        ], width=6),
                                        dbc.Col([
                                            html.Div([
                                                dbc.Button([
                                                    html.Span("过滤", id="filter-btn-text"),
                                                    dbc.Spinner(size="sm", color="light", id="filter-loading-spinner", spinner_style={"display": "none", "marginLeft": "5px"})
                                                ], id="execute-filter-btn", color="success", className="w-100", size="sm"),
                                                dcc.Loading(
                                                    id="filter-loading",
                                                    type="circle",
                                                    children=html.Div(id="filter-loading-output"),
                                                    style={"display": "none"}
                                                )
                                            ])
                                        ], width=6)
                                    ], className="mt-2 mb-3"),
                                    # 显示模式切换开关
                                    dbc.RadioItems(
                                        id="display-mode",
                                        options=[
                                            {"label": "过滤结果", "value": "filtered"},
                                            {"label": "源文件", "value": "source"},
                                            {"label": "高亮显示", "value": "highlight"}
                                        ],
                                        value="filtered",
                                        inline=True
                                    )
                                ], width=12)
                            ], className="mb-3"),
                            html.Div(id="log-filter-results", style={"maxHeight": "calc(100vh - 300px)", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px", "fontFamily": "monospace", "fontSize": "12px"})
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
                                        html.Div(id="saved-strings-container", style={"maxHeight": "375px", "overflowY": "auto", "marginTop": "10px"})
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
        ], style={"display": "none"}),
        
        # Tab3内容 - 日志管理
        html.Div(id="tab-3-content", children=[
            dbc.Row([
                dbc.Col([
                    html.H4("日志管理", className="mb-4"),
                    
                    # 文件上传区域
                    dbc.Card([
                        dbc.CardHeader([
                            html.H5("日志文件上传", className="mb-0")
                        ]),
                        dbc.CardBody([
                            html.P("上传日志文件到logs目录，支持.txt和.log格式的文件。", className="text-muted mb-3"),
                            
                            # 文件上传组件
                            dcc.Upload(
                                id='upload-log-file',
                                children=html.Div([
                                    html.I(className="bi bi-cloud-upload me-2"),
                                    '拖拽文件到此处或点击选择文件'
                                ]),
                                style={
                                    'width': '100%',
                                    'height': '100px',
                                    'lineHeight': '100px',
                                    'borderWidth': '2px',
                                    'borderStyle': 'dashed',
                                    'borderRadius': '5px',
                                    'textAlign': 'center',
                                    'cursor': 'pointer',
                                    'borderColor': '#6c757d',
                                    'color': '#6c757d'
                                },
                                multiple=False,
                                accept='.txt,.log'
                            ),
                            
                            # 上传状态显示
                            html.Div(id='upload-status', className="mt-3"),
                            
                            # 已上传文件列表
                            html.Hr(),
                            html.H6("已上传的文件", className="mt-3"),
                            html.Div(id='uploaded-files-list', className="mt-2")
                        ])
                    ], className="mb-4"),
                    
                    # 文件管理区域
                    dbc.Card([
                        dbc.CardHeader([
                            html.H5("日志文件管理", className="mb-0")
                        ]),
                        dbc.CardBody([
                            html.P("管理已上传的日志文件。", className="text-muted mb-3"),
                            
                            # 文件列表和操作
                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("选择日志文件:"),
                                    dcc.Dropdown(
                                        id="log-file-manager-selector",
                                        placeholder="选择要管理的文件...",
                                        clearable=True
                                    )
                                ], width=8),
                                dbc.Col([
                                    dbc.Label("操作:", className="d-block"),
                                    dbc.Button("删除文件", id="delete-log-file-btn", color="danger", className="w-100")
                                ], width=4)
                            ], className="mb-3"),
                            
                            # 文件信息显示
                            html.Div(id='file-info-display', className="mt-3")
                        ])
                    ])
                ], width=12)
            ], className="mb-4")
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
        dcc.Store(id='temp-keywords-store', data=[]),  # 存储临时关键字列表
        
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

# 控制日志文件选择器drawer的打开/关闭
@app.callback(
    Output("log-file-drawer", "is_open"),
    [Input("log-file-drawer-toggle", "n_clicks")],
    [State("log-file-drawer", "is_open")],
    prevent_initial_call=True
)
def toggle_log_file_drawer(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open

# 控制临时关键字drawer的打开/关闭
@app.callback(
    Output("temp-keyword-drawer", "is_open"),
    [Input("temp-keyword-drawer-toggle", "n_clicks")],
    [State("temp-keyword-drawer", "is_open")],
    prevent_initial_call=True
)
def toggle_temp_keyword_drawer(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open

# 页面加载时自动恢复之前的选择
@app.callback(
    Output("log-file-selector", "value"),
    [Input("data-store", "data"),
     Input("main-tabs", "active_tab")],  # 添加tab切换作为触发
    [State("log-file-selector", "options")],
    prevent_initial_call='initial_duplicate'  # 允许初始调用
)
def restore_previous_selections(data_store_data, active_tab, log_file_options):
    # 只有在tab-1（日志过滤tab）激活时才处理回调
    if active_tab != "tab-1":
        return dash.no_update
    
    ctx = dash.callback_context
    
    # 检查是否是页面加载时的初始调用或tab切换
    is_valid_trigger = False
    if ctx.triggered:
        trigger_id = ctx.triggered[0]["prop_id"]
        # 如果是data-store的数据更新或tab切换，则认为是有效的触发
        if trigger_id == "data-store.data" and data_store_data is not None:
            is_valid_trigger = True
        elif trigger_id == "main-tabs.active_tab" and active_tab:
            is_valid_trigger = True
    
    # 只在有效触发时执行恢复
    if is_valid_trigger:
        # 从文件加载用户选择状态
        user_selections = load_user_selections()
        selected_log_file = user_selections.get("selected_log_file", "")
        
        # 恢复日志文件选择
        if selected_log_file and log_file_options:
            # 检查之前选择的文件是否仍然存在
            for option in log_file_options:
                if option["value"] == selected_log_file:
                    return selected_log_file
        
        # 如果没有找到匹配的日志文件，返回空字符串
        return ""
    
    # 如果不是有效触发，保持当前状态不变
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
    ctx = dash.callback_context
    
    # 检查是否是页面加载时的初始调用
    is_initial_load = False
    if ctx.triggered:
        trigger_id = ctx.triggered[0]["prop_id"]
        if trigger_id == "data-store.data" and data_store_data is not None:
            is_initial_load = True
    
    # 页面加载时或任何tab激活时都尝试恢复字符串选择
    if is_initial_load or active_tab:
        # 从文件加载用户选择状态
        user_selections = load_user_selections()
        
        # 检查是否有保存的字符串数据
        selected_strings = user_selections.get("selected_strings", [])
        
        # 检查是否有保存的配置文件数据
        selected_config_files = user_selections.get("selected_config_files", [])
        
        # 如果有保存的字符串数据，直接返回
        if selected_strings:
            # 检查对应的日志文件是否存在
            saved_log_file = user_selections.get("selected_log_file", "")
            if saved_log_file:
                log_path = get_log_path(saved_log_file)
                if os.path.exists(log_path):
                    return selected_strings
            else:
                # 如果没有保存的日志文件，但保存了字符串，也返回字符串
                return selected_strings
        
        # 如果有保存的配置文件数据，尝试加载配置文件
        if selected_config_files:
            loaded_strings = []
            for config_file in selected_config_files:
                config_path = get_config_path(config_file)
                if os.path.exists(config_path):
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            saved_selections = json.load(f)
                        
                        # 从保存的选择中提取所有字符串
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
                    except Exception as e:
                        print(f"加载配置文件 {config_file} 时出错: {e}")
            
            if loaded_strings:
                # 保存到用户选择状态
                save_user_selections(selected_log_file, loaded_strings)
                return loaded_strings
        
        # 如果没有保存的字符串数据或配置文件，尝试从默认配置文件加载
        if has_default_config():
            default_strings = load_default_config()
            if default_strings:
                # 保存到用户选择状态
                save_user_selections(selected_log_file, default_strings)
                return default_strings
    
    # 如果都没有，返回空列表
    return []

# 页面加载时恢复配置文件选择
@app.callback(
    Output("selected-config-files", "data", allow_duplicate=True),
    [Input("data-store", "data"),
     Input("main-tabs", "active_tab")],
    prevent_initial_call='initial_duplicate'  # 使用特殊值允许初始调用和重复输出
)
def restore_config_selections(data_store_data, active_tab):
    ctx = dash.callback_context
    
    # 检查是否是页面加载时的初始调用或tab切换
    is_valid_trigger = False
    if ctx.triggered:
        trigger_id = ctx.triggered[0]["prop_id"]
        # 如果是data-store的数据更新或tab切换，则认为是有效的触发
        if trigger_id == "data-store.data" and data_store_data is not None:
            is_valid_trigger = True
        elif trigger_id == "main-tabs.active_tab" and active_tab:
            is_valid_trigger = True
    
    # 只在有效触发时执行恢复
    if is_valid_trigger:
        # 从文件加载用户选择状态
        user_selections = load_user_selections()
        
        # 检查是否有保存的配置文件数据
        selected_config_files = user_selections.get("selected_config_files", [])
        
        # 如果有保存的配置文件数据，检查配置文件是否仍然存在
        if selected_config_files:
            valid_config_files = []
            for config_file in selected_config_files:
                config_path = get_config_path(config_file)
                if os.path.exists(config_path):
                    valid_config_files.append(config_file)
            
            # 返回有效的配置文件列表
            return valid_config_files
        
        # 如果没有保存的配置文件数据，返回空列表
        return []
    
    # 如果不是有效触发，保持当前状态不变
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
     Output("category-filter", "options")],
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
        return dash.no_update, dash.no_update
    
    if not data or "categories" not in data:
        return [], [{"label": "所有分类", "value": "all"}]
    
    # 更新分类选项
    category_options = [{"label": "所有分类", "value": "all"}] + \
                      [{"label": cat, "value": cat} for cat in data["categories"].keys()]
    
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
    
    return string_elements, category_options

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

# 更新当前选择的日志文件名显示
@app.callback(
    Output("current-log-file-display", "children"),
    [Input("selected-log-file", "data"),
     Input("main-tabs", "active_tab")],
    prevent_initial_call=True
)
def update_current_log_file_display(selected_file, active_tab):
    # 只有在日志过滤tab激活时才显示
    if active_tab != "tab-1":
        return html.Div("当前未选择日志文件", className="text-muted")
    
    if selected_file and selected_file != "":
        return html.Div([
            html.Small("当前选择的日志文件:", className="d-block text-muted mb-1"),
            html.Strong(selected_file, className="text-primary")
        ])
    else:
        return html.Div("请选择日志文件", className="text-muted")

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
        button_id = ctx.triggered[0]["prop_id"].split(".")[0]
        
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
        button_id = ctx.triggered[0]["prop_id"].split(".")[0]
        
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

    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
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
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
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

# 生成并执行过滤命令的回调
@app.callback(
    [Output("log-filter-results", "children"),
     Output("filtered-result-store", "data"),
     Output("source-result-store", "data"),
     Output("filter-loading-spinner", "spinner_style", allow_duplicate=True),
     Output("filter-btn-text", "children", allow_duplicate=True),
     Output("execute-filter-btn", "disabled", allow_duplicate=True)],
    [Input("execute-filter-btn", "n_clicks"),
     Input("display-mode", "value")],
    [State("filter-tab-strings-store", "data"),
     State("temp-keywords-store", "data"),
     State("log-file-selector", "value"),
     State("main-tabs", "active_tab")],  # 添加当前激活的tab状态
    prevent_initial_call=True
)
def execute_filter_command(n_clicks, display_mode, filter_tab_strings, temp_keywords, selected_log_file, active_tab):
    # 只有在日志过滤tab激活时才处理回调
    if active_tab != "tab-1":
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    # 获取触发回调的组件ID
    ctx = dash.callback_context
    if not ctx.triggered:
        return "", "", "", {"display": "none", "marginLeft": "5px"}, "过滤", False
    
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    # 如果是显示模式切换，但还没有执行过滤操作
    if triggered_id == "display-mode" and n_clicks == 0:
        return html.P("请先执行过滤操作", className="text-info text-center"), "", "", {"display": "none", "marginLeft": "5px"}, "过滤", False
    
    # 执行过滤命令，包含临时关键字
    filtered_command, filtered_result = execute_filter_logic(filter_tab_strings, temp_keywords, selected_log_file)
    
    # 执行源文件命令，传递选中的字符串和临时关键字用于高亮
    source_command, source_result = execute_source_logic(selected_log_file, filter_tab_strings, temp_keywords)
    
    # 根据显示模式返回结果
    if display_mode == "source":
        return source_result, filtered_result, source_result, {"display": "none", "marginLeft": "5px"}, "过滤", False
    elif display_mode == "highlight":
        # 高亮模式：使用highlight配置执行过滤命令
        highlight_strings = load_highlight_config()
        if highlight_strings:
            highlight_command, highlight_result = execute_filter_logic(highlight_strings, [], selected_log_file)
            return highlight_result, filtered_result, source_result, {"display": "none", "marginLeft": "5px"}, "过滤", False
        else:
            # 如果没有highlight配置，显示提示信息
            return html.P("未找到highlight配置文件或配置为空", className="text-warning text-center"), filtered_result, source_result, {"display": "none", "marginLeft": "5px"}, "过滤", False
    else:
        return filtered_result, filtered_result, source_result, {"display": "none", "marginLeft": "5px"}, "过滤", False

def execute_filter_logic(selected_strings, temp_keywords, selected_log_file):
    """执行过滤逻辑，包含临时关键字"""
    # 合并选中的字符串和临时关键字
    all_strings = []
    if selected_strings:
        all_strings.extend(selected_strings)
    if temp_keywords:
        # 临时关键字默认为保留字符串
        for keyword in temp_keywords:
            all_strings.append(keyword)
    
    # 提取保留字符串和过滤字符串
    keep_strings = []
    filter_strings = []
    
    for item in all_strings:
        if isinstance(item, dict):
            if item["type"] == "keep":
                keep_strings.append(item["text"])
            else:
                filter_strings.append(item["text"])
        else:
            # 旧格式字符串和临时关键字，默认为保留字符串
            keep_strings.append(item)
    
    # 本地方式
    if not selected_log_file:
        return "", html.P("请选择日志文件", className="text-danger text-center")
    log_path = get_log_path(selected_log_file)
    
    # 构建grep命令
    grep_parts = []
    
    if keep_strings:
        # 保留字符串的grep模式
        keep_patterns = []
        for s in keep_strings:
            # 转义特殊字符
            escaped_s = re.escape(s)
            keep_patterns.append(escaped_s)
        
        if len(keep_patterns) == 1:
            grep_parts.append(f"grep -E '{keep_patterns[0]}' {log_path}")
        else:
            grep_parts.append(f"grep -E '({'|'.join(keep_patterns)})' {log_path}")
    
    if filter_strings:
        # 过滤字符串的grep模式
        filter_patterns = []
        for s in filter_strings:
            # 转义特殊字符
            escaped_s = re.escape(s)
            filter_patterns.append(escaped_s)
        
        if len(filter_patterns) == 1:
            filter_pattern = filter_patterns[0]
        else:
            filter_pattern = f"({'|'.join(filter_patterns)})"
        
        if grep_parts:
            grep_parts.append(f"grep -v -E '{filter_pattern}'")
        else:
            grep_parts.append(f"grep -v -E '{filter_pattern}' {log_path}")
    
    # 如果没有选择任何字符串，直接显示文件内容
    if not grep_parts:
        full_command = f"cat {log_path}"
    else:
        # 组合grep命令
        full_command = " | ".join(grep_parts)
    
    # 执行命令，传递选中的字符串和数据用于高亮
    data = load_data()  # 加载当前数据
    result_display = execute_command(full_command, all_strings, data)
    
    return full_command, result_display

def execute_source_logic(selected_log_file, selected_strings=None, temp_keywords=None):
    """执行源文件逻辑，包含临时关键字"""
    # 本地方式显示源文件
    if not selected_log_file:
        return "", html.P("请选择日志文件", className="text-danger text-center")
    log_path = get_log_path(selected_log_file)
    full_command = f"cat {log_path}"
    
    # 合并选中的字符串和临时关键字
    all_strings = []
    if selected_strings:
        all_strings.extend(selected_strings)
    if temp_keywords:
        # 临时关键字默认为保留字符串
        for keyword in temp_keywords:
            all_strings.append(keyword)
    
    # 执行命令，如果提供了选中的字符串，则进行高亮
    if all_strings:
        data = load_data()  # 加载当前数据
        result_display = execute_command(full_command, all_strings, data)
    else:
        result_display = execute_command(full_command)
    
    return full_command, result_display

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

def highlight_keywords(text, selected_strings, data):
    """在文本中高亮显示不同分类的关键字"""
    if not selected_strings or not data or "categories" not in data:
        return text
    
    # 获取所有分类
    categories = list(data["categories"].keys())
    if not categories:
        return text
    
    # 为每个分类分配颜色
    category_colors = get_category_colors(categories)
    
    # 构建关键字到分类的映射
    keyword_to_category = {}
    for category, strings in data["categories"].items():
        for string in strings:
            keyword_to_category[string] = category
    
    # 从选中的字符串中提取需要高亮的关键字
    keywords_to_highlight = []
    for item in selected_strings:
        if isinstance(item, dict):
            string_text = item["text"]
        else:
            string_text = item
        
        if string_text in keyword_to_category:
            keywords_to_highlight.append(string_text)
    
    if not keywords_to_highlight:
        return text
    
    # 按长度降序排序，确保长关键字优先匹配
    keywords_to_highlight.sort(key=len, reverse=True)
    
    # 对每个关键字进行高亮处理
    highlighted_text = text
    for keyword in keywords_to_highlight:
        if keyword in keyword_to_category:
            category = keyword_to_category[keyword]
            color = category_colors[category]
            
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

def highlight_keywords_dash(text, selected_strings, data):
    """为Dash组件生成高亮显示的组件列表（优化版本）"""
    start_time = time.time()
    
    if not selected_strings or not data or "categories" not in data:
        result = html.Pre(text, className="small")
        return result
    
    # 性能优化：使用缓存
    cache_key = highlight_cache.get_cache_key(text, selected_strings, data)
    cached_result = highlight_cache.get(cache_key)
    if cached_result:
        end_time = time.time()
        print(f"高亮处理（缓存命中）: {end_time - start_time:.3f}秒")
        return cached_result
    
    # 性能监控：记录文本大小
    text_size = len(text)
    
    # 性能优化：如果文本过大，使用简化模式
    if text_size > 100000:  # 超过100KB的文本
        result = html.Div([
            html.P(f"注意：文本过大（{text_size} 字节），已禁用高亮显示以提升性能", className="text-warning mb-2"),
            html.Pre(text, className="small")
        ])
        highlight_cache.put(cache_key, result)
        end_time = time.time()
        print(f"高亮处理（大文件简化）: {end_time - start_time:.3f}秒，文本大小: {text_size} 字节")
        return result
    
    # 获取所有分类
    categories = list(data["categories"].keys())
    if not categories:
        return html.Pre(text, className="small")
    
    # 为每个分类分配颜色
    category_colors = get_category_colors(categories)
    
    # 构建关键字到分类的映射
    keyword_to_category = {}
    for category, strings in data["categories"].items():
        for string in strings:
            keyword_to_category[string] = category
    
    # 从选中的字符串中提取需要高亮的关键字
    keywords_to_highlight = []
    for item in selected_strings:
        if isinstance(item, dict):
            string_text = item["text"]
        else:
            string_text = item
        
        if string_text in keyword_to_category:
            keywords_to_highlight.append(string_text)
    
    if not keywords_to_highlight:
        result = html.Pre(text, className="small")
        highlight_cache.put(cache_key, result)
        return result
    
    # 性能优化：限制高亮关键字数量
    if len(keywords_to_highlight) > 20:
        keywords_to_highlight = keywords_to_highlight[:20]  # 最多处理20个关键字
    
    # 按长度降序排序，确保长关键字优先匹配
    keywords_to_highlight.sort(key=len, reverse=True)
    
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
        
        for line in lines:
            if not line.strip():
                # 空行直接添加
                highlighted_lines.append(html.Div('\n', style={'whiteSpace': 'pre', 'fontFamily': 'monospace', 'fontSize': '12px'}))
                continue
            
            # 使用单一正则表达式查找所有匹配
            matches = list(regex.finditer(line))
            
            if not matches:
                # 该行没有关键字，直接添加
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
                category = None
                color = None
                
                # 查找匹配的关键字对应的分类
                for keyword in keywords_to_highlight:
                    if keyword.lower() == matched_text.lower():
                        if keyword in keyword_to_category:
                            category = keyword_to_category[keyword]
                            color = category_colors[category]
                            break
                
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
            components.append('\n')
            
            # 创建该行的Div组件
            highlighted_lines.append(html.Div(components, style={'whiteSpace': 'pre', 'fontFamily': 'monospace', 'fontSize': '12px'}))
        
        # 返回包含所有行的Div
        result = html.Div(highlighted_lines)
        highlight_cache.put(cache_key, result)
        
        # 性能监控：记录处理时间
        end_time = time.time()
        processing_time = end_time - start_time
        print(f"高亮处理完成: {processing_time:.3f}秒，文本大小: {text_size} 字节，关键字数量: {len(keywords_to_highlight)}")
        
        return result
    
    except Exception as e:
        # 如果正则表达式处理失败，回退到简单显示
        print(f"高亮处理失败，使用简单显示: {e}")
        result = html.Pre(text, className="small")
        highlight_cache.put(cache_key, result)
        
        # 性能监控：记录错误处理时间
        end_time = time.time()
        processing_time = end_time - start_time
        print(f"高亮处理失败: {processing_time:.3f}秒，文本大小: {text_size} 字节")
        
        return result

def execute_command(full_command, selected_strings=None, data=None):
    """执行命令并返回结果显示"""
    try:
        # 本地命令执行 - 使用二进制模式读取，然后尝试多种编码
        result = subprocess.run(
            full_command,
            shell=True,
            capture_output=True,
            text=False,  # 不使用text模式，获取原始字节
            timeout=30
        )
        
        # 处理结果
        if result.returncode == 0:
            # 本地结果需要解码
            output_bytes = result.stdout
            if not output_bytes:
                output = "没有找到符合条件的日志行"
            else:
                # 尝试多种编码
                encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'iso-8859-1']
                output = None
                
                for encoding in encodings:
                    try:
                        output = output_bytes.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                
                # 如果所有编码都失败，使用latin-1（不会失败）
                if output is None:
                    output = output_bytes.decode('latin-1', errors='replace')
            
            if not output.strip():
                output = "没有找到符合条件的日志行"
            
            # 计算行数
            line_count = len(output.split('\n'))
            
            # 如果提供了选中的字符串和数据，进行关键字高亮
            if selected_strings and data:
                # 使用新的Dash组件高亮函数
                highlighted_display = highlight_keywords_dash(output, selected_strings, data)
                
                # 如果超过3000行，添加提示信息
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
                # 如果超过3000行，添加提示信息
                if line_count > 3000:
                    result_display = html.Div([
                        html.P(f"注意：结果包含 {line_count} 行，已启用滚动条", className="text-info mb-2"),
                        html.Pre(output, className="small")
                    ])
                else:
                    result_display = html.Pre(output, className="small")
        else:
            error_output = result.stderr
            # 错误信息也需要解码
            if isinstance(error_output, bytes):
                encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
                for encoding in encodings:
                    try:
                        error_output = error_output.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    error_output = error_output.decode('latin-1', errors='replace')
            
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
     Output("tab-3-content", "style")],
    [Input("main-tabs", "active_tab")]
)
def toggle_tab_visibility(active_tab):
    """切换标签页的显示/隐藏，而不是重新渲染内容，以保留状态"""
    if active_tab == "tab-1":
        return {"display": "block"}, {"display": "none"}, {"display": "none"}
    elif active_tab == "tab-2":
        return {"display": "none"}, {"display": "block"}, {"display": "none"}
    elif active_tab == "tab-3":
        return {"display": "none"}, {"display": "none"}, {"display": "block"}
    
    # 默认显示tab-1
    return {"display": "block"}, {"display": "none"}, {"display": "none"}

# 日志管理tab的回调函数

# 文件上传处理
@app.callback(
    [Output('upload-status', 'children'),
     Output('uploaded-files-list', 'children'),
     Output('log-file-manager-selector', 'options', allow_duplicate=True)],
    [Input('upload-log-file', 'contents')],
    [State('upload-log-file', 'filename'),
     State('upload-log-file', 'last_modified')],
    prevent_initial_call=True
)
def handle_file_upload(contents, filename, last_modified):
    if contents is None:
        return dash.no_update, dash.no_update, dash.no_update
    
    try:
        # 确保logs目录存在
        ensure_log_dir()
        
        # 解析文件内容
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        
        # 保存文件到logs目录
        file_path = os.path.join(LOG_DIR, filename)
        with open(file_path, 'wb') as f:
            f.write(decoded)
        
        # 更新文件列表
        log_files = get_log_files()
        
        # 创建文件列表显示
        file_list = []
        for file in log_files:
            file_path = os.path.join(LOG_DIR, file)
            file_size = os.path.getsize(file_path)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
            
            file_list.append(html.Div([
                dbc.Row([
                    dbc.Col([html.Strong(file)], width=6),
                    dbc.Col([f"大小: {file_size} 字节"], width=3),
                    dbc.Col([f"修改时间: {file_mtime}"], width=3)
                ], className="border-bottom py-2")
            ]))
        
        if not file_list:
            file_list = [html.P("暂无上传的文件", className="text-muted")]
        
        # 更新文件管理器选择器选项
        options = [{'label': file, 'value': file} for file in log_files]
        
        # 返回成功状态
        status = dbc.Alert(f"文件 '{filename}' 已成功上传到logs目录！", color="success", dismissable=True)
        return status, file_list, options
        
    except Exception as e:
        error_status = dbc.Alert(f"文件上传失败: {str(e)}", color="danger", dismissable=True)
        return error_status, dash.no_update, dash.no_update

# 更新文件管理器选择器选项
@app.callback(
    Output('log-file-manager-selector', 'options', allow_duplicate=True),
    [Input('main-tabs', 'active_tab')],
    prevent_initial_call='initial_duplicate'
)
def update_file_manager_options(active_tab):
    if active_tab == "tab-3":
        log_files = get_log_files()
        options = [{'label': file, 'value': file} for file in log_files]
        return options
    return dash.no_update

# 显示文件信息
@app.callback(
    Output('file-info-display', 'children'),
    [Input('log-file-manager-selector', 'value')],
    prevent_initial_call=True
)
def show_file_info(selected_file):
    if selected_file is None:
        return html.P("请选择一个文件查看详细信息", className="text-muted")
    
    try:
        file_path = os.path.join(LOG_DIR, selected_file)
        
        if not os.path.exists(file_path):
            return dbc.Alert("文件不存在", color="warning")
        
        # 获取文件信息
        file_size = os.path.getsize(file_path)
        file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
        file_ctime = datetime.fromtimestamp(os.path.getctime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
        
        # 读取文件行数（只读取前几行预览）
        line_count = 0
        preview_lines = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for i, line in enumerate(f):
                    line_count += 1
                    if i < 5:  # 只显示前5行作为预览
                        preview_lines.append(line.strip())
        except:
            line_count = "无法读取"
        
        return dbc.Card([
            dbc.CardHeader([html.H6("文件详细信息", className="mb-0")]),
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([html.Strong("文件名:")], width=3),
                    dbc.Col([selected_file], width=9)
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([html.Strong("文件大小:")], width=3),
                    dbc.Col([f"{file_size} 字节"], width=9)
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([html.Strong("修改时间:")], width=3),
                    dbc.Col([file_mtime], width=9)
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([html.Strong("创建时间:")], width=3),
                    dbc.Col([file_ctime], width=9)
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([html.Strong("行数:")], width=3),
                    dbc.Col([str(line_count) if isinstance(line_count, int) else line_count], width=9)
                ], className="mb-3"),
                html.Hr(),
                html.H6("文件内容预览:", className="mb-2"),
                html.Div([
                    html.Pre(line, className="mb-1 text-muted small") for line in preview_lines
                ], style={"maxHeight": "150px", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "10px", "borderRadius": "5px"})
            ])
        ])
        
    except Exception as e:
        return dbc.Alert(f"获取文件信息失败: {str(e)}", color="danger")

# 删除文件操作
@app.callback(
    [Output('log-file-manager-selector', 'value', allow_duplicate=True),
     Output('uploaded-files-list', 'children', allow_duplicate=True),
     Output('file-info-display', 'children', allow_duplicate=True),
     Output('log-file-manager-selector', 'options', allow_duplicate=True)],
    [Input('delete-log-file-btn', 'n_clicks')],
    [State('log-file-manager-selector', 'value')],
    prevent_initial_call=True
)
def delete_log_file(n_clicks, selected_file):
    if n_clicks is None or selected_file is None:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    try:
        file_path = os.path.join(LOG_DIR, selected_file)
        
        if os.path.exists(file_path):
            os.remove(file_path)
            
            # 更新文件列表
            log_files = get_log_files()
            
            # 创建文件列表显示
            file_list = []
            for file in log_files:
                file_path = os.path.join(LOG_DIR, file)
                file_size = os.path.getsize(file_path)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
                
                file_list.append(html.Div([
                    dbc.Row([
                        dbc.Col([html.Strong(file)], width=6),
                        dbc.Col([f"大小: {file_size} 字节"], width=3),
                        dbc.Col([f"修改时间: {file_mtime}"], width=3)
                    ], className="border-bottom py-2")
                ]))
            
            if not file_list:
                file_list = [html.P("暂无上传的文件", className="text-muted")]
            
            # 更新文件管理器选择器选项
            options = [{'label': file, 'value': file} for file in log_files]
            
            # 清空选择器和文件信息显示
            return None, file_list, html.P("文件已从logs目录删除", className="text-success"), options
        else:
            return dash.no_update, dash.no_update, dbc.Alert("文件不存在", color="warning"), dash.no_update
            
    except Exception as e:
        return dash.no_update, dash.no_update, dbc.Alert(f"删除文件失败: {str(e)}", color="danger"), dash.no_update

# 页面加载时初始化文件列表
@app.callback(
    Output('uploaded-files-list', 'children', allow_duplicate=True),
    [Input('main-tabs', 'active_tab')],
    prevent_initial_call='initial_duplicate'
)
def initialize_file_list(active_tab):
    if active_tab == "tab-3":
        log_files = get_log_files()
        
        # 创建文件列表显示
        file_list = []
        for file in log_files:
            file_path = os.path.join(LOG_DIR, file)
            file_size = os.path.getsize(file_path)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
            
            file_list.append(html.Div([
                dbc.Row([
                    dbc.Col([html.Strong(file)], width=6),
                    dbc.Col([f"大小: {file_size} 字节"], width=3),
                    dbc.Col([f"修改时间: {file_mtime}"], width=3)
                ], className="border-bottom py-2")
            ]))
        
        if not file_list:
            file_list = [html.P("暂无上传的文件", className="text-muted")]
        
        return file_list
    
    return dash.no_update

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
     Input('selected-config-files', 'data')],
    prevent_initial_call='initial_duplicate'
)
def update_config_files_display(active_tab, selected_config_files):
    if active_tab == "tab-1":
        config_files = get_config_files()
        
        if not config_files:
            return html.P("暂无配置文件，请在配置管理页面创建配置文件", className="text-muted text-center")
        
        # 创建配置文件按钮列表
        config_buttons = []
        for config_file in config_files:
            # 检查当前配置文件是否被选中（支持多选）
            is_selected = config_file in selected_config_files
            
            config_buttons.append(
                dbc.Button(
                    config_file,
                    id={"type": "config-file-btn", "index": config_file},
                    color="primary" if is_selected else "outline-primary",
                    size="sm",
                    className="m-1",
                    style={"whiteSpace": "nowrap", "flexShrink": 0}
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
     Input('clear-config-selection-btn', 'n_clicks')],
    [State('selected-config-files', 'data'),
     State('main-tabs', 'active_tab')],
    prevent_initial_call=True
)
def handle_config_file_selection(config_btn_clicks, clear_click, current_selection, active_tab):
    # 只有在日志过滤tab激活时才处理回调
    if active_tab != "tab-1":
        return dash.no_update
        
    ctx = dash.callback_context
    
    # 如果点击了清除按钮
    if ctx.triggered and ctx.triggered[0]['prop_id'] == 'clear-config-selection-btn.n_clicks':
        # 保存空的选择状态，但保留当前的日志文件选择
        current_selections = load_user_selections()
        save_user_selections(current_selections.get("selected_log_file", ""), [], selected_config_files=[])
        return []
    
    # 如果点击了配置文件按钮
    if ctx.triggered and 'config-file-btn' in ctx.triggered[0]['prop_id']:
        # 获取被点击的按钮的index（即配置文件名）
        prop_id = ctx.triggered[0]['prop_id']
        config_file = prop_id.split('.')[0].split('"index":"')[1].split('"')[0]
        
        # 如果配置文件已经在选中列表中，则移除它（取消选择）
        if config_file in current_selection:
            current_selection.remove(config_file)
        else:
            # 否则添加到选中列表中
            current_selection.append(config_file)
        
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
        loaded_strings = []
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
            
            # 从保存的选择中提取所有字符串
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
            
            loaded_configs.append(selected_config_file)
        
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
    Output('temp-keywords-display', 'children', allow_duplicate=True),
    [Input('temp-keywords-store', 'data')],
    prevent_initial_call=True
)
def update_temp_keywords_display(keywords):
    """根据存储的数据更新临时关键字显示"""
    print(f"=== 存储变化触发显示更新 ===")
    print(f"存储中的关键字: {keywords}")
    print(f"关键字类型: {type(keywords)}")
    print(f"关键字ID: {id(keywords)}")
    result = create_temp_keyword_buttons(keywords or [])
    print(f"更新的显示内容: {type(result)}")
    return result

# 添加临时关键字
@app.callback(
    Output('temp-keywords-store', 'data'),
    [Input('temp-keyword-add-btn', 'n_clicks')],
    [State('temp-keyword-text', 'value'),
     State('temp-keywords-store', 'data')],
    prevent_initial_call=True
)
def add_temp_keyword(n_clicks, keyword_text, existing_keywords):
    print(f"=== 添加临时关键字回调被触发 ===")
    print(f"n_clicks: {n_clicks}")
    print(f"keyword_text: '{keyword_text}'")
    print(f"existing_keywords: {existing_keywords}")
    print(f"existing_keywords 类型: {type(existing_keywords)}")
    print(f"existing_keywords ID: {id(existing_keywords)}")
    
    # 获取回调上下文
    ctx = dash.callback_context
    print(f"回调上下文: {ctx.triggered}")
    
    # 只有在按钮被点击时才处理
    if not ctx.triggered:
        print("没有触发事件，返回无更新")
        return dash.no_update
    
    # 检查是否是按钮点击事件
    prop_id = ctx.triggered[0]['prop_id']
    print(f"触发ID: {prop_id}")
    
    if 'temp-keyword-add-btn' not in prop_id:
        print("不是添加按钮点击事件，返回无更新")
        return dash.no_update
        
    if n_clicks is None:
        print("按钮未被点击，返回无更新")
        return dash.no_update
        
    if keyword_text and keyword_text.strip():
        # 直接使用输入的关键字（去除前后空格）
        new_keyword = keyword_text.strip()
        print(f"添加新关键字: '{new_keyword}'")
        
        # 合并现有关键字和新关键字，去重
        all_keywords = existing_keywords or []
        if new_keyword not in all_keywords:
            all_keywords.append(new_keyword)
            print(f"关键字已添加到列表: {all_keywords}")
        else:
            print(f"关键字已存在，不重复添加")
        
        # 只返回存储数据，显示由存储监听回调更新
        return all_keywords
    else:
        print("输入内容为空，返回现有内容")
        # 如果没有输入内容，保持现有存储不变
        return existing_keywords or []

# 处理临时关键字按钮点击（删除关键字）
@app.callback(
    Output('temp-keywords-store', 'data', allow_duplicate=True),
    [Input({"type": "temp-keyword-btn", "index": dash.ALL}, 'n_clicks')],
    [State('temp-keywords-store', 'data')],
    prevent_initial_call=True
)
def handle_temp_keyword_click(keyword_clicks, current_keywords):
    ctx = dash.callback_context
    
    print(f"=== 删除关键字回调被触发 ===")
    print(f"keyword_clicks: {keyword_clicks}")
    print(f"current_keywords: {current_keywords}")
    print(f"current_keywords 类型: {type(current_keywords)}")
    print(f"current_keywords ID: {id(current_keywords)}")
    print(f"ctx.triggered: {ctx.triggered}")
    
    # 如果没有点击事件，返回无更新
    if not ctx.triggered:
        print("没有触发事件，返回无更新")
        return dash.no_update
    
    # 获取被点击的关键字
    prop_id = ctx.triggered[0]['prop_id']
    print(f"触发ID: {prop_id}")
    
    # 检查是否是关键字按钮点击事件
    if 'temp-keyword-btn' in prop_id:
        # 检查按钮是否真的被点击了（n_clicks不为None）
        trigger_value = ctx.triggered[0].get('value')
        print(f"触发值: {trigger_value}")
        
        if trigger_value is None:
            print("按钮未被点击，返回无更新")
            return dash.no_update
            
        # 提取被点击的关键字
        keyword = prop_id.split('.')[0].split('"index":"')[1].split('"')[0]
        print(f"要删除的关键字: '{keyword}'")
        
        # 从关键字列表中移除被点击的关键字
        updated_keywords = [kw for kw in current_keywords if kw != keyword]
        print(f"更新后的关键字列表: {updated_keywords}")
        
        # 只返回更新后的关键字列表，显示由存储监听回调更新
        return updated_keywords
    
    print("不是按钮点击事件，返回无更新")
    return dash.no_update

# 临时关键字变化时自动更新右侧显示结果（已禁用自动过滤，改为手动触发）
@app.callback(
    Output("log-filter-results", "children", allow_duplicate=True),
    [Input("temp-keywords-store", "data"),
     Input("filter-tab-strings-store", "data"),
     Input("log-file-selector", "value"),
     Input("display-mode", "value")],
    [State("main-tabs", "active_tab")],
    prevent_initial_call=True
)
def auto_update_results_on_temp_keywords(temp_keywords, filter_tab_strings, selected_log_file, display_mode, active_tab):
    # 只有在日志过滤tab激活时才处理回调
    if active_tab != "tab-1":
        return dash.no_update
    
    # 获取回调上下文，检查触发源
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    
    # 获取触发回调的组件ID
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    # 只有当临时关键字变化时才显示提示信息
    # 配置文件选择变化时不自动更新显示，保持当前过滤结果
    if triggered_id == "temp-keywords-store":
        # 检查是否有临时关键字或选中的字符串
        has_temp_keywords = temp_keywords and len(temp_keywords) > 0
        has_selected_strings = filter_tab_strings and len(filter_tab_strings) > 0
        
        # 如果没有临时关键字且没有选中的字符串，显示提示信息
        if not has_temp_keywords and not has_selected_strings:
            return html.P("请选择配置文件或输入临时关键字，然后点击'生成'按钮执行过滤", className="text-info text-center")
        
        # 如果没有选择日志文件，显示提示
        if not selected_log_file:
            return html.P("请选择日志文件", className="text-danger text-center")
        
        # 临时关键字变化时显示提示信息
        return html.P("临时关键字已更新，请点击'生成'按钮执行过滤", className="text-success text-center")
    
    # 对于其他触发源（如配置文件选择、日志文件选择、显示模式切换），保持当前显示不变
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
    print(f"=== create_temp_keyword_buttons 被调用 ===")
    print(f"输入的关键字列表: {keywords}")
    print(f"列表类型: {type(keywords)}")
    print(f"列表长度: {len(keywords) if keywords else 0}")
    
    if not keywords:
        print("关键字列表为空，返回提示信息")
        return html.P("未输入临时关键字", className="text-muted")
    
    keyword_buttons = []
    for keyword in keywords:
        keyword_buttons.append(
            dbc.Button(
                keyword,
                id={"type": "temp-keyword-btn", "index": keyword},
                color="outline-primary",
                size="sm",
                className="m-1",
                style={"whiteSpace": "nowrap", "flexShrink": 0}
            )
        )
    
    # 使用d-flex和flex-wrap实现多列布局
    return html.Div(
        keyword_buttons,
        className="d-flex flex-wrap gap-2",
        style={"minHeight": "50px"}
    )


if __name__ == "__main__":
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Log Filter Application')
    parser.add_argument('--port', type=int, default=8052, help='Port to run the application on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind the application to')
    args = parser.parse_args()
    
    app.run(debug=True, port=args.port, host=args.host)