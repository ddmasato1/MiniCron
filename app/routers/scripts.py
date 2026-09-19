import os
import re
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from app.core.security import get_current_admin, validate_script_path
from app.core.config import settings
from app.core.scheduler import scheduler_manager
from app.models.db import get_db
from app.models.schemas import ApiResponse, CronPreviewRequest, CronPreviewResponse, ScriptSaveRequest

router = APIRouter(prefix="/api", tags=["Scripts & Tools"], dependencies=[Depends(get_current_admin)])

def sanitize_script_filename(raw_name: str) -> str:
    """严格净化文件名：防路径穿越与非法特殊字符"""
    name = Path(raw_name.strip()).name
    if not name:
        raise ValueError("文件名不能为空")
    
    if not name.endswith(".py"):
        name += ".py"

    base_name = name[:-3]
    if not re.match(r'^[a-zA-Z0-9_\-]+$', base_name):
        raise ValueError("文件名仅允许包含英文字母、数字、下划线(_)和中划线(-)，扩展名必须为 .py")

    return name

@router.get("/scripts", response_model=ApiResponse)
async def list_scripts():
    """扫描 scripts/ 目录下可供调度的合法 Python 脚本文件"""
    scripts_dir = settings.SCRIPTS_DIR.resolve()
    script_files = []

    for file_path in scripts_dir.rglob("*.py"):
        if file_path.is_file():
            rel_path = file_path.relative_to(scripts_dir).as_posix()
            stat = file_path.stat()
            script_files.append({
                "relative_path": rel_path,
                "file_size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })

    script_files.sort(key=lambda x: x["relative_path"])
    return ApiResponse(data=script_files)

@router.get("/scripts/content", response_model=ApiResponse)
async def get_script_content(path: str = Query(..., description="脚本相对路径")):
    """读取指定脚本文件的源代码内容（只读查看）"""
    try:
        abs_path = validate_script_path(path)
        content = abs_path.read_text(encoding="utf-8", errors="replace")
        return ApiResponse(data={"path": path, "content": content})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/scripts/save", response_model=ApiResponse)
async def save_script_content(payload: ScriptSaveRequest):
    """通过页面直接粘贴/编写代码并自动保存到 scripts 目录"""
    try:
        safe_filename = sanitize_script_filename(payload.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    target_path = (settings.SCRIPTS_DIR / safe_filename).resolve()
    
    # 路径安全沙箱校验
    if target_path.parent != settings.SCRIPTS_DIR.resolve():
        raise HTTPException(status_code=403, detail="非法路径越权")

    if target_path.exists() and not payload.overwrite:
        raise HTTPException(status_code=409, detail=f"文件 '{safe_filename}' 已存在，请勾选覆盖选项")

    # 写入文件
    try:
        target_path.write_text(payload.content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存文件失败: {e}")

    return ApiResponse(
        message=f"脚本 '{safe_filename}' 已成功保存至 scripts 目录",
        data={
            "relative_path": safe_filename,
            "file_size": target_path.stat().st_size
        }
    )

@router.post("/scripts/upload", response_model=ApiResponse)
async def upload_script_file(
    file: UploadFile = File(...),
    overwrite: bool = Form(False)
):
    """直接从本地选择 .py 文件上传并自动保存至 scripts 目录"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供有效文件名")

    try:
        safe_filename = sanitize_script_filename(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    target_path = (settings.SCRIPTS_DIR / safe_filename).resolve()

    if target_path.parent != settings.SCRIPTS_DIR.resolve():
        raise HTTPException(status_code=403, detail="非法路径越权")

    if target_path.exists() and not overwrite:
        raise HTTPException(status_code=409, detail=f"文件 '{safe_filename}' 已存在，若需替换请勾选覆盖选项")

    try:
        content = await file.read()
        target_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入文件失败: {e}")

    return ApiResponse(
        message=f"脚本 '{safe_filename}' 上传成功并已落盘",
        data={
            "relative_path": safe_filename,
            "file_size": target_path.stat().st_size
        }
    )

@router.delete("/scripts", response_model=ApiResponse)
async def delete_script_file(path: str = Query(..., description="要删除的脚本相对路径")):
    """删除 scripts 目录中的指定脚本（带任务依赖防误删检测）"""
    try:
        abs_path = validate_script_path(path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 检查是否有任务正在引用此脚本
    async with get_db() as db:
        cursor = await db.execute("SELECT id, name FROM tasks WHERE script_path = ?", (path,))
        used_tasks = await cursor.fetchall()
        if used_tasks:
            names = "、".join([f"【{t['name']}】" for t in used_tasks])
            raise HTTPException(
                status_code=400,
                detail=f"无法删除：脚本正在被任务 {names} 引用，请先修改或删除关联任务"
            )

    try:
        abs_path.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除文件失败: {e}")

    return ApiResponse(message=f"脚本 '{path}' 已成功删除")

@router.post("/tools/cron-preview", response_model=ApiResponse)
async def preview_cron_expression(payload: CronPreviewRequest):
    """验证并预演 Cron 表达式未来 5 次的预计触发时间"""
    try:
        next_runs = scheduler_manager.preview_cron(payload.cron_expression, count=5)
        return ApiResponse(data={
            "is_valid": True,
            "next_runs": next_runs,
            "error_message": None
        })
    except Exception as e:
        return ApiResponse(
            code=400,
            message="Cron 表达式格式校验未通过",
            data={
                "is_valid": False,
                "next_runs": [],
                "error_message": str(e)
            }
        )
