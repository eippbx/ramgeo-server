# REST API 接口文档

## 1. 概述

本文档详细描述了 RAMGEO 代理服务器的 REST API 接口规范。所有接口均采用 RESTful 架构设计，使用 JSON 格式进行数据交换。

### 1.1 基础信息

- **基础URL**: `http://<host>:<port>/api/v1`
- **协议**: HTTP/1.1
- **数据格式**: JSON
- **字符编码**: UTF-8

### 1.2 通用响应格式

所有接口返回的响应都遵循以下格式：

#### 成功响应

```json
{
  "data": {},
  "message": "Success",
  "timestamp": "2023-01-01T12:00:00Z"
}
```

#### 错误响应

```json
{
  "detail": "Error message",
  "timestamp": "2023-01-01T12:00:00Z"
}
```

### 1.3 HTTP 状态码

| 状态码 | 描述 | 使用场景 |
|--------|------|----------|
| 200 | OK | 请求成功 |
| 400 | Bad Request | 请求参数错误 |
| 404 | Not Found | 资源不存在 |
| 500 | Internal Server Error | 服务器内部错误 |

### 1.4 认证

当前版本不需要认证，所有接口均可直接访问。

## 2. 系统状态接口

### 2.1 获取系统状态

获取代理服务器的运行状态。

**Endpoint**: `GET /api/v1/status`

**请求参数**: 无

**响应示例**:

```json
{
  "status": "ok",
  "timestamp": "2023-01-01T12:00:00Z"
}
```

**字段说明**:

| 字段名 | 类型 | 描述 |
|--------|------|------|
| status | string | 系统状态，"ok" 表示正常 |
| timestamp | string | 响应时间戳（ISO 8601格式） |

## 3. 节点管理接口

### 3.1 获取所有节点列表

获取所有注册节点的信息列表。

**Endpoint**: `GET /api/v1/nodes`

**请求参数**: 无

**响应示例**:

```json
{
  "nodes": [
    {
      "node_id": "node-001",
      "node_name": "Node Server 001",
      "status": "HEALTHY",
      "capabilities": {
        "cpu_count": 4,
        "memory_gb": 16,
        "disk_gb": 100
      },
      "load": {
        "cpu_usage": 0.45,
        "memory_usage": 0.6,
        "disk_usage": 0.75
      },
      "active_tasks": 2,
      "last_heartbeat": "2023-01-01T12:00:00Z",
      "ip_address": "192.168.1.100"
    }
  ],
  "total": 1
}
```

**字段说明**:

| 字段名 | 类型 | 描述 |
|--------|------|------|
| nodes | array | 节点信息数组 |
| total | integer | 节点总数 |

**节点信息字段说明**:

| 字段名 | 类型 | 描述 |
|--------|------|------|
| node_id | string | 节点唯一标识符 |
| node_name | string | 节点名称 |
| status | string | 节点状态（UNKNOWN/CONNECTING/CONNECTED/HEALTHY/UNHEALTHY/BUSY/IDLE/OFFLINE/DRAINING） |
| capabilities | object | 节点能力信息 |
| capabilities.cpu_count | integer | CPU 核心数 |
| capabilities.memory_gb | number | 内存大小（GB） |
| capabilities.disk_gb | number | 磁盘大小（GB） |
| load | object | 节点负载信息 |
| load.cpu_usage | number | CPU 使用率（0-1） |
| load.memory_usage | number | 内存使用率（0-1） |
| load.disk_usage | number | 磁盘使用率（0-1） |
| active_tasks | integer | 当前活动任务数 |
| last_heartbeat | string | 最后心跳时间（ISO 8601格式） |
| ip_address | string | 节点 IP 地址 |

### 3.2 获取单个节点信息

获取指定节点的详细信息。

**Endpoint**: `GET /api/v1/nodes/{node_id}`

**路径参数**:

| 参数名 | 类型 | 必选 | 描述 |
|--------|------|------|------|
| node_id | string | 是 | 节点唯一标识符 |

**响应示例**:

