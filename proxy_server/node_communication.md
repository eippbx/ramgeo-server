# Proxy Server 与 Node Server 通信协议文档

## 1. 概述

本文档详细描述了 `proxy_server`（代理服务器）与 `node_server`（节点服务器）之间的通信协议，用于指导 `node_server` 的开发。通信基于 WebSocket 协议，实现了节点注册、任务处理、状态监控、文件传输等功能。

### 1.1 开发语言
- **Node Server**: 基于 Python 3.12 实现
- **运行环境**: Ubuntu 22.04 或以上版本
- **运行方式**: 使用conda activate ramgeo 激活ramgeo环境后，运行python -m proxy_server.main 启动服务

### 1.2 通信协议
- **协议版本**: 1.0
- **消息格式**: JSON 格式
- **编码**: UTF-8

### 1.3 目录结构定义  
./config/
- **node_config.yaml**: 节点服务器配置文件
./logs/
- **node.log**: 节点服务器日志文件
./bin/
- **ramgeo**: 节点处理任务的执行文件
./work/
- **任务工作目录**: 节点处理任务的工作目录，用于存储任务文件和结果
./src/
- **节点处理任务代码目录**: 节点处理任务的源代码目录，用于存储任务处理的 Python 脚本

### 参数文件定义
文件位置及名称： ./config/node_config.yaml

```yaml
# 节点服务器配置
node:
  # 节点唯一标识符
  node_id: "node-001"
  # 节点名称（可选）
  node_name: "Node Server 001"
  
# 代理服务器配置
proxy:
  # 代理服务器的 WebSocket 地址
  proxy_server_url: "ws://192.168.84.251:8765/node-ws"

# 运行配置
runtime:
  # 节点状态报告的时间间隔，单位秒
  report_time: 10
  # 节点工作目录，用于存储任务文件和结果
  work_dir: "./work"
  # 节点日志目录，用于存储运行日志
  log_dir: "./logs"
  # 处理任务的执行文件
  run_bin: "./bin/ramgeo"
  
# WebSocket 配置
websocket:
  # 连接超时时间，单位秒
  connect_timeout: 10
  # 重连间隔时间，单位秒
  reconnect_interval: 5
  # 最大重连次数
  max_reconnect_attempts: 10
  
# 日志配置
logging:
  # 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
  level: "DEBUG"
  # 日志文件大小限制，单位MB
  max_file_size: 10
  # 日志文件保留数量
  backup_count: 10
  
```

## 2. 系统架构

### 2.1 核心组件
- **Node Server**:
  - WebSocket 客户端: 与代理服务器的 `proxy_server_url` 端点建立连接
  - 任务执行器: 执行分配的计算任务
  - 资源监控器: 监控节点资源使用情况（CPU、内存、磁盘等）
  - 心跳响应器: 确保及时响应代理服务器的心跳检测

### 2.2 业务流程

```
Node Server → Proxy Server
1. 建立WebSocket连接 → (/node-ws) 端点
2. 发送注册消息 → 包含node_id和初始能力报告
3. 接收注册响应 → 确认连接成功
4. 定期发送状态报告 → 每10秒发送CPU、内存、磁盘资源占用情况百分比
5. 响应心跳消息 → 收到心跳后立即回复
6. 接收任务分配 → 接收任务文件完成后在work工作目录下创建{任务文件名}的目录，并将任务文件重新命名为ramgeo.in，再在当前目录下运行 {run_bin}执行计算任务，计算任务完成后将生成的两个文件（tl.line 和 tl.grid）然后将tl.line重命名为{任务文件名}.line 和将tl.grid重命名为{任务文件名}.grid，最后将这两个文件发送给Proxy Server。
7. 完成任务 → 任务执行完成后先发送任务生成的两个文件（{任务文件名}.line 和 {任务文件名}.grid），再发送任务完成状态消息。
```

## 3. WebSocket 连接

### 3.1 连接端点

