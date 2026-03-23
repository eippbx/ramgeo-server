"""
任务管理器
管理计算任务的调度、执行、监控和状态跟踪
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from enum import Enum
from collections import defaultdict, deque
import heapq

from shared.config import Config
from shared.logger import setup_logging
from shared.metrics import MetricsCollector
from shared.database import DatabaseManager
from shared.redis_client import RedisClient
from shared.exceptions import TaskError, NodeError
from shared.validators import validate_task_data, validate_file_data

logger = setup_logging(__name__)

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"        # 等待调度
    SCHEDULED = "scheduled"    # 已调度到节点
    RUNNING = "running"        # 正在执行
    COMPLETED = "completed"    # 执行成功
    FAILED = "failed"          # 执行失败
    CANCELLED = "cancelled"    # 已取消
    TIMEOUT = "timeout"        # 执行超时
    RETRYING = "retrying"      # 重试中

class TaskPriority(Enum):
    """任务优先级枚举"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3

class TaskType(Enum):
    """任务类型枚举"""
    RAMGEO = "ramgeo"          # RAMGEO计算任务
    VALIDATION = "validation"  # 数据验证任务
    POST_PROCESSING = "post_processing"  # 后处理任务
    BATCH = "batch"            # 批量任务

class TaskManager:
    """任务管理器"""
    
    def __init__(self, config: Config, db: DatabaseManager, redis: RedisClient,
                 node_manager, file_manager, metrics: MetricsCollector):
        self.config = config
        self.db = db
        self.redis = redis
        self.node_manager = node_manager
        self.file_manager = file_manager
        self.metrics = metrics
        
        # 任务存储
        self.tasks: Dict[str, Dict] = {}
        self.task_status: Dict[str, TaskStatus] = {}
        self.task_nodes: Dict[str, str] = {}  # task_id -> node_id
        self.node_tasks: Dict[str, Set[str]] = defaultdict(set)  # node_id -> task_ids
        
        # 任务队列
        self.task_queue = []  # 优先级队列 (priority, timestamp, task_id)
        self.task_retry_queue = deque()  # 重试队列
        
        # 订阅管理
        self.task_subscribers: Dict[str, Set[str]] = defaultdict(set)  # task_id -> user_ids
        self.user_tasks: Dict[str, Set[str]] = defaultdict(set)  # user_id -> task_ids
        
        # 依赖管理
        self.task_dependencies: Dict[str, Set[str]] = defaultdict(set)  # task_id -> depends_on
        self.task_dependents: Dict[str, Set[str]] = defaultdict(set)  # task_id -> dependent_tasks
        
        # 重试管理
        self.task_retries: Dict[str, int] = defaultdict(int)
        self.max_retries = config.get('task.max_retries', 3)
        self.retry_delay = config.get('task.retry_delay', 60)  # 秒
        
        # 超时管理
        self.task_timeouts: Dict[str, asyncio.Task] = {}
        self.default_timeout = config.get('task.default_timeout', 3600)  # 秒
        
        # 统计信息
        self.start_time = datetime.now()
        self.total_tasks_created = 0
        self.total_tasks_completed = 0
        self.total_tasks_failed = 0
        
        # 性能指标
        self.avg_execution_time = 0
        self.success_rate = 1.0
        
        # 异步锁
        self.lock = asyncio.Lock()
        
        # 后台任务
        self.background_tasks = []
        self.running = True
        
        # 调度器
        self.scheduler = None
        
        # 任务类型处理器
        self.task_handlers = {
            TaskType.RAMGEO.value: self._handle_ramgeo_task,
            TaskType.VALIDATION.value: self._handle_validation_task,
            TaskType.POST_PROCESSING.value: self._handle_post_processing_task,
            TaskType.BATCH.value: self._handle_batch_task,
        }
    
    async def start_scheduler(self):
        """启动任务调度器"""
        logger.info("启动任务调度器...")
        
        # 从数据库加载未完成的任务
        await self._load_pending_tasks()
        
        # 启动调度循环
        scheduler_task = asyncio.create_task(self._scheduler_loop())
        self.background_tasks.append(scheduler_task)
        
        # 启动重试检查
        retry_task = asyncio.create_task(self._retry_check_loop())
        self.background_tasks.append(retry_task)
        
        # 启动超时检查
        timeout_task = asyncio.create_task(self._timeout_check_loop())
        self.background_tasks.append(timeout_task)
        
        # 启动统计更新
        stats_task = asyncio.create_task(self._update_stats_loop())
        self.background_tasks.append(stats_task)
        
        # 启动清理任务
        cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.background_tasks.append(cleanup_task)
        
        logger.info("任务调度器启动完成")
    
    async def shutdown(self):
        """关闭任务管理器"""
        logger.info("关闭任务管理器...")
        
        self.running = False
        
        # 取消所有后台任务
        for task in self.background_tasks:
            task.cancel()
        
        # 取消所有超时检查任务
        for timeout_task in self.task_timeouts.values():
            timeout_task.cancel()
        
        # 等待任务完成
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        # 保存任务状态到数据库
        await self._save_tasks_to_database()
        
        logger.info("任务管理器关闭完成")
    
    async def create_task(self, user_id: str, task_data: Dict, 
                         priority: TaskPriority = TaskPriority.NORMAL,
                         task_type: str = TaskType.RAMGEO.value) -> Dict:
        """创建新任务"""
        try:
            # 验证任务数据
            if not validate_task_data(task_data):
                raise TaskError("无效的任务数据")
            
            # 生成任务ID
            task_id = self._generate_task_id()
            
            async with self.lock:
                # 创建任务记录
                task = {
                    'id': task_id,
                    'user_id': user_id,
                    'type': task_type,
                    'status': TaskStatus.PENDING.value,
                    'priority': priority.value,
                    'data': task_data,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat(),
                    'retry_count': 0,
                    'execution_time': None,
                    'result': None,
                    'error': None,
                    'metadata': {
                        'version': '1.0',
                        'created_by': user_id
                    }
                }
                
                # 检查依赖任务
                dependencies = task_data.get('dependencies', [])
                if dependencies:
                    # 验证依赖任务是否存在且已完成
                    for dep_id in dependencies:
                        if dep_id not in self.tasks:
                            raise TaskError(f"依赖任务不存在: {dep_id}")
                        
                        dep_status = self.task_status.get(dep_id)
                        if dep_status not in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                            task['status'] = TaskStatus.PENDING.value
                            self.task_dependencies[task_id].add(dep_id)
                            self.task_dependents[dep_id].add(task_id)
                
                # 存储任务
                self.tasks[task_id] = task
                self.task_status[task_id] = TaskStatus.PENDING
                self.user_tasks[user_id].add(task_id)
                
                # 更新统计
                self.total_tasks_created += 1
                self.metrics.increment_counter('tasks_created')
                
                # 保存到数据库
                await self._save_task_to_database(task)
                
                # 如果是独立任务或所有依赖已完成，加入调度队列
                if not dependencies or all(
                    self.task_status.get(dep_id) == TaskStatus.COMPLETED 
                    for dep_id in dependencies
                ):
                    await self._enqueue_task(task_id, priority)
                
                logger.info(f"创建任务成功: {task_id}, 用户: {user_id}, 类型: {task_type}")
                
                return {
                    'task_id': task_id,
                    'status': task['status'],
                    'created_at': task['created_at'],
                    'message': '任务创建成功'
                }
        
        except Exception as e:
            logger.error(f"创建任务失败: {e}")
            raise TaskError(f"创建任务失败: {str(e)}")
    
    async def _enqueue_task(self, task_id: str, priority: TaskPriority):
        """将任务加入调度队列"""
        task = self.tasks.get(task_id)
        if not task:
            return
        
        # 计算优先级分数（优先级越高，分数越小）
        priority_score = -priority.value  # 负值使得高优先级先出队
        
        # 添加时间戳确保FIFO顺序
        timestamp = time.time()
        
        # 加入优先级队列
        heapq.heappush(self.task_queue, (priority_score, timestamp, task_id))
        
        # 更新任务状态
        self.task_status[task_id] = TaskStatus.PENDING
        task['status'] = TaskStatus.PENDING.value
        task['updated_at'] = datetime.now().isoformat()
        
        logger.debug(f"任务加入调度队列: {task_id}, 优先级: {priority.value}")
    
    async def submit_task(self, user_id: str, file_data: bytes, filename: str,
                         parameters: Dict = None, priority: TaskPriority = TaskPriority.NORMAL) -> Dict:
        """提交RAMGEO计算任务（包含文件上传）"""
        try:
            # 验证文件
            if not validate_file_data(file_data, filename):
                raise TaskError("无效的文件数据")
            
            # 生成任务ID
            task_id = self._generate_task_id()
            
            # 保存文件
            file_info = await self.file_manager.save_uploaded_file(
                user_id, task_id, file_data, filename
            )
            
            # 准备任务数据
            task_data = {
                'input_file': file_info,
                'parameters': parameters or {},
                'user_id': user_id,
                'filename': filename,
                'file_size': len(file_data)
            }
            
            # 创建任务
            return await self.create_task(
                user_id=user_id,
                task_data=task_data,
                priority=priority,
                task_type=TaskType.RAMGEO.value
            )
            
        except Exception as e:
            logger.error(f"提交任务失败: {e}")
            raise TaskError(f"提交任务失败: {str(e)}")
    
    async def _scheduler_loop(self):
        """任务调度循环"""
        while self.running:
            try:
                await self._schedule_tasks()
                await asyncio.sleep(1)  # 每秒调度一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"调度循环错误: {e}")
                await asyncio.sleep(5)
    
    async def _schedule_tasks(self):
        """调度待处理任务"""
        scheduled_count = 0
        
        while self.task_queue and scheduled_count < 10:  # 每次最多调度10个任务
            # 从优先级队列中获取任务
            _, _, task_id = heapq.heappop(self.task_queue)
            
            async with self.lock:
                if task_id not in self.tasks:
                    continue
                
                task = self.tasks[task_id]
                
                # 检查任务状态
                if self.task_status[task_id] != TaskStatus.PENDING:
                    continue
                
                # 检查依赖
                dependencies = self.task_dependencies.get(task_id, set())
                if dependencies:
                    # 检查依赖是否都已完成
                    all_completed = all(
                        self.task_status.get(dep_id) == TaskStatus.COMPLETED
                        for dep_id in dependencies
                    )
                    
                    if not all_completed:
                        # 有未完成的依赖，放回队列
                        heapq.heappush(self.task_queue, (
                            -TaskPriority(task['priority']).value,
                            time.time(),
                            task_id
                        ))
                        continue
                
                # 选择节点
                node_id = await self._select_node_for_task(task)
                
                if node_id:
                    # 分配任务到节点
                    success = await self._assign_task_to_node(task_id, node_id)
                    
                    if success:
                        scheduled_count += 1
                        logger.info(f"任务调度成功: {task_id} -> {node_id}")
                    else:
                        # 调度失败，放回队列
                        heapq.heappush(self.task_queue, (
                            -TaskPriority(task['priority']).value,
                            time.time(),
                            task_id
                        ))
                else:
                    # 没有可用节点，放回队列
                    heapq.heappush(self.task_queue, (
                        -TaskPriority(task['priority']).value,
                        time.time(),
                        task_id
                    ))
                    await asyncio.sleep(1)  # 等待节点可用
        
        if scheduled_count > 0:
            logger.debug(f"本次调度了 {scheduled_count} 个任务")
    
    async def _select_node_for_task(self, task: Dict) -> Optional[str]:
        """为任务选择节点"""
        # 获取任务要求
        task_requirements = task['data'].get('requirements', {})
        
        # 特殊要求
        if task['type'] == TaskType.RAMGEO.value:
            task_requirements.update({
                'ramgeo_version': '1.5',
                'special_requirements': ['ramgeo']
            })
        
        # 从节点管理器选择节点
        return await self.node_manager.select_node_for_task(task_requirements)
    
    async def _assign_task_to_node(self, task_id: str, node_id: str) -> bool:
        """分配任务到节点"""
        try:
            task = self.tasks[task_id]
            
            # 准备任务数据
            task_data = {
                'task_id': task_id,
                'type': task['type'],
                'data': task['data'],
                'priority': task['priority'],
                'timeout': task['data'].get('timeout', self.default_timeout),
                'metadata': task['metadata']
            }
            
            # 通过WebSocket发送任务到节点
            success = await self.node_manager.assign_task_to_node(node_id, task_data)
            
            if success:
                # 更新任务状态
                self.task_status[task_id] = TaskStatus.SCHEDULED
                task['status'] = TaskStatus.SCHEDULED.value
                task['assigned_node'] = node_id
                task['scheduled_at'] = datetime.now().isoformat()
                task['updated_at'] = datetime.now().isoformat()
                
                # 更新映射关系
                self.task_nodes[task_id] = node_id
                self.node_tasks[node_id].add(task_id)
                
                # 启动超时检查
                self._start_timeout_check(task_id, task['data'].get('timeout', self.default_timeout))
                
                # 保存到数据库
                await self._save_task_to_database(task)
                
                # 更新指标
                self.metrics.increment_counter('tasks_scheduled')
                self.metrics.set_gauge('pending_tasks', len(self.task_queue))
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"分配任务到节点失败: {e}")
            return False
    
    async def update_task_progress(self, task_id: str, progress: float):
        """更新任务进度"""
        async with self.lock:
            if task_id not in self.tasks:
                logger.warning(f"更新进度失败，任务不存在: {task_id}")
                return
            
            task = self.tasks[task_id]
            task['progress'] = progress
            task['updated_at'] = datetime.now().isoformat()
            
            # 更新Redis缓存
            await self.redis.set(f"task:{task_id}:progress", progress, expire=300)
            
            # 通知订阅者
            await self._notify_task_progress(task_id, progress)
            
            logger.debug(f"任务进度更新: {task_id} - {progress:.2%}")
    
    async def update_task_status(self, task_id: str, status: TaskStatus, 
                               result: Dict = None, error: Dict = None):
        """更新任务状态"""
        async with self.lock:
            if task_id not in self.tasks:
                logger.warning(f"更新状态失败，任务不存在: {task_id}")
                return
            
            task = self.tasks[task_id]
            old_status = self.task_status.get(task_id)
            
            # 更新状态
            self.task_status[task_id] = status
            task['status'] = status.value
            task['updated_at'] = datetime.now().isoformat()
            
            if result:
                task['result'] = result
            
            if error:
                task['error'] = error
            
            # 如果任务完成，记录执行时间
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                if 'started_at' in task:
                    started_at = datetime.fromisoformat(task['started_at'])
                    task['execution_time'] = (datetime.now() - started_at).total_seconds()
                
                # 清理节点映射
                if task_id in self.task_nodes:
                    node_id = self.task_nodes[task_id]
                    self.node_tasks[node_id].discard(task_id)
                    del self.task_nodes[task_id]
                
                # 取消超时检查
                if task_id in self.task_timeouts:
                    self.task_timeouts[task_id].cancel()
                    del self.task_timeouts[task_id]
                
                # 处理依赖任务
                await self._handle_task_completion(task_id, status)
            
            # 保存到数据库
            await self._save_task_to_database(task)
            
            # 通知订阅者
            await self._notify_task_status(task_id, status, result, error)
            
            # 更新统计
            await self._update_task_statistics(task_id, status, old_status)
            
            logger.info(f"任务状态更新: {task_id} - {old_status} -> {status}")
    
    async def complete_task(self, task_id: str, result_data: Dict):
        """标记任务完成"""
        try:
            # 验证结果数据
            if not isinstance(result_data, dict):
                raise TaskError("无效的结果数据")
            
            # 获取输出文件
            output_files = result_data.get('output_files', [])
            
            # 保存结果文件
            if output_files:
                task = self.tasks.get(task_id)
                if task:
                    user_id = task.get('user_id')
                    await self.file_manager.save_task_results(
                        user_id, task_id, output_files, result_data
                    )
            
            # 更新任务状态
            await self.update_task_status(
                task_id,
                TaskStatus.COMPLETED,
                result=result_data
            )
            
            logger.info(f"任务完成: {task_id}")
            
        except Exception as e:
            logger.error(f"完成任务处理失败: {e}")
            await self.fail_task(task_id, {'error': str(e)})
    
    async def fail_task(self, task_id: str, error_data: Dict):
        """标记任务失败"""
        try:
            # 检查重试次数
            retry_count = self.task_retries.get(task_id, 0)
            
            if retry_count < self.max_retries:
                # 需要重试
                self.task_retries[task_id] = retry_count + 1
                
                await self.update_task_status(
                    task_id,
                    TaskStatus.RETRYING,
                    error=error_data
                )
                
                # 加入重试队列
                retry_time = datetime.now() + timedelta(seconds=self.retry_delay)
                self.task_retry_queue.append((retry_time, task_id))
                
                logger.info(f"任务进入重试队列: {task_id} (重试 {retry_count + 1}/{self.max_retries})")
                
            else:
                # 重试次数用尽，标记为失败
                await self.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    error=error_data
                )
                
                logger.warning(f"任务失败: {task_id} (已达到最大重试次数)")
                
        except Exception as e:
            logger.error(f"处理任务失败状态错误: {e}")
    
    async def cancel_task(self, task_id: str, reason: str = None):
        """取消任务"""
        async with self.lock:
            if task_id not in self.tasks:
                raise TaskError(f"任务不存在: {task_id}")
            
            status = self.task_status.get(task_id)
            
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                raise TaskError(f"任务已处于最终状态，无法取消: {status}")
            
            # 更新状态
            await self.update_task_status(
                task_id,
                TaskStatus.CANCELLED,
                error={'reason': reason or '用户取消'}
            )
            
            # 如果任务正在节点上运行，通知节点取消
            if task_id in self.task_nodes:
                node_id = self.task_nodes[task_id]
                await self.node_manager.cancel_node_task(node_id, task_id)
            
            logger.info(f"任务已取消: {task_id}, 原因: {reason}")
    
    async def get_task_info(self, task_id: str, user_id: str = None) -> Optional[Dict]:
        """获取任务信息"""
        async with self.lock:
            if task_id not in self.tasks:
                return None
            
            task = self.tasks[task_id].copy()
            
            # 检查权限
            if user_id and task['user_id'] != user_id:
                # 检查是否是管理员
                # 这里可以添加权限检查逻辑
                return None
            
            # 添加额外信息
            task['status'] = self.task_status[task_id].value
            
            # 获取进度
            progress = await self.redis.get(f"task:{task_id}:progress")
            if progress:
                task['progress'] = float(progress)
            
            # 获取节点信息
            if task_id in self.task_nodes:
                node_id = self.task_nodes[task_id]
                task['node_id'] = node_id
                
                # 获取节点状态
                node_info = await self.node_manager.get_node_info(node_id)
                if node_info:
                    task['node_info'] = node_info
            
            # 获取依赖任务状态
            dependencies = self.task_dependencies.get(task_id, set())
            if dependencies:
                task['dependencies'] = []
                for dep_id in dependencies:
                    dep_status = self.task_status.get(dep_id)
                    if dep_status:
                        task['dependencies'].append({
                            'task_id': dep_id,
                            'status': dep_status.value
                        })
            
            # 获取文件信息
            if task['type'] == TaskType.RAMGEO.value:
                file_info = await self.file_manager.get_task_files(task_id)
                if file_info:
                    task['files'] = file_info
            
            return task
    
    async def get_user_tasks(self, user_id: str, status_filter: List[str] = None,
                           limit: int = 100, offset: int = 0) -> List[Dict]:
        """获取用户的任务列表"""
        async with self.lock:
            user_task_ids = self.user_tasks.get(user_id, set())
            tasks = []
            
            for task_id in list(user_task_ids)[offset:offset+limit]:
                if task_id not in self.tasks:
                    continue
                
                task_status = self.task_status.get(task_id)
                
                # 状态过滤
                if status_filter and task_status.value not in status_filter:
                    continue
                
                task_info = await self.get_task_info(task_id, user_id)
                if task_info:
                    tasks.append(task_info)
            
            return tasks
    
    async def get_all_tasks(self, filters: Dict = None, limit: int = 100, 
                          offset: int = 0) -> List[Dict]:
        """获取所有任务（管理员）"""
        async with self.lock:
            tasks = []
            count = 0
            
            for task_id, task in self.tasks.items():
                # 应用过滤器
                if filters:
                    if not self._apply_filters(task, filters):
                        continue
                
                if count >= offset:
                    task_info = await self.get_task_info(task_id)
                    if task_info:
                        tasks.append(task_info)
                
                count += 1
                
                if len(tasks) >= limit:
                    break
            
            return tasks
    
    def _apply_filters(self, task: Dict, filters: Dict) -> bool:
        """应用过滤器"""
        for key, value in filters.items():
            if key == 'status':
                if self.task_status.get(task['id']).value != value:
                    return False
            elif key == 'user_id':
                if task.get('user_id') != value:
                    return False
            elif key == 'type':
                if task.get('type') != value:
                    return False
            elif key == 'date_from':
                created_at = datetime.fromisoformat(task['created_at'])
                date_from = datetime.fromisoformat(value)
                if created_at < date_from:
                    return False
            elif key == 'date_to':
                created_at = datetime.fromisoformat(task['created_at'])
                date_to = datetime.fromisoformat(value)
                if created_at > date_to:
                    return False
        
        return True
    
    async def subscribe_to_task(self, user_id: str, task_id: str):
        """订阅任务更新"""
        async with self.lock:
            if task_id in self.tasks:
                self.task_subscribers[task_id].add(user_id)
                logger.debug(f"用户订阅任务: {user_id} -> {task_id}")
    
    async def unsubscribe_from_task(self, user_id: str, task_id: str):
        """取消订阅任务更新"""
        async with self.lock:
            if task_id in self.task_subscribers:
                self.task_subscribers[task_id].discard(user_id)
                logger.debug(f"用户取消订阅任务: {user_id} -> {task_id}")
    
    async def get_task_subscribers(self, task_id: str) -> Set[str]:
        """获取任务订阅者"""
        return self.task_subscribers.get(task_id, set())
    
    async def _notify_task_progress(self, task_id: str, progress: float):
        """通知任务进度更新"""
        subscribers = self.task_subscribers.get(task_id, set())
        
        if not subscribers:
            return
        
        notification = {
            'type': 'task_progress',
            'task_id': task_id,
            'progress': progress,
            'timestamp': datetime.now().isoformat()
        }
        
        # 发布到Redis频道
        await self.redis.publish(f'task:{task_id}:updates', json.dumps(notification))
        
        # 直接通知WebSocket连接（如果实现的话）
        # 这里可以集成到WebSocket服务器
    
    async def _notify_task_status(self, task_id: str, status: TaskStatus,
                                result: Dict = None, error: Dict = None):
        """通知任务状态更新"""
        subscribers = self.task_subscribers.get(task_id, set())
        
        if not subscribers:
            return
        
        notification = {
            'type': 'task_status',
            'task_id': task_id,
            'status': status.value,
            'timestamp': datetime.now().isoformat()
        }
        
        if result:
            notification['result'] = result
        
        if error:
            notification['error'] = error
        
        # 发布到Redis频道
        await self.redis.publish(f'task:{task_id}:updates', json.dumps(notification))
    
    async def _handle_task_completion(self, task_id: str, status: TaskStatus):
        """处理任务完成后的依赖关系"""
        # 检查依赖此任务的其他任务
        dependents = self.task_dependents.get(task_id, set())
        
        for dependent_id in dependents:
            if dependent_id not in self.tasks:
                continue
            
            # 检查所有依赖是否都已完成
            dependencies = self.task_dependencies.get(dependent_id, set())
            all_completed = all(
                self.task_status.get(dep_id) == TaskStatus.COMPLETED
                for dep_id in dependencies
            )
            
            if all_completed:
                # 所有依赖都已完成，可以调度此任务
                task = self.tasks[dependent_id]
                priority = TaskPriority(task['priority'])
                await self._enqueue_task(dependent_id, priority)
                
                logger.debug(f"依赖任务完成，调度任务: {task_id} -> {dependent_id}")
    
    async def _retry_check_loop(self):
        """重试检查循环"""
        while self.running:
            try:
                await self._process_retry_queue()
                await asyncio.sleep(10)  # 每10秒检查一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"重试检查循环错误: {e}")
                await asyncio.sleep(30)
    
    async def _process_retry_queue(self):
        """处理重试队列"""
        current_time = datetime.now()
        
        while self.task_retry_queue:
            retry_time, task_id = self.task_retry_queue[0]
            
            if retry_time > current_time:
                break
            
            # 弹出队列
            self.task_retry_queue.popleft()
            
            async with self.lock:
                if task_id not in self.tasks:
                    continue
                
                task = self.tasks[task_id]
                
                # 检查任务状态
                if self.task_status[task_id] != TaskStatus.RETRYING:
                    continue
                
                # 重新调度任务
                priority = TaskPriority(task['priority'])
                await self._enqueue_task(task_id, priority)
                
                logger.info(f"重试任务: {task_id}")
    
    async def _timeout_check_loop(self):
        """超时检查循环"""
        while self.running:
            try:
                await self._check_task_timeouts()
                await asyncio.sleep(30)  # 每30秒检查一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"超时检查循环错误: {e}")
                await asyncio.sleep(60)
    
    async def _check_task_timeouts(self):
        """检查任务超时"""
        current_time = time.time()
        timeout_tasks = []
        
        async with self.lock:
            for task_id, task in self.tasks.items():
                status = self.task_status.get(task_id)
                
                if status not in [TaskStatus.SCHEDULED, TaskStatus.RUNNING]:
                    continue
                
                # 获取任务开始时间
                started_at = task.get('started_at') or task.get('scheduled_at')
                if not started_at:
                    continue
                
                try:
                    start_time = datetime.fromisoformat(started_at).timestamp()
                    timeout = task['data'].get('timeout', self.default_timeout)
                    
                    if current_time - start_time > timeout:
                        timeout_tasks.append(task_id)
                except Exception as e:
                    logger.error(f"检查任务超时失败 {task_id}: {e}")
        
        # 处理超时任务
        for task_id in timeout_tasks:
            await self.update_task_status(
                task_id,
                TaskStatus.TIMEOUT,
                error={'reason': '执行超时'}
            )
            
            logger.warning(f"任务执行超时: {task_id}")
    
    def _start_timeout_check(self, task_id: str, timeout: int):
        """启动超时检查任务"""
        async def check_timeout():
            await asyncio.sleep(timeout)
            
            async with self.lock:
                if task_id not in self.task_status:
                    return
                
                status = self.task_status[task_id]
                if status in [TaskStatus.SCHEDULED, TaskStatus.RUNNING]:
                    await self.update_task_status(
                        task_id,
                        TaskStatus.TIMEOUT,
                        error={'reason': '执行超时'}
                    )
        
        # 创建超时检查任务
        timeout_task = asyncio.create_task(check_timeout())
        self.task_timeouts[task_id] = timeout_task
    
    async def _update_stats_loop(self):
        """统计更新循环"""
        while self.running:
            try:
                await self._update_statistics()
                await asyncio.sleep(60)  # 每分钟更新一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"统计更新循环错误: {e}")
                await asyncio.sleep(300)
    
    async def _update_statistics(self):
        """更新统计信息"""
        try:
            total_tasks = len(self.tasks)
            completed_tasks = sum(1 for s in self.task_status.values() 
                                if s == TaskStatus.COMPLETED)
            failed_tasks = sum(1 for s in self.task_status.values() 
                             if s == TaskStatus.FAILED)
            
            # 计算成功率
            if completed_tasks + failed_tasks > 0:
                self.success_rate = completed_tasks / (completed_tasks + failed_tasks)
            
            # 计算平均执行时间
            execution_times = []
            for task in self.tasks.values():
                if task.get('execution_time'):
                    execution_times.append(task['execution_time'])
            
            if execution_times:
                self.avg_execution_time = sum(execution_times) / len(execution_times)
            
            # 保存统计到Redis
            stats = {
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'failed_tasks': failed_tasks,
                'success_rate': self.success_rate,
                'avg_execution_time': self.avg_execution_time,
                'pending_tasks': len(self.task_queue),
                'running_tasks': sum(1 for s in self.task_status.values() 
                                   if s == TaskStatus.RUNNING),
                'timestamp': datetime.now().isoformat()
            }
            
            await self.redis.set('task_statistics', json.dumps(stats), expire=300)
            
            # 更新指标
            self.metrics.set_gauge('total_tasks', total_tasks)
            self.metrics.set_gauge('completed_tasks', completed_tasks)
            self.metrics.set_gauge('failed_tasks', failed_tasks)
            self.metrics.set_gauge('task_success_rate', self.success_rate)
            self.metrics.set_gauge('avg_execution_time', self.avg_execution_time)
            
        except Exception as e:
            logger.error(f"更新统计信息失败: {e}")
    
    async def _update_task_statistics(self, task_id: str, new_status: TaskStatus, 
                                    old_status: TaskStatus):
        """更新任务统计"""
        if new_status == TaskStatus.COMPLETED:
            self.total_tasks_completed += 1
            self.metrics.increment_counter('tasks_completed')
        
        elif new_status == TaskStatus.FAILED:
            self.total_tasks_failed += 1
            self.metrics.increment_counter('tasks_failed')
    
    async def _cleanup_loop(self):
        """清理循环"""
        while self.running:
            try:
                await self._cleanup_old_tasks()
                await asyncio.sleep(3600)  # 每小时清理一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理循环错误: {e}")
                await asyncio.sleep(3600)
    
    async def _cleanup_old_tasks(self):
        """清理旧任务"""
        cutoff_time = datetime.now() - timedelta(days=7)  # 保留7天
        
        async with self.lock:
            tasks_to_remove = []
            
            for task_id, task in self.tasks.items():
                status = self.task_status.get(task_id)
                
                # 只清理已完成或失败的任务
                if status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    continue
                
                try:
                    updated_at = datetime.fromisoformat(task.get('updated_at', datetime.now().isoformat()))
                    if updated_at < cutoff_time:
                        tasks_to_remove.append(task_id)
                except (ValueError, KeyError):
                    continue
            
            # 移除旧任务
            for task_id in tasks_to_remove:
                await self._remove_task(task_id)
                logger.info(f"清理旧任务: {task_id}")
    
    async def _handle_ramgeo_task(self, task_id: str, task_data: Dict) -> bool:
        """处理RAMGEO计算任务"""
        try:
            # 选择合适的节点
            node_id = await self.node_manager.select_node(task_data.get('requirements', {}))
            if not node_id:
                logger.warning(f"没有可用的节点来执行任务: {task_id}")
                return False
            
            # 分配任务给节点
            success = await self._assign_task_to_node(task_id, node_id)
            if not success:
                logger.warning(f"无法将任务分配给节点: {task_id}, 节点: {node_id}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"处理RAMGEO任务失败: {task_id}, 错误: {e}")
            return False
    
    async def _handle_validation_task(self, task_id: str, task_data: Dict) -> bool:
        """处理数据验证任务"""
        try:
            # 选择合适的节点
            node_id = await self.node_manager.select_node(task_data.get('requirements', {}))
            if not node_id:
                logger.warning(f"没有可用的节点来执行验证任务: {task_id}")
                return False
            
            # 分配任务给节点
            success = await self._assign_task_to_node(task_id, node_id)
            if not success:
                logger.warning(f"无法将验证任务分配给节点: {task_id}, 节点: {node_id}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"处理验证任务失败: {task_id}, 错误: {e}")
            return False
    
    async def _handle_post_processing_task(self, task_id: str, task_data: Dict) -> bool:
        """处理后处理任务"""
        try:
            # 选择合适的节点
            node_id = await self.node_manager.select_node(task_data.get('requirements', {}))
            if not node_id:
                logger.warning(f"没有可用的节点来执行后处理任务: {task_id}")
                return False
            
            # 分配任务给节点
            success = await self._assign_task_to_node(task_id, node_id)
            if not success:
                logger.warning(f"无法将后处理任务分配给节点: {task_id}, 节点: {node_id}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"处理后处理任务失败: {task_id}, 错误: {e}")
            return False
    
    async def _handle_batch_task(self, task_id: str, task_data: Dict) -> bool:
        """处理批量任务"""
        try:
            # 选择合适的节点
            node_id = await self.node_manager.select_node(task_data.get('requirements', {}))
            if not node_id:
                logger.warning(f"没有可用的节点来执行批量任务: {task_id}")
                return False
            
            # 分配任务给节点
            success = await self._assign_task_to_node(task_id, node_id)
            if not success:
                logger.warning(f"无法将批量任务分配给节点: {task_id}, 节点: {node_id}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"处理批量任务失败: {task_id}, 错误: {e}")
            return False
    
    async def _load_pending_tasks(self):
        """从数据库加载待处理任务"""
        try:
            # 检查数据库连接是否可用
            if not hasattr(self.db, 'execute') or not hasattr(self.db, 'is_connected') or not self.db.is_connected or self.db.pool is None:
                logger.warning("数据库连接不可用，跳过加载待处理任务")
                return
            
            logger.info("从数据库加载待处理任务...")
            # 从数据库加载所有状态为PENDING的任务
            query = "SELECT * FROM tasks WHERE status = ?"
            rows = await self.db.fetch(query, TaskStatus.PENDING)
            
            # 使用局部锁而不是实例锁
            local_lock = asyncio.Lock()
            async with local_lock:
                for row in rows:
                    task_id = row['id']
                    # 仅当任务不在内存中时才加载
                    if task_id not in self.tasks:
                        task_data = {
                            'id': row['id'],
                            'type': row['type'],
                            'data': row['data'],
                            'priority': row['priority'],
                            'created_at': row['created_at'],
                            'updated_at': row['updated_at'],
                            'user_id': row.get('user_id')
                        }
                        
                        # 添加到任务队列
                        self.tasks[task_id] = task_data
                        priority = TaskPriority(task_data['priority'])
                        await self._enqueue_task(task_id, priority)
                        logger.info(f"加载待处理任务: {task_id}")
        except Exception as e:
            logger.error(f"加载待处理任务失败: {e}")
    
    async def _save_tasks_to_database(self):
        """保存任务到数据库"""
        try:
            # 检查数据库连接是否可用
            if not hasattr(self.db, 'execute') or not hasattr(self.db, 'is_connected') or not self.db.is_connected or self.db.pool is None:
                logger.warning("数据库连接不可用，跳过保存任务到数据库")
                return
            
            logger.info("保存任务到数据库...")
            # 使用局部锁而不是实例锁
            local_lock = asyncio.Lock()
            async with local_lock:
                for task_id, task in self.tasks.items():
                    status = self.task_status.get(task_id, TaskStatus.PENDING)
                    
                    # 检查任务是否已经在数据库中
                    check_query = "SELECT id FROM tasks WHERE id = ?"
                    existing = await self.db.fetchrow(check_query, task_id)
                    
                    # 准备任务数据
                    task_data = {
                        'id': task_id,
                        'type': task['type'],
                        'data': task.get('data', {}),
                        'status': status,
                        'priority': task.get('priority', TaskPriority.MEDIUM),
                        'created_at': task.get('created_at', datetime.now().isoformat()),
                        'updated_at': datetime.now().isoformat(),
                        'user_id': task.get('user_id')
                    }
                    
                    if existing:
                        # 更新现有任务
                        update_query = """
                            UPDATE tasks 
                            SET type = ?, data = ?, status = ?, priority = ?, 
                                updated_at = ?, user_id = ? 
                            WHERE id = ?
                        """
                        await self.db.execute(
                            update_query, 
                            task_data['type'], task_data['data'], task_data['status'],
                            task_data['priority'], task_data['updated_at'],
                            task_data['user_id'], task_id
                        )
                    else:
                        # 插入新任务
                        insert_query = """
                            INSERT INTO tasks 
                            (id, type, data, status, priority, created_at, updated_at, user_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """
                        await self.db.execute(
                            insert_query, 
                            task_id, task_data['type'], task_data['data'],
                            task_data['status'], task_data['priority'],
                            task_data['created_at'], task_data['updated_at'],
                            task_data['user_id']
                        )
        except Exception as e:
            logger.error(f"保存任务到数据库失败: {e}")
