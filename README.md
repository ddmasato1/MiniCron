# MiniCron 🕒

> **超轻量、高安全、极简易用的 Python 定时任务可视化管理系统**  
> 专为个人日常签到、数据抓取等小型定时脚本打造，彻底替代臃肿且存在安全隐患的传统面板。

---

## 💡 为什么选择 MiniCron？

很多开发者在小型 Linux 服务器或 NAS 上仅需定时运行 3~5 个 Python 签到脚本。过去常使用**青龙面板**，但面临两大痛点：
1. **太重**：多语言运行环境与后台服务常驻，内存开销动辄 **500MB ~ 1.5GB**，低配服务器极易卡死或 OOM。
2. **安全风险高**：历史上频发未授权访问与 RCE（任意命令执行）漏洞，一旦暴露外网极易被入侵沦为肉鸡。

**MiniCron** 采用极简设计理念：
* ⚡ **超低开销**：单 Python 进程托管 Web 与调度，内存占用 **< 50MB**。
* 🛡️ **安全防注入**：禁用一切系统 Shell 拼接执行，白名单隔离脚本路径，杜绝 RCE 与目录穿越。
* 🎯 **开箱即用**：内置 SQLite 与免编译现代化 Web UI，单个端口搞定所有服务，零中间件依赖。

---

## 📁 规范工程目录

```text
MiniCron/
├── docs/                      # 核心规范与设计文档
│   ├── PRD.md                 # 产品需求规格说明书
│   ├── ARCHITECTURE.md        # 系统架构设计方案 (含 Mermaid 拓扑与 E-R 图)
│   ├── API_SPEC.md            # RESTful API 接口规范
│   └── help.md                # 用户配置与使用指南 (FAQ、通知接入、Cron速查)
├── app/                       # 核心业务源码 (FastAPI)
│   ├── core/                  # 配置管理、APScheduler 调度生命周期、PBKDF2 安全鉴权
│   ├── models/                # SQLite 数据模型与 Pydantic 契约
│   ├── routers/               # 任务/执行/系统/环境/依赖/通知设置 API 路由
│   ├── services/              # 任务安全执行器、日志流处理、依赖包管理器、Telegram 通知推送
│   └── static/                # 现代化 Web 控制台 (Vue 3 + Tailwind CSS SPA)
├── scripts/                   # 用户定时 Python 脚本存放目录 (通过 Web 控制台在线编辑/上传/粘贴)
│   ├── notify.py              # MiniCron 通用通知桥接模块 (兼容青龙等常见脚本 from notify import send)
│   └── .gitkeep
├── data/                      # 运行时持久化数据 (Git 忽略)
│   ├── minicron.db            # SQLite 数据库文件 (自动生成与迁移)
│   └── logs/                  # 任务执行日志归档
├── Dockerfile                 # 基于 Python 3.11-slim 的轻量生产镜像
├── docker-compose.yml         # 容器化部署编排 (挂载 data / scripts / app)
├── verify_minicron.py         # 端到端全链路自动化测试套件
├── .gitignore
├── CHANGELOG.md                # 规范发版与版本变更日志
├── README.md
└── requirements.txt           # Python 核心依赖清单 (含 requests, pysocks 等)
```

---

## 📖 文档中心

* 📘 **[配置与使用指南 (HELP & FAQ)](docs/help.md)**：**强烈推荐新手阅读**！包含脚本如何添加通知、Telegram Bot 获取、环境变量优先级、依赖安装与 Crontab 表达式速查表。
* 📋 **[产品需求规格说明书 (PRD)](docs/PRD.md)**：包含业务背景、用户角色、详细功能清单（任务管理、调度执行、日志追踪）及非功能安全指标。
* 🏛️ **[系统架构设计方案 (ARCHITECTURE)](docs/ARCHITECTURE.md)**：包含系统架构拓扑、任务状态机时序图、防注入安全沙箱原理及数据库 E-R 规范。
* 🔌 **[RESTful API 规范文档 (API_SPEC)](docs/API_SPEC.md)**：详细定义所有前后端交互接口与请求响应数据结构。
* 📜 **[版本变更日志 (CHANGELOG)](CHANGELOG.md)**：详细记录各版本的发布与功能演进历史。