- **节点连接端点**: {proxy.proxy_server_url}
- **协议**: WebSocket (ws://)
- **支持的客户端版本**: WebSocket RFC 6455

### 3.2 连接建立流程

1. Node Server 发起 WebSocket 连接请求到 `/node-ws` 端点
2. Proxy Server 接受连接并立即开始等待注册消息
3. Node Server 在连接建立后必须在5秒内发送 `register` 类型的认证消息
4. Proxy Server 注册节点身份（`node_id`）
5. 注册成功后，Proxy Server 发送 `register_response` 消息确认
6. 连接建立成功，开始正常通信
7. Proxy Server 自动启动心跳检测机制

### 3.3 proxy_server连接返回代码

| 关闭码 | 描述 | 原因 | 处理方式 |
|--------|------|------|----------|
| 1003 | Registration failed | 无效的 node_id | Node Server 应检查注册信息并重试连接 |
| 1008 | Invalid message type | 无效的消息类型或格式 | Node Server 应检查消息格式并修复 |
| 1000 | Normal closure | 正常关闭连接 | 无需特殊处理 |
| 1011 | Internal server error | 服务器内部错误 | Node Server 应等待一段时间后重试连接 |
| 1006 | Abnormal closure | 连接意外关闭 | Node Server 应立即尝试重连 |

### 3.4 连接管理

- **自动重连**: Node Server 应实现自动重连机制，重连间隔建议使用指数退避策略（初始1秒，每次翻倍，最大60秒）
- **连接状态跟踪**: Node Server 应维护连接状态（CONNECTING, CONNECTED, DISCONNECTED）
- **资源清理**: 连接关闭时，Node Server 应清理相关资源和任务

## 4. 消息格式规范

所有消息都采用 JSON 格式，必须包含以下字段：

| 字段名     | 类型   | 描述                     | 必选 | 格式要求 |
|------------|--------|--------------------------|------|----------|
| `type`     | string | 消息类型                 | 是   | 必须是支持的类型之一 |
| `timestamp`| string | 消息发送时间戳（ISO格式）| 是   | 必须是有效的ISO 8601日期时间字符串 |

### 4.1 消息验证规则

1. **JSON格式验证**: 所有消息必须是有效的JSON格式
2. **必填字段检查**: 必须包含 `type` 和 `timestamp` 字段
3. **类型验证**: 字段类型必须与规范一致
4. **消息类型检查**: 消息类型必须是支持的类型之一
5. **时间戳验证**: 时间戳必须是有效的ISO 8601格式
6. **内容验证**: 特定消息类型的业务字段必须符合规范

### 4.2 消息类型列表

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


## 5. 注册机制

### 5.1 注册流程

1. Node Server 连接到 `/node-ws` 端点
2. Proxy Server 等待认证注册消息
3. Node Server 发送 `register` 消息，包含 `node_id`和能力信息
4. Proxy Server 验证 `node_id`的合法性和唯一性
5. 注册成功：Proxy Server 发送 `register_response` 消息，状态为 `registered`
6. 注册失败：关闭连接，状态码 1003，消息 "Registration failed"

### 5.2 注册消息格式

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

### 5.3 认证响应消息格式

```json
{
  "type": "register_response",
  "timestamp": "2023-01-01T12:00:01Z",
  "status": "registered",
  "node_id": "node_id", 
  "message": "Registration successful"
}
```

## 6. 心跳检测机制

### 6.1 心跳流程

1. Proxy Server向 Node Server 发送 `heartbeat` 消息
2. Node Server 收到心跳消息后，立即回复 `heartbeat_response` 消息

### 6.2 心跳消息格式

```json
{
  "type": "heartbeat",
  "timestamp": "2023-01-01T12:00:30Z"
}
```

### 6.3 心跳响应消息格式

```json
{
  "type": "heartbeat_response",
  "timestamp": "2023-01-01T12:00:31Z"
}
```

## 7. 节点状态管理

### 7.1 状态报告流程

1. Node Server 定期（在配置文件里配置 `report_time`）发送 `status_report` 消息
2. 自动获取系统信息,报告内容包括 CPU 负载、内存使用、磁盘使用、网络状态等

### 7.2 状态报告消息格式

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

## 8. 任务执行与取消

### 8.1 任务执行流程

1. 接收 Proxy Server 发送的任务文件到该节点，在参数文件定义的runtime.work_dir目录下以该发送的文件名创建任务ID目录，将发送的任务文件以ramgeo.in为名称保存到该目录下
2. 在任务ID目录下运行ramgeo
3. 接收 Proxy Server 发送的 `task_cancel` 取消指定任务
4. 任务完成后，运行的ramgeo会输出两个文件（tl.grid、tl.line），将tl.grid更名为{目录名}.grid，将tl.line更名为{目录名}.line，将这两个文件发送到Proxy Server
5. 发送 `task_complete` 消息，包含任务ID、输出文件路径、执行时间等信息

### 8.2 任务状态

| 状态值 | 描述 |
|--------|------|
| `RUNNING` | 任务正在执行 |
| `COMPLETED` | 任务执行完成 |
| `FAILED` | 任务执行失败 |
| `CANCELLED` | 任务已取消 |

### 8.3 任务进度消息格式

- 接收任务进度消息
```json
{
  "type": "task_progress",
  "timestamp": "2023-01-01T12:03:30Z",
  "task_id": "task-456",
  "run_time": 128,  // 任务已执行时间（秒）
  "message": "Processing task 456..."
}
```

### 8.3 任务完成消息格式

- 发送任务完成消息
```json
{
  "type": "task_complete",
  "timestamp": "2023-01-01T12:30:00Z",
  "task_id": "task-456",
  "result": {
    "execution_time": 1680,   // 任务执行时间（秒）
    "status": "success"
  }
}
```

### 8.6 任务失败消息格式 

- 发送任务失败消息
```json
{
  "type": "task_failed",
  "timestamp": "2023-01-01T12:15:00Z",
  "task_id": "task-456",
  "error": {
    "message": "ramgeo execution failed: Invalid input file format"  // 内容为ramgeo执行返回的错误信息
  },
  "execution_time": 900    // 任务执行时间（秒）
}
```

## 9. 文件传输机制

### 9.1 文件传输流程

1. 发送方将大文件分割成小块（建议 1MB - 10MB ）
2. 发送方使用 `file_transfer` 消息逐个发送文件块
3. 接收方收到文件块后发送 `chunk_received` 消息确认
4. 所有文件块发送完成后，接收方重组文件

### 9.2 文件接收消息格式  

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

### 9.3 文件块接收确认消息格式

```json
{
  "type": "chunk_received",
  "timestamp": "2023-01-01T12:05:01Z",
  "transfer_id": "task-456",  // 任务唯一标识符，用于在通信中标识任务，以及文件传输时使用
  "index": 0,
  "status": "ok"
}
```
### 9.4 文件传输错误处理

1. **文件块丢失**: 发送方应重发丢失的文件块
2. **文件块校验失败**: 接收方应请求重发该文件块
3. **文件完整性校验失败**: 接收方应请求重传整个文件

### 9.5 文件传输完成后的处理

1. 收到的文件在工作目录中（参数文件定义的:runtime.work_dir）新建一个任务ID("transfer_id"值)目录，并命名为ramgeo.in,该目录为该任务的工作目录，用于存储该任务的所有文件
2. 在任务ID目录下运行（参数文件定义的:runtime.run_bin），运行ramgeo
3. ramgeo运行结束后会输出文件两个文件（tl.grid、tl.line）分别更名为"{transfer_id}.grid"、"{transfer_id}.line"并保存到任务ID目录

### 9.6 任务完成后的处理

1. 任务完成后Node Server会将任务ID目录下的"{transfer_id}.grid"、"{transfer_id}.line"文件发送给Proxy Server
2. Node Server 发送文件完成后发送 `task_complete` 消息
3. Proxy Server 收到 `task_complete` 消息后，更新任务状态为 `COMPLETED`
4. Proxy Server 会将任务执行时间和输出文件列表发送给客户端

## 11. 错误处理与恢复

### 11.1 连接错误处理

1. **连接断开**: Node Server 应自动重连，重连间隔建议指数退避
2. **认证失败**: Node Server 应检查认证信息并重试
3. **心跳超时**: Node Server 应主动检查连接状态并重新建立连接

### 11.2 任务错误处理

1. **任务执行失败**: Node Server 发送 `task_failed` 消息，包含详细错误信息


## 13. 日志记录

### 13.1 日志记录流程

1. Node Server 应记录详细的日志
2. 日志应包含时间戳、日志级别、模块、消息等信息
3. 日志应存储在配置文件中指定的路径（参数文件定义的:runtime.log_dir）
4. 日志文件名格式为"{node_id}.log"，其中"{node_id}"为节点ID
5. 日志文件大小为参数文件定义的:logging.max_log_size（默认10MB），超过时应自动滚动到新文件
6. 日志文件滚动时，保留最近的N个文件（参数文件定义的:logging.backup_count，默认10个），超过时旧文件将被删除
7. 日志级别为参数文件定义的:logging.log_level（默认INFO），可选值为DEBUG、INFO、WARNING、ERROR、CRITICAL

### 13.2 日志记录级别

| 日志级别 | 描述                     |
|----------|--------------------------|
| `DEBUG`  | 详细的调试信息，用于开发和故障排除 |
| `INFO`   | 普通的运行信息，用于监控和正常操作 |
| `WARNING`| 警告信息，指示潜在问题或异常情况 |
| `ERROR`  | 错误信息，指示任务失败或异常情况 |
| `CRITICAL`| 严重错误信息，指示系统崩溃或不可恢复问题 |


### 13.3 日志记录格式

```text
  "timestamp": "2023-01-01T12:05:00Z",  "level": "INFO",  "module": "NodeServer",  "message": "Node erver started on port 8080"
```

## 14. 优雅的关闭

### 14.1 关闭方式
禁止直接关闭Node Server，而应通过发送 `shutdown` 消息来关闭

### 14.2 关闭流程

1. Node Server 收到 `shutdown` 消息后，应先停止接受新任务
2. 已分配任务完成后，Node Server 应关闭所有连接并退出
