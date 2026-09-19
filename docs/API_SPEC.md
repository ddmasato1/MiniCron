# MiniCron RESTful API 规范说明书 (API_SPEC)

---

## 1. 基础规范

* **协议与基础路径**：`HTTP/1.1` 或 `HTTP/2`，所有接口均以 `/api` 为前缀。
* **数据交换格式**：统一采用 `application/json`，字符编码为 `UTF-8`。
* **认证方式**：
  * 请求 Header 中携带：`Authorization: Bearer <ADMIN_TOKEN>`
  * 或通过 HTTP-Only Cookie: `minicron_token=<ADMIN_TOKEN>`
* **统一响应体包装**：
  ```json
  {
    "code": 0,
    "message": "success",
    "data": { ... }
  }
  ```
  *(注：业务成功时 `code` 为 0，发生异常时 `code` 大于 0，并在 `message` 中给出具体错误原因)*

---

## 2. 身份认证接口 (Auth)

### 2.1 用户登录
* **路径**：`POST /api/auth/login`
* **鉴权要求**：无需鉴权 (公开)
* **请求体 (JSON)**：
  ```json
  {
    "password": "your_secure_password"
  }
  ```
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "登录成功",
    "data": {
      "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "expire_at": "2026-09-26T23:59:59Z"
    }
  }
  ```

### 2.2 验证登录状态
* **路径**：`GET /api/auth/me`
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "authenticated": true,
      "role": "admin"
    }
  }
  ```

---

## 3. 任务管理接口 (Tasks)

### 3.1 获取所有任务列表
* **路径**：`GET /api/tasks`
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "success",
    "data": [
      {
        "id": 1,
        "name": "每日论坛签到",
        "script_path": "sample_checkin.py",
        "cron_expression": "0 8 * * *",
        "enabled": true,
        "timeout_seconds": 300,
        "env_vars": {
          "ACCOUNT_ID": "user_001"
        },
        "next_run_time": "2026-09-20T08:00:00+08:00",
        "latest_execution": {
          "id": "c7a8b3d1-4e92-421b-b461-71bf9e8a719a",
          "status": "SUCCESS",
          "exit_code": 0,
          "start_time": "2026-09-19T08:00:01+08:00",
          "duration_seconds": 2.15
        }
      }
    ]
  }
  ```

### 3.2 创建新任务
* **路径**：`POST /api/tasks`
* **请求体 (JSON)**：
  ```json
  {
    "name": "B站每日投币",
    "script_path": "bilibili_checkin.py",
    "cron_expression": "30 9 * * *",
    "enabled": true,
    "timeout_seconds": 300,
    "env_vars": {
      "BILI_COOKIE": "SESSDATA=xxxxx;"
    }
  }
  ```
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "任务创建成功",
    "data": {
      "id": 2,
      "name": "B站每日投币",
      "next_run_time": "2026-09-19T09:30:00+08:00"
    }
  }
  ```

### 3.3 修改任务配置
* **路径**：`PUT /api/tasks/{task_id}`
* **请求体 (JSON)**：与创建任务一致。
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "任务更新成功",
    "data": { "id": 1 }
  }
  ```

### 3.4 切换任务启用/禁用状态
* **路径**：`POST /api/tasks/{task_id}/toggle`
* **请求体 (JSON)**：
  ```json
  {
    "enabled": false
  }
  ```
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "已成功禁用该任务",
    "data": { "id": 1, "enabled": false }
  }
  ```

### 3.5 删除任务
* **路径**：`DELETE /api/tasks/{task_id}`
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "任务已删除",
    "data": { "id": 1 }
  }
  ```

### 3.6 手动立即触发任务 (Run Now)
* **路径**：`POST /api/tasks/{task_id}/run`
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "任务已触发执行",
    "data": {
      "execution_id": "9d81d451-cfa8-4bf0-a925-5e60938e2190",
      "task_id": 1,
      "status": "RUNNING"
    }
  }
  ```

---

## 4. 执行历史与日志接口 (Executions & Logs)

### 4.1 获取任务历史执行记录
* **路径**：`GET /api/tasks/{task_id}/executions?limit=20&page=1`
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "total": 45,
      "list": [
        {
          "id": "c7a8b3d1-4e92-421b-b461-71bf9e8a719a",
          "trigger_type": "CRON",
          "status": "SUCCESS",
          "exit_code": 0,
          "start_time": "2026-09-19T08:00:01+08:00",
          "end_time": "2026-09-19T08:00:03+08:00",
          "duration_seconds": 2.15
        }
      ]
    }
  }
  ```

### 4.2 获取某次执行的完整日志内容
* **路径**：`GET /api/executions/{execution_id}/log`
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "execution_id": "c7a8b3d1-4e92-421b-b461-71bf9e8a719a",
      "content": "[2026-09-19 08:00:01] 开始执行日常签到任务...\n当前签到账号: user_001\n正在连接签到服务...\n今日签到成功！获得积分: 10点。\n[2026-09-19 08:00:03] 任务执行完成。\n"
    }
  }
  ```

---

## 5. 脚本与系统辅助接口 (Scripts & System)

### 5.1 获取白名单脚本目录文件列表
* **路径**：`GET /api/scripts`
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "success",
    "data": [
      {
        "relative_path": "sample_checkin.py",
        "file_size": 752,
        "modified_at": "2026-09-19T00:14:12+08:00"
      }
    ]
  }
  ```

### 5.2 在线粘贴保存脚本
* **路径**：`POST /api/scripts/save`
* **请求体 (JSON)**：
  ```json
  {
    "filename": "custom_checkin.py",
    "content": "#!/usr/bin/env python3\nprint('Hello')",
    "overwrite": false
  }
  ```
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "脚本 'custom_checkin.py' 已成功保存至 scripts 目录",
    "data": { "relative_path": "custom_checkin.py", "file_size": 35 }
  }
  ```

### 5.3 本地文件上传保存
* **路径**：`POST /api/scripts/upload`
* **请求类型**：`multipart/form-data`
* **表单参数**：
  * `file`: 上传的 Python 文件对象 (*.py)
  * `overwrite`: 布尔值，同名时是否覆盖
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "脚本 'custom_checkin.py' 上传成功并已落盘",
    "data": { "relative_path": "custom_checkin.py", "file_size": 35 }
  }
  ```

### 5.4 删除指定脚本
* **路径**：`DELETE /api/scripts?path={relative_path}`
* **特性**：内置任务依赖防护，若存在任何任务引用该脚本将自动阻断并提示关联任务名称。
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "脚本 'custom_checkin.py' 已成功删除"
  }
  ```

### 5.2 Cron 表达式时间预览工具
* **路径**：`POST /api/tools/cron-preview`
* **请求体 (JSON)**：
  ```json
  {
    "cron_expression": "0 8 * * *"
  }
  ```
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "is_valid": true,
      "next_runs": [
        "2026-09-19 08:00:00",
        "2026-09-20 08:00:00",
        "2026-09-21 08:00:00",
        "2026-09-22 08:00:00",
        "2026-09-23 08:00:00"
      ]
    }
  }
  ```

### 5.3 系统状态与探针
* **路径**：`GET /api/system/status`
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "server_time": "2026-09-19T00:15:00+08:00",
      "uptime_seconds": 3600,
      "memory_usage_mb": 34.8,
      "active_jobs": 3,
      "scheduler_running": true
    }
  }
  ```
