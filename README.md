# RAMGEO API 系统完整使用文档

## 系统概述

RAMGEO API 系统是一个基于 Flask 的 RESTful API 服务，用于管理 RAMGEO 计算任务的提交、执行和结果获取。系统支持多任务并发执行，具有任务队列管理和资源限制功能。

## 系统架构

```
RAMGEO API 系统架构
├── API 服务器 (Flask)
│   ├── 任务管理器 (TaskManager)
│   ├── 任务执行器 (run_ramgeo_task)
│   └── 文件处理器
├── 配置系统 (CONFIG)
├── 运行目录 (/home/ramgeo/run)
└── 可执行文件 (/usr/sbin/ramgeo)
```

## 环境要求

### 系统要求
- Python 3.7+
- Flask 2.3.3+
- RAMGEO 可执行程序

### 硬件要求
- 建议至少 4GB RAM
- 足够的磁盘空间存储计算结果
- 支持并发任务的 CPU

## 安装部署

### 1. 安装依赖
```bash
pip install Flask==2.3.3 Werkzeug==2.3.7
```

### 2. 创建目录结构
```bash
# 创建运行目录
sudo mkdir -p /home/ramgeo/run
sudo chmod 777 /home/ramgeo/run

# 创建临时上传目录
mkdir -p /tmp/ramgeo_uploads
```

### 3. 安装 RAMGEO 可执行文件
确保 `/usr/sbin/ramgeo` 存在并具有执行权限：
```bash
sudo chmod +x /usr/sbin/ramgeo
```

### 4. 配置文件说明
系统使用内置配置，主要参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| PATH | `/home/ramgeo/run` | 主运行目录 |
| FILE | `/usr/sbin/ramgeo` | 执行文件路径 |
| TOTAL | 20 | 最大并发任务数 |
| HOST | `0.0.0.0` | 服务器监听地址 |
| PORT | 3000 | 服务器监听端口 |
| UPLOAD_FOLDER | `/tmp/ramgeo_uploads` | 临时上传目录 |

## 启动服务

### 方式1：直接启动
```bash
python ramgeo_api.py
```

### 方式2：使用启动脚本（推荐）
```bash
# 创建启动脚本
cat > start_ramgeo.sh << 'EOF'
#!/bin/bash
cd /path/to/ramgeo/api
python ramgeo_api.py
EOF

chmod +x start_ramgeo.sh
./start_ramgeo.sh
```

### 方式3：使用 systemd 服务（生产环境）
```bash
# 创建服务文件
sudo cat > /etc/systemd/system/ramgeo-api.service << EOF
[Unit]
Description=RAMGEO API Service
After=network.target

[Service]
Type=simple
User=ramgeo
WorkingDirectory=/path/to/ramgeo/api
ExecStart=/usr/bin/python3 ramgeo_api.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
sudo systemctl daemon-reload
sudo systemctl start ramgeo-api
sudo systemctl enable ramgeo-api
```

## API 接口文档

### 基础信息
- 基础URL：`http://your-server-ip:3000`
- 所有响应均为 JSON 格式
- 所有时间戳使用 ISO 8601 格式

### API-1：上传文件并启动任务

**端点**：`POST /ramgeo/upload`

**功能**：上传 RAMGEO 输入文件并启动计算任务

**请求格式**：
- Content-Type: `multipart/form-data`
- 参数：`file` (文件字段)

**cURL 示例**：
```bash
curl -X POST \
  -F "file=@/path/to/your/ramgeo.in" \
  http://localhost:3000/ramgeo/upload
```

**Python 示例**：
```python
import requests

url = "http://localhost:3000/ramgeo/upload"
files = {'file': open('ramgeo.in', 'rb')}
response = requests.post(url, files=files)
print(response.json())
```

**成功响应**：
```json
{
    "status": "success",
    "message": "Task started successfully",
    "id": "20231201_143045",
    "task_dir": "/home/ramgeo/run/20231201_143045"
}
```

**失败响应**：
```json
{
    "status": "error",
    "message": "No available task slots",
    "id": 0
}
```

**HTTP 状态码**：
- 200：任务启动成功
- 400：请求错误（无文件、无可用槽位等）
- 500：服务器内部错误

### API-2：查询任务状态

**端点**：`GET /ramgeo/status`

**功能**：查询指定任务的状态和执行进度

**请求参数**：
| 参数 | 必选 | 说明 |
|------|------|------|
| id | 是 | 任务ID |

**cURL 示例**：
```bash
curl "http://localhost:3000/ramgeo/status?id=20231201_143045"
```

**成功响应（任务运行中）**：
```json
{
    "status": "running",
    "message": "Task is still running",
    "task_id": "20231201_143045",
    "start_time": "2023-12-01T14:30:45.123456",
    "elapsed_time": 15.78,
    "download_urls": []
}
```

