# MiniCron RESTful API 规范说明书 (API_SPEC)

---

## 1. 基础规范

* **协议与基础路径**：`HTTP/1.1` 或 `HTTP/2`，所有接口均以 `/api` 为前缀。
* **数据交换格式**：统一采用 `application/json`，字符编码为 `UTF-8`。
* **认证方式**：
  * 登录成功后取得会话 Token，请求 Header 中携带：`Authorization: Bearer <SESSION_TOKEN>`
  * 或通过 HTTP-Only Cookie: `minicron_token=<SESSION_TOKEN>`
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
      "expires_in": 604800
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
      "username": "admin"
    }
  }
  ```

### 2.3 注销会话
* **路径**：`POST /api/auth/logout`
* **鉴权要求**：无需鉴权 (公开)
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "已成功退出登录"
  }
  ```

### 2.4 修改管理员密码
* **路径**：`POST /api/auth/change-password`
* **鉴权要求**：需登录鉴权 (`Bearer Token` 或 `Cookie`)
* **请求体 (JSON)**：
  ```json
  {
    "old_password": "current_password",
    "new_password": "new_secure_password"
  }
  ```
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "密码修改成功，新密码已持久化生效"
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

### 4.3 实时获取执行日志 (SSE)
* **路径**：`GET /api/executions/{execution_id}/stream`
* **响应类型**：`text/event-stream`
* **说明**：订阅指定执行记录的实时日志。任务结束后返回 `finished: true` 事件并关闭流。
* **事件示例**：
  ```text
  data: {"line": "开始执行任务...\n"}

  data: {"line": "", "finished": true}
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

### 5.3 在线编辑更新脚本源码
* **路径**：`PUT /api/scripts/content`
* **请求体 (JSON)**：
  ```json
  {
    "path": "custom_checkin.py",
    "content": "#!/usr/bin/env python3\nprint('Updated Code')"
  }
  ```
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "脚本 'custom_checkin.py' 保存成功",
    "data": {
      "relative_path": "custom_checkin.py",
      "file_size": 42,
      "modified_at": "2026-09-19 08:30:00"
    }
  }
  ```

### 5.4 本地文件上传保存
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

### 5.5 删除指定脚本
* **路径**：`DELETE /api/scripts?path={relative_path}`
* **特性**：内置任务依赖防护，若存在任何任务引用该脚本将自动阻断并提示关联任务名称。
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "脚本 'custom_checkin.py' 已成功删除"
  }
  ```

### 5.6 Cron 表达式时间预览工具
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

### 5.7 系统状态与探针
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

### 5.8 获取系统配置与使用指南 Markdown
* **路径**：`GET /api/system/help`
* **鉴权**：需要 Bearer Token
* **功能**：自适应读取并返回 `docs/help.md` 的 Markdown 原始内容，供前端控制台内置帮助模态框渲染。
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "content": "# MiniCron 配置与使用指南 (Help & FAQ) 📖\n\n..."
    }
  }
  ```

---

## 6. 全局环境变量接口 (Global Environment Variables)

### 6.1 获取所有全局环境变量列表
* **路径**：`GET /api/env-vars`
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "success",
    "data": [
      {
        "id": 1,
        "key": "TG_BOT_TOKEN",
        "value": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        "description": "Telegram 告警通知 Bot Token",
        "enabled": true,
        "created_at": "2026-09-19 08:00:00",
        "updated_at": "2026-09-19 08:00:00"
      }
    ]
  }
  ```

### 6.2 创建新的全局环境变量
* **路径**：`POST /api/env-vars`
* **请求体 (JSON)**：
  ```json
  {
    "key": "BARK_KEY",
    "value": "abcdef123456",
    "description": "Bark 推送通知密钥",
    "enabled": true
  }
  ```
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "环境变量 'BARK_KEY' 创建成功",
    "data": { "id": 2, "key": "BARK_KEY" }
  }
  ```

### 6.3 修改全局环境变量
* **路径**：`PUT /api/env-vars/{var_id}`
* **请求体 (JSON)**：
  ```json
  {
    "key": "BARK_KEY",
    "value": "new_secret_key",
    "description": "更新后的 Bark 推送密钥",
    "enabled": true
  }
  ```
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "环境变量更新成功",
    "data": { "id": 2 }
  }
  ```

### 6.4 切换环境变量启用/禁用状态
* **路径**：`POST /api/env-vars/{var_id}/toggle`
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
    "message": "状态切换成功",
    "data": { "id": 2, "enabled": false }
  }
  ```

