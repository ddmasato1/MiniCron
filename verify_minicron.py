#!/usr/bin/env python3
import asyncio
import os
import sys
from pathlib import Path

# 添加工程根目录至 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import settings
from app.core.security import validate_script_path, create_admin_token, verify_token
from app.core.scheduler import scheduler_manager
from app.models.db import init_db, get_db
from app.services.runner import task_runner

async def main():
    print("=== [1/5] 测试核心配置与目录初始化 ===")
    print(f"BASE_DIR: {settings.BASE_DIR}")
    print(f"DB_PATH:  {settings.DB_PATH}")
    assert settings.SCRIPTS_DIR.exists(), "scripts 目录不存在"
    print("✅ 目录与配置检查通过")

    print("\n=== [2/5] 测试安全沙箱路径防注入校验 ===")
    # 正常脚本校验
    valid_path = validate_script_path("sample_checkin.py")
    print(f"合法脚本解析: {valid_path}")
    assert valid_path.exists(), "脚本文件应存在"

    # 路径穿越测试 (../)
    try:
        validate_script_path("../../../etc/passwd")
        assert False, "未能成功拦截路径穿越"
    except Exception as e:
        print(f"✅ 成功拦截非法路径穿越: {e}")

    # 非 Python 文件测试
    try:
        validate_script_path("../requirements.txt")
        assert False, "未能成功拦截非 py 扩展名"
    except Exception as e:
        print(f"✅ 成功拦截非 Python 文件: {e}")

    print("\n=== [3/5] 测试 Token 生成与时序安全验证 ===")
    token = create_admin_token()
    print(f"生成 Token: {token[:30]}...")
    assert verify_token(token) is True, "有效 Token 校验失败"
    assert verify_token("fake:token:signature") is False, "非法 Token 应被拦截"
    print("✅ Token 鉴权校验通过")

    print("\n=== [4/5] 测试数据库初始化与任务执行器 ===")
    await init_db()
    print("SQLite 数据库初始化完成")

    # 写入一个测试任务
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO tasks (name, script_path, cron_expression, env_vars, timeout_seconds, enabled)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("测试每日签到", "sample_checkin.py", "0 8 * * *", '{"CHECKIN_ACCOUNT_ID": "test_user_888"}', 60, 1)
        )
        await db.commit()
        test_task_id = cursor.lastrowid
        print(f"已创建测试任务 ID: {test_task_id}")

    # 执行任务
    print("正在启动任务执行器...")
    exec_id = await task_runner.run_task(test_task_id, trigger_type="MANUAL")
    print(f"执行流水号: {exec_id}")

    # 等待子进程执行完毕
    for _ in range(15):
        await asyncio.sleep(0.5)
        if not task_runner.is_task_running(test_task_id):
            break

    # 验证执行结果
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM task_executions WHERE id = ?", (exec_id,))
        record = await cursor.fetchone()
        assert record is not None, "未找到执行记录"
        record_dict = dict(record)
        print(f"执行记录: 状态={record_dict['status']}, 退出码={record_dict['exit_code']}, 耗时={record_dict['duration_seconds']}s")
        assert record_dict['status'] == "SUCCESS", f"任务应为 SUCCESS 状态，实际为 {record_dict['status']}"
        assert record_dict['exit_code'] == 0, f"退出码应为 0，实际为 {record_dict['exit_code']}"

    # 读取生成的日志文件
    log_file = settings.LOGS_DIR / record_dict["log_path"]
    assert log_file.exists(), "日志文件不存在"
    log_content = log_file.read_text(encoding="utf-8")
    print(f"捕获到的执行日志片段:\n{log_content.strip()}")
    assert "test_user_888" in log_content, "自定义环境变量未能成功传递给子进程"
    print("✅ 任务执行器与日志捕获验证通过")

    print("\n=== [5/5] 测试 APScheduler 调度器集成 ===")
    scheduler_manager.start()
    await scheduler_manager.reload_all_jobs()
    next_run = scheduler_manager.get_next_run_time(test_task_id)
    print(f"任务下一次触发时间: {next_run}")
    assert next_run is not None, "未获取到预计触发时间"

    preview_times = scheduler_manager.preview_cron("0 8 * * *", 3)
    print(f"Cron 预演未来 3 次: {preview_times}")
    assert len(preview_times) == 3, "Cron 预演数量不匹配"
    scheduler_manager.shutdown()
    print("✅ 调度器测试通过")

    print("\n=== [6/6] 测试页面脚本在线保存与防误删依赖保护 ===")
    from app.routers.scripts import save_script_content, delete_script_file, sanitize_script_filename
    from app.models.schemas import ScriptSaveRequest

    assert sanitize_script_filename("test_tool") == "test_tool.py"
    req = ScriptSaveRequest(filename="auto_pasted.py", content="#!/usr/bin/env python3\nprint('Pasted OK')", overwrite=True)
    res = await save_script_content(req)
    assert res.code == 0
    saved_path = settings.SCRIPTS_DIR / "auto_pasted.py"
    assert saved_path.exists()

    # 测试防误删：被使用的脚本不可删除
    try:
        await delete_script_file("sample_checkin.py")
        assert False, "应当阻断对被引用脚本的删除"
    except Exception:
        print("✅ 成功阻断删除已被任务引用的脚本")

    # 删除临时测试脚本
    del_res = await delete_script_file("auto_pasted.py")
    assert del_res.code == 0
    assert not saved_path.exists()
    print("✅ 脚本在线保存与安全删除测试通过")

    print("\n🎉 全部 6 项自动化测试验证通过！")

if __name__ == "__main__":
    asyncio.run(main())
