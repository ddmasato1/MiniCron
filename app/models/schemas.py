from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class TaskBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="任务名称")
    script_path: str = Field(..., description="脚本文件名或相对路径，必须在 scripts/ 目录下")
    cron_expression: str = Field(..., description="标准 5 字段 Crontab 表达式")
    env_vars: Dict[str, str] = Field(default_factory=dict, description="环境变量字典")
    timeout_seconds: int = Field(300, ge=10, le=86400, description="超时限制（秒）")
    enabled: bool = Field(True, description="是否启用")

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    script_path: Optional[str] = None
    cron_expression: Optional[str] = None
    env_vars: Optional[Dict[str, str]] = None
    timeout_seconds: Optional[int] = Field(None, ge=10, le=86400)
    enabled: Optional[bool] = None

class TaskToggle(BaseModel):
    enabled: bool

class TaskExecutionOut(BaseModel):
    id: str
    task_id: int
    trigger_type: str
    status: str
    exit_code: Optional[int] = None
    start_time: str
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    log_path: Optional[str] = None

class TaskOut(TaskBase):
    id: int
    created_at: str
    updated_at: str
    next_run_time: Optional[str] = None
    latest_execution: Optional[TaskExecutionOut] = None

class ScriptItem(BaseModel):
    relative_path: str
    file_size: int
    modified_at: str

class ScriptSaveRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=100, description="脚本文件名")
    content: str = Field(..., description="Python 脚本源代码")
    overwrite: bool = Field(False, description="若文件已存在是否覆盖")

class ScriptUpdateRequest(BaseModel):
    path: str = Field(..., min_length=1, description="脚本相对路径")
    content: str = Field(..., description="修改后的 Python 脚本源代码")

class CronPreviewRequest(BaseModel):
    cron_expression: str

class CronPreviewResponse(BaseModel):
    is_valid: bool
    next_runs: List[str]
    error_message: Optional[str] = None

class LoginRequest(BaseModel):
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., description="当前原密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码（至少6位）")

class GlobalEnvVarCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=100, description="环境变量名")
    value: str = Field(..., description="环境变量值")
    description: Optional[str] = Field("", max_length=255, description="备注说明")
    enabled: bool = Field(True, description="是否启用")

class GlobalEnvVarUpdate(BaseModel):
    key: Optional[str] = Field(None, min_length=1, max_length=100)
    value: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None

class GlobalEnvVarToggle(BaseModel):
    enabled: bool

class GlobalEnvVarOut(BaseModel):
    id: int
    key: str
    value: str
    description: str
    enabled: bool
    created_at: str
    updated_at: str

class PackageInstallRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="模块/包名，如 requests 或 bs4==0.0.2")
    mirror: Optional[str] = Field("https://pypi.tuna.tsinghua.edu.cn/simple", description="PyPI 镜像源地址")

class PackageUninstallRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="要卸载的包名")

class PackageItem(BaseModel):
    name: str
    version: str
    is_core: bool = False
    is_custom: bool = False

class NotificationSettings(BaseModel):
    telegram_enabled: bool = Field(False, description="是否启用 Telegram 通知")
    telegram_bot_token: Optional[str] = Field("", description="Telegram Bot Token")
    telegram_chat_id: Optional[str] = Field("", description="Telegram Chat ID")
    proxy_url: Optional[str] = Field("", description="网络代理地址 (如 http://127.0.0.1:7890 或 socks5://127.0.0.1:1080)")
    api_base_url: Optional[str] = Field("https://api.telegram.org", description="Telegram API 基础地址 (支持自建反代域名)")
    notify_policy: str = Field("CUSTOM_ONLY", description="任务通知策略: CUSTOM_ONLY (仅脚本主动通知), ONLY_FAILURE (仅失败), ALWAYS (全部), OFF (关闭)")
    
    # 系统安全通知配置
    security_notify_enabled: bool = Field(True, description="是否启用系统安全事件通知")
    security_chat_id: Optional[str] = Field("", description="安全事件通知独立的 Telegram Chat ID (留空则继承主 Chat ID)")
    notify_on_login_success: bool = Field(False, description="是否开启登录成功通知")
    notify_on_login_failure: bool = Field(True, description="是否开启登录失败告警")
    notify_on_password_change: bool = Field(True, description="是否开启密码修改提醒")

class NotificationTestRequest(BaseModel):
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    proxy_url: Optional[str] = None
    api_base_url: Optional[str] = None
    security_chat_id: Optional[str] = None
    test_type: Optional[str] = Field("task", description="测试类型: task (测试任务通知) 或 security (测试安全告警)")

class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Optional[Any] = None