```json
{
  "node_id": "node-001",
  "node_name": "Node Server 001",
  "status": "HEALTHY",
  "capabilities": {
    "cpu_count": 4,
    "memory_gb": 16,
    "disk_gb": 100
  },
  "load": {
    "cpu_usage": 0.45,
    "memory_usage": 0.6,
    "disk_usage": 0.75
  },
  "active_tasks": 2,
  "last_heartbeat": "2023-01-01T12:00:00Z",
  "ip_address": "192.168.1.100"
}
```

**字段说明**: 同 3.1 节点信息字段说明

**错误响应**:

```json
{
  "detail": "Node node-001 not found"
}
```

### 3.3 排空节点

将节点设置为排空状态，不再接收新任务，但继续执行现有任务。

**Endpoint**: `POST /api/v1/nodes/{node_id}/drain`

**路径参数**:

| 参数名 | 类型 | 必选 | 描述 |
|--------|------|------|------|
| node_id | string | 是 | 节点唯一标识符 |

**响应示例**:

```json
{
  "node_id": "node-001",
  "action": "drain",
  "status": "success"
}
```

**字段说明**:

| 字段名 | 类型 | 描述 |
|--------|------|------|
| node_id | string | 节点唯一标识符 |
| action | string | 执行的操作 |
| status | string | 操作状态 |

**错误响应**:

```json
{
  "detail": "Node node-001 not found"
}
```

### 3.4 激活节点

将节点从排空状态恢复为正常状态，开始接收新任务。

**Endpoint**: `POST /api/v1/nodes/{node_id}/activate`

**路径参数**:

| 参数名 | 类型 | 必选 | 描述 |
|--------|------|------|------|
| node_id | string | 是 | 节点唯一标识符 |

**响应示例**:

```json
{
  "node_id": "node-001",
  "action": "activate",
  "status": "success"
}
```

**字段说明**: 同 3.3

**错误响应**: 同 3.3

## 4. 任务管理接口

### 4.1 上传任务文件

上传任务文件并创建新任务。

**Endpoint**: `POST /api/v1/tasks/upload`

**请求参数**:

| 参数名 | 类型 | 必选 | 描述 |
|--------|------|------|------|
| task_type | string | 是 | 任务类型（查询参数） |
| file | file | 是 | 任务输入文件（表单数据） |
| chunk_index | integer | 否 | 分片索引（分片上传时使用） |
| total_chunks | integer | 否 | 总分片数（分片上传时使用） |
| file_hash | string | 否 | 文件 MD5 哈希值（可选） |

**请求示例**:

```bash
curl -X POST "http://localhost:8080/api/v1/tasks/upload?task_type=ramgeo" \
  -F "file=@input_file.in"
```

**响应示例**:

```json
{
  "task_id": "task-1767414007-8eaebe5e",
  "status": "pending"
}
```

**字段说明**:

| 字段名 | 类型 | 描述 |
|--------|------|------|
| task_id | string | 任务唯一标识符 |
| status | string | 任务状态 |

**分片上传响应示例**:

```json
{
  "task_id": "task-1767414007-8eaebe5e",
  "chunk_index": 0,
  "status": "chunk_received"
}
```

**错误响应**:

```json
{
  "detail": "Failed to upload task file: error message"
}
```

### 4.2 获取任务列表

获取任务列表，支持按状态和优先级过滤。

**Endpoint**: `GET /api/v1/tasks`

**查询参数**:

| 参数名 | 类型 | 必选 | 描述 |
|--------|------|------|------|
| status | string | 否 | 按任务状态过滤（PENDING/RUNNING/COMPLETED/FAILED/CANCELLED） |
| priority | string | 否 | 按任务优先级过滤（LOW/NORMAL/HIGH/URGENT） |
| limit | integer | 否 | 最大返回数量（默认100，范围1-1000） |
| offset | integer | 否 | 分页偏移量（默认0） |

**请求示例**:

```bash
curl -X GET "http://localhost:8080/api/v1/tasks?status=COMPLETED&limit=10&offset=0"
```

**响应示例**:

```json
{
  "tasks": [
    {
      "task_id": "task-1767414007-8eaebe5e",
      "status": "COMPLETED",
      "assigned_node_id": "node-001",
      "created_at": "2023-01-01T12:00:00Z",
      "started_at": "2023-01-01T12:00:01Z",
      "completed_at": "2023-01-01T12:00:30Z",
      "error": null,
      "retry_count": 0,
      "file_uploaded": true
    }
  ],
  "total": 1,
  "limit": 10,
  "offset": 0
}
```

