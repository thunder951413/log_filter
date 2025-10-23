import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import json
import os
import subprocess
import re
import base64
from datetime import datetime

# 初始化 Dash 应用，使用 Bootstrap 主题
app = dash.Dash(
    __name__, 
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    external_scripts=[
        "/assets/fullscreen_log.js"
    ]
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
    """获取所有配置文件列表"""
    ensure_config_dir()
    config_files = []
    if os.path.exists(CONFIG_DIR):
        for file in os.listdir(CONFIG_DIR):
            if file.endswith('.json'):
                config_files.append(file[:-5])  # 去掉.json后缀
    return config_files

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
def save_user_selections(selected_log_file, selected_strings):
    selections = {
        "selected_log_file": selected_log_file,
        "selected_strings": selected_strings,
        "last_updated": datetime.now().isoformat()
    }
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
    dbc.Container([
        # 状态提示
        dbc.Row([
            dbc.Col([
                dbc.Alert(id="status-alert", is_open=False, dismissable=True, duration=4000)
            ], width=12)
        ]),
        
        # 存储组件
        dcc.Store(id='filtered-result-store', data=''),
        dcc.Store(id='source-result-store', data=''),
        
        # 日志过滤选项
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Button(
                            [html.I(className="bi bi-chevron-down me-2"), "日志过滤选项"],
                            id="filter-options-toggle",
                            className="btn btn-link text-decoration-none w-100 text-start"
                        )
                    ]),
                    dbc.Collapse(
                        dbc.CardBody([
                            dbc.Row([
                                # 左侧：当前控件
                                dbc.Col([
                                    # 文件选择
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Label("选择日志文件:"),
                                            dcc.Dropdown(
                                                id="log-file-selector",
                                                placeholder="从logs目录选择文件...",
                                                options=[],
                                                clearable=False
                                            )
                                        ], width=12, className="mb-3")
                                    ]),
                                    
                                    # 生成的命令
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.Label("生成的命令:", className="mt-3"),
                                            dbc.Textarea(
                                                id="generated-command",
                                                placeholder="这里将显示生成的grep命令...",
                                                style={"height": "100px", "fontFamily": "monospace"}
                                            ),
                                            dbc.Button("复制命令", id="copy-command-btn", color="secondary", size="sm", className="mt-2")
                                        ], width=12)
                                    ])
                                ], width=6),
                                
                                # 右侧：日志上传/删除功能
                                dbc.Col([
                                    # 标题
                                    dbc.Label("日志管理:", className="text-center mb-3"),
                                    
                                    # 切换按钮
                                    dbc.Row([
                                        dbc.Col([
                                            dbc.ButtonGroup([
                                                dbc.Button("上传", id="upload-mode-btn", color="primary", active=True),
                                                dbc.Button("删除", id="delete-mode-btn", color="secondary", active=False)
                                            ], className="w-100")
                                        ], width=12)
                                    ], className="mb-3"),
                                    
                                    # 上传模式内容
                                    html.Div(id="upload-mode-content", children=[
                                        # 文件上传组件
                                        dcc.Upload(
                                            id='upload-log-file',
                                            children=html.Div([
                                                html.I(className="bi bi-cloud-upload me-2"),
                                                '拖拽文件到这里或点击选择文件'
                                            ]),
                                            style={
                                                'width': '100%',
                                                'height': '100px',
                                                'lineHeight': '100px',
                                                'borderWidth': '2px',
                                                'borderStyle': 'dashed',
                                                'borderRadius': '5px',
                                                'textAlign': 'center',
                                                'margin': '10px 0',
                                                'cursor': 'pointer',
                                                'backgroundColor': '#f8f9fa'
                                            },
                                            multiple=False,
                                            accept='.txt,.log,.text'
                                        ),
                                        
                                        # 上传状态显示
                                        html.Div(id='upload-status', className="mt-2")
                                    ]),
                                    
                                    # 删除模式内容
                                    html.Div(id="delete-mode-content", style={"display": "none"}, children=[
                                        # 文件选择器
                                        dbc.Row([
                                            dbc.Col([
                                                dbc.Label("选择要删除的文件:"),
                                                dcc.Dropdown(
                                                    id="delete-file-selector",
                                                    placeholder="选择文件...",
                                                    options=[],
                                                    clearable=False
                                                )
                                            ], width=12, className="mb-3")
                                        ]),
                                        
                                        # 删除按钮
                                        dbc.Row([
                                            dbc.Col([
                                                dbc.Button(
                                                    "删除选中文件", 
                                                    id="delete-file-btn", 
                                                    color="danger", 
                                                    className="w-100"
                                                )
                                            ], width=12)
                                        ]),
                                        
                                        # 删除状态显示
                                        html.Div(id='delete-status', className="mt-2")
                                    ]),
                                    
                                ], width=6)
                            ])
                        ]),
                        id="filter-options-collapse",
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
                            # 配置文件选择器已移除
                            dbc.Row([
                                dbc.Col([
                                    dbc.Button("keyword", id="keyword-btn", color="primary", className="float-end"),
                                ], width=12)
                            ], className="mb-2"),
                            

                            
                            # 选中的字符串和已保存的字符串区域（并排布局）
                            html.Hr(),
                            dbc.Row([
                                # 左侧：选中的字符串
                                dbc.Col([
                                    html.H4("选中的字符串", className="card-title"),
                                    dbc.Button("清除选择", id="clear-selection-btn", color="danger", size="sm", className="mb-2"),
                                    html.Div(id="selected-strings-container", style={"maxHeight": "600px", "overflowY": "auto"})
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
                            ])
                        ]),
                        id="config-management-collapse",
                        is_open=True
                    )
                ])
            ], width=12)
        ], className="mb-4"),
        
        # 执行过滤命令按钮
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                dbc.Button("生成并执行过滤命令", id="execute-filter-btn", color="primary", className="w-100", size="lg")
                            ], width=12)
                        ])
                    ])
                ])
            ], width=12)
        ], className="mb-3"),
        
        # 日志过滤结果
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("日志过滤结果", className="card-title"),
                        # 显示模式切换开关
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("显示模式:"),
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
                            ], width=12, className="mb-3")
                        ]),
                        html.Div(id="log-filter-results", style={"maxHeight": "600px", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px", "fontFamily": "monospace", "fontSize": "12px"})
                    ])
                ])
            ], width=12)
        ], className="mb-4"),
        
        # 抽屉组件
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
        
        # 存储组件
        dcc.Store(id="data-store"),
        dcc.Store(id="selected-strings", data=[]),
        dcc.Store(id="selected-log-file", data=""),
    ], fluid=True)
])

