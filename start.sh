#!/usr/bin/env bash
set -e

# MiniCron 一键启动脚本
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# 自动定位 conda 环境或默认 python
CONDA_PYTHON="$HOME/miniconda3/envs/minicron/bin/python"

if [ -f "$CONDA_PYTHON" ]; then
    PYTHON_EXEC="$CONDA_PYTHON"
elif command -v python3 &>/dev/null; then
    PYTHON_EXEC="python3"
else
    PYTHON_EXEC="python"
fi

echo "=================================================="
echo "🕒 正在启动 MiniCron 任务调度与可视化控制台..."
echo "🐍 Python 解释器: $PYTHON_EXEC"
echo "📁 脚本目录: $DIR/scripts"
echo "🌐 控制台地址: http://0.0.0.0:8000"
echo "🔑 默认密码: admin123 (可通过环境变量 ADMIN_PASSWORD 自定义)"
echo "=================================================="

exec "$PYTHON_EXEC" -m app.main
