# Proxy Server 开发需求技术文档

## 1. 概述

本文档详细描述了 `proxy_server`（代理服务器）的开发需求和技术规范，作为 RAMGEO 分布式计算系统的核心组件，代理服务器负责节点管理、任务调度、文件传输和客户端接口提供。

### 1.1 开发语言
- **Proxy Server**: 基于 Python 3.12 实现
- **运行环境**: Ubuntu 22.04 或以上版本
- **运行方式**: 使用conda activate ramgeo 激活ramgeo环境后，运行python -m proxy_server.main 启动服务

### 1.2 核心功能
- 节点管理：注册、心跳监测和状态管理
- 任务调度：接收客户端任务、分配节点、跟踪执行状态
- 文件传输：管理任务输入文件分发和结果文件收集
- 负载均衡：根据节点能力和状态分配任务
- 客户端接口：提供 REST API 供客户端访问系统功能

## 2. 系统架构

### 2.1 核心组件

- **WebSocket 服务器**: 管理与计算节点的 WebSocket 连接，处理节点注册、认证、心跳和消息通信
- **任务管理器**: 接收客户端任务、维护任务队列、分配任务、跟踪任务状态
- **节点管理器**: 管理节点生命周期、监控节点状态、维护节点能力信息
- **负载均衡器**: 根据预设策略选择合适节点执行任务
- **文件管理器**: 处理文件上传、分片传输、完整性校验和存储管理
- **REST API 服务**: 提供客户端访问的 RESTful 接口

### 2.2 架构图
```
┌─────────────────────────────────────────────────────┐
│                   客户端层                           │
│                ┌─────────────┐                      │
│                │   API集成   │                       │
│                └─────────────┘                      │
└─────────────────────────────────────────────────────┘
                       │ HTTP
┌─────────────────────────────────────────────────────┐
│             代理服务器层 `proxy_server`               │
│  ┌───────────────────────────────────────────────┐  │
│  │            分布式任务管理器                      │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐        │  │
│  │  │任务调度   │  │负载均衡  │  │状态监控  │        │  │
│  │  └─────────┘  └─────────┘  └─────────┘        │  │
│  └───────────────────────────────────────────────┘  │
│                   │ WebSocket                       │
└─────────────────────────────────────────────────────┘
                    │ WebSocket
┌────────────────────────────────────────────────────┐
│           计算节点层  `node_server`                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │  节点1       │  │  节点2       │  │  节点N      │ │
│  │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │ │
│  │ │WebSocket│ │  │ │WebSocket│ │  │ │WebSocket│ │ │
│  │ │ 服务器   │ │  │ │ 服务器   │ │  │ │ 服务器   │ │ │
│  │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │ │
│  │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │ │
│  │ │ RAMGEO  │ │  │ │ RAMGEO  │ │  │ │ RAMGEO  │ │ │
│  │ │ 计算引擎 │ │  │ │ 计算引擎  │ │  │ │ 计算引擎 │ │ │
│  │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │ │
│  └─────────────┘  └─────────────┘  └─────────────┘ │
└────────────────────────────────────────────────────┘
```
### 2.3 目录结构

```
proxy_server/   # 代理服务器程序代码
config/         # 配置文件目录
  config.yaml    # 主配置文件
logs/           # 日志文件目录
  proxy.log      # 代理服务器日志文件
uploads/        # 上传文件存储目录

```

## 3. WebSocket 服务

### 3.1 连接端点

