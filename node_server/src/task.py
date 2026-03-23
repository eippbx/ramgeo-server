import asyncio
import subprocess
import logging
import os
from datetime import datetime
from typing import Dict, Optional
from file_manager import FileManager

logger = logging.getLogger(__name__)

class Task:
    """任务处理器，负责执行任务、管理文件传输和报告任务状态"""
    
    def __init__(self, task_id: str, task_data: Dict, node_server):
        """
        初始化任务处理器
        
        Args:
            task_id: 任务ID
            task_data: 任务数据
            node_server: 节点服务器实例
        """
        self.task_id = task_id
        self.task_data = task_data
        self.node_server = node_server
        
        # 任务状态
        self.status = 'PENDING'
        self.start_time = None
        self.end_time = None
        self.error_message = None
        
        # 文件管理器
        self.file_manager = FileManager(node_server.config.get('runtime.work_dir'))
        
        # 文件接收缓冲区
        self.received_chunks = {}
        self.total_chunks = 0
        self.file_hash = None
        
        logger.info(f"任务初始化: {task_id}")
    
    async def receive_file_chunk(self, chunk: str, index: int, total_chunks: int, 
                                 file_hash: str, chunk_hash: str) -> bool:
        """
        接收文件分片
        
        Args:
            chunk: Base64编码的文件块
            index: 分片索引
            total_chunks: 总分片数
            file_hash: 文件MD5哈希
            chunk_hash: 分片MD5哈希
            
        Returns:
            bool: 是否成功
        """
        try:
            # 解码Base64
            import base64
            chunk_data = base64.b64decode(chunk)
            
            # 验证分片哈希
            calculated_hash = self.file_manager.calculate_chunk_md5(chunk_data)
            if calculated_hash != chunk_hash:
                logger.error(f"分片哈希验证失败: 期望={chunk_hash}, 实际={calculated_hash}")
                return False
            
            # 保存分片
            self.received_chunks[index] = chunk_data
            self.total_chunks = total_chunks
            self.file_hash = file_hash
            
            logger.debug(f"接收分片: {self.task_id}, 索引={index}, 进度={len(self.received_chunks)}/{total_chunks}")
            return True
        except Exception as e:
            logger.error(f"接收文件分片失败: {e}")
            return False
    
    def is_file_complete(self) -> bool:
        """
        检查文件是否接收完整
        
        Returns:
            bool: 是否完整
        """
        return len(self.received_chunks) == self.total_chunks
    
    def save_input_file(self) -> bool:
        """
        保存输入文件
        
        Returns:
            bool: 是否成功
        """
        try:
            # 合并所有分片
            chunks = [self.received_chunks[i] for i in range(self.total_chunks)]
            file_data = b''.join(chunks)
            
            # 保存文件
            input_file_path = self.file_manager.save_input_file(self.task_id, file_data)
            
            # 验证文件哈希
            calculated_hash = self.file_manager.calculate_md5(input_file_path)
            if calculated_hash != self.file_hash:
                logger.error(f"文件哈希验证失败: 期望={self.file_hash}, 实际={calculated_hash}")
                return False
            
            logger.info(f"输入文件保存成功: {input_file_path}")
            return True
        except Exception as e:
            logger.error(f"保存输入文件失败: {e}")
            return False
    
    async def execute(self) -> bool:
        """
        执行任务
        
        Returns:
            bool: 是否成功
        """
        self.status = 'RUNNING'
        self.start_time = datetime.now()
        logger.info(f"开始执行任务: {self.task_id}")
        
        try:
            # 获取工作目录
            work_dir = self.node_server.config.get('runtime.work_dir')
            
            # 获取ramgeo可执行文件路径
            ramgeo_bin = self.node_server.config.get('runtime.run_bin')
            
            # 转换为绝对路径
            if not os.path.isabs(ramgeo_bin):
                script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                ramgeo_bin = os.path.join(script_dir, ramgeo_bin)
                ramgeo_bin = os.path.abspath(ramgeo_bin)
            
            # 检查ramgeo是否存在
            if not os.path.exists(ramgeo_bin):
                raise Exception(f"ramgeo可执行文件不存在: {ramgeo_bin}")
            
            # 任务文件相对路径（相对于work_dir）
            task_file_path = os.path.join(work_dir, self.task_id)
            task_file_relative_path = os.path.relpath(task_file_path, work_dir)
            
            # 执行ramgeo，参数为任务文件的相对路径
            logger.info(f"执行ramgeo: {ramgeo_bin}, 参数: {task_file_relative_path}, 工作目录: {work_dir}")
            process = await asyncio.create_subprocess_exec(
                ramgeo_bin,
                task_file_relative_path,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 等待进程完成
            stdout, stderr = await process.communicate()
            
            # 检查执行结果
            if process.returncode != 0:
                error_message = stderr.decode('utf-8') if stderr else "Unknown error"
                raise Exception(f"ramgeo execution failed: {error_message}")
            
            logger.info(f"ramgeo执行成功: {self.task_id}")
            
            # 检查输出文件是否生成
            grid_file = os.path.join(work_dir, f"{self.task_id}.grid")
            line_file = os.path.join(work_dir, f"{self.task_id}.line")
            
            if not os.path.exists(grid_file):
                logger.warning(f"输出文件未生成: {grid_file}")
            if not os.path.exists(line_file):
                logger.warning(f"输出文件未生成: {line_file}")
            
            # 上传结果文件
            if os.path.exists(grid_file):
                await self.node_server.ws_client.upload_file(grid_file, f"{self.task_id}.grid")
                logger.info(f"grid文件已上传: {grid_file}")
            if os.path.exists(line_file):
                await self.node_server.ws_client.upload_file(line_file, f"{self.task_id}.line")
                logger.info(f"line文件已上传: {line_file}")
            
            # 任务执行成功
            self.status = 'COMPLETED'
            self.end_time = datetime.now()
            return True
            
        except Exception as e:
            logger.error(f"任务执行失败: {self.task_id}, 错误: {e}")
            self.status = 'FAILED'
            self.error_message = str(e)
            self.end_time = datetime.now()
            return False
    
    async def send_complete_message(self):
        """发送任务完成消息"""
        execution_time = int((self.end_time - self.start_time).total_seconds()) if self.start_time and self.end_time else 0
        
        message = {
            'type': 'task_complete',
            'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'task_id': self.task_id,
            'result': {
                'execution_time': execution_time,
                'status': 'success'
            }
        }
        
        await self.node_server.ws_client.send_message(message)
        logger.info(f"任务完成消息已发送: {self.task_id}")
    
    async def send_failed_message(self):
        """发送任务失败消息"""
        execution_time = int((self.end_time - self.start_time).total_seconds()) if self.start_time and self.end_time else 0
        
        message = {
            'type': 'task_failed',
            'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'task_id': self.task_id,
            'error': {
                'message': self.error_message or 'Unknown error'
            },
            'execution_time': execution_time
        }
        
        await self.node_server.ws_client.send_message(message)
        logger.info(f"任务失败消息已发送: {self.task_id}")
    
    async def start(self):
        """启动任务执行流程"""
        try:
            # 执行任务
            success = await self.execute()
            
            if success:
                # 发送完成消息
                await self.send_complete_message()
            else:
                # 发送失败消息
                await self.send_failed_message()
        except Exception as e:
            logger.error(f"任务执行流程异常: {self.task_id}, 错误: {e}")
            self.status = 'FAILED'
            self.error_message = str(e)
            await self.send_failed_message()
        finally:
            # 从节点服务器的任务列表中移除
            if self.task_id in self.node_server.current_tasks:
                del self.node_server.current_tasks[self.task_id]
            logger.info(f"任务结束: {self.task_id}, 状态={self.status}")
    
    def cancel(self):
        """取消任务"""
        self.status = 'CANCELLED'
        logger.info(f"任务已取消: {self.task_id}")
