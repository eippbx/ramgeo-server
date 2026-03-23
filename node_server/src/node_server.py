import asyncio
import logging
import os
import hashlib
import base64
from datetime import datetime

import config
import websocket_client
import task
import resource_monitor

# 使用绝对导入
Config = config.Config
WebSocketClient = websocket_client.WebSocketClient
Task = task.Task
ResourceMonitor = resource_monitor.ResourceMonitor

logger = logging.getLogger(__name__)

class NodeServer:
    """节点服务器，负责与代理服务器通信、管理任务执行、监控资源等"""
    
    def __init__(self, config_file_path=None):
        """
        初始化节点服务器
        
        Args:
            config_file_path: 配置文件路径
        """
        # 加载配置
        self.config = Config(config_file_path)
        
        # 节点信息
        self.node_id = self.config.get('node.node_id')
        self.node_name = self.config.get('node.node_name', '')
        self.node_description = self.config.get('node.description', '')
        
        # 资源监控器
        self.resource_monitor = ResourceMonitor()
        
        # 运行状态
        self.is_registered = False
        self.current_tasks = {}  # task_id: Task object
        self.max_tasks = self.config.get('runtime.max_tasks')
        self.is_running = False
        
        # 初始化WebSocket客户端
        self.ws_client = WebSocketClient(self.config, self.handle_message)
        # 设置连接成功后的回调函数
        self.ws_client.on_connect_callback = self.send_register_message
        # 设置断开连接后的回调函数
        self.ws_client.on_disconnect_callback = self.on_disconnect
        
        logger.info(f"节点服务器初始化完成: {self.node_id}")
    
    async def start(self):
        """启动节点服务器"""
        logger.info(f"启动节点服务器: {self.node_id}")
        self.is_running = True
        
        # 启动WebSocket客户端
        await self.ws_client.run()
    
    async def stop(self):
        """停止节点服务器"""
        logger.info(f"停止节点服务器: {self.node_id}")
        self.is_running = False
        
        # 关闭WebSocket连接
        await self.ws_client.disconnect()
        
        # 等待所有任务完成
        if self.current_tasks:
            logger.info(f"等待任务完成: {len(self.current_tasks)}个任务")
            await asyncio.sleep(5)
    
    async def handle_message(self, message):
        """
        处理从代理服务器收到的消息
        
        Args:
            message: 消息字典
        """
        message_type = message.get('type')
        
        if message_type == 'register_response':
            await self.handle_register_response(message)
        elif message_type == 'heartbeat':
            await self.handle_heartbeat(message)
        elif message_type == 'task_assign':
            await self.handle_task_assign(message)
        elif message_type == 'file_transfer':
            await self.handle_file_transfer(message)
        elif message_type == 'chunk_received':
            await self.handle_chunk_received(message)
        elif message_type == 'task_cancel':
            await self.handle_task_cancel(message)
        elif message_type == 'shutdown':
            await self.handle_shutdown(message)
        else:
            logger.warning(f"未知消息类型: {message_type}")
    
    async def send_register_message(self):
        """发送注册消息"""
        # 等待一小段时间，确保代理服务器准备好接收注册消息
        await asyncio.sleep(0.5)
        
        register_message = {
            'type': 'register',
            'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'node_id': self.node_id,
            'node_name': self.node_name,
            'capabilities': self.resource_monitor.get_capabilities(self.max_tasks)
        }
        
        logger.info(f"发送注册消息: {self.node_id}")
        await self.ws_client.send_message(register_message)
    
    async def handle_register_response(self, message):
        """
        处理注册响应
        
        Args:
            message: 注册响应消息
        """
        status = message.get('status')
        node_id = message.get('node_id')
        
        if status == 'registered' and node_id == self.node_id:
            self.is_registered = True
            logger.info(f"节点注册成功: {self.node_id}")
            
            # 注册成功后，开始定期发送状态报告
            asyncio.create_task(self.send_status_reports())
        else:
            logger.error(f"节点注册失败: {message.get('message', '未知错误')}")
    
    async def handle_heartbeat(self, message):
        """
        处理心跳消息
        
        Args:
            message: 心跳消息
        """
        heartbeat_response = {
            'type': 'heartbeat_response',
            'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        }
        
        await self.ws_client.send_message(heartbeat_response)
        logger.debug("心跳响应已发送")
    
    async def on_disconnect(self):
        """WebSocket连接断开时的回调"""
        logger.warning("WebSocket连接已断开，重置注册状态")
        self.is_registered = False
    
    async def handle_task_assign(self, message):
        """
        处理任务分配
        
        Args:
            message: 任务分配消息
        """
        task_id = message.get('task_id')
        task_data = message.get('data', {})
        
        logger.info(f"收到任务分配: {task_id}")
        
        # 检查是否有可用的任务槽位
        if len(self.current_tasks) >= self.max_tasks:
            logger.warning(f"任务槽位已满，拒绝任务: {task_id}")
            # TODO: 发送任务拒绝消息
            return
        
        # 创建任务对象
        task_obj = Task(task_id, task_data, self)
        self.current_tasks[task_id] = task_obj
        
        # 启动任务执行
        asyncio.create_task(task_obj.start())
    
    async def handle_file_transfer(self, message):
        """
        处理文件传输
        
        Args:
            message: 文件传输消息
        """
        transfer_id = message.get('transfer_id')
        chunk = message.get('chunk')
        index = message.get('index')
        total_chunks = message.get('total_chunks')
        file_hash = message.get('file_hash')
        chunk_hash = message.get('chunk_hash')
        
        logger.debug(f"收到文件分片: {transfer_id}, 索引={index}, 总数={total_chunks}")
        
        # 检查任务是否存在
        if transfer_id not in self.current_tasks:
            # 创建新任务
            task_obj = Task(transfer_id, {}, self)
            self.current_tasks[transfer_id] = task_obj
        
        task_obj = self.current_tasks[transfer_id]
        
        # 接收文件分片
        success = await task_obj.receive_file_chunk(
            chunk, index, total_chunks, file_hash, chunk_hash
        )
        
        if success:
            # 发送分片确认
            chunk_received_message = {
                'type': 'chunk_received',
                'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                'transfer_id': transfer_id,
                'index': index,
                'status': 'ok'
            }
            await self.ws_client.send_message(chunk_received_message)
            
            # 检查文件是否接收完整
            if task_obj.is_file_complete():
                logger.info(f"文件接收完整: {transfer_id}")
                
                # 保存输入文件
                if not task_obj.save_input_file():
                    logger.error(f"保存输入文件失败: {transfer_id}")
                    await self.send_task_failed_message(transfer_id, "保存输入文件失败")
        else:
            # 发送失败确认
            chunk_received_message = {
                'type': 'chunk_received',
                'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                'transfer_id': transfer_id,
                'index': index,
                'status': 'error'
            }
            await self.ws_client.send_message(chunk_received_message)
    
    async def handle_chunk_received(self, message):
        """
        处理分片接收确认
        
        Args:
            message: 分片接收确认消息
        """
        transfer_id = message.get('transfer_id')
        index = message.get('index')
        status = message.get('status')
        
        logger.debug(f"收到分片确认: {transfer_id}, 索引={index}, 状态={status}")
        # 这里可以添加重试逻辑
    
    async def handle_task_cancel(self, message):
        """
        处理任务取消
        
        Args:
            message: 任务取消消息
        """
        task_id = message.get('task_id')
        
        logger.info(f"收到任务取消请求: {task_id}")
        
        if task_id in self.current_tasks:
            task_obj = self.current_tasks[task_id]
            task_obj.cancel()
            logger.info(f"任务已取消: {task_id}")
        else:
            logger.warning(f"任务不存在: {task_id}")
    
    async def handle_shutdown(self, message):
        """
        处理关闭请求
        
        Args:
            message: 关闭请求消息
        """
        logger.info("收到关闭请求")
        await self.stop()
    
    async def send_status_reports(self):
        """定期发送状态报告"""
        report_interval = self.config.get('runtime.report_time', 10)
        
        while self.is_running and self.is_registered:
            try:
                # 获取状态报告
                status_data = self.resource_monitor.get_status_report(
                    active_tasks=len(self.current_tasks)
                )
                
                # 发送状态报告
                status_message = {
                    'type': 'status_report',
                    'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'data': status_data
                }
                
                await self.ws_client.send_message(status_message)
                logger.debug("状态报告已发送")
                
                # 等待下一次报告
                await asyncio.sleep(report_interval)
            except Exception as e:
                logger.error(f"发送状态报告失败: {e}")
                await asyncio.sleep(report_interval)
    
    async def send_task_failed_message(self, task_id: str, error_message: str):
        """
        发送任务失败消息
        
        Args:
            task_id: 任务ID
            error_message: 错误消息
        """
        message = {
            'type': 'task_failed',
            'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'task_id': task_id,
            'error': {
                'message': error_message
            },
            'execution_time': 0
        }
        
        await self.ws_client.send_message(message)
        logger.info(f"任务失败消息已发送: {task_id}")