- **节点连接端点**: `/node-ws`
- **协议**: WebSocket (ws://) 
- **监听地址**: 0.0.0.0
- **监听端口**: 8765

### 3.2 连接管理

1. **连接建立**: 接受节点的 WebSocket 连接请求
2. **连接认证**: 等待节点发送 `register` 消息进行节点注册
3. **连接保持**: 通过心跳机制维护连接状态
4. **连接关闭**: 支持正常关闭和异常关闭，使用标准关闭码

### 3.3 连接关闭代码

| 关闭码 | 描述 | 原因 | 处理方式 |
|--------|------|------|----------|
| 1003 | Authentication failed | 无效的 node_id 或认证信息 | 关闭连接并发送失败消息 |
| 1005 | Node is registered | 该节点已注册 | 关闭连接并记录错误 |
| 1008 | Invalid message type | 无效的消息类型或格式 | 关闭连接并记录错误 |
| 1000 | Normal closure | 正常关闭连接 | 清理资源 |
| 1011 | Internal server error | 服务器内部错误 | 记录错误并关闭连接 |
| 1006 | Abnormal closure | 连接意外关闭 | 标记节点为离线 |

### 3.4. 消息格式规范

所有消息都采用 JSON 格式，必须包含以下字段：

| 字段名     | 类型   | 描述                     | 必选 | 格式要求 |
|------------|--------|--------------------------|------|----------|
| `type`     | string | 消息类型                 | 是   | 必须是支持的类型之一 |
| `timestamp`| string | 消息发送时间戳（ISO格式）| 是   | 必须是有效的ISO 8601日期时间字符串 |

### 3.4.1 消息验证规则

1. **JSON格式验证**: 所有消息必须是有效的JSON格式
2. **必填字段检查**: 必须包含 `type` 和 `timestamp` 字段
3. **类型验证**: 字段类型必须与规范一致
4. **消息类型检查**: 消息类型必须是支持的类型之一
5. **时间戳验证**: 时间戳必须是有效的ISO 8601格式
6. **内容验证**: 特定消息类型的业务字段必须符合规范

### 3.4.2 支持的消息类型

| 消息类型          | 发送方      | 接收方      | 描述                     | 处理流程 |
|-------------------|-------------|-------------|--------------------------|----------|
| `register`        | Node Server | Proxy Server| 节点注册                 | 验证身份并绑定连接 |
| `register_response`   | Proxy Server| Node Server | 注册结果响应             | 确认连接成功 |
| `heartbeat`       | Proxy Server| Node Server | 心跳检测                 | 更新节点状态并响应 |
| `heartbeat_response` | Node Server | Proxy Server| 心跳响应                 | 重置心跳超时计数器 |
| `status_report`   | Node Server | Proxy Server| 节点状态报告             | 更新节点资源使用情况 |
| `task_assign`     | Proxy Server| Node Server | 任务分配                 | 执行任务并报告进度 |
| `task_progress`   | Proxy Server| Node Server | 任务执行查询             | 报告任务状态 |
| `task_complete`   | Node Server | Proxy Server| 任务完成报告             | 更新任务结果 |
| `task_failed`     | Node Server | Proxy Server| 任务失败报告             | 更新任务状态并尝试重分配 |
| `file_transfer`   | 双向        | 双向        | 文件分片传输             | 存储分片并发送确认 |
| `chunk_received`  | 双向        | 双向        | 文件分片接收确认         | 发送下一个分片或完成传输 |
| `connected`       | Proxy Server| Node Server | 连接确认                 | 开始正常通信流程 |
| `shutdown`        | Proxy Server| Node Server | 关闭请求                 | 节点开始关闭流程 |

## 3.5. 注册机制

### 3.5.1 注册流程

1. Proxy Server 接受节点的 WebSocket 连接
2. Proxy Server 等待节点发送注册消息
3. 节点发送 `register` 消息，包含 `node_id` 和能力信息
4. Proxy Server 验证 `node_id` 的合法性和唯一性
5. 注册成功：发送 `register_response` 消息，状态为 `registered`
6. 注册失败：关闭连接，状态码 1003，消息 "Registration failed"

### 5.2 注册消息处理

- **接收到的node节点注册消息格式**: 
```json
{
  "type": "register",
  "timestamp": "2023-01-01T12:00:00Z",
  "node_id": "node_id",  // 节点唯一标识符，用于在通信中标识节点，在 node_config.yaml 中配置
  "node_name": "node_name",  // 节点名称，用于在 UI 中显示
  "capabilities": {
    "cpu_cores": 4,     // 节点 CPU 核心数
    "memory_gb": 16,    // 节点内存大小（GB）
    "disk_gb": 100     // 节点磁盘大小（GB）
  }
}
```
- **发送的node节点注册响应消息格式**: 
```json
{
  "type": "register_response",
  "timestamp": "2023-01-01T12:00:00Z",
  "status": "registered",  // 注册状态，"registered" 表示成功
  "node_id": "node_id",     // 节点唯一标识符，与注册消息中的 node_id 一致
  "message": "Registration successful"
}
```


## 3.6. 心跳与状态管理

### 3.6.1 心跳机制

1. Proxy Server 每 websocket.heartbeat_interval 秒向所有已认证节点发送 `heartbeat` 消息
2. 节点必须在 10 秒内回复 `heartbeat_response` 消息
3. 连续 3 次心跳超时，标记节点为 `UNHEALTHY`
4. 连续 5 次心跳超时，标记节点为 `OFFLINE`
### 3.6.2 心跳消息格式

```json
{
  "type": "heartbeat",
  "timestamp": "2023-01-01T12:00:30Z"
}
```

### 3.6.3 心跳响应消息格式

```json
{
  "type": "heartbeat_response",
  "timestamp": "2023-01-01T12:00:31Z"
}
```

### 3.6.4 节点状态枚举

| 状态值 | 描述 |
|--------|------|
| `UNKNOWN` | 未知状态 |
| `CONNECTING` | 正在连接 |
| `CONNECTED` | 已连接但未认证 |
| `HEALTHY` | 健康状态 |
| `UNHEALTHY` | 不健康状态（心跳超时或任务失败） |
| `BUSY` | 节点忙碌 |
| `IDLE` | 节点空闲 |
| `OFFLINE` | 节点离线 |

### 3.6.5 状态报告处理

- 接收节点的 `status_report` 消息并更新节点状态
- 状态报告包含：CPU 负载、内存使用、磁盘使用、当前活动任务数
- 用于负载均衡决策和健康检查

### 3.6.6 节点上报状态报告消息格式

```json
{
  "type": "status_report",
  "timestamp": "2023-01-01T12:01:00Z",
  "data": {
    "cpu_load": 0.45,   // 节点 CPU 负载（0-1）
    "memory_usage": 0.6, // 节点内存使用（0-1）
    "disk_usage": 0.75,  // 节点磁盘使用（0-1）
    "active_tasks": 2,    // 节点当前活动任务数
    "system_temperature": 45 // 节点系统温度（摄氏度）
  }
}
```

## 3.7. 负载均衡策略

### 3.7.1 支持的策略

- 在配置文件参数：load_balancing.strategy 中配置负载均衡策略

| 策略名称 | 描述 | 实现要求 |
|----------|------|----------|
| `RANDOM` | 随机选择节点 | 实现简单随机算法 |
| `ROUND_ROBIN` | 轮询选择节点 | 维护节点顺序列表 |
| `LEAST_CONNECTIONS` | 选择连接数最少的节点 | 跟踪每个节点的活动连接数 |
| `WEIGHTED_ROUND_ROBIN` | 加权轮询选择节点 | 根据节点能力分配权重 |
| `LEAST_LOAD` | 选择负载最低的节点 | 基于 CPU/内存负载计算 |
| `AFFINITY` | 根据任务亲和性选择节点 | 支持任务与节点的亲和性配置 |

### 3.7.2 节点能力匹配

- 根据任务的资源需求（CPU、内存等）和节点的能力报告进行匹配
- 选择满足任务资源需求的最合适节点

## 3.8. 任务管理

### 3.8.1 任务状态

| 状态值 | 描述 |
|--------|------|
| `PENDING` | 任务等待分配 |
| `SCHEDULED` | 任务已分配但未开始执行 |
| `RUNNING` | 任务正在执行 |
| `COMPLETED` | 任务执行完成 |
| `FAILED` | 任务执行失败 |

### 3.8.2 任务流程

1. **任务接收**: 通过 REST API 接收客户端提交的任务文件
2. **任务ID生成**: 生成32位唯一任务ID，用于跟踪任务进度和状态
3. **任务队列**: 加入任务队列等待分配
4. **任务分配**: 选择合适节点发送任务文件
5. **接收任务结果文件**: 接收节点处理任务后的结果文件
6. **任务结果处理**: 接收任务结果或失败信息
7. **客户端获取结果文件**: 处理客户端获取结果文件的请求

### 3.8.3 任务分配
通过websock发送任务文件，节点收到文件后，立即处理任务。

## 3.9. 文件传输机制

### 3.9.1 文件传输流程

1. **输入文件分发**: 将客户端上传的输入文件分发给执行节点
2. **大文件分片**: 支持大文件分片传输（1MB-10MB/片）
3. **分片确认**: 接收节点的 `chunk_received` 确认
4. **文件重组**: 节点接收所有分片后重组文件
5. **完整性校验**: 使用 MD5 哈希验证文件完整性
6. **结果文件返回**: 任务处理完成后，将结果文件通过websock发送回Proxy Server，Proxy Server接收到Node Server任务状态更新为COMPLETED。

### 3.9.2 文件传输消息处理

- **发送文件分片**: 
  ```python
  async def send_file_chunks(self, node_id, task_id, filename, file_path):
      # 分割文件为分片
      chunks = self._split_file(file_path)
      total_chunks = len(chunks)
      
      for i, chunk in enumerate(chunks):
          await self.send_message_to_node(node_id, {
              "type": "file_transfer",
              "timestamp": datetime.now().isoformat(),
              "transfer_id": task_id,
              "chunk": base64.b64encode(chunk).decode('utf-8'),
              "index": i,
              "total_chunks": total_chunks,
              "file_hash": self._calculate_file_hash(file_path),
              "chunk_hash": self._calculate_chunk_hash(chunk)
          })
          # 等待分片确认
          await self.wait_for_chunk_confirmation(task_id, i)
  ```

## 4. REST API 接口

### 4.1 任务管理接口

| API路径 | 方法 | 描述 |
|---------|------|------|
| `/api/v1/tasks/upload?task_type={task_type}` | POST | 上传任务输入文件 |
| `/api/v1/tasks` | POST | 获取任务列表 |
| `/api/v1/tasks/{task_id}` | GET | 获取任务详情 |
| `/api/v1/tasks/{task_id}` | DELETE | 取消任务 |
| `/api/v1/tasks/files/{task_id}.line` | GET | 下载任务生成的line文件 |
| `/api/v1/tasks/files/{task_id}.grid` | GET | 下载任务生成的grid文件 |

- **上传任务输入文件**: 客户端通过 POST 请求 `/api/v1/tasks/upload` 上传任务文件，proxy server 接收完成后生成任务ID，值为32位随机TOKEN值，返回任务ID:{TOKEN}, 任务状态为: PENDING|SCHEDULED|RUNNING|COMPLETED|FAILED。
**响应示例**:
```json
{
  "task_id": "TOKEN",
  "status": "pending"
}
```
- **获取任务列表**: 客户端通过 POST 请求 `/api/v1/tasks` 获取任务列表，proxy server 收到请求后，返回任务列表。
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

- **获取任务详情**: 客户端通过 GET 请求 `/api/v1/tasks/{task_id}` 获取任务状态和详情 
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
  "retry_count": 0       // 当前重试次数，FAILED时为重试次数
}
```
- **取消任务**: 客户端通过 DELETE 请求 `/api/v1/tasks/{task_id}/cancel` 取消任务，proxy server 收到请求后，将任务状态更新为CANCELLED。

**响应示例**:
```json
{
  "task_id": "TOKEN",
  "status": "cancelled"
}
```

- **下载任务完成的line文件**: 客户端通过 GET 请求 `/api/v1/tasks/files/{task_id}.line` 下载任务文件，proxy server 收到请求后，将文件发送给客户端。

- **下载任务完成的grid文件**: 客户端通过 GET 请求 `/api/v1/tasks/files/{task_id}.grid` 下载任务文件，proxy server 收到请求后，将文件发送给客户端。

### 4.2 系统管理接口

| API路径 | 方法 | 描述 |
|---------|------|------|
| `/api/v1/status` | GET | 获取系统状态 |
| `/api/v1/nodes` | GET | 获取节点列表 |
| `/api/v1/nodes/{node_id}` | GET | 获取节点详情 |
| `/api/v1/nodes/{node_id}/drain` | POST | 将节点设置为排水模式 |
| `/api/v1/nodes/{node_id}/activate` | POST | 激活节点 |

- **获取系统状态**: 客户端通过 GET 请求 `/api/v1/status` 获取系统状态，proxy server 收到请求后，返回系统状态。
**响应示例**:
```json
{
  "status": "ok",
  "timestamp": "2024-07-01T00:00:00Z"
}
```

- **获取节点列表**: 客户端通过 GET 请求 `/api/v1/nodes` 获取节点列表，proxy server 收到请求后，返回节点列表。
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
        "cpu_usage": 25.5,
        "memory_usage": 45.2,
        "disk_usage": 50.0
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
        "cpu_usage": 25.5,
        "memory_usage": 45.2,
        "disk_usage": 50.0
      },
      "active_tasks": 2,
      "last_heartbeat": "2024-07-01T12:34:56Z",
      "ip_address": "192.168.1.101"
    }
  ],
  "total": 2
}
```
    
