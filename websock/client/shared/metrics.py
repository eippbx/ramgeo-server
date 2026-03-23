#!/usr/bin/env python3
"""
指标收集模块
用于收集系统和业务指标
"""

import time
import psutil
from typing import Dict, List, Optional, Any
from datetime import datetime


class MetricsCollector:
    """
    通用指标收集器
    """
    
    def __init__(self, collector_name: str = 'system'):
        self.collector_name = collector_name
        self.counters = {}  # 计数器
        self.gauges = {}  # 仪表盘
        self.histograms = {}  # 直方图
        self.start_time = time.time()
    
    def increment_counter(self, name: str, value: float = 1.0, labels: Optional[Dict] = None):
        """
        增加计数器
        
        Args:
            name: 指标名称
            value: 增加的值
            labels: 标签字典
        """
        key = self._get_metric_key(name, labels)
        if key not in self.counters:
            self.counters[key] = 0.0
        self.counters[key] += value
    
    def set_gauge(self, name: str, value: float, labels: Optional[Dict] = None):
        """
        设置仪表盘值
        
        Args:
            name: 指标名称
            value: 仪表盘值
            labels: 标签字典
        """
        key = self._get_metric_key(name, labels)
        self.gauges[key] = value
    
    def observe_histogram(self, name: str, value: float, labels: Optional[Dict] = None):
        """
        观察直方图值
        
        Args:
            name: 指标名称
            value: 观察值
            labels: 标签字典
        """
        key = self._get_metric_key(name, labels)
        if key not in self.histograms:
            self.histograms[key] = []
        self.histograms[key].append(value)
    
    def get_counter(self, name: str, labels: Optional[Dict] = None) -> float:
        """
        获取计数器值
        
        Args:
            name: 指标名称
            labels: 标签字典
        
        Returns:
            计数器值
        """
        key = self._get_metric_key(name, labels)
        return self.counters.get(key, 0.0)
    
    def get_gauge(self, name: str, labels: Optional[Dict] = None) -> float:
        """
        获取仪表盘值
        
        Args:
            name: 指标名称
            labels: 标签字典
        
        Returns:
            仪表盘值
        """
        key = self._get_metric_key(name, labels)
        return self.gauges.get(key, 0.0)
    
    def get_histogram(self, name: str, labels: Optional[Dict] = None) -> List[float]:
        """
        获取直方图值列表
        
        Args:
            name: 指标名称
            labels: 标签字典
        
        Returns:
            直方图值列表
        """
        key = self._get_metric_key(name, labels)
        return self.histograms.get(key, [])
    
    def collect_system_metrics(self) -> Dict[str, Any]:
        """
        收集系统指标
        
        Returns:
            系统指标字典
        """
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'uptime': time.time() - self.start_time,
            'cpu': {
                'usage_percent': psutil.cpu_percent(interval=0.1),
                'count': psutil.cpu_count(logical=True),
                'count_physical': psutil.cpu_count(logical=False)
            },
            'memory': {
                'total': psutil.virtual_memory().total,
                'available': psutil.virtual_memory().available,
                'used': psutil.virtual_memory().used,
                'percent': psutil.virtual_memory().percent
            },
            'disk': {
                'total': psutil.disk_usage('/').total,
                'used': psutil.disk_usage('/').used,
                'free': psutil.disk_usage('/').free,
                'percent': psutil.disk_usage('/').percent
            },
            'network': {
                'bytes_sent': psutil.net_io_counters().bytes_sent,
                'bytes_recv': psutil.net_io_counters().bytes_recv,
                'packets_sent': psutil.net_io_counters().packets_sent,
                'packets_recv': psutil.net_io_counters().packets_recv
            }
        }
        
        return metrics
    
    def collect_metrics(self) -> Dict[str, Any]:
        """
        收集所有指标
        
        Returns:
            所有指标字典
        """
        return {
            'counters': self.counters,
            'gauges': self.gauges,
            'histograms': {
                k: {
                    'count': len(v),
                    'min': min(v) if v else 0,
                    'max': max(v) if v else 0,
                    'avg': sum(v) / len(v) if v else 0
                }
                for k, v in self.histograms.items()
            },
            'system': self.collect_system_metrics()
        }
    
    def reset(self):
        """
        重置所有指标
        """
        self.counters.clear()
        self.gauges.clear()
        self.histograms.clear()
        self.start_time = time.time()
    
    def _get_metric_key(self, name: str, labels: Optional[Dict]) -> str:
        """
        获取指标键名
        
        Args:
            name: 指标名称
            labels: 标签字典
        
        Returns:
            指标键名
        """
        if not labels:
            return name
        
        # 将标签转换为字符串
        label_str = ','.join([f'{k}={v}' for k, v in sorted(labels.items())])
        return f'{name}[{label_str}]'


class NodeMetricsCollector(MetricsCollector):
    """
    计算节点指标收集器
    """
    
    def __init__(self, node_id: str):
        super().__init__(f'node_{node_id}')
        self.node_id = node_id
    
    def collect_node_metrics(self) -> Dict[str, Any]:
        """
        收集节点特定指标
        
        Returns:
            节点指标字典
        """
        system_metrics = self.collect_system_metrics()
        
        # 收集GPU指标（如果有）
        gpu_metrics = []
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            for gpu in gpus:
                gpu_metrics.append({
                    'id': gpu.id,
                    'name': gpu.name,
                    'load': gpu.load,
                    'memory_util': gpu.memoryUtil,
                    'memory_total': gpu.memoryTotal,
                    'memory_used': gpu.memoryUsed,
                    'temperature': gpu.temperature
                })
        except ImportError:
            pass
        except Exception:
            pass
        
        return {
            'node_id': self.node_id,
            'system': system_metrics,
            'gpu': gpu_metrics,
            'business': {
                'active_tasks': self.get_gauge('active_tasks'),
                'completed_tasks': self.get_counter('completed_tasks'),
                'failed_tasks': self.get_counter('failed_tasks'),
                'task_execution_time': {
                    'count': len(self.get_histogram('task_execution_time')),
                    'avg': sum(self.get_histogram('task_execution_time')) / len(self.get_histogram('task_execution_time')) if self.get_histogram('task_execution_time') else 0
                }
            }
        }


class ProxyMetricsCollector(MetricsCollector):
    """
    代理服务器指标收集器
    """
    
    def __init__(self):
        super().__init__('proxy')
    
    def collect_proxy_metrics(self) -> Dict[str, Any]:
        """
        收集代理服务器特定指标
        
        Returns:
            代理服务器指标字典
        """
        system_metrics = self.collect_system_metrics()
        
        return {
            'system': system_metrics,
            'business': {
                'total_nodes': self.get_gauge('total_nodes'),
                'active_nodes': self.get_gauge('active_nodes'),
                'pending_tasks': self.get_gauge('pending_tasks'),
                'running_tasks': self.get_gauge('running_tasks'),
                'completed_tasks': self.get_counter('completed_tasks'),
                'failed_tasks': self.get_counter('failed_tasks'),
                'http_requests': self.get_counter('http_requests'),
                'websocket_connections': self.get_gauge('websocket_connections')
            }
        }
