import json
from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.responses import StreamingResponse
from app.core.security import get_current_admin
from app.services.package_service import package_manager
from app.models.schemas import (
    PackageInstallRequest, PackageUninstallRequest, ApiResponse
)

router = APIRouter(prefix="/api/packages", tags=["Packages"], dependencies=[Depends(get_current_admin)])

@router.get("", response_model=ApiResponse)
async def list_packages():
    """获取所有已安装的 Python 依赖模块列表"""
    try:
        packages = await package_manager.list_packages()
        return ApiResponse(data=packages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status", response_model=ApiResponse)
async def get_install_status():
    """查询当前是否有模块正在安装中"""
    return ApiResponse(
        data={
            "is_installing": package_manager.is_installing(),
            "target": package_manager.get_current_install_target()
        }
    )

@router.post("/install", response_model=ApiResponse)
async def install_package(payload: PackageInstallRequest):
    """在线安装 Python 依赖模块"""
    try:
        mirror = payload.mirror or "https://pypi.tuna.tsinghua.edu.cn/simple"
        result = await package_manager.install_package(payload.name, mirror)
        if not result["success"]:
            return ApiResponse(code=400, message=result["message"], data=result)
        return ApiResponse(message=result["message"], data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"安装过程发生异常: {e}")

@router.post("/uninstall", response_model=ApiResponse)
async def uninstall_package(payload: PackageUninstallRequest):
    """卸载自定义安装的 Python 模块"""
    try:
        result = await package_manager.uninstall_package(payload.name)
        return ApiResponse(message=result["message"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"卸载过程发生异常: {e}")

@router.get("/install/stream")
async def stream_install_log():
    """Server-Sent Events (SSE) 实时捕获 pip install 输出流"""
    async def event_generator():
        async for line in package_manager.subscribe_log():
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
