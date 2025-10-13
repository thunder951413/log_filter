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
app.layout = html.Div([
    # 右上角keyword按钮 - 使用绝对定位
    dbc.Button("keyword", id="keyword-btn", color="primary", 
               style={"position": "fixed",  "right": "20px", "zIndex": "1000"}),
    
    dbc.Container([
        # Tab导航
        dbc.Tabs([
            # 第一个Tab：字符串管理
            dbc.Tab([
                # 顶部行：包含保存/加载按钮
                dbc.Row([
                    dbc.Col([
                        dbc.Button("保存选中字符串", id="save-selected-btn", color="success", className="mr-2"),
                        dbc.Button("加载字符串", id="load-strings-btn", color="secondary"),
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
                    html.P("这是第二个标签页，用于数据分析功能。", className="text-muted text-center")
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
                    ], width=12, className="mb-3"),
                    dbc.Col([
                        dbc.Button("删除选中字符串", id="delete-strings-btn", color="danger", className="w-100")
                    ], width=12)
                ], className="mb-4 p-3 border rounded")
            ],
            id="keyword-drawer",
            placement="end",
            is_open=False,
            style={"width": "66.67%"}
        ),
        
        # 存储组件
        dcc.Store(id="data-store", data=data),
        dcc.Store(id="selected-strings", data=[]),
    ], fluid=True)
])

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

# 选择字符串和加载字符串回调
@app.callback(
    Output("selected-strings", "data"),
    [Input({"type": "select-string-btn", "index": dash.ALL}, "n_clicks"),
     Input("clear-selection-btn", "n_clicks"),
     Input("load-strings-btn", "n_clicks")],
    [State("selected-strings", "data"),
     State("data-store", "data")]
)
def select_or_load_string(select_clicks, clear_clicks, load_clicks, selected_strings, data):
    ctx = callback_context
    
    # 清除选择
    if clear_clicks:
        return []
    
    # 加载字符串
    if load_clicks:
        SAVED_SELECTIONS_FILE = 'selected_strings.json'
        if os.path.exists(SAVED_SELECTIONS_FILE):
            try:
                with open(SAVED_SELECTIONS_FILE, 'r', encoding='utf-8') as f:
                    saved_selections = json.load(f)
                
                # 从保存的选择中提取所有字符串
                all_strings = []
                for category, strings in saved_selections.items():
                    all_strings.extend(strings)
                
                # 检查所有字符串是否都存在于当前数据中
                valid_strings = []
                
                for string in all_strings:
                    for category, strings in data["categories"].items():
                        if string in strings:
                            valid_strings.append(string)
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
                
                # 检查是否已经选择
                if selected_string not in selected_strings:
                    selected_strings.append(selected_string)
    
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
     Input("load-strings-btn", "n_clicks")],
    [State("input-string", "value"),
     State("input-category", "value"),
     State("data-store", "data"),
     State("selected-strings", "data")]
)
def show_status(add_clicks, select_clicks, clear_clicks, save_clicks, load_clicks, input_string, input_category, data, selected_strings):
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
            # 按分类组织选中的字符串
            categorized_strings = {}
            for category, strings in data["categories"].items():
                for string in strings:
                    if string in selected_strings:
                        if category not in categorized_strings:
                            categorized_strings[category] = []
                        categorized_strings[category].append(string)
            
            # 保存选中的字符串到文件
            SAVED_SELECTIONS_FILE = 'selected_strings.json'
            with open(SAVED_SELECTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(categorized_strings, f, ensure_ascii=False, indent=2)
            
            return f"成功保存 {len(selected_strings)} 个选中的字符串到 {SAVED_SELECTIONS_FILE}", True, "success"
        else:
            return "没有选中的字符串可供保存", True, "warning"
    
    # 加载字符串状态
    if "load-strings-btn" in trigger_id and load_clicks:
        SAVED_SELECTIONS_FILE = 'selected_strings.json'
        if os.path.exists(SAVED_SELECTIONS_FILE):
            try:
                with open(SAVED_SELECTIONS_FILE, 'r', encoding='utf-8') as f:
                    saved_selections = json.load(f)
                
                # 从保存的选择中提取所有字符串
                all_strings = []
                for category, strings in saved_selections.items():
                    all_strings.extend(strings)
                
                return f"成功加载 {len(all_strings)} 个字符串", True, "success"
            except Exception:
                return "加载字符串失败", True, "danger"
        else:
            return "没有保存的字符串文件", True, "warning"
    
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
    
    # 创建字符串选择列表
    string_elements = []
    for i, string in enumerate(strings):
        string_elements.append(
            dbc.Checklist(
                options=[{"label": string, "value": f"{selected_category}-{i}"}],
                value=[],
                id={"type": "drawer-string-checkbox", "index": f"{selected_category}-{i}"},
                switch=True,
                className="mb-2"
            )
        )
    
    return string_elements

# 删除选中字符串的回调
@app.callback(
    [Output("data-store", "data", allow_duplicate=True),
     Output("drawer-strings-container", "children", allow_duplicate=True),
     Output("drawer-category-filter", "options", allow_duplicate=True),
     Output("saved-strings-container", "children", allow_duplicate=True),
     Output("category-filter", "options", allow_duplicate=True)],
    [Input("delete-strings-btn", "n_clicks")],
    [State("drawer-category-filter", "value"),
     State({"type": "drawer-string-checkbox", "index": dash.ALL}, "value"),
     State("data-store", "data")],
    prevent_initial_call=True
)
def delete_selected_strings(n_clicks, selected_category, checkbox_values, data):
    if not n_clicks or not selected_category or not checkbox_values:
        return data, dash.no_update, dash.no_update
    
    # 获取所有被选中的字符串索引
    selected_indices = []
    for checkbox_value in checkbox_values:
        if checkbox_value:  # 如果复选框被选中
            for value in checkbox_value:
                # 解析字符串索引："分类名-索引"
                category_index = value.split("-")
                if len(category_index) == 2 and category_index[0] == selected_category:
                    try:
                        index = int(category_index[1])
                        selected_indices.append(index)
                    except ValueError:
                        continue
    
    # 按索引从大到小排序，以便从后往前删除（避免索引变化问题）
    selected_indices.sort(reverse=True)
    
    # 删除选中的字符串
    deleted_count = 0
    if selected_category in data["categories"]:
        for index in selected_indices:
            if 0 <= index < len(data["categories"][selected_category]):
                data["categories"][selected_category].pop(index)
                deleted_count += 1
        
        # 如果分类为空，删除该分类
        if not data["categories"][selected_category]:
            del data["categories"][selected_category]
        
        # 保存数据
        save_data(data)
    
    # 更新显示
    if deleted_count > 0:
        # 重新获取当前分类的字符串
        if selected_category in data["categories"] and data["categories"][selected_category]:
            strings = data["categories"][selected_category]
            string_elements = []
            for i, string in enumerate(strings):
                string_elements.append(
                    dbc.Checklist(
                        options=[{"label": string, "value": f"{selected_category}-{i}"}],
                        value=[],
                        id={"type": "drawer-string-checkbox", "index": f"{selected_category}-{i}"},
                        switch=True,
                        className="mb-2"
                    )
                )
            
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
        else:
            # 如果分类被删除或为空，清空显示
            main_category_options = [{"label": "所有分类", "value": "all"}] + \
                                   [{"label": cat, "value": cat} for cat in data["categories"].keys()]
            
            return data, html.P("该分类中没有字符串", className="text-muted text-center"), [{"label": cat, "value": cat} for cat in data["categories"].keys() if data["categories"][cat]], [html.P("没有找到字符串", className="text-muted")], main_category_options
    
    return data, dash.no_update, dash.no_update, dash.no_update, dash.no_update

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