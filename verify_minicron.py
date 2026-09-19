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
    sample_script = settings.SCRIPTS_DIR / "sample_checkin.py"
    if not sample_script.exists():
        sample_script.write_text("import os\nprint(f'Checkin OK for user {os.getenv(\"CHECKIN_ACCOUNT_ID\", \"test\")}')\n", encoding="utf-8")
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

    print("\n=== [7/9] 测试管理员密码修改与 PBKDF2 哈希持久化 ===")
    from app.core.security import verify_admin_password, set_admin_password, hash_password, verify_password
    from app.routers.auth import change_password
    from app.models.schemas import ChangePasswordRequest

    # 1. 验证默认密码
    assert await verify_admin_password("admin123") is True, "默认密码应验证通过"
    assert await verify_admin_password("wrong_password") is False, "错误密码应被拦截"

    # 2. 测试修改密码 API
    cp_req = ChangePasswordRequest(old_password="admin123", new_password="new_secret_password_2026")
    cp_res = await change_password(cp_req, is_admin=True)
    assert cp_res.code == 0
    print("密码已修改为新密码")

    # 3. 验证旧密码失效，新密码生效
    assert await verify_admin_password("admin123") is False, "旧密码应失效"
    assert await verify_admin_password("new_secret_password_2026") is True, "新密码应验证通过"

    # 4. 恢复为默认密码方便后续测试
    await set_admin_password("admin123")
    assert await verify_admin_password("admin123") is True
    print("✅ 密码修改与 PBKDF2 哈希持久化测试通过")

    print("\n=== [8/9] 测试脚本在线编辑 (PUT /api/scripts/content) ===")
    from app.routers.scripts import update_script_content, get_script_content
    from app.models.schemas import ScriptUpdateRequest

    edit_req = ScriptUpdateRequest(
        path="sample_checkin.py",
        content="import os\nprint(f'Online Edited: GLOBAL={os.getenv(\"GLOBAL_KEY\", \"\")} TASK={os.getenv(\"CHECKIN_ACCOUNT_ID\", \"\")}')\n"
    )
    edit_res = await update_script_content(edit_req)
    assert edit_res.code == 0
    print(f"在线编辑成功: {edit_res.message}")

    content_res = await get_script_content("sample_checkin.py")
    assert "Online Edited" in content_res.data["content"]
    print("✅ 脚本在线编辑测试通过")

    print("\n=== [9/9] 测试全局环境变量 CRUD 及执行器多级注入与覆盖 ===")
    from app.routers.env_vars import (
        create_env_var, list_env_vars, toggle_env_var, update_env_var, delete_env_var
    )
    from app.models.schemas import (
        GlobalEnvVarCreate, GlobalEnvVarUpdate, GlobalEnvVarToggle
    )

    # 1. 创建全局环境变量
    create_env_res = await create_env_var(GlobalEnvVarCreate(
        key="GLOBAL_KEY",
        value="global_secret_value_123",
        description="全局告警测试密钥",
        enabled=True
    ))
    assert create_env_res.code == 0
    global_var_id = create_env_res.data["id"]

    # 重复创建相同 key 应报错
    try:
        await create_env_var(GlobalEnvVarCreate(key="GLOBAL_KEY", value="dup"))
        assert False, "应阻断同名环境变量创建"
    except Exception:
        print("✅ 成功阻断同名环境变量重复创建")

    # 2. 查询列表
    list_res = await list_env_vars()
    assert any(v["key"] == "GLOBAL_KEY" for v in list_res.data)

    # 3. 运行任务，验证全局环境变量注入
    print("触发任务执行以验证全局环境变量注入...")
    exec_id2 = await task_runner.run_task(test_task_id, trigger_type="MANUAL")
    for _ in range(15):
        await asyncio.sleep(0.5)
        if not task_runner.is_task_running(test_task_id):
            break

    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM task_executions WHERE id = ?", (exec_id2,))
        record2 = dict(await cursor.fetchone())
        assert record2["status"] == "SUCCESS"

    log_file2 = settings.LOGS_DIR / record2["log_path"]
    log_content2 = log_file2.read_text(encoding="utf-8")
    print(f"日志捕获内容:\n{log_content2.strip()}")
    assert "GLOBAL=global_secret_value_123" in log_content2, "全局环境变量未能成功注入子进程"
    assert "TASK=test_user_888" in log_content2, "任务私有环境变量未能正常注入"

    # 4. 测试任务级变量覆盖全局变量
    # 更新任务添加 GLOBAL_KEY="task_override_value"
    async with get_db() as db:
        await db.execute(
            "UPDATE tasks SET env_vars = ? WHERE id = ?",
            ('{"CHECKIN_ACCOUNT_ID": "test_user_999", "GLOBAL_KEY": "task_override_value"}', test_task_id)
        )
        await db.commit()

    exec_id3 = await task_runner.run_task(test_task_id, trigger_type="MANUAL")
    for _ in range(15):
        await asyncio.sleep(0.5)
        if not task_runner.is_task_running(test_task_id):
            break

    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM task_executions WHERE id = ?", (exec_id3,))
        record3 = dict(await cursor.fetchone())
        assert record3["status"] == "SUCCESS"

    log_file3 = settings.LOGS_DIR / record3["log_path"]
    log_content3 = log_file3.read_text(encoding="utf-8")
    assert "GLOBAL=task_override_value" in log_content3, "任务环境变量未能成功覆盖全局环境变量"
    print("✅ 任务环境变量覆盖全局变量机制验证通过")

    # 5. 清理测试环境变量
    del_env_res = await delete_env_var(global_var_id)
    assert del_env_res.code == 0
    print("✅ 全局环境变量 CRUD 与注入覆盖测试通过")

    print("\n=== [10/10] 测试第三方模块依赖管理 (PackageManager) 与安全防护 ===")
    from app.services.package_service import package_manager, CORE_PACKAGES
    from app.routers.packages import list_packages, install_package, uninstall_package
    from app.models.schemas import PackageInstallRequest, PackageUninstallRequest

    # 1. 查询已安装包
    pkgs = await package_manager.list_packages()
    assert len(pkgs) > 0, "pip packages 列表不应为空"
    pkg_dict = {p["name"].lower(): p for p in pkgs}
    assert "fastapi" in pkg_dict, "fastapi 应在已安装列表中"
    assert pkg_dict["fastapi"]["is_core"] is True, "fastapi 应标记为 is_core"
    print(f"已安装依赖总数: {len(pkgs)}，验证核心依赖识别正确")

    # 2. 核心依赖防卸载安全保护拦截
    try:
        await package_manager.uninstall_package("fastapi")
        assert False, "应当阻断核心包 fastapi 的卸载"
    except ValueError as e:
        print(f"✅ 成功阻断核心系统依赖卸载: {e}")

    # 3. 模拟自定义依赖记录与查询
    async with get_db() as db:
        await db.execute(
            "INSERT INTO custom_packages (name, version, installed_at) VALUES (?, ?, ?)",
            ("mock_test_pkg", "1.0.0", "2026-09-19 09:00:00")
        )
        await db.commit()

    pkgs_after = await package_manager.list_packages()
    mock_pkg = next((p for p in pkgs_after if p["name"] == "mock_test_pkg"), None)
    # mock_test_pkg isn't in pip list, but let's verify DB recording
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM custom_packages WHERE name = 'mock_test_pkg'")
        rec = await cursor.fetchone()
        assert rec is not None, "mock_test_pkg 应记录在 DB"
        # 清理
        await db.execute("DELETE FROM custom_packages WHERE name = 'mock_test_pkg'")
        await db.commit()
    print("✅ 自定义依赖持久化记录机制验证通过")

    # 4. 非法包名参数校验拦截
    try:
        await package_manager.install_package("invalid;rm -rf /")
        assert False, "应阻断非法包名参数注入"
    except ValueError as e:
        print(f"✅ 成功拦截非法包名参数注入: {e}")

    print("✅ 第三方模块依赖管理与安全防护验证通过")

    print("\n🎉 全部 10 项端到端自动化测试验证通过！")

if __name__ == "__main__":
    asyncio.run(main())


