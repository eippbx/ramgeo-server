# Proxy Server REST API 文档

## 1. 概述

Proxy Server REST API 提供了对代理服务器的完整管理功能，包括节点管理、任务调度、文件传输和系统监控等。API 基于 FastAPI 构建，提供了高性能的 RESTful 接口。

### 1.1 基本信息

- **API 版本**: 1.0.0
- **Base URL**: `http://192.168.84.251:8080`
- **响应格式**: JSON

## 3. 健康检查

### 3.1 获取系统状态

**Endpoint**: `GET /api/v1/status`
**描述**: 检查代理服务器的健康状态

**响应示例**:
```json
{
  "status": "ok",
  "timestamp": "2024-07-01T00:00:00Z"
}
```

## 4. 节点管理

### 4.1 获取节点列表

**Endpoint**: `GET /api/v1/nodes`
**描述**: 获取所有节点的信息

**响应示例**:
```json
{
  "nodes": [
    {
      "node_id": "node-123",
      "node_name": "Node Server 123",
      "status": "HEALTHY",    // 节点状态
      "capabilities": {       // 节点的硬件规格
        "cpu_count": 4,
        "memory_gb": 8,
        "disk_gb": 100
      },
      "load": {
        "cpu_usage": 0.25,
        "memory_usage": 0.45,
        "disk_usage": 0.50
      },
      "active_tasks": 2,
      "last_heartbeat": "2024-07-01T12:34:56Z",
      "ip_address": "192.168.1.100"
    }
    {
      "node_id": "node-124",
      "node_name": "Node Server 124",
      "status": "HEALTHY",    // 节点状态
      "capabilities": {       // 节点的硬件规格
        "cpu_count": 4,
        "memory_gb": 8,
        "disk_gb": 100
      },
      "load": {
        "cpu_usage": 0.25,
        "memory_usage": 0.35,
        "disk_usage": 0.15
      },
      "active_tasks": 2,
      "last_heartbeat": "2024-07-01T12:34:56Z",
      "ip_address": "192.168.1.101"
    }
  ],
  "total": 2
}
```

### 4.2 获取节点详情

**Endpoint**: `GET /api/v1/nodes/{node_id}`
**认证**: 需要
**描述**: 获取指定节点的详细信息

**路径参数**:
- `node_id`: 节点 ID

**响应示例**:
```json
{
  "node_id": "node-123",
  "status": "HEALTHY",
  "capabilities": {
    "cpu_count": 4,
    "memory_gb": 8,
    "supported_tasks": ["task_type_1", "task_type_2"]
  },
  "load": {
    "cpu_usage": 0.25,
    "memory_usage": 0.45,
    "disk_usage": 0.50
  },
  "active_tasks": 2,
  "last_heartbeat": "2024-07-01T12:34:56Z",
  "ip_address": "192.168.1.100"
}
```

### 4.4 将节点设置为排水模式

**Endpoint**: `POST /api/v1/nodes/{node_id}/drain`
**认证**: 需要
**描述**: 将节点设置为排水模式，不再分配新任务

**路径参数**:
- `node_id`: 节点 ID

**响应示例**:
```json
{
  "node_id": "node-123",
  "action": "drain",
  "status": "success"
}
```

### 4.5 激活节点

**Endpoint**: `POST /api/v1/nodes/{node_id}/activate`
**认证**: 需要
**描述**: 激活节点，使其可以接收新任务

**路径参数**:
- `node_id`: 节点 ID

**响应示例**:
```json
{
  "node_id": "node-123",
  "action": "activate",
  "status": "success"
}
```

## 5. 任务管理

### 5.1 创建新任务

**Endpoint**: `POST /api/v1/tasks/upload?task_type=task_type_1`
**描述**: POST方式发送一个ramgeo.in文件到服务端，创建一个新任务.

**请求体**:
type:multipart/form-data
form-data:
- `file` (必需): 包含任务定义的ramgeo.in文件
  type:file


**响应示例**:
```json
{
  "task_id": "task-456",
  "status": "pending",
  "message": "Task uploaded successfully"
}
```

