#!/usr/bin/env python3
"""
日志管理模块
提供统一的日志配置和记录功能
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

# 日志级别映射
LOG_LEVEL_MAP = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}


def setup_logging(
    logger_name: str,
    log_level: str = 'INFO',
    log_dir: str = './logs',
    log_format: Optional[str] = None,
    rotation_size: str = '100MB',
    backup_count: int = 10
) -> logging.Logger:
    """
    设置日志记录器
    
    Args:
        logger_name: 日志记录器名称
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: 日志文件存储目录
        log_format: 日志格式
        rotation_size: 日志文件轮转大小
        backup_count: 保留的日志文件数量
    
    Returns:
        配置好的日志记录器对象
    """
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    # 确保日志目录相对于项目根目录创建
    if not Path(log_dir).is_absolute():
        log_dir = str(project_root / log_dir)
    # 创建日志目录
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    # 创建日志记录器
    logger = logging.getLogger(logger_name)
    logger.setLevel(LOG_LEVEL_MAP.get(log_level, logging.INFO))
    logger.propagate = False
    
    # 清除已有的处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 默认日志格式
    if not log_format:
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(LOG_LEVEL_MAP.get(log_level, logging.INFO))
    console_formatter = logging.Formatter(log_format)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 创建文件处理器
    log_file = Path(log_dir) / f'{logger_name}.log'
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(LOG_LEVEL_MAP.get(log_level, logging.INFO))
    file_formatter = logging.Formatter(log_format)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # 添加轮转功能
    try:
        from logging.handlers import RotatingFileHandler
        rotating_handler = RotatingFileHandler(
            log_file,
            maxBytes=_get_bytes_from_str(rotation_size),
            backupCount=backup_count,
            encoding='utf-8'
        )
        rotating_handler.setLevel(LOG_LEVEL_MAP.get(log_level, logging.INFO))
        rotating_handler.setFormatter(file_formatter)
        logger.addHandler(rotating_handler)
    except ImportError:
        logger.warning('无法导入RotatingFileHandler，日志文件将不会自动轮转')
    
    return logger


def get_logger(logger_name: str) -> logging.Logger:
    """
    获取日志记录器
    
    Args:
        logger_name: 日志记录器名称
    
    Returns:
        日志记录器对象
    """
    return logging.getLogger(logger_name)


def _get_bytes_from_str(size_str: str) -> int:
    """
    将字符串大小转换为字节数
    
    Args:
        size_str: 大小字符串，如 '100MB', '1GB'
    
    Returns:
        字节数
    """
    size_str = size_str.strip().upper()
    
    # 提取数字和单位
    import re
    match = re.match(r'(\d+)([KMGTPE]?B)?', size_str)
    if not match:
        raise ValueError(f'无效的大小格式: {size_str}')
    
    size = int(match.group(1))
    unit = match.group(2) or 'B'
    
    # 单位转换系数
    units = {
        'B': 1,
        'KB': 1024,
        'MB': 1024 ** 2,
        'GB': 1024 ** 3,
        'TB': 1024 ** 4,
        'PB': 1024 ** 5,
        'EB': 1024 ** 6
    }
    
    return size * units[unit]


def log_exception(
    logger: logging.Logger,
    error: Exception,
    message: str = '发生异常',
    extra: Optional[Dict] = None
):
    """
    记录异常信息
    
    Args:
        logger: 日志记录器
        error: 异常对象
        message: 错误消息
        extra: 额外的上下文信息
    """
    if extra is None:
        extra = {}
    
    logger.error(
        f'{message}: {str(error)}',
        exc_info=error,
        extra=extra
    )


# 默认日志记录器
DEFAULT_LOGGER = setup_logging(__name__)
