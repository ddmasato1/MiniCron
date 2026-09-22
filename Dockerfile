FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 环境变量：无缓冲、不生成 pyc 缓存、时区设置为上海
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

# 替换 apt 源为清华大学开源镜像源并安装时区支持
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources; \
    fi && \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list; \
        sed -i 's/security.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list; \
    fi && \
    apt-get update && \
    apt-get install -y --no-install-recommends tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# 复制依赖清单利用 Docker 缓存层
COPY requirements.txt .

# 安装 Python 核心依赖 (使用清华 PyPI 镜像加速)
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制应用代码、示例脚本与文档
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY docs/ ./docs/

# 创建持久化日志目录
RUN mkdir -p /app/data/logs

# 暴露端口
EXPOSE 8000

# 启动服务
CMD ["python", "-m", "app.main"]