# 初始化数据存储
@app.callback(
    Output("data-store", "data", allow_duplicate=True),
    [Input("status-alert", "children")],
    prevent_initial_call="initial_duplicate"
)
def initialize_data_store(status_children):
    return load_data()

# 页面加载时自动恢复之前的选择
@app.callback(
    Output("log-file-selector", "value"),
    [Input("data-store", "data")],
    [State("log-file-selector", "options")],
    prevent_initial_call=False
)
def restore_previous_selections(data_store_data, log_file_options):
    ctx = dash.callback_context
    
    # 检查是否是页面初始加载
    # 在页面加载时，triggered可能包含初始触发信息，我们需要检查是否是真正的用户交互
    is_initial_load = True
    if ctx.triggered:
        # 检查触发源，如果是data-store的初始加载，则认为是页面初始加载
        trigger_id = ctx.triggered[0]["prop_id"]
        if trigger_id != "data-store.data":
            is_initial_load = False
    
    # 只在页面初始加载时执行恢复
    if is_initial_load:
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
    
    # 如果不是初始加载，保持当前状态不变
    return dash.no_update

# 页面加载时恢复字符串选择
@app.callback(
    Output("selected-strings", "data", allow_duplicate=True),
    [Input("selected-log-file", "data")],
    prevent_initial_call='initial_duplicate'  # 使用特殊值允许初始调用和重复输出
)
def restore_string_selections(selected_log_file):
    # 只有当有选中的日志文件时才恢复字符串
    if selected_log_file:
        # 从文件加载用户选择状态
        user_selections = load_user_selections()
        
        # 检查是否有保存的字符串数据
        selected_strings = user_selections.get("selected_strings", [])
        if selected_strings:
            # 检查对应的日志文件是否存在
            saved_log_file = user_selections.get("selected_log_file", "")
            if saved_log_file == selected_log_file:
                log_path = get_log_path(saved_log_file)
                if os.path.exists(log_path):
                    return selected_strings
    
    # 如果没有保存的字符串数据或日志文件不匹配，尝试从默认配置文件加载
    if has_default_config():
        default_strings = load_default_config()
        if default_strings:
            # 保存到用户选择状态
            save_user_selections(selected_log_file, default_strings)
            return default_strings
    
    # 如果都没有，返回空列表
    return []