**字段说明**:

| 字段名 | 类型 | 描述 |
|--------|------|------|
| tasks | array | 任务信息数组 |
| total | integer | 符合条件的任务总数 |
| limit | integer | 返回的最大任务数 |
| offset | integer | 分页偏移量 |

**任务信息字段说明**:

| 字段名 | 类型 | 描述 |
|--------|------|------|
| task_id | string | 任务唯一标识符 |
| status | string | 任务状态（PENDING/RUNNING/COMPLETED/FAILED/CANCELLED） |
| assigned_node_id | string | 分配的节点 ID（未分配时为 null） |
| created_at | string | 任务创建时间（ISO 8601格式） |
| started_at | string | 任务开始时间（ISO 8601格式，未开始时为 null） |
| completed_at | string | 任务完成时间（ISO 8601格式，未完成时为 null） |
| error | string | 错误信息（无错误时为 null） |
| retry_count | integer | 重试次数 |
| file_uploaded | boolean | 文件是否已上传 |

### 4.3 获取单个任务信息

获取指定任务的详细信息。

**Endpoint**: `GET /api/v1/tasks/{task_id}`

**路径参数**:

| 参数名 | 类型 | 必选 | 描述 |
|--------|------|------|------|
| task_id | string | 是 | 任务唯一标识符 |

**响应示例**:

```json
{
  "task_id": "task-1767414007-8eaebe5e",
  "status": "COMPLETED",
  "assigned_node_id": "node-001",
  "created_at": "2023-01-01T12:00:00Z",
  "started_at": "2023-01-01T12:00:01Z",
  "completed_at": "2023-01-01T12:00:30Z",
  "error": null,
  "retry_count": 0,
  "file_uploaded": true
}
```

**字段说明**: 同 4.2 任务信息字段说明

**错误响应**:

```json
{
  "detail": "Task task-1767414007-8eaebe5e not found"
}
```

### 4.4 取消任务

取消指定的任务。

**Endpoint**: `POST /api/v1/tasks/{task_id}/cancel`

**路径参数**:

| 参数名 | 类型 | 必选 | 描述 |
|--------|------|------|------|
| task_id | string | 是 | 任务唯一标识符 |

**响应示例**:

```json
{
  "task_id": "task-1767414007-8eaebe5e",
  "status": "cancelled"
}
```

**字段说明**:

| 字段名 | 类型 | 描述 |
|--------|------|------|
| task_id | string | 任务唯一标识符 |
| status | string | 任务状态 |

**错误响应**:

```json
{
  "detail": "Task task-1767414007-8eaebe5e not found"
}
```

```json
{
  "detail": "Cannot cancel task in COMPLETED status"
}
```

## 5. 文件下载接口

### 5.1 下载任务结果文件（.line）

下载指定任务的 .line 结果文件。

**Endpoint**: `GET /api/v1/tasks/files/{task_id}.line`

**路径参数**:

| 参数名 | 类型 | 必选 | 描述 |
|--------|------|------|------|
| task_id | string | 是 | 任务唯一标识符 |

**响应**: 文件内容（application/octet-stream）

**错误响应**:

```json
{
  "detail": "Task task-1767414007-8eaebe5e not found"
}
```

```json
{
  "detail": "Task task-1767414007-8eaebe5e is not completed (current status: RUNNING)"
}
```

```json
{
  "detail": "Line file not found for task task-1767414007-8eaebe5e"
}
```

### 5.2 下载任务结果文件（.grid）

下载指定任务的 .grid 结果文件。

**Endpoint**: `GET /api/v1/tasks/files/{task_id}.grid`

**路径参数**:

| 参数名 | 类型 | 必选 | 描述 |
|--------|------|------|------|
| task_id | string | 是 | 任务唯一标识符 |

**响应**: 文件内容（application/octet-stream）

**错误响应**: 同 5.1

## 6. 错误处理

### 6.1 通用错误响应

所有错误响应都遵循以下格式：

```json
{
  "detail": "Error message",
  "timestamp": "2023-01-01T12:00:00Z"
}
```

