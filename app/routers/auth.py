from fastapi import APIRouter, Response, HTTPException, Depends, status
from app.core.config import settings
from app.core.security import (
    create_admin_token, get_current_admin, verify_admin_password, set_admin_password
)
from app.models.schemas import LoginRequest, ChangePasswordRequest, ApiResponse

router = APIRouter(prefix="/api/auth", tags=["Auth"])

@router.post("/login", response_model=ApiResponse)
async def login(payload: LoginRequest, response: Response):
    """管理员登录"""
    if not await verify_admin_password(payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="密码错误，请核对后重试"
        )
    
    token = create_admin_token()
    max_age = settings.TOKEN_EXPIRE_DAYS * 86400

    # 注入安全 Cookie
    response.set_cookie(
        key="minicron_token",
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax"
    )

    return ApiResponse(
        message="登录成功",
        data={
            "token": token,
            "expires_in": max_age
        }
    )

@router.get("/me", response_model=ApiResponse)
async def get_current_user_status(is_admin: bool = Depends(get_current_admin)):
    """校验当前会话鉴权状态"""
    return ApiResponse(
        data={
            "authenticated": True,
            "username": "admin"
        }
    )

@router.post("/logout", response_model=ApiResponse)
async def logout(response: Response):
    """注销会话"""
    response.delete_cookie("minicron_token")
    return ApiResponse(message="已成功退出登录")

@router.post("/change-password", response_model=ApiResponse)
async def change_password(payload: ChangePasswordRequest, is_admin: bool = Depends(get_current_admin)):
    """修改管理员密码"""
    if not await verify_admin_password(payload.old_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码验证失败，请核对后重试"
        )
    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码长度不能少于6位"
        )
    if payload.old_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能与原密码相同"
        )
    await set_admin_password(payload.new_password)
    return ApiResponse(message="密码修改成功，新密码已持久化生效")