- **获取节点详情**: 客户端通过 GET 请求 `/api/v1/nodes/{node_id}` 获取节点详情，proxy server 收到请求后，返回节点详情。
**响应示例**:
```json
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
    "cpu_usage": 25.5,
    "memory_usage": 45.2,
    "disk_usage": 50.0
  },
  "active_tasks": 2,
  "last_heartbeat": "2024-07-01T12:34:56Z",
  "ip_address": "192.168.1.100"
}
```

- **将节点设置为排水模式**: 客户端通过 POST 请求 `/api/v1/nodes/{node_id}/drain` 将节点设置为排水模式，proxy server 收到请求后，将节点状态更新为DRAINING。
**响应示例**:
```json
{
  "node_id": "node-123",
  "status": "draining"
}
```

- **激活节点**: 客户端通过 POST 请求 `/api/v1/nodes/{node_id}/activate` 激活节点，proxy server 收到请求后，将节点状态更新为HEALTHY。
**响应示例**:
```json
{
  "node_id": "node-123",
  "status": "healthy"
}
```

## 5. 错误处理

### 5.1 节点错误处理

1. **节点离线**: 检测到节点离线时，重新分配其任务
2. **任务失败**: 节点任务失败时，根据配置决定重试或标记失败
3. **性能下降**: 节点性能下降时，减少其任务分配