# 控制配置文件管理区域折叠/展开的回调
@app.callback(
    Output("config-management-collapse", "is_open"),
    [Input("config-management-toggle", "n_clicks")],
    [State("config-management-collapse", "is_open")]
)
def toggle_config_management(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open

# 控制抽屉显示隐藏的回调
@app.callback(
    Output("keyword-drawer", "is_open"),
    [Input("keyword-btn", "n_clicks")],
    [State("keyword-drawer", "is_open")]
)
def toggle_drawer(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open

# 更新抽屉分类建议列表
@app.callback(
    Output("category-suggestions", "children"),
    [Input("data-store", "data"),
     Input("keyword-drawer", "is_open")]
)
def update_drawer_category_options(data, is_open):
    if not data or "categories" not in data:
        return []
    
    # 返回所有分类作为建议选项
    return [html.Option(value=cat) for cat in data["categories"].keys()]

# 添加字符串回调
@app.callback(
    [Output("data-store", "data"),
     Output("input-string", "value"),
     Output("input-category", "value")],
    [Input("add-string-btn", "n_clicks")],
    [State("input-string", "value"),
     State("input-category", "value"),
     State("data-store", "data")]
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

# 更新已保存字符串显示
@app.callback(
    [Output("saved-strings-container", "children"),
     Output("category-filter", "options")],
    [Input("data-store", "data"),
     Input("category-filter", "value"),
     Input("string-type-radio", "value"),
     Input("selected-strings", "data")]  # 添加selected-strings作为输入
)
def update_saved_strings(data, selected_category, string_type, selected_strings):
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
    Output("log-file-selector", "options"),
    [Input("status-alert", "children")],
    prevent_initial_call=False
)
def update_log_file_selector(status_children):
    # 始终显示日志文件选择器
    log_files = get_log_files()
    options = [{"label": file, "value": file} for file in log_files]
    return options

# 保存日志文件选择状态
@app.callback(
    Output("selected-log-file", "data"),
    [Input("log-file-selector", "value")],
    [State("selected-strings", "data")],
    prevent_initial_call=True  # 防止页面加载时触发保存
)
def save_log_file_selection(selected_file, selected_strings):
    ctx = dash.callback_context
    
    # 检查是否是页面初始加载时的触发
    is_initial_trigger = False
    if ctx.triggered:
        trigger_id = ctx.triggered[0]["prop_id"]
        # 如果是页面初始加载时的触发，并且值是None或空字符串，则认为是初始触发
        if trigger_id == "log-file-selector.value" and (ctx.triggered[0]["value"] is None or ctx.triggered[0]["value"] == ""):
            is_initial_trigger = True
    
    # 只有在用户真正选择文件时才保存，而不是在恢复过程中
    if not is_initial_trigger and selected_file is not None and selected_file != "":
        # 保存到文件
        save_user_selections(selected_file, selected_strings)
    
    # 返回当前选择的文件，但如果是初始触发则返回dash.no_update
    if is_initial_trigger:
        return dash.no_update
    
    return selected_file if selected_file else ""

# 选择字符串回调
@app.callback(
    Output("selected-strings", "data"),
    [Input({"type": "select-string-btn", "index": dash.ALL}, "n_clicks"),
     Input("clear-selection-btn", "n_clicks")],
    [State("selected-strings", "data"),
     State("data-store", "data"),
     State("string-type-radio", "value"),
     State("selected-log-file", "data")],
    prevent_initial_call=True  # 防止页面加载时触发
)
def select_string(select_clicks, clear_clicks, selected_strings, data, string_type, selected_log_file):
    ctx = callback_context
    
    # 检查是否是用户交互触发的
    is_user_interaction = False
    if ctx.triggered:
        trigger_id = ctx.triggered[0]["prop_id"]
        # 如果是按钮点击或用户操作，才认为是用户交互
        if "n_clicks" in trigger_id and ctx.triggered[0]["value"]:
            is_user_interaction = True
    
    # 清除选择
    if clear_clicks and is_user_interaction:
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

# 状态提示回调 - 整合所有状态更新
@app.callback(
    [Output("status-alert", "children"),
     Output("status-alert", "is_open"),
     Output("status-alert", "color")],
    [Input("add-string-btn", "n_clicks"),
     Input({"type": "select-string-btn", "index": dash.ALL}, "n_clicks"),
     Input("clear-selection-btn", "n_clicks")],
    [State("input-string", "value"),
     State("input-category", "value"),
     State("data-store", "data"),
     State("selected-strings", "data")]
)
def show_status(add_clicks, select_clicks, clear_clicks, input_string, input_category, data, selected_strings):
    ctx = callback_context
    
    if not ctx.triggered:
        return "", False, "success"

    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    # 添加字符串状态
    if "add-string-btn" in trigger_id and add_clicks:
        if input_string and input_category:
            return f"成功添加字符串到分类 '{input_category}'", True, "success"
        else:
            return "请输入字符串和分类", True, "danger"
    
    # 清除选择状态
    if "clear-selection-btn" in trigger_id and clear_clicks:
        return "已清除所有选择", True, "info"
    
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
                return "该字符串已经被选择", True, "warning"
            else:
                return "已选择字符串", True, "success"
    
    return "", False, "success"

# 抽屉中更新分类选项的回调
@app.callback(
    Output("drawer-category-filter", "options"),
    [Input("data-store", "data")]
)
def update_drawer_category_options(data):
    if not data or "categories" not in data:
        return []
    
    # 创建分类选项，只显示有字符串的分类
    category_options = [{"label": cat, "value": cat} for cat in data["categories"].keys() if data["categories"][cat]]
    
    return category_options

# 抽屉中显示分类字符串的回调
@app.callback(
    Output("drawer-strings-container", "children"),
    [Input("data-store", "data"),
     Input("drawer-category-filter", "value")]
)
def update_drawer_strings(data, selected_category):
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
                id={"type": "drawer-string-btn", "index": f"{selected_category}-{i}"},
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

# 抽屉中点击字符串删除的回调
@app.callback(
    [Output("data-store", "data", allow_duplicate=True),
     Output("drawer-strings-container", "children", allow_duplicate=True),
     Output("drawer-category-filter", "options", allow_duplicate=True),
     Output("saved-strings-container", "children", allow_duplicate=True),
     Output("category-filter", "options", allow_duplicate=True)],
    [Input({"type": "drawer-string-btn", "index": dash.ALL}, "n_clicks")],
    [State({"type": "drawer-string-btn", "index": dash.ALL}, "id"),
     State("drawer-category-filter", "value"),
     State("data-store", "data")],
    prevent_initial_call=True
)
def delete_drawer_string(n_clicks, button_ids, selected_category, data):
    # 检查是否有按钮被点击
    if not any(n_clicks):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    # 找出被点击的按钮
    ctx = callback_context
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
            
            # 更新抽屉中的字符串显示
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
                            id={"type": "drawer-string-btn", "index": f"{selected_category}-{i}"},
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
                                color="primary",
                                outline=True,
                                size="sm",
                                style={"whiteSpace": "nowrap", "flexShrink": 0}
                            ) for i, string in enumerate(strings)
                        ]
                    )
                    
                    main_string_elements.append(button_container)
            
            if not main_string_elements:
                main_string_elements = [html.P("没有找到字符串", className="text-muted")]
            
            # 更新主页面分类选项
            main_category_options = [{"label": "所有分类", "value": "all"}] + \
                                   [{"label": cat, "value": cat} for cat in data["categories"].keys()]
            
            return data, string_elements, category_options, main_string_elements, main_category_options
        
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    except (ValueError, IndexError, AttributeError):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

