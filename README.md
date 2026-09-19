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
│   └── API_SPEC.md            # RESTful API 接口规范
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
├── Dockerfile                 # 98MB 极简 Alpine 生产镜像
├── docker-compose.yml         # 容器化部署编排 (挂载 data / scripts / app)
├── verify_minicron.py         # 端到端全链路自动化测试套件
├── .gitignore
├── README.md
└── requirements.txt           # Python 核心依赖清单 (含 requests, pysocks 等)
```

---

## 📖 设计与规范文档

* 📋 **[产品需求规格说明书 (PRD)](docs/PRD.md)**：包含业务背景、用户角色、详细功能清单（任务管理、调度执行、日志追踪）及非功能安全指标。
* 🏛️ **[系统架构设计方案 (ARCHITECTURE)](docs/ARCHITECTURE.md)**：包含系统架构拓扑、任务状态机时序图、防注入安全沙箱原理及数据库 E-R 规范。
* 🔌 **[RESTful API 规范文档 (API_SPEC)](docs/API_SPEC.md)**：详细定义所有前后端交互接口与请求响应数据结构。

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
  * 🔔 **Telegram 通知与出海代理 (国内服务器支持)**：任务执行后智能异步推送通知（支持「仅失败推送」或「始终推送」）；针对国内服务器防火墙限制，**原生支持 HTTP/SOCKS5 代理**及**自定义反向代理 API Base URL（如 Cloudflare Workers）**，更支持一键在线发送测试通知排查连通性。
  * 📦 **第三方依赖管理**：在控制台直接管理 Python 模块包（`pip list` / `pip install` / `pip uninstall`），支持清华/阿里/腾讯国内镜像源与 SSE 终端实时流式回显；自定义模块入库持久化并在容器重启时自愈恢复；严密保护核心系统库防止误删。
  * 🔍 **智能模块诊断**：执行任务报错 `ModuleNotFoundError` 时，日志窗口智能识别缺失包名并提示「一键在线安装」，零门槛解决环境缺失问题。
  * 📜 **实时日志捕获**：Server-Sent Events (SSE) 终端流式广播与历史日志全量归档。

---

## 🔔 Telegram 结果通知与出海代理配置

如果您的服务器部署在中国大陆境内，由于网络原因无法直接访问 Telegram 官方 API (`api.telegram.org`)，MiniCron 提供两种开箱即用的解决方案：

在控制台顶部点击 **「⚙️ 设置中心」** 并切换至 **「🔔 通知与代理」**：
1. **基础参数**：
   * **Bot Token**：从 [@BotFather](https://t.me/BotFather) 获取的机器人 Token。
   * **Chat ID**：接收通知的用户或群组 ID（可通过 [@userinfobot](https://t.me/userinfobot) 查询）。
   * **推送策略**：
     * `仅失败时推送`（推荐）：日常签到成功静默，仅在脚本异常或超时被杀时报警并附带异常日志摘要。
     * `始终推送`：每次执行完毕均发送完整结果通知（含脚本运行产生的内容）。
     * `关闭通知`。
2. **📢 智能捕获脚本运行内容 (无需修改脚本)**：
   * **实际业务输出推送**：通知中不仅包含退出码、耗时等元数据，还会自动清洗剥离 MiniCron 内部标记，提取脚本实际产生的打印内容（如登录状态、签到积分、用户名等），并以 HTML `<pre>` 规范格式推送。
   * **兼容青龙面板脚本 (`notify.py`)**：内置 `scripts/notify.py` 垫片，原生兼容 `from notify import send` 规范，脚本无需任何修改即可无缝运行与发送通知。
3. **国内服务器防拦截配置（二选一即可）**：
   * **方案 A：正向代理 (HTTP / SOCKS5)**
     * 若服务器本地或内网运行有代理客户端（如 Clash / v2ray / xray），填入代理地址：
       * HTTP 代理：`http://127.0.0.1:7890`
       * SOCKS5 代理：`socks5://127.0.0.1:1080` 或 `socks5h://...`
   * **方案 B：反向代理 Base URL (无需本地代理软件)**
     * 若没有代理客户端，可使用 Cloudflare Workers 或海外 VPS 反向代理 `api.telegram.org`，在「自定义 API Base URL」中填入反代地址，例如：
       * `https://tg-proxy.yourdomain.com`
4. **🧪 连通性测试**：
   * 填写完毕后，点击 **「🧪 发送测试通知」** 按钮，系统将立即尝试向配置的 Telegram 目标发送测试消息，秒级反馈连通状态与详细排错信息。

---

### 🧪 运行自动化测试套件
```bash
python verify_minicron.py
```

---

## 🔒 安全最佳实践
1. **推荐反代**：在公网部署时，建议监听 `127.0.0.1:8000`，外网通过 Nginx 配置 HTTPS 证书并反向代理。
2. **私有网络**：推荐结合 Tailscale、WireGuard 等私有组网工具访问控制台，不对公网开放 Web 端口。

