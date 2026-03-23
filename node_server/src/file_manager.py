import os
import hashlib
import base64
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class FileManager:
    """文件管理器，负责文件传输、分片处理、完整性校验等"""
    
    def __init__(self, work_dir: str):
        """
        初始化文件管理器
        
        Args:
            work_dir: 工作目录，用于存储任务文件和结果
        """
        self.work_dir = work_dir
        self.chunk_size = 1024 * 1024 * 5  # 默认分片大小：5MB
        
        # 确保工作目录存在
        os.makedirs(work_dir, exist_ok=True)
        logger.info(f"文件管理器初始化完成，工作目录: {work_dir}")
    
    def calculate_md5(self, file_path: str) -> str:
        """
        计算文件的MD5哈希值
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: MD5哈希值
        """
        md5_hash = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    md5_hash.update(chunk)
            return md5_hash.hexdigest()
        except Exception as e:
            logger.error(f"计算文件MD5失败: {e}")
            raise
    
    def calculate_chunk_md5(self, chunk: bytes) -> str:
        """
        计算文件块的MD5哈希值
        
        Args:
            chunk: 文件块数据
            
        Returns:
            str: MD5哈希值
        """
        return hashlib.md5(chunk).hexdigest()
    
    def split_file(self, file_path: str) -> List[bytes]:
        """
        将文件分割成多个块
        
        Args:
            file_path: 文件路径
            
        Returns:
            List[bytes]: 文件块列表
        """
        chunks = []
        try:
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    chunks.append(chunk)
            logger.info(f"文件分割完成: {file_path}, 共{len(chunks)}个块")
            return chunks
        except Exception as e:
            logger.error(f"文件分割失败: {e}")
            raise
    
    def merge_chunks(self, chunks: List[bytes], output_path: str) -> None:
        """
        将多个文件块合并成一个文件
        
        Args:
            chunks: 文件块列表
            output_path: 输出文件路径
        """
        try:
            with open(output_path, 'wb') as f:
                for chunk in chunks:
                    f.write(chunk)
            logger.info(f"文件合并完成: {output_path}")
        except Exception as e:
            logger.error(f"文件合并失败: {e}")
            raise
    
    def create_task_directory(self, task_id: str) -> str:
        """
        创建任务目录
        
        Args:
            task_id: 任务ID
            
        Returns:
            str: 任务目录路径
        """
        task_dir = os.path.join(self.work_dir, task_id)
        os.makedirs(task_dir, exist_ok=True)
        logger.info(f"创建任务目录: {task_dir}")
        return task_dir
    
    def save_input_file(self, task_id: str, file_data: bytes) -> str:
        """
        保存任务输入文件
        
        Args:
            task_id: 任务ID
            file_data: 文件数据
            
        Returns:
            str: 输入文件路径
        """
        input_file_path = os.path.join(self.work_dir, task_id)
        
        try:
            with open(input_file_path, 'wb') as f:
                f.write(file_data)
            logger.info(f"保存输入文件: {input_file_path}")
            return input_file_path
        except Exception as e:
            logger.error(f"保存输入文件失败: {e}")
            raise
    
    def get_output_files(self, task_id: str) -> Dict[str, str]:
        """
        获取任务输出文件
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict[str, str]: 输出文件路径字典 {'line': path, 'grid': path}
        """
        task_dir = os.path.join(self.work_dir, task_id)
        line_file = os.path.join(task_dir, f'{task_id}.line')
        grid_file = os.path.join(task_dir, f'{task_id}.grid')
        
        output_files = {}
        
        if os.path.exists(line_file):
            output_files['line'] = line_file
        else:
            logger.warning(f"Line文件不存在: {line_file}")
        
        if os.path.exists(grid_file):
            output_files['grid'] = grid_file
        else:
            logger.warning(f"Grid文件不存在: {grid_file}")
        
        return output_files
    
    def rename_output_files(self, task_id: str) -> bool:
        """
        重命名输出文件（tl.line -> {task_id}.line, tl.grid -> {task_id}.grid）
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否成功
        """
        task_dir = os.path.join(self.work_dir, task_id)
        
        try:
            # 重命名 tl.line
            tl_line = os.path.join(task_dir, 'tl.line')
            if os.path.exists(tl_line):
                line_file = os.path.join(task_dir, f'{task_id}.line')
                os.rename(tl_line, line_file)
                logger.info(f"重命名文件: {tl_line} -> {line_file}")
            
            # 重命名 tl.grid
            tl_grid = os.path.join(task_dir, 'tl.grid')
            if os.path.exists(tl_grid):
                grid_file = os.path.join(task_dir, f'{task_id}.grid')
                os.rename(tl_grid, grid_file)
                logger.info(f"重命名文件: {tl_grid} -> {grid_file}")
            
            return True
        except Exception as e:
            logger.error(f"重命名输出文件失败: {e}")
            return False
    
    def read_file_as_base64(self, file_path: str) -> Optional[str]:
        """
        读取文件并转换为Base64编码
        
        Args:
            file_path: 文件路径
            
        Returns:
            Optional[str]: Base64编码的文件内容，失败返回None
        """
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
            return base64.b64encode(file_data).decode('utf-8')
        except Exception as e:
            logger.error(f"读取文件失败: {e}")
            return None
    
    def save_base64_file(self, file_path: str, base64_data: str) -> bool:
        """
        保存Base64编码的文件
        
        Args:
            file_path: 文件路径
            base64_data: Base64编码的数据
            
        Returns:
            bool: 是否成功
        """
        try:
            file_data = base64.b64decode(base64_data)
            with open(file_path, 'wb') as f:
                f.write(file_data)
            logger.info(f"保存Base64文件: {file_path}")
            return True
        except Exception as e:
            logger.error(f"保存Base64文件失败: {e}")
            return False
    
    def cleanup_task_directory(self, task_id: str) -> bool:
        """
        清理任务目录
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否成功
        """
        task_dir = os.path.join(self.work_dir, task_id)
        try:
            import shutil
            shutil.rmtree(task_dir)
            logger.info(f"清理任务目录: {task_dir}")
            return True
        except Exception as e:
            logger.error(f"清理任务目录失败: {e}")
            return False
