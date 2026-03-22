#!/bin/bash
# 意大利旅游解说系统 - 启动脚本

# 进入脚本所在目录
cd "$(dirname "$0")"

# 激活虚拟环境
source venv/bin/activate

# 启动Flask应用
echo "======================================"
echo "  意大利旅游解说系统"
echo "======================================"
echo ""
echo "启动中..."
echo "访问地址: http://localhost:8686"
echo "按 Ctrl+C 停止服务"
echo ""

python app.py