# 更新选中字符串显示
@app.callback(
    Output("selected-strings-container", "children"),
    [Input("selected-strings", "data"),
     Input("data-store", "data")]
)  
def update_selected_strings(selected_strings, data):
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
     State("selected-log-file", "data")],
    prevent_initial_call=True
)
def toggle_selected_string(n_clicks, button_ids, selected_strings, selected_log_file):
    ctx = callback_context
    
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



# 生成并执行过滤命令的回调
@app.callback(
    [Output("generated-command", "value"),
     Output("log-filter-results", "children"),
     Output("filtered-result-store", "data"),
     Output("source-result-store", "data")],
    [Input("execute-filter-btn", "n_clicks"),
     Input("display-mode", "value")],
    [State("selected-strings", "data"),
     State("log-file-selector", "value")],
    prevent_initial_call=True
)
def execute_filter_command(n_clicks, display_mode, selected_strings, selected_log_file):
    # 获取触发回调的组件ID
    ctx = dash.callback_context
    if not ctx.triggered:
        return "", "", "", ""
    
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    # 如果是显示模式切换，但还没有执行过滤操作
    if triggered_id == "display-mode" and n_clicks == 0:
        return "", html.P("请先执行过滤操作", className="text-info text-center"), "", ""
    
    # 执行过滤命令
    filtered_command, filtered_result = execute_filter_logic(selected_strings, selected_log_file)
    
    # 执行源文件命令，传递选中的字符串用于高亮
    source_command, source_result = execute_source_logic(selected_log_file, selected_strings)
    
    # 根据显示模式返回结果
    if display_mode == "source":
        return source_command, source_result, filtered_result, source_result
    elif display_mode == "highlight":
        # 高亮模式：使用highlight配置执行过滤命令
        highlight_strings = load_highlight_config()
        if highlight_strings:
            highlight_command, highlight_result = execute_filter_logic(highlight_strings, selected_log_file)
            return highlight_command, highlight_result, filtered_result, source_result
        else:
            # 如果没有highlight配置，显示提示信息
            return "", html.P("未找到highlight配置文件或配置为空", className="text-warning text-center"), filtered_result, source_result
    else:
        return filtered_command, filtered_result, filtered_result, source_result

