import sqlite3
import aiosqlite
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from app.core.config import settings

INIT_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    script_path TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    env_vars TEXT DEFAULT '{}',
    timeout_seconds INTEGER DEFAULT 300,
    enabled INTEGER DEFAULT 1,
    next_run_time TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS task_executions (
    id TEXT PRIMARY KEY,
    task_id INTEGER NOT NULL,
    trigger_type TEXT NOT NULL, -- 'CRON' or 'MANUAL'
    status TEXT NOT NULL,       -- 'RUNNING', 'SUCCESS', 'FAILED', 'TIMEOUT'
    exit_code INTEGER,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    duration_seconds REAL,
    log_path TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS system_configs (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS global_env_vars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    description TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS custom_packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    version TEXT,
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_task_executions_task_id ON task_executions(task_id);
CREATE INDEX IF NOT EXISTS idx_task_executions_start_time ON task_executions(start_time DESC);
"""

async def init_db() -> None:
    """初始化 SQLite 数据库及数据表结构并开启 WAL 模式"""
    async with aiosqlite.connect(settings.DB_PATH) as db:
        await db.executescript(INIT_SQL)
        await db.commit()

@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """获取异步数据库连接，自动启用字典行格式映射"""
    db = await aiosqlite.connect(settings.DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()
