#!/usr/bin/env python3
"""
资源监控模块
实现节点资源监控功能
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable, List

import psutil

from shared.logger import setup_logging
from shared.exceptions import *

logger = setup_logging(__name__)


class ResourceMonitor:
    """
    资源监控器类
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化资源监控器
        
        Args:
            config: 配置信息
        """
        self.config = config
        
        # 监控配置
        self.monitor_interval = config.get('resource_monitor', {}).get('interval', 5)  # 监控间隔（秒）
        self.max_history = config.get('resource_monitor', {}).get('max_history', 100)  # 最大历史记录数
        
        # 监控历史数据
        self.cpu_history = []
        self.memory_history = []
        self.disk_history = []
        self.network_history = []
        self.process_history = []
        
        # 资源阈值
        self.resource_thresholds = config.get('resource_monitor', {}).get('thresholds', {
            'cpu': 80,  # CPU使用率阈值（%）
            'memory': 80,  # 内存使用率阈值（%）
            'disk': 80,  # 磁盘使用率阈值（%）
        })
        
        # 监控任务
        self.monitor_task = None
        self.is_monitoring = False
        
        # 资源使用回调
        self.resource_callbacks = []
        self.alert_callbacks = []
        
        logger.info(f"资源监控器初始化完成，监控间隔: {self.monitor_interval}秒")
    
    async def start_monitoring(self) -> None:
        """
        开始资源监控
        """
        if self.is_monitoring:
            logger.warning("资源监控已经在运行")
            return
        
        self.is_monitoring = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("资源监控已启动")
    
    async def stop_monitoring(self) -> None:
        """
        停止资源监控
        """
        if not self.is_monitoring:
            logger.warning("资源监控已经停止")
            return
        
        self.is_monitoring = False
        
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                logger.info("资源监控任务已取消")
            except Exception as e:
                logger.error(f"停止资源监控时发生错误: {e}")
        
        logger.info("资源监控已停止")
    
    async def _monitor_loop(self) -> None:
        """
        资源监控循环
        """
        try:
            while self.is_monitoring:
                # 获取资源使用情况
                resource_usage = await self.get_resource_usage()
                
                # 记录历史数据
                await self._record_history(resource_usage)
                
                # 检查资源阈值
                await self._check_thresholds(resource_usage)
                
                # 调用资源使用回调
                for callback in self.resource_callbacks:
                    await callback(resource_usage)
                
                # 等待下一次监控
                await asyncio.sleep(self.monitor_interval)
                
        except asyncio.CancelledError:
            logger.info("资源监控循环已取消")
        except Exception as e:
            logger.error(f"资源监控循环发生错误: {e}")
            # 重启监控
            self.is_monitoring = False
            await self.start_monitoring()
    
    async def get_resource_usage(self) -> Dict[str, Any]:
        """
        获取当前资源使用情况
        
        Returns:
            资源使用情况
        """
        try:
            # 获取CPU使用率
            cpu_usage = psutil.cpu_percent(interval=0.1)
            cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
            
            # 获取内存使用率
            mem = psutil.virtual_memory()
            memory_usage = mem.percent
            memory_used = mem.used
            memory_free = mem.available
            memory_total = mem.total
            
            # 获取磁盘使用率
            disk = psutil.disk_usage('/')
            disk_usage = disk.percent
            disk_used = disk.used
            disk_free = disk.free
            disk_total = disk.total
            
            # 获取网络IO
            net = psutil.net_io_counters()
            network_sent = net.bytes_sent
            network_recv = net.bytes_recv
            
            # 获取进程信息
            process_count = len(psutil.pids())
            processes = []
            
            # 获取前10个占用CPU最多的进程
            try:
                for proc in sorted(psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']),
                                  key=lambda x: x.info['cpu_percent'], reverse=True)[:10]:
                    processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cpu_percent': proc.info['cpu_percent'],
                        'memory_percent': proc.info['memory_percent']
                    })
            except (psutil.AccessDenied, PermissionError) as e:
                logger.warning(f"获取进程信息时遇到权限错误: {e}")
                # 提供一个空的进程列表而不是失败
                processes = []
            except Exception as e:
                logger.error(f"获取进程信息时发生未知错误: {e}")
                processes = []
            
            # 构建资源使用情况
            resource_usage = {
                'timestamp': int(time.time()),
                'cpu': {
                    'usage_percent': cpu_usage,
                    'per_core': cpu_per_core,
                    'count': len(cpu_per_core)
                },
                'memory': {
                    'usage_percent': memory_usage,
                    'used': memory_used,
                    'free': memory_free,
                    'total': memory_total
                },
                'disk': {
                    'usage_percent': disk_usage,
                    'used': disk_used,
                    'free': disk_free,
                    'total': disk_total
                },
                'network': {
                    'sent': network_sent,
                    'recv': network_recv
                },
                'processes': {
                    'count': process_count,
                    'top_10_cpu': processes
                }
            }
            
            return resource_usage
            
        except Exception as e:
            logger.error(f"获取资源使用情况失败: {e}")
            return {}
    
    async def _record_history(self, resource_usage: Dict[str, Any]) -> None:
        """
        记录资源使用历史
        
        Args:
            resource_usage: 资源使用情况
        """
        try:
            timestamp = resource_usage.get('timestamp')
            
            # 记录CPU历史
            cpu_data = {
                'timestamp': timestamp,
                'usage_percent': resource_usage['cpu']['usage_percent']
            }
            self.cpu_history.append(cpu_data)
            
            # 记录内存历史
            memory_data = {
                'timestamp': timestamp,
                'usage_percent': resource_usage['memory']['usage_percent']
            }
            self.memory_history.append(memory_data)
            
            # 记录磁盘历史
            disk_data = {
                'timestamp': timestamp,
                'usage_percent': resource_usage['disk']['usage_percent']
            }
            self.disk_history.append(disk_data)
            
            # 记录网络历史
            network_data = {
                'timestamp': timestamp,
                'sent': resource_usage['network']['sent'],
                'recv': resource_usage['network']['recv']
            }
            self.network_history.append(network_data)
            
            # 记录进程历史
            process_data = {
                'timestamp': timestamp,
                'count': resource_usage['processes']['count']
            }
            self.process_history.append(process_data)
            
            # 限制历史记录数量
            if len(self.cpu_history) > self.max_history:
                self.cpu_history.pop(0)
            
            if len(self.memory_history) > self.max_history:
                self.memory_history.pop(0)
            
            if len(self.disk_history) > self.max_history:
                self.disk_history.pop(0)
            
            if len(self.network_history) > self.max_history:
                self.network_history.pop(0)
            
            if len(self.process_history) > self.max_history:
                self.process_history.pop(0)
                
        except Exception as e:
            logger.error(f"记录资源历史失败: {e}")
    
    async def _check_thresholds(self, resource_usage: Dict[str, Any]) -> None:
        """
        检查资源使用阈值
        
        Args:
            resource_usage: 资源使用情况
        """
        try:
            # 检查CPU使用率
            cpu_usage = resource_usage['cpu']['usage_percent']
            cpu_threshold = self.resource_thresholds.get('cpu', 80)
            
            if cpu_usage >= cpu_threshold:
                await self._trigger_alert({
                    'type': 'cpu',
                    'level': 'warning',
                    'message': f"CPU使用率超过阈值: {cpu_usage}% (阈值: {cpu_threshold}%)",
                    'value': cpu_usage,
                    'threshold': cpu_threshold,
                    'timestamp': resource_usage.get('timestamp')
                })
            
            # 检查内存使用率
            memory_usage = resource_usage['memory']['usage_percent']
            memory_threshold = self.resource_thresholds.get('memory', 80)
            
            if memory_usage >= memory_threshold:
                await self._trigger_alert({
                    'type': 'memory',
                    'level': 'warning',
                    'message': f"内存使用率超过阈值: {memory_usage}% (阈值: {memory_threshold}%)",
                    'value': memory_usage,
                    'threshold': memory_threshold,
                    'timestamp': resource_usage.get('timestamp')
                })
            
            # 检查磁盘使用率
            disk_usage = resource_usage['disk']['usage_percent']
            disk_threshold = self.resource_thresholds.get('disk', 80)
            
            if disk_usage >= disk_threshold:
                await self._trigger_alert({
                    'type': 'disk',
                    'level': 'warning',
                    'message': f"磁盘使用率超过阈值: {disk_usage}% (阈值: {disk_threshold}%)",
                    'value': disk_usage,
                    'threshold': disk_threshold,
                    'timestamp': resource_usage.get('timestamp')
                })
                
        except Exception as e:
            logger.error(f"检查资源阈值失败: {e}")
    
    async def _trigger_alert(self, alert: Dict[str, Any]) -> None:
        """
        触发资源警报
        
        Args:
            alert: 警报信息
        """
        logger.warning(f"资源警报: {alert['message']}")
        
        # 调用警报回调
        for callback in self.alert_callbacks:
            await callback(alert)
    
    def add_resource_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        添加资源使用回调
        
        Args:
            callback: 回调函数
        """
        self.resource_callbacks.append(callback)
    
    def add_alert_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        添加警报回调
        
        Args:
            callback: 回调函数
        """
        self.alert_callbacks.append(callback)
    
    async def get_resource_history(self) -> Dict[str, Any]:
        """
        获取资源使用历史
        
        Returns:
            资源使用历史
        """
        return {
            'cpu': self.cpu_history,
            'memory': self.memory_history,
            'disk': self.disk_history,
            'network': self.network_history,
            'process': self.process_history
        }
    
    async def get_resource_summary(self) -> Dict[str, Any]:
        """
        获取资源使用摘要
        
        Returns:
            资源使用摘要
        """
        # 获取当前资源使用情况
        current_usage = await self.get_resource_usage()
        
        # 计算历史平均值
        cpu_avg = sum(d['usage_percent'] for d in self.cpu_history) / len(self.cpu_history) if self.cpu_history else 0
        memory_avg = sum(d['usage_percent'] for d in self.memory_history) / len(self.memory_history) if self.memory_history else 0
        disk_avg = sum(d['usage_percent'] for d in self.disk_history) / len(self.disk_history) if self.disk_history else 0
        
        return {
            'current': current_usage,
            'average': {
                'cpu': cpu_avg,
                'memory': memory_avg,
                'disk': disk_avg
            },
            'thresholds': self.resource_thresholds,
            'history_length': len(self.cpu_history)
        }
    
    async def get_process_info(self, pid: int) -> Optional[Dict[str, Any]]:
        """
        获取进程信息
        
        Args:
            pid: 进程ID
        
        Returns:
            进程信息
        """
        try:
            proc = psutil.Process(pid)
            
            return {
                'pid': proc.pid,
                'name': proc.name(),
                'cmdline': proc.cmdline(),
                'cpu_percent': proc.cpu_percent(interval=0.1),
                'memory_percent': proc.memory_percent(),
                'memory_info': {
                    'rss': proc.memory_info().rss,
                    'vms': proc.memory_info().vms
                },
                'status': proc.status(),
                'created_at': proc.create_time(),
                'num_threads': proc.num_threads(),
                'num_fds': proc.num_fds() if hasattr(proc, 'num_fds') else 0,
                'username': proc.username()
            }
            
        except psutil.NoSuchProcess:
            logger.warning(f"进程{pid}不存在")
            return None
        except Exception as e:
            logger.error(f"获取进程{pid}信息失败: {e}")
            return None
    
    async def get_top_processes(self, count: int = 10, sort_by: str = 'cpu') -> List[Dict[str, Any]]:
        """
        获取占用资源最多的进程
        
        Args:
            count: 返回的进程数量
            sort_by: 排序方式 ('cpu' or 'memory')
        
        Returns:
            进程列表
        """
        try:
            processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'cmdline']):
                try:
                    processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cpu_percent': proc.info['cpu_percent'],
                        'memory_percent': proc.info['memory_percent'],
                        'cmdline': ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                    })
                except (psutil.AccessDenied, PermissionError):
                    # 跳过没有权限访问的进程
                    continue
                except psutil.NoSuchProcess:
                    # 跳过不存在的进程
                    continue
                except Exception as e:
                    logger.warning(f"获取进程{proc.info.get('pid', 'unknown')}信息失败: {e}")
                    continue
            
            # 排序
            if sort_by == 'cpu':
                sorted_processes = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)
            elif sort_by == 'memory':
                sorted_processes = sorted(processes, key=lambda x: x['memory_percent'], reverse=True)
            else:
                sorted_processes = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)
            
            # 返回前count个进程
            return sorted_processes[:count]
            
        except Exception as e:
            logger.error(f"获取进程列表失败: {e}")
            return []
    
    async def stop(self) -> None:
        """
        停止资源监控器
        """
        await self.stop_monitoring()
        
        logger.info("资源监控器已停止")
