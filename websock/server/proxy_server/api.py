#!/usr/bin/env python3
"""
API模块
提供REST API接口
"""

import json
import logging
from typing import Dict, Any, Optional
from aiohttp import web

from shared.logger import setup_logging
from shared.exceptions import *
from .auth_manager import AuthManager
from .node_manager import NodeManager
from .task_manager import TaskManager
from .file_manager import FileManager

logger = setup_logging(__name__)


class APIHandler:
    """
    API处理器类
    """
    
    def __init__(self, config: Dict[str, Any], auth_manager: AuthManager, 
                 node_manager: NodeManager, task_manager: TaskManager, 
                 file_manager: FileManager):
        """
        初始化API处理器
        
        Args:
            config: 配置信息
            auth_manager: 认证管理器实例
            node_manager: 节点管理器实例
            task_manager: 任务管理器实例
            file_manager: 文件管理器实例
        """
        self.config = config
        self.auth_manager = auth_manager
        self.node_manager = node_manager
        self.task_manager = task_manager
        self.file_manager = file_manager
    
    # ------------------- 认证相关API -------------------
    
    async def login(self, request: web.Request) -> web.Response:
        """
        用户登录API
        
        Args:
            request: 请求对象
        
        Returns:
            响应对象
        """
        try:
            data = await request.json()
            username = data.get('username')
            password = data.get('password')
            
            if not username or not password:
                raise BadRequestError("用户名和密码不能为空")
            
            # 认证用户
            user_info = await self.auth_manager.authenticate_user(username, password)
            
            # 生成JWT令牌
            token = await self.auth_manager.generate_jwt_token(user_info)
            
            return web.json_response({
                'success': True,
                'message': '登录成功',
                'data': {
                    'token': token,
                    'user': user_info
                }
            })
            
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
        except Exception as e:
            logger.error(f"登录API失败: {e}")
            return web.json_response({
                'success': False,
                'message': '登录过程中发生错误',
                'code': 500
            }, status=500)
    
    async def get_user_info(self, request: web.Request) -> web.Response:
        """
        获取用户信息API
        
        Args:
            request: 请求对象
        
        Returns:
            响应对象
        """
        try:
            # 从请求上下文中获取用户信息
            user_info = request.get('user_info')
            
            if not user_info:
                raise AuthenticationError("未认证的用户")
            
            return web.json_response({
                'success': True,
                'message': '获取用户信息成功',
                'data': user_info
            })
            
        except AuthenticationError as e:
            return web.json_response({
                'success': False,
                'message': str(e),
                'code': e.code
            }, status=e.code)
        except Exception as e:
            logger.error(f"获取用户信息API失败: {e}")
            return web.json_response({
                'success': False,
                'message': '获取用户信息过程中发生错误',
                'code': 500
            }, status=500)
    
    async def generate_api_key(self, request: web.Request) -> web.Response:
        """
        生成API密钥API
        
        Args:
            request: 请求对象
        
        Returns:
            响应对象
        """
        try:
            # 从请求上下文中获取用户信息
            user_info = request.get('user_info')
            
            if not user_info:
                raise AuthenticationError("未认证的用户")
            
            # 获取请求参数
            data = await request.json()
            description = data.get('description', '')
            
            # 生成API密钥
            api_key = await self.auth_manager.generate_api_key(user_info['id'], description)
            
            return web.json_response({
                'success': True,
                'message': '生成API密钥成功',
                'data': {
                    'api_key': api_key
                }
            })
            
        except AuthenticationError as e:
            return web.json_response({
                'success': False,
                'message': str(e),
                'code': e.code
            }, status=e.code)
        except Exception as e:
            logger.error(f"生成API密钥API失败: {e}")
            return web.json_response({
                'success': False,
                'message': '生成API密钥过程中发生错误',
                'code': 500
            }, status=500)
    
    # ------------------- 节点管理API -------------------
    
    async def get_nodes(self, request: web.Request) -> web.Response:
        """
        获取节点列表API
        
        Args:
            request: 请求对象
        
        Returns:
            响应对象
        """
        try:
            # 从请求上下文中获取用户信息
            user_info = request.get('user_info')
            
            if not user_info:
                raise AuthenticationError("未认证的用户")
            
            # 检查权限
            if not await self.auth_manager.authorize_role(user_info['role'], 'manager'):
                raise AuthorizationError("没有权限访问此API")
            
            # 获取节点列表
            nodes = await self.node_manager.get_all_nodes()
            
            return web.json_response({
                'success': True,
                'message': '获取节点列表成功',
                'data': {
                    'nodes': nodes
                }
            })
            
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
        except Exception as e:
            logger.error(f"获取节点列表API失败: {e}")
            return web.json_response({
                'success': False,
                'message': '获取节点列表过程中发生错误',
                'code': 500
            }, status=500)
    
    async def get_node(self, request: web.Request) -> web.Response:
        """
        获取节点详情API
        
        Args:
            request: 请求对象
        
        Returns:
            响应对象
        """
        try:
            # 从请求上下文中获取用户信息
            user_info = request.get('user_info')
            
            if not user_info:
                raise AuthenticationError("未认证的用户")
            
            # 检查权限
            if not await self.auth_manager.authorize_role(user_info['role'], 'manager'):
                raise AuthorizationError("没有权限访问此API")
            
            # 获取节点ID
            node_id = request.match_info.get('node_id')
            
            # 获取节点详情
            node = await self.node_manager.get_node(node_id)
            
            return web.json_response({
                'success': True,
                'message': '获取节点详情成功',
                'data': {
                    'node': node
                }
            })
            
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
        except Exception as e:
            logger.error(f"获取节点详情API失败: {e}")
            return web.json_response({
                'success': False,
                'message': '获取节点详情过程中发生错误',
                'code': 500
            }, status=500)
    
    # ------------------- 任务管理API -------------------
    
    async def create_task(self, request: web.Request) -> web.Response:
        """
        创建任务API
        
        Args:
            request: 请求对象
        
        Returns:
            响应对象
        """
        try:
            # 从请求上下文中获取用户信息
            user_info = request.get('user_info')
            
            if not user_info:
                raise AuthenticationError("未认证的用户")
            
            # 获取请求数据
            data = await request.json()
            task_type = data.get('type')
            params = data.get('params', {})
            priority = data.get('priority', 'medium')
            
            if not task_type:
                raise BadRequestError("任务类型不能为空")
            
            # 创建任务
            task = await self.task_manager.create_task(
                user_id=user_info['id'],
                task_type=task_type,
                params=params,
                priority=priority
            )
            
            return web.json_response({
                'success': True,
                'message': '创建任务成功',
                'data': {
                    'task': task
                }
            })
            
        except AuthenticationError as e:
            return web.json_response({
                'success': False,
                'message': str(e),
                'code': e.code
            }, status=e.code)
        except BadRequestError as e:
            return web.json_response({
                'success': False,
                'message': str(e),
                'code': e.code
            }, status=e.code)
        except Exception as e:
            logger.error(f"创建任务API失败: {e}")
            return web.json_response({
                'success': False,
                'message': '创建任务过程中发生错误',
                'code': 500
            }, status=500)
    
    async def get_tasks(self, request: web.Request) -> web.Response:
        """
        获取任务列表API
        
        Args:
            request: 请求对象
        
        Returns:
            响应对象
        """
        try:
            # 从请求上下文中获取用户信息
            user_info = request.get('user_info')
            
            if not user_info:
                raise AuthenticationError("未认证的用户")
            
            # 获取查询参数
            status = request.query.get('status')
            page = int(request.query.get('page', 1))
            page_size = int(request.query.get('page_size', 10))
            
            # 获取任务列表
            tasks, total = await self.task_manager.get_tasks(
                user_id=user_info['id'],
                status=status,
                page=page,
                page_size=page_size
            )
            
            return web.json_response({
                'success': True,
                'message': '获取任务列表成功',
                'data': {
                    'tasks': tasks,
                    'total': total,
                    'page': page,
                    'page_size': page_size
                }
            })
            
        except AuthenticationError as e:
            return web.json_response({
                'success': False,
                'message': str(e),
                'code': e.code
            }, status=e.code)
        except Exception as e:
            logger.error(f"获取任务列表API失败: {e}")
            return web.json_response({
                'success': False,
                'message': '获取任务列表过程中发生错误',
                'code': 500
            }, status=500)
    
    async def get_task(self, request: web.Request) -> web.Response:
        """
        获取任务详情API
        
        Args:
            request: 请求对象
        
        Returns:
            响应对象
        """
        try:
            # 从请求上下文中获取用户信息
            user_info = request.get('user_info')
            
            if not user_info:
                raise AuthenticationError("未认证的用户")
            
            # 获取任务ID
            task_id = request.match_info.get('task_id')
            
            # 获取任务详情
            task = await self.task_manager.get_task(task_id)
            
            # 检查任务权限
            if task['user_id'] != user_info['id'] and not await self.auth_manager.authorize_role(user_info['role'], 'manager'):
                raise AuthorizationError("没有权限访问此任务")
            
            return web.json_response({
                'success': True,
                'message': '获取任务详情成功',
                'data': {
                    'task': task
                }
            })
            
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
        except Exception as e:
            logger.error(f"获取任务详情API失败: {e}")
            return web.json_response({
                'success': False,
                'message': '获取任务详情过程中发生错误',
                'code': 500
            }, status=500)
    
    async def cancel_task(self, request: web.Request) -> web.Response:
        """
        取消任务API
        
        Args:
            request: 请求对象
        
        Returns:
            响应对象
        """
        try:
            # 从请求上下文中获取用户信息
            user_info = request.get('user_info')
            
            if not user_info:
                raise AuthenticationError("未认证的用户")
            
            # 获取任务ID
            task_id = request.match_info.get('task_id')
            
            # 获取任务详情
            task = await self.task_manager.get_task(task_id)
            
            # 检查任务权限
            if task['user_id'] != user_info['id'] and not await self.auth_manager.authorize_role(user_info['role'], 'manager'):
                raise AuthorizationError("没有权限操作此任务")
            
            # 取消任务
            await self.task_manager.cancel_task(task_id)
            
            return web.json_response({
                'success': True,
                'message': '取消任务成功',
            })
            
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
        except Exception as e:
            logger.error(f"取消任务API失败: {e}")
            return web.json_response({
                'success': False,
                'message': '取消任务过程中发生错误',
                'code': 500
            }, status=500)
    
    # ------------------- 文件管理API -------------------
    
    async def upload_file(self, request: web.Request) -> web.Response:
        """
        文件上传API
        
        Args:
            request: 请求对象
        
        Returns:
            响应对象
        """
        try:
            # 从请求上下文中获取用户信息
            user_info = request.get('user_info')
            
            if not user_info:
                raise AuthenticationError("未认证的用户")
            
            # 解析表单数据
            reader = await request.multipart()
            file_field = await reader.next()
            
            if not file_field or file_field.name != 'file':
                raise BadRequestError("文件字段不能为空")
            
            filename = file_field.filename
            content = await file_field.read()
            
            # 保存文件
            saved_filename = await self.file_manager.save_file(content, filename, user_info['id'])
            
            return web.json_response({
                'success': True,
                'message': '文件上传成功',
                'data': {
                    'filename': saved_filename,
                    'original_filename': filename,
                    'size': len(content)
                }
            })
            
        except AuthenticationError as e:
            return web.json_response({
                'success': False,
                'message': str(e),
                'code': e.code
            }, status=e.code)
        except BadRequestError as e:
            return web.json_response({
                'success': False,
                'message': str(e),
                'code': e.code
            }, status=e.code)
        except Exception as e:
            logger.error(f"文件上传API失败: {e}")
            return web.json_response({
                'success': False,
                'message': '文件上传过程中发生错误',
                'code': 500
            }, status=500)
    
    async def download_file(self, request: web.Request) -> web.Response:
        """
        文件下载API
        
        Args:
            request: 请求对象
        
        Returns:
            响应对象
        """
        try:
            # 从请求上下文中获取用户信息
            user_info = request.get('user_info')
            
            if not user_info:
                raise AuthenticationError("未认证的用户")
            
            # 获取文件名
            filename = request.match_info.get('filename')
            
            # 获取文件内容
            content = await self.file_manager.get_file(filename)
            
            # 获取文件信息
            file_info = await self.file_manager.get_file_info(filename)
            
            # 检查权限
            if not filename.startswith(f"{user_info['id']}_") and not await self.auth_manager.authorize_role(user_info['role'], 'manager'):
                raise AuthorizationError("没有权限访问此文件")
            
            # 返回文件
            return web.Response(
                body=content,
                headers={
                    'Content-Type': 'application/octet-stream',
                    'Content-Disposition': f'attachment; filename={file_info.get("original_filename", filename)}',
                    'Content-Length': str(len(content))
                }
            )
            
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
        except Exception as e:
            logger.error(f"文件下载API失败: {e}")
            return web.json_response({
                'success': False,
                'message': '文件下载过程中发生错误',
                'code': 500
            }, status=500)
    
    # ------------------- 系统监控API -------------------
    
    async def get_system_status(self, request: web.Request) -> web.Response:
        """
        获取系统状态API
        
        Args:
            request: 请求对象
        
        Returns:
            响应对象
        """
        try:
            # 从请求上下文中获取用户信息
            user_info = request.get('user_info')
            
            if not user_info:
                raise AuthenticationError("未认证的用户")
            
            # 检查权限
            if not await self.auth_manager.authorize_role(user_info['role'], 'manager'):
                raise AuthorizationError("没有权限访问此API")
            
            # 获取系统状态
            system_status = {
                'nodes': await self.node_manager.get_nodes_status(),
                'tasks': await self.task_manager.get_tasks_status(),
                'resources': await self.get_system_resources()
            }
            
            return web.json_response({
                'success': True,
                'message': '获取系统状态成功',
                'data': system_status
            })
            
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
        except Exception as e:
            logger.error(f"获取系统状态API失败: {e}")
            return web.json_response({
                'success': False,
                'message': '获取系统状态过程中发生错误',
                'code': 500
            }, status=500)
    
    async def get_system_resources(self) -> Dict[str, Any]:
        """
        获取系统资源使用情况
        
        Returns:
            系统资源使用情况
        """
        import psutil
        
        try:
            # CPU使用率
            cpu_usage = psutil.cpu_percent(interval=1)
            
            # 内存使用率
            mem = psutil.virtual_memory()
            memory_usage = mem.percent
            memory_available = mem.available
            memory_total = mem.total
            
            # 磁盘使用率
            disk = psutil.disk_usage('/')
            disk_usage = disk.percent
            disk_free = disk.free
            disk_total = disk.total
            
            # 网络IO
            net = psutil.net_io_counters()
            net_sent = net.bytes_sent
            net_recv = net.bytes_recv
            
            return {
                'cpu_usage': cpu_usage,
                'memory': {
                    'usage_percent': memory_usage,
                    'available': memory_available,
                    'total': memory_total
                },
                'disk': {
                    'usage_percent': disk_usage,
                    'free': disk_free,
                    'total': disk_total
                },
                'network': {
                    'sent': net_sent,
                    'recv': net_recv
                }
            }
            
        except Exception as e:
            logger.error(f"获取系统资源失败: {e}")
            return {}


def setup_routes(app: web.Application, api_handler: APIHandler) -> None:
    """
    设置API路由
    
    Args:
        app: aiohttp应用实例
        api_handler: API处理器实例
    """
    # 认证相关路由
    app.router.add_post('/api/login', api_handler.login)
    app.router.add_get('/api/user', api_handler.get_user_info)
    app.router.add_post('/api/api-key', api_handler.generate_api_key)
    
    # 节点管理路由
    app.router.add_get('/api/nodes', api_handler.get_nodes)
    app.router.add_get('/api/nodes/{node_id}', api_handler.get_node)
    
    # 任务管理路由
    app.router.add_post('/api/tasks', api_handler.create_task)
    app.router.add_get('/api/tasks', api_handler.get_tasks)
    app.router.add_get('/api/tasks/{task_id}', api_handler.get_task)
    app.router.add_post('/api/tasks/{task_id}/cancel', api_handler.cancel_task)
    
    # 文件管理路由
    app.router.add_post('/api/files/upload', api_handler.upload_file)
    app.router.add_get('/api/files/{filename}', api_handler.download_file)
    
    # 系统监控路由
    app.router.add_get('/api/system/status', api_handler.get_system_status)
