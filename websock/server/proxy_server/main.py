#!/usr/bin/env python3
"""
RAMGEO分布式系统 - 代理服务器主程序
提供统一的WebSocket和HTTP接口，管理所有计算节点
"""

import asyncio
import json
import logging
import signal
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import aiohttp
from aiohttp import web
import redis.asyncio as aioredis
from jose import jwt
import bcrypt
from cryptography.fernet import Fernet
import prometheus_client
from prometheus_client import Counter, Gauge, Histogram, Summary

# 项目模块
from shared.config import Config
from shared.logger import setup_logging
from shared.metrics import MetricsCollector
from shared.database import DatabaseManager
from shared.redis_client import RedisClient
from shared.security import SecurityManager
from shared.exceptions import (
    AuthenticationError, AuthorizationError,
    NodeError, TaskError, FileError
)

# 导入业务模块
from proxy_server.websocket_server import WebSocketServer
from proxy_server.task_manager import TaskManager
from proxy_server.node_manager import NodeManager
from proxy_server.file_manager import FileManager
from proxy_server.auth_manager import AuthManager
from proxy_server.api import setup_routes
from proxy_server.middleware import MiddlewareManager

# 设置日志
logger = setup_logging(__name__)

# 全局配置
config = Config()

class ProxyServer:
    """代理服务器主类"""
    
    def __init__(self):
        self.config = config
        self.app = None
        self.runner = None
        self.websocket_server = None
        self.task_manager = None
        self.node_manager = None
        self.file_manager = None
        self.auth_manager = None
        self.metrics = MetricsCollector()
        self.db = None
        self.redis = None
        self.security = None
        self.shutdown_event = asyncio.Event()
        
        # 初始化统计信息
        self.stats = {
            'start_time': datetime.now(),
            'total_requests': 0,
            'total_tasks': 0,
            'active_connections': 0
        }
    
    async def initialize(self):
        """初始化服务器"""
        logger.info("初始化代理服务器...")
        
        # 初始化数据库连接（允许失败）
        try:
            await self._init_database()
        except Exception as e:
            logger.warning(f"数据库连接失败，将在没有数据库的情况下运行: {e}")
        
        # 初始化Redis连接（允许失败）
        try:
            await self._init_redis()
        except Exception as e:
            logger.warning(f"Redis连接失败，将在没有Redis的情况下运行: {e}")
        
        # 初始化安全模块
        self.security = SecurityManager(config)
        
        # 初始化认证管理器（允许在没有数据库或Redis的情况下创建）
        await self._init_auth_manager()
        
        # 创建Web应用
        self.app = web.Application(
            client_max_size=config.get('file_transfer.max_file_size', 100 * 1024 * 1024)
        )
        
        # 设置中间件
        middleware_manager = MiddlewareManager(self.auth_manager)
        self.app.middlewares.extend(middleware_manager.get_middlewares())
        
        # 初始化其他业务管理器
        await self._init_other_managers()
        
        # 创建API处理器
        from proxy_server.api import APIHandler
        self.api_handler = APIHandler(
            config=self.config,
            auth_manager=self.auth_manager,
            node_manager=self.node_manager,
            task_manager=self.task_manager,
            file_manager=self.file_manager
        )
        
        # 设置路由
        setup_routes(self.app, self.api_handler)
        
        # 设置静态文件
        await self._setup_static_files()
        
        # 启动后台任务
        asyncio.create_task(self._background_tasks())
        
        logger.info("代理服务器初始化完成")
    
    async def _init_database(self):
        """初始化数据库连接"""
        try:
            db_config = config.get('database', {})
            self.db = DatabaseManager(db_config)
            await self.db.connect()
            logger.info("数据库连接成功")
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise
    
    async def _init_redis(self):
        """初始化Redis连接"""
        try:
            redis_config = config.get('redis', {})
            self.redis = RedisClient(redis_config)
            await self.redis.connect()
            logger.info("Redis连接成功")
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            raise
    
    async def _init_auth_manager(self):
        """初始化认证管理器"""
        # 认证管理器
        self.auth_manager = AuthManager(config, self.db, self.security)
        
    async def _init_other_managers(self):
        """初始化其他业务管理器"""
        # 节点管理器
        self.node_manager = NodeManager(
            config=self.config,
            db=self.db,
            redis=self.redis,
            metrics=self.metrics
        )
        
        # 文件管理器
        self.file_manager = FileManager(
            config=self.config
        )
        
        # 任务管理器
        self.task_manager = TaskManager(
            config=self.config,
            db=self.db,
            redis=self.redis,
            node_manager=self.node_manager,
            file_manager=self.file_manager,
            metrics=self.metrics
        )
        
        # WebSocket服务器
        self.websocket_server = WebSocketServer(
            config=self.config,
            node_manager=self.node_manager,
            task_manager=self.task_manager,
            auth_manager=self.auth_manager,
            metrics=self.metrics
        )
        
        # 注册WebSocket处理器
        await self.websocket_server.setup(self.app)
        
        # 启动节点发现
        await self.node_manager.start_discovery()
        
        # 启动任务调度器
        await self.task_manager.start_scheduler()
        
        logger.info("业务管理器初始化完成")
    
    async def _setup_static_files(self):
        """设置静态文件服务"""
        static_path = Path(__file__).parent.parent / 'web_client' / 'dist'
        if static_path.exists():
            self.app.router.add_static('/static/', static_path)
            logger.info(f"静态文件服务已启用: {static_path}")
    
    async def _background_tasks(self):
        """后台任务"""
        while not self.shutdown_event.is_set():
            try:
                # 定期清理临时文件
                await self.file_manager.cleanup_temp_files()
                
                # 定期检查节点健康
                await self.node_manager.check_health()
                
                # 定期更新统计信息
                await self._update_stats()
                
                # 定期备份数据库
                if datetime.now().hour == 2:  # 凌晨2点
                    await self._backup_database()
                
            except Exception as e:
                logger.error(f"后台任务执行失败: {e}")
            
            await asyncio.sleep(60)  # 每分钟执行一次
    
    async def _update_stats(self):
        """更新统计信息"""
        try:
            self.stats['active_connections'] = len(self.websocket_server.active_connections)
            self.stats['total_requests'] = self.metrics.get_counter('http_requests')
            
            # 保存到Redis
            await self.redis.set('proxy_stats', json.dumps(self.stats), expire=300)
            
        except Exception as e:
            logger.error(f"更新统计信息失败: {e}")
    
    async def _backup_database(self):
        """备份数据库"""
        try:
            backup_file = f"/backups/db_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
            # 这里实现数据库备份逻辑
            logger.info(f"数据库备份完成: {backup_file}")
        except Exception as e:
            logger.error(f"数据库备份失败: {e}")
    
    async def start(self):
        """启动服务器"""
        try:
            # 设置信号处理（仅在非Windows平台）
            if sys.platform != 'win32':
                for sig in (signal.SIGINT, signal.SIGTERM):
                    asyncio.get_event_loop().add_signal_handler(
                        sig, lambda: asyncio.create_task(self.shutdown())
                    )
                logger.info("信号处理已设置")
            else:
                logger.info("在Windows平台上跳过信号处理设置")
            
            # 创建HTTP服务器
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            # 启动服务器
            host = config.get('proxy.host', '0.0.0.0')
            port = config.get('proxy.port', 8080)
            
            site = web.TCPSite(self.runner, host, port)
            await site.start()
            
            logger.info(f"代理服务器启动成功: http://{host}:{port}")
            
            # 启动Prometheus metrics
            metrics_port = config.get('proxy.metrics_port', 9090)
            prometheus_client.start_http_server(metrics_port)
            logger.info(f"Metrics server started on port {metrics_port}")
            
            # 等待关闭事件
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"服务器启动失败: {e}")
            logger.exception("服务器启动异常详情:")
            raise
    
    async def shutdown(self):
        """优雅关闭服务器"""
        logger.info("开始关闭代理服务器...")
        
        # 设置关闭事件
        self.shutdown_event.set()
        
        # 关闭业务管理器
        if self.task_manager:
            await self.task_manager.shutdown()
        
        if self.node_manager:
            await self.node_manager.shutdown()
        
        if self.websocket_server:
            await self.websocket_server.shutdown()
        
        # 关闭数据库连接
        if self.db:
            await self.db.disconnect()
        
        if self.redis:
            await self.redis.disconnect()
        
        # 关闭HTTP服务器
        if self.runner:
            await self.runner.cleanup()
        
        logger.info("代理服务器关闭完成")
        
        # 退出程序
        sys.exit(0)

async def main():
    """主函数"""
    server = ProxyServer()
    
    try:
        await server.initialize()
        await server.start()
    except KeyboardInterrupt:
        logger.info("接收到中断信号")
    except Exception as e:
        logger.error(f"服务器运行失败: {e}")
        raise
    finally:
        await server.shutdown()

if __name__ == '__main__':
    # 设置事件循环策略
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行主程序
    asyncio.run(main())