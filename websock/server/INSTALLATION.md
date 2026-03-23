# RAMGEO WebSocket Proxy Server 安装手册

## 1. 系统要求

### 1.1 硬件要求
- CPU: 至少 2 核
- 内存: 至少 4 GB
- 磁盘空间: 至少 10 GB（用于安装和数据存储）

### 1.2 软件要求
- **操作系统**: Linux (Ubuntu 20.04+)
- **Python**: 3.8 或更高版本
- **数据库**: MySQL 5.7 或更高版本
- **Redis**: 6.0 或更高版本

## 2. 环境准备

### 2.1 安装 Python

#### Linux (Ubuntu)
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
python3 --version
pip3 --version
```

### 2.2 安装 MySQL

#### Linux (Ubuntu)
```bash
sudo apt update
sudo apt install mysql-server
sudo systemctl start mysql
sudo systemctl enable mysql

# 设置 root 密码
sudo mysql -u root
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'Pga39016';
FLUSH PRIVILEGES;
exit
```

### 2.3 安装 Redis

#### Linux (Ubuntu)
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

## 3. 安装步骤

### 3.1 克隆项目代码

```bash
cd /path/to/your/workspace
git clone <repository-url>
cd websock
```

### 3.2 创建虚拟环境

#### Linux (Ubuntu)
```bash
# 创建conda环境
conda create -n ramgeo python=3.8 -y

# 激活conda环境
conda activate ramgeo
```

### 3.3 安装依赖

```bash
pip install -r requirements.txt
```

### 3.4 配置 MySQL 数据库

1. 连接到 MySQL 数据库：

#### Linux (Ubuntu)
```bash
mysql -u root -p
```

2. 在 MySQL 控制台执行：

```sql
-- 创建数据库
CREATE DATABASE IF NOT EXISTS ramgeo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 确保 root 用户有正确的权限（已在安装步骤中设置密码为 Pga39016）
-- 退出
quit;
```

## 4. 配置文件设置

### 4.1 创建 .env 文件

从示例文件复制并修改：

```bash
cp .env.example .env
```

编辑 `.env` 文件，根据你的环境配置以下内容：

```env
# Database Configuration
DATABASE_URL=mysql+pymysql://root:Pga39016@localhost:3306/ramgeo
REDIS_URL=redis://localhost:6379/0

# Server Configuration
SERVER_HOST=0.0.0.0
SERVER_PORT=8765
API_HOST=0.0.0.0
API_PORT=8080

# Security Configuration
SECRET_KEY=your-secret-key-change-this-in-production
JWT_EXPIRATION=3600
JWT_ALGORITHM=HS256

# Node Configuration
NODE_ID=node-1
NODE_NAME=Node 1
NODE_TYPE=cpu
MAX_WORKERS=4

# Proxy Configuration
PROXY_WEBSOCKET_URI=ws://localhost:8765
PROXY_API_KEY=your-proxy-api-key

# Metrics Configuration
METRICS_PORT=9090
```

### 4.2 修改 config.yaml 文件

根据需要修改 `config/config.yaml` 文件中的配置项。

## 5. 初始化数据库

需要手动初始化数据库表结构。创建一个初始化脚本：

### 5.1 创建初始化脚本

创建一个名为 `init_db.py` 的文件：

```python
#!/usr/bin/env python3
"""
数据库初始化脚本
"""

import sys
import asyncio
import logging
from shared.database import DatabaseManager
from shared.config import Config
from shared.logger import setup_logging

logger = setup_logging(__name__)

async def main():
    """主函数"""
    logger.info("开始初始化数据库...")
    
    # 加载配置
    config = Config()
    db_config = config.get('database', {})
    
    # 创建数据库管理器
    db = DatabaseManager(db_config)
    
    try:
        # 连接数据库
        await db.connect()
        
        # 创建表
        await db.create_tables()
        
        logger.info("数据库初始化完成！")
        
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise
    finally:
        # 关闭连接
        await db.disconnect()

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
```

### 5.2 运行初始化脚本

```bash
# 确保已激活conda环境
# conda activate ramgeo

