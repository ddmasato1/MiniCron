# MiniCron 系统设计与架构方案 (ARCHITECTURE)

---

## 1. 架构目标与设计原则

MiniCron 的设计遵循三大核心原则：
1. **轻量至简 (Minimalist)**：零多余后台进程、零重型中间件依赖（无 Redis、无外部 MQ），单机自包含，系统常驻内存严格控制在 **50MB** 以内。
2. **防注入沙箱 (Security Sandbox)**：将“防命令注入、防路径越权、防未授权访问”作为底层第一设计原则，杜绝由于 Web 界面暴露引发的服务器被提权风险。
3. **高内聚可扩展 (Self-Contained & Extensible)**：前后端一体化单端口交付，调度器与数据持久层紧密联动，支持未来无缝扩展推送渠道（如 Bark / 钉钉 / 企业微信通知）。

---

## 2. 系统整体架构 (System Architecture)

```mermaid
flowchart TD
    subgraph Client ["前端交互层 (Client)"]
        UI["Web 控制台 (Single Page App)<br/>Vue 3 + Tailwind CSS<br/>(含在线编辑器 / 依赖管理 / 环境变量 / 智能诊断)"]
    end

    subgraph Server ["MiniCron 核心服务 (Python / FastAPI)"]
        Router["API 路由网关 (FastAPI)"]
        AuthMiddleware["鉴权守卫 (Cookie / Token Auth & PBKDF2)"]
        
        subgraph CoreEngine ["核心引擎层"]
            Scheduler["调度管理器 (APScheduler)<br/>CronTrigger + JobListener"]
            Security["安全守卫 (SecurityGuard)<br/>Path Sandbox + No-Shell Argv"]
            Runner["异步任务执行器 (TaskRunner)<br/>Async Subprocess + Stream Tee"]
            PkgMgr["依赖管理器 (PackageManager)<br/>pip Subprocess + SSE Broadcast"]
        end

        subgraph ServiceLayer ["业务服务层"]
            TaskSvc["任务服务 (TaskService)"]
            LogSvc["日志服务 (LogService)"]
            ScriptSvc["脚本服务 (ScriptService)"]
            EnvVarSvc["环境变量服务 (EnvVarService)"]
        end
    end

    subgraph Storage ["数据与持久化层 (Storage)"]
        DB[("SQLite 数据库 (minicron.db)<br/>tasks / task_executions<br/>global_env_vars / custom_packages<br/>system_configs")]
        LogFiles["执行日志目录<br/>(data/logs/)"]
        ScriptFiles["白名单脚本目录<br/>(scripts/*.py)"]
    end

    UI <-->|HTTP REST / Server-Sent Events| Router
    Router --> AuthMiddleware
    AuthMiddleware --> ServiceLayer
    
    TaskSvc --> DB
    TaskSvc --> Scheduler
    ScriptSvc --> ScriptFiles
    EnvVarSvc --> DB
    PkgMgr --> DB
    
    Scheduler -->|定时触发| Runner
    TaskSvc -->|手动触发 Run Now| Runner
    
    Runner --> Security
    Security -->|校验安全路径| ScriptFiles
    Runner -->|合并全局与任务环境变量| EnvVarSvc
    Runner -->|派生受限子进程| Subprocess["Python 独立子进程<br/>(sys.executable + argv)"]
    
    Subprocess -->|stdout / stderr| Runner
    Runner -->|写入日志| LogFiles
    Runner -->|回填执行结果| LogSvc
    LogSvc --> DB
```

---

## 3. 核心子系统与模块职责

### 3.1 调度管理器 (`app.core.scheduler`)
* **核心组件**：基于 `apscheduler.schedulers.background.BackgroundScheduler`。
* **生命周期集成**：
  * **应用启动**：FastAPI `lifespan` 启动事件中，从 SQLite 遍历所有 `enabled=True` 的任务并注册为 CronJob。
  * **动态热更新**：通过 Web 界面新增、编辑、删除或暂停任务时，调度管理器动态调用 `add_job`、`modify_job`、`remove_job` 或 `pause_job`，**无需重启服务**。
  * **重入保护**：配置 `max_instances=1, coalesce=True`，杜绝同一任务因耗时过长导致定时并发堆叠。

