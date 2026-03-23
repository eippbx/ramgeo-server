#!/usr/bin/env python3
"""
RAMGEO计算节点服务
连接到代理服务器，执行RAMGEO计算任务
"""

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import websockets
import psutil
import GPUtil

from shared.config import Config
from shared.logger import setup_logging
from shared.metrics import NodeMetricsCollector
from shared.security import SecurityManager
from shared.exceptions import NodeError, TaskError

# 导入节点模块
from node_server.websocket_client import WebSocketClient
from node_server.task_executor import TaskExecutor
from node_server.resource_monitor import ResourceMonitor
from node_server.file_handler import FileHandler

logger = setup_logging(__name__)

class NodeServer:
    """计算节点服务器"""
    
    def __init__(self, config_path: str = None):
        self.config = Config(config_path)
        self.node_id = self.config.get('node.id') or self._generate_node_id()
        self.node_name = self.config.get('node.name') or f"node-{self.node_id[:8]}"
        
        # 服务组件
        self.ws_client = None
        self.task_executor = None
        self.resource_monitor = None
        self.file_handler = None
        self.security = None
        self.metrics = None
        
        # 状态管理
        self.status = 'initializing'
        self.capabilities = {}
        self.active_tasks = {}
        self.shutdown_event = asyncio.Event()
        
        # 代理服务器连接信息
        self.proxy_url = self.config.get('proxy.ws_url', 'ws://localhost:8080/ws')
        self.auth_token = self.config.get('node.auth_token')
        
        # 工作目录
        self.work_dir = Path(self.config.get('node.work_dir', '/var/ramgeo/workspace'))
        self.work_dir.mkdir(parents=True, exist_ok=True)
    
    def _generate_node_id(self) -> str:
        """生成节点ID"""
        hostname = os.uname().nodename
        return f"{hostname}-{uuid.uuid4().hex[:8]}"
    
    async def initialize(self):
        """初始化节点"""
        logger.info(f"初始化计算节点: {self.node_name} ({self.node_id})")
        
        # 初始化安全模块
        self.security = SecurityManager(self.config)
        
        # 初始化指标收集器
        self.metrics = NodeMetricsCollector(self.node_id)
        
        # 获取节点能力
        await self._discover_capabilities()
        
        # 初始化文件处理器
        self.file_handler = FileHandler(
            config=self.config,
            work_dir=self.work_dir,
            security=self.security
        )
        
        # 初始化任务执行器
        self.task_executor = TaskExecutor(
            config=self.config,
            file_handler=self.file_handler,
            metrics=self.metrics,
            node_id=self.node_id
        )
        
        # 初始化资源监控器
        self.resource_monitor = ResourceMonitor(
            config=self.config,
            metrics=self.metrics
        )
        
        # 初始化WebSocket客户端
        self.ws_client = WebSocketClient(
            config=self.config,
            node_id=self.node_id,
            node_name=self.node_name,
            capabilities=self.capabilities,
            auth_token=self.auth_token,
            proxy_url=self.proxy_url,
            task_executor=self.task_executor,
            resource_monitor=self.resource_monitor
        )
        
        self.status = 'initialized'
        logger.info("节点初始化完成")
    
    async def _discover_capabilities(self):
        """发现节点能力"""
        logger.info("发现节点能力...")
        
        # 获取系统信息
        cpu_cores = psutil.cpu_count(logical=False) or 1
        memory_gb = psutil.virtual_memory().total / (1024**3)
        
        # 检查RAMGEO安装
        ramgeo_path = self.config.get('node.ramgeo_path', '/usr/sbin/ramgeo')
        ramgeo_version = '1.0'
        
        if os.path.exists(ramgeo_path):
            try:
                result = subprocess.run(
                    [ramgeo_path, '--version'],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    version_line = result.stdout.strip()
                    # 解析版本号
                    import re
                    match = re.search(r'(\d+\.\d+\.\d+)', version_line)
                    if match:
                        ramgeo_version = match.group(1)
            except Exception as e:
                logger.warning(f"获取RAMGEO版本失败: {e}")
        
        # 检查GPU
        gpu_info = []
        try:
            gpus = GPUtil.getGPUs()
            for gpu in gpus:
                gpu_info.append({
                    'id': gpu.id,
                    'name': gpu.name,
                    'memory_total': gpu.memoryTotal,
                    'memory_free': gpu.memoryFree
                })
        except Exception as e:
            logger.warning(f"获取GPU信息失败: {e}")
        
        # 构建能力信息
        self.capabilities = {
            'ramgeo_version': ramgeo_version,
            'ramgeo_path': ramgeo_path,
            'cpu_cores': cpu_cores,
            'memory_gb': round(memory_gb, 2),
            'gpus': gpu_info,
            'max_tasks': self.config.get('node.max_tasks', 5),
            'max_file_size': self.config.get('node.max_file_size', 100 * 1024 * 1024),
            'supported_formats': ['ramgeo.in'],
            'node_type': 'high_performance' if cpu_cores >= 8 else 'general',
            'special_capabilities': ['gpu'] if gpu_info else []
        }
        
        logger.info(f"节点能力: CPU={cpu_cores}核, 内存={memory_gb:.1f}GB, RAMGEO={ramgeo_version}")
    
    async def start(self):
        """启动节点服务"""
        logger.info("启动节点服务...")
        
        try:
            # 设置信号处理
            for sig in (signal.SIGINT, signal.SIGTERM):
                asyncio.get_event_loop().add_signal_handler(
                    sig, lambda: asyncio.create_task(self.shutdown())
                )
            
            # 启动资源监控
            await self.resource_monitor.start()
            
            # 连接到代理服务器
            await self.ws_client.connect()
            
            # 启动心跳
            asyncio.create_task(self._heartbeat_loop())
            
            # 启动状态报告
            asyncio.create_task(self._status_report_loop())
            
            self.status = 'running'
            logger.info(f"节点服务启动成功，连接到: {self.proxy_url}")
            
            # 等待关闭事件
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"节点服务启动失败: {e}")
            raise
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        while not self.shutdown_event.is_set():
            try:
                await self.ws_client.send_heartbeat()
                await asyncio.sleep(30)  # 每30秒发送一次心跳
            except Exception as e:
                logger.error(f"心跳发送失败: {e}")
                # 尝试重新连接
                await self._reconnect()
    
    async def _status_report_loop(self):
        """状态报告循环"""
        while not self.shutdown_event.is_set():
            try:
                # 收集系统指标
                system_metrics = await self.resource_monitor.collect_metrics()
                
                # 构建状态报告
                status_report = {
                    'status': self.status,
                    'metrics': system_metrics,
                    'active_tasks': len(self.active_tasks),
                    'capabilities': self.capabilities,
                    'timestamp': datetime.now().isoformat()
                }
                
                # 发送状态报告
                await self.ws_client.send_status_report(status_report)
                
                await asyncio.sleep(10)  # 每10秒报告一次
                
            except Exception as e:
                logger.error(f"状态报告失败: {e}")
    
    async def _reconnect(self):
        """重新连接到代理服务器"""
        logger.info("尝试重新连接到代理服务器...")
        
        retry_count = 0
        max_retries = self.config.get('node.max_retries', 5)
        retry_delay = self.config.get('node.retry_delay', 5)
        
        while retry_count < max_retries and not self.shutdown_event.is_set():
            try:
                await self.ws_client.disconnect()
                await asyncio.sleep(retry_delay)
                await self.ws_client.connect()
                logger.info("重新连接成功")
                return
            except Exception as e:
                retry_count += 1
                logger.error(f"重新连接失败 ({retry_count}/{max_retries}): {e}")
                await asyncio.sleep(retry_delay * retry_count)
        
        logger.error("重新连接失败，达到最大重试次数")
        await self.shutdown()
    
    async def shutdown(self):
        """优雅关闭节点"""
        logger.info("开始关闭节点服务...")
        
        self.shutdown_event.set()
        self.status = 'shutting_down'
        
        # 停止所有任务
        if self.task_executor:
            await self.task_executor.stop_all_tasks()
        
        # 断开WebSocket连接
        if self.ws_client:
            await self.ws_client.disconnect()
        
        # 停止资源监控
        if self.resource_monitor:
            await self.resource_monitor.stop()
        
        # 清理工作目录
        if self.file_handler:
            await self.file_handler.cleanup()
        
        self.status = 'stopped'
        logger.info("节点服务关闭完成")
        
        # 退出程序
        sys.exit(0)

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='RAMGEO计算节点服务')
    parser.add_argument('--config', '-c', help='配置文件路径')
    parser.add_argument('--proxy', '-p', help='代理服务器URL')
    parser.add_argument('--token', '-t', help='认证令牌')
    parser.add_argument('--id', help='节点ID')
    parser.add_argument('--name', help='节点名称')
    
    args = parser.parse_args()
    
    # 创建节点服务器
    server = NodeServer(args.config)
    
    # 覆盖配置
    if args.proxy:
        server.proxy_url = args.proxy
    if args.token:
        server.auth_token = args.token
    if args.id:
        server.node_id = args.id
    if args.name:
        server.node_name = args.name
    
    try:
        await server.initialize()
        await server.start()
    except KeyboardInterrupt:
        logger.info("接收到中断信号")
    except Exception as e:
        logger.error(f"节点服务运行失败: {e}")
        raise
    finally:
        await server.shutdown()

if __name__ == '__main__':
    # 设置事件循环策略
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行主程序
    asyncio.run(main())