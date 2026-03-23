from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime
import json


class MessageType(str, Enum):
    REGISTER = "register"
    REGISTER_RESPONSE = "register_response"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_RESPONSE = "heartbeat_response"
    STATUS_REPORT = "status_report"
    TASK_ASSIGN = "task_assign"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETE = "task_complete"
    TASK_FAILED = "task_failed"
    FILE_TRANSFER = "file_transfer"
    CHUNK_RECEIVED = "chunk_received"
    CONNECTED = "connected"
    SHUTDOWN = "shutdown"


class NodeStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    BUSY = "BUSY"
    IDLE = "IDLE"
    OFFLINE = "OFFLINE"
    DRAINING = "DRAINING"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WebSocketCloseCode(int, Enum):
    NORMAL_CLOSURE = 1000
    AUTHENTICATION_FAILED = 1003
    NODE_REGISTERED = 1005
    INVALID_MESSAGE_TYPE = 1008
    INTERNAL_SERVER_ERROR = 1011
    ABNORMAL_CLOSURE = 1006


class TaskPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class LoadBalancingStrategy(str, Enum):
    RANDOM = "RANDOM"
    ROUND_ROBIN = "ROUND_ROBIN"
    LEAST_CONNECTIONS = "LEAST_CONNECTIONS"
    WEIGHTED_ROUND_ROBIN = "WEIGHTED_ROUND_ROBIN"
    WEIGHTED_LEAST_CONNECTIONS = "WEIGHTED_LEAST_CONNECTIONS"
    LEAST_LOAD = "LEAST_LOAD"
    AFFINITY = "AFFINITY"


class ErrorCode(str, Enum):
    NODE_OFFLINE = "NODE_OFFLINE"
    TASK_TIMEOUT = "TASK_TIMEOUT"
    FILE_TRANSFER_ERROR = "FILE_TRANSFER_ERROR"
    INVALID_TASK_PARAMS = "INVALID_TASK_PARAMS"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"


class Message:
    def __init__(self, message_type: MessageType, timestamp: Optional[str] = None, **kwargs):
        self.type = message_type
        self.timestamp = timestamp or datetime.utcnow().isoformat() + "Z"
        self.data = kwargs

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.type.value,
            "timestamp": self.timestamp
        }
        result.update(self.data)
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        message_type = MessageType(data.get("type"))
        timestamp = data.get("timestamp")
        message_data = {k: v for k, v in data.items() if k not in ["type", "timestamp"]}
        return cls(message_type, timestamp, **message_data)

    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        data = json.loads(json_str)
        return cls.from_dict(data)


class NodeCapabilities:
    def __init__(self, cpu_cores: int, memory_gb: float, disk_gb: float):
        self.cpu_cores = cpu_cores
        self.memory_gb = memory_gb
        self.disk_gb = disk_gb

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_count": self.cpu_cores,
            "memory_gb": self.memory_gb,
            "disk_gb": self.disk_gb
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeCapabilities":
        return cls(
            cpu_cores=data.get("cpu_cores", data.get("cpu_count", 0)),
            memory_gb=data.get("memory_gb", 0),
            disk_gb=data.get("disk_gb", 0)
        )


class NodeLoad:
    def __init__(self, cpu_usage: float = 0.0, memory_usage: float = 0.0, 
                 disk_usage: float = 0.0, active_tasks: int = 0,
                 system_temperature: Optional[float] = None):
        self.cpu_usage = cpu_usage
        self.memory_usage = memory_usage
        self.disk_usage = disk_usage
        self.active_tasks = active_tasks
        self.system_temperature = system_temperature

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "disk_usage": self.disk_usage,
            "active_tasks": self.active_tasks
        }
        if self.system_temperature is not None:
            result["system_temperature"] = self.system_temperature
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeLoad":
        return cls(
            cpu_usage=data.get("cpu_load", data.get("cpu_usage", 0.0)),
            memory_usage=data.get("memory_usage", 0.0),
            disk_usage=data.get("disk_usage", 0.0),
            active_tasks=data.get("active_tasks", 0),
            system_temperature=data.get("system_temperature")
        )


class TaskInfo:
    def __init__(self, task_id: str, task_type: str, parameters: Dict[str, Any],
                 priority: TaskPriority = TaskPriority.NORMAL):
        self.task_id = task_id
        self.task_type = task_type
        self.parameters = parameters
        self.priority = priority
        self.status = TaskStatus.PENDING
        self.node_id = None
        self.created_at = datetime.utcnow()
        self.started_at = None
        self.completed_at = None
        self.result = None
        self.error = None
        self.retry_count = 0
        self.max_retries = 3
        self.file_uploaded = False
        self.input_file_path = None
        self.output_files = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "parameters": self.parameters,
            "priority": self.priority.value,
            "status": self.status.value,
            "assigned_node_id": self.node_id,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "started_at": self.started_at.isoformat() + "Z" if self.started_at else None,
            "completed_at": self.completed_at.isoformat() + "Z" if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "file_uploaded": self.file_uploaded,
            "input_file_path": self.input_file_path,
            "output_files": self.output_files
        }
