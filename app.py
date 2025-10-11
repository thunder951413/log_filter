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

# 应用布局
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.H1("字符串分类管理器", className="text-center mb-4"),
        ], width=12)
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
        
        # 右侧：其他功能
        dbc.Col([
            # 输入区域
            dbc.Card([
                dbc.CardBody([
                    html.H4("添加字符串", className="card-title"),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("字符串内容:"),
                            dbc.Textarea(id="input-string", placeholder="输入要分类的字符串...", style={"height": "100px"})
                        ], width=8),
                        dbc.Col([
                            dbc.Label("分类:"),
                            dbc.Input(id="input-category", placeholder="输入分类名称...", type="text")
                        ], width=4)
                    ], className="mb-3"),
                    dbc.Button("添加字符串", id="add-string-btn", color="primary", className="w-100")
                ])
            ], className="mb-4"),
            
            # 已保存的字符串区域
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
    
    # 存储组件
    dcc.Store(id="data-store", data=data),
    dcc.Store(id="selected-strings", data=[]),
], fluid=True)

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
     Input("category-filter", "value")]
)
def update_saved_strings(data, selected_category):
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
                        color="primary",
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

# 选择字符串回调
@app.callback(
    Output("selected-strings", "data"),
    [Input({"type": "select-string-btn", "index": dash.ALL}, "n_clicks"),
     Input("clear-selection-btn", "n_clicks")],
    [State("selected-strings", "data"),
     State("data-store", "data")]
)
def select_string(select_clicks, clear_clicks, selected_strings, data):
    ctx = callback_context
    
    # 清除选择
    if clear_clicks:
        return []
    
    # 选择字符串
    if ctx.triggered and ctx.triggered[0]["value"]:
        button_id = ctx.triggered[0]["prop_id"].split(".")[0]
        button_id = eval(button_id)  # 转换为字典
        category_index = button_id["index"].split("-")
        category = category_index[0]
        index = int(category_index[1])
        
        if category in data["categories"] and index < len(data["categories"][category]):
            selected_string = data["categories"][category][index]
            
            # 检查是否已经选择
            if selected_string not in selected_strings:
                selected_strings.append(selected_string)
    
    return selected_strings

# 状态提示回调
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

# 更新选中字符串显示
@app.callback(
    Output("selected-strings-container", "children"),
    [Input("selected-strings", "data"),
     Input("data-store", "data")]
)
def update_selected_strings(selected_strings, data):
    if not selected_strings:
        return [html.P("没有选中的字符串", className="text-muted")]
    
    # 按分类组织选中的字符串
    categorized_strings = {}
    for category, strings in data["categories"].items():
        for string in strings:
            if string in selected_strings:
                if category not in categorized_strings:
                    categorized_strings[category] = []
                categorized_strings[category].append(string)
    
    # 创建显示元素
    display_elements = []
    for category, strings in categorized_strings.items():
        display_elements.append(html.H6(category, className="mt-3 mb-2"))
        # 使用flex布局创建紧凑的按钮显示
        string_buttons = []
        for string in strings:
            string_buttons.append(
                dbc.Button(
                    string, 
                    id={"type": "selected-string-btn", "index": string},
                    color="primary", 
                    size="sm",
                    className="m-1",
                    style={"whiteSpace": "nowrap", "flexShrink": 0}
                )
            )
        # 使用d-flex和flex-wrap实现多列布局
        display_elements.append(
            html.Div(
                string_buttons,
                className="d-flex flex-wrap gap-2",
                style={"minHeight": "50px"}
            )
        )
    
    return display_elements

if __name__ == "__main__":
    app.run_server(debug=True)