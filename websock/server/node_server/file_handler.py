#!/usr/bin/env python3
"""
文件处理模块
实现节点文件处理功能
"""

import asyncio
import logging
import os
import shutil
import uuid
import tempfile
import hashlib
from typing import Dict, Any, Optional, List

from shared.logger import setup_logging
from shared.exceptions import *

logger = setup_logging(__name__)


class FileHandler:
    """
    文件处理器类
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化文件处理器
        
        Args:
            config: 配置信息
        """
        self.config = config
        
        # 文件存储目录
        self.storage_dir = config.get('file_handler', {}).get('storage_dir', './storage')
        self.temp_dir = config.get('file_handler', {}).get('temp_dir', './temp')
        self.result_dir = config.get('file_handler', {}).get('result_dir', './results')
        
        # 文件配置
        self.max_file_size = config.get('file_handler', {}).get('max_file_size', 100 * 1024 * 1024)  # 最大文件大小（100MB）
        self.allowed_extensions = config.get('file_handler', {}).get('allowed_extensions', [
            'json', 'geojson', 'shp', 'shx', 'dbf', 'prj', 'zip', 'rar', '7z',
            'tif', 'tiff', 'jpg', 'jpeg', 'png', 'bmp', 'csv', 'txt'
        ])
        
        # 初始化文件目录
        self._init_directories()
        
        logger.info(f"文件处理器初始化完成，存储目录: {self.storage_dir}")
    
    def _init_directories(self) -> None:
        """
        初始化文件目录
        """
        try:
            # 创建存储目录
            os.makedirs(self.storage_dir, exist_ok=True)
            os.makedirs(self.temp_dir, exist_ok=True)
            os.makedirs(self.result_dir, exist_ok=True)
            
            logger.info(f"文件目录已初始化: storage={self.storage_dir}, temp={self.temp_dir}, result={self.result_dir}")
            
        except Exception as e:
            logger.error(f"初始化文件目录失败: {e}")
            raise FileSystemError(f"初始化文件目录失败: {e}")
    
    async def save_file(self, file_data: bytes, filename: str, task_id: str = None) -> Dict[str, Any]:
        """
        保存文件
        
        Args:
            file_data: 文件数据
            filename: 文件名
            task_id: 任务ID（可选）
            
        Returns:
            文件信息
        """
        try:
            # 验证文件大小
            if len(file_data) > self.max_file_size:
                raise PayloadTooLargeError(f"文件大小超过限制: {len(file_data)} bytes > {self.max_file_size} bytes")
            
            # 验证文件扩展名
            ext = filename.split('.')[-1].lower() if '.' in filename else ''
            if ext and ext not in self.allowed_extensions:
                raise InvalidFileFormatError(f"不支持的文件格式: {ext}")
            
            # 生成唯一文件名
            unique_filename = self._generate_unique_filename(filename)
            
            # 确定存储路径
            if task_id:
                # 为特定任务创建子目录
                task_dir = os.path.join(self.storage_dir, task_id)
                os.makedirs(task_dir, exist_ok=True)
                file_path = os.path.join(task_dir, unique_filename)
            else:
                # 直接存储在根目录
                file_path = os.path.join(self.storage_dir, unique_filename)
            
            # 保存文件
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            # 计算文件哈希
            file_hash = self._calculate_file_hash(file_path)
            
            # 获取文件信息
            file_info = {
                'filename': filename,
                'unique_filename': unique_filename,
                'file_path': file_path,
                'size': len(file_data),
                'hash': file_hash,
                'created_at': os.path.getctime(file_path),
                'task_id': task_id
            }
            
            logger.info(f"文件已保存: {filename} -> {unique_filename}, 大小: {len(file_data)} bytes")
            
            return file_info
            
        except Exception as e:
            logger.error(f"保存文件失败: {e}")
            raise FileSaveError(f"保存文件失败: {e}")
    
    async def load_file(self, file_path: str) -> bytes:
        """
        加载文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件数据
        """
        try:
            # 验证文件路径
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            # 加载文件
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            logger.info(f"文件已加载: {file_path}, 大小: {len(file_data)} bytes")
            
            return file_data
            
        except Exception as e:
            logger.error(f"加载文件失败: {e}")
            raise FileLoadError(f"加载文件失败: {e}")
    
    async def delete_file(self, file_path: str) -> bool:
        """
        删除文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否删除成功
        """
        try:
            # 验证文件路径
            if not os.path.exists(file_path):
                logger.warning(f"文件不存在: {file_path}")
                return False
            
            # 删除文件
            os.remove(file_path)
            
            logger.info(f"文件已删除: {file_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"删除文件失败: {e}")
            return False
    
    async def save_result(self, result_data: bytes, filename: str, task_id: str) -> Dict[str, Any]:
        """
        保存计算结果
        
        Args:
            result_data: 结果数据
            filename: 文件名
            task_id: 任务ID
            
        Returns:
            结果文件信息
        """
        try:
            # 为特定任务创建结果子目录
            task_result_dir = os.path.join(self.result_dir, task_id)
            os.makedirs(task_result_dir, exist_ok=True)
            
            # 生成唯一文件名
            unique_filename = self._generate_unique_filename(filename)
            file_path = os.path.join(task_result_dir, unique_filename)
            
            # 保存结果
            with open(file_path, 'wb') as f:
                f.write(result_data)
            
            # 计算文件哈希
            file_hash = self._calculate_file_hash(file_path)
            
            # 获取文件信息
            file_info = {
                'filename': filename,
                'unique_filename': unique_filename,
                'file_path': file_path,
                'size': len(result_data),
                'hash': file_hash,
                'created_at': os.path.getctime(file_path),
                'task_id': task_id
            }
            
            logger.info(f"结果文件已保存: {filename} -> {unique_filename}, 大小: {len(result_data)} bytes")
            
            return file_info
            
        except Exception as e:
            logger.error(f"保存结果文件失败: {e}")
            raise ResultSaveError(f"保存结果文件失败: {e}")
    
    async def load_result(self, task_id: str, filename: str = None) -> bytes:
        """
        加载计算结果
        
        Args:
            task_id: 任务ID
            filename: 文件名（可选）
            
        Returns:
            结果数据
        """
        try:
            # 确定结果目录
            task_result_dir = os.path.join(self.result_dir, task_id)
            
            if not os.path.exists(task_result_dir):
                raise FileNotFoundError(f"任务结果目录不存在: {task_result_dir}")
            
            if filename:
                # 加载特定文件
                file_path = os.path.join(task_result_dir, filename)
                return await self.load_file(file_path)
            else:
                # 加载第一个文件
                files = os.listdir(task_result_dir)
                if not files:
                    raise FileNotFoundError(f"任务结果目录为空: {task_result_dir}")
                
                file_path = os.path.join(task_result_dir, files[0])
                return await self.load_file(file_path)
                
        except Exception as e:
            logger.error(f"加载结果文件失败: {e}")
            raise ResultLoadError(f"加载结果文件失败: {e}")
    
    async def get_result_files(self, task_id: str) -> List[Dict[str, Any]]:
        """
        获取任务结果文件列表
        
        Args:
            task_id: 任务ID
            
        Returns:
            文件列表
        """
        try:
            # 确定结果目录
            task_result_dir = os.path.join(self.result_dir, task_id)
            
            if not os.path.exists(task_result_dir):
                return []
            
            # 获取文件列表
            files = []
            for filename in os.listdir(task_result_dir):
                file_path = os.path.join(task_result_dir, filename)
                
                if os.path.isfile(file_path):
                    file_info = {
                        'filename': filename,
                        'file_path': file_path,
                        'size': os.path.getsize(file_path),
                        'created_at': os.path.getctime(file_path),
                        'modified_at': os.path.getmtime(file_path)
                    }
                    files.append(file_info)
            
            # 按创建时间排序
            files.sort(key=lambda x: x['created_at'], reverse=True)
            
            return files
            
        except Exception as e:
            logger.error(f"获取结果文件列表失败: {e}")
            raise FileListError(f"获取结果文件列表失败: {e}")
    
    async def create_temp_file(self, data: bytes, suffix: str = '') -> str:
        """
        创建临时文件
        
        Args:
            data: 文件数据
            suffix: 文件后缀
            
        Returns:
            临时文件路径
        """
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='wb', suffix=suffix, dir=self.temp_dir, delete=False) as f:
                f.write(data)
                temp_path = f.name
            
            logger.info(f"临时文件已创建: {temp_path}")
            
            return temp_path
            
        except Exception as e:
            logger.error(f"创建临时文件失败: {e}")
            raise TempFileError(f"创建临时文件失败: {e}")
    
    async def delete_temp_file(self, file_path: str) -> bool:
        """
        删除临时文件
        
        Args:
            file_path: 临时文件路径
            
        Returns:
            是否删除成功
        """
        try:
            # 验证文件是否在临时目录
            if not file_path.startswith(self.temp_dir):
                logger.warning(f"文件不在临时目录: {file_path}")
                return False
            
            return await self.delete_file(file_path)
            
        except Exception as e:
            logger.error(f"删除临时文件失败: {e}")
            return False
    
    async def cleanup_temp_files(self) -> int:
        """
        清理所有临时文件
        
        Returns:
            删除的文件数量
        """
        try:
            deleted_count = 0
            
            for filename in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, filename)
                
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted_count += 1
            
            logger.info(f"已清理 {deleted_count} 个临时文件")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")
            return 0
    
    async def get_file_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        获取文件信息
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件信息
        """
        try:
            if not os.path.exists(file_path):
                return None
            
            return {
                'file_path': file_path,
                'filename': os.path.basename(file_path),
                'size': os.path.getsize(file_path),
                'created_at': os.path.getctime(file_path),
                'modified_at': os.path.getmtime(file_path),
                'is_file': os.path.isfile(file_path),
                'is_dir': os.path.isdir(file_path)
            }
            
        except Exception as e:
            logger.error(f"获取文件信息失败: {e}")
            return None
    
    async def move_file(self, src_path: str, dst_path: str) -> bool:
        """
        移动文件
        
        Args:
            src_path: 源路径
            dst_path: 目标路径
            
        Returns:
            是否移动成功
        """
        try:
            if not os.path.exists(src_path):
                logger.warning(f"源文件不存在: {src_path}")
                return False
            
            # 创建目标目录
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            
            # 移动文件
            shutil.move(src_path, dst_path)
            
            logger.info(f"文件已移动: {src_path} -> {dst_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"移动文件失败: {e}")
            return False
    
    async def copy_file(self, src_path: str, dst_path: str) -> bool:
        """
        复制文件
        
        Args:
            src_path: 源路径
            dst_path: 目标路径
            
        Returns:
            是否复制成功
        """
        try:
            if not os.path.exists(src_path):
                logger.warning(f"源文件不存在: {src_path}")
                return False
            
            # 创建目标目录
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            
            # 复制文件
            shutil.copy2(src_path, dst_path)
            
            logger.info(f"文件已复制: {src_path} -> {dst_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"复制文件失败: {e}")
            return False
    
    def _generate_unique_filename(self, filename: str) -> str:
        """
        生成唯一文件名
        
        Args:
            filename: 原始文件名
            
        Returns:
            唯一文件名
        """
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        name = filename.rsplit('.', 1)[0] if '.' in filename else filename
        
        # 生成UUID
        unique_id = uuid.uuid4().hex[:8]
        
        # 构建唯一文件名
        if ext:
            return f"{name}_{unique_id}.{ext}"
        else:
            return f"{name}_{unique_id}"
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """
        计算文件哈希
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件哈希值
        """
        try:
            hasher = hashlib.sha256()
            
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hasher.update(chunk)
            
            return hasher.hexdigest()
            
        except Exception as e:
            logger.error(f"计算文件哈希失败: {e}")
            return ''
    
    async def get_directory_size(self, dir_path: str) -> int:
        """
        获取目录大小
        
        Args:
            dir_path: 目录路径
            
        Returns:
            目录大小（字节）
        """
        try:
            total_size = 0
            
            for root, _, files in os.walk(dir_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    total_size += os.path.getsize(file_path)
            
            return total_size
            
        except Exception as e:
            logger.error(f"获取目录大小失败: {e}")
            return 0
    
    async def clean_task_files(self, task_id: str) -> None:
        """
        清理任务相关文件
        
        Args:
            task_id: 任务ID
        """
        try:
            # 清理任务存储目录
            task_storage_dir = os.path.join(self.storage_dir, task_id)
            if os.path.exists(task_storage_dir):
                shutil.rmtree(task_storage_dir)
                logger.info(f"任务存储目录已清理: {task_storage_dir}")
            
            # 清理任务结果目录
            task_result_dir = os.path.join(self.result_dir, task_id)
            if os.path.exists(task_result_dir):
                shutil.rmtree(task_result_dir)
                logger.info(f"任务结果目录已清理: {task_result_dir}")
                
        except Exception as e:
            logger.error(f"清理任务文件失败: {e}")
    
    async def stop(self) -> None:
        """
        停止文件处理器
        """
        try:
            # 清理临时文件
            await self.cleanup_temp_files()
            
            logger.info("文件处理器已停止")
            
        except Exception as e:
            logger.error(f"停止文件处理器失败: {e}")
