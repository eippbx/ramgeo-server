import yaml
import os
import logging

logger = logging.getLogger(__name__)

class Config:
    """配置加载器"""
    
    def __init__(self, config_file_path=None):
        """
        初始化配置加载器
        
        Args:
            config_file_path: 配置文件路径，如果为None则使用默认路径
        """
        if config_file_path is None:
            config_file_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'config',
                'node_config.yaml'
            )
        
        self.config_file_path = config_file_path
        self.config_data = self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_file_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            logger.info(f"配置文件加载成功: {self.config_file_path}")
            return config_data
        except FileNotFoundError:
            logger.error(f"配置文件不存在: {self.config_file_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"配置文件解析失败: {e}")
            raise
        except Exception as e:
            logger.error(f"加载配置文件时发生错误: {e}")
            raise
    
    def get(self, key, default=None):
        """
        获取配置值
        
        Args:
            key: 配置键，支持点分隔的嵌套键，如 'node.node_id'
            default: 默认值
            
        Returns:
            配置值，如果不存在则返回默认值
        """
        keys = key.split('.')
        value = self.config_data
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def reload(self):
        """重新加载配置文件"""
        logger.info("重新加载配置文件...")
        self.config_data = self._load_config()