**成功响应（任务已完成）**：
```json
{
    "status": "completed",
    "message": "Task completed successfully",
    "task_id": "20231201_143045",
    "start_time": "2023-12-01T14:30:45.123456",
    "completion_time": "2023-12-01T14:31:05.987654",
    "elapsed_time": 20.86,
    "files": ["tl.grid", "tl.line"],
    "download_urls": [
        "http://localhost:3000/ramgeo/20231201_143045/tl.grid",
        "http://localhost:3000/ramgeo/20231201_143045/tl.line"
    ]
}
```

**字段说明**：
| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 任务状态：running/completed/error |
| message | string | 状态描述信息 |
| task_id | string | 任务ID |
| start_time | string | 任务开始时间 |
| elapsed_time | number | 运行时间（秒） |
| completion_time | string | 完成时间（仅已完成任务） |
| files | array | 生成的文件列表 |
| download_urls | array | 文件下载URL列表 |

### API-3：查询空闲任务数

**端点**：`GET /ramgeo/idel`

**功能**：查询当前可用的任务槽位数量

**cURL 示例**：
```bash
curl http://localhost:3000/ramgeo/idel
```

**成功响应**：
```json
{
    "status": "success",
    "available_slots": 19,
    "total_slots": 20,
    "active_tasks": 1
}
```

**字段说明**：
| 字段 | 类型 | 说明 |
|------|------|------|
| available_slots | number | 可用任务槽位 |
| total_slots | number | 总任务槽位 |
| active_tasks | number | 正在运行的任务数 |

### 文件下载接口

**端点**：`GET /ramgeo/<task_id>/<filename>`

**功能**：下载任务生成的文件

**支持的文件**：
- `tl.grid`：网格结果文件
- `tl.line`：线结果文件
- `ramgeo.log`：任务执行日志

**示例**：
```bash
# 下载网格文件
curl -O http://localhost:3000/ramgeo/20231201_143045/tl.grid

# 下载线文件
curl -O http://localhost:3000/ramgeo/20231201_143045/tl.line

# 下载日志文件
curl -O http://localhost:3000/ramgeo/20231201_143045/ramgeo.log
```

## 任务管理

### 任务生命周期
```
创建任务 → 上传文件 → 分配槽位 → 执行计算 → 生成结果 → 释放槽位
```

### 任务目录结构
```
/home/ramgeo/run/
├── 20231201_143045/          # 任务目录（任务ID）
│   ├── ramgeo.in             # 输入文件
│   ├── tl.grid              # 网格结果文件
│   ├── tl.line              # 线结果文件
│   └── ramgeo.log           # 执行日志
├── 20231201_143120/
└── ...
```

### 任务命名规则
任务ID采用时间戳格式：`YYYYMMDD_HHMMSS`
- `YYYY`：4位年份
- `MM`：2位月份
- `DD`：2位日期
- `HH`：2位小时（24小时制）
- `MM`：2位分钟
- `SS`：2位秒

## 监控和调试

### 健康检查端点
```bash
curl http://localhost:3000/ramgeo/health
```

响应：
```json
{
    "status": "healthy",
    "timestamp": "2023-12-01T14:30:45.123456",
    "config": {
        "PATH": "/home/ramgeo/run",
        "FILE": "/usr/sbin/ramgeo",
        "TOTAL": 20,
        "HOST": "0.0.0.0",
        "PORT": 3000,
        "UPLOAD_FOLDER": "/tmp/ramgeo_uploads"
    }
}
```

### 任务列表端点（调试用）
```bash
curl http://localhost:3000/ramgeo/tasks
```

## 客户端使用示例

### Python 客户端
```python
import requests
import time

class RAMGEOClient:
    def __init__(self, base_url="http://localhost:3000"):
        self.base_url = base_url
    
    def submit_task(self, input_file):
        """提交任务"""
        with open(input_file, 'rb') as f:
            files = {'file': f}
            response = requests.post(f"{self.base_url}/ramgeo/upload", files=files)
        
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success':
                return data['id']
        
        return None
    
    def check_status(self, task_id):
        """检查任务状态"""
        response = requests.get(f"{self.base_url}/ramgeo/status", params={'id': task_id})
        if response.status_code == 200:
            return response.json()
        return None
    
    def wait_for_completion(self, task_id, interval=5):
        """等待任务完成"""
        while True:
            status = self.check_status(task_id)
            if status and status['status'] == 'completed':
                return status
            
            print(f"任务 {task_id} 运行中，已运行 {status['elapsed_time']} 秒")
            time.sleep(interval)
    
    def download_file(self, task_id, filename, save_path):
        """下载文件"""
        url = f"{self.base_url}/ramgeo/{task_id}/{filename}"
        response = requests.get(url)
        
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            return True
        
        return False

# 使用示例
client = RAMGEOClient()

# 提交任务
task_id = client.submit_task("my_input.in")
if task_id:
    print(f"任务提交成功，ID: {task_id}")
    
    # 等待完成
    result = client.wait_for_completion(task_id)
    print(f"任务完成，耗时: {result['elapsed_time']} 秒")
    
    # 下载结果
    for url in result['download_urls']:
        filename = url.split('/')[-1]
        client.download_file(task_id, filename, f"output_{filename}")
else:
    print("任务提交失败")
```

