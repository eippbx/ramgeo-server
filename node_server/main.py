#!/usr/bin/env python3
"""
节点服务器主程序入口
"""

import asyncio
import logging
import logging.handlers
import os
import sys

# 添加src目录到Python路径
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from config import Config
from node_server import NodeServer

def setup_logging(config):
    """设置日志配置"""
    log_dir = config.get('runtime.log_dir')
    log_level = config.get('logging.level', 'INFO')
    max_file_size = config.get('logging.max_file_size', 10) * 1024 * 1024  # MB转字节
    backup_count = config.get('logging.backup_count', 5)
    
    # 确保日志目录存在
    os.makedirs(log_dir, exist_ok=True)
    
    # 设置日志格式
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 配置根日志记录器
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # 控制台日志处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_formatter = logging.Formatter(log_format)
    console_handler.setFormatter(console_formatter)
    
    # 文件日志处理器
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'node_server.log'),
        maxBytes=max_file_size,
        backupCount=backup_count
    )
    file_handler.setLevel(getattr(logging, log_level.upper()))
    file_formatter = logging.Formatter(log_format)
    file_handler.setFormatter(file_formatter)
    
    # 添加处理器到根日志记录器
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

async def main():
    """主函数"""
    try:
        # 加载配置
        config = Config()
        
        # 设置日志
        setup_logging(config)
        
        # 创建节点服务器实例
        node_server = NodeServer()
        
        # 启动节点服务器
        await node_server.start()
        
    except KeyboardInterrupt:
        logging.info("接收到键盘中断，正在停止节点服务器")
        await node_server.stop()
    except Exception as e:
        logging.error(f"节点服务器启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
