import asyncio
import websockets
import json
import logging
import os
import base64
from datetime import datetime

logger = logging.getLogger(__name__)

class WebSocketClient:
    """WebSocket客户端，负责与代理服务器通信"""
    
    def __init__(self, config, message_handler):
        """
        初始化WebSocket客户端
        
        Args:
            config: 配置对象
            message_handler: 消息处理函数
        """
        self.config = config
        self.message_handler = message_handler
        
        # WebSocket配置
        self.proxy_url = config.get('proxy.proxy_server_url')
        self.connect_timeout = config.get('websocket.connect_timeout', 10)
        self.reconnect_interval = config.get('websocket.reconnect_interval', 5)
        self.max_reconnect_attempts = config.get('websocket.max_reconnect_attempts', 10)
        
        # 连接状态
        self.websocket = None
        self.is_connected = False
        self.reconnect_attempts = 0
        
        # 事件循环
        self.loop = asyncio.get_event_loop()
        
        # 回调函数
        self.on_connect_callback = None
        self.on_disconnect_callback = None
    
    async def connect(self):
        """建立WebSocket连接（单次尝试）"""
        try:
            logger.info(f"尝试连接到代理服务器: {self.proxy_url}")
            
            self.websocket = await asyncio.wait_for(
                websockets.connect(self.proxy_url),
                timeout=self.connect_timeout
            )
            
            self.is_connected = True
            self.reconnect_attempts = 0
            logger.info("WebSocket连接成功建立")
            
            return True
            
        except asyncio.TimeoutError:
            logger.warning(f"连接超时: {self.proxy_url}")
            raise
        except websockets.exceptions.WebSocketException as e:
            logger.warning(f"WebSocket连接失败: {e}")
            raise
        except Exception as e:
            logger.error(f"连接失败: {e}")
            raise
    
    async def disconnect(self):
        """关闭WebSocket连接"""
        if self.websocket and self.is_connected:
            try:
                await self.websocket.close()
                logger.info("WebSocket连接已关闭")
            except Exception as e:
                logger.error(f"关闭WebSocket连接失败: {e}")
            finally:
                self.is_connected = False
                self.websocket = None
                
                # 调用断开连接回调
                if hasattr(self, 'on_disconnect_callback') and callable(self.on_disconnect_callback):
                    await self.on_disconnect_callback()
    
    async def send_message(self, message):
        """
        发送消息到代理服务器
        
        Args:
            message (dict): 要发送的消息字典
        """
        if not self.is_connected or not self.websocket:
            logger.error("无法发送消息，WebSocket连接未建立")
            return False
        
        try:
            # 确保消息包含type和timestamp字段
            if 'type' not in message:
                logger.error("消息缺少type字段")
                return False
            
            if 'timestamp' not in message:
                message['timestamp'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            
            message_str = json.dumps(message)
            logger.debug(f"消息已发送: {message['type']}, 内容: {message_str}")
            await self.websocket.send(message_str)
            return True
            
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"发送消息失败: {e}")
            self.is_connected = False
        except Exception as e:
            logger.error(f"发送消息时发生错误: {e}")
        
        return False
    
    async def upload_file(self, file_path: str, file_name: str, chunk_size: int = 1024 * 1024 * 5):
        """
        上传文件到代理服务器
        
        Args:
            file_path: 本地文件路径
            file_name: 上传时的文件名
            chunk_size: 分片大小（字节），默认5MB
        """
        if not self.is_connected or not self.websocket:
            logger.error("无法上传文件，WebSocket连接未建立")
            return False
        
        try:
            if not os.path.exists(file_path):
                logger.error(f"文件不存在: {file_path}")
                return False
            
            # 计算文件哈希
            import hashlib
            file_hash = hashlib.md5()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    file_hash.update(chunk)
            file_md5 = file_hash.hexdigest()
            
            # 读取文件并分片
            chunks = []
            with open(file_path, 'rb') as f:
                while True:
                    chunk_data = f.read(chunk_size)
                    if not chunk_data:
                        break
                    chunks.append(chunk_data)
            
            total_chunks = len(chunks)
            logger.info(f"开始上传文件: {file_name}, 大小={os.path.getsize(file_path)}字节, 分片数={total_chunks}")
            
            # 逐个发送分片
            for index, chunk_data in enumerate(chunks):
                # 计算分片哈希
                chunk_md5 = hashlib.md5(chunk_data).hexdigest()
                
                # Base64编码
                chunk_base64 = base64.b64encode(chunk_data).decode('utf-8')
                
                # 发送文件分片
                message = {
                    'type': 'file_transfer',
                    'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'transfer_id': file_name,
                    'chunk': chunk_base64,
                    'index': index,
                    'total_chunks': total_chunks,
                    'file_hash': file_md5,
                    'chunk_hash': chunk_md5
                }
                
                await self.send_message(message)
                logger.debug(f"文件分片已发送: {file_name}, 索引={index}/{total_chunks}")
                
                # 等待确认（简单实现，实际应该等待chunk_received消息）
                await asyncio.sleep(0.1)
            
            logger.info(f"文件上传完成: {file_name}")
            return True
            
        except Exception as e:
            logger.error(f"上传文件失败: {e}")
            return False
    
    async def receive_messages(self):
        """接收并处理来自代理服务器的消息"""
        while self.is_connected and self.websocket:
            try:
                message_str = await self.websocket.recv()
                logger.debug(f"收到原始消息: {message_str}")
                message = json.loads(message_str)
                
                logger.debug(f"收到消息: {message.get('type')}")
                
                # 处理消息
                await self.message_handler(message)
                
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"WebSocket连接已关闭: {e.code} - {e.reason}")
                self.is_connected = False
                
                # 调用断开连接回调
                if hasattr(self, 'on_disconnect_callback') and callable(self.on_disconnect_callback):
                    await self.on_disconnect_callback()
                
                break
            except json.JSONDecodeError as e:
                logger.error(f"消息解析错误: {e}")
            except Exception as e:
                logger.error(f"处理消息时发生错误: {e}")
    
    async def run(self):
        """运行WebSocket客户端，实现自动重连和错误处理"""
        backoff_time = self.reconnect_interval  # 初始退避时间
        max_backoff_time = 60  # 最大退避时间
        
        while True:
            if not self.is_connected:
                try:
                    connected = await self.connect()
                    if connected:
                        # 连接成功后，重置退避时间
                        backoff_time = self.reconnect_interval
                        
                        # 调用注册方法（如果提供了的话）
                        if hasattr(self, 'on_connect_callback') and callable(self.on_connect_callback):
                            await self.on_connect_callback()
                except Exception as e:
                    # 连接失败，使用指数退避策略
                    self.reconnect_attempts += 1
                    if self.reconnect_attempts >= self.max_reconnect_attempts:
                        logger.error(f"达到最大重连尝试次数 ({self.max_reconnect_attempts})，停止重连")
                        break
                    
                    logger.warning(f"连接失败 ({self.reconnect_attempts}/{self.max_reconnect_attempts})，{backoff_time}秒后重试...")
                    await asyncio.sleep(backoff_time)
                    
                    # 更新退避时间
                    backoff_time = min(backoff_time * 2, max_backoff_time)
                    continue
            
            try:
                await self.receive_messages()
            except websockets.exceptions.WebSocketException as e:
                logger.error(f"WebSocket异常: {e}")
                await self.disconnect()
            except asyncio.TimeoutError:
                logger.error("WebSocket接收超时")
                await self.disconnect()
            except Exception as e:
                logger.error(f"接收消息时发生未预期异常: {e}")
                await self.disconnect()
            
            if not self.is_connected:
                # 等待一段时间后尝试重连
                self.reconnect_attempts += 1
                if self.reconnect_attempts >= self.max_reconnect_attempts:
                    logger.error(f"达到最大重连尝试次数 ({self.max_reconnect_attempts})，停止重连")
                    break
                
                logger.error(f"连接已断开 ({self.reconnect_attempts}/{self.max_reconnect_attempts})，{backoff_time}秒后重试...")
                await asyncio.sleep(backoff_time)
                
                # 更新退避时间
                backoff_time = min(backoff_time * 2, max_backoff_time)
