#!/usr/bin/env python3
"""
数据库管理模块
提供数据库连接和操作功能
"""

import asyncio
from typing import Dict, List, Optional, Any, AsyncGenerator
import aiomysql
import logging

from shared.logger import setup_logging

logger = setup_logging(__name__)


class DatabaseManager:
    """
    数据库管理器
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化数据库管理器
        
        Args:
            config: 数据库配置
        """
        self.config = config
        self.pool = None
        self.is_connected = False
    
    async def connect(self) -> None:
        """
        建立数据库连接池
        """
        try:
            # 使用分散参数配置
            host = self.config.get('host', 'localhost')
            port = self.config.get('port', 3306)  # MySQL默认端口
            database = self.config.get('name', 'ramgeo')
            logger.info(f"连接数据库: {host}:{port}/{database}")
            
            self.pool = await aiomysql.create_pool(
                host=host,
                port=port,
                user=self.config.get('user', 'root'),
                password=self.config.get('password', ''),
                db=database,
                minsize=self.config.get('min_size', 1),
                maxsize=self.config.get('max_size', 10),
                autocommit=True,
                maxconnections=self.config.get('max_inactive_connection_lifetime', 300),
                connect_timeout=self.config.get('command_timeout', 30)
            )
            
            self.is_connected = True
            logger.info("数据库连接成功")
            
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            raise
    
    async def disconnect(self) -> None:
        """
        关闭数据库连接池
        """
        if self.pool is not None:
            await self.pool.close()
            self.is_connected = False
            logger.info("数据库连接已关闭")
    
    async def execute(self, query: str, *args: Any) -> int:
        """
        执行SQL查询（不返回结果）
        
        Args:
            query: SQL查询语句
            args: 查询参数
        
        Returns:
            受影响的行数
        """
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                return cursor.rowcount
    
    async def fetchrow(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        """
        执行SQL查询并返回一行结果
        
        Args:
            query: SQL查询语句
            args: 查询参数
        
        Returns:
            结果行或None
        """
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                return await cursor.fetchone()
    
    async def fetch(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        """
        执行SQL查询并返回多行结果
        
        Args:
            query: SQL查询语句
            args: 查询参数
        
        Returns:
            结果行列表
        """
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, args)
                return await cursor.fetchall()
    
    async def fetchval(self, query: str, *args: Any, column: int = 0) -> Any:
        """
        执行SQL查询并返回单个值
        
        Args:
            query: SQL查询语句
            args: 查询参数
            column: 返回值所在的列索引
        
        Returns:
            查询结果值
        """
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, args)
                row = await cursor.fetchone()
                if row:
                    return row[column]
                return None
    
    async def copy_from(self, table: str, data: List[List[Any]], columns: Optional[List[str]] = None) -> int:
        """
        批量插入数据
        
        Args:
            table: 表名
            data: 数据列表
            columns: 列名列表
        
        Returns:
            插入的行数
        """
        if not data:
            return 0
        
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                if columns:
                    columns_str = f"({', '.join(columns)})"
                    placeholders = f"({', '.join(['%s'] * len(columns))})"
                else:
                    # 自动获取列名
                    await cursor.execute(f"DESCRIBE {table}")
                    columns = [col[0] for col in await cursor.fetchall()]
                    columns_str = f"({', '.join(columns)})"
                    placeholders = f"({', '.join(['%s'] * len(columns))})"
                
                insert_query = f"INSERT INTO {table} {columns_str} VALUES {placeholders}"
                
                count = 0
                for row in data:
                    await cursor.execute(insert_query, row)
                    count += cursor.rowcount
                
                return count
    
    async def copy_to(self, table: str, columns: Optional[List[str]] = None) -> AsyncGenerator[List[Any], None]:
        """
        批量导出数据
        
        Args:
            table: 表名
            columns: 列名列表
        
        Returns:
            数据行生成器
        """
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                query = f"SELECT {', '.join(columns) if columns else '*'} FROM {table}"
                await cursor.execute(query)
                
                while True:
                    rows = await cursor.fetchmany(100)
                    if not rows:
                        break
                    for row in rows:
                        yield list(row)
    
    async def create_tables(self) -> None:
        """
        创建必要的数据库表
        """
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # 创建节点表
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS nodes (
                        id VARCHAR(64) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        status VARCHAR(32) NOT NULL DEFAULT 'online',
                        capabilities JSON NOT NULL,
                        resources JSON NOT NULL,
                        metrics JSON NOT NULL,
                        connection JSON NOT NULL,
                        metadata JSON NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                
                # 创建任务表
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id VARCHAR(64) PRIMARY KEY,
                        user_id VARCHAR(64) NOT NULL,
                        status VARCHAR(32) NOT NULL DEFAULT 'pending',
                        priority INTEGER NOT NULL DEFAULT 0,
                        input_files JSON NOT NULL,
                        output_files JSON NOT NULL,
                        parameters JSON NOT NULL,
                        node_id VARCHAR(64),
                        timestamps JSON NOT NULL,
                        metrics JSON NOT NULL,
                        error_info JSON NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE SET NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                
                # 创建索引
                await cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
                await cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_node_id ON tasks(node_id)")
                await cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)")
                
                logger.info("数据库表创建/更新完成")
    
    async def get_connection(self) -> aiomysql.Connection:
        """
        获取数据库连接
        
        Returns:
            数据库连接
        """
        return await self.pool.acquire()
    
    @property
    def connected(self) -> bool:
        """
        检查数据库连接状态
        
        Returns:
            连接状态
        """
        return self.is_connected