### 5.2 任务错误处理

1. **任务超时**: 超过预设时间（默认3600秒）未完成，标记为超时
2. **任务失败**: 节点报告任务失败时，记录错误信息
3. **重试机制**: 支持任务自动重试（默认最多3次，间隔60秒）

### 5.3 错误代码

| 错误代码               | 描述                     | 处理建议                     |
|------------------------|--------------------------|------------------------------|
| `NODE_OFFLINE`         | 节点离线                 | 重新分配任务                 |
| `TASK_TIMEOUT`         | 任务执行超时             | 检查任务逻辑或增加超时时间   |
| `FILE_TRANSFER_ERROR`  | 文件传输错误             | 重新传输文件                 |
| `INVALID_TASK_PARAMS`  | 无效的任务参数           | 拒绝任务并返回错误           |
| `RESOURCE_UNAVAILABLE` | 所需资源不可用           | 等待资源释放或增加节点资源   |

## 6. 系统配置

### 6.1 配置文件路径
`~/config/proxy_config.yaml`

### 6.2 核心配置项

```yaml
# 代理服务器配置
rest_api:
  host: "0.0.0.0"  # 代理服务器监听主机
  port: 8080       # 代理服务器监听端口
  debug: true     # 调试模式
  log_level: "INFO"  # 日志级别
  metrics_port: 8090  # 指标监控端口

# WebSocket 配置
websocket:
  host: "0.0.0.0"  # WebSocket 监听主机
  port: 8764  # WebSocket 监听端口
  heartbeat_interval: 30  # 心跳间隔（秒）
  heartbeat_timeout: 60  # 心跳超时（秒）
  max_message_size: 104857600  # 最大消息大小（100MB）
  max_connections: 1000  # 最大连接数

# 节点管理配置
node:
  max_tasks: 5  # 节点最大并发任务数
  max_file_size: 104857600  # 最大文件大小（100MB）
  work_dir: "~/workspace"  # 工作目录
  health_check_interval: 60  # 健康检查间隔（秒）
  max_failures: 3  # 最大失败次数
  max_retries: 5  # 最大重试次数
  retry_delay: 5  # 重试延迟（秒）

# 负载均衡配置
load_balancing:
  strategy: "least_connections"  # 负载均衡策略
  weights: {}  # 节点权重配置
  affinity_timeout: 300  # 亲和性超时（秒）

# 文件传输配置
file_transfer:
  chunk_size: 1048576  # 分片大小（1MB）
  compression: true  # 是否压缩
  encryption: false  # 是否加密
  temp_dir: "~/tmp/ramgeo"  # 临时目录
  retention_days: 7  # 文件保留天数

# 数据库配置
database:
  host: "localhost"  # 数据库主机
  port: 3306  # 数据库端口
  name: "ramgeo"  # 数据库名称
  user: "root"  # 数据库用户
  password: "Pga39016"  # 数据库密码
  pool_size: 10  # 连接池大小
  max_overflow: 20  # 最大溢出连接数
  echo: false  # 是否输出SQL语句

# Redis 配置
redis:
  host: "localhost"  # Redis主机
  port: 6379  # Redis端口
  password: null  # Redis密码
  db: 0  # Redis数据库
  max_connections: 20  # 最大连接数
  decode_responses: true  # 是否解码响应

# 监控配置
monitoring:
  enabled: true  # 是否启用监控
  metrics_interval: 10  # 指标收集间隔（秒）
  alerting:
    enabled: true  # 是否启用告警
    webhook_url: null  # 告警Webhook URL
  logging:
    level: "INFO"  # 日志级别
    format: "json"  # 日志格式
    rotation:
      size: "100MB"  # 日志文件大小
      backup_count: 10  # 备份数量
```

