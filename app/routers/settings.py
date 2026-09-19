from fastapi import APIRouter, HTTPException, Depends
from app.core.security import get_current_admin
from app.services.notifier import notifier_service
from app.models.schemas import ApiResponse, NotificationSettings, NotificationTestRequest

router = APIRouter(prefix="/api/settings", tags=["Settings"], dependencies=[Depends(get_current_admin)])

@router.get("/notifications", response_model=ApiResponse)
async def get_notification_settings():
    """获取系统当前通知与网络代理配置"""
    cfg = await notifier_service.get_settings()
    return ApiResponse(data=cfg)

@router.post("/notifications", response_model=ApiResponse)
async def save_notification_settings(payload: NotificationSettings):
    """保存通知与网络代理配置"""
    current_cfg = await notifier_service.get_settings()
    new_data = payload.model_dump()

    # 若未修改 token (例如留空)，则保留原 token
    if not new_data.get("telegram_bot_token") and current_cfg.get("telegram_bot_token"):
        new_data["telegram_bot_token"] = current_cfg["telegram_bot_token"]

    await notifier_service.save_settings(new_data)
    return ApiResponse(message="通知与网络代理配置已成功保存", data=new_data)

@router.post("/notifications/test", response_model=ApiResponse)
async def test_notification_connection(payload: NotificationTestRequest):
    """即时测试 Telegram 代理与通知连通性"""
    test_dict = {k: v for k, v in payload.model_dump().items() if v is not None}
    
    success, msg = await notifier_service.test_notification(test_dict)
    if not success:
        return ApiResponse(code=400, message=msg)

    return ApiResponse(message="测试消息已成功送达 Telegram！请在客户端查收")
