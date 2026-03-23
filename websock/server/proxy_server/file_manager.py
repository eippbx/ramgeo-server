#!/usr/bin/env python3
"""
文件管理器模块
提供文件上传、下载、管理等功能
"""

import os
import uuid
import shutil
import asyncio
import aiofiles
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from shared.logger import setup_logging
from shared.exceptions import FileError, NotFoundError, BadRequestError, PayloadTooLargeError

logger = setup_logging(__name__)


class FileManager:
    """
    文件管理器类
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化文件管理器
        
        Args:
            config: 配置信息
        """
        self.config = config
        
        # 文件存储配置
        self.upload_dir = config.get('file.upload_dir', '/tmp/ramgeo/uploads')
        self.download_dir = config.get('file.download_dir', '/tmp/ramgeo/downloads')
        self.max_file_size = config.get('file.max_size', 100 * 1024 * 1024)  # 默认100MB
        self.allowed_extensions = config.get('file.allowed_extensions', [])
        
        # 临时文件清理配置
        self.temp_file_expiration = config.get('file.temp_expiration', 3600)  # 默认1小时
        
        # 确保目录存在
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """
        确保所需目录存在
        """
        for directory in [self.upload_dir, self.download_dir]:
            try:
                os.makedirs(directory, exist_ok=True)
                logger.info(f"确保目录存在: {directory}")
            except Exception as e:
                logger.error(f"创建目录失败: {directory}, 错误: {e}")
                raise FileError(f"无法创建目录: {directory}", details={"directory": directory})
    
    async def save_file(self, file_content: bytes, filename: str, user_id: str) -> str:
        """
        保存上传的文件
        
        Args:
            file_content: 文件内容
            filename: 原始文件名
            user_id: 用户ID
        
        Returns:
            保存的文件路径
        """
        # 验证文件大小
        if len(file_content) > self.max_file_size:
            raise PayloadTooLargeError(f"文件大小超过限制: {self.max_file_size / (1024 * 1024)}MB")
        
        # 验证文件扩展名
        if self.allowed_extensions:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in self.allowed_extensions:
                raise BadRequestError(f"不支持的文件类型: {ext}")
        
        # 生成唯一文件名
        file_id = str(uuid.uuid4())
        ext = os.path.splitext(filename)[1]
        unique_filename = f"{user_id}_{file_id}{ext}"
        
        # 保存文件
        file_path = os.path.join(self.upload_dir, unique_filename)
        
        try:
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(file_content)
            
            logger.info(f"文件保存成功: {file_path}")
            return unique_filename
            
        except Exception as e:
            logger.error(f"保存文件失败: {file_path}, 错误: {e}")
            raise FileError(f"无法保存文件: {filename}", details={"filename": filename})
    
    async def get_file(self, filename: str) -> bytes:
        """
        获取文件内容
        
        Args:
            filename: 文件名
        
        Returns:
            文件内容
        """
        file_path = os.path.join(self.upload_dir, filename)
        
        if not os.path.exists(file_path):
            raise NotFoundError(f"文件不存在: {filename}")
        
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                content = await f.read()
            
            return content
            
        except Exception as e:
            logger.error(f"读取文件失败: {file_path}, 错误: {e}")
            raise FileError(f"无法读取文件: {filename}", details={"filename": filename})
    
    async def delete_file(self, filename: str) -> bool:
        """
        删除文件
        
        Args:
            filename: 文件名
        
        Returns:
            删除是否成功
        """
        file_path = os.path.join(self.upload_dir, filename)
        
        if not os.path.exists(file_path):
            return True  # 文件不存在，视为删除成功
        
        try:
            os.remove(file_path)
            logger.info(f"文件删除成功: {file_path}")
            return True
        except Exception as e:
            logger.error(f"删除文件失败: {file_path}, 错误: {e}")
            raise FileError(f"无法删除文件: {filename}", details={"filename": filename})
    
    async def list_files(self, user_id: str) -> List[Dict[str, Any]]:
        """
        列出用户的所有文件
        
        Args:
            user_id: 用户ID
        
        Returns:
            文件列表
        """
        files = []
        
        try:
            for filename in os.listdir(self.upload_dir):
                if filename.startswith(f"{user_id}_"):
                    file_path = os.path.join(self.upload_dir, filename)
                    stats = os.stat(file_path)
                    
                    files.append({
                        "filename": filename,
                        "size": stats.st_size,
                        "created_at": datetime.fromtimestamp(stats.st_ctime).isoformat(),
                        "updated_at": datetime.fromtimestamp(stats.st_mtime).isoformat()
                    })
            
            return files
            
        except Exception as e:
            logger.error(f"列出文件失败: {e}")
            raise FileError("无法列出文件", details={"user_id": user_id})
    
    async def get_file_info(self, filename: str) -> Dict[str, Any]:
        """
        获取文件信息
        
        Args:
            filename: 文件名
        
        Returns:
            文件信息
        """
        file_path = os.path.join(self.upload_dir, filename)
        
        if not os.path.exists(file_path):
            raise NotFoundError(f"文件不存在: {filename}")
        
        try:
            stats = os.stat(file_path)
            
            return {
                "filename": filename,
                "size": stats.st_size,
                "created_at": datetime.fromtimestamp(stats.st_ctime).isoformat(),
                "updated_at": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                "path": file_path
            }
            
        except Exception as e:
            logger.error(f"获取文件信息失败: {file_path}, 错误: {e}")
            raise FileError(f"无法获取文件信息: {filename}", details={"filename": filename})
    
    async def move_file(self, source_filename: str, destination: str) -> str:
        """
        移动文件
        
        Args:
            source_filename: 源文件名
            destination: 目标目录
        
        Returns:
            移动后的文件路径
        """
        source_path = os.path.join(self.upload_dir, source_filename)
        destination_path = os.path.join(destination, source_filename)
        
        if not os.path.exists(source_path):
            raise NotFoundError(f"源文件不存在: {source_filename}")
        
        try:
            # 确保目标目录存在
            os.makedirs(destination, exist_ok=True)
            
            # 移动文件
            shutil.move(source_path, destination_path)
            logger.info(f"文件移动成功: {source_path} -> {destination_path}")
            
            return destination_path
            
        except Exception as e:
            logger.error(f"移动文件失败: {source_path} -> {destination_path}, 错误: {e}")
            raise FileError(f"无法移动文件: {source_filename}", details={"source": source_filename, "destination": destination})
    
    async def copy_file(self, source_filename: str, destination: str) -> str:
        """
        复制文件
        
        Args:
            source_filename: 源文件名
            destination: 目标目录
        
        Returns:
            复制后的文件路径
        """
        source_path = os.path.join(self.upload_dir, source_filename)
        destination_path = os.path.join(destination, source_filename)
        
        if not os.path.exists(source_path):
            raise NotFoundError(f"源文件不存在: {source_filename}")
        
        try:
            # 确保目标目录存在
            os.makedirs(destination, exist_ok=True)
            
            # 复制文件
            shutil.copy2(source_path, destination_path)
            logger.info(f"文件复制成功: {source_path} -> {destination_path}")
            
            return destination_path
            
        except Exception as e:
            logger.error(f"复制文件失败: {source_path} -> {destination_path}, 错误: {e}")
            raise FileError(f"无法复制文件: {source_filename}", details={"source": source_filename, "destination": destination})
    
    async def cleanup_temp_files(self) -> int:
        """
        清理临时文件
        
        Returns:
            清理的文件数量
        """
        cleaned_count = 0
        current_time = datetime.now().timestamp()
        
        try:
            for filename in os.listdir(self.upload_dir):
                file_path = os.path.join(self.upload_dir, filename)
                stats = os.stat(file_path)
                
                # 检查文件是否过期
                if current_time - stats.st_mtime > self.temp_file_expiration:
                    os.remove(file_path)
                    cleaned_count += 1
                    logger.info(f"清理临时文件: {file_path}")
            
            logger.info(f"清理了 {cleaned_count} 个临时文件")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")
            raise FileError("无法清理临时文件")
    
    async def get_directory_size(self, directory: str) -> int:
        """
        获取目录大小
        
        Args:
            directory: 目录路径
        
        Returns:
            目录大小（字节）
        """
        total_size = 0
        
        try:
            for dirpath, dirnames, filenames in os.walk(directory):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    stats = os.stat(file_path)
                    total_size += stats.st_size
            
            return total_size
            
        except Exception as e:
            logger.error(f"获取目录大小失败: {directory}, 错误: {e}")
            raise FileError(f"无法获取目录大小: {directory}", details={"directory": directory})
    
    async def create_zip_archive(self, filenames: List[str], archive_name: str) -> str:
        """
        创建ZIP归档文件
        
        Args:
            filenames: 要归档的文件名列表
            archive_name: 归档文件名
        
        Returns:
            归档文件路径
        """
        import zipfile
        
        # 生成唯一归档文件名
        archive_id = str(uuid.uuid4())
        archive_ext = os.path.splitext(archive_name)[1] or '.zip'
        unique_archive_name = f"{archive_id}{archive_ext}"
        archive_path = os.path.join(self.download_dir, unique_archive_name)
        
        try:
            # 创建ZIP文件
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for filename in filenames:
                    file_path = os.path.join(self.upload_dir, filename)
                    if os.path.exists(file_path):
                        zipf.write(file_path, filename)
            
            logger.info(f"创建归档文件成功: {archive_path}")
            return unique_archive_name
            
        except Exception as e:
            logger.error(f"创建归档文件失败: {archive_path}, 错误: {e}")
            raise FileError(f"无法创建归档文件: {archive_name}", details={"archive_name": archive_name})