### 6.2 常见错误码

| HTTP 状态码 | 错误描述 | 处理建议 |
|-------------|----------|----------|
| 400 | Bad Request | 检查请求参数是否正确 |
| 404 | Not Found | 检查资源 ID 是否正确 |
| 500 | Internal Server Error | 联系系统管理员 |

### 6.3 业务错误

| 错误信息 | 描述 | 处理建议 |
|----------|------|----------|
| Node {node_id} not found | 节点不存在 | 检查节点 ID 是否正确 |
| Task {task_id} not found | 任务不存在 | 检查任务 ID 是否正确 |
| Cannot cancel task in {status} status | 无法取消已完成的任务 | 只能取消 PENDING 或 RUNNING 状态的任务 |
| Task {task_id} is not completed | 任务未完成 | 等待任务完成后再下载结果文件 |
| Line file not found for task {task_id} | 结果文件不存在 | 检查任务是否正确生成结果文件 |

## 7. 使用示例

### 7.1 完整任务处理流程

#### 步骤 1: 上传任务文件

```bash
curl -X POST "http://localhost:8080/api/v1/tasks/upload?task_type=ramgeo" \
  -F "file=@input_file.in"
```

响应:

```json
{
  "task_id": "task-1767414007-8eaebe5e",
  "status": "pending"
}
```

#### 步骤 2: 查询任务状态

```bash
curl -X GET "http://localhost:8080/api/v1/tasks/task-1767414007-8eaebe5e"
```

响应:

```json
{
  "task_id": "task-1767414007-8eaebe5e",
  "status": "RUNNING",
  "assigned_node_id": "node-001",
  "created_at": "2023-01-01T12:00:00Z",
  "started_at": "2023-01-01T12:00:01Z",
  "completed_at": null,
  "error": null,
  "retry_count": 0,
  "file_uploaded": true
}
```

#### 步骤 3: 下载结果文件

```bash
curl -X GET "http://localhost:8080/api/v1/tasks/files/task-1767414007-8eaebe5e.grid" \
  -o output.grid

curl -X GET "http://localhost:8080/api/v1/tasks/files/task-1767414007-8eaebe5e.line" \
  -o output.line
```

### 7.2 节点管理示例

#### 获取所有节点

```bash
curl -X GET "http://localhost:8080/api/v1/nodes"
```

#### 排空节点

```bash
curl -X POST "http://localhost:8080/api/v1/nodes/node-001/drain"
```

#### 激活节点

```bash
curl -X POST "http://localhost:8080/api/v1/nodes/node-001/activate"
```

### 7.3 任务查询示例

#### 获取所有已完成的任务

```bash
curl -X GET "http://localhost:8080/api/v1/tasks?status=COMPLETED"
```

#### 获取前 10 个任务

```bash
curl -X GET "http://localhost:8080/api/v1/tasks?limit=10&offset=0"
```

## 8. 附录

### 8.1 任务状态说明

| 状态值 | 描述 |
|--------|------|
| PENDING | 任务等待分配 |
| RUNNING | 任务正在执行 |
| COMPLETED | 任务执行完成 |
| FAILED | 任务执行失败 |
| CANCELLED | 任务已取消 |

### 8.2 节点状态说明

| 状态值 | 描述 |
|--------|------|
| UNKNOWN | 未知状态 |
| CONNECTING | 正在连接 |
| CONNECTED | 已连接但未认证 |
| HEALTHY | 健康状态 |
| UNHEALTHY | 不健康状态（心跳超时或任务失败） |
| BUSY | 节点忙碌 |
| IDLE | 节点空闲 |
| OFFLINE | 节点离线 |
| DRAINING | 节点正在排空（不再接收新任务） |

### 8.3 任务优先级说明

| 优先级值 | 描述 |
|----------|------|
| LOW | 低优先级 |
| NORMAL | 普通优先级 |
| HIGH | 高优先级 |
| URGENT | 紧急优先级 |

### 8.4 支持的任务类型

| 任务类型 | 描述 |
|----------|------|
| ramgeo | RAMGEO 计算任务 |

### 8.5 时间戳格式

所有时间戳均采用 ISO 8601 格式，例如：

```
2023-01-01T12:00:00Z
```

