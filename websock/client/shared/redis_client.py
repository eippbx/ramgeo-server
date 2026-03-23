#!/usr/bin/env python3
"""
Redis客户端模块
提供Redis连接和操作功能
"""

import asyncio
import json
from typing import Dict, List, Optional, Any, AsyncGenerator
import redis.asyncio as aioredis
import logging

from shared.logger import setup_logging

logger = setup_logging(__name__)


class RedisClient:
    """
    Redis客户端
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化Redis客户端
        
        Args:
            config: Redis配置
        """
        self.config = config
        self.pool = None
        self.is_connected = False
    
    async def connect(self) -> None:
        """
        建立Redis连接池
        """
        try:
            logger.info(f"连接Redis: {self.config.get('host')}:{self.config.get('port')}")
            
            # 创建连接池
            self.pool = aioredis.ConnectionPool.from_url(
                f"redis://{self.config.get('host', 'localhost')}:{self.config.get('port', 6379)}",
                password=self.config.get('password'),
                db=self.config.get('db', 0),
                max_connections=self.config.get('max_connections', 10),
                decode_responses=self.config.get('decode_responses', True)
            )
            
            self.is_connected = True
            logger.info("Redis连接成功")
            
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            raise
    
    async def disconnect(self) -> None:
        """
        关闭Redis连接池
        """
        if self.pool is not None:
            await self.pool.disconnect()
            self.is_connected = False
            logger.info("Redis连接已关闭")
    
    async def get(self, key: str) -> Optional[str]:
        """
        获取键值
        
        Args:
            key: 键名
        
        Returns:
            值或None
        """
        async with self.pool.get_connection() as conn:
            return await conn.get(key)
    
    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """
        设置键值
        
        Args:
            key: 键名
            value: 值
            expire: 过期时间（秒）
        
        Returns:
            设置是否成功
        """
        async with self.pool.get_connection() as conn:
            if expire:
                return await conn.setex(key, expire, value)
            else:
                return await conn.set(key, value)
    
    async def delete(self, *keys: str) -> int:
        """
        删除键
        
        Args:
            keys: 键名列表
        
        Returns:
            删除的键数
        """
        async with self.pool.get_connection() as conn:
            return await conn.delete(*keys)
    
    async def exists(self, *keys: str) -> int:
        """
        检查键是否存在
        
        Args:
            keys: 键名列表
        
        Returns:
            存在的键数
        """
        async with self.pool.get_connection() as conn:
            return await conn.exists(*keys)
    
    async def incr(self, key: str, amount: int = 1) -> int:
        """
        递增键值
        
        Args:
            key: 键名
            amount: 递增值
        
        Returns:
            递增后的值
        """
        async with self.pool.get_connection() as conn:
            return await conn.incrby(key, amount)
    
    async def decr(self, key: str, amount: int = 1) -> int:
        """
        递减键值
        
        Args:
            key: 键名
            amount: 递减值
        
        Returns:
            递减后的值
        """
        async with self.pool.get_connection() as conn:
            return await conn.decrby(key, amount)
    
    async def hget(self, name: str, key: str) -> Optional[str]:
        """
        获取哈希表字段值
        
        Args:
            name: 哈希表名
            key: 字段名
        
        Returns:
            字段值或None
        """
        async with self.pool.get_connection() as conn:
            return await conn.hget(name, key)
    
    async def hset(self, name: str, key: str, value: Any) -> int:
        """
        设置哈希表字段值
        
        Args:
            name: 哈希表名
            key: 字段名
            value: 字段值
        
        Returns:
            受影响的字段数
        """
        async with self.pool.get_connection() as conn:
            return await conn.hset(name, key, value)
    
    async def hgetall(self, name: str) -> Dict[str, str]:
        """
        获取哈希表所有字段和值
        
        Args:
            name: 哈希表名
        
        Returns:
            所有字段和值的字典
        """
        async with self.pool.get_connection() as conn:
            return await conn.hgetall(name)
    
    async def hdel(self, name: str, *keys: str) -> int:
        """
        删除哈希表字段
        
        Args:
            name: 哈希表名
            keys: 字段名列表
        
        Returns:
            删除的字段数
        """
        async with self.pool.get_connection() as conn:
            return await conn.hdel(name, *keys)
    
    async def lpush(self, name: str, *values: Any) -> int:
        """
        向左推入列表元素
        
        Args:
            name: 列表名
            values: 元素值
        
        Returns:
            列表长度
        """
        async with self.pool.get_connection() as conn:
            return await conn.lpush(name, *values)
    
    async def rpush(self, name: str, *values: Any) -> int:
        """
        向右推入列表元素
        
        Args:
            name: 列表名
            values: 元素值
        
        Returns:
            列表长度
        """
        async with self.pool.get_connection() as conn:
            return await conn.rpush(name, *values)
    
    async def lpop(self, name: str) -> Optional[str]:
        """
        向左弹出列表元素
        
        Args:
            name: 列表名
        
        Returns:
            弹出的元素或None
        """
        async with self.pool.get_connection() as conn:
            return await conn.lpop(name)
    
    async def rpop(self, name: str) -> Optional[str]:
        """
        向右弹出列表元素
        
        Args:
            name: 列表名
        
        Returns:
            弹出的元素或None
        """
        async with self.pool.get_connection() as conn:
            return await conn.rpop(name)
    
    async def llen(self, name: str) -> int:
        """
        获取列表长度
        
        Args:
            name: 列表名
        
        Returns:
            列表长度
        """
        async with self.pool.get_connection() as conn:
            return await conn.llen(name)
    
    async def publish(self, channel: str, message: Any) -> int:
        """
        发布消息
        
        Args:
            channel: 频道名
            message: 消息内容
        
        Returns:
            订阅者数量
        """
        async with self.pool.get_connection() as conn:
            return await conn.publish(channel, message)
    
    async def subscribe(self, channel: str) -> AsyncGenerator[str, None]:
        """
        订阅频道
        
        Args:
            channel: 频道名
        
        Returns:
            消息生成器
        """
        async with self.pool.get_connection() as conn:
            pubsub = conn.pubsub()
            await pubsub.subscribe(channel)
            
            try:
                async for message in pubsub.listen():
                    if message['type'] == 'message':
                        yield message['data']
            finally:
                await pubsub.unsubscribe(channel)
    
    async def expire(self, key: str, seconds: int) -> bool:
        """
        设置键过期时间
        
        Args:
            key: 键名
            seconds: 过期时间（秒）
        
        Returns:
            设置是否成功
        """
        async with self.pool.get_connection() as conn:
            return await conn.expire(key, seconds)
    
    async def ttl(self, key: str) -> int:
        """
        获取键剩余过期时间
        
        Args:
            key: 键名
        
        Returns:
            剩余时间（秒），-1表示不过期，-2表示键不存在
        """
        async with self.pool.get_connection() as conn:
            return await conn.ttl(key)
    
    async def get_json(self, key: str, default: Optional[Any] = None) -> Any:
        """
        获取JSON格式的值
        
        Args:
            key: 键名
            default: 默认值
        
        Returns:
            解析后的JSON值
        """
        value = await self.get(key)
        if value is None:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.error(f"JSON解析失败: {value}")
            return default
    
    async def set_json(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """
        设置JSON格式的值
        
        Args:
            key: 键名
            value: 要序列化的JSON值
            expire: 过期时间（秒）
        
        Returns:
            设置是否成功
        """
        try:
            json_value = json.dumps(value)
            return await self.set(key, json_value, expire)
        except json.JSONDecodeError:
            logger.error(f"JSON序列化失败: {value}")
            return False
    
    @property
    def connected(self) -> bool:
        """
        检查Redis连接状态
        
        Returns:
            连接状态
        """
        return self.is_connected
