#!/usr/bin/env python3
"""
异常模块
定义系统中使用的自定义异常类
"""


class RAMGeoException(Exception):
    """
    RAMGEO系统基础异常类
    """
    def __init__(self, message: str, code: int = 500, details: dict = None):
        """
        初始化基础异常
        
        Args:
            message: 异常消息
            code: 错误代码
            details: 详细信息
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
    
    def to_dict(self) -> dict:
        """
        将异常转换为字典
        
        Returns:
            异常信息字典
        """
        return {
            'error': {
                'code': self.code,
                'message': self.message,
                'details': self.details
            }
        }


class ConfigurationError(RAMGeoException):
    """
    配置错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=500, details=details)


class DatabaseError(RAMGeoException):
    """
    数据库错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=500, details=details)


class RedisError(RAMGeoException):
    """
    Redis错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=500, details=details)


class NetworkError(RAMGeoException):
    """
    网络错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=503, details=details)


class WebSocketError(RAMGeoException):
    """
    WebSocket错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=503, details=details)


class AuthenticationError(RAMGeoException):
    """
    认证错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=401, details=details)


class AuthorizationError(RAMGeoException):
    """
    授权错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=403, details=details)


class ValidationError(RAMGeoException):
    """
    验证错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=400, details=details)


class NotFoundError(RAMGeoException):
    """
    资源未找到异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=404, details=details)


class ConflictError(RAMGeoException):
    """
    资源冲突异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=409, details=details)


class RateLimitError(RAMGeoException):
    """
    速率限制异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=429, details=details)


class TaskError(RAMGeoException):
    """
    任务错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=500, details=details)


class NodeError(RAMGeoException):
    """
    节点错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=500, details=details)


class FileError(RAMGeoException):
    """
    文件错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=500, details=details)


class ExecutionError(RAMGeoException):
    """
    执行错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=500, details=details)


class ResourceError(RAMGeoException):
    """
    资源错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=500, details=details)


class TimeoutError(RAMGeoException):
    """
    超时错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=504, details=details)


class InternalServerError(RAMGeoException):
    """
    内部服务器错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=500, details=details)


class ServiceUnavailableError(RAMGeoException):
    """
    服务不可用异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=503, details=details)


class BadRequestError(RAMGeoException):
    """
    请求错误异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=400, details=details)


class UnsupportedMediaTypeError(RAMGeoException):
    """
    不支持的媒体类型异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=415, details=details)


class PayloadTooLargeError(RAMGeoException):
    """
    请求体过大异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=413, details=details)


class TooManyRequestsError(RAMGeoException):
    """
    请求过多异常
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code=429, details=details)


# 快捷函数
def raise_config_error(message: str, details: dict = None) -> None:
    """
    抛出配置错误异常
    """
    raise ConfigurationError(message, details)


def raise_database_error(message: str, details: dict = None) -> None:
    """
    抛出数据库错误异常
    """
    raise DatabaseError(message, details)


def raise_redis_error(message: str, details: dict = None) -> None:
    """
    抛出Redis错误异常
    """
    raise RedisError(message, details)


def raise_network_error(message: str, details: dict = None) -> None:
    """
    抛出网络错误异常
    """
    raise NetworkError(message, details)


def raise_websocket_error(message: str, details: dict = None) -> None:
    """
    抛出WebSocket错误异常
    """
    raise WebSocketError(message, details)


def raise_auth_error(message: str, details: dict = None) -> None:
    """
    抛出认证错误异常
    """
    raise AuthenticationError(message, details)


def raise_authorization_error(message: str, details: dict = None) -> None:
    """
    抛出授权错误异常
    """
    raise AuthorizationError(message, details)


def raise_validation_error(message: str, details: dict = None) -> None:
    """
    抛出验证错误异常
    """
    raise ValidationError(message, details)


def raise_not_found_error(message: str, details: dict = None) -> None:
    """
    抛出资源未找到异常
    """
    raise NotFoundError(message, details)


def raise_conflict_error(message: str, details: dict = None) -> None:
    """
    抛出资源冲突异常
    """
    raise ConflictError(message, details)


def raise_task_error(message: str, details: dict = None) -> None:
    """
    抛出任务错误异常
    """
    raise TaskError(message, details)


def raise_node_error(message: str, details: dict = None) -> None:
    """
    抛出节点错误异常
    """
    raise NodeError(message, details)


def raise_file_error(message: str, details: dict = None) -> None:
    """
    抛出文件错误异常
    """
    raise FileError(message, details)


def raise_execution_error(message: str, details: dict = None) -> None:
    """
    抛出执行错误异常
    """
    raise ExecutionError(message, details)


def raise_resource_error(message: str, details: dict = None) -> None:
    """
    抛出资源错误异常
    """
    raise ResourceError(message, details)


def raise_timeout_error(message: str, details: dict = None) -> None:
    """
    抛出超时错误异常
    """
    raise TimeoutError(message, details)


def raise_internal_error(message: str, details: dict = None) -> None:
    """
    抛出内部服务器错误异常
    """
    raise InternalServerError(message, details)


def raise_service_unavailable(message: str, details: dict = None) -> None:
    """
    抛出服务不可用异常
    """
    raise ServiceUnavailableError(message, details)


def raise_bad_request(message: str, details: dict = None) -> None:
    """
    抛出请求错误异常
    """
    raise BadRequestError(message, details)


def raise_unsupported_media_type(message: str, details: dict = None) -> None:
    """
    抛出不支持的媒体类型异常
    """
    raise UnsupportedMediaTypeError(message, details)


def raise_payload_too_large(message: str, details: dict = None) -> None:
    """
    抛出请求体过大异常
    """
    raise PayloadTooLargeError(message, details)


def raise_too_many_requests(message: str, details: dict = None) -> None:
    """
    抛出请求过多异常
    """
    raise TooManyRequestsError(message, details)