其中：
- `2023-01-01`: 日期（年-月-日）
- `T`: 日期和时间的分隔符
- `12:00:00`: 时间（时:分:秒）
- `Z`: UTC 时区标识符

### 8.6 文件大小限制

- 单个文件最大大小: 100MB
- 分片大小: 1MB
- 支持分片上传大文件

### 8.7 并发限制

- 最大并发连接数: 1000
- 最大并发任务数: 100

### 8.8 性能指标

- API 响应时间: < 100ms
- 文件传输速度: > 10MB/s
- 任务处理吞吐量: > 100 任务/分钟

## 9 Mallab 调用说明
- **原始调用**: 修改直接在Mallab中调用`ramgeo.exe`。
- **通过API调用**: 通过REST API上传任务文件，查询任务状态，下载结果文件。

### 9.1 定义函数
```matlab
% 主函数：通过API处理多个任务
function processTasksWithAPI(NA, nam)
    % API服务器地址
    api_base_url = 'http://192.168.84.251:8080/api/v1';
    
    % 遍历所有任务
    parfor n = 1:NA
        % 获取当前目录路径
        current_dir = fullfile('.', 'TLtemp', ['tltemp' num2str(n, '%03d')]);
        
        % 切换到当前任务目录
        cd(current_dir);
        
        try
            % 1. 上传任务文件到API服务器
            task_id = uploadTaskFile(api_base_url, current_dir);
            
            if ~isempty(task_id)
                % 2. 轮询任务状态，直到完成
                task_completed = pollTaskStatus(api_base_url, task_id);
                
                if task_completed
                    % 3. 下载结果文件
                    downloadResultFiles(api_base_url, task_id, current_dir);
                else
                    warning('任务 %s 未成功完成', task_id);
                end
            else
                warning('任务 %d 上传失败', n);
            end
        catch ME
            warning('处理任务 %d 时出错: %s', n, ME.message);
        end
        
        % 返回到原始目录
        cd(nam);
    end
end

% 函数1：上传任务文件
function task_id = uploadTaskFile(api_base_url, current_dir)
    task_id = '';
    
    % 检查ramgeo.in文件是否存在
    ramgeo_file = fullfile(current_dir, 'ramgeo.in');
    if ~exist(ramgeo_file, 'file')
        warning('文件不存在: %s', ramgeo_file);
        return;
    end
    
    % 构建上传URL
    upload_url = [api_base_url '/tasks/upload'];
    
    % 准备HTTP请求选项
    options = weboptions('RequestMethod', 'POST', ...
                         'MediaType', 'multipart/form-data', ...
                         'Timeout', 30, ...
                         'ContentType', 'json');
    
    try
        % 上传文件
        response = webwrite(upload_url, options, 'file', ramgeo_file);
        
        % 提取任务ID
        if isfield(response, 'task_id')
            task_id = response.task_id;
            fprintf('任务上传成功: %s\n', task_id);
        end
    catch ME
        warning('上传文件失败: %s', ME.message);
    end
end

% 函数2：轮询任务状态
function task_completed = pollTaskStatus(api_base_url, task_id)
    task_completed = false;
    max_attempts = 360000; % 最多轮询100小时（5秒间隔）
    poll_interval = 5; % 5秒
    
    % 构建状态查询URL
    status_url = [api_base_url '/tasks/' task_id];
    
    for attempt = 1:max_attempts
        try
            % 获取任务状态
            options = weboptions('Timeout', 10, 'ContentType', 'json');
            response = webread(status_url, options);
            
            % 检查状态字段
            if isfield(response, 'status')
                status = upper(response.status);
                
                fprintf('任务 %s 状态: %s (尝试 %d)\n', task_id, status, attempt);
                
                % 检查任务是否完成
                if strcmp(status, 'COMPLETED')
                    task_completed = true;
                    fprintf('任务 %s 已完成\n', task_id);
                    return;
                    
                elseif strcmp(status, 'FAILED')
                    error_msg = '未知错误';
                    if isfield(response, 'error') && ~isempty(response.error)
                        error_msg = response.error;
                    end
                    warning('任务 %s 失败: %s', task_id, error_msg);
                    return;
                    
                elseif strcmp(status, 'PENDING') || strcmp(status, 'SCHEDULED') || strcmp(status, 'RUNNING')
                    % 任务仍在运行，继续等待
                    pause(poll_interval);
                    
                else
                    warning('未知状态: %s', status);
                    pause(poll_interval);
                end
            else
                warning('响应中没有status字段');
                pause(poll_interval);
            end            
        catch ME
            warning('获取任务状态失败: %s', ME.message);
            pause(poll_interval);
        end
    end    
    warning('任务 %s 轮询超时', task_id);
end

% 函数3：下载结果文件
function downloadResultFiles(api_base_url, task_id, current_dir)
    % 要下载的文件类型
    file_types = {'.line', '.grid'};
    
    for i = 1:length(file_types)
        file_type = file_types{i};
        filename = [task_id file_type];
        
        % 构建下载URL
        download_url = [api_base_url '/tasks/files/' filename];
        
        % 本地保存路径
        save_path = fullfile(current_dir, filename);        
        try
            % 下载文件
            options = weboptions('Timeout', 60, 'ContentType', 'binary');
            data = webread(download_url, options);
            
            % 保存文件
            fid = fopen(save_path, 'wb');
            if fid ~= -1
                fwrite(fid, data);
                fclose(fid);
                fprintf('文件下载成功: %s\n', save_path);
            else
                warning('无法创建文件: %s', save_path);
            end            
        catch ME
            warning('下载文件 %s 失败: %s', filename, ME.message);
        end
    end
end

% 函数4：获取API服务器状态（可选，用于测试连接）
function server_status = checkServerStatus(api_base_url)
    server_status = false;
    try
        status_url = [api_base_url '/status'];
        options = weboptions('Timeout', 5, 'ContentType', 'json');
        response = webread(status_url, options);
        if isfield(response, 'status') && strcmp(response.status, 'ok')
            server_status = true;
            fprintf('API服务器状态正常\n');
        end
    catch ME
        warning('无法连接到API服务器: %s', ME.message);
    end
end

% 使用示例（替换原来的代码）：
% Parfor n=1:NA
%   cd(['.\TLtemp\tltemp' num2str(n,'%03d')]);
%   processTasksWithAPI(1, pwd); % 处理当前目录的任务
%   cd (nam)
% end
```
### 9.2 主要功能说明：

