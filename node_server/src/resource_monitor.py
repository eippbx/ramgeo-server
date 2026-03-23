import psutil
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ResourceMonitor:
    """资源监控器，负责监控节点的CPU、内存、磁盘等资源使用情况"""
    
    def __init__(self):
        """初始化资源监控器"""
        self.cpu_count = psutil.cpu_count(logical=True)
        self.memory_total = psutil.virtual_memory().total / (1024**3)  # GB
        self.disk_total = psutil.disk_usage('/').total / (1024**3)  # GB
        
        logger.info(f"资源监控器初始化完成: CPU核心数={self.cpu_count}, "
                   f"内存={self.memory_total:.2f}GB, 磁盘={self.disk_total:.2f}GB")
    
    def get_cpu_load(self):
        """
        获取CPU负载
        
        Returns:
            float: CPU负载 (0-1)
        """
        try:
            cpu_load = psutil.cpu_percent(interval=0.1) / 100.0
            return cpu_load
        except Exception as e:
            logger.error(f"获取CPU负载失败: {e}")
            return 0.0
    
    def get_memory_usage(self):
        """
        获取内存使用率
        
        Returns:
            float: 内存使用率 (0-1)
        """
        try:
            memory = psutil.virtual_memory()
            return memory.percent / 100.0
        except Exception as e:
            logger.error(f"获取内存使用率失败: {e}")
            return 0.0
    
    def get_disk_usage(self):
        """
        获取磁盘使用率
        
        Returns:
            float: 磁盘使用率 (0-1)
        """
        try:
            disk = psutil.disk_usage('/')
            return disk.percent / 100.0
        except Exception as e:
            logger.error(f"获取磁盘使用率失败: {e}")
            return 0.0
    
    def get_network_speed(self):
        """
        获取网络速度
        
        Returns:
            float: 网络速度 (MB/s)
        """
        try:
            net_io = psutil.net_io_counters()
            # 这里返回当前的网络IO统计，实际速度需要通过时间差计算
            # 简化处理，返回0
            return 0.0
        except Exception as e:
            logger.error(f"获取网络速度失败: {e}")
            return 0.0
    
    def get_system_temperature(self):
        """
        获取系统温度
        
        Returns:
            float: 系统温度 (摄氏度)
        """
        try:
            # 尝试获取CPU温度
            if hasattr(psutil, 'sensors_temperatures'):
                temps = psutil.sensors_temperatures()
                if temps:
                    # 获取第一个温度传感器的温度
                    for name, entries in temps.items():
                        if entries:
                            return entries[0].current
            # 如果无法获取温度，返回一个默认值
            return 30.0
        except Exception as e:
            logger.error(f"获取系统温度失败: {e}")
            return 30.0
    
    def get_status_report(self, active_tasks=0):
        """
        获取节点状态报告
        
        Args:
            active_tasks: 当前活动任务数
            
        Returns:
            dict: 节点状态报告
        """
        return {
            'cpu_load': round(self.get_cpu_load(), 3),
            'memory_usage': round(self.get_memory_usage(), 3),
            'disk_usage': round(self.get_disk_usage(), 3),
            'active_tasks': active_tasks,
            'system_temperature': int(self.get_system_temperature())
        }
    
    def get_capabilities(self, max_tasks):
        """
        获取节点能力信息
        
        Args:
            max_tasks: 最大任务数（此参数已废弃，保留以兼容旧代码）
            
        Returns:
            dict: 节点能力信息
        """
        return {
            'cpu_cores': self.cpu_count,
            'memory_gb': int(self.memory_total),
            'disk_gb': int(self.disk_total)
        }
