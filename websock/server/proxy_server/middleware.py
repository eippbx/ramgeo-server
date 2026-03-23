#!/usr/bin/env python3
"""
中间件模块
实现API中间件功能
"""

import logging
import time
from typing import Dict, Any, Optional, Callable
from aiohttp import web

from shared.logger import setup_logging
from shared.exceptions import *
from .auth_manager import AuthManager

logger = setup_logging(__name__)


class MiddlewareManager:
    """
    中间件管理器类
    """
    
    def __init__(self, auth_manager: AuthManager):
        """
        初始化中间件管理器
        
        Args:
            auth_manager: 认证管理器实例
        """
        self.auth_manager = auth_manager
    
    async def auth_middleware(self, request: web.Request, handler: Callable) -> web.Response:
        """
        认证中间件
        
        Args:
            request: 请求对象
            handler: 下一个处理函数
        
        Returns:
            响应对象
        """
        # 不需要认证的路由
        public_routes = [
            '/api/login',
        ]
        
        # 检查是否为公开路由
        if request.path in public_routes:
            return await handler(request)
        
        # 从请求头获取Authorization
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return web.json_response({
                'success': False,
                'message': '缺少认证信息',
                'code': 401
            }, status=401)
        
        # 检查Authorization格式
        if not auth_header.startswith('Bearer '):
            return web.json_response({
                'success': False,
                'message': '无效的认证格式',
                'code': 401
            }, status=401)
        
        # 获取JWT令牌
        token = auth_header[7:]
        
        try:
            # 验证JWT令牌
            user_info = await self.auth_manager.verify_jwt_token(token)
            
            # 将用户信息添加到请求上下文
            request['user_info'] = user_info
            
            # 继续处理请求
            return await handler(request)
            
        except TokenExpiredError as e:
            return web.json_response({
                'success': False,
                'message': '令牌已过期',
                'code': e.code
            }, status=e.code)
        except TokenInvalidError as e:
            return web.json_response({
                'success': False,
                'message': '无效的令牌',
                'code': e.code
            }, status=e.code)
        except Exception as e:
            logger.error(f"认证中间件错误: {e}")
            return web.json_response({
                'success': False,
                'message': '认证失败',
                'code': 401
            }, status=401)
    
    async def api_key_middleware(self, request: web.Request, handler: Callable) -> web.Response:
        """
        API密钥认证中间件
        
        Args:
            request: 请求对象
            handler: 下一个处理函数
        
        Returns:
            响应对象
        """
        # 不需要API密钥认证的路由
        excluded_routes = [
            '/api/login',
            '/api/user',
            '/api/api-key',
        ]
        
        # 检查是否为排除路由
        if request.path in excluded_routes:
            return await handler(request)
        
        # 从请求头获取X-API-Key
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            # 从查询参数获取api_key
            api_key = request.query.get('api_key')
        
        if not api_key:
            return web.json_response({
                'success': False,
                'message': '缺少API密钥',
                'code': 401
            }, status=401)
        
        try:
            # 验证API密钥
            user_info = await self.auth_manager.authenticate_api_key(api_key)
            
            # 将用户信息添加到请求上下文
            request['user_info'] = user_info
            
            # 继续处理请求
            return await handler(request)
            
        except InvalidAPIKeyError as e:
            return web.json_response({
                'success': False,
                'message': '无效的API密钥',
                'code': e.code
            }, status=e.code)
        except Exception as e:
            logger.error(f"API密钥中间件错误: {e}")
            return web.json_response({
                'success': False,
                'message': 'API密钥认证失败',
                'code': 401
            }, status=401)
    
    async def log_middleware(self, request: web.Request, handler: Callable) -> web.Response:
        """
        日志中间件
        
        Args:
            request: 请求对象
            handler: 下一个处理函数
        
        Returns:
            响应对象
        """
        # 记录请求开始时间
        start_time = time.time()
        
        # 记录请求信息
        logger.info(f"{request.method} {request.path} - 开始处理请求")
        
        try:
            # 继续处理请求
            response = await handler(request)
            
            # 计算请求处理时间
            process_time = time.time() - start_time
            
            # 记录响应信息
            logger.info(f"{request.method} {request.path} - 处理完成，状态码: {response.status}, 处理时间: {process_time:.3f}s")
            
            return response
            
        except Exception as e:
            # 计算请求处理时间
            process_time = time.time() - start_time
            
            # 记录异常信息
            logger.error(f"{request.method} {request.path} - 处理失败，错误: {e}, 处理时间: {process_time:.3f}s")
            
            # 重新抛出异常
            raise
    
    async def cors_middleware(self, request: web.Request, handler: Callable) -> web.Response:
        """
        CORS中间件
        
        Args:
            request: 请求对象
            handler: 下一个处理函数
        
        Returns:
            响应对象
        """
        # 处理OPTIONS请求
        if request.method == 'OPTIONS':
            return web.Response(
                headers={
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-API-Key',
                    'Access-Control-Max-Age': '3600'
                }
            )
        
        # 处理正常请求
        response = await handler(request)
        
        # 添加CORS头
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
        
        return response
    
    async def error_middleware(self, request: web.Request, handler: Callable) -> web.Response:
        """
        错误处理中间件
        
        Args:
            request: 请求对象
            handler: 下一个处理函数
        
        Returns:
            响应对象
        """
        try:
            return await handler(request)
            
        except BadRequestError as e:
            return web.json_response({
                'success': False,
                'message': str(e),
                'code': e.code
            }, status=e.code)
        except AuthenticationError as e:
            return web.json_response({
                'success': False,
                'message': str(e),
                'code': e.code
            }, status=e.code)
        except AuthorizationError as e:
            return web.json_response({
                'success': False,
                'message': str(e),
                'code': e.code
            }, status=e.code)
        except NotFoundError as e:
            return web.json_response({
                'success': False,
                'message': str(e),
                'code': e.code
            }, status=e.code)
        except DuplicateError as e:
            return web.json_response({
                'success': False,
                'message': str(e),
                'code': e.code
            }, status=e.code)
        except DatabaseError as e:
            return web.json_response({
                'success': False,
                'message': '数据库操作失败',
                'code': e.code
            }, status=e.code)
        except RedisError as e:
            return web.json_response({
                'success': False,
                'message': '缓存操作失败',
                'code': e.code
            }, status=e.code)
        except FileError as e:
            return web.json_response({
                'success': False,
                'message': '文件操作失败',
                'code': e.code
            }, status=e.code)
        except NetworkError as e:
            return web.json_response({
                'success': False,
                'message': '网络操作失败',
                'code': e.code
            }, status=e.code)
        except ConfigurationError as e:
            return web.json_response({
                'success': False,
                'message': '配置错误',
                'code': e.code
            }, status=e.code)
        except SecurityError as e:
            return web.json_response({
                'success': False,
                'message': '安全错误',
                'code': e.code
            }, status=e.code)
        except ValidationError as e:
            return web.json_response({
                'success': False,
                'message': '数据验证失败',
                'code': e.code
            }, status=e.code)
        except TaskError as e:
            return web.json_response({
                'success': False,
                'message': '任务操作失败',
                'code': e.code
            }, status=e.code)
        except NodeError as e:
            return web.json_response({
                'success': False,
                'message': '节点操作失败',
                'code': e.code
            }, status=e.code)
        except WebSocketError as e:
            return web.json_response({
                'success': False,
                'message': 'WebSocket操作失败',
                'code': e.code
            }, status=e.code)
        except ResourceError as e:
            return web.json_response({
                'success': False,
                'message': '资源操作失败',
                'code': e.code
            }, status=e.code)
        except InternalError as e:
            return web.json_response({
                'success': False,
                'message': '内部服务器错误',
                'code': e.code
            }, status=e.code)
        except RAMGeoException as e:
            return web.json_response({
                'success': False,
                'message': str(e),
                'code': e.code
            }, status=e.code)
        except Exception as e:
            logger.error(f"未处理的异常: {e}")
            return web.json_response({
                'success': False,
                'message': '服务器内部错误',
                'code': 500
            }, status=500)
    
    def get_middlewares(self) -> list:
        """
        获取所有中间件
        
        Returns:
            中间件列表
        """
        return [
            self.log_middleware,
            self.cors_middleware,
            self.api_key_middleware,
            self.auth_middleware,
            self.error_middleware,
        ]
