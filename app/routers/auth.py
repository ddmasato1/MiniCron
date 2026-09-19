from fastapi import APIRouter, Response, HTTPException, Depends, status
from app.core.config import settings
from app.core.security import create_admin_token, get_current_admin
from app.models.schemas import LoginRequest, ApiResponse

router = APIRouter(prefix="/api/auth", tags=["Auth"])

@router.post("/login", response_model=ApiResponse)
async def login(payload: LoginRequest, response: Response):
    """管理员登录"""
    if payload.password != settings.ADMIN_PASSWORD:
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
