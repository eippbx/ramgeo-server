"""
WebSocket服务器实现
处理与计算节点的WebSocket通信
"""

import asyncio
import json
import logging
import base64
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError
from websockets.server import WebSocketServerProtocol
from aiohttp import web
import aiohttp_cors

from shared.config import Config
from shared.logger import setup_logging
from shared.metrics import MetricsCollector
from shared.security import SecurityManager
from shared.exceptions import AuthenticationError, NodeError

logger = setup_logging(__name__)

class WebSocketServer:
    """WebSocket服务器管理器"""
    
    def __init__(self, config: Config, node_manager, task_manager, 
                 auth_manager, metrics: MetricsCollector):
        self.config = config
        self.node_manager = node_manager
        self.task_manager = task_manager
        self.auth_manager = auth_manager
        self.metrics = metrics
        
        # 连接管理
        self.active_connections: Dict[str, WebSocketServerProtocol] = {}
        self.node_connections: Dict[str, str] = {}  # node_id -> connection_id
        self.connection_nodes: Dict[str, str] = {}  # connection_id -> node_id
        
        # 消息处理器注册
        self.message_handlers = {
            'auth': self._handle_auth,
            'heartbeat': self._handle_heartbeat,
            'status_report': self._handle_status_report,
            'task_progress': self._handle_task_progress,
            'task_complete': self._handle_task_complete,
            'task_failed': self._handle_task_failed,
            'file_transfer': self._handle_file_transfer,
            'capabilities': self._handle_capabilities,
        }
        
        # 心跳管理
        self.heartbeat_timeouts: Dict[str, asyncio.Task] = {}
        
        # 消息队列
        self.message_queues: Dict[str, asyncio.Queue] = {}
    
    async def setup(self, app: web.Application):
        """设置WebSocket路由"""
        # 设置CORS
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
            )
        })
        
        # WebSocket端点
        ws_route = cors.add(app.router.add_resource('/ws'))
        cors.add(ws_route.add_route('GET', self.websocket_handler))
        
        # 节点WebSocket端点
        node_ws_route = cors.add(app.router.add_resource('/node-ws'))
        cors.add(node_ws_route.add_route('GET', self.node_websocket_handler))
        
        # 客户端WebSocket端点
        client_ws_route = cors.add(app.router.add_resource('/client-ws'))
        cors.add(client_ws_route.add_route('GET', self.client_websocket_handler))
        
        logger.info("WebSocket路由设置完成")
    
    async def websocket_handler(self, request: web.Request):
        """通用WebSocket处理器"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        connection_id = str(id(ws))
        logger.info(f"新的WebSocket连接: {connection_id}")
        
        try:
            self.active_connections[connection_id] = ws
            self.metrics.increment_counter('websocket_connections')
            
            # 发送连接确认
            await self._send_message(ws, {
                'type': 'connected',
                'connection_id': connection_id,
                'timestamp': datetime.now().isoformat(),
                'server_info': {
                    'version': '1.0.0',
                    'supported_protocols': ['v1']
                }
            })
            
            # 处理消息
            async for msg in ws:
                await self._process_message(connection_id, msg)
                
        except ConnectionClosed:
            logger.info(f"WebSocket连接关闭: {connection_id}")
        except Exception as e:
            logger.error(f"WebSocket处理错误: {e}")
        finally:
            # 清理连接
            await self._cleanup_connection(connection_id)
        
        return ws
    
    async def node_websocket_handler(self, request: web.Request):
        """计算节点WebSocket处理器"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        connection_id = str(id(ws))
        logger.info(f"新的节点WebSocket连接: {connection_id}")
        
        try:
            self.active_connections[connection_id] = ws
            self.metrics.increment_counter('node_connections')
            
            # 等待认证消息
            auth_message = await ws.receive()
            if auth_message.type != web.WSMsgType.TEXT:
                await ws.close(code=1008, message='Invalid message type')
                return ws
            
            auth_data = json.loads(auth_message.data)
            if auth_data.get('type') != 'auth':
                await ws.close(code=1008, message='Authentication required')
                return ws
            
            # 验证节点身份
            node_id = auth_data.get('node_id')
            auth_token = auth_data.get('token')
            
            if not await self.auth_manager.authenticate_node(node_id, auth_token):
                await ws.close(code=1003, message='Authentication failed')
                return ws
            
            # 认证成功
            self.node_connections[node_id] = connection_id
            self.connection_nodes[connection_id] = node_id
            
            await self._send_message(ws, {
                'type': 'auth_response',
                'status': 'authenticated',
                'node_id': node_id,
                'timestamp': datetime.now().isoformat()
            })
            
            # 启动心跳检测
            asyncio.create_task(self._start_heartbeat(node_id, ws))
            
            # 处理节点消息
            async for msg in ws:
                await self._process_node_message(node_id, msg)
                
        except ConnectionClosed:
            logger.info(f"节点WebSocket连接关闭: {connection_id}")
        except Exception as e:
            logger.error(f"节点WebSocket处理错误: {e}")
        finally:
            # 清理连接
            await self._cleanup_node_connection(connection_id)
        
        return ws
    
    async def client_websocket_handler(self, request: web.Request):
        """客户端WebSocket处理器"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        connection_id = str(id(ws))
        
        # 获取认证token
        token = request.query.get('token')
        if not token:
            await ws.close(code=1008, message='Authentication token required')
            return ws
        
        try:
            # 验证用户token
            user_info = await self.auth_manager.verify_user_token(token)
            if not user_info:
                await ws.close(code=1003, message='Authentication failed')
                return ws
            
            user_id = user_info['user_id']
            logger.info(f"新的客户端WebSocket连接: {connection_id}, 用户: {user_id}")
            
            self.active_connections[connection_id] = ws
            self.metrics.increment_counter('client_connections')
            
            # 发送连接确认
            await self._send_message(ws, {
                'type': 'connected',
                'user_id': user_id,
                'timestamp': datetime.now().isoformat(),
                'permissions': user_info.get('permissions', [])
            })
            
            # 发送系统状态
            system_status = await self._get_system_status()
            await self._send_message(ws, {
                'type': 'system_status',
                'data': system_status
            })
            
            # 处理客户端消息
            async for msg in ws:
                await self._process_client_message(user_id, msg)
                
        except ConnectionClosed:
            logger.info(f"客户端WebSocket连接关闭: {connection_id}")
        except Exception as e:
            logger.error(f"客户端WebSocket处理错误: {e}")
        finally:
            # 清理连接
            await self._cleanup_connection(connection_id)
        
        return ws
    
    async def _process_message(self, connection_id: str, msg):
        """处理通用消息"""
        if msg.type == web.WSMsgType.TEXT:
            try:
                data = json.loads(msg.data)
                message_type = data.get('type')
                
                if message_type in self.message_handlers:
                    await self.message_handlers[message_type](connection_id, data)
                else:
                    logger.warning(f"未知的消息类型: {message_type}")
                    
            except json.JSONDecodeError:
                logger.error("无效的JSON消息")
            except Exception as e:
                logger.error(f"消息处理错误: {e}")
    
    async def _process_node_message(self, node_id: str, msg):
        """处理节点消息"""
        if msg.type == web.WSMsgType.TEXT:
            try:
                data = json.loads(msg.data)
                message_type = data.get('type')
                
                # 更新节点最后活跃时间
                await self.node_manager.update_node_activity(node_id)
                
                if message_type == 'heartbeat':
                    await self._handle_node_heartbeat(node_id, data)
                elif message_type == 'status_report':
                    await self._handle_node_status(node_id, data)
                elif message_type == 'task_progress':
                    await self._handle_node_task_progress(node_id, data)
                elif message_type == 'task_complete':
                    await self._handle_node_task_complete(node_id, data)
                elif message_type == 'task_failed':
                    await self._handle_node_task_failed(node_id, data)
                elif message_type == 'file_transfer':
                    await self._handle_node_file_transfer(node_id, data)
                else:
                    logger.warning(f"未知的节点消息类型: {message_type}")
                    
            except json.JSONDecodeError:
                logger.error("无效的JSON消息")
            except Exception as e:
                logger.error(f"节点消息处理错误: {e}")
    
    async def _process_client_message(self, user_id: str, msg):
        """处理客户端消息"""
        if msg.type == web.WSMsgType.TEXT:
            try:
                data = json.loads(msg.data)
                message_type = data.get('type')
                
                if message_type == 'subscribe':
                    await self._handle_client_subscribe(user_id, data)
                elif message_type == 'unsubscribe':
                    await self._handle_client_unsubscribe(user_id, data)
                elif message_type == 'task_query':
                    await self._handle_client_task_query(user_id, data)
                elif message_type == 'system_query':
                    await self._handle_client_system_query(user_id, data)
                else:
                    logger.warning(f"未知的客户端消息类型: {message_type}")
                    
            except json.JSONDecodeError:
                logger.error("无效的JSON消息")
            except Exception as e:
                logger.error(f"客户端消息处理错误: {e}")
    
    async def _handle_auth(self, connection_id: str, data: Dict):
        """处理认证消息"""
        node_id = data.get('node_id')
        token = data.get('token')
        
        if not node_id or not token:
            await self._send_error(connection_id, 'Missing authentication credentials')
            return
        
        try:
            # 验证节点身份
            if await self.auth_manager.authenticate_node(node_id, token):
                self.node_connections[node_id] = connection_id
                self.connection_nodes[connection_id] = node_id
                
                await self._send_message_to_connection(connection_id, {
                    'type': 'auth_response',
                    'status': 'authenticated',
                    'node_id': node_id,
                    'timestamp': datetime.now().isoformat()
                })
                
                logger.info(f"节点认证成功: {node_id}")
                
                # 通知节点管理器
                await self.node_manager.node_connected(node_id, connection_id)
                
            else:
                await self._send_error(connection_id, 'Authentication failed')
                await self._close_connection(connection_id, 1003)
                
        except Exception as e:
            logger.error(f"认证处理错误: {e}")
            await self._send_error(connection_id, 'Authentication error')
    
    async def _handle_heartbeat(self, connection_id: str, data: Dict):
        """处理心跳消息"""
        node_id = self.connection_nodes.get(connection_id)
        if node_id:
            await self.node_manager.update_node_heartbeat(node_id)
        
        await self._send_message_to_connection(connection_id, {
            'type': 'heartbeat_response',
            'timestamp': datetime.now().isoformat()
        })
    
    async def _handle_status_report(self, connection_id: str, data: Dict):
        """处理状态报告"""
        node_id = self.connection_nodes.get(connection_id)
        if node_id:
            status_data = data.get('data', {})
            await self.node_manager.update_node_status(node_id, status_data)
    
    async def _handle_task_progress(self, connection_id: str, data: Dict):
        """处理任务进度"""
        task_id = data.get('task_id')
        progress = data.get('progress')
        
        if task_id and progress is not None:
            await self.task_manager.update_task_progress(task_id, progress)
            
            # 通知相关客户端
            await self._broadcast_task_progress(task_id, progress)
    
    async def _handle_task_complete(self, connection_id: str, data: Dict):
        """处理任务完成"""
        task_id = data.get('task_id')
        result_data = data.get('result', {})
        
        if task_id:
            await self.task_manager.complete_task(task_id, result_data)
            
            # 通知相关客户端
            await self._broadcast_task_complete(task_id, result_data)
    
    async def _handle_task_failed(self, connection_id: str, data: Dict):
        """处理任务失败"""
        task_id = data.get('task_id')
        error_data = data.get('error', {})
        
        if task_id:
            await self.task_manager.fail_task(task_id, error_data)
            
            # 通知相关客户端
            await self._broadcast_task_failed(task_id, error_data)
    
    async def _handle_file_transfer(self, connection_id: str, data: Dict):
        """处理文件传输"""
        transfer_id = data.get('transfer_id')
        chunk_data = data.get('chunk')
        chunk_index = data.get('index')
        total_chunks = data.get('total')
        
        if transfer_id and chunk_data:
            # 处理文件分片
            await self.file_manager.process_chunk(
                transfer_id, chunk_data, chunk_index, total_chunks
            )
            
            # 发送确认
            await self._send_message_to_connection(connection_id, {
                'type': 'chunk_received',
                'transfer_id': transfer_id,
                'index': chunk_index,
                'timestamp': datetime.now().isoformat()
            })
    
    async def _handle_capabilities(self, connection_id: str, data: Dict):
        """处理能力报告"""
        node_id = self.connection_nodes.get(connection_id)
        if node_id:
            capabilities = data.get('capabilities', {})
            await self.node_manager.update_node_capabilities(node_id, capabilities)
    
    async def _handle_node_heartbeat(self, node_id: str, data: Dict):
        """处理节点心跳"""
        await self.node_manager.update_node_heartbeat(node_id)
        
        # 发送心跳响应
        await self._send_message_to_node(node_id, {
            'type': 'heartbeat_response',
            'timestamp': datetime.now().isoformat()
        })
    
    async def _handle_node_status(self, node_id: str, data: Dict):
        """处理节点状态"""
        status_data = data.get('data', {})
        await self.node_manager.update_node_status(node_id, status_data)
    
    async def _handle_node_task_progress(self, node_id: str, data: Dict):
        """处理节点任务进度"""
        task_id = data.get('task_id')
        progress = data.get('progress')
        
        if task_id and progress is not None:
            await self.task_manager.update_task_progress(task_id, progress)
    
    async def _handle_node_task_complete(self, node_id: str, data: Dict):
        """处理节点任务完成"""
        task_id = data.get('task_id')
        result_data = data.get('result', {})
        
        if task_id:
            await self.task_manager.complete_task(task_id, result_data)
    
    async def _handle_node_task_failed(self, node_id: str, data: Dict):
        """处理节点任务失败"""
        task_id = data.get('task_id')
        error_data = data.get('error', {})
        
        if task_id:
            await self.task_manager.fail_task(task_id, error_data)
    
    async def _handle_node_file_transfer(self, node_id: str, data: Dict):
        """处理节点文件传输"""
        # 这里实现文件传输逻辑
        pass
    
    async def _handle_client_subscribe(self, user_id: str, data: Dict):
        """处理客户端订阅"""
        subscription_type = data.get('type')
        subscription_id = data.get('id')
        
        if subscription_type == 'task':
            # 订阅任务更新
            await self.task_manager.subscribe_to_task(user_id, subscription_id)
        elif subscription_type == 'node':
            # 订阅节点更新
            await self.node_manager.subscribe_to_node(user_id, subscription_id)
        elif subscription_type == 'system':
            # 订阅系统更新
            await self._subscribe_to_system_updates(user_id)
    
    async def _handle_client_unsubscribe(self, user_id: str, data: Dict):
        """处理客户端取消订阅"""
        subscription_type = data.get('type')
        subscription_id = data.get('id')
        
        if subscription_type == 'task':
            # 取消订阅任务更新
            await self.task_manager.unsubscribe_from_task(user_id, subscription_id)
        elif subscription_type == 'node':
            # 取消订阅节点更新
            await self.node_manager.unsubscribe_from_node(user_id, subscription_id)
    
    async def _handle_client_task_query(self, user_id: str, data: Dict):
        """处理客户端任务查询"""
        task_id = data.get('task_id')
        if task_id:
            task_info = await self.task_manager.get_task_info(task_id, user_id)
            await self._send_message_to_user(user_id, {
                'type': 'task_info',
                'data': task_info
            })
    
    async def _handle_client_system_query(self, user_id: str, data: Dict):
        """处理客户端系统查询"""
        query_type = data.get('query_type')
        
        if query_type == 'status':
            system_status = await self._get_system_status()
            await self._send_message_to_user(user_id, {
                'type': 'system_status',
                'data': system_status
            })
        elif query_type == 'nodes':
            nodes_info = await self.node_manager.get_all_nodes_info()
            await self._send_message_to_user(user_id, {
                'type': 'nodes_info',
                'data': nodes_info
            })
    
    async def _start_heartbeat(self, node_id: str, ws):
        """启动心跳检测"""
        while True:
            try:
                # 等待心跳
                await asyncio.sleep(self.config.get('websocket.heartbeat_interval', 30))
                
                # 发送心跳
                await self._send_message(ws, {
                    'type': 'heartbeat',
                    'timestamp': datetime.now().isoformat()
                })
                
                # 设置超时检测
                self.heartbeat_timeouts[node_id] = asyncio.create_task(
                    self._check_heartbeat_timeout(node_id)
                )
                
            except ConnectionClosed:
                break
            except Exception as e:
                logger.error(f"心跳发送失败: {e}")
                break
    
    async def _check_heartbeat_timeout(self, node_id: str):
        """检查心跳超时"""
        await asyncio.sleep(self.config.get('websocket.heartbeat_timeout', 60))
        
        # 检查节点是否还在线
        if node_id in self.node_connections:
            logger.warning(f"节点心跳超时: {node_id}")
            await self.node_manager.mark_node_unhealthy(node_id)
    
    async def _cleanup_connection(self, connection_id: str):
        """清理连接"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        
        if connection_id in self.connection_nodes:
            node_id = self.connection_nodes[connection_id]
            del self.connection_nodes[connection_id]
            
            if node_id in self.node_connections:
                del self.node_connections[node_id]
            
            # 通知节点管理器
            await self.node_manager.node_disconnected(node_id)
        
        self.metrics.decrement_counter('websocket_connections')
    
    async def _cleanup_node_connection(self, connection_id: str):
        """清理节点连接"""
        await self._cleanup_connection(connection_id)
        self.metrics.decrement_counter('node_connections')
    
    async def _send_message(self, ws, data: Dict):
        """发送消息"""
        try:
            await ws.send_str(json.dumps(data))
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
    
    async def _send_message_to_connection(self, connection_id: str, data: Dict):
        """发送消息到指定连接"""
        if connection_id in self.active_connections:
            await self._send_message(self.active_connections[connection_id], data)
    
    async def _send_message_to_node(self, node_id: str, data: Dict):
        """发送消息到指定节点"""
        if node_id in self.node_connections:
            connection_id = self.node_connections[node_id]
            await self._send_message_to_connection(connection_id, data)
    
    async def _send_message_to_user(self, user_id: str, data: Dict):
        """发送消息到指定用户的所有连接"""
        # 这里需要实现用户连接映射
        pass
    
    async def _send_error(self, connection_id: str, error_message: str):
        """发送错误消息"""
        await self._send_message_to_connection(connection_id, {
            'type': 'error',
            'message': error_message,
            'timestamp': datetime.now().isoformat()
        })
    
    async def _close_connection(self, connection_id: str, code: int = 1000):
        """关闭连接"""
        if connection_id in self.active_connections:
            ws = self.active_connections[connection_id]
            await ws.close(code=code)
    
    async def _broadcast_task_progress(self, task_id: str, progress: float):
        """广播任务进度"""
        subscribers = await self.task_manager.get_task_subscribers(task_id)
        
        for user_id in subscribers:
            await self._send_message_to_user(user_id, {
                'type': 'task_progress',
                'task_id': task_id,
                'progress': progress,
                'timestamp': datetime.now().isoformat()
            })
    
    async def _broadcast_task_complete(self, task_id: str, result_data: Dict):
        """广播任务完成"""
        subscribers = await self.task_manager.get_task_subscribers(task_id)
        
        for user_id in subscribers:
            await self._send_message_to_user(user_id, {
                'type': 'task_complete',
                'task_id': task_id,
                'result': result_data,
                'timestamp': datetime.now().isoformat()
            })
    
    async def _broadcast_task_failed(self, task_id: str, error_data: Dict):
        """广播任务失败"""
        subscribers = await self.task_manager.get_task_subscribers(task_id)
        
        for user_id in subscribers:
            await self._send_message_to_user(user_id, {
                'type': 'task_failed',
                'task_id': task_id,
                'error': error_data,
                'timestamp': datetime.now().isoformat()
            })
    
    async def _subscribe_to_system_updates(self, user_id: str):
        """订阅系统更新"""
        # 这里实现系统更新订阅逻辑
        pass
    
    async def _get_system_status(self) -> Dict:
        """获取系统状态"""
        return {
            'total_nodes': await self.node_manager.get_total_nodes(),
            'active_nodes': await self.node_manager.get_active_nodes(),
            'total_tasks': await self.task_manager.get_total_tasks(),
            'active_tasks': await self.task_manager.get_active_tasks(),
            'system_load': await self._calculate_system_load(),
            'uptime': str(datetime.now() - self.node_manager.start_time),
        }
    
    async def _calculate_system_load(self) -> float:
        """计算系统负载"""
        # 这里实现系统负载计算
        return 0.0
    
    async def assign_task_to_node(self, node_id: str, task_data: Dict) -> bool:
        """分配任务到节点"""
        if node_id not in self.node_connections:
            logger.warning(f"节点未连接: {node_id}")
            return False
        
        try:
            await self._send_message_to_node(node_id, {
                'type': 'task_assign',
                'task_id': task_data.get('task_id'),
                'data': task_data,
                'timestamp': datetime.now().isoformat()
            })
            return True
        except Exception as e:
            logger.error(f"分配任务失败: {e}")
            return False
    
    async def broadcast_to_nodes(self, message: Dict):
        """广播消息到所有节点"""
        for node_id in list(self.node_connections.keys()):
            try:
                await self._send_message_to_node(node_id, message)
            except Exception as e:
                logger.error(f"广播消息失败到节点 {node_id}: {e}")
    
    async def shutdown(self):
        """关闭WebSocket服务器"""
        logger.info("关闭WebSocket服务器...")
        
        # 取消所有心跳检测任务
        for task in self.heartbeat_timeouts.values():
            task.cancel()
        
        # 关闭所有连接
        for connection_id in list(self.active_connections.keys()):
            try:
                await self._close_connection(connection_id)
            except Exception as e:
                logger.error(f"关闭连接失败 {connection_id}: {e}")
        
        logger.info("WebSocket服务器关闭完成")