### 6.5 删除全局环境变量
* **路径**：`DELETE /api/env-vars/{var_id}`
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "环境变量 'BARK_KEY' 已成功删除"
  }
  ```

---

## 7. Python 模块依赖管理接口 (Packages)

### 7.1 获取已安装模块列表
* **路径**：`GET /api/packages`
* **鉴权要求**：需管理员鉴权
* **说明**：获取当前运行环境下所有 pip 模块，标注是否属于 MiniCron 系统核心受保护依赖 (`is_core`) 以及是否属于用户自定义安装持久化依赖 (`is_custom`)。
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "success",
    "data": [
      {
        "name": "requests",
        "version": "2.31.0",
        "is_core": true,
        "is_custom": false
      },
      {
        "name": "pytz",
        "version": "2024.1",
        "is_core": false,
        "is_custom": true
      }
    ]
  }
  ```

### 7.2 查询模块安装状态
* **路径**：`GET /api/packages/status`
* **说明**：检测后台当前是否有正在执行的 `pip install` 任务，防止并发安装产生锁竞争冲突。
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "is_installing": false,
      "target": null
    }
  }
  ```

### 7.3 在线安装第三方模块
* **路径**：`POST /api/packages/install`
* **请求体 (JSON)**：
  ```json
  {
    "name": "beautifulsoup4>=4.12.0",
    "mirror": "https://pypi.tuna.tsinghua.edu.cn/simple"
  }
  ```
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "模块 'beautifulsoup4' 安装成功 (版本: 4.12.3)",
    "data": {
      "success": true,
      "name": "beautifulsoup4",
      "version": "4.12.3",
      "message": "模块 'beautifulsoup4' 安装成功 (版本: 4.12.3)"
    }
  }
  ```

### 7.4 卸载自定义模块
* **路径**：`POST /api/packages/uninstall`
* **请求体 (JSON)**：
  ```json
  {
    "name": "beautifulsoup4"
  }
  ```
* **说明**：支持卸载用户通过界面安装的第三方模块。若尝试卸载 MiniCron 核心依赖（如 `fastapi`, `apscheduler`），将被安全机制硬阻断拦截（HTTP 400）。
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "模块 'beautifulsoup4' 已成功卸载"
  }
  ```

### 7.5 实时流式捕获安装日志 (SSE)
* **路径**：`GET /api/packages/install/stream`
* **数据流格式**：`text/event-stream`
* **事件内容**：
  ```
  data: {"line": "Looking in indexes: https://pypi.tuna.tsinghua.edu.cn/simple\n"}

  data: {"line": "Collecting beautifulsoup4\n"}

  data: {"line": "Successfully installed beautifulsoup4-4.12.3\n"}

  data: {"line": "", "finished": true}
  ```

---

## 8. 系统通知与网络代理接口 (Notifications & Settings)

### 8.1 获取当前通知与代理配置
* **路径**：`GET /api/settings/notifications`
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "success",
    "data": {
      "telegram_enabled": true,
      "telegram_bot_token": "123456:ABC-DEF...",
      "telegram_chat_id": "987654321",
      "proxy_url": "http://127.0.0.1:7890",
      "api_base_url": "https://api.telegram.org",
      "notify_policy": "CUSTOM_ONLY",
      "security_notify_enabled": true,
      "security_chat_id": "11223344",
      "notify_on_login_success": false,
      "notify_on_login_failure": true,
      "notify_on_password_change": true
    }
  }
  ```

### 8.2 保存通知与代理配置
* **路径**：`POST /api/settings/notifications`
* **请求体 (JSON)**：
  ```json
  {
    "telegram_enabled": true,
    "telegram_bot_token": "123456:ABC-DEF...",
    "telegram_chat_id": "987654321",
    "proxy_url": "http://127.0.0.1:7890",
    "api_base_url": "https://api.telegram.org",
    "notify_policy": "CUSTOM_ONLY",
    "security_notify_enabled": true,
    "security_chat_id": "11223344",
    "notify_on_login_success": false,
    "notify_on_login_failure": true,
    "notify_on_password_change": true
  }
  ```
* **响应示例**：
  ```json
  {
    "code": 0,
    "message": "通知与网络代理配置已成功保存",
    "data": { ... }
  }
  ```

### 8.3 测试 Telegram 通知与代理连通性
* **路径**：`POST /api/settings/notifications/test`
* **请求体 (JSON)**：
  ```json
  {
    "telegram_bot_token": "123456:ABC-DEF...",
    "telegram_chat_id": "987654321",
    "security_chat_id": "11223344",
    "test_type": "task",
    "proxy_url": "socks5://127.0.0.1:1080",
    "api_base_url": "https://api.telegram.org"
  }
  ```
* `test_type` 可选值为 `task`（测试任务通知，使用 `telegram_chat_id`）或 `security`（测试安全告警，优先使用 `security_chat_id`，未填写时回退至任务 Chat ID）。
* **成功响应**：
  ```json
  {
    "code": 0,
    "message": "测试消息已成功送达 Telegram！请在客户端查收"
  }
  ```
* **连通失败响应 (带友好诊断原因)**：
  ```json
  {
    "code": 400,
    "message": "代理连接失败，请检查代理地址是否可用或端口是否正确: ..."
  }
  ```