---

## 🚀 部署与运行方式

### 方式一：Docker Compose 容器化部署 (推荐生产部署 🌟)
无需在服务器上安装 Python 或任何虚拟环境，通过 Docker 直接运行：

```bash
# 1. 启动容器 (后台运行)
docker compose up -d

# 2. 查看实时运行日志
docker compose logs -f

# 3. 停止容器
docker compose down
```

### 方式二：Docker 单容器运行
```bash
# 1. 构建镜像
docker build -t minicron:latest .

# 2. 启动容器 (挂载数据与脚本目录)
docker run -d \
  --name minicron \
  --restart unless-stopped \
  -p 8000:8000 \
  -e ADMIN_PASSWORD="your_secure_password" \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/scripts:/app/scripts \
  minicron:latest
```

### 方式三：本地 Conda / Python 环境运行
```bash
# 激活本地环境
source ~/.zshrc
conda activate minicron

# 启动服务
./start.sh
```

---

## 🖥️ 访问可视化控制台
浏览器打开：**`http://localhost:8000`**
* **默认管理员密码**：`admin123`（支持在顶部「⚙️ 设置中心」->「修改管理密码」在线修改并持久化落库，亦可通过环境变量 `ADMIN_PASSWORD` 预设）。
* **功能亮点**：
  * 📋 **任务调度**：可视化 Crontab 表达式配置与未来 5 次触发时间预演，一键开启/暂停、手动立即运行。
  * 📝 **脚本在线编辑**：支持在控制台直接在线编写、编辑、粘贴保存或上传 `.py` 脚本文件，内置 Tab 缩进与 `Ctrl+S` / `Cmd+S` 快捷保存。
  * ⚙️ **一体化系统设置中心**：将通知与出海代理、全局环境变量、Python 依赖管理、修改密码全面收敛整合为现代化的侧边栏 Tab 控制台，彻底告别弹窗堆叠与顶栏拥挤。
  * 🔔 **通知体系与系统安全告警（青龙直观模式 + 安全解耦）**：
    * **任务通知（青龙直观模式）**：脚本调用 `notify.send()` 时直接推送纯净的标题+内容，无机器参数噪音；任务崩溃自动兜底告警；支持「仅脚本主动通知」、「仅失败」等灵活策略。
    * **系统安全告警**：登录失败防暴破告警（带客户端 IP 溯源）、密码修改提醒、登录成功通知；支持配置独立安全 Chat ID 分流至管理员私聊。
    * **国内网络穿透**：原生支持 HTTP/SOCKS5 代理及自定义反向代理 Base URL，提供双通道独立测试按钮。
  * 📦 **第三方依赖管理**：在控制台直接管理 Python 模块包（`pip list` / `pip install` / `pip uninstall`），支持清华/阿里/腾讯国内镜像源与 SSE 终端实时流式回显；自定义模块入库持久化并在容器重启时自愈恢复；严密保护核心系统库防止误删。
  * 🔍 **智能模块诊断**：执行任务报错 `ModuleNotFoundError` 时，日志窗口智能识别缺失包名并提示「一键在线安装」，零门槛解决环境缺失问题。
  * 📜 **实时日志捕获**：Server-Sent Events (SSE) 终端流式广播与历史日志全量归档。

---

---

## 🔔 Telegram 结果通知、系统安全告警与出海代理配置

如果您的服务器部署在中国大陆境内，由于网络原因无法直接访问 Telegram 官方 API (`api.telegram.org`)，MiniCron 提供开箱即用的多路穿透方案，并将**系统安全告警**与**日常任务通知**在通道与呈现上进行了彻底解耦：

