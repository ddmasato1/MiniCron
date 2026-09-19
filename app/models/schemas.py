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

class CronPreviewRequest(BaseModel):
    cron_expression: str

class CronPreviewResponse(BaseModel):
    is_valid: bool
    next_runs: List[str]
    error_message: Optional[str] = None

class LoginRequest(BaseModel):
    password: str

class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Optional[Any] = None
