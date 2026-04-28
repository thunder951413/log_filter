#!/bin/bash
# 激活Python虚拟环境的脚本

echo "正在激活Python虚拟环境..."
source .venv/bin/activate

echo "Python版本: $(python --version)"
echo "Python3版本: $(python3 --version)"
echo "虚拟环境已激活。使用 'deactivate' 退出。"