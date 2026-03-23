#!/usr/bin/env python3
"""
任务执行器模块
实现任务执行、进程管理和并发控制功能
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Dict, Any, Optional, Callable, List

from shared.logger import setup_logging
from shared.exceptions import *
from shared.security import SecurityManager

logger = setup_logging(__name__)


class TaskExecutor:
    """
    任务执行器类
    """
    
    def __init__(self, config: Dict[str, Any], security_manager: SecurityManager):
        """
        初始化任务执行器
        
        Args:
            config: 配置信息
            security_manager: 安全管理器实例
        """
        self.config = config
        self.security_manager = security_manager
        
        # 任务执行配置
        self.max_workers = config.get('task_executor', {}).get('max_workers', 4)
        self.task_timeout = config.get('task_executor', {}).get('task_timeout', 3600)  # 默认1小时
        self.temp_dir = config.get('task_executor', {}).get('temp_dir', './temp')
        
        # 任务执行池
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.process_executor = ProcessPoolExecutor(max_workers=self.max_workers)
        
        # 任务状态
        self.running_tasks = {}
        self.task_status_callbacks = []
        
        # 初始化临时目录
        os.makedirs(self.temp_dir, exist_ok=True)
        
        logger.info(f"任务执行器初始化完成，最大工作线程数: {self.max_workers}")
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行任务
        
        Args:
            task: 任务信息
        
        Returns:
            任务执行结果
        """
        task_id = task.get('id')
        task_type = task.get('type')
        
        if not task_id or not task_type:
            raise TaskError("任务ID和类型不能为空")
        
        logger.info(f"开始执行任务: {task_id} (类型: {task_type})")
        
        # 记录任务开始时间
        start_time = time.time()
        
        # 更新任务状态
        await self.update_task_status(task_id, 'running')
        
        # 创建任务临时目录
        task_temp_dir = os.path.join(self.temp_dir, task_id)
        os.makedirs(task_temp_dir, exist_ok=True)
        
        try:
            # 根据任务类型执行不同的任务
            result = await self._execute_task_by_type(task_type, task, task_temp_dir)
            
            # 记录任务结束时间
            end_time = time.time()
            
            # 构建成功结果
            task_result = {
                'success': True,
                'task_id': task_id,
                'result': result,
                'execution_time': end_time - start_time,
                'start_time': start_time,
                'end_time': end_time
            }
            
            # 更新任务状态
            await self.update_task_status(task_id, 'completed', task_result)
            
            logger.info(f"任务执行完成: {task_id}")
            return task_result
            
        except Exception as e:
            # 记录任务结束时间
            end_time = time.time()
            
            # 构建失败结果
            task_result = {
                'success': False,
                'task_id': task_id,
                'error': str(e),
                'traceback': traceback.format_exc(),
                'execution_time': end_time - start_time,
                'start_time': start_time,
                'end_time': end_time
            }
            
            # 更新任务状态
            await self.update_task_status(task_id, 'failed', task_result)
            
            logger.error(f"任务执行失败: {task_id}, 错误: {e}")
            return task_result
            
        finally:
            # 清理任务
            await self._cleanup_task(task_id, task_temp_dir)
    
    async def _execute_task_by_type(self, task_type: str, task: Dict[str, Any], temp_dir: str) -> Any:
        """
        根据任务类型执行任务
        
        Args:
            task_type: 任务类型
            task: 任务信息
            temp_dir: 临时目录
        
        Returns:
            任务执行结果
        """
        task_id = task.get('id')
        params = task.get('params', {})
        
        try:
            if task_type == 'dem':
                return await self._execute_dem_task(params, temp_dir)
            elif task_type == 'image_processing':
                return await self._execute_image_processing_task(params, temp_dir)
            elif task_type == 'calculation':
                return await self._execute_calculation_task(params, temp_dir)
            else:
                raise TaskError(f"不支持的任务类型: {task_type}")
                
        except Exception as e:
            logger.error(f"执行{task_type}任务失败: {e}")
            raise TaskError(f"任务执行失败: {e}")
    
    async def _execute_dem_task(self, params: Dict[str, Any], temp_dir: str) -> Dict[str, Any]:
        """
        执行DEM（数字高程模型）相关任务
        
        Args:
            params: 任务参数
            temp_dir: 临时目录
        
        Returns:
            任务执行结果
        """
        logger.info(f"执行DEM任务，参数: {params}")
        
        # 模拟DEM任务执行
        await asyncio.sleep(5)  # 模拟耗时操作
        
        # 构建结果
        result = {
            'task_type': 'dem',
            'result': {
                'elevation_range': {'min': 0, 'max': 1000},
                'cell_count': 1000000,
                'processing_time': 5.23
            },
            'message': 'DEM任务执行完成'
        }
        
        return result
    
    async def _execute_image_processing_task(self, params: Dict[str, Any], temp_dir: str) -> Dict[str, Any]:
        """
        执行图像处理任务
        
        Args:
            params: 任务参数
            temp_dir: 临时目录
        
        Returns:
            任务执行结果
        """
        logger.info(f"执行图像处理任务，参数: {params}")
        
        # 模拟图像处理任务执行
        await asyncio.sleep(10)  # 模拟耗时操作
        
        # 构建结果
        result = {
            'task_type': 'image_processing',
            'result': {
                'processed_image_path': os.path.join(temp_dir, 'processed_image.tif'),
                'processing_operations': ['filter', 'resize', 'enhance'],
                'image_size': {'width': 1024, 'height': 768},
                'processing_time': 10.56
            },
            'message': '图像处理任务执行完成'
        }
        
        return result
    
    async def _execute_calculation_task(self, params: Dict[str, Any], temp_dir: str) -> Dict[str, Any]:
        """
        执行计算任务
        
        Args:
            params: 任务参数
            temp_dir: 临时目录
        
        Returns:
            任务执行结果
        """
        logger.info(f"执行计算任务，参数: {params}")
        
        # 提取计算参数
        calculation_type = params.get('calculation_type', 'addition')
        numbers = params.get('numbers', [])
        
        # 在进程池中执行计算任务
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self.process_executor,
            self._perform_calculation,
            calculation_type, numbers
        )
        
        # 构建结果
        result = {
            'task_type': 'calculation',
            'result': {
                'calculation_type': calculation_type,
                'input_numbers': numbers,
                'result': result,
                'processing_time': 2.12
            },
            'message': '计算任务执行完成'
        }
        
        return result
    
    def _perform_calculation(self, calculation_type: str, numbers: List[float]) -> float:
        """
        执行计算操作
        
        Args:
            calculation_type: 计算类型
            numbers: 数字列表
        
        Returns:
            计算结果
        """
        if not numbers:
            return 0.0
        
        if calculation_type == 'addition':
            return sum(numbers)
        elif calculation_type == 'subtraction':
            result = numbers[0]
            for num in numbers[1:]:
                result -= num
            return result
        elif calculation_type == 'multiplication':
            result = 1.0
            for num in numbers:
                result *= num
            return result
        elif calculation_type == 'division':
            result = numbers[0]
            for num in numbers[1:]:
                if num == 0:
                    raise ValueError("除数不能为零")
                result /= num
            return result
        elif calculation_type == 'average':
            return sum(numbers) / len(numbers)
        else:
            raise ValueError(f"不支持的计算类型: {calculation_type}")
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
        
        Returns:
            取消是否成功
        """
        logger.info(f"尝试取消任务: {task_id}")
        
        # 检查任务是否在运行
        if task_id not in self.running_tasks:
            logger.warning(f"任务{task_id}不在运行状态")
            return False
        
        # 取消任务
        try:
            # 从运行任务中获取任务信息
            task_info = self.running_tasks.get(task_id)
            
            # 如果是进程执行的任务，尝试终止进程
            if 'process' in task_info:
                process = task_info['process']
                if process and process.poll() is None:
                    process.terminate()
                    logger.info(f"已终止任务{task_id}的进程")
            
            # 更新任务状态
            await self.update_task_status(task_id, 'cancelled')
            
            return True
            
        except Exception as e:
            logger.error(f"取消任务{task_id}失败: {e}")
            return False
    
    async def update_task_status(self, task_id: str, status: str, result: Optional[Dict[str, Any]] = None) -> None:
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 任务状态
            result: 任务结果（可选）
        """
        # 更新任务状态
        task_status = {
            'task_id': task_id,
            'status': status,
            'timestamp': int(time.time()),
            'result': result
        }
        
        # 调用所有状态回调
        for callback in self.task_status_callbacks:
            await callback(task_status)
    
    def add_task_status_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        添加任务状态回调
        
        Args:
            callback: 回调函数
        """
        self.task_status_callbacks.append(callback)
    
    async def _cleanup_task(self, task_id: str, temp_dir: str) -> None:
        """
        清理任务资源
        
        Args:
            task_id: 任务ID
            temp_dir: 临时目录
        """
        try:
            # 从运行任务中移除
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
            
            # 清理临时目录
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logger.debug(f"已清理任务{task_id}的临时目录: {temp_dir}")
                
        except Exception as e:
            logger.error(f"清理任务{task_id}资源失败: {e}")
    
    async def get_running_tasks(self) -> Dict[str, Any]:
        """
        获取正在运行的任务
        
        Returns:
            正在运行的任务列表
        """
        return self.running_tasks
    
    async def shutdown(self) -> None:
        """
        关闭任务执行器
        """
        logger.info("正在关闭任务执行器...")
        
        # 关闭执行池
        self.executor.shutdown(wait=True)
        self.process_executor.shutdown(wait=True)
        
        # 清理所有任务
        for task_id in list(self.running_tasks.keys()):
            await self.cancel_task(task_id)
        
        # 清理临时目录
        try:
            shutil.rmtree(self.temp_dir)
            logger.info(f"已清理临时目录: {self.temp_dir}")
        except Exception as e:
            logger.error(f"清理临时目录失败: {e}")
        
        logger.info("任务执行器已关闭")