def execute_filter_logic(selected_strings, selected_log_file):
    """执行过滤逻辑"""
    # 提取保留字符串和过滤字符串
    keep_strings = []
    filter_strings = []
    
    for item in selected_strings:
        if isinstance(item, dict):
            if item["type"] == "keep":
                keep_strings.append(item["text"])
            else:
                filter_strings.append(item["text"])
        else:
            # 旧格式字符串，默认为保留字符串
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
    result_display = execute_command(full_command, selected_strings, data)
    
    return full_command, result_display

def execute_source_logic(selected_log_file, selected_strings=None):
    """执行源文件逻辑"""
    # 本地方式显示源文件
    if not selected_log_file:
        return "", html.P("请选择日志文件", className="text-danger text-center")
    log_path = get_log_path(selected_log_file)
    full_command = f"cat {log_path}"
    
    # 执行命令，如果提供了选中的字符串，则进行高亮
    if selected_strings:
        data = load_data()  # 加载当前数据
        result_display = execute_command(full_command, selected_strings, data)
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
    """为Dash组件生成高亮显示的组件列表"""
    if not selected_strings or not data or "categories" not in data:
        return html.Pre(text, className="small")
    
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
        return html.Pre(text, className="small")
    
    # 按长度降序排序，确保长关键字优先匹配
    keywords_to_highlight.sort(key=len, reverse=True)
    
    # 按行处理文本，确保每行都能正确高亮
    lines = text.split('\n')
    highlighted_lines = []
    
    for line in lines:
        if not line.strip():
            # 空行直接添加
            highlighted_lines.append(html.Div('\n', style={'whiteSpace': 'pre', 'fontFamily': 'monospace', 'fontSize': '12px'}))
            continue
            
        components = []
        remaining_text = line
        
        # 查找该行中所有需要高亮的关键字位置
        keyword_positions = []
        for keyword in keywords_to_highlight:
            if keyword in keyword_to_category:
                pattern = re.escape(keyword)
                matches = re.finditer(pattern, remaining_text, re.IGNORECASE)
                for match in matches:
                    keyword_positions.append({
                        'keyword': keyword,
                        'start': match.start(),
                        'end': match.end(),
                        'category': keyword_to_category[keyword],
                        'color': category_colors[keyword_to_category[keyword]]
                    })
        
        # 按起始位置排序
        keyword_positions.sort(key=lambda x: x['start'])
        
        if not keyword_positions:
            # 该行没有关键字，直接添加
            highlighted_lines.append(html.Div(line + '\n', style={'whiteSpace': 'pre', 'fontFamily': 'monospace', 'fontSize': '12px'}))
            continue
        
        # 构建该行的组件
        current_pos = 0
        for pos in keyword_positions:
            # 添加关键字前的文本
            if pos['start'] > current_pos:
                before_text = line[current_pos:pos['start']]
                components.append(before_text)
            
            # 添加高亮的关键字
            components.append(
                html.Span(
                    line[pos['start']:pos['end']],
                    style={
                        'backgroundColor': pos['color'],
                        'color': 'white',
                        'padding': '2px 4px',
                        'borderRadius': '3px',
                        'fontWeight': 'bold',
                        'display': 'inline'
                    }
                )
            )
            
            current_pos = pos['end']
        
        # 添加剩余文本
        if current_pos < len(line):
            components.append(line[current_pos:])
        
        # 添加换行符
        components.append('\n')
        
        # 创建该行的Div组件
        highlighted_lines.append(html.Div(components, style={'whiteSpace': 'pre', 'fontFamily': 'monospace', 'fontSize': '12px'}))
    
    # 返回包含所有行的Div
    return html.Div(highlighted_lines)

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



