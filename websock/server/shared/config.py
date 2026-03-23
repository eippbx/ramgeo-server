"""
配置管理模块
支持YAML、环境变量、命令行参数等多种配置方式
"""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dotenv import load_dotenv
import argparse

class Config:
    """配置管理类"""
    
    def __init__(self, config_path: Optional[str] = None):
        self._config = {}
        self.config_path = config_path
        
        # 加载环境变量
        load_dotenv()
        
        # 加载配置文件
        self._load_config()
        
        # 解析命令行参数
        self._parse_args()
        
        # 设置默认值
        self._set_defaults()
    
    def _load_config(self):
        """加载配置文件"""
        config_files = []
        
        # 1. 命令行指定的配置文件
        if self.config_path and os.path.exists(self.config_path):
            config_files.append(self.config_path)
        
        # 2. 默认配置文件位置
        default_paths = [
            './config/config.yaml',
            './config.yaml',
            '/etc/ramgeo/config.yaml',
            '~/.ramgeo/config.yaml'
        ]
        
        for path in default_paths:
            expanded_path = os.path.expanduser(path)
            if os.path.exists(expanded_path):
                config_files.append(expanded_path)
        
        # 加载所有配置文件
        for config_file in config_files:
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                        file_config = yaml.safe_load(f)
                    elif config_file.endswith('.json'):
                        file_config = json.load(f)
                    else:
                        continue
                    
                    self._merge_config(file_config)
                    print(f"加载配置文件: {config_file}")
                    
            except Exception as e:
                print(f"加载配置文件失败 {config_file}: {e}")
        
        # 3. 环境变量
        self._load_env_vars()
    
    def _load_env_vars(self):
        """加载环境变量"""
        env_config = {}
        
        # 遍历所有环境变量
        for key, value in os.environ.items():
            if key.startswith('RAMGEO_'):
                # 转换环境变量名: RAMGEO_DATABASE_HOST -> database.host
                config_key = key[7:].lower().replace('__', '.').replace('_', '.')
                
                # 解析值
                if value.lower() in ('true', 'false'):
                    env_config[config_key] = value.lower() == 'true'
                elif value.isdigit():
                    env_config[config_key] = int(value)
                elif self._is_float(value):
                    env_config[config_key] = float(value)
                elif value.startswith('[') and value.endswith(']'):
                    # 数组值
                    try:
                        env_config[config_key] = json.loads(value)
                    except:
                        env_config[config_key] = value.split(',')
                elif value.startswith('{') and value.endswith('}'):
                    # 对象值
                    try:
                        env_config[config_key] = json.loads(value)
                    except:
                        env_config[config_key] = value
                else:
                    env_config[config_key] = value
        
        self._merge_config(env_config)
    
    def _parse_args(self):
        """解析命令行参数"""
        parser = argparse.ArgumentParser(description='RAMGEO分布式计算系统')
        
        # 代理服务器参数
        parser.add_argument('--host', help='服务器主机')
        parser.add_argument('--port', type=int, help='服务器端口')
        parser.add_argument('--debug', action='store_true', help='调试模式')
        
        # 数据库参数
        parser.add_argument('--db-host', help='数据库主机')
        parser.add_argument('--db-port', type=int, help='数据库端口')
        parser.add_argument('--db-name', help='数据库名称')
        parser.add_argument('--db-user', help='数据库用户')
        parser.add_argument('--db-password', help='数据库密码')
        
        # Redis参数
        parser.add_argument('--redis-host', help='Redis主机')
        parser.add_argument('--redis-port', type=int, help='Redis端口')
        parser.add_argument('--redis-password', help='Redis密码')
        
        # WebSocket参数
        parser.add_argument('--ws-host', help='WebSocket主机')
        parser.add_argument('--ws-port', type=int, help='WebSocket端口')
        
        # 节点参数
        parser.add_argument('--node-id', help='节点ID')
        parser.add_argument('--node-name', help='节点名称')
        parser.add_argument('--node-token', help='节点认证令牌')
        
        # 尝试解析参数
        try:
            args = parser.parse_args()
            args_dict = vars(args)
            
            # 转换参数到配置格式
            cli_config = {}
            for key, value in args_dict.items():
                if value is not None:
                    if key in ['host', 'port', 'debug']:
                        cli_config[f'proxy.{key}'] = value
                    elif key.startswith('db_'):
                        cli_config[f'database.{key[3:]}'] = value
                    elif key.startswith('redis_'):
                        cli_config[f'redis.{key[6:]}'] = value
                    elif key.startswith('ws_'):
                        cli_config[f'websocket.{key[3:]}'] = value
                    elif key.startswith('node_'):
                        cli_config[f'node.{key[5:]}'] = value
            
            self._merge_config(cli_config)
            
        except SystemExit:
            # 忽略参数解析错误，继续使用默认配置
            pass
    
    def _merge_config(self, new_config: Dict):
        """合并配置"""
        def _merge_dict(d1: Dict, d2: Dict) -> Dict:
            """递归合并字典"""
            for key, value in d2.items():
                if key in d1 and isinstance(d1[key], dict) and isinstance(value, dict):
                    d1[key] = _merge_dict(d1[key], value)
                else:
                    d1[key] = value
            return d1
        
        self._config = _merge_dict(self._config, self._dict_to_nested(new_config))
    
    def _dict_to_nested(self, flat_dict: Dict) -> Dict:
        """将扁平字典转换为嵌套字典"""
        result = {}
        for key, value in flat_dict.items():
            keys = key.split('.')
            current = result
            for i, k in enumerate(keys):
                if i == len(keys) - 1:
                    current[k] = value
                else:
                    if k not in current:
                        current[k] = {}
                    current = current[k]
        return result
    
    def _set_defaults(self):
        """设置默认值"""
        defaults = {
            'proxy': {
                'host': '0.0.0.0',
                'port': 8080,
                'debug': False,
                'log_level': 'INFO',
                'metrics_port': 9090
            },
            'database': {
                'host': 'localhost',
                'port': 3306,
                'name': 'ramgeo',
                'user': 'root',
                'password': 'Pga39016',
                'pool_size': 10,
                'max_overflow': 20,
                'echo': False
            },
            'redis': {
                'host': 'localhost',
                'port': 6379,
                'password': None,
                'db': 0,
                'max_connections': 20,
                'decode_responses': True
            },
            'websocket': {
                'host': '0.0.0.0',
                'port': 8081,
                'heartbeat_interval': 30,
                'heartbeat_timeout': 60,
                'max_message_size': 100 * 1024 * 1024,  # 100MB
                'max_connections': 1000
            },
            'node': {
                'max_tasks': 5,
                'max_file_size': 100 * 1024 * 1024,  # 100MB
                'work_dir': '/var/ramgeo/workspace',
                'ramgeo_path': '/usr/sbin/ramgeo',
                'health_check_interval': 60,
                'max_failures': 3,
                'max_retries': 5,
                'retry_delay': 5
            },
            'load_balancing': {
                'strategy': 'least_connections',
                'weights': {},
                'affinity_timeout': 300
            },
            'file_transfer': {
                'chunk_size': 1 * 1024 * 1024,  # 1MB
                'compression': True,
                'encryption': True,
                'temp_dir': '/tmp/ramgeo',
                'retention_days': 7
            },
            'security': {
                'jwt_secret': 'your-secret-key-change-in-production',
                'jwt_expire_hours': 24,
                'bcrypt_rounds': 12,
                'cors_origins': ['*'],
                'rate_limit': {
                    'enabled': True,
                    'requests_per_minute': 60
                }
            },
            'monitoring': {
                'enabled': True,
                'metrics_interval': 10,
                'alerting': {
                    'enabled': True,
                    'webhook_url': None
                },
                'logging': {
                    'level': 'INFO',
                    'format': 'json',
                    'rotation': {
                        'size': '100MB',
                        'backup_count': 10
                    }
                }
            }
        }
        
        self._merge_config(defaults)
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """设置配置值"""
        keys = key.split('.')
        config = self._config
        
        for i, k in enumerate(keys):
            if i == len(keys) - 1:
                config[k] = value
            else:
                if k not in config:
                    config[k] = {}
                config = config[k]
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """获取布尔值配置"""
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        elif isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'on')
        elif isinstance(value, (int, float)):
            return value != 0
        return bool(value)
    
    def get_int(self, key: str, default: int = 0) -> int:
        """获取整数值配置"""
        value = self.get(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def get_float(self, key: str, default: float = 0.0) -> float:
        """获取浮点值配置"""
        value = self.get(key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def get_list(self, key: str, default: list = None) -> list:
        """获取列表值配置"""
        if default is None:
            default = []
        
        value = self.get(key, default)
        if isinstance(value, list):
            return value
        elif isinstance(value, str):
            return [item.strip() for item in value.split(',')]
        else:
            return [value]
    
    def get_dict(self, key: str, default: dict = None) -> dict:
        """获取字典值配置"""
        if default is None:
            default = {}
        
        value = self.get(key, default)
        if isinstance(value, dict):
            return value
        else:
            return default
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return self._config.copy()
    
    def save(self, filepath: str, format: str = 'yaml'):
        """保存配置到文件"""
        try:
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                if format.lower() == 'yaml':
                    yaml.dump(self._config, f, default_flow_style=False)
                elif format.lower() == 'json':
                    json.dump(self._config, f, indent=2)
                else:
                    raise ValueError(f"不支持的格式: {format}")
            
            print(f"配置已保存到: {filepath}")
            return True
            
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False
    
    def _is_float(self, value: str) -> bool:
        """检查字符串是否可以转换为浮点数"""
        try:
            float(value)
            return True
        except ValueError:
            return False
    
    def __getitem__(self, key: str) -> Any:
        """支持字典式访问"""
        return self.get(key)
    
    def __setitem__(self, key: str, value: Any):
        """支持字典式设置"""
        self.set(key, value)
    
    def __contains__(self, key: str) -> bool:
        """检查键是否存在"""
        return self.get(key) is not None
    
    def __str__(self) -> str:
        """字符串表示"""
        return json.dumps(self._config, indent=2, ensure_ascii=False)


# 全局配置实例
_config_instance = None

def get_config(config_path: Optional[str] = None) -> Config:
    """获取全局配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path)
    return _config_instance

def reload_config(config_path: Optional[str] = None) -> Config:
    """重新加载配置"""
    global _config_instance
    _config_instance = Config(config_path)
    return _config_instance