#!/bin/bash
set -a
# 获取脚本所在目录的绝对路径
SCRIPT_DIR=$(cd $(dirname "$0") && cd .. && pwd)
# 使用绝对路径源 .env 文件
source "$SCRIPT_DIR/.env"
set +a

# 将上级目录的绝对路径添加到 PYTHONPATH
export PYTHONPATH="$SCRIPT_DIR/:$PYTHONPATH"

uvicorn app:app --host 0.0.0.0 --port 8000 --http h11