python3 init_db.py
```

或者，您也可以直接在 MySQL 中执行以下 SQL 语句来创建表：

```sql
-- 创建节点表
CREATE TABLE IF NOT EXISTS nodes (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'online',
    capabilities JSON NOT NULL,
    resources JSON NOT NULL,
    metrics JSON NOT NULL,
    connection JSON NOT NULL,
    metadata JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 创建任务表
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 0,
    input_files JSON NOT NULL,
    output_files JSON NOT NULL,
    parameters JSON NOT NULL,
    node_id VARCHAR(64),
    timestamps JSON NOT NULL,
    metrics JSON NOT NULL,
    error_info JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_node_id ON tasks(node_id);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
```

## 6. 启动服务

### 6.1 启动代理服务器

#### 代理服务器配置说明

代理服务器是系统的核心组件，负责任务调度、节点管理和通信协调。

1. **检查代理服务器配置文件**
   - 代理服务器配置文件位于 `proxy_server/config.py`
   - 主要配置项包括：WebSocket服务端口（默认8765）、API端口（默认8080）、数据库连接等

2. **启动代理服务器**

```bash
# 确保已激活conda环境
# conda activate ramgeo

python3 -m proxy_server.main
```

3. **验证代理服务器启动状态**
   - 检查日志输出，确认服务器正常启动
   - 代理服务器将监听：
     - WebSocket通信：`ws://localhost:8765`
     - API接口：`http://localhost:8080`

### 6.2 启动计算节点

计算节点负责执行实际的计算任务，需要连接到代理服务器。

1. **配置计算节点**
   - 计算节点配置文件位于 `node_server/config.py`
   - 主要配置项包括：节点ID、节点名称、最大工作线程数、代理服务器地址等
   - 确保 `PROXY_WEBSOCKET_URI` 配置正确指向代理服务器地址

2. **在新的终端窗口中启动计算节点**

```bash
# 激活conda环境
# conda activate ramgeo

python3 -m node_server.main
```

3. **验证计算节点连接状态**
   - 检查计算节点日志输出，确认成功连接到代理服务器
   - 检查代理服务器日志，应该能看到节点连接信息

## 7. 部署架构说明

### 7.1 代理服务器部署

代理服务器建议部署在具有稳定网络连接的服务器上，具体要求：

- **硬件要求**：至少2核CPU，4GB内存，10GB磁盘空间
- **网络要求**：稳定的公网或局域网连接，开放WebSocket端口（默认8765）和API端口（默认8080）
- **软件要求**：Python 3.8+，MySQL 5.7+，Redis 6.0+
- **部署模式**：
  - 单节点部署：适用于开发和测试环境
  - 多节点部署：适用于生产环境，需要配置负载均衡

### 7.2 计算节点部署

计算节点可以部署在多台机器上，以实现分布式计算，具体要求：

- **硬件要求**：根据计算任务需求配置（CPU核心数、内存、GPU等）
- **网络要求**：能够连接到代理服务器的网络环境
- **软件要求**：Python 3.8+，所需的计算库（如NumPy、SciPy等）
- **部署模式**：
  - 单节点部署：适用于开发和测试环境
  - 多节点部署：适用于生产环境，可根据任务需求横向扩展

### 7.3 配置文件同步

在分布式部署时，确保以下配置在所有节点上保持一致：

- 代理服务器地址和端口
- 数据库连接信息
- Redis连接信息
- 加密密钥（如果有）

## 8. 验证安装

1. 检查代理服务器是否正常运行：
   - 访问 `http://localhost:8080` 应该可以看到 API 接口
   - 检查日志输出，确认没有错误

2. 检查计算节点是否正常连接：
   - 计算节点应该能够成功连接到代理服务器
   - 检查代理服务器日志，应该能看到节点连接信息

## 9. 常见问题排查

### 9.1 数据库连接错误
- 检查 `.env` 文件中的 `DATABASE_URL` 是否正确
- 确保 MySQL 服务正在运行
- 确保数据库用户有正确的权限

### 9.2 Redis 连接错误
- 检查 `.env` 文件中的 `REDIS_URL` 是否正确
- 确保 Redis 服务正在运行

### 9.3 端口被占用
- 检查 `SERVER_PORT`, `API_PORT` 是否被其他应用占用
- 修改 `.env` 文件中的端口配置

### 9.4 依赖安装错误
- 确保使用了正确的 Python 版本
- 尝试更新 pip：`pip install --upgrade pip`
- 检查网络连接是否正常

## 10. 停止服务

### 10.1 停止代理服务器
- 按 `Ctrl + C` 终止进程

### 10.2 停止计算节点
- 按 `Ctrl + C` 终止进程

## 11. 重启服务

按照第 6 节的步骤重新启动服务即可。

## 12. 卸载

1. 停止所有服务
2. 删除项目目录
3. 删除数据库（可选）：
   ```sql
   DROP DATABASE ramgeo;
   ```

## 13. 版本更新

1. 拉取最新代码：
   ```bash
git pull
   ```
2. 安装新的依赖（如果有）：
   ```bash
pip install -r requirements.txt
   ```
3. 重启服务

---

**注意：** 本安装手册适用于开发环境。在生产环境中，建议使用更安全的配置和部署方式，如使用 Docker、Nginx 反向代理等。