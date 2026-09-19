import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import asyncio
from app.core.config import settings
from app.models.db import init_db
from app.core.scheduler import scheduler_manager
from app.services.package_service import package_manager
from app.routers import auth, tasks, scripts, system, env_vars, packages, settings as settings_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("minicron")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 初始化 SQLite 数据库与表结构
    logger.info("[Init] 正在初始化 SQLite 数据库...")
    await init_db()

    # 2. 启动 APScheduler 调度器并加载任务
    logger.info("[Init] 正在加载定时任务至 APScheduler...")
    scheduler_manager.start()
    await scheduler_manager.reload_all_jobs()

    # 3. 异步后台检测并恢复自定义依赖模块
    asyncio.create_task(package_manager.restore_custom_packages())

    logger.info(f"🚀 MiniCron 启动完毕！访问地址: http://{settings.HOST}:{settings.PORT}")
    yield

    # 停机清理
    logger.info("[Shutdown] 正在关闭调度引擎...")
    scheduler_manager.shutdown()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 API 路由
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(scripts.router)
app.include_router(system.router)
app.include_router(env_vars.router)
app.include_router(packages.router)
app.include_router(settings_router.router)

# 挂载前端静态文件 (托管 SPA 单页面)
static_dir = settings.BASE_DIR / "app" / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
