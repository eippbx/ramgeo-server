#!/bin/bash

# 节点服务器管理脚本
# 功能: 启动、停止、重启、查看状态

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 配置
WORK_DIR="$SCRIPT_DIR"
LOG_DIR="$WORK_DIR/logs"
PID_FILE="$WORK_DIR/node_server.pid"
CONDA_ENV="ramgeo"
PYTHON_SCRIPT="$WORK_DIR/main.py"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 确保日志目录存在
mkdir -p "$LOG_DIR"

# 检查进程是否运行
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0
        else
            rm -f "$PID_FILE"
            return 1
        fi
    fi
    return 1
}

# 激活conda环境
activate_conda() {
    if ! command -v conda &> /dev/null; then
        echo -e "${RED}错误: 未找到conda命令${NC}"
        return 1
    fi
    
    source $(conda info --base)/etc/profile.d/conda.sh
    conda activate "$CONDA_ENV" 2>&1
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}错误: 无法激活conda环境 $CONDA_ENV${NC}"
        return 1
    fi
    
    return 0
}

# 启动服务
start_service() {
    if is_running; then
        echo -e "${YELLOW}节点服务器已经在运行中 (PID: $(cat $PID_FILE))${NC}"
        return 1
    fi
    
    echo "正在启动节点服务器..."
    
    # 激活conda环境
    if ! activate_conda; then
        return 1
    fi
    
    # 启动服务（后台运行）
    nohup python3 "$PYTHON_SCRIPT" > "$LOG_DIR/node_server_output.log" 2>&1 &
    PID=$!
    
    # 保存PID
    echo $PID > "$PID_FILE"
    
    # 等待启动
    sleep 2
    
    # 检查进程是否成功启动
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}节点服务器启动成功 (PID: $PID)${NC}"
        echo "日志文件: $LOG_DIR/node_server.log"
        echo "输出日志: $LOG_DIR/node_server_output.log"
        return 0
    else
        echo -e "${RED}节点服务器启动失败${NC}"
        rm -f "$PID_FILE"
        return 1
    fi
}

# 停止服务
stop_service() {
    if ! is_running; then
        echo -e "${YELLOW}节点服务器未运行${NC}"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    echo "正在停止节点服务器 (PID: $PID)..."
    
    # 发送TERM信号
    kill "$PID" 2>/dev/null || true
    
    # 等待进程结束
    for i in {1..10}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    # 如果进程仍在运行，强制终止
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}进程未响应，正在强制终止...${NC}"
        kill -9 "$PID" 2>/dev/null || true
        sleep 1
    fi
    
    # 删除PID文件
    rm -f "$PID_FILE"
    
    # 检查是否成功停止
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}节点服务器已停止${NC}"
        return 0
    else
        echo -e "${RED}节点服务器停止失败${NC}"
        return 1
    fi
}

# 重启服务
restart_service() {
    echo "正在重启节点服务器..."
    stop_service
    sleep 2
    start_service
}

# 查看状态
status_service() {
    echo "=== 节点服务器状态 ==="
    
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo -e "状态: ${GREEN}运行中${NC}"
        echo "PID: $PID"
        echo "启动时间: $(ps -p $PID -o lstart= 2>/dev/null || echo '未知')"
        echo "CPU使用率: $(ps -p $PID -o %cpu= 2>/dev/null || echo '未知')%"
        echo "内存使用: $(ps -p $PID -o %mem= 2>/dev/null || echo '未知')%"
        echo "运行时长: $(ps -p $PID -o etime= 2>/dev/null || echo '未知')"
        echo ""
        echo "日志文件: $LOG_DIR/node_server.log"
        echo "输出日志: $LOG_DIR/node_server_output.log"
    else
        echo -e "状态: ${RED}未运行${NC}"
    fi
    
    echo ""
    
    # 检查是否有ramgeo任务进程
    RAMGEO_COUNT=$(ps aux | grep "[r]amgeo.*task-" | wc -l)
    if [ $RAMGEO_COUNT -gt 0 ]; then
        echo -e "${YELLOW}警告: 发现 $RAMGEO_COUNT 个ramgeo任务进程仍在运行${NC}"
        echo "任务进程列表:"
        ps aux | grep "[r]amgeo.*task-" | awk '{print "  PID:", $2, "  任务:", $12, $13, $14}'
    fi
}

# 查看日志
view_logs() {
    LOG_FILE="$LOG_DIR/node_server.log"
    
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "${RED}日志文件不存在: $LOG_FILE${NC}"
        return 1
    fi
    
    if [ -z "$1" ]; then
        # 默认显示最后50行
        tail -n 50 "$LOG_FILE"
    else
        # 显示指定行数
        tail -n "$1" "$LOG_FILE"
    fi
}

# 实时查看日志
tail_logs() {
    LOG_FILE="$LOG_DIR/node_server.log"
    
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "${RED}日志文件不存在: $LOG_FILE${NC}"
        return 1
    fi
    
    echo "正在实时查看日志 (按Ctrl+C退出)..."
    tail -f "$LOG_FILE"
}

# 清理日志
clean_logs() {
    echo "正在清理日志文件..."
    
    # 备份当前日志
    if [ -f "$LOG_DIR/node_server.log" ]; then
        BACKUP_FILE="$LOG_DIR/node_server_$(date +%Y%m%d_%H%M%S).log.bak"
        mv "$LOG_DIR/node_server.log" "$BACKUP_FILE"
        echo "日志已备份到: $BACKUP_FILE"
    fi
    
    if [ -f "$LOG_DIR/node_server_output.log" ]; then
        BACKUP_FILE="$LOG_DIR/node_server_output_$(date +%Y%m%d_%H%M%S).log.bak"
        mv "$LOG_DIR/node_server_output.log" "$BACKUP_FILE"
        echo "输出日志已备份到: $BACKUP_FILE"
    fi
    
    echo -e "${GREEN}日志清理完成${NC}"
}

# 显示帮助信息
show_help() {
    echo "节点服务器管理脚本"
    echo ""
    echo "用法: $0 {start|stop|restart|status|logs|tail|clean|help}"
    echo ""
    echo "命令:"
    echo "  start    - 启动节点服务器（后台运行）"
    echo "  stop     - 停止节点服务器"
    echo "  restart  - 重启节点服务器"
    echo "  status   - 查看节点服务器状态"
    echo "  logs     - 查看日志（可指定行数，默认50行）"
    echo "  tail     - 实时查看日志"
    echo "  clean    - 清理日志文件（自动备份）"
    echo "  help     - 显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 start              # 启动服务"
    echo "  $0 logs 100           # 查看最后100行日志"
    echo "  $0 tail               # 实时查看日志"
}

# 主函数
main() {
    case "$1" in
        start)
            start_service
            ;;
        stop)
            stop_service
            ;;
        restart)
            restart_service
            ;;
        status)
            status_service
            ;;
        logs)
            view_logs "$2"
            ;;
        tail)
            tail_logs
            ;;
        clean)
            clean_logs
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            echo -e "${RED}错误: 未知命令 '$1'${NC}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
