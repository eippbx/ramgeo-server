#!/bin/bash

# 节点服务器启动脚本

# 设置工作目录
WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 确保日志目录存在
LOG_DIR="$WORK_DIR/logs"
mkdir -p "$LOG_DIR"

# 设置日志文件
LOG_FILE="$LOG_DIR/node_server_$(date +%Y%m%d_%H%M%S).log"

# 输出启动信息
echo "=== 节点服务器启动脚本 ===" > "$LOG_FILE"
echo "启动时间: $(date)" >> "$LOG_FILE"
echo "工作目录: $WORK_DIR" >> "$LOG_FILE"
echo "日志文件: $LOG_FILE" >> "$LOG_FILE"
echo "==========================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# 激活conda环境
echo "正在激活conda环境: ramgeo" >> "$LOG_FILE"
source $(conda info --base)/etc/profile.d/conda.sh
conda activate ramgeo >> "$LOG_FILE" 2>&1

if [ $? -ne 0 ]; then
    echo "错误: 无法激活conda环境 ramgeo" >> "$LOG_FILE"
    echo "错误: 无法激活conda环境 ramgeo"
    exit 1
fi

# 启动节点服务器（前台运行，用于调试）
echo "启动节点服务器（前台模式），日志将直接输出到控制台..."
python3 "$WORK_DIR/main.py" 2>&1
