#!/bin/bash

# 代理服务器启动脚本

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 配置
CONDA_ENV_NAME="ramgeo"
PROXY_SERVER_CMD="python -m proxy_server.main"
PID_FILE=".proxy_server.pid"
LOG_FILE="logs/proxy_server.log"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 创建日志目录
mkdir -p logs

# 激活conda环境
activate_conda_env() {
    # 查找conda安装路径
    if [ -n "$CONDA_EXE" ]; then
        CONDA_PATH="$CONDA_EXE"
    elif [ -f "$HOME/miniconda3/bin/conda" ]; then
        CONDA_PATH="$HOME/miniconda3/bin/conda"
    elif [ -f "$HOME/anaconda3/bin/conda" ]; then
        CONDA_PATH="$HOME/anaconda3/bin/conda"
    elif [ -f "/opt/miniconda3/bin/conda" ]; then
        CONDA_PATH="/opt/miniconda3/bin/conda"
    elif [ -f "/opt/anaconda3/bin/conda" ]; then
        CONDA_PATH="/opt/anaconda3/bin/conda"
    else
        echo -e "${RED}未找到conda安装路径${NC}"
        return 1
    fi
    
    # 获取conda基础路径
    CONDA_BASE=$(dirname $(dirname "$CONDA_PATH"))
    
    # 初始化conda
    if [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
        source "$CONDA_BASE/etc/profile.d/conda.sh"
    else
        echo -e "${RED}未找到conda初始化脚本${NC}"
        return 1
    fi
    
    # 激活环境
    if conda env list | grep -q "^${CONDA_ENV_NAME} "; then
        conda activate "$CONDA_ENV_NAME"
        echo -e "${GREEN}已激活conda环境: ${CONDA_ENV_NAME}${NC}"
        return 0
    else
        echo -e "${RED}conda环境 ${CONDA_ENV_NAME} 不存在${NC}"
        echo -e "${YELLOW}可用环境列表:${NC}"
        conda env list
        return 1
    fi
}

# 检查是否已有代理服务器在运行
check_running() {
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            echo -e "${YELLOW}代理服务器已在运行 (PID: $OLD_PID)${NC}"
            return 0
        else
            echo -e "${YELLOW}发现旧的PID文件，清理中...${NC}"
            rm -f "$PID_FILE"
        fi
    fi
    
    # 检查端口占用
    if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${RED}端口 8080 已被占用${NC}"
        echo -e "${YELLOW}尝试终止占用端口的进程...${NC}"
        lsof -ti:8080 | xargs -r kill -9
        sleep 1
    fi
    
    if lsof -Pi :8765 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${RED}端口 8765 已被占用${NC}"
        echo -e "${YELLOW}尝试终止占用端口的进程...${NC}"
        lsof -ti:8765 | xargs -r kill -9
        sleep 1
    fi
    
    return 1
}

# 停止代理服务器
stop_proxy_server() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        echo -e "${YELLOW}停止代理服务器 (PID: $PID)...${NC}"
        kill "$PID" 2>/dev/null
        
        # 等待进程结束
        for i in {1..10}; do
            if ! ps -p "$PID" > /dev/null 2>&1; then
                echo -e "${GREEN}代理服务器已停止${NC}"
                rm -f "$PID_FILE"
                return 0
            fi
            sleep 1
        done
        
        # 强制终止
        echo -e "${YELLOW}强制终止代理服务器...${NC}"
        kill -9 "$PID" 2>/dev/null
        rm -f "$PID_FILE"
    else
        echo -e "${YELLOW}未找到PID文件，尝试通过端口停止...${NC}"
        lsof -ti:8080,8765 | xargs -r kill -9
    fi
}

# 启动代理服务器
start_proxy_server() {
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}    启动 RAMGEO 代理服务器${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    
    # 检查是否已运行
    if check_running; then
        echo -e "${YELLOW}如需重启，请先执行: $0 stop${NC}"
        return 1
    fi
    
    # 激活conda环境
    if ! activate_conda_env; then
        echo -e "${RED}激活conda环境失败，无法启动服务器${NC}"
        return 1
    fi
    
    echo -e "${GREEN}工作目录: $SCRIPT_DIR${NC}"
    echo -e "${GREEN}启动命令: $PROXY_SERVER_CMD${NC}"
    echo ""
    
    # 启动服务器
    nohup $PROXY_SERVER_CMD > "$LOG_FILE" 2>&1 &
    PID=$!
    
    # 保存PID
    echo $PID > "$PID_FILE"
    
    # 等待启动
    sleep 3
    
    # 检查是否启动成功
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}代理服务器启动成功！${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo -e "PID: $PID"
        echo -e "REST API: http://localhost:8080"
        echo -e "WebSocket: ws://localhost:8765"
        echo -e "日志文件: $LOG_FILE"
        echo ""
        echo -e "${YELLOW}查看日志: tail -f $LOG_FILE${NC}"
        echo -e "${YELLOW}停止服务: $0 stop${NC}"
        echo -e "${YELLOW}查看状态: $0 status${NC}"
        return 0
    else
        echo -e "${RED}代理服务器启动失败！${NC}"
        echo -e "${YELLOW}查看日志: tail -50 $LOG_FILE${NC}"
        rm -f "$PID_FILE"
        return 1
    fi
}

# 查看状态
show_status() {
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}    代理服务器状态${NC}"
    echo -e "${GREEN}========================================${NC}"
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}状态: 运行中${NC}"
            echo -e "PID: $PID"
            
            # 检查端口
            if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null 2>&1; then
                echo -e "REST API: ${GREEN}运行中${NC} (http://localhost:8080)"
            else
                echo -e "REST API: ${RED}未监听${NC}"
            fi
            
            if lsof -Pi :8765 -sTCP:LISTEN -t >/dev/null 2>&1; then
                echo -e "WebSocket: ${GREEN}运行中${NC} (ws://localhost:8765)"
            else
                echo -e "WebSocket: ${RED}未监听${NC}"
            fi
            
            # 显示最近的日志
            echo ""
            echo -e "${YELLOW}最近的日志:${NC}"
            tail -20 "$LOG_FILE" 2>/dev/null || echo "日志文件不存在"
        else
            echo -e "${RED}状态: 未运行${NC}"
            echo -e "${YELLOW}PID文件存在但进程不存在，清理中...${NC}"
            rm -f "$PID_FILE"
        fi
    else
        echo -e "${RED}状态: 未运行${NC}"
    fi
}

# 主函数
main() {
    case "${1:-start}" in
        start)
            start_proxy_server
            ;;
        stop)
            stop_proxy_server
            ;;
        restart)
            stop_proxy_server
            sleep 2
            start_proxy_server
            ;;
        status)
            show_status
            ;;
        *)
            echo "用法: $0 {start|stop|restart|status}"
            echo ""
            echo "命令:"
            echo "  start   - 启动代理服务器"
            echo "  stop    - 停止代理服务器"
            echo "  restart - 重启代理服务器"
            echo "  status  - 查看服务器状态"
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