## 7. 部署要求

### 7.1 硬件要求
- CPU: 至少 4 核
- 内存: 至少 16GB
- 磁盘: 至少 100GB 可用空间
- 网络: 千兆网卡

### 7.2 软件要求
- Python 3.12
- aiohttp
- websockets
- pyyaml
- redis (可选，用于任务队列)

### 7.3 部署架构

支持单机部署、集群部署和高可用部署，详见开发需求文档中的部署架构部分。

## 8. 监控与运维

### 8.1 监控指标

- **系统级指标**: CPU 使用率、内存使用率、磁盘使用率、网络 IO
- **服务级指标**: WebSocket 连接数、消息速率、API 请求速率、响应时间
- **业务级指标**: 任务提交数、任务完成数、任务失败率、节点可用率

### 8.2 日志管理

- 记录详细的系统日志、操作日志和错误日志
- 支持不同日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
- 日志格式包含时间戳、日志级别、模块、消息等信息

### 8.3 告警规则

| 告警级别 | 触发条件 | 通知方式 | 响应时间 |
|----------|----------|----------|----------|
| 紧急 | 所有节点离线 | 邮件 | 5分钟内 |
| 严重 | 超过50%节点离线 | 邮件 | 15分钟内 |
| 警告 | 单个节点连续故障 | 邮件 | 30分钟内 |
| 提示 | 磁盘使用率>80% | 邮件 | 1小时内 |
| 信息 | 任务失败率>5% | 邮件 | 2小时内 |

## 9. 安全要求
内部使用，不对外开放，无安全要求。

### 9.1 注册控制
- 对已注册的node id进行单一注册，不允许重复注册，防止多节点使用相同ID

## 10. 开发计划

### 10.1 开发阶段

1. **基础框架搭建**: WebSocket 服务、节点管理、任务管理基础框架
2. **核心功能实现**: 注册机制、心跳检测、任务分配、文件传输
3. **高级功能实现**: 负载均衡、错误处理、REST API
4. **测试与优化**: 单元测试、集成测试、性能优化
5. **文档完善**: 技术文档、API 文档

### 10.2 优先级

| 功能模块 | 优先级 |
|----------|--------|
| WebSocket 服务 | P0 |
| 节点管理 | P0 |
| 任务管理 | P0 |
| 文件传输 | P0 |
| REST API | P0 |
| 负载均衡 | P1 |
| 错误处理 | P1 |
| 监控与告警 | P1 |
| 安全功能 | P2 |
