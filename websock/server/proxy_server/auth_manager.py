#!/usr/bin/env python3
"""
认证管理器模块
提供用户认证、授权、API密钥管理等功能
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from shared.logger import setup_logging
from shared.exceptions import AuthenticationError, AuthorizationError, NotFoundError, BadRequestError
from shared.security import SecurityManager
from shared.database import DatabaseManager

logger = setup_logging(__name__)


class AuthManager:
    """
    认证管理器类
    """
    
    def __init__(self, config: Dict[str, Any], db_manager: DatabaseManager, security_manager: SecurityManager):
        """
        初始化认证管理器
        
        Args:
            config: 配置信息
            db_manager: 数据库管理器实例
            security_manager: 安全管理器实例
        """
        self.config = config
        self.db_manager = db_manager
        self.security_manager = security_manager
        
        # JWT配置
        self.jwt_secret_key = config.get('security.jwt_secret_key')
        self.jwt_algorithm = config.get('security.jwt_algorithm', 'HS256')
        self.jwt_expiration = config.get('security.jwt_expiration', 3600)  # 1小时
        
        # API密钥配置
        self.api_key_enabled = config.get('security.api_key_enabled', True)
    
    async def authenticate_user(self, username: str, password: str) -> Dict[str, Any]:
        """
        用户认证
        
        Args:
            username: 用户名
            password: 密码
        
        Returns:
            用户信息
        """
        try:
            # 查询用户
            user = await self.db_manager.fetchrow(
                "SELECT id, username, password_hash, role, status, created_at, updated_at "
                "FROM users WHERE username = $1",
                (username,)
            )
            
            if not user:
                logger.warning(f"用户不存在: {username}")
                raise AuthenticationError("用户名或密码错误")
            
            if user['status'] != 'active':
                logger.warning(f"用户状态异常: {username}, 状态: {user['status']}")
                raise AuthenticationError("用户账号已被禁用")
            
            # 验证密码
            if not self.security_manager.verify_hash(password, user['password_hash']):
                logger.warning(f"密码错误: {username}")
                raise AuthenticationError("用户名或密码错误")
            
            logger.info(f"用户认证成功: {username}")
            
            # 返回用户信息（不包含密码哈希）
            return {
                'id': user['id'],
                'username': user['username'],
                'role': user['role'],
                'status': user['status'],
                'created_at': user['created_at'],
                'updated_at': user['updated_at']
            }
            
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"用户认证失败: {username}, 错误: {e}")
            raise AuthenticationError("认证过程中发生错误")
    
    async def authenticate_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        API密钥认证
        
        Args:
            api_key: API密钥
        
        Returns:
            API密钥信息
        """
        if not self.api_key_enabled:
            raise AuthenticationError("API密钥认证已禁用")
        
        try:
            # 查询API密钥
            api_key_info = await self.db_manager.fetchrow(
                "SELECT id, key_hash, user_id, description, status, created_at, updated_at "
                "FROM api_keys WHERE status = 'active'",
            )
            
            if not api_key_info:
                logger.warning(f"无效的API密钥")
                raise AuthenticationError("无效的API密钥")
            
            # 验证API密钥
            if not self.security_manager.verify_api_key(api_key, api_key_info['key_hash']):
                logger.warning(f"API密钥验证失败")
                raise AuthenticationError("无效的API密钥")
            
            # 获取用户信息
            user = await self.db_manager.fetchrow(
                "SELECT id, username, role, status "
                "FROM users WHERE id = $1 AND status = 'active'",
                (api_key_info['user_id'],)
            )
            
            if not user:
                logger.warning(f"API密钥对应的用户不存在或已禁用: {api_key_info['user_id']}")
                raise AuthenticationError("无效的API密钥")
            
            logger.info(f"API密钥认证成功, 用户: {user['username']}")
            
            return {
                'api_key_id': api_key_info['id'],
                'user_id': user['id'],
                'username': user['username'],
                'role': user['role'],
                'description': api_key_info['description'],
                'created_at': api_key_info['created_at']
            }
            
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"API密钥认证失败, 错误: {e}")
            raise AuthenticationError("API密钥认证过程中发生错误")
    
    async def generate_jwt_token(self, user_info: Dict[str, Any]) -> str:
        """
        生成JWT令牌
        
        Args:
            user_info: 用户信息
        
        Returns:
            JWT令牌
        """
        payload = {
            'user_id': user_info['id'],
            'username': user_info['username'],
            'role': user_info['role'],
            'exp': datetime.utcnow().timestamp() + self.jwt_expiration
        }
        
        return self.security_manager.generate_jwt_token(payload)
    
    async def verify_jwt_token(self, token: str) -> Dict[str, Any]:
        """
        验证JWT令牌
        
        Args:
            token: JWT令牌
        
        Returns:
            解码后的用户信息
        """
        try:
            payload = self.security_manager.verify_jwt_token(token)
            
            if not payload:
                raise AuthenticationError("无效的JWT令牌")
            
            # 检查令牌是否过期
            if payload.get('exp') and payload['exp'] < datetime.utcnow().timestamp():
                raise AuthenticationError("JWT令牌已过期")
            
            # 验证用户是否存在且活跃
            user = await self.db_manager.fetchrow(
                "SELECT id, username, role, status "
                "FROM users WHERE id = $1 AND status = 'active'",
                (payload['user_id'],)
            )
            
            if not user:
                logger.warning(f"JWT令牌对应的用户不存在或已禁用: {payload['user_id']}")
                raise AuthenticationError("无效的JWT令牌")
            
            return payload
            
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"JWT令牌验证失败, 错误: {e}")
            raise AuthenticationError("JWT令牌验证过程中发生错误")
    
    async def authorize_role(self, user_role: str, required_role: str) -> bool:
        """
        角色授权检查
        
        Args:
            user_role: 用户角色
            required_role: 要求的角色
        
        Returns:
            授权是否通过
        """
        # 定义角色层级关系
        role_hierarchy = {
            'admin': ['admin', 'manager', 'user'],
            'manager': ['manager', 'user'],
            'user': ['user']
        }
        
        # 检查角色是否存在
        if user_role not in role_hierarchy:
            logger.warning(f"未知的用户角色: {user_role}")
            raise AuthorizationError("未知的用户角色")
        
        if required_role not in role_hierarchy:
            logger.warning(f"未知的要求角色: {required_role}")
            raise AuthorizationError("未知的要求角色")
        
        # 检查用户角色是否有权限
        if required_role not in role_hierarchy[user_role]:
            logger.warning(f"角色授权失败: 用户角色 {user_role}, 要求角色 {required_role}")
            return False
        
        logger.debug(f"角色授权成功: 用户角色 {user_role}, 要求角色 {required_role}")
        return True
    
    async def check_permission(self, user_id: str, resource: str, action: str) -> bool:
        """
        权限检查
        
        Args:
            user_id: 用户ID
            resource: 资源
            action: 操作
        
        Returns:
            权限是否通过
        """
        try:
            # 获取用户信息
            user = await self.db_manager.fetchrow(
                "SELECT id, role "
                "FROM users WHERE id = $1",
                (user_id,)
            )
            
            if not user:
                logger.warning(f"用户不存在: {user_id}")
                return False
            
            # 管理员拥有所有权限
            if user['role'] == 'admin':
                return True
            
            # 查询权限
            permission = await self.db_manager.fetchrow(
                "SELECT COUNT(*) as count "
                "FROM role_permissions rp "
                "JOIN permissions p ON rp.permission_id = p.id "
                "WHERE rp.role = $1 AND p.resource = $2 AND p.action = $3",
                (user['role'], resource, action)
            )
            
            return permission['count'] > 0
            
        except Exception as e:
            logger.error(f"权限检查失败: 用户ID {user_id}, 资源 {resource}, 操作 {action}, 错误: {e}")
            return False
    
    async def create_user(self, username: str, password: str, role: str = 'user') -> Dict[str, Any]:
        """
        创建用户
        
        Args:
            username: 用户名
            password: 密码
            role: 角色
        
        Returns:
            创建的用户信息
        """
        try:
            # 检查用户名是否已存在
            existing_user = await self.db_manager.fetchrow(
                "SELECT id FROM users WHERE username = $1",
                (username,)
            )
            
            if existing_user:
                raise BadRequestError("用户名已存在")
            
            # 哈希密码
            password_hash = self.security_manager.generate_hash(password)
            
            # 创建用户
            user = await self.db_manager.fetchrow(
                "INSERT INTO users (username, password_hash, role, status) "
                "VALUES ($1, $2, $3, 'active') RETURNING *",
                (username, password_hash, role)
            )
            
            logger.info(f"创建用户成功: {username}, 角色: {role}")
            
            # 返回用户信息（不包含密码哈希）
            return {
                'id': user['id'],
                'username': user['username'],
                'role': user['role'],
                'status': user['status'],
                'created_at': user['created_at'],
                'updated_at': user['updated_at']
            }
            
        except Exception as e:
            logger.error(f"创建用户失败: {username}, 错误: {e}")
            raise
    
    async def generate_api_key(self, user_id: str, description: str = '') -> str:
        """
        生成API密钥
        
        Args:
            user_id: 用户ID
            description: 描述
        
        Returns:
            生成的API密钥
        """
        try:
            # 检查用户是否存在
            user = await self.db_manager.fetchrow(
                "SELECT id FROM users WHERE id = $1",
                (user_id,)
            )
            
            if not user:
                raise NotFoundError("用户不存在")
            
            # 生成API密钥
            api_key = self.security_manager.generate_api_key()
            key_hash = self.security_manager.hash_api_key(api_key)
            
            # 保存API密钥
            await self.db_manager.execute(
                "INSERT INTO api_keys (key_hash, user_id, description, status) "
                "VALUES ($1, $2, $3, 'active')",
                (key_hash, user_id, description)
            )
            
            logger.info(f"生成API密钥成功: 用户ID {user_id}")
            return api_key
            
        except Exception as e:
            logger.error(f"生成API密钥失败: 用户ID {user_id}, 错误: {e}")
            raise
    
    async def revoke_api_key(self, api_key_id: str, user_id: str) -> bool:
        """
        撤销API密钥
        
        Args:
            api_key_id: API密钥ID
            user_id: 用户ID
        
        Returns:
            撤销是否成功
        """
        try:
            # 检查API密钥是否属于该用户
            result = await self.db_manager.execute(
                "UPDATE api_keys SET status = 'revoked', updated_at = NOW() "
                "WHERE id = $1 AND user_id = $2 AND status = 'active'",
                (api_key_id, user_id)
            )
            
            if result == 0:
                logger.warning(f"API密钥不存在或已被撤销: ID {api_key_id}, 用户ID {user_id}")
                return False
            
            logger.info(f"撤销API密钥成功: ID {api_key_id}, 用户ID {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"撤销API密钥失败: ID {api_key_id}, 用户ID {user_id}, 错误: {e}")
            return False
    
    async def get_user_api_keys(self, user_id: str) -> list:
        """
        获取用户的API密钥列表
        
        Args:
            user_id: 用户ID
        
        Returns:
            API密钥列表
        """
        try:
            api_keys = await self.db_manager.fetch(
                "SELECT id, description, status, created_at, updated_at "
                "FROM api_keys WHERE user_id = $1 ORDER BY created_at DESC",
                (user_id,)
            )
            
            return api_keys
            
        except Exception as e:
            logger.error(f"获取用户API密钥列表失败: 用户ID {user_id}, 错误: {e}")
            return []
