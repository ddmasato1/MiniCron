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
│   ├── ARCHITECTURE.md        # 系统架构设计方案 (含 Mermaid 图解)
│   └── API_SPEC.md            # RESTful API 接口规范
├── app/                       # 核心业务源码 (FastAPI)
│   ├── core/                  # 配置管理、APScheduler 调度生命周期、安全鉴权
│   ├── models/                # SQLite 数据模型
│   ├── routers/               # 任务/执行/系统 API 路由
│   ├── services/              # 任务安全执行器、日志流处理
│   └── static/                # 现代化 Web 控制台 (SPA)
├── scripts/                   # 用户定时 Python 脚本存放目录 (通过 Web 控制台上传/新建，代码库默认忽略)
│   └── .gitkeep
├── data/                      # 运行时持久化数据 (Git 忽略)
│   ├── minicron.db            # SQLite 数据库文件 (自动生成)
│   └── logs/                  # 每次执行的任务日志归档
├── .gitignore
├── README.md
└── requirements.txt           # Python 核心依赖清单
```

---

## 📖 设计与规范文档

* 📋 **[产品需求规格说明书 (PRD)](docs/PRD.md)**：包含业务背景、用户角色、详细功能清单（任务管理、调度执行、日志追踪）及非功能安全指标。
* 🏛️ **[系统架构设计方案 (ARCHITECTURE)](docs/ARCHITECTURE.md)**：包含系统架构拓扑、任务状态机时序图、防注入安全沙箱原理及数据库 E-R 规范。
* 🔌 **[RESTful API 规范文档 (API_SPEC)](docs/API_SPEC.md)**：详细定义所有前后端交互接口与请求响应数据结构。

---

## 🚀 快速起步

### 1. 激活 Conda 独立运行环境
已为您在本地创建独立的 Conda 环境 `minicron`：
```bash
source ~/.zshrc
conda activate minicron
```

### 2. 方式一：一键脚本启动 (推荐)
直接运行项目根目录下的启动脚本：
```bash
./start.sh
```

### 3. 方式二：手动 Python 启动
```bash
export ADMIN_PASSWORD="your_secure_password" # 默认 admin123
python -m app.main
```

### 4. 访问可视化控制台
浏览器打开：**`http://localhost:8000`**
* 默认管理员密码：`admin123`
* 登录后可自由添加、编辑、开启/暂停定时任务，或点击“立即运行”并实时查看脚本输出日志。

### 5. 运行自动化测试套件
```bash
python verify_minicron.py
```

---

## 🔒 安全最佳实践
1. **推荐反代**：在公网部署时，建议监听 `127.0.0.1:8000`，外网通过 Nginx 配置 HTTPS 证书并反向代理。
2. **私有网络**：推荐结合 Tailscale、WireGuard 等私有组网工具访问控制台，不对公网开放 Web 端口。