在控制台顶部点击 **「⚙️ 设置中心」** 并切换至 **「🔔 通知与代理」**：

### 1. 定时任务通知（青龙直观模式）
* **Chat ID**：接收任务执行报告的用户、频道或群组 ID（可通过 [@userinfobot](https://t.me/userinfobot) 查询）。
* **任务通知策略**：
  * `仅脚本主动通知 (青龙模式，推荐)`：日常成功任务静默无打扰；脚本中调用 `notify.send()` 时立即推送纯净业务通知；若脚本异常崩溃或超时，系统自动兜底发送故障告警卡片。
  * `仅失败时通知`：日常签到成功静默，仅在脚本异常（退出码非 0）或超时被杀时发送精简故障报告。
  * `每次执行均通知`：无论成功失败均发送通知。
  * `完全关闭任务通知`。
* **纯净业务内容呈现（图 2 体验）**：
  * 脚本中调用 `from notify import send; send(title, content)` 时，系统直接将标题与内容作为通知主体发送，文末附带轻量标注（`🕒 时间戳 · 任务名`），彻底剔除退出代码、耗时等所有机器参数噪音。
  * 内置 `scripts/notify.py` 垫片，原生兼容青龙面板脚本规范，零侵入、零修改。

### 2. 系统安全通知（独立告警通道）
* **专属安全 Chat ID**：支持单独配置安全告警接收目标（如管理员个人私聊 ID），将敏感安全信息与任务群组彻底隔离；未填写时自动回退至上述任务 Chat ID。
* **细分告警事件开关**：
  * ⚠️ **登录失败告警**（默认开启）：密码验证错误时触发，自动记录并上报来源 IP 地址与时间，强力防范暴力破解。
  * 🔐 **管理员密码修改**（默认开启）：密码变更后立即推送凭据已更新提醒。
  * 🔑 **登录成功提醒**（默认关闭）：自用频繁可关闭，避免打扰；需要时可一键开启。

### 3. 国内服务器网络穿透配置（二选一即可）
* **方案 A：正向代理 (HTTP / SOCKS5)**
  * 若服务器本地或内网运行有代理客户端（如 Clash / v2ray / xray），填入代理地址：
    * HTTP 代理：`http://127.0.0.1:7890`
    * SOCKS5 代理：`socks5://127.0.0.1:1080` 或 `socks5h://...`
* **方案 B：反向代理 Base URL (无需本地代理软件)**
  * 若没有代理客户端，可使用 Cloudflare Workers 或海外 VPS 反向代理 `api.telegram.org`，在「反向代理 Base URL」中填入反代地址，例如：
    * `https://tg-proxy.yourdomain.com`

### 4. 🧪 双通道独立连通性测试
* 点击 **「🧪 测试任务通道」**：即时验证任务群组/频道的推送连通性。
* 点击 **「🛡️ 测试安全通道」**：即时验证管理员专属私聊的安全告警连通性。
* 秒级反馈连接状态与详细排错信息。

---

### 🧪 运行自动化测试套件
```bash
python verify_minicron.py
```

---

## 🔒 安全最佳实践
1. **推荐反代**：在公网部署时，建议监听 `127.0.0.1:8000`，外网通过 Nginx 配置 HTTPS 证书并反向代理。
2. **私有网络**：推荐结合 Tailscale、WireGuard 等私有组网工具访问控制台，不对公网开放 Web 端口。

---

## 📜 发版与更新历史
详细版本变更历史请参阅 **[CHANGELOG.md](CHANGELOG.md)**。
* **[v1.1.0](https://github.com/ddmasato1/MiniCron/releases/tag/v1.1.0)**：系统安全告警拆分、青龙模式纯净自定义通知、双通道独立测试。
* **[v1.0.0](https://github.com/ddmasato1/MiniCron/releases/tag/v1.0.0)**：MiniCron 首个正式版本发布。

