import hmac
import hashlib
import time
from pathlib import Path
from typing import Optional
from fastapi import HTTPException, Security, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

security_bearer = HTTPBearer(auto_error=False)

def create_admin_token() -> str:
    """基于密钥与时间戳生成防篡改管理 Token"""
    timestamp = str(int(time.time()))
    payload = f"admin:{timestamp}"
    signature = hmac.new(
        settings.SECRET_KEY.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return f"{payload}:{signature}"

def verify_token(token: str) -> bool:
    """验证管理 Token 的合法性与有效期限"""
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False
        username, timestamp_str, signature = parts
        if username != "admin":
            return False
        timestamp = int(timestamp_str)
        # 验证是否过期 (默认 7 天)
        if time.time() - timestamp > settings.TOKEN_EXPIRE_DAYS * 86400:
            return False
        
        expected_payload = f"admin:{timestamp_str}"
        expected_sig = hmac.new(
            settings.SECRET_KEY.encode(),
            expected_payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # 使用常量时间比对防时序攻击
        return hmac.compare_digest(signature, expected_sig)
    except Exception:
        return False

async def get_current_admin(
    request: Request,
    auth: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)
) -> bool:
    """FastAPI 依赖注入：校验请求头 Bearer Token 或 Cookie"""
    token = None
    if auth and auth.credentials:
        token = auth.credentials
    elif "minicron_token" in request.cookies:
        token = request.cookies.get("minicron_token")

    if not token or not verify_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败或登录已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True

def validate_script_path(script_relative_path: str) -> Path:
    """
    严谨的安全沙箱路径校验：
    1. 禁止路径穿越 (../)
    2. 校验最终目标是否严格处于 SCRIPTS_DIR 目录内
    3. 校验目标文件必须存在且扩展名为 .py
    """
    scripts_dir = settings.SCRIPTS_DIR.resolve()
    
    # 防止空路径
    clean_path = script_relative_path.strip().lstrip("/\\")
    if not clean_path:
        raise ValueError("脚本路径不能为空")
    
    # 计算解析后的绝对路径
    target_path = (scripts_dir / clean_path).resolve()
    
    # 核心安全防线：判定是否位于白名单目录内
    try:
        target_path.relative_to(scripts_dir)
    except ValueError:
        raise ValueError(f"越权访问阻断：脚本路径 '{script_relative_path}' 超出允许的脚本目录范围")
    
    if not target_path.exists():
        raise FileNotFoundError(f"指定的脚本文件不存在: {script_relative_path}")
    
    if not target_path.is_file():
        raise ValueError(f"指定的路径不是一个有效文件: {script_relative_path}")
        
    if target_path.suffix != ".py":
        raise ValueError(f"安全阻断：仅允许调度 Python 脚本 (*.py)，当前为: {target_path.suffix}")
        
    return target_path
