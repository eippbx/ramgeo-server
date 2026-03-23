import asyncio
import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from shared.constants import (
    NodeStatus, NodeCapabilities, NodeLoad, MessageType, 
    WebSocketCloseCode, Message
)


logger = logging.getLogger(__name__)


class NodeInfo:
    def __init__(self, node_id: str, node_name: str, capabilities: NodeCapabilities,
                 ip_address: Optional[str] = None):
        self.node_id = node_id
        self.node_name = node_name
        self.capabilities = capabilities
        self.ip_address = ip_address
        self.status = NodeStatus.CONNECTED
        self.load = NodeLoad()
        self.active_tasks = set()
        self.registered_at = datetime.utcnow()
        self.last_heartbeat = datetime.utcnow()
        self.heartbeat_timeout_count = 0
        self.websocket = None
        self.is_draining = False

    def update_status(self, status: NodeStatus):
        self.status = status
        logger.info(f"Node {self.node_id} status changed to {status.value}")

    def update_load(self, load: NodeLoad):
        self.load = load
        self.active_tasks = set(range(load.active_tasks))

    def update_heartbeat(self):
        self.last_heartbeat = datetime.utcnow()
        self.heartbeat_timeout_count = 0
        if self.status == NodeStatus.UNHEALTHY:
            self.update_status(NodeStatus.HEALTHY)

    def increment_heartbeat_timeout(self):
        self.heartbeat_timeout_count += 1
        if self.heartbeat_timeout_count >= 3:
            if self.status == NodeStatus.HEALTHY:
                self.update_status(NodeStatus.UNHEALTHY)
                logger.warning(f"Node {self.node_id} marked as UNHEALTHY after 3 heartbeat timeouts")

    def add_task(self, task_id: str):
        self.active_tasks.add(task_id)
        self.load.active_tasks = len(self.active_tasks)

    def remove_task(self, task_id: str):
        self.active_tasks.discard(task_id)
        self.load.active_tasks = len(self.active_tasks)

    def set_draining(self, draining: bool):
        self.is_draining = draining
        if draining:
            self.update_status(NodeStatus.DRAINING)
        elif self.status == NodeStatus.DRAINING:
            self.update_status(NodeStatus.HEALTHY)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "status": self.status.value,
            "capabilities": self.capabilities.to_dict(),
            "load": self.load.to_dict(),
            "active_tasks": len(self.active_tasks),
            "last_heartbeat": self.last_heartbeat.isoformat() + "Z" if self.last_heartbeat else None,
            "ip_address": self.ip_address
        }


