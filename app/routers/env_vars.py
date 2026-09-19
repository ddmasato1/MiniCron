import re
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status
from app.core.security import get_current_admin
from app.models.db import get_db
from app.models.schemas import (
    GlobalEnvVarCreate, GlobalEnvVarUpdate, GlobalEnvVarToggle, GlobalEnvVarOut, ApiResponse
)

router = APIRouter(prefix="/api/env-vars", tags=["Global Environment Variables"], dependencies=[Depends(get_current_admin)])

ENV_KEY_REGEX = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

def validate_env_key(key: str) -> str:
    cleaned = key.strip()
    if not cleaned:
        raise ValueError("环境变量名不能为空")
    if not ENV_KEY_REGEX.match(cleaned):
        raise ValueError(f"环境变量名 '{cleaned}' 不合法：仅允许以字母或下划线开头，由字母、数字及下划线组成")
    return cleaned

@router.get("", response_model=ApiResponse)
async def list_env_vars():
    """获取所有全局环境变量列表"""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM global_env_vars ORDER BY id DESC")
        rows = await cursor.fetchall()
        result = [dict(r) for r in rows]
    return ApiResponse(data=result)

@router.post("", response_model=ApiResponse)
async def create_env_var(payload: GlobalEnvVarCreate):
    """创建新的全局环境变量"""
    try:
        clean_key = validate_env_key(payload.key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with get_db() as db:
        # 检查是否重复
        cursor = await db.execute("SELECT id FROM global_env_vars WHERE key = ?", (clean_key,))
        existing = await cursor.fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"环境变量名 '{clean_key}' 已存在，请勿重复添加")

        cursor = await db.execute(
            """
            INSERT INTO global_env_vars (key, value, description, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (clean_key, payload.value, payload.description or "", 1 if payload.enabled else 0, now_iso, now_iso)
        )
        await db.commit()
        var_id = cursor.lastrowid

    return ApiResponse(
        message=f"环境变量 '{clean_key}' 创建成功",
        data={"id": var_id, "key": clean_key}
    )

@router.put("/{var_id}", response_model=ApiResponse)
async def update_env_var(var_id: int, payload: GlobalEnvVarUpdate):
    """修改全局环境变量"""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM global_env_vars WHERE id = ?", (var_id,))
        record = await cursor.fetchone()
        if not record:
            raise HTTPException(status_code=404, detail="目标环境变量不存在")

        record = dict(record)
        new_key = record["key"]
        if payload.key is not None:
            try:
                new_key = validate_env_key(payload.key)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            if new_key != record["key"]:
                check_cursor = await db.execute("SELECT id FROM global_env_vars WHERE key = ? AND id != ?", (new_key, var_id))
                if await check_cursor.fetchone():
                    raise HTTPException(status_code=409, detail=f"环境变量名 '{new_key}' 已存在")

        new_value = payload.value if payload.value is not None else record["value"]
        new_desc = payload.description if payload.description is not None else record["description"]
        new_enabled = payload.enabled if payload.enabled is not None else bool(record["enabled"])
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        await db.execute(
            """
            UPDATE global_env_vars 
            SET key = ?, value = ?, description = ?, enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_key, new_value, new_desc, 1 if new_enabled else 0, now_iso, var_id)
        )
        await db.commit()

    return ApiResponse(message="环境变量更新成功", data={"id": var_id})

@router.post("/{var_id}/toggle", response_model=ApiResponse)
async def toggle_env_var(var_id: int, payload: GlobalEnvVarToggle):
    """快速启用/禁用某项环境变量"""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM global_env_vars WHERE id = ?", (var_id,))
        record = await cursor.fetchone()
        if not record:
            raise HTTPException(status_code=404, detail="目标环境变量不存在")

        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            "UPDATE global_env_vars SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if payload.enabled else 0, now_iso, var_id)
        )
        await db.commit()

    return ApiResponse(
        message="状态切换成功",
        data={"id": var_id, "enabled": payload.enabled}
    )

@router.delete("/{var_id}", response_model=ApiResponse)
async def delete_env_var(var_id: int):
    """删除指定全局环境变量"""
    async with get_db() as db:
        cursor = await db.execute("SELECT key FROM global_env_vars WHERE id = ?", (var_id,))
        record = await cursor.fetchone()
        if not record:
            raise HTTPException(status_code=404, detail="目标环境变量不存在")

        key_name = record["key"]
        await db.execute("DELETE FROM global_env_vars WHERE id = ?", (var_id,))
        await db.commit()

    return ApiResponse(message=f"环境变量 '{key_name}' 已成功删除")
