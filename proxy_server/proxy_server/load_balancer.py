import random
import logging
from typing import List, Optional, Dict
from shared.constants import (
    LoadBalancingStrategy, TaskInfo, TaskPriority
)


logger = logging.getLogger(__name__)


class LoadBalancer:
    def __init__(self, config: dict):
        self.config = config
        lb_config = config.get("load_balancing", {})
        self.strategy = LoadBalancingStrategy(lb_config.get("strategy", "LEAST_CONNECTIONS"))
        self.weights = lb_config.get("weights", {})
        self.affinity_timeout = lb_config.get("affinity_timeout", 300)
        self.affinity_cache: Dict[str, str] = {}
        self.round_robin_index = 0
        
        node_config = config.get("node", {})
        self.max_cpu = node_config.get("max_cpu", 0.90)
        self.max_memory = node_config.get("max_memory", 0.90)
        self.max_disk = node_config.get("max_disk", 0.90)

    def select_node(self, task: TaskInfo, available_nodes: List) -> Optional:
        if not available_nodes:
            logger.warning("No available nodes for task assignment")
            return None
        
        eligible_nodes = self._filter_eligible_nodes(available_nodes)
        
        if not eligible_nodes:
            logger.warning("No eligible nodes after capability filtering")
            return None
        
        if self.strategy == LoadBalancingStrategy.RANDOM:
            return self._select_random(eligible_nodes)
        elif self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
            return self._select_round_robin(eligible_nodes)
        elif self.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
            return self._select_least_connections(eligible_nodes)
        elif self.strategy == LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN:
            return self._select_weighted_round_robin(eligible_nodes)
        elif self.strategy == LoadBalancingStrategy.WEIGHTED_LEAST_CONNECTIONS:
            return self._select_weighted_least_connections(eligible_nodes)
        elif self.strategy == LoadBalancingStrategy.LEAST_LOAD:
            return self._select_least_load(eligible_nodes)
        elif self.strategy == LoadBalancingStrategy.AFFINITY:
            return self._select_affinity(task, eligible_nodes)
        else:
            logger.warning(f"Unknown load balancing strategy: {self.strategy}, using LEAST_CONNECTIONS")
            return self._select_least_connections(eligible_nodes)
    
    def _filter_eligible_nodes(self, available_nodes: List) -> List:
        eligible_nodes = []
        for node in available_nodes:
            if (node.load.cpu_usage <= self.max_cpu and
                node.load.memory_usage <= self.max_memory and
                node.load.disk_usage <= self.max_disk):
                eligible_nodes.append(node)
            else:
                logger.debug(f"Node {node.node_id} excluded due to resource constraints: "
                           f"CPU={node.load.cpu_usage:.2f}, Memory={node.load.memory_usage:.2f}, "
                           f"Disk={node.load.disk_usage:.2f}")
        
        logger.debug(f"Filtered {len(available_nodes)} nodes to {len(eligible_nodes)} eligible nodes")
        return eligible_nodes

    def _select_random(self, available_nodes: List) -> Optional:
        selected = random.choice(available_nodes)
        logger.debug(f"Selected node {selected.node_id} using RANDOM strategy")
        return selected

    def _select_round_robin(self, available_nodes: List) -> Optional:
        if not available_nodes:
            return None
        
        selected = available_nodes[self.round_robin_index % len(available_nodes)]
        self.round_robin_index += 1
        logger.debug(f"Selected node {selected.node_id} using ROUND_ROBIN strategy (index: {self.round_robin_index})")
        return selected

    def _select_least_connections(self, available_nodes: List) -> Optional:
        selected = min(available_nodes, key=lambda node: len(node.active_tasks))
        logger.debug(f"Selected node {selected.node_id} using LEAST_CONNECTIONS strategy (active tasks: {len(selected.active_tasks)})")
        return selected

    def _select_weighted_round_robin(self, available_nodes: List) -> Optional:
        if not available_nodes:
            return None
        
        node_weights = []
        total_weight = 0
        for node in available_nodes:
            weight = self.weights.get(node.node_id, 1)
            node_weights.append((node, weight))
            total_weight += weight
        
        if total_weight == 0:
            return self._select_least_connections(available_nodes)
        
        import random
        rand = random.uniform(0, total_weight)
        cumulative = 0
        selected = None
        for node, weight in node_weights:
            cumulative += weight
            if rand <= cumulative:
                selected = node
                break
        
        if not selected:
            selected = node_weights[-1][0]
        
        logger.debug(f"Selected node {selected.node_id} using WEIGHTED_ROUND_ROBIN strategy (weight: {self.weights.get(selected.node_id, 1)})")
        return selected

    def _select_weighted_least_connections(self, available_nodes: List) -> Optional:
        if not available_nodes:
            return None
        
        def weighted_score(node):
            weight = self.weights.get(node.node_id, 1)
            connections = len(node.active_tasks)
            return connections / weight if weight > 0 else float('inf')
        
        selected = min(available_nodes, key=weighted_score)
        score = weighted_score(selected)
        weight = self.weights.get(selected.node_id, 1)
        logger.debug(f"Selected node {selected.node_id} using WEIGHTED_LEAST_CONNECTIONS strategy "
                   f"(score: {score:.2f}, weight: {weight})")
        return selected

    def _select_least_load(self, available_nodes: List) -> Optional:
        def calculate_load_score(node):
            cpu_load = node.load.cpu_usage * 0.4
            memory_load = node.load.memory_usage * 0.3
            task_load = (len(node.active_tasks) / 5) * 0.3
            return cpu_load + memory_load + task_load
        
        selected = min(available_nodes, key=calculate_load_score)
        score = calculate_load_score(selected)
        logger.debug(f"Selected node {selected.node_id} using LEAST_LOAD strategy (score: {score:.2f})")
        return selected

    def _select_affinity(self, task: TaskInfo, available_nodes: List) -> Optional:
        task_type = task.task_type
        affinity_key = f"{task_type}_{task.priority.value}"
        
        cached_node_id = self.affinity_cache.get(affinity_key)
        if cached_node_id:
            for node in available_nodes:
                if node.node_id == cached_node_id:
                    logger.debug(f"Selected node {node.node_id} using AFFINITY strategy (cached)")
                    return node
        
        selected = self._select_least_connections(available_nodes)
        if selected:
            self.affinity_cache[affinity_key] = selected.node_id
            logger.debug(f"Selected node {selected.node_id} using AFFINITY strategy (new affinity)")
        return selected

    def clear_affinity_cache(self, task_type: Optional[str] = None):
        if task_type:
            keys_to_remove = [k for k in self.affinity_cache.keys() if k.startswith(task_type)]
            for key in keys_to_remove:
                del self.affinity_cache[key]
            logger.debug(f"Cleared affinity cache for task type: {task_type}")
        else:
            self.affinity_cache.clear()
            logger.debug("Cleared all affinity cache")

    def update_node_weight(self, node_id: str, weight: int):
        self.weights[node_id] = weight
        logger.info(f"Updated node {node_id} weight to {weight}")

    def get_node_weight(self, node_id: str) -> int:
        return self.weights.get(node_id, 1)

    def set_strategy(self, strategy: LoadBalancingStrategy):
        self.strategy = strategy
        logger.info(f"Load balancing strategy changed to {strategy.value}")
