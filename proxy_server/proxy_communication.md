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
状态码 1003，消息 "Registration failed"
关闭码 1004，消息 "Node is registered"

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

## 3.7. 节点负载均衡策略

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

- 根据节点的能力报告中的资源规格（CPU、内存、磁盘）匹配小于等于配置文件参数：node.max_cpu、node.max_memory、node.max_disk 的节点
- 选择满足任务资源需求的最合适节点

## 3.8. 任务处理流程

### 3.8.1 任务状态

| 状态值 | 描述 |
|--------|------|
| `PENDING` | 任务等待分配 |
| `RUNNING` | 任务正在执行 |
| `COMPLETED` | 任务执行完成 |
| `FAILED` | 任务执行失败 |
| `CANCELLED` | 任务已取消 |

### 3.8.2 任务接收

1、 通过 REST API 接收客户端提交的任务文件
2、 保存任务文件到工作目录：将上传的文件保存在工作目录里: 配置文件 node.work_dir 中指定的目录
3、 加入任务队列等待分配：将任务加入任务队列，等待负载均衡策略选择节点分配任务
4、 任务分配：选择合适节点发送任务文件
5、 任务结果处理：接收任务结果或失败信息
7、 客户端获取结果文件：处理客户端获取结果文件的请求

#### 3.8.2.1 通过rest api接收任务文件

**Endpoint**: `POST /api/v1/tasks/upload?task_type=ramgeo`

**描述**: 接收客户端提交的任务文件 ，任务文件类型为为ramgeo

**请求示例**:
Body 类型为 multipart/form-data

**参数**:
- `file` (必需): 包含任务定义的ramgeo.in文件
  type:file

返回值：
- 成功：返回 HTTP 200 OK 响应，包含任务 ID
- 失败：返回 HTTP 400 Bad Request 响应，包含错误信息

**响应示例**：
- 成功：
  ```json
  {
    "task_id": "task-456",    // 任务唯一标识符，用于在通信中标识任务，以及文件传输时使用
    "status": "PENDING",
    "message": "Task uploaded successfully"
  }
  ```
- 失败：
  ```json
  {
    "task_id": "",
    "status": "FAILED",
    "message": "No Node available to run the task"
  }
  ```
#### 3.8.2.2 接收到的文件处理
系统自动生成任务ID，格式为：task-<时间戳>-<随机数>，时间戳为当前时间的毫秒数，随机数为4位随机数
接收到的文件命名为：<任务ID>.in，保存在工作目录里（配置文件 node.work_dir 中指定的目录）

#### 3.8.2.3 任务队列管理
- 维护任务队列：使用队列数据结构（如 Python 的 `queue.Queue`）管理待处理任务
- 任务状态更新：任务状态从 `PENDING` 变为 `RUNNING` 时，更新任务状态
- 任务完成或失败：任务完成或失败时，更新任务状态为 `COMPLETED` 或 `FAILED`，并从队列中移除

#### 3.8.2.4 任务分配
- 选择节点：根据负载均衡策略选择合适节点
- 通过websocket 发送任务文件给节点服务器
发送参照 3.9.1 任务文件传输消息格式

#### 3.8.2.5 任务状态更新
- 发送任务文件完成后，任务状态从 `PENDING` 变为 `RUNNING` 时，更新任务状态
- 发送任务文件失败，任务状态不做处理，在队列里等待重新分配节点

## 3.9. 代理服务器同节点服务器之间的文件传输机制

### 3.9.1 文件传输流程

1. **输入文件分发**: 将客户端上传的输入文件分发给执行节点
2. **大文件分片**: 支持大文件分片传输（1MB-10MB/片）
3. **分片确认**: 接收节点的 `chunk_received` 确认消息，确认分片已接收
4. **文件重组**: 节点接收所有分片后重组文件
5. **完整性校验**: 使用 MD5 哈希验证文件完整性

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
### 3.9.3 文件发送消息格式  

```json
{
  "type": "file_transfer",
  "timestamp": "2023-01-01T12:05:00Z",
  "transfer_id": "task-456",   // 任务唯一标识符，用于在通信中标识任务，以及文件传输时使用
  "chunk": "base64_encoded_chunk_data...",  // 文件块数据，使用 Base64 编码
  "index": 0,
  "total_chunks": 10,                 // 文件总块数
  "file_hash": "md5_hash_of_file",    // 文件的 MD5 哈希值，用于验证文件完整性
  "chunk_hash": "md5_hash_of_chunk"   // 文件块的 MD5 哈希值，用于验证文件块完整性
}
```

### 3.9.4 文件块接收确认消息格式

```json
{
  "type": "chunk_received",
  "timestamp": "2023-01-01T12:05:01Z",
  "transfer_id": "task-456",  // 任务唯一标识符，用于在通信中标识任务，以及文件传输时使用
  "index": 0,
  "status": "ok"
}
```

### 3.9.5 文件传输错误处理

1. **文件块丢失**: 发送方应重发丢失的文件块
2. **文件块校验失败**: 接收方应请求重发该文件块
3. **文件完整性校验失败**: 接收方应请求重传整个文件

### 3.9.6 文件接收的处理
- 所有节点发送过来的文件，全部存放到uploads目录下

### 3.9.7 文件的清理
- 根据参数文件中配置的file_transfer.cleanup_time文件保留的天数值，定时清理uploads目录下的文件

## 4. REST API 接口

### 详见 proxy_server_rest_api.md

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
参见 ./config/proxy_config.yaml 文件内容及注释

## 7. 部署要求

### 7.1 硬件要求
- CPU: 至少 4 核
- 内存: 至少 16GB
- 磁盘: 至少 100GB 可用空间
- 网络: 千兆网卡

### 7.2 部署架构

支持单机部署、集群部署和高可用部署，详见开发需求文档中的部署架构部分。

## 8. 日志

### 8.1 日志管理

- 记录详细的系统日志、操作日志和错误日志
- 支持不同日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
- 日志格式包含时间戳、日志级别、模块、消息等信息


## 9. 安全要求
内部使用，不对外开放，无安全要求。

### 9.1 注册控制
- 对已注册的node id进行单一注册，不允许重复注册，防止多节点使用相同ID