### 3.2 安全任务执行器 (`app.services.runner`)
* **进程隔离**：
  ```python
  # 核心安全执行范例：杜绝 shell=True 与字符串拼接
  process = await asyncio.create_subprocess_exec(
      sys.executable,
      script_absolute_path,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.STDOUT,
      env=merged_env,
      cwd=str(SCRIPTS_DIR)
  )
  ```
* **流式日志捕获 (Stream Teeing)**：
  * 子进程的输出通过异步迭代器实时读取。
  * **双向落盘**：一边实时写入对应的文件 `data/logs/<task_id>_<exec_id>.log`，一边广播给当前正在查看实时日志的 Web 客户端。
* **超时终止机制**：
  * 使用 `asyncio.wait_for(..., timeout=task.timeout_seconds)`，超时未退出时向子进程发送 `SIGTERM`，若 3 秒内未退出则强制 `SIGKILL`，防止僵尸进程。

### 3.3 安全沙箱模型 (`app.core.security`)
为彻底吸取青龙面板的安全教训，MiniCron 在架构上设立 4 道硬核防线：

| 防御维度 | 青龙等传统系统常见隐患 | MiniCron 架构级防护 |
| :--- | :--- | :--- |
| **命令执行方式** | 允许输入字符串通过 `sh -c "..."` 执行，极易被拼接注入 (如 `; rm -rf` 或反弹 shell) | 强制使用 `create_subprocess_exec` 列表传参，**彻底禁用系统 Shell 解释器** |
| **文件路径控制** | 未对相对路径严格校验，存在 `../../etc/passwd` 等路径遍历风险 | 强制调用 `path.resolve()`，校验 `child.is_relative_to(SCRIPTS_DIR)`，违者直接阻断 |
| **依赖与动态代码** | 允许从未知 Git 仓库直接拉取执行动态代码，存在供应链投毒 | 只允许执行本地人工放置在 `./scripts` 的脚本，不提供外部任意拉库机制 |
| **接口鉴权体系** | 存在未授权接口或默认空密码，易被公网扫描器撞库爆破 | 启动时强制要求设定 `ADMIN_PASSWORD` 或生成随机强 Token，全量 API 接入鉴权校验 |

### 3.4 模块依赖管理器与容器自愈 (`app.services.package_service`)
* **异步 `pip` 管道执行**：
  * 使用 `asyncio.create_subprocess_exec` 触发 `python -m pip install <package> -i <mirror> --no-cache-dir`。
  * 并发互斥锁设计，同一时间仅允许单个包在后台执行安装，防止底层 pip 锁冲突。
* **Server-Sent Events (SSE) 终端日志广播**：
  * 通过内存多播队列 (`asyncio.Queue`)，将 `pip` 子进程输出的标准输出与标准错误按行实时推送给前端控制台。
* **核心运行库硬拦截保护**：
  * 内置核心依赖集合 `CORE_PACKAGES`（如 `fastapi`, `uvicorn`, `apscheduler`, `aiosqlite`, `pydantic`, `pip` 等）。
  * 拒绝卸载核心模块（抛出 HTTP 400），防止由于 Web 控制台误操作造成 MiniCron 进程崩溃。
* **容器重启自愈自愈恢复 (`restore_custom_packages`)**：
  * 自定义模块安装成功后持久化写入 SQLite `custom_packages` 表；
  * FastAPI 启动时（`lifespan`），系统自动拉取当前 `pip list` 与数据表比对，自动安装缺失依赖，完美解决容器销毁重建后的环境丢失痛点。

### 3.5 全局环境变量多级注入机制 (`app.routers.env_vars` & `app.services.runner`)
* **多级注入模型**：
  ```text
  基础操作系统环境 (os.environ)
            ↓
  全局已启用环境变量 (global_env_vars, enabled=1)
            ↓
  任务独有自定义环境变量 (task.env_vars, JSON Map，同名优先覆盖)
  ```
* **敏感数据脱敏**：
  * 前端以掩码显示（如 `1234••••5678`），支持明文切换与快速复制；
  * 子进程启动日志仅记录注入的 Key 列表，避免日志落盘泄露密钥。

