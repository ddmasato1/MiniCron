import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Optional, Set, AsyncGenerator
from app.models.db import get_db
from app.models.schemas import PackageItem

logger = logging.getLogger("minicron.packages")

# 核心系统受保护依赖清单（全小写），严禁在界面被卸载
CORE_PACKAGES: Set[str] = {
    "fastapi", "uvicorn", "apscheduler", "aiosqlite", "pydantic",
    "pydantic-settings", "pydantic_core", "python-multipart", "python-dotenv",
    "requests", "pip", "setuptools", "wheel", "croniter", "starlette",
    "anyio", "typing_extensions", "typing-inspection", "tzlocal", "click",
    "idna", "certifi", "charset-normalizer", "urllib3", "h11", "httptools"
}

PACKAGE_NAME_REGEX = re.compile(r'^[a-zA-Z0-9_\-\.><=~!@/]+$')

class PackageManager:
    def __init__(self):
        self._is_installing: bool = False
        self._current_install_target: Optional[str] = None
        self._log_subscribers: List[asyncio.Queue] = []

    def is_installing(self) -> bool:
        return self._is_installing

    def get_current_install_target(self) -> Optional[str]:
        return self._current_install_target

    async def subscribe_log(self) -> AsyncGenerator[str, None]:
        q = asyncio.Queue()
        self._log_subscribers.append(q)
        try:
            while True:
                line = await q.get()
                if line is None:
                    break
                yield line
        finally:
            if q in self._log_subscribers:
                self._log_subscribers.remove(q)

    async def _broadcast_log(self, line: str):
        for q in list(self._log_subscribers):
            await q.put(line)

    async def _close_log_stream(self):
        for q in list(self._log_subscribers):
            await q.put(None)

    async def list_packages(self) -> List[Dict]:
        """获取当前环境所有已安装的 Python 包并标注系统核心与自定义状态"""
        # 1. 查询当前 pip list
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pip", "list", "--format=json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"获取 pip 列表失败: {err_msg}")

        try:
            pip_items = json.loads(stdout.decode("utf-8", errors="replace"))
        except Exception:
            pip_items = []

        # 2. 查询 SQLite custom_packages
        custom_pkgs_map: Dict[str, str] = {}
        try:
            async with get_db() as db:
                cursor = await db.execute("SELECT name, version FROM custom_packages")
                rows = await cursor.fetchall()
                for r in rows:
                    custom_pkgs_map[r["name"].lower()] = r["version"] or ""
        except Exception as e:
            logger.warning(f"读取 custom_packages 失败: {e}")

        # 3. 组装结果
        result = []
        for item in pip_items:
            pkg_name = item.get("name", "")
            pkg_ver = item.get("version", "")
            pkg_lower = pkg_name.lower()
            is_core = pkg_lower in CORE_PACKAGES
            is_custom = pkg_lower in custom_pkgs_map
            result.append({
                "name": pkg_name,
                "version": pkg_ver,
                "is_core": is_core,
                "is_custom": is_custom
            })

        # 按自定义包优先、随后按字母排序
        result.sort(key=lambda x: (not x["is_custom"], x["name"].lower()))
        return result

    async def install_package(
        self,
        raw_name: str,
        mirror: str = "https://pypi.tuna.tsinghua.edu.cn/simple"
    ) -> Dict:
        """在线安装 Python 模块并实时流式输出日志"""
        pkg_name = raw_name.strip()
        if not pkg_name:
            raise ValueError("模块名称不能为空")
        if not PACKAGE_NAME_REGEX.match(pkg_name):
            raise ValueError(f"模块名称 '{pkg_name}' 包含非法字符")

        if self._is_installing:
            raise RuntimeError(f"当前已有模块正在安装中 ({self._current_install_target})，请等待完成")

        self._is_installing = True
        self._current_install_target = pkg_name

        # 构造 pip 命令
        cmd = [
            sys.executable, "-m", "pip", "install", pkg_name,
            "-i", mirror,
            "--no-cache-dir"
        ]

        start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = f"=== [MiniCron 包管理器] 开始安装模块: {pkg_name} ===\n" \
                 f"=== 镜像源: {mirror} | 启动时间: {start_time} ===\n\n"
        await self._broadcast_log(header)

        success = False
        full_logs = [header]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )

            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace")
                full_logs.append(line)
                await self._broadcast_log(line)

            await process.wait()
            success = (process.returncode == 0)

            footer = f"\n=== 安装结束，状态: {'成功' if success else '失败 (退出码: ' + str(process.returncode) + ')'} ===\n"
            full_logs.append(footer)
            await self._broadcast_log(footer)

            if success:
                # 解析提取基础名称（去掉 == 等约束）
                base_name = re.split(r'[=><!~]', pkg_name)[0].strip()
                installed_version = await self._find_installed_version(base_name)

                # 持久化记录到 SQLite
                async with get_db() as db:
                    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    await db.execute(
                        """
                        INSERT INTO custom_packages (name, version, installed_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(name) DO UPDATE SET version = excluded.version, installed_at = excluded.installed_at
                        """,
                        (base_name, installed_version, now_iso)
                    )
                    await db.commit()

                return {
                    "success": True,
                    "name": base_name,
                    "version": installed_version,
                    "message": f"模块 '{base_name}' 安装成功 (版本: {installed_version})"
                }
            else:
                return {
                    "success": False,
                    "name": pkg_name,
                    "message": f"安装失败，退出码: {process.returncode}"
                }

        finally:
            self._is_installing = False
            self._current_install_target = None
            await self._close_log_stream()

    async def _find_installed_version(self, base_name: str) -> str:
        try:
            packages = await self.list_packages()
            for p in packages:
                if p["name"].lower() == base_name.lower():
                    return p["version"]
        except Exception:
            pass
        return "latest"

    async def uninstall_package(self, raw_name: str) -> Dict:
        """卸载自定义安装的 Python 模块"""
        pkg_name = raw_name.strip()
        if not pkg_name:
            raise ValueError("模块名称不能为空")

        pkg_lower = pkg_name.lower()
        if pkg_lower in CORE_PACKAGES:
            raise ValueError(f"安全保护拦截：模块 '{pkg_name}' 属于 MiniCron 系统核心运行依赖，严禁卸载")

        cmd = [sys.executable, "-m", "pip", "uninstall", "-y", pkg_name]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"卸载模块失败: {err_msg}")

        # 从 SQLite 移除
        async with get_db() as db:
            await db.execute("DELETE FROM custom_packages WHERE LOWER(name) = ?", (pkg_lower,))
            await db.commit()

        return {"success": True, "message": f"模块 '{pkg_name}' 已成功卸载"}

    async def restore_custom_packages(self):
        """应用启动时自动检测并恢复缺失的自定义依赖（解决 Docker 容器销毁重建后的包丢失问题）"""
        try:
            async with get_db() as db:
                cursor = await db.execute("SELECT name, version FROM custom_packages")
                rows = await cursor.fetchall()
                if not rows:
                    return

            installed_packages = await self.list_packages()
            installed_names = {p["name"].lower() for p in installed_packages}

            for row in rows:
                name = row["name"]
                version = row["version"]
                if name.lower() not in installed_names:
                    logger.info(f"[PackageManager] 发现缺失的自定义依赖: {name} (期望版本: {version})，正在自动补全安装...")
                    install_target = f"{name}=={version}" if version and version != "latest" else name
                    try:
                        await self.install_package(install_target)
                        logger.info(f"[PackageManager] ✅ 自定义依赖 {name} 自动补全安装完成！")
                    except Exception as e:
                        logger.error(f"[PackageManager] ❌ 自动恢复安装依赖 {name} 失败: {e}")
        except Exception as e:
            logger.warning(f"[PackageManager] 检查恢复依赖时发生异常: {e}")

package_manager = PackageManager()
