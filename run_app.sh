#!/bin/bash
# 直接运行应用的脚本
# 无需激活虚拟环境，直接使用虚拟环境中的python

echo "正在启动日志分析应用..."
echo ""

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "❌ 错误: 找不到虚拟环境 (.venv目录)"
    echo "请先创建虚拟环境: python3 -m venv .venv"
    exit 1
fi

# 检查应用文件
if [ ! -f "app.py" ]; then
    echo "❌ 错误: 找不到app.py文件"
    exit 1
fi

# 直接使用虚拟环境中的python运行应用
echo "使用虚拟环境中的Python:"
echo "  路径: $(pwd)/.venv/bin/python"
echo "  版本: $(.venv/bin/python --version 2>&1)"
echo ""

echo "启动应用 (端口: 8052)..."
echo "按 Ctrl+C 停止应用"
echo ""

# 运行应用
.venv/bin/python app.py