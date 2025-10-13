import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
import json
import os

# 初始化 Dash 应用，使用 Bootstrap 主题
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# 数据存储文件路径
DATA_FILE = 'string_data.json'

# 获取所有配置文件
CONFIG_DIR = 'configs'

def ensure_config_dir():
    """确保配置目录存在"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

def get_config_files():
    """获取所有配置文件列表"""
    ensure_config_dir()
    config_files = []
    if os.path.exists(CONFIG_DIR):
        for file in os.listdir(CONFIG_DIR):
            if file.endswith('.json'):
                config_files.append(file[:-5])  # 去掉.json后缀
    return config_files

def get_config_path(config_name):
    """获取配置文件的完整路径"""
    ensure_config_dir()
    return os.path.join(CONFIG_DIR, f"{config_name}.json")

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

# 初始数据
data = load_data()

# 确保配置目录存在
ensure_config_dir()

# 应用布局
app.layout = html.Div([
    # 右上角keyword按钮 - 使用绝对定位
    dbc.Button("keyword", id="keyword-btn", color="primary", 
               style={"position": "fixed",  "right": "20px", "zIndex": "1000"}),
    
    dbc.Container([
        # Tab导航
        dbc.Tabs([
            # 第一个Tab：字符串管理
            dbc.Tab([
                # 可折叠的配置文件管理菜单
                dbc.Row([
                    dbc.Col([
                        dbc.Accordion([
                            dbc.AccordionItem([
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Input(
                                            id="config-name-input",
                                            placeholder="输入配置文件名...",
                                            type="text",
                                            style={"width": "200px"}
                                        )
                                    ], width=4),
                                    dbc.Col([
                                        dbc.Button("保存选中字符串", id="save-selected-btn", color="success"),
                                    ], width=8)
                                ], className="mb-2"),
                                dbc.Row([
                                    dbc.Col([
                                        dcc.Dropdown(
                                            id="config-selector",
                                            placeholder="选择配置文件...",
                                            style={"width": "200px"}
                                        )
                                    ], width=4),
                                    dbc.Col([
                                        dbc.Button("加载字符串", id="load-strings-btn", color="secondary", className="mr-2"),
                                        html.Span(" "),
                                        dbc.Button("删除配置", id="delete-config-btn", color="danger"),
                                    ], width=8)
                                ])
                            ], title="配置文件管理", item_id="config-management")
                        ], flush=True, start_collapsed=True, always_open=False)
                    ], width=12, className="mb-4")
                ]),
                
                # 主内容区域 - 左右两栏
                dbc.Row([
                    # 左侧：选中的字符串
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H4("选中的字符串", className="card-title"),
                                dbc.Button("清除选择", id="clear-selection-btn", color="danger", size="sm", className="mb-2"),
                                html.Div(id="selected-strings-container", style={"maxHeight": "400px", "overflowY": "auto"})
                            ])
                        ])
                    ], width=6),
                    
                    # 右侧：已保存的字符串区域
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
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
                                html.Div(id="saved-strings-container", style={"maxHeight": "250px", "overflowY": "auto", "marginTop": "10px"})
                            ])
                        ])
                    ], width=6)
                ], className="mb-4"),
                
                # 状态提示
                dbc.Row([
                    dbc.Col([
                        dbc.Alert(id="status-alert", is_open=False, dismissable=True, duration=4000)
                    ], width=12)
                ]),
            ], label="字符串管理", tab_id="tab-1"),
            
            # 第二个Tab：数据分析
            dbc.Tab([
                html.Div([
                    html.H3("数据分析", className="text-center mb-4"),
                    
                    # 日志过滤预览区域
                    dbc.Row([
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.H4("日志过滤预览", className="card-title"),
                                    html.P("这里将显示基于您选择的保留和过滤字符串的日志过滤结果", className="text-muted mb-3"),
                                    html.Div(id="log-preview-container", style={"maxHeight": "300px", "overflowY": "auto", "backgroundColor": "#f8f9fa", "padding": "10px", "border": "1px solid #dee2e6", "borderRadius": "5px"})
                                ])
                            ])
                        ], width=12)
                    ], className="mb-4"),
                    
                    # 其他数据分析功能
                    dbc.Row([
                        dbc.Col([
                            html.P("这是第二个标签页，用于数据分析功能。", className="text-muted text-center")
                        ], width=12)
                    ])
                ], className="p-4")
            ], label="数据分析", tab_id="tab-2"),
            
            # 第三个Tab：设置
            dbc.Tab([
                html.Div([
                    html.H3("设置", className="text-center mb-4"),
                    html.P("这是第三个标签页，用于系统设置。", className="text-muted text-center")
                ], className="p-4")
            ], label="设置", tab_id="tab-3")
        ], id="main-tabs", active_tab="tab-1"),
        
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
    ], fluid=True)
])

# 初始化数据存储
@app.callback(
    Output("data-store", "data", allow_duplicate=True),
    [Input("main-tabs", "active_tab")],
    prevent_initial_call="initial_duplicate"
)
def initialize_data_store(active_tab):
    return load_data()

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
     Input("string-type-radio", "value")]
)
def update_saved_strings(data, selected_category, string_type):
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
                        outline=True,
                        size="sm",
                        style={"whiteSpace": "nowrap", "flexShrink": 0}
                    ) for i, string in enumerate(strings)
                ]
            )
            
            string_elements.append(button_container)
    
    if not string_elements:
        string_elements = [html.P("没有找到字符串", className="text-muted")]
    
    return string_elements, category_options

# 更新配置文件选择器选项
@app.callback(
    Output("config-selector", "options"),
    [Input("status-alert", "children"),
     Input("main-tabs", "active_tab")],
    [State("status-alert", "children")],
    prevent_initial_call=False
)
def update_config_selector(status_children, active_tab, current_status):
    ctx = callback_context
    
    # 只有在状态提示显示保存或删除成功时才触发更新
    if ctx.triggered:
        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger_id == "status-alert" and current_status:
            # 检查状态消息是否包含保存或删除成功的信息
            if "成功保存" in current_status or "成功删除" in current_status:
                config_files = get_config_files()
                options = [{"label": config, "value": config} for config in config_files]
                return options
    
    # 默认情况下也返回当前配置列表
    config_files = get_config_files()
    options = [{"label": config, "value": config} for config in config_files]
    return options

# 选择字符串和加载字符串回调
@app.callback(
    Output("selected-strings", "data"),
    [Input({"type": "select-string-btn", "index": dash.ALL}, "n_clicks"),
     Input("clear-selection-btn", "n_clicks"),
     Input("load-strings-btn", "n_clicks")],
    [State("selected-strings", "data"),
     State("data-store", "data"),
     State("config-selector", "value"),
     State("string-type-radio", "value")]
)
def select_or_load_string(select_clicks, clear_clicks, load_clicks, selected_strings, data, selected_config, string_type):
    ctx = callback_context
    
    # 清除选择
    if clear_clicks:
        return []
    
    # 加载字符串
    if load_clicks and selected_config:
        config_path = get_config_path(selected_config)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    saved_selections = json.load(f)
                
                # 从保存的选择中提取所有字符串
                loaded_strings = []
                
                # 检查是否是新格式的配置文件（带类型信息）
                is_new_format = False
                for category, content in saved_selections.items():
                    if isinstance(content, dict) and ("keep" in content or "filter" in content):
                        is_new_format = True
                        break
                
                if is_new_format:
                    # 处理新格式的配置文件
                    for category, content in saved_selections.items():
                        if isinstance(content, dict):
                            # 处理保留字符串
                            if "keep" in content:
                                for string in content["keep"]:
                                    loaded_strings.append({
                                        "text": string,
                                        "type": "keep"
                                    })
                            
                            # 处理过滤字符串
                            if "filter" in content:
                                for string in content["filter"]:
                                    loaded_strings.append({
                                        "text": string,
                                        "type": "filter"
                                    })
                else:
                    # 处理旧格式的配置文件
                    for category, strings in saved_selections.items():
                        for string in strings:
                            loaded_strings.append({
                                "text": string,
                                "type": "keep"  # 默认为保留字符串
                            })
                
                # 检查所有字符串是否都存在于当前数据中
                valid_strings = []
                
                for item in loaded_strings:
                    string_text = item["text"]
                    for category, strings in data["categories"].items():
                        if string_text in strings:
                            valid_strings.append(item)
                            break
                
                return valid_strings
            except Exception:
                # 如果加载失败，保持当前选择不变
                return selected_strings
        else:
            # 如果文件不存在，保持当前选择不变
            return selected_strings
    
    # 选择字符串
    if ctx.triggered and ctx.triggered[0]["value"]:
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
    
    return selected_strings

# 状态提示回调 - 整合所有状态更新
@app.callback(
    [Output("status-alert", "children"),
     Output("status-alert", "is_open"),
     Output("status-alert", "color")],
    [Input("add-string-btn", "n_clicks"),
     Input({"type": "select-string-btn", "index": dash.ALL}, "n_clicks"),
     Input("clear-selection-btn", "n_clicks"),
     Input("save-selected-btn", "n_clicks"),
     Input("load-strings-btn", "n_clicks"),
     Input("delete-config-btn", "n_clicks")],
    [State("input-string", "value"),
     State("input-category", "value"),
     State("data-store", "data"),
     State("selected-strings", "data"),
     State("config-name-input", "value"),
     State("config-selector", "value")]
)
def show_status(add_clicks, select_clicks, clear_clicks, save_clicks, load_clicks, delete_clicks, input_string, input_category, data, selected_strings, config_name, selected_config):
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
    
    # 保存选中字符串状态
    if "save-selected-btn" in trigger_id and save_clicks:
        if selected_strings:
            if not config_name:
                return "请输入配置文件名", True, "warning"
            
            # 按分类和类型组织选中的字符串
            categorized_strings = {}
            for item in selected_strings:
                if isinstance(item, dict):
                    string_text = item["text"]
                    string_type = item["type"]
                    
                    # 查找字符串所属的分类
                    for category, strings in data["categories"].items():
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
                    for category, strings in data["categories"].items():
                        if string_text in strings:
                            # 创建分类（如果不存在）
                            if category not in categorized_strings:
                                categorized_strings[category] = {"keep": [], "filter": []}
                            
                            # 默认为保留字符串
                            categorized_strings[category]["keep"].append(string_text)
                            break
            
            # 保存选中的字符串到配置文件
            config_path = get_config_path(config_name)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(categorized_strings, f, ensure_ascii=False, indent=2)
            
            return f"成功保存 {len(selected_strings)} 个选中的字符串到配置文件 '{config_name}'", True, "success"
        else:
            return "没有选中的字符串可供保存", True, "warning"
    
    # 加载字符串状态
    if "load-strings-btn" in trigger_id and load_clicks:
        if not selected_config:
            return "请选择要加载的配置文件", True, "warning"
        
        config_path = get_config_path(selected_config)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    saved_selections = json.load(f)
                
                # 从保存的选择中提取所有字符串
                loaded_strings = []
                
                # 检查是否是新格式的配置文件（带类型信息）
                is_new_format = False
                for category, content in saved_selections.items():
                    if isinstance(content, dict) and ("keep" in content or "filter" in content):
                        is_new_format = True
                        break
                
                if is_new_format:
                    # 处理新格式的配置文件
                    keep_count = 0
                    filter_count = 0
                    
                    for category, content in saved_selections.items():
                        if isinstance(content, dict):
                            # 处理保留字符串
                            if "keep" in content:
                                keep_count += len(content["keep"])
                            
                            # 处理过滤字符串
                            if "filter" in content:
                                filter_count += len(content["filter"])
                    
                    if keep_count > 0 and filter_count > 0:
                        return f"成功加载 {keep_count} 个保留字符串和 {filter_count} 个过滤字符串", True, "success"
                    elif keep_count > 0:
                        return f"成功加载 {keep_count} 个保留字符串", True, "success"
                    else:
                        return f"成功加载 {filter_count} 个过滤字符串", True, "success"
                else:
                    # 处理旧格式的配置文件
                    for category, strings in saved_selections.items():
                        loaded_strings.extend(strings)
                    
                    return f"成功加载 {len(loaded_strings)} 个字符串", True, "success"
            except Exception:
                return "加载配置文件失败", True, "danger"
        else:
            return "配置文件不存在", True, "warning"
    
    # 删除配置状态
    if "delete-config-btn" in trigger_id and delete_clicks:
        if not selected_config:
            return "请选择要删除的配置文件", True, "warning"
        
        config_path = get_config_path(selected_config)
        if os.path.exists(config_path):
            try:
                os.remove(config_path)
                return f"成功删除配置文件 '{selected_config}'", True, "success"
            except Exception:
                return "删除配置文件失败", True, "danger"
        else:
            return "配置文件不存在", True, "warning"
    
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

# 更新日志过滤预览
@app.callback(
    Output("log-preview-container", "children"),
    [Input("selected-strings", "data")]
)
def update_log_preview(selected_strings):
    if not selected_strings:
        return [
            html.P("请选择字符串以查看日志过滤预览", className="text-muted text-center"),
            html.Pre("示例日志:\n"
                    "2023-01-01 10:00:00 INFO [UserService] 用户登录成功\n"
                    "2023-01-01 10:00:01 DEBUG [DatabaseService] 执行SQL查询\n"
                    "2023-01-01 10:00:02 ERROR [PaymentService] 支付处理失败\n"
                    "2023-01-01 10:00:03 INFO [UserService] 用户登出\n"
                    "2023-01-01 10:00:04 WARN [CacheService] 缓存即将过期", 
                    className="text-muted small")
        ]
    
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
    
    # 示例日志
    sample_logs = [
        "2023-01-01 10:00:00 INFO [UserService] 用户登录成功",
        "2023-01-01 10:00:01 DEBUG [DatabaseService] 执行SQL查询",
        "2023-01-01 10:00:02 ERROR [PaymentService] 支付处理失败",
        "2023-01-01 10:00:03 INFO [UserService] 用户登出",
        "2023-01-01 10:00:04 WARN [CacheService] 缓存即将过期",
        "2023-01-01 10:00:05 INFO [OrderService] 创建订单成功",
        "2023-01-01 10:00:06 ERROR [PaymentService] 支付超时",
        "2023-01-01 10:00:07 DEBUG [UserService] 验证用户令牌",
        "2023-01-01 10:00:08 INFO [NotificationService] 发送邮件通知",
        "2023-01-01 10:00:09 WARN [DatabaseService] 连接池接近上限"
    ]
    
    # 应用保留字符串过滤
    filtered_logs = []
    if keep_strings:
        for log in sample_logs:
            for keep_str in keep_strings:
                if keep_str in log:
                    filtered_logs.append(log)
                    break
    else:
        filtered_logs = sample_logs
    
    # 应用过滤字符串
    final_logs = []
    if filter_strings:
        for log in filtered_logs:
            should_keep = True
            for filter_str in filter_strings:
                if filter_str in log:
                    should_keep = False
                    break
            if should_keep:
                final_logs.append(log)
    else:
        final_logs = filtered_logs
    
    # 创建预览内容
    preview_elements = []
    
    # 添加过滤说明
    if keep_strings and filter_strings:
        preview_elements.append(html.P(f"保留包含 {', '.join(keep_strings)} 但不包含 {', '.join(filter_strings)} 的日志行", className="text-info small mb-2"))
    elif keep_strings:
        preview_elements.append(html.P(f"保留包含 {', '.join(keep_strings)} 的日志行", className="text-success small mb-2"))
    elif filter_strings:
        preview_elements.append(html.P(f"过滤掉包含 {', '.join(filter_strings)} 的日志行", className="text-danger small mb-2"))
    
    # 添加过滤结果
    if final_logs:
        preview_elements.append(html.Pre("\n".join(final_logs), className="small"))
    else:
        preview_elements.append(html.P("没有符合条件的日志行", className="text-warning"))
    
    return preview_elements

# 点击已选择字符串取消选择的回调
@app.callback(
    Output("selected-strings", "data", allow_duplicate=True),
    [Input({"type": "selected-string-btn", "index": dash.ALL}, "n_clicks")],
    [State({"type": "selected-string-btn", "index": dash.ALL}, "id"),
     State("selected-strings", "data")],
    prevent_initial_call=True
)
def toggle_selected_string(n_clicks, button_ids, selected_strings):
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
                
                return new_selected_strings
    
    return selected_strings

if __name__ == "__main__":
    app.run_server(debug=True)