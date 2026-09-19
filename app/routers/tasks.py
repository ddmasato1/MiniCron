import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.responses import StreamingResponse
from app.core.security import get_current_admin, validate_script_path
from app.core.config import settings
from app.core.scheduler import scheduler_manager
from app.services.runner import task_runner
from app.models.db import get_db
from app.models.schemas import (
    TaskCreate, TaskUpdate, TaskToggle, ApiResponse
)

router = APIRouter(prefix="/api", tags=["Tasks"], dependencies=[Depends(get_current_admin)])

@router.get("/tasks", response_model=ApiResponse)
async def list_tasks():
    """获取所有任务及最新一次执行快照"""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM tasks ORDER BY id DESC")
        tasks = await cursor.fetchall()
        
        result = []
        for row in tasks:
            task = dict(row)
            task_id = task["id"]
            
            # 解析环境变量
            try:
                task["env_vars"] = json.loads(task.get("env_vars", "{}") or "{}")
            except Exception:
                task["env_vars"] = {}

            # 动态计算下次运行时间与运行状态
            task["next_run_time"] = scheduler_manager.get_next_run_time(task_id) if task["enabled"] else None
            task["is_running"] = task_runner.is_task_running(task_id)

            # 查询最近一次执行记录
            exec_cursor = await db.execute(
                """
                SELECT * FROM task_executions 
                WHERE task_id = ? 
                ORDER BY start_time DESC LIMIT 1
                """,
                (task_id,)
            )
            latest_exec = await exec_cursor.fetchone()
            task["latest_execution"] = dict(latest_exec) if latest_exec else None

            result.append(task)

    return ApiResponse(data=result)

@router.post("/tasks", response_model=ApiResponse)
async def create_task(payload: TaskCreate):
    """创建新任务并注册定时调度"""
    # 1. 校验脚本文件安全性与存在性
    try:
        validate_script_path(payload.script_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. 校验 Cron 表达式
    try:
        scheduler_manager.preview_cron(payload.cron_expression, 1)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    env_json = json.dumps(payload.env_vars, ensure_ascii=False)
    now_iso = datetime.now().isoformat()

    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO tasks 
            (name, script_path, cron_expression, env_vars, timeout_seconds, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name,
                payload.script_path,
                payload.cron_expression,
                env_json,
                payload.timeout_seconds,
                1 if payload.enabled else 0,
                now_iso,
                now_iso
            )
        )
        await db.commit()
        task_id = cursor.lastrowid

    # 3. 同步注册至 APScheduler
    if payload.enabled:
        scheduler_manager.add_or_update_job(task_id, payload.cron_expression, True)

    return ApiResponse(
        message="任务创建成功",
        data={
            "id": task_id,
            "next_run_time": scheduler_manager.get_next_run_time(task_id) if payload.enabled else None
        }
    )

@router.put("/tasks/{task_id}", response_model=ApiResponse)
async def update_task(task_id: int, payload: TaskUpdate):
    """修改任务属性并动态热重载调度"""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = await cursor.fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="目标任务不存在")

        task = dict(task)
        new_name = payload.name if payload.name is not None else task["name"]
        new_script = payload.script_path if payload.script_path is not None else task["script_path"]
        new_cron = payload.cron_expression if payload.cron_expression is not None else task["cron_expression"]
        new_timeout = payload.timeout_seconds if payload.timeout_seconds is not None else task["timeout_seconds"]
        new_enabled = payload.enabled if payload.enabled is not None else bool(task["enabled"])
        
        if payload.env_vars is not None:
            new_env = json.dumps(payload.env_vars, ensure_ascii=False)
        else:
            new_env = task["env_vars"]

        # 校验脚本
        try:
            validate_script_path(new_script)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 校验 Cron
        try:
            scheduler_manager.preview_cron(new_cron, 1)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        now_iso = datetime.now().isoformat()
        await db.execute(
            """
            UPDATE tasks 
            SET name = ?, script_path = ?, cron_expression = ?, env_vars = ?, 
                timeout_seconds = ?, enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                new_name, new_script, new_cron, new_env,
                new_timeout, 1 if new_enabled else 0, now_iso, task_id
            )
        )
        await db.commit()

    # 热重载调度器
    scheduler_manager.add_or_update_job(task_id, new_cron, new_enabled)

    return ApiResponse(
        message="任务更新成功",
        data={"id": task_id}
    )

@router.post("/tasks/{task_id}/toggle", response_model=ApiResponse)
async def toggle_task(task_id: int, payload: TaskToggle):
    """一键启用/禁用任务"""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task = await cursor.fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="目标任务不存在")

        task = dict(task)
        await db.execute(
            "UPDATE tasks SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if payload.enabled else 0, datetime.now().isoformat(), task_id)
        )
        await db.commit()

    scheduler_manager.add_or_update_job(task_id, task["cron_expression"], payload.enabled)

    return ApiResponse(
        message="状态已更新",
        data={"id": task_id, "enabled": payload.enabled}
    )

@router.delete("/tasks/{task_id}", response_model=ApiResponse)
async def delete_task(task_id: int):
    """删除任务及调度"""
    scheduler_manager.remove_job(task_id)
    async with get_db() as db:
        await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.commit()

    return ApiResponse(message="任务已删除", data={"id": task_id})

@router.post("/tasks/{task_id}/run", response_model=ApiResponse)
async def trigger_run_task(task_id: int):
    """手动立即触发运行一次任务 (Run Now)"""
    if task_runner.is_task_running(task_id):
        raise HTTPException(status_code=409, detail="该任务正在运行中，请勿重复触发")

    execution_id = await task_runner.run_task(task_id, trigger_type="MANUAL")
    if not execution_id:
        raise HTTPException(status_code=500, detail="触发任务失败，请检查任务配置")

    return ApiResponse(
        message="任务已启动",
        data={
            "task_id": task_id,
            "execution_id": execution_id
        }
    )

@router.get("/tasks/{task_id}/executions", response_model=ApiResponse)
async def list_task_executions(
    task_id: int,
    limit: int = Query(20, ge=1, le=100)
):
    """查询指定任务的历史执行记录"""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT * FROM task_executions 
            WHERE task_id = ? 
            ORDER BY start_time DESC LIMIT ?
            """,
            (task_id, limit)
        )
        rows = await cursor.fetchall()
        result = [dict(r) for r in rows]

    return ApiResponse(data=result)

@router.get("/executions/{execution_id}/log", response_model=ApiResponse)
async def get_execution_log(execution_id: str):
    """读取指定执行记录的完整日志文件"""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM task_executions WHERE id = ?", (execution_id,)
        )
        record = await cursor.fetchone()
        if not record:
            raise HTTPException(status_code=404, detail="执行记录不存在")

    log_path = settings.LOGS_DIR / record["log_path"]
    if not log_path.exists():
        return ApiResponse(data={"content": "（暂无日志或日志文件已被清理）"})

    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        content = f"读取日志出错: {e}"

    return ApiResponse(data={"content": content, "status": record["status"]})

@router.get("/executions/{execution_id}/stream")
async def stream_execution_log(execution_id: str):
    """Server-Sent Events (SSE) 实时日志流"""
    async def event_generator():
        async for line in task_runner.subscribe_log(execution_id):
            yield f"data: {json.dumps({'line': line})}\n\n"
        yield f"data: {json.dumps({'line': '', 'finished': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
