#!/usr/bin/env python3
"""
验证模块
提供数据验证功能
"""

import json
import logging
from typing import Dict, Any, Optional

from shared.logger import setup_logging

logger = setup_logging(__name__)

def validate_task_data(task_data: Dict[str, Any]) -> bool:
    """
    验证任务数据
    
    Args:
        task_data: 任务数据
    
    Returns:
        验证是否通过
    """
    try:
        if not isinstance(task_data, dict):
            return False
        
        # 基本验证
        required_fields = ['task_type', 'parameters']
        for field in required_fields:
            if field not in task_data:
                return False
        
        # 验证任务类型
        valid_task_types = ['ramgeo', 'validation', 'post_processing', 'batch']
        if task_data['task_type'] not in valid_task_types:
            return False
        
        # 验证参数
        if not isinstance(task_data['parameters'], dict):
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"任务数据验证失败: {e}")
        return False

def validate_file_data(file_data: bytes, filename: str) -> bool:
    """
    验证文件数据
    
    Args:
        file_data: 文件数据
        filename: 文件名
    
    Returns:
        验证是否通过
    """
    try:
        if not isinstance(file_data, bytes):
            return False
        
        if not isinstance(filename, str):
            return False
        
        # 验证文件大小（不超过100MB）
        if len(file_data) > 100 * 1024 * 1024:
            return False
        
        # 验证文件名
        if not filename:
            return False
        
        # 验证文件扩展名
        valid_extensions = ['.tif', '.tiff', '.dem', '.hgt', '.zip']
        if not any(filename.lower().endswith(ext) for ext in valid_extensions):
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"文件数据验证失败: {e}")
        return False