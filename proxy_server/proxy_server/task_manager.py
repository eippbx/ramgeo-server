import asyncio
import logging
import uuid
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from shared.constants import (
    TaskStatus, TaskPriority, TaskInfo, MessageType, Message
)


logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self, config: dict):
        self.config = config
        self.tasks: Dict[str, TaskInfo] = {}
        self.pending_tasks: List[TaskInfo] = []
        self.node_config = config.get("node", {})
        self.max_retries = self.node_config.get("max_retries", 5)
        self.retry_delay = self.node_config.get("retry_delay", 5)
        self.task_timeout = 3600
        self._processing_task = None
        self._timeout_check_task = None

    async def start(self):
        logger.info("Starting TaskManager")
        self._processing_task = asyncio.create_task(self._process_pending_tasks())
        self._timeout_check_task = asyncio.create_task(self._check_task_timeouts())

    async def stop(self):
        logger.info("Stopping TaskManager")
        if self._processing_task:
            self._processing_task.cancel()
        if self._timeout_check_task:
            self._timeout_check_task.cancel()
        await asyncio.gather(
            self._processing_task, self._timeout_check_task,
            return_exceptions=True
        )

    async def _process_pending_tasks(self):
        while True:
            try:
                if self.pending_tasks:
                    await self._assign_tasks()
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in task processing loop: {e}")

    async def _check_task_timeouts(self):
        while True:
            try:
                await asyncio.sleep(60)
                await self._check_timeouts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in timeout check loop: {e}")

    async def _assign_tasks(self):
        from proxy_server.node_manager import NodeManager
        from proxy_server.load_balancer import LoadBalancer
        
        if not hasattr(self, 'node_manager') or not hasattr(self, 'load_balancer'):
            return
        
        available_nodes = self.node_manager.get_available_nodes()
        if not available_nodes:
            logger.debug("No available nodes to assign tasks")
            return
        
        tasks_to_remove = []
        for i, task in enumerate(self.pending_tasks):
            if not task.file_uploaded:
                logger.debug(f"Task {task.task_id} has no input file uploaded yet, putting back to queue")
                continue
            
            selected_node = self.load_balancer.select_node(task, available_nodes)
            if selected_node:
                task.status = TaskStatus.RUNNING
                task.node_id = selected_node.node_id
                task.started_at = datetime.utcnow()
                self.node_manager.assign_task_to_node(selected_node.node_id, task.task_id)
                tasks_to_remove.append(i)
                logger.info(f"Task {task.task_id} assigned to node {selected_node.node_id}")
                
                if hasattr(self, 'websocket_server') and self.websocket_server:
                    file_path = f"./uploads/{task.task_id}.in"
                    success = await self.websocket_server.send_task_to_node(
                        selected_node.node_id, task, file_path
                    )
                    if not success:
                        logger.error(f"Failed to send task {task.task_id} to node {selected_node.node_id}")
                        task.status = TaskStatus.PENDING
                        task.node_id = None
                        task.started_at = None
                        self.node_manager.remove_task_from_node(selected_node.node_id, task.task_id)
                        continue
                
                if selected_node not in available_nodes:
                    available_nodes = self.node_manager.get_available_nodes()
                    if not available_nodes:
                        break
        
        for i in sorted(tasks_to_remove, reverse=True):
            self.pending_tasks.pop(i)

    async def _check_timeouts(self):
        now = datetime.utcnow()
        for task_id, task in self.tasks.items():
            if task.status == TaskStatus.RUNNING:
                if task.started_at:
                    elapsed = (now - task.started_at).total_seconds()
                    if elapsed > self.task_timeout:
                        logger.warning(f"Task {task_id} timed out after {elapsed} seconds")
                        await self._handle_task_timeout(task)

    async def _handle_task_timeout(self, task: TaskInfo):
        task.status = TaskStatus.FAILED
        task.error = "Task execution timeout"
        task.completed_at = datetime.utcnow()
        
        if task.node_id:
            from proxy_server.node_manager import NodeManager
            if hasattr(self, 'node_manager'):
                self.node_manager.remove_task_from_node(task.node_id, task.task_id)
        
        if task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = TaskStatus.PENDING
            task.node_id = None
            task.started_at = None
            task.error = None
            self._add_to_pending_queue(task)
            logger.info(f"Task {task.task_id} will be retried (attempt {task.retry_count}/{task.max_retries})")
        else:
            logger.error(f"Task {task.task_id} failed after {task.retry_count} retries")

    def create_task(self, task_type: str, parameters: dict, 
                   priority: TaskPriority = TaskPriority.NORMAL, 
                   task_id: Optional[str] = None) -> TaskInfo:
        if task_id is None:
            task_id = uuid.uuid4().hex
        task = TaskInfo(task_id, task_type, parameters, priority)
        self.tasks[task_id] = task
        self._add_to_pending_queue(task)
        logger.info(f"Created task {task_id} with type {task_type} and priority {priority.value}")
        return task

    def _add_to_pending_queue(self, task: TaskInfo):
        priority_order = {
            TaskPriority.URGENT: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.NORMAL: 2,
            TaskPriority.LOW: 3
        }
        task.priority_value = priority_order.get(task.priority, 2)
        self.pending_tasks.append(task)
        self.pending_tasks.sort(key=lambda t: (t.priority_value, t.created_at))
        logger.debug(f"Task {task.task_id} added to pending queue (position: {len(self.pending_tasks)})")

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        return self.tasks.get(task_id)

    def get_all_tasks(self, status: Optional[TaskStatus] = None, 
                     limit: int = 100, offset: int = 0) -> List[TaskInfo]:
        tasks = list(self.tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[offset:offset + limit]

    def get_task_count(self, status: Optional[TaskStatus] = None) -> int:
        if status:
            return len([t for t in self.tasks.values() if t.status == status])
        return len(self.tasks)

    def update_task_status(self, task_id: str, status: TaskStatus, 
                          error: Optional[str] = None, result: Optional[dict] = None):
        task = self.get_task(task_id)
        if task:
            task.status = status
            if error:
                task.error = error
            if result:
                task.result = result
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                task.completed_at = datetime.utcnow()
                if task.node_id:
                    from proxy_server.node_manager import NodeManager
                    if hasattr(self, 'node_manager'):
                        self.node_manager.remove_task_from_node(task.node_id, task_id)
            logger.info(f"Task {task_id} status updated to {status.value}")

    def handle_task_complete(self, task_id: str, result: Optional[dict] = None):
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = datetime.utcnow()
            if task.node_id:
                from proxy_server.node_manager import NodeManager
                if hasattr(self, 'node_manager'):
                    self.node_manager.remove_task_from_node(task.node_id, task_id)
            logger.info(f"Task {task_id} completed successfully")

    def handle_task_failed(self, task_id: str, error: str):
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.error = error
            task.completed_at = datetime.utcnow()
            
            if task.node_id:
                from proxy_server.node_manager import NodeManager
                if hasattr(self, 'node_manager'):
                    self.node_manager.remove_task_from_node(task.node_id, task_id)
            
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                task.node_id = None
                task.started_at = None
                task.error = None
                task.completed_at = None
                self._add_to_pending_queue(task)
                logger.info(f"Task {task_id} will be retried (attempt {task.retry_count}/{task.max_retries})")
            else:
                logger.error(f"Task {task_id} failed after {task.retry_count} retries: {error}")

    def cancel_task(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if task and task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.utcnow()
            if task.task_id in [t.task_id for t in self.pending_tasks]:
                self.pending_tasks = [t for t in self.pending_tasks if t.task_id != task_id]
            if task.node_id:
                from proxy_server.node_manager import NodeManager
                if hasattr(self, 'node_manager'):
                    self.node_manager.remove_task_from_node(task.node_id, task_id)
            logger.info(f"Task {task_id} cancelled")
            return True
        return False

    def set_file_uploaded(self, task_id: str, file_path: str):
        task = self.get_task(task_id)
        if task:
            task.file_uploaded = True
            task.input_file_path = file_path
            logger.info(f"Task {task_id} input file uploaded: {file_path}")

    def mark_file_uploaded(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if task:
            task.file_uploaded = True
            logger.info(f"Task {task_id} marked as file uploaded")
            return True
        return False

    def is_file_uploaded(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        return task.file_uploaded if task else False

    def get_input_file_path(self, task_id: str) -> Optional[str]:
        task = self.get_task(task_id)
        return task.input_file_path if task else None

    def add_output_file(self, task_id: str, file_type: str, file_path: str):
        task = self.get_task(task_id)
        if task:
            task.output_files[file_type] = file_path
            logger.info(f"Task {task_id} output file added: {file_type} -> {file_path}")

    def get_output_file(self, task_id: str, file_type: str) -> Optional[str]:
        task = self.get_task(task_id)
        if task:
            return task.output_files.get(file_type)
        return None

    def get_task_stats(self) -> dict:
        return {
            "total_tasks": len(self.tasks),
            "pending_tasks": self.get_task_count(TaskStatus.PENDING),
            "running_tasks": self.get_task_count(TaskStatus.RUNNING),
            "completed_tasks": self.get_task_count(TaskStatus.COMPLETED),
            "failed_tasks": self.get_task_count(TaskStatus.FAILED),
            "cancelled_tasks": self.get_task_count(TaskStatus.CANCELLED)
        }

    def set_node_manager(self, node_manager):
        self.node_manager = node_manager

    def set_load_balancer(self, load_balancer):
        self.load_balancer = load_balancer

    def set_websocket_server(self, websocket_server):
        self.websocket_server = websocket_server
