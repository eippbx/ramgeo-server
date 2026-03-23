"""
节点管理器
管理所有计算节点的状态、连接和负载
"""

import asyncio
import json
import logging
import time
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from enum import Enum
import statistics
from collections import defaultdict

from shared.config import Config
from shared.logger import setup_logging
from shared.metrics import MetricsCollector
from shared.database import DatabaseManager
from shared.redis_client import RedisClient
from shared.exceptions import NodeError

logger = setup_logging(__name__)

class NodeStatus(Enum):
    """节点状态枚举"""
    UNKNOWN = "unknown"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    BUSY = "busy"
    IDLE = "idle"
    OFFLINE = "offline"

class LoadBalancingStrategy(Enum):
    """负载均衡策略"""
    RANDOM = "random"
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_LOAD = "least_load"
    AFFINITY = "affinity"

class NodeManager:
    """节点管理器"""
    
    def __init__(self, config: Config, db: DatabaseManager, 
                 redis: RedisClient, metrics: MetricsCollector):
        self.config = config
        self.db = db
        self.redis = redis
        self.metrics = metrics
        
        # 节点状态存储
        self.nodes: Dict[str, Dict] = {}
        self.node_status: Dict[str, NodeStatus] = {}
        self.node_connections: Dict[str, str] = {}
        self.node_capabilities: Dict[str, Dict] = {}
        self.node_metrics: Dict[str, Dict] = {}
        self.node_load: Dict[str, int] = defaultdict(int)
        
        # 负载均衡
        self.lb_strategy = LoadBalancingStrategy(
            config.get('load_balancing.strategy', 'least_connections')
        )
        self.node_weights: Dict[str, float] = {}
        self.round_robin_index = 0
        
        # 订阅管理
        self.node_subscribers: Dict[str, Set[str]] = defaultdict(set)
        
        # 任务映射
        self.node_tasks: Dict[str, Set[str]] = defaultdict(set)
        self.task_nodes: Dict[str, str] = {}
        
        # 健康检查
        self.health_check_interval = config.get('node.health_check_interval', 60)
        self.heartbeat_timeout = config.get('websocket.heartbeat_timeout', 60)
        self.max_failures = config.get('node.max_failures', 3)
        self.node_failures: Dict[str, int] = defaultdict(int)
        
        # 统计信息
        self.start_time = datetime.now()
        self.total_nodes_registered = 0
        self.total_nodes_failed = 0
        
        # 锁
        self.lock = asyncio.Lock()
        
        # 后台任务
        self.background_tasks = []
        self.running = True
    
    async def start_discovery(self):
        """启动节点发现服务"""
        logger.info("启动节点发现服务...")
        
        # 从数据库加载已知节点
        await self._load_nodes_from_database()
        
        # 启动健康检查
        health_task = asyncio.create_task(self._health_check_loop())
        self.background_tasks.append(health_task)
        
        # 启动状态同步
        sync_task = asyncio.create_task(self._sync_status_loop())
        self.background_tasks.append(sync_task)
        
        # 启动负载计算
        load_task = asyncio.create_task(self._calculate_load_loop())
        self.background_tasks.append(load_task)
        
        logger.info("节点发现服务启动完成")
    
    async def shutdown(self):
        """关闭节点管理器"""
        logger.info("关闭节点管理器...")
        
        self.running = False
        
        # 取消所有后台任务
        for task in self.background_tasks:
            task.cancel()
        
        # 等待任务完成
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        # 保存节点状态到数据库
        await self._save_nodes_to_database()
        
        logger.info("节点管理器关闭完成")
    
    async def node_connected(self, node_id: str, connection_id: str):
        """节点连接成功"""
        async with self.lock:
            if node_id not in self.nodes:
                # 新节点，创建记录
                self.nodes[node_id] = {
                    'id': node_id,
                    'first_seen': datetime.now().isoformat(),
                    'last_seen': datetime.now().isoformat(),
                    'connection_id': connection_id,
                    'total_tasks': 0,
                    'failed_tasks': 0,
                    'total_runtime': 0,
                }
                self.total_nodes_registered += 1
            
            self.node_connections[node_id] = connection_id
            self.node_status[node_id] = NodeStatus.CONNECTED
            self.nodes[node_id]['last_seen'] = datetime.now().isoformat()
            self.nodes[node_id]['connection_id'] = connection_id
            self.node_failures[node_id] = 0
            
            logger.info(f"节点连接成功: {node_id}")
            
            # 更新指标
            self.metrics.set_gauge('active_nodes', len(self.get_active_nodes()))
            self.metrics.increment_counter('node_connections')
    
    async def node_disconnected(self, node_id: str):
        """节点断开连接"""
        async with self.lock:
            if node_id in self.node_status:
                self.node_status[node_id] = NodeStatus.OFFLINE
                
                # 清除连接信息
                if node_id in self.node_connections:
                    del self.node_connections[node_id]
                
                logger.info(f"节点断开连接: {node_id}")
                
                # 更新指标
                self.metrics.set_gauge('active_nodes', len(self.get_active_nodes()))
                self.metrics.decrement_counter('node_connections')
                
                # 处理节点上的任务
                await self._handle_node_disconnection_tasks(node_id)
    
    async def _handle_node_disconnection_tasks(self, node_id: str):
        """处理节点断开时的任务"""
        if node_id in self.node_tasks:
            tasks = self.node_tasks[node_id].copy()
            
            for task_id in tasks:
                # 重新分配任务
                await self._reassign_task(task_id)
                
                # 从节点任务列表中移除
                self.node_tasks[node_id].remove(task_id)
                if task_id in self.task_nodes:
                    del self.task_nodes[task_id]
            
            logger.info(f"节点 {node_id} 断开，重新分配了 {len(tasks)} 个任务")
    
    async def _reassign_task(self, task_id: str):
        """重新分配任务"""
        # 这里需要与任务管理器交互来重新分配任务
        # 简化实现：记录任务需要重新分配
        await self.redis.publish('task_reassign', json.dumps({
            'task_id': task_id,
            'reason': 'node_disconnected',
            'timestamp': datetime.now().isoformat()
        }))
    
    async def update_node_heartbeat(self, node_id: str):
        """更新节点心跳"""
        async with self.lock:
            if node_id in self.nodes:
                self.nodes[node_id]['last_heartbeat'] = datetime.now().isoformat()
                self.nodes[node_id]['last_seen'] = datetime.now().isoformat()
                
                # 如果节点之前不健康，标记为健康
                if self.node_status.get(node_id) in [NodeStatus.UNHEALTHY, NodeStatus.OFFLINE]:
                    self.node_status[node_id] = NodeStatus.HEALTHY
                    self.node_failures[node_id] = 0
                    logger.info(f"节点恢复健康: {node_id}")
    
    async def update_node_activity(self, node_id: str):
        """更新节点活动时间"""
        async with self.lock:
            if node_id in self.nodes:
                self.nodes[node_id]['last_activity'] = datetime.now().isoformat()
    
    async def update_node_status(self, node_id: str, status_data: Dict):
        """更新节点状态"""
        async with self.lock:
            if node_id not in self.nodes:
                return
            
            # 更新节点信息
            self.nodes[node_id].update({
                'last_status_update': datetime.now().isoformat(),
                'status_data': status_data
            })
            
            # 更新节点指标
            if 'metrics' in status_data:
                self.node_metrics[node_id] = status_data['metrics']
                
                # 计算节点负载
                await self._calculate_node_load(node_id, status_data['metrics'])
            
            # 更新节点状态
            if 'status' in status_data:
                try:
                    self.node_status[node_id] = NodeStatus(status_data['status'])
                except ValueError:
                    logger.warning(f"未知的节点状态: {status_data['status']}")
            
            logger.debug(f"节点状态更新: {node_id} - {status_data}")
    
    async def update_node_capabilities(self, node_id: str, capabilities: Dict):
        """更新节点能力"""
        async with self.lock:
            self.node_capabilities[node_id] = capabilities
            
            # 更新节点权重
            await self._update_node_weight(node_id, capabilities)
            
            logger.info(f"节点能力更新: {node_id} - {capabilities}")
    
    async def _update_node_weight(self, node_id: str, capabilities: Dict):
        """更新节点权重"""
        weight = 1.0  # 基础权重
        
        # 根据CPU核心数调整权重
        cpu_cores = capabilities.get('cpu_cores', 1)
        weight *= min(cpu_cores / 4, 2.0)  # 最多2倍
        
        # 根据内存调整权重
        memory_gb = capabilities.get('memory_gb', 4)
        weight *= min(memory_gb / 16, 1.5)  # 最多1.5倍
        
        # 根据RAMGEO版本调整权重
        ramgeo_version = capabilities.get('ramgeo_version', '1.0')
        if ramgeo_version >= '1.5':
            weight *= 1.2
        
        # 根据节点类型调整权重
        node_type = capabilities.get('node_type', 'general')
        if node_type == 'high_performance':
            weight *= 2.0
        elif node_type == 'gpu_accelerated':
            weight *= 3.0
        
        self.node_weights[node_id] = max(0.1, min(weight, 5.0))  # 限制在0.1-5.0之间
    
    async def _calculate_node_load(self, node_id: str, metrics: Dict):
        """计算节点负载"""
        load = 0
        
        # CPU负载
        cpu_load = metrics.get('cpu_load', 0)
        load += cpu_load * 0.4  # CPU权重40%
        
        # 内存使用率
        memory_usage = metrics.get('memory_usage', 0)
        load += memory_usage * 0.3  # 内存权重30%
        
        # 活动任务数
        active_tasks = metrics.get('active_tasks', 0)
        max_tasks = self.node_capabilities.get(node_id, {}).get('max_tasks', 10)
        task_load = min(active_tasks / max_tasks, 1.0)
        load += task_load * 0.3  # 任务权重30%
        
        # 磁盘IO（如果有）
        disk_io = metrics.get('disk_io', 0)
        load += min(disk_io, 0.1)  # 磁盘权重最多10%
        
        self.node_load[node_id] = min(load, 1.0)
        
        # 根据负载更新节点状态
        if load > 0.8:
            self.node_status[node_id] = NodeStatus.BUSY
        elif load < 0.2:
            self.node_status[node_id] = NodeStatus.IDLE
    
    async def mark_node_unhealthy(self, node_id: str):
        """标记节点不健康"""
        async with self.lock:
            if node_id in self.node_status:
                self.node_failures[node_id] += 1
                
                if self.node_failures[node_id] >= self.max_failures:
                    self.node_status[node_id] = NodeStatus.UNHEALTHY
                    logger.warning(f"节点标记为不健康: {node_id} (失败次数: {self.node_failures[node_id]})")
                    
                    # 发送告警
                    await self._send_node_alert(node_id, 'unhealthy')
                else:
                    logger.warning(f"节点心跳失败: {node_id} (失败次数: {self.node_failures[node_id]})")
    
    async def _send_node_alert(self, node_id: str, alert_type: str):
        """发送节点告警"""
        alert_data = {
            'node_id': node_id,
            'alert_type': alert_type,
            'timestamp': datetime.now().isoformat(),
            'failures': self.node_failures.get(node_id, 0),
            'status': self.node_status.get(node_id, NodeStatus.UNKNOWN).value
        }
        
        # 发布到Redis
        await self.redis.publish('node_alerts', json.dumps(alert_data))
        
        # 记录日志
        logger.warning(f"节点告警: {node_id} - {alert_type}")
    
    async def select_node_for_task(self, task_requirements: Dict) -> Optional[str]:
        """为任务选择节点"""
        async with self.lock:
            # 获取可用节点
            available_nodes = self.get_available_nodes()
            
            if not available_nodes:
                logger.warning("没有可用节点")
                return None
            
            # 筛选满足要求的节点
            suitable_nodes = []
            for node_id in available_nodes:
                if await self._check_node_suitability(node_id, task_requirements):
                    suitable_nodes.append(node_id)
            
            if not suitable_nodes:
                logger.warning("没有满足要求的节点")
                return None
            
            # 根据负载均衡策略选择节点
            if self.lb_strategy == LoadBalancingStrategy.RANDOM:
                return random.choice(suitable_nodes)
            
            elif self.lb_strategy == LoadBalancingStrategy.ROUND_ROBIN:
                selected_index = self.round_robin_index % len(suitable_nodes)
                self.round_robin_index += 1
                return suitable_nodes[selected_index]
            
            elif self.lb_strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
                return min(suitable_nodes, key=lambda x: len(self.node_tasks.get(x, set())))
            
            elif self.lb_strategy == LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN:
                # 加权随机选择
                weights = [self.node_weights.get(node_id, 1.0) for node_id in suitable_nodes]
                return random.choices(suitable_nodes, weights=weights, k=1)[0]
            
            elif self.lb_strategy == LoadBalancingStrategy.LEAST_LOAD:
                return min(suitable_nodes, key=lambda x: self.node_load.get(x, 0))
            
            else:
                # 默认使用最少连接
                return min(suitable_nodes, key=lambda x: len(self.node_tasks.get(x, set())))
    
    async def _check_node_suitability(self, node_id: str, requirements: Dict) -> bool:
        """检查节点是否满足任务要求"""
        # 检查节点状态
        if self.node_status.get(node_id) not in [NodeStatus.HEALTHY, NodeStatus.IDLE]:
            return False
        
        # 检查节点负载
        node_load = self.node_load.get(node_id, 0)
        max_load = requirements.get('max_load', 0.8)
        if node_load > max_load:
            return False
        
        # 检查节点能力
        capabilities = self.node_capabilities.get(node_id, {})
        
        # 检查RAMGEO版本
        required_version = requirements.get('ramgeo_version')
        if required_version:
            node_version = capabilities.get('ramgeo_version', '1.0')
            if node_version < required_version:
                return False
        
        # 检查内存要求
        required_memory = requirements.get('required_memory')
        if required_memory:
            available_memory = capabilities.get('memory_gb', 0) * 1024  # 转换为MB
            if available_memory < required_memory:
                return False
        
        # 检查CPU要求
        required_cpu = requirements.get('required_cpu')
        if required_cpu:
            available_cpu = capabilities.get('cpu_cores', 1)
            if available_cpu < required_cpu:
                return False
        
        # 检查特殊硬件要求
        special_requirements = requirements.get('special_requirements', [])
        node_special = capabilities.get('special_capabilities', [])
        
        for req in special_requirements:
            if req not in node_special:
                return False
        
        return True
    
    def get_available_nodes(self) -> List[str]:
        """获取可用节点列表"""
        available = []
        for node_id, status in self.node_status.items():
            if status in [NodeStatus.HEALTHY, NodeStatus.IDLE]:
                available.append(node_id)
        return available
    
    def get_active_nodes(self) -> List[str]:
        """获取活动节点列表"""
        active = []
        for node_id, status in self.node_status.items():
            if status not in [NodeStatus.OFFLINE, NodeStatus.UNKNOWN]:
                active.append(node_id)
        return active
    
    def get_total_nodes(self) -> int:
        """获取总节点数"""
        return len(self.nodes)
    
    async def assign_task_to_node(self, node_id: str, task_id: str):
        """分配任务到节点"""
        async with self.lock:
            if node_id not in self.node_tasks:
                self.node_tasks[node_id] = set()
            
            self.node_tasks[node_id].add(task_id)
            self.task_nodes[task_id] = node_id
            
            # 更新节点任务计数
            if node_id in self.nodes:
                self.nodes[node_id]['total_tasks'] = self.nodes[node_id].get('total_tasks', 0) + 1
            
            logger.debug(f"任务 {task_id} 分配给节点 {node_id}")
    
    async def remove_task_from_node(self, task_id: str):
        """从节点移除任务"""
        async with self.lock:
            if task_id in self.task_nodes:
                node_id = self.task_nodes[task_id]
                
                if node_id in self.node_tasks:
                    self.node_tasks[node_id].discard(task_id)
                
                del self.task_nodes[task_id]
                
                logger.debug(f"任务 {task_id} 从节点 {node_id} 移除")
    
    async def get_node_info(self, node_id: str) -> Optional[Dict]:
        """获取节点详细信息"""
        async with self.lock:
            if node_id not in self.nodes:
                return None
            
            info = self.nodes[node_id].copy()
            info['status'] = self.node_status.get(node_id, NodeStatus.UNKNOWN).value
            info['capabilities'] = self.node_capabilities.get(node_id, {})
            info['metrics'] = self.node_metrics.get(node_id, {})
            info['load'] = self.node_load.get(node_id, 0)
            info['active_tasks'] = len(self.node_tasks.get(node_id, set()))
            info['weight'] = self.node_weights.get(node_id, 1.0)
            info['failures'] = self.node_failures.get(node_id, 0)
            
            # 计算节点健康分数
            info['health_score'] = await self._calculate_node_health_score(node_id)
            
            return info
    
    async def get_all_nodes_info(self) -> List[Dict]:
        """获取所有节点信息"""
        async with self.lock:
            nodes_info = []
            for node_id in self.nodes.keys():
                node_info = await self.get_node_info(node_id)
                if node_info:
                    nodes_info.append(node_info)
            return nodes_info
    
    async def _calculate_node_health_score(self, node_id: str) -> float:
        """计算节点健康分数"""
        score = 1.0
        
        # 状态扣分
        status = self.node_status.get(node_id)
        if status == NodeStatus.UNHEALTHY:
            score -= 0.5
        elif status == NodeStatus.BUSY:
            score -= 0.1
        elif status == NodeStatus.OFFLINE:
            return 0.0
        
        # 失败次数扣分
        failures = self.node_failures.get(node_id, 0)
        score -= min(failures * 0.1, 0.3)
        
        # 负载扣分
        load = self.node_load.get(node_id, 0)
        if load > 0.8:
            score -= 0.2
        elif load > 0.9:
            score -= 0.4
        
        # 任务失败率扣分
        node_data = self.nodes.get(node_id, {})
        total_tasks = node_data.get('total_tasks', 0)
        failed_tasks = node_data.get('failed_tasks', 0)
        
        if total_tasks > 0:
            failure_rate = failed_tasks / total_tasks
            score -= min(failure_rate, 0.3)
        
        return max(0.0, min(score, 1.0))
    
    async def subscribe_to_node(self, user_id: str, node_id: str):
        """订阅节点更新"""
        async with self.lock:
            self.node_subscribers[node_id].add(user_id)
    
    async def unsubscribe_from_node(self, user_id: str, node_id: str):
        """取消订阅节点更新"""
        async with self.lock:
            if node_id in self.node_subscribers:
                self.node_subscribers[node_id].discard(user_id)
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self.running:
            try:
                await self.check_health()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查循环错误: {e}")
                await asyncio.sleep(60)  # 出错后等待1分钟
    
    async def check_health(self):
        """执行健康检查"""
        async with self.lock:
            current_time = datetime.now()
            
            for node_id, node_data in self.nodes.items():
                # 检查心跳超时
                last_heartbeat = node_data.get('last_heartbeat')
                if last_heartbeat:
                    try:
                        last_time = datetime.fromisoformat(last_heartbeat.replace('Z', '+00:00'))
                        time_diff = (current_time - last_time).total_seconds()
                        
                        if time_diff > self.heartbeat_timeout:
                            await self.mark_node_unhealthy(node_id)
                    except Exception as e:
                        logger.error(f"解析心跳时间失败 {node_id}: {e}")
            
            logger.debug("健康检查完成")
    
    async def _sync_status_loop(self):
        """状态同步循环"""
        while self.running:
            try:
                await self._sync_nodes_status()
                await asyncio.sleep(30)  # 每30秒同步一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"状态同步循环错误: {e}")
                await asyncio.sleep(60)
    
    async def _sync_nodes_status(self):
        """同步节点状态到数据库"""
        try:
            nodes_info = await self.get_all_nodes_info()
            
            # 保存到数据库
            for node_info in nodes_info:
                await self.db.execute(
                    """
                    INSERT INTO nodes (node_id, info, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (node_id) DO UPDATE
                    SET info = EXCLUDED.info, updated_at = NOW()
                    """,
                    node_info['id'], json.dumps(node_info)
                )
            
            logger.debug(f"同步了 {len(nodes_info)} 个节点状态到数据库")
            
        except Exception as e:
            logger.error(f"同步节点状态失败: {e}")
    
    async def _calculate_load_loop(self):
        """负载计算循环"""
        while self.running:
            try:
                await self._update_all_node_loads()
                await asyncio.sleep(10)  # 每10秒计算一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"负载计算循环错误: {e}")
                await asyncio.sleep(30)
    
    async def _update_all_node_loads(self):
        """更新所有节点负载"""
        async with self.lock:
            for node_id in self.nodes.keys():
                metrics = self.node_metrics.get(node_id, {})
                await self._calculate_node_load(node_id, metrics)
    
    async def _load_nodes_from_database(self):
        """从数据库加载节点"""
        try:
            rows = await self.db.fetch("SELECT node_id, info FROM nodes")
            
            for row in rows:
                node_id = row['node_id']
                info = json.loads(row['info'])
                
                self.nodes[node_id] = info
                self.node_status[node_id] = NodeStatus(info.get('status', 'unknown'))
                
                if 'capabilities' in info:
                    self.node_capabilities[node_id] = info['capabilities']
                
                logger.info(f"从数据库加载节点: {node_id}")
            
            logger.info(f"从数据库加载了 {len(rows)} 个节点")
            
        except Exception as e:
            logger.error(f"从数据库加载节点失败: {e}")
    
    async def _save_nodes_to_database(self):
        """保存节点到数据库"""
        try:
            nodes_info = await self.get_all_nodes_info()
            
            for node_info in nodes_info:
                await self.db.execute(
                    """
                    INSERT INTO nodes (node_id, info, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (node_id) DO UPDATE
                    SET info = EXCLUDED.info, updated_at = NOW()
                    """,
                    node_info['id'], json.dumps(node_info)
                )
            
            logger.info(f"保存了 {len(nodes_info)} 个节点到数据库")
            
        except Exception as e:
            logger.error(f"保存节点到数据库失败: {e}")