### 3.6 密码持久化与哈希安全模型 (`app.core.security`)
* **PBKDF2-HMAC-SHA256 加盐算法**：
  * 每次生成 16 字节密码学安全随机 Salt，执行 100,000 次加盐迭代哈希；
  * 存储格式：`pbkdf2:sha256:100000$<salt_hex>$<hash_hex>`；
  * 比对时使用 `hmac.compare_digest` 恒定时间比对，杜绝时序攻击（Timing Attack）；
* **多源优先降级策略**：
  * 优先读取 SQLite `system_configs` 中键为 `admin_password_hash` 的记录；
  * 若数据库未配置，则回退兼容环境变量 `ADMIN_PASSWORD` 或默认密码 `admin123`。

---

## 4. 任务执行状态机与时序图

### 4.1 状态流转模型

```mermaid
stateDiagram-v2
    [*] --> PENDING: 定时触发 / 手动 Run Now
    PENDING --> RUNNING: 分配 ExecutionID，拉起子进程
    RUNNING --> SUCCESS: ExitCode == 0
    RUNNING --> FAILED: ExitCode != 0
    RUNNING --> TIMEOUT: 运行超过最大超时时间 (SIGKILL)
    SUCCESS --> [*]: 回写日志索引与结束时间
    FAILED --> [*]: 回写日志索引与结束时间
    TIMEOUT --> [*]: 记录超时状态并回写
```

### 4.2 任务触发执行时序图

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户 / APScheduler
    participant Router as API / 调度钩子
    participant Runner as TaskRunner 执行器
    participant Security as SecurityGuard
    participant Process as Python 子进程
    participant LogStorage as 日志文件系统
    participant DB as SQLite 数据库

    User->>Router: 触发任务 (task_id)
    Router->>DB: 检查任务是否存在且未在运行中
    Router->>Runner: 提交执行请求
    Runner->>DB: 插入执行历史 (status='RUNNING', start_time=Now)
    Runner->>Security: 校验脚本路径合法性
    Security-->>Runner: 校验通过 (返回安全绝对路径)
    
    Runner->>Process: 派生独立 Python 进程 (argv, env, cwd)
    
    loop 实时输出捕获
        Process-->>Runner: stdout / stderr 数据块
        Runner->>LogStorage: 追加写入 data/logs/<exec_id>.log
    end

    Process-->>Runner: 进程结束，返回 exit_code
    Runner->>DB: 更新执行记录 (status, exit_code, end_time, duration)
    Runner-->>Router: 执行完成通知
