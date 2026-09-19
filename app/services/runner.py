import asyncio
import os
import sys
import uuid
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Set, AsyncGenerator
from app.core.config import settings
from app.core.security import validate_script_path
from app.models.db import get_db

class TaskRunner:
    def __init__(self):
        # 跟踪正在运行的任务 ID，实现并发重入保护
        self._running_tasks: Set[int] = set()
        # 实时日志广播频道：execution_id -> list of asyncio.Queue
        self._log_subscribers: Dict[str, list[asyncio.Queue]] = {}

    def is_task_running(self, task_id: int) -> bool:
        return task_id in self._running_tasks

    async def subscribe_log(self, execution_id: str) -> AsyncGenerator[str, None]:
        """订阅正在运行任务的实时输出日志"""
        q = asyncio.Queue()
        if execution_id not in self._log_subscribers:
            self._log_subscribers[execution_id] = []
        self._log_subscribers[execution_id].append(q)
        try:
            while True:
                line = await q.get()
                if line is None:  # 结束标记
                    break
                yield line
        finally:
            if execution_id in self._log_subscribers:
                if q in self._log_subscribers[execution_id]:
                    self._log_subscribers[execution_id].remove(q)
                if not self._log_subscribers[execution_id]:
                    del self._log_subscribers[execution_id]

    async def _broadcast_log(self, execution_id: str, line: str):
        if execution_id in self._log_subscribers:
            for q in self._log_subscribers[execution_id]:
                await q.put(line)

    async def _close_log_stream(self, execution_id: str):
        if execution_id in self._log_subscribers:
            for q in self._log_subscribers[execution_id]:
                await q.put(None)

    async def run_task(
        self,
        task_id: int,
        trigger_type: str = "MANUAL"
    ) -> Optional[str]:
        """执行单个任务的核心流控"""
        # 并发防重入校验
        if task_id in self._running_tasks:
            print(f"[TaskRunner] 任务 ID={task_id} 正在运行中，跳过本次触发")
            return None

        # 从数据库加载任务配置
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            task = await cursor.fetchone()
            if not task:
                print(f"[TaskRunner] 任务 ID={task_id} 不存在")
                return None

        execution_id = str(uuid.uuid4())
        self._running_tasks.add(task_id)

        # 异步启动后台执行协程，不阻塞当前调度循环
        asyncio.create_task(self._execute_subprocess(execution_id, dict(task), trigger_type))
        return execution_id

    async def _execute_subprocess(
        self,
        execution_id: str,
        task: dict,
        trigger_type: str
    ):
        task_id = task["id"]
        script_rel_path = task["script_path"]
        timeout_seconds = task.get("timeout_seconds", 300)
        
        try:
            env_vars = json.loads(task.get("env_vars", "{}") or "{}")
        except Exception:
            env_vars = {}

        log_filename = f"{task_id}_{execution_id}.log"
        log_abs_path = settings.LOGS_DIR / log_filename
        start_time = datetime.now()
        start_iso = start_time.isoformat()

        # 写入初始执行中记录
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO task_executions 
                (id, task_id, trigger_type, status, start_time, log_path)
                VALUES (?, ?, ?, 'RUNNING', ?, ?)
                """,
                (execution_id, task_id, trigger_type, start_iso, log_filename)
            )
            await db.commit()

        # 加载已启用的全局环境变量
        global_env_dict = {}
        try:
            async with get_db() as db:
                cursor = await db.execute("SELECT key, value FROM global_env_vars WHERE enabled = 1")
                rows = await cursor.fetchall()
                for r in rows:
                    global_env_dict[str(r["key"])] = str(r["value"])
        except Exception as e:
            print(f"[TaskRunner] 读取全局环境变量异常: {e}")

        status = "FAILED"
        exit_code = -1

        try:
            # 1. 严格安全沙箱路径校验
            script_abs_path = validate_script_path(script_rel_path)

            # 2. 准备安全环境变量 (强制开启 Python 无缓冲输出)
            # 合并顺序：基础系统环境 -> 全局环境变量 -> 任务独有环境变量（优先级递增）
            merged_env = os.environ.copy()
            merged_env["PYTHONUNBUFFERED"] = "1"
            for k, v in global_env_dict.items():
                merged_env[str(k)] = str(v)
            for k, v in env_vars.items():
                merged_env[str(k)] = str(v)

            # 3. 严格使用非 shell 的参数数组拉起子进程
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(script_abs_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=merged_env,
                cwd=str(settings.SCRIPTS_DIR)
            )

            # 4. 双向流式写入日志文件与广播
            injected_keys = list(set(list(global_env_dict.keys()) + list(env_vars.keys())))
            injected_info = f"=== 已注入环境变量: {', '.join(sorted(injected_keys))} ===\n" if injected_keys else ""

            with open(log_abs_path, "w", encoding="utf-8", buffering=1) as log_file:
                header = f"=== [MiniCron] 任务启动 ID={task_id} 执行流水号={execution_id} ===\n" \
                         f"=== 脚本: {script_rel_path} | 触发类型: {trigger_type} | 开始时间: {start_iso} ===\n" \
                         f"{injected_info}\n"
                log_file.write(header)
                await self._broadcast_log(execution_id, header)

                async def read_stream():
                    while True:
                        line_bytes = await process.stdout.readline()
                        if not line_bytes:
                            break
                        line = line_bytes.decode("utf-8", errors="replace")
                        log_file.write(line)
                        await self._broadcast_log(execution_id, line)

                try:
                    await asyncio.wait_for(read_stream(), timeout=timeout_seconds)
                    await process.wait()
                    exit_code = process.returncode
                    status = "SUCCESS" if exit_code == 0 else "FAILED"
                except asyncio.TimeoutError:
                    status = "TIMEOUT"
                    exit_code = -9
                    timeout_msg = f"\n\n!!! [MiniCron] 任务运行超时 (超过设定限制 {timeout_seconds} 秒)，已强制终止子进程 !!!\n"
                    log_file.write(timeout_msg)
                    await self._broadcast_log(execution_id, timeout_msg)
                    try:
                        process.kill()
                    except Exception:
                        pass

                footer = f"\n=== [MiniCron] 任务执行结束，状态: {status}，退出码: {exit_code} ===\n"
                log_file.write(footer)
                await self._broadcast_log(execution_id, footer)

        except Exception as e:
            status = "FAILED"
            exit_code = 127
            error_msg = f"\n\n!!! [MiniCron] 任务启动异常阻断: {str(e)} !!!\n"
            with open(log_abs_path, "a", encoding="utf-8") as log_file:
                log_file.write(error_msg)
            await self._broadcast_log(execution_id, error_msg)

        finally:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            self._running_tasks.discard(task_id)
            await self._close_log_stream(execution_id)

            # 更新最终执行状态
            async with get_db() as db:
                await db.execute(
                    """
                    UPDATE task_executions 
                    SET status = ?, exit_code = ?, end_time = ?, duration_seconds = ?
                    WHERE id = ?
                    """,
                    (status, exit_code, end_time.isoformat(), duration, execution_id)
                )
                await db.commit()

# 全局单例执行器
task_runner = TaskRunner()
