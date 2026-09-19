import os
import sys
import resource
import time
from datetime import datetime
from fastapi import APIRouter, Depends
from app.core.security import get_current_admin
from app.core.scheduler import scheduler_manager
from app.services.runner import task_runner
from app.models.schemas import ApiResponse

router = APIRouter(prefix="/api/system", tags=["System"], dependencies=[Depends(get_current_admin)])

START_TIME = time.time()

def get_process_memory_mb() -> float:
    """获取当前 Python 进程驻留物理内存 (RSS)"""
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # 在 macOS 上 ru_maxrss 单位为 bytes，在 Linux 上单位为 KB
        if sys.platform == "darwin":
            return round(usage.ru_maxrss / (1024 * 1024), 2)
        else:
            return round(usage.ru_maxrss / 1024, 2)
    except Exception:
        return 0.0

@router.get("/status", response_model=ApiResponse)
async def get_system_status():
    """获取 MiniCron 服务运行状态指标与资源消耗"""
    uptime_seconds = int(time.time() - START_TIME)
    
    return ApiResponse(
        data={
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "uptime_seconds": uptime_seconds,
            "memory_usage_mb": get_process_memory_mb(),
            "python_version": sys.version.split()[0],
            "scheduler_running": scheduler_manager.is_running,
            "active_running_tasks": len(task_runner._running_tasks)
        }
    )