### Shell 脚本客户端
```bash
#!/bin/bash
# ramgeo_client.sh

BASE_URL="http://localhost:3000"

# 提交任务
submit_task() {
    local input_file=$1
    echo "提交任务: $input_file"
    
    response=$(curl -s -X POST -F "file=@$input_file" "$BASE_URL/ramgeo/upload")
    task_id=$(echo $response | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
    
    if [ -n "$task_id" ]; then
        echo "任务ID: $task_id"
        echo $task_id
    else
        echo "提交失败"
        return 1
    fi
}

# 检查状态
check_status() {
    local task_id=$1
    curl -s "$BASE_URL/ramgeo/status?id=$task_id"
}

# 下载文件
download_file() {
    local task_id=$1
    local filename=$2
    local output_dir=$3
    
    curl -s -o "$output_dir/$filename" "$BASE_URL/ramgeo/$task_id/$filename"
}

# 主流程
main() {
    input_file=$1
    output_dir=${2:-./output}
    
    mkdir -p $output_dir
    
    # 提交任务
    task_id=$(submit_task $input_file)
    if [ $? -ne 0 ]; then
        exit 1
    fi
    
    # 等待完成
    echo "等待任务完成..."
    while true; do
        status=$(check_status $task_id)
        state=$(echo $status | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        
        if [ "$state" = "completed" ]; then
            echo "任务完成"
            break
        elif [ "$state" = "running" ]; then
            elapsed=$(echo $status | grep -o '"elapsed_time":[0-9.]*' | cut -d':' -f2)
            echo "运行中，已耗时: ${elapsed}秒"
            sleep 5
        else
            echo "任务错误"
            exit 1
        fi
    done
    
    # 下载文件
    echo "下载结果文件..."
    download_file $task_id "tl.grid" $output_dir
    download_file $task_id "tl.line" $output_dir
    download_file $task_id "ramgeo.log" $output_dir
    
    echo "任务完成，结果保存在: $output_dir"
}

# 执行
main "$@"
```

## 故障排除

### 常见问题

1. **无法启动服务**
   - 检查 Python 版本：`python --version`
   - 检查依赖：`pip list | grep Flask`
   - 检查端口占用：`netstat -tlnp | grep 3000`

2. **上传文件失败**
   - 检查文件大小限制
   - 检查磁盘空间
   - 检查目录权限

3. **任务无法执行**
   - 检查 `/usr/sbin/ramgeo` 是否存在
   - 检查执行权限：`ls -l /usr/sbin/ramgeo`
   - 检查任务槽位是否已满

4. **无法下载文件**
   - 检查任务是否完成
   - 检查文件是否存在
   - 检查网络连接

### 日志查看
```bash
# 查看服务日志
journalctl -u ramgeo-api -f

# 查看任务日志
cat /home/ramgeo/run/20231201_143045/ramgeo.log
```

## 性能优化建议

### 1. 调整并发数
根据服务器资源调整 `TOTAL` 值：
- CPU密集型任务：建议设置为 CPU 核心数
- I/O密集型任务：可以适当增加并发数

### 2. 存储优化
- 定期清理旧任务目录
- 使用高性能存储（如 SSD）
- 考虑添加存储配额限制

### 3. 网络优化
- 使用 Nginx 作为反向代理
- 启用 gzip 压缩
- 配置合理的超时时间

## 安全建议

### 1. 访问控制
- 添加 API 认证
- 限制 IP 访问
- 使用 HTTPS

### 2. 输入验证
- 验证上传文件格式
- 限制文件大小
- 检查恶意内容

### 3. 资源限制
- 设置任务超时时间
- 限制单个任务资源使用
- 监控系统负载

## 扩展功能建议

### 1. 批量任务处理
添加批量上传接口，支持多个文件同时提交。

### 2. 任务优先级
实现任务优先级队列，重要任务优先执行。

### 3. 进度通知
支持 Webhook 回调，任务完成时通知客户端。

### 4. 结果可视化
添加结果预览和可视化接口。

## 联系和支持

如有问题，请：
1. 查看服务日志
2. 检查任务目录中的日志文件
3. 确保 RAMGEO 可执行文件正确安装
4. 确认系统资源充足

---

**版本信息**：RAMGEO API v1.0  
**更新日期**：2025年12月  
**文档维护**：eippbx for IACAS