class NodeManager:
    def __init__(self, config: dict):
        self.config = config
        self.nodes: Dict[str, NodeInfo] = {}
        self.node_config = config.get("node", {})
        self.max_cpu = self.node_config.get("max_cpu", 0.90)
        self.max_memory = self.node_config.get("max_memory", 0.90)
        self.max_disk = self.node_config.get("max_disk", 0.90)
        self.max_failures = self.node_config.get("max_failures", 3)
        self.health_check_interval = self.node_config.get("health_check_interval", 60)
        self._health_check_task = None
        self._heartbeat_task = None

    async def start(self):
        logger.info("Starting NodeManager")
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self):
        logger.info("Stopping NodeManager")
        if self._health_check_task:
            self._health_check_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        await asyncio.gather(
            self._health_check_task, self._heartbeat_task, 
            return_exceptions=True
        )

    async def _health_check_loop(self):
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._check_node_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

    async def _heartbeat_loop(self):
        websocket_config = self.config.get("websocket", {})
        heartbeat_interval = websocket_config.get("heartbeat_interval", 30)
        while True:
            try:
                await asyncio.sleep(heartbeat_interval)
                await self._send_heartbeats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")

    async def _check_node_health(self):
        now = datetime.utcnow()
        websocket_config = self.config.get("websocket", {})
        heartbeat_timeout = websocket_config.get("heartbeat_timeout", 60)
        
        for node_id, node in self.nodes.items():
            if node.status == NodeStatus.OFFLINE:
                continue
            
            time_since_heartbeat = (now - node.last_heartbeat).total_seconds()
            if time_since_heartbeat > heartbeat_timeout:
                node.increment_heartbeat_timeout()
                logger.warning(f"Node {node_id} heartbeat timeout (count: {node.heartbeat_timeout_count}, time: {time_since_heartbeat:.1f}s)")
                
                if node.heartbeat_timeout_count >= 3:
                    logger.error(f"Node {node_id} heartbeat timeout exceeded threshold, unregistering node")
                    self.unregister_node(node_id)

    async def _send_heartbeats(self):
        heartbeat_msg = Message(MessageType.HEARTBEAT)
        for node_id, node in self.nodes.items():
            if node.status in [NodeStatus.HEALTHY, NodeStatus.UNHEALTHY, NodeStatus.BUSY, NodeStatus.IDLE]:
                if node.websocket:
                    try:
                        await node.websocket.send(heartbeat_msg.to_json())
                        logger.debug(f"Sent heartbeat to node {node_id}")
                    except Exception as e:
                        logger.error(f"Failed to send heartbeat to node {node_id}: {e}")

    def register_node(self, node_id: str, node_name: str, capabilities: NodeCapabilities,
                      websocket, ip_address: Optional[str] = None) -> bool:
        if node_id in self.nodes:
            logger.error(f"Node {node_id} is already registered")
            return False
        
        node = NodeInfo(node_id, node_name, capabilities, ip_address)
        node.websocket = websocket
        node.update_status(NodeStatus.HEALTHY)
        self.nodes[node_id] = node
        logger.info(f"Node {node_id} ({node_name}) registered successfully")
        return True

    def unregister_node(self, node_id: str):
        if node_id in self.nodes:
            node = self.nodes[node_id]
            node.update_status(NodeStatus.OFFLINE)
            node.websocket = None
            del self.nodes[node_id]
            logger.info(f"Node {node_id} unregistered and removed from node list")

    def get_node(self, node_id: str) -> Optional[NodeInfo]:
        return self.nodes.get(node_id)

    def get_all_nodes(self) -> List[NodeInfo]:
        return list(self.nodes.values())

    def get_healthy_nodes(self) -> List[NodeInfo]:
        return [node for node in self.nodes.values() 
                if node.status == NodeStatus.HEALTHY and not node.is_draining]

    def is_node_available(self, node: NodeInfo) -> bool:
        if node.status != NodeStatus.HEALTHY or node.is_draining:
            return False
        
        if node.load.cpu_usage >= self.max_cpu:
            logger.debug(f"Node {node.node_id} not available: CPU usage {node.load.cpu_usage:.2f} >= max {self.max_cpu:.2f}")
            return False
        
        if node.load.memory_usage >= self.max_memory:
            logger.debug(f"Node {node.node_id} not available: Memory usage {node.load.memory_usage:.2f} >= max {self.max_memory:.2f}")
            return False
        
        if node.load.disk_usage >= self.max_disk:
            logger.debug(f"Node {node.node_id} not available: Disk usage {node.load.disk_usage:.2f} >= max {self.max_disk:.2f}")
            return False
        
        return True

    def get_available_nodes(self) -> List[NodeInfo]:
        return [node for node in self.nodes.values() 
                if self.is_node_available(node)]

    def update_node_status(self, node_id: str, status: NodeStatus):
        node = self.get_node(node_id)
        if node:
            node.update_status(status)

    def update_node_load(self, node_id: str, load: NodeLoad):
        node = self.get_node(node_id)
        if node:
            node.update_load(load)
            
            if node.status == NodeStatus.HEALTHY:
                if load.cpu_usage >= self.max_cpu or load.memory_usage >= self.max_memory or load.disk_usage >= self.max_disk:
                    node.update_status(NodeStatus.BUSY)
                    logger.info(f"Node {node_id} marked as BUSY due to resource constraints: CPU={load.cpu_usage:.2f}, Memory={load.memory_usage:.2f}, Disk={load.disk_usage:.2f}")
            elif node.status == NodeStatus.BUSY:
                if load.cpu_usage < self.max_cpu and load.memory_usage < self.max_memory and load.disk_usage < self.max_disk:
                    node.update_status(NodeStatus.HEALTHY)
                    logger.info(f"Node {node_id} marked as HEALTHY: CPU={load.cpu_usage:.2f}, Memory={load.memory_usage:.2f}, Disk={load.disk_usage:.2f}")

    def handle_heartbeat_response(self, node_id: str):
        node = self.get_node(node_id)
        if node:
            node.update_heartbeat()
            logger.debug(f"Received heartbeat response from node {node_id}")

    def update_heartbeat(self, node_id: str):
        self.handle_heartbeat_response(node_id)

    def set_node_draining(self, node_id: str, draining: bool) -> bool:
        node = self.get_node(node_id)
        if node:
            node.set_draining(draining)
            logger.info(f"Node {node_id} draining set to {draining}")
            return True
        return False

    def activate_node(self, node_id: str) -> bool:
        node = self.get_node(node_id)
        if node:
            node.set_draining(False)
            if node.status == NodeStatus.OFFLINE:
                node.update_status(NodeStatus.HEALTHY)
            logger.info(f"Node {node_id} activated")
            return True
        return False

    def assign_task_to_node(self, node_id: str, task_id: str) -> bool:
        node = self.get_node(node_id)
        if node and self.is_node_available(node):
            node.add_task(task_id)
            logger.info(f"Task {task_id} assigned to node {node_id}")
            return True
        return False

    def remove_task_from_node(self, node_id: str, task_id: str):
        node = self.get_node(node_id)
        if node:
            node.remove_task(task_id)
            logger.info(f"Task {task_id} removed from node {node_id}")

    def get_node_stats(self) -> dict:
        total_nodes = len(self.nodes)
        healthy_nodes = len([n for n in self.nodes.values() if n.status == NodeStatus.HEALTHY])
        unhealthy_nodes = len([n for n in self.nodes.values() if n.status == NodeStatus.UNHEALTHY])
        offline_nodes = len([n for n in self.nodes.values() if n.status == NodeStatus.OFFLINE])
        draining_nodes = len([n for n in self.nodes.values() if n.is_draining])
        total_active_tasks = sum(len(n.active_tasks) for n in self.nodes.values())
        
        return {
            "total_nodes": total_nodes,
            "healthy_nodes": healthy_nodes,
            "unhealthy_nodes": unhealthy_nodes,
            "offline_nodes": offline_nodes,
            "draining_nodes": draining_nodes,
            "total_active_tasks": total_active_tasks
        }