### 5.2 获取任务列表

**Endpoint**: `GET /api/v1/tasks`
**认证**: 需要
**描述**: 获取任务列表

**查询参数**:
- `status` (可选): 根据任务状态过滤
- `priority` (可选): 根据任务优先级过滤
- `limit` (可选): 结果数量限制，默认: 100
- `offset` (可选): 分页偏移量，默认: 0

**响应示例**:
```json
{
  "tasks": [
    {
      "task_id": "TOKEN",
      "status": "RUNNING",
      "assigned_node_id": "node-123", // 已分配节点ID
      "created_at": "2024-07-01T12:00:00Z",
      "started_at": "2024-07-01T12:01:00Z",
      "completed_at": null,
      "error": null,
      "retry_count": 0
    },
    {
      "task_id": "TOKEN",
      "status": "COMPLETED",
      "assigned_node_id": "node-124",
      "created_at": "2024-07-01T12:02:00Z",
      "started_at": "2024-07-01T12:03:00Z",
      "completed_at": "2024-07-01T12:04:00Z",
      "error": null,
      "retry_count": 0
    },
  ],
  "total": 2,
  "limit": 100,   // 每页返回任务数量，默认100
  "offset": 0     // 偏移量，默认0，用于分页查询
}
```

### 5.3 获取任务详情

**Endpoint**: `GET /api/v1/tasks/{task_id}`
**描述**: 获取指定任务的详细信息

**路径参数**:
- `task_id`: 任务 ID

**响应示例**:
```json
{
  "task_id": "TOKEN",    // 任务ID
  "status": "RUNNING",      // 任务状态，PENDING|SCHEDULED|RUNNING|COMPLETED|FAILED
  "assigned_node_id": "node-123",         // 已分配节点ID
  "created_at": "2024-07-01T12:00:00Z",   // 任务创建时间
  "started_at": "2024-07-01T12:01:00Z",   // 任务开始执行时间
  "completed_at": null,   // 任务完成时间，COMPLETED时为任务完成时间
  "error": null,          // 任务执行错误信息，FAILED时为错误详情
  "retry_count": 0,       // 当前重试次数，FAILED时为重试次数
}
```

### 5.4 取消任务

**Endpoint**: `POST /api/v1/tasks/{task_id}/cancel`
**描述**: 取消指定任务

**路径参数**:
- `task_id`: 任务 ID

**响应示例**:
```json
{
  "task_id": "task-456",
  "status": "cancelled"
}
```
### 5.5 下载任务完成文件

## 6. 文件管理

### 6.1 获取文件传输列表

**Endpoint**: `GET /api/v1/files/transfers`
**认证**: 需要
**描述**: 获取所有文件传输的信息

**查询参数**:
- `status` (可选): 根据传输状态过滤

**响应示例**:
```json
{
  "transfers": [
    {
      "transfer_id": "transfer-123",
      "filename": "large_file.zip",
      "total_chunks": 10,
      "total_size": 10485760,
      "status": "COMPLETED",
      "received_chunks_count": 10,
      "received_size": 10485760,
      "start_time": "2024-07-01T12:00:00Z",
      "completed_at": "2024-07-01T12:02:00Z",
      "node_id": "node-123",
      "checksum": "d41d8cd98f00b204e9800998ecf8427e",
      "chunk_size": 1048576,
      "progress": 100.0
    }
  ],
  "total": 1
}
```

### 6.2 获取文件下载链接

首先，需要获取任务状态。如果任务状态为COMPLETED，才可以获取文件下载链接。

- **获取任务完成后生成的line文件**
**Endpoint**: `GET /api/v1/tasks/files/{task_id}.line`
**描述**: 获取任务完成后生成的line文件

- **获取任务完成后生成的grid文件**
**Endpoint**: `GET /api/v1/tasks/files/{task_id}.grid`
**描述**: 获取任务完成后生成的grid文件

### v1.0.0 (2024-07-01)

- 初始版本发布