1. **`processTasksWithAPI`函数**：
   - 主函数，替换原来的`ramgeo.exe`调用
   - 使用parfor并行处理多个任务

2. **`uploadTaskFile`函数**：
   - 上传ramgeo.in文件到API服务器
   - 返回任务ID

3. **`pollTaskStatus`函数**：
   - 每5秒查询任务状态
   - 支持任务状态：PENDING, SCHEDULED, RUNNING, COMPLETED, FAILED
   - 最多轮询1小时（可根据需要调整）

4. **`downloadResultFiles`函数**：
   - 下载任务结果文件（.line和.grid）
   - 保存到当前目录

5. **`checkServerStatus`函数**（可选）：
   - 测试API服务器连接状态

### 9.3 使用方法：

将原来的代码替换为：
```matlab
% 在使用前可先检查服务器状态
api_base_url = 'http://192.168.84.251:8080/api/v1';
if checkServerStatus(api_base_url)
    parfor n=1:NA
        current_dir = ['.\TLtemp\tltemp' num2str(n,'%03d')];
        cd(current_dir);
        processTasksWithAPI(1, current_dir); % 处理当前任务
        cd(nam)
    end
else
    error('无法连接到API服务器，请检查网络连接和服务器状态');
end
```

## 注意事项：

1. 需要MATLAB的HTTP通信工具箱支持
2. 根据实际情况调整超时时间和轮询次数
3. 确保网络可以访问API服务器（192.168.84.251:8080）
4. 错误处理已包含，但可能需要根据实际情况调整

这个代码提供了完整的API集成功能，可以无缝替换原来的本地执行方式。

## 10. 更新日志

### v1.0.0 (2026-01-03)

- 初始版本发布
- 实现基础节点管理接口
- 实现任务管理接口
- 实现文件上传和下载接口
- 支持分片上传大文件
- 支持任务状态查询
- 支持节点排空和激活操作
