#!/usr/bin/env python3
"""
WebSocket客户端模块
实现与代理服务器的WebSocket通信
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Callable

import websockets

from shared.logger import setup_logging
from shared.exceptions import *
from shared.security import SecurityManager

logger = setup_logging(__name__)


class WebSocketClient:
    """
    WebSocket客户端类
    """
    
    def __init__(self, config: Dict[str, Any], security_manager: SecurityManager):
        """
        初始化WebSocket客户端
        
        Args:
            config: 配置信息
            security_manager: 安全管理器实例
        """
        self.config = config
        self.security_manager = security_manager
        
        # WebSocket连接信息
        self.ws_uri = config.get('node_server.proxy', {}).get('websocket_uri', 'ws://localhost:8765')
        self.api_key = config.get('node_server.proxy', {}).get('api_key')
        
        # 节点信息
        self.node_id = config.get('node_server', {}).get('id')
        self.node_name = config.get('node_server', {}).get('name', f'node-{self.node_id}')
        self.node_type = config.get('node_server', {}).get('type', 'cpu')
        self.max_workers = config.get('node_server', {}).get('max_workers', 4)
        
        # WebSocket连接
        self.websocket = None
        self.is_connected = False
        self.connection_task = None
        
        # 消息处理器
        self.message_handlers = {
            'task_assigned': self.handle_task_assigned,
            'task_cancel': self.handle_task_cancel,
            'node_command': self.handle_node_command,
        }
        
        # 心跳相关
        self.heartbeat_interval = config.get('node_server.proxy', {}).get('heartbeat_interval', 30)
        self.last_heartbeat = 0
        self.heartbeat_task = None
        
        # 重连相关
        self.reconnect_interval = config.get('node_server.proxy', {}).get('reconnect_interval', 5)
        self.max_reconnect_attempts = config.get('node_server.proxy', {}).get('max_reconnect_attempts', 10)
        self.reconnect_attempts = 0
        
        # 任务执行回调
        self.task_execution_callback = None
        
        logger.info(f"WebSocket客户端初始化完成，节点ID: {self.node_id}，代理服务器URI: {self.ws_uri}")
    
    async def connect(self) -> bool:
        """
        连接到代理服务器
        
        Returns:
            连接是否成功
        """
        try:
            # 创建WebSocket连接
            self.websocket = await websockets.connect(
                self.ws_uri,
                extra_headers={'X-API-Key': self.api_key}
            )
            
            self.is_connected = True
            self.reconnect_attempts = 0
            
            logger.info(f"WebSocket连接成功: {self.ws_uri}")
            
            # 开始接收消息
            self.connection_task = asyncio.create_task(self.receive_messages())
            
            # 开始心跳任务
            self.heartbeat_task = asyncio.create_task(self.send_heartbeat())
            
            # 注册节点
            await self.register_node()
            
            return True
            
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self) -> None:
        """
        断开与代理服务器的连接
        """
        try:
            # 取消所有任务
            if self.connection_task:
                self.connection_task.cancel()
                await asyncio.wait([self.connection_task], timeout=5)
            
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
                await asyncio.wait([self.heartbeat_task], timeout=5)
            
            # 关闭WebSocket连接
            if self.websocket and self.is_connected:
                await self.websocket.close()
                logger.info(f"WebSocket连接已关闭")
            
            self.is_connected = False
            self.websocket = None
            
        except Exception as e:
            logger.error(f"断开WebSocket连接失败: {e}")
    
    async def reconnect(self) -> None:
        """
        重新连接到代理服务器
        """
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error(f"达到最大重连尝试次数 ({self.max_reconnect_attempts})，停止重连")
            return
        
        self.reconnect_attempts += 1
        
        logger.info(f"正在尝试第 {self.reconnect_attempts} 次重连...")
        
        # 等待一段时间后重连
        await asyncio.sleep(self.reconnect_interval)
        
        # 尝试连接
        success = await self.connect()
        
        if not success:
            # 继续重连
            await self.reconnect()
    
    async def receive_messages(self) -> None:
        """
        接收来自代理服务器的消息
        """
        try:
            while self.is_connected:
                # 接收消息
                message = await self.websocket.recv()
                
                logger.debug(f"接收到消息: {message}")
                
                # 解析消息
                try:
                    data = json.loads(message)
                    await self.handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"解析消息失败: {e}")
                    
        except websockets.ConnectionClosed as e:
            logger.error(f"WebSocket连接关闭: {e}")
            self.is_connected = False
            await self.reconnect()
        except Exception as e:
            logger.error(f"接收消息时发生错误: {e}")
            self.is_connected = False
            await self.reconnect()
    
    async def handle_message(self, message: Dict[str, Any]) -> None:
        """
        处理接收到的消息
        
        Args:
            message: 消息内容
        """
        try:
            # 获取消息类型
            message_type = message.get('type')
            
            if not message_type:
                logger.warning(f"接收到无效消息（缺少类型）: {message}")
                return
            
            # 获取消息处理器
            handler = self.message_handlers.get(message_type)
            
            if handler:
                await handler(message)
            else:
                logger.warning(f"未找到消息处理器: {message_type}")
                
        except Exception as e:
            logger.error(f"处理消息时发生错误: {e}")
    
    async def handle_task_assigned(self, message: Dict[str, Any]) -> None:
        """
        处理任务分配消息
        
        Args:
            message: 消息内容
        """
        try:
            task_info = message.get('data', {})
            logger.info(f"接收到任务分配: {task_info}")
            
            # 调用任务执行回调
            if self.task_execution_callback:
                await self.task_execution_callback(task_info)
            
            # 发送任务接收确认
            await self.send_message({
                'type': 'task_received',
                'data': {
                    'task_id': task_info.get('id'),
                    'status': 'received'
                }
            })
            
        except Exception as e:
            logger.error(f"处理任务分配消息时发生错误: {e}")
    
    async def handle_task_cancel(self, message: Dict[str, Any]) -> None:
        """
        处理任务取消消息
        
        Args:
            message: 消息内容
        """
        try:
            task_info = message.get('data', {})
            task_id = task_info.get('task_id')
            
            logger.info(f"接收到任务取消命令: {task_id}")
            
            # 调用任务执行回调进行取消操作
            if self.task_execution_callback:
                await self.task_execution_callback({'id': task_id, 'action': 'cancel'})
            
            # 发送任务取消确认
            await self.send_message({
                'type': 'task_cancelled',
                'data': {
                    'task_id': task_id,
                    'status': 'cancelled'
                }
            })
            
        except Exception as e:
            logger.error(f"处理任务取消消息时发生错误: {e}")
    
    async def handle_node_command(self, message: Dict[str, Any]) -> None:
        """
        处理节点命令消息
        
        Args:
            message: 消息内容
        """
        try:
            command_info = message.get('data', {})
            command = command_info.get('command')
            
            logger.info(f"接收到节点命令: {command}")
            
            # 处理不同的命令
            if command == 'shutdown':
                # 关闭节点服务
                logger.info("接收到关闭命令，准备关闭节点服务")
                # TODO: 实现节点关闭逻辑
                
            elif command == 'restart':
                # 重启节点服务
                logger.info("接收到重启命令，准备重启节点服务")
                # TODO: 实现节点重启逻辑
                
            elif command == 'update':
                # 更新节点服务
                logger.info("接收到更新命令，准备更新节点服务")
                # TODO: 实现节点更新逻辑
                
            elif command == 'status':
                # 发送节点状态
                await self.send_node_status()
                
            # 发送命令执行确认
            await self.send_message({
                'type': 'command_executed',
                'data': {
                    'command': command,
                    'status': 'success'
                }
            })
            
        except Exception as e:
            logger.error(f"处理节点命令消息时发生错误: {e}")
    
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """
        发送消息到代理服务器
        
        Args:
            message: 消息内容
        
        Returns:
            发送是否成功
        """
        try:
            if not self.is_connected or not self.websocket:
                logger.warning("WebSocket未连接，无法发送消息")
                return False
            
            # 添加节点信息
            message['node_id'] = self.node_id
            message['timestamp'] = int(time.time())
            
            # 发送消息
            await self.websocket.send(json.dumps(message))
            
            logger.debug(f"发送消息成功: {message}")
            return True
            
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False
    
    async def register_node(self) -> None:
        """
        注册节点到代理服务器
        """
        try:
            # 构建节点注册消息
            register_message = {
                'type': 'node_register',
                'data': {
                    'node_id': self.node_id,
                    'node_name': self.node_name,
                    'node_type': self.node_type,
                    'max_workers': self.max_workers,
                    'status': 'online',
                    'capabilities': await self.get_node_capabilities(),
                }
            }
            
            # 发送注册消息
            await self.send_message(register_message)
            
            logger.info("节点注册请求已发送")
            
        except Exception as e:
            logger.error(f"注册节点失败: {e}")
    
    async def get_node_capabilities(self) -> Dict[str, Any]:
        """
        获取节点能力信息
        
        Returns:
            节点能力信息
        """
        import psutil
        import platform
        
        try:
            # 获取CPU信息
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq().current if psutil.cpu_freq() else 0
            
            # 获取内存信息
            mem = psutil.virtual_memory()
            memory_total = mem.total
            
            # 获取磁盘信息
            disk = psutil.disk_usage('/')
            disk_total = disk.total
            
            # 获取系统信息
            system_info = {
                'os': platform.system(),
                'os_version': platform.version(),
                'architecture': platform.architecture()[0],
                'python_version': platform.python_version(),
            }
            
            return {
                'cpu': {
                    'count': cpu_count,
                    'frequency': cpu_freq
                },
                'memory': {
                    'total': memory_total
                },
                'disk': {
                    'total': disk_total
                },
                'system': system_info,
                'supported_tasks': ['dem', 'image_processing', 'calculation']
            }
            
        except Exception as e:
            logger.error(f"获取节点能力信息失败: {e}")
            return {}
    
    async def send_heartbeat(self) -> None:
        """
        发送心跳消息
        """
        try:
            while self.is_connected:
                # 检查是否需要发送心跳
                current_time = time.time()
                if current_time - self.last_heartbeat >= self.heartbeat_interval:
                    # 构建心跳消息
                    heartbeat_message = {
                        'type': 'node_heartbeat',
                        'data': {
                            'node_id': self.node_id,
                            'status': 'online',
                            'timestamp': int(current_time),
                            'resource_usage': await self.get_resource_usage()
                        }
                    }
                    
                    # 发送心跳消息
                    await self.send_message(heartbeat_message)
                    
                    self.last_heartbeat = current_time
                    
                # 等待一段时间
                await asyncio.sleep(self.heartbeat_interval)
                
        except Exception as e:
            logger.error(f"发送心跳消息时发生错误: {e}")
    
    async def get_resource_usage(self) -> Dict[str, Any]:
        """
        获取节点资源使用情况
        
        Returns:
            节点资源使用情况
        """
        import psutil
        
        try:
            # CPU使用率
            cpu_usage = psutil.cpu_percent(interval=0.1)
            
            # 内存使用率
            mem = psutil.virtual_memory()
            memory_usage = mem.percent
            
            # 磁盘使用率
            disk = psutil.disk_usage('/')
            disk_usage = disk.percent
            
            # 获取正在运行的进程数
            process_count = len(psutil.pids())
            
            return {
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage,
                'disk_usage': disk_usage,
                'process_count': process_count
            }
            
        except Exception as e:
            logger.error(f"获取资源使用情况失败: {e}")
            return {}
    
    async def send_node_status(self) -> None:
        """
        发送节点状态信息
        """
        try:
            # 构建节点状态消息
            status_message = {
                'type': 'node_status',
                'data': {
                    'node_id': self.node_id,
                    'status': 'online' if self.is_connected else 'offline',
                    'timestamp': int(time.time()),
                    'resource_usage': await self.get_resource_usage(),
                    'capabilities': await self.get_node_capabilities()
                }
            }
            
            # 发送状态消息
            await self.send_message(status_message)
            
            logger.debug("节点状态信息已发送")
            
        except Exception as e:
            logger.error(f"发送节点状态信息失败: {e}")
    
    async def send_task_status(self, task_id: str, status: str, result: Optional[Dict[str, Any]] = None) -> None:
        """
        发送任务状态信息
        
        Args:
            task_id: 任务ID
            status: 任务状态
            result: 任务结果（可选）
        """
        try:
            # 构建任务状态消息
            task_status_message = {
                'type': 'task_status',
                'data': {
                    'node_id': self.node_id,
                    'task_id': task_id,
                    'status': status,
                    'timestamp': int(time.time()),
                    'result': result
                }
            }
            
            # 发送任务状态消息
            await self.send_message(task_status_message)
            
            logger.debug(f"任务状态信息已发送: 任务ID={task_id}, 状态={status}")
            
        except Exception as e:
            logger.error(f"发送任务状态信息失败: {e}")
    
    def set_task_execution_callback(self, callback: Callable) -> None:
        """
        设置任务执行回调函数
        
        Args:
            callback: 回调函数
        """
        self.task_execution_callback = callback
    
    async def close(self) -> None:
        """
        关闭WebSocket客户端
        """
        logger.info("正在关闭WebSocket客户端...")
        
        # 发送节点离线消息
        if self.is_connected:
            await self.send_message({
                'type': 'node_offline',
                'data': {
                    'node_id': self.node_id,
                    'timestamp': int(time.time())
                }
            })
        
        # 断开连接
        await self.disconnect()
        
        logger.info("WebSocket客户端已关闭")