# 文件上传回调
@app.callback(
    [Output("upload-status", "children", allow_duplicate=True),
     Output("log-file-selector", "options", allow_duplicate=True)],
    [Input("upload-log-file", "contents")],
    [State("upload-log-file", "filename"),
     State("log-file-selector", "options")],
    prevent_initial_call=True
)
def handle_upload(contents, filename, current_options):
    if contents is None or filename is None:
        return "", dash.no_update
    
    try:
        # 确保logs目录存在
        ensure_log_dir()
        
        # 获取目标文件路径
        target_path = os.path.join(LOG_DIR, filename)
        
        # 检查文件是否已存在
        if os.path.exists(target_path):
            return (
                dbc.Alert(f"文件 '{filename}' 已存在，请重命名或删除原文件", color="warning"),
                dash.no_update
            )
        
        # 解析base64内容并保存文件
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        
        # 保存文件
        with open(target_path, 'wb') as f:
            f.write(decoded)
        
        # 更新文件选择器选项
        log_files = get_log_files()
        new_options = [{"label": file, "value": file} for file in log_files]
        
        return (
            dbc.Alert(f"成功上传文件 '{filename}'", color="success"),
            new_options
        )
        
    except Exception as e:
        return (
            dbc.Alert(f"上传失败: {str(e)}", color="danger"),
            dash.no_update
        )

# 切换上传/删除模式的回调
@app.callback(
    [Output("upload-mode-btn", "active"),
     Output("delete-mode-btn", "active"),
     Output("upload-mode-content", "style"),
     Output("delete-mode-content", "style"),
     Output("delete-file-selector", "options")],
    [Input("upload-mode-btn", "n_clicks"),
     Input("delete-mode-btn", "n_clicks")],
    [State("upload-mode-btn", "active"),
     State("delete-mode-btn", "active")]
)
def toggle_upload_delete_mode(upload_clicks, delete_clicks, upload_active, delete_active):
    ctx = callback_context
    if not ctx.triggered:
        # 初始状态：上传模式激活
        return True, False, {"display": "block"}, {"display": "none"}, []
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if button_id == "upload-mode-btn":
        # 切换到上传模式
        return True, False, {"display": "block"}, {"display": "none"}, []
    elif button_id == "delete-mode-btn":
        # 切换到删除模式，更新文件选择器选项
        log_files = get_log_files()
        delete_options = [{"label": file, "value": file} for file in log_files]
        return False, True, {"display": "none"}, {"display": "block"}, delete_options
    
    # 默认返回上传模式
    return True, False, {"display": "block"}, {"display": "none"}, []

# 文件删除回调
@app.callback(
    [Output("delete-status", "children"),
     Output("log-file-selector", "options", allow_duplicate=True),
     Output("delete-file-selector", "value")],
    [Input("delete-file-btn", "n_clicks")],
    [State("delete-file-selector", "value")],
    prevent_initial_call=True
)
def handle_delete(n_clicks, selected_file):
    if n_clicks is None or n_clicks == 0 or not selected_file:
        return "", dash.no_update, dash.no_update
    
    try:
        # 确保logs目录存在
        ensure_log_dir()
        
        # 获取目标文件路径
        target_path = os.path.join(LOG_DIR, selected_file)
        
        # 检查文件是否存在
        if not os.path.exists(target_path):
            return (
                dbc.Alert(f"文件 '{selected_file}' 不存在", color="warning"),
                dash.no_update,
                ""
            )
        
        # 删除文件
        os.remove(target_path)
        
        # 更新文件选择器选项
        log_files = get_log_files()
        new_options = [{"label": file, "value": file} for file in log_files]
        
        return (
            dbc.Alert(f"成功删除文件 '{selected_file}'", color="success"),
            new_options,
            ""  # 清空删除选择器
        )
        
    except Exception as e:
        return (
            dbc.Alert(f"删除失败: {str(e)}", color="danger"),
            dash.no_update,
            dash.no_update
        )

# 切换日志过滤选项折叠状态的回调
@app.callback(
    Output("filter-options-collapse", "is_open"),
    [Input("filter-options-toggle", "n_clicks")],
    [State("filter-options-collapse", "is_open")]
)
def toggle_filter_options(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open



if __name__ == "__main__":
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Log Filter Application')
    parser.add_argument('--port', type=int, default=8052, help='Port to run the application on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind the application to')
    args = parser.parse_args()
    
    app.run(debug=True, port=args.port, host=args.host)