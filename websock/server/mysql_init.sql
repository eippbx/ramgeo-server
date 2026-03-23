-- RAMGEO分布式计算系统MySQL初始化脚本

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS ramgeo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 使用创建的数据库
USE ramgeo;

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

-- 创建用户并授权（如果不存在）
-- 注意：在生产环境中，建议使用更严格的权限设置
CREATE USER IF NOT EXISTS 'root'@'localhost' IDENTIFIED BY 'Pga39016';
GRANT ALL PRIVILEGES ON ramgeo.* TO 'root'@'localhost';
FLUSH PRIVILEGES;

-- 显示创建的表
SHOW TABLES;

-- 显示表结构
DESCRIBE nodes;
DESCRIBE tasks;