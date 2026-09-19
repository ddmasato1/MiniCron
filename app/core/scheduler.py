import logging
from typing import Optional, List
from datetime import datetime
from croniter import croniter
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.services.runner import task_runner
from app.models.db import get_db

logger = logging.getLogger("minicron.scheduler")

class SchedulerManager:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._is_running = False

    def start(self):
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            logger.info("[Scheduler] APScheduler 定时引擎已启动")

    def shutdown(self):
        if self._is_running:
            self.scheduler.shutdown()
            self._is_running = False
            logger.info("[Scheduler] APScheduler 定时引擎已关闭")

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def reload_all_jobs(self):
        """从 SQLite 数据库全量加载所有已启用的任务并注册调度"""
        async with get_db() as db:
            cursor = await db.execute("SELECT id, cron_expression, enabled FROM tasks WHERE enabled = 1")
            tasks = await cursor.fetchall()

        # 清除现有调度
        for job in self.scheduler.get_jobs():
            if job.id.startswith("task_"):
                self.scheduler.remove_job(job.id)

        count = 0
        for task in tasks:
            task_id = task["id"]
            cron_expr = task["cron_expression"]
            try:
                trigger = CronTrigger.from_crontab(cron_expr)
                self.scheduler.add_job(
                    func=task_runner.run_task,
                    trigger=trigger,
                    id=f"task_{task_id}",
                    args=[task_id, "CRON"],
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True
                )
                count += 1
            except Exception as e:
                logger.error(f"[Scheduler] 注册任务 ID={task_id} 定时失败: {e}")

        logger.info(f"[Scheduler] 成功从数据库注册 {count} 个定时任务")

    def add_or_update_job(self, task_id: int, cron_expr: str, enabled: bool):
        """动态新增或热更新单个任务的调度触发"""
        job_id = f"task_{task_id}"
        if not enabled:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            return

        try:
            trigger = CronTrigger.from_crontab(cron_expr)
            self.scheduler.add_job(
                func=task_runner.run_task,
                trigger=trigger,
                id=job_id,
                args=[task_id, "CRON"],
                replace_existing=True,
                max_instances=1,
                coalesce=True
            )
            logger.info(f"[Scheduler] 成功热更新任务 ID={task_id} 定时表达式为: {cron_expr}")
        except Exception as e:
            logger.error(f"[Scheduler] 热更新任务 ID={task_id} 失败: {e}")
            raise ValueError(f"无效的 Crontab 表达式: {cron_expr}")

    def remove_job(self, task_id: int):
        """从调度器中移除任务"""
        job_id = f"task_{task_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

    def get_next_run_time(self, task_id: int) -> Optional[str]:
        """获取指定任务预计的下一次执行时间"""
        job = self.scheduler.get_job(f"task_{task_id}")
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
        return None

    @staticmethod
    def preview_cron(cron_expr: str, count: int = 5) -> List[str]:
        """解析 Cron 表达式并预演未来 N 次执行时间点"""
        if not croniter.is_valid(cron_expr):
            raise ValueError("非法的 Crontab 表达式，请遵循标准 Linux 5 字段格式 (分 时 日 月 周)")
        
        now = datetime.now()
        iter_obj = croniter(cron_expr, now)
        results = []
        for _ in range(count):
            next_dt = iter_obj.get_next(datetime)
            results.append(next_dt.strftime("%Y-%m-%d %H:%M:%S"))
        return results

# 全局单例调度管理器
scheduler_manager = SchedulerManager()