```

---

## 5. 数据模型设计 (Database Schema)

MiniCron 采用轻量 SQLite 单文件数据库，开启 **WAL (Write-Ahead Logging)** 模式以支持高并发读写。

### 5.1 数据表关系 (E-R)

```mermaid
erDiagram
    TASK ||--o{ TASK_EXECUTION : "拥有多次执行历史"
    
    TASK {
        int id PK "自增主键"
        string name "任务名称 (如: 掘金签到)"
        string script_path "脚本相对路径 (如: checkin.py)"
        string cron_expression "Cron 表达式 (如: 0 8 * * *)"
        string env_vars "任务级私有环境变量 (JSON 格式)"
        int timeout_seconds "超时限制 (秒，默认 300)"
        bool enabled "是否启用 (1=启用, 0=暂停)"
        datetime next_run_time "预计下次运行时间"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    TASK_EXECUTION {
        string id PK "UUID 唯一执行流水号"
        int task_id FK "关联任务 ID"
        string status "状态 (RUNNING / SUCCESS / FAILED / TIMEOUT)"
        int exit_code "子进程退出码 (0为成功)"
        datetime start_time "开始时间"
        datetime end_time "结束时间"
        float duration_seconds "执行耗时 (秒)"
        string log_path "关联日志文件相对路径"
        string trigger_type "触发来源 (CRON / MANUAL)"
    }

    GLOBAL_ENV_VAR {
        int id PK "自增主键"
        string key "变量键名 (唯一索引)"
        string value "变量值"
        string description "用途说明"
        bool enabled "启用开关 (1=生效, 0=禁用)"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    CUSTOM_PACKAGE {
        int id PK "自增主键"
        string name "模块名称 (如: beautifulsoup4，唯一索引)"
        string version "安装版本号 (如: 4.12.3)"
        datetime installed_at "安装完成时间"
    }

    SYSTEM_CONFIG {
        int id PK "自增主键"
        string key "配置项键名 (如: admin_password_hash，唯一索引)"
        string value "配置项数值"
        datetime updated_at "最后更新时间"
    }
```

---

## 6. 前端控制台架构设计

* **架构选型**：纯静态现代化单页面 (SPA)。
* **技术方案**：
  * 基于现代化 ESM 模块化加载的 Vue 3 + Tailwind CSS。
  * 零构建步骤（无需本地 Node.js、npm build），直接由 FastAPI 的 `StaticFiles` 服务高效托管。
* **界面模块划分**：
  1. **Dashboard 顶部全局导航**：
     * 系统状态指标（实时时间、运行中任务数、系统内存占用）；
     * 快捷运维入口：**「🌐 环境变量」**、**「📦 依赖管理」**、**「🔑 修改密码」**、**「🚪 退出登录」**。
  2. **任务主看板**：
     * 表格/卡片布局展示所有任务，显示状态、上次耗时、下次触发时间；
     * 操作栏：一键“立即运行”、“查看最新日志”、“编辑”、“启用/禁用开关”。
  3. **任务配置弹窗**：
     * 智能 Cron 表达式输入框 + 实时预演未来 5 次触发时间；
     * 可用脚本下拉单选框，配备「在线编辑此脚本」快捷跳转入口；
     * 任务级私有环境变量动态 Key-Value 编辑器。
  4. **全功能日志抽屉 (Log Viewer)**：
     * 暗色终端风格视图，支持一键清屏、自动滚动追踪最新输出、日志内容复制与下载；
     * **智能缺失依赖诊断横幅 (Smart Diagnostics)**：检测到 `ModuleNotFoundError` 错误时自动弹出黄色警告条，并提供「一键在线安装」快捷直达按钮。
  5. **全功能脚本管理中心 (Script Hub)**：
     * 涵盖已有脚本清单、在线粘贴编写保存、本地 `.py` 文件拖拽上传、在线源码只读查看；
     * **在线代码编辑器**：提供代码高亮、行号与字数统计、Tab 插入 4 空格、`Ctrl+S` / `Cmd+S` 快捷键瞬间保存；
     * **防误删保护机制**：删除脚本前自动检测关联定时任务，被引用时强制拦截并友好提示。
  6. **全局环境变量管理面板 (Env Modal)**：
     * 统一管理所有任务共享的全局配置；
     * 敏感密钥脱敏掩码显示、支持小眼睛一键明暗文切换与便捷复制；
     * 支持单个变量无损启停切换与在线修改。
  7. **第三方依赖管理中心 (Package Modal)**：
     * 实时检索当前 Python 环境已安装模块，区分核心系统库与自定义扩展；
     * 在线安装模块：支持输入包名与版本，内置清华源、阿里源、腾讯源、官方源下拉选择；
     * **SSE 实时终端日志流**：安装过程实时回显终端控制台；
     * 核心依赖保护：严密禁用核心库的卸载入口，杜绝系统崩溃风险。
  8. **管理员密码修改弹窗 (Password Modal)**：
     * 原密码验证防非法篡改，新密码二次确认校验，修改成功自动持久化并更新当前凭证。

---

## 7. 部署方案与生产建议

1. **Docker Compose 容器化模式 (生产首选 🌟)**：
   * 基于 `python:3.11-alpine`，完整镜像体积仅 **98.6MB**（网络拉取仅约 35MB），内存占用 < 35MB。
   * 固化时区 `TZ=Asia/Shanghai`，确保定时规则按当地时间精准执行。
   * 双目录挂载：`./data:/app/data` (持久化数据库与日志) 与 `./scripts:/app/scripts` (挂载脚本并支持 Web 界面双向同步热更新)。
   * 启动命令：
     ```bash
     docker compose up -d
     ```
2. **生产环境反向代理建议**：
   * MiniCron 容器绑定映射至宿主机 `127.0.0.1:8000`。
   * 外网使用 Nginx 配置 SSL 证书并反向代理，配合 Fail2ban、Cloudflare 或 Tailscale 内网实现安全访问。
3. **本地 Conda / Python 环境运行 (开发模式)**：
   ```bash
   source ~/.zshrc
   conda activate minicron
   ./start.sh
   ```
