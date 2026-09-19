import html
import json
import logging
import asyncio
import re
from datetime import datetime
from typing import Optional, Tuple
import requests
from app.models.db import get_db
from app.core.config import settings

logger = logging.getLogger("minicron.notifier")

DEFAULT_NOTIFY_SETTINGS = {
    "telegram_enabled": False,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "proxy_url": "",
    "api_base_url": "https://api.telegram.org",
    "notify_policy": "ONLY_FAILURE"  # ONLY_FAILURE, ALWAYS, OFF
}

class NotifierService:
    async def get_settings(self) -> dict:
        """从 SQLite 获取通知与代理配置"""
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT value FROM system_configs WHERE key = 'notification_settings'"
            )
            row = await cursor.fetchone()
            if row and row["value"]:
                try:
                    loaded = json.loads(row["value"])
                    return {**DEFAULT_NOTIFY_SETTINGS, **loaded}
                except Exception:
                    pass
        return DEFAULT_NOTIFY_SETTINGS.copy()

    async def save_settings(self, cfg: dict) -> None:
        """持久化保存通知与代理配置"""
        data_json = json.dumps(cfg, ensure_ascii=False)
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO system_configs (key, value, updated_at)
                VALUES ('notification_settings', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (data_json,)
            )
            await db.commit()

    @staticmethod
    def _extract_clean_script_output(raw_log: str, max_chars: int = 2800, max_lines: int = 35) -> str:
        """
        清洗并提取脚本产生的实际输出内容：
        1. 剥离 MiniCron 内部运行头尾标识与环境变量注入提示
        2. 过滤 ANSI 终端颜色代码
        3. 保留尾部核心结果日志（签到脚本的核心结果通常在末尾）
        4. 截断超长内容以适应 Telegram 4096 字符限制
        """
        if not raw_log or not raw_log.strip():
            return ""

        # 过滤 ANSI 转义字符
        ansi_regex = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        cleaned_text = ansi_regex.sub('', raw_log)

        lines = cleaned_text.splitlines()
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            # 过滤 MiniCron 系统的包裹标记
            if stripped.startswith("=== [MiniCron]") or stripped.startswith("=== 脚本:") or stripped.startswith("=== 已注入环境变量:"):
                continue
            filtered_lines.append(line)

        # 去除首尾空行
        while filtered_lines and not filtered_lines[0].strip():
            filtered_lines.pop(0)
        while filtered_lines and not filtered_lines[-1].strip():
            filtered_lines.pop()

        if not filtered_lines:
            return ""

        truncated = False
        if len(filtered_lines) > max_lines:
            filtered_lines = filtered_lines[-max_lines:]
            truncated = True

        result = "\n".join(filtered_lines)
        if len(result) > max_chars:
            result = result[-max_chars:]
            truncated = True

        if truncated:
            return f"... (前文日志已折叠) ...\n{result.strip()}"
        return result.strip()

    @staticmethod
    def _send_telegram_sync(
        bot_token: str,
        chat_id: str,
        text: str,
        proxy_url: Optional[str] = None,
        api_base_url: Optional[str] = None
    ) -> Tuple[bool, str]:
        """同步发送 Telegram 消息（支持 HTTP/SOCKS5 代理和自定义 API Base URL）"""
        if not bot_token or not chat_id:
            return False, "Bot Token 或 Chat ID 未填写"

        base_url = (api_base_url or "https://api.telegram.org").strip().rstrip("/")
        if not base_url.startswith("http://") and not base_url.startswith("https://"):
            base_url = "https://" + base_url

        url = f"{base_url}/bot{bot_token}/sendMessage"

        proxies = None
        if proxy_url and proxy_url.strip():
            p = proxy_url.strip()
            proxies = {"http": p, "https": p}

        payload = {
            "chat_id": chat_id.strip(),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            resp = requests.post(url, json=payload, proxies=proxies, timeout=15)
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                return True, "发送成功"
            else:
                err_desc = data.get("description", resp.text)
                return False, f"Telegram API 拒绝: {err_desc} (状态码: {resp.status_code})"
        except requests.exceptions.ProxyError as e:
            return False, f"代理连接失败，请检查代理地址是否可用或端口是否正确: {e}"
        except requests.exceptions.ConnectTimeout:
            return False, "连接超时，在中国大陆服务器请务必配置有效代理或使用自建反代域名"
        except requests.exceptions.SSLError as e:
            return False, f"SSL 证书错误: {e}"
        except Exception as e:
            return False, f"网络请求异常: {str(e)}"

    async def test_notification(self, test_cfg: Optional[dict] = None) -> Tuple[bool, str]:
        """测试 Telegram 代理与通知连通性"""
        cfg = await self.get_settings()
        if test_cfg:
            for k, v in test_cfg.items():
                if v is not None and (v != "" or k in ["proxy_url", "api_base_url"]):
                    cfg[k] = v

        bot_token = cfg.get("telegram_bot_token", "").strip()
        chat_id = cfg.get("telegram_chat_id", "").strip()
        proxy_url = cfg.get("proxy_url", "").strip()
        api_base_url = cfg.get("api_base_url", "").strip() or "https://api.telegram.org"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        proxy_display = proxy_url if proxy_url else "直连（未配置代理）"

        msg = (
            f"<b>🕒 MiniCron 通知测试</b>\n\n"
            f"🎉 恭喜！Telegram 通知已成功连通！\n"
            f"🌐 <b>网络代理:</b> <code>{proxy_display}</code>\n"
            f"🔗 <b>API 节点:</b> <code>{api_base_url}</code>\n"
            f"⏰ <b>测试时间:</b> <code>{now_str}</code>"
        )

        return await asyncio.to_thread(
            self._send_telegram_sync,
            bot_token,
            chat_id,
            msg,
            proxy_url,
            api_base_url
        )

    async def notify_task_result(self, task: dict, execution: dict) -> None:
        """任务执行完毕后触发结果通知"""
        try:
            cfg = await self.get_settings()
            if not cfg.get("telegram_enabled"):
                return

            policy = cfg.get("notify_policy", "ONLY_FAILURE")
            status = execution.get("status", "FAILED")
            
            if policy == "OFF":
                return
            if policy == "ONLY_FAILURE" and status == "SUCCESS":
                return

            status_emoji = "✅ 成功" if status == "SUCCESS" else ("⏱️ 超时" if status == "TIMEOUT" else "❌ 失败")
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            task_name = task.get("name", "未命名任务")
            script_path = task.get("script_path", "")
            duration = execution.get("duration_seconds", 0.0)
            exit_code = execution.get("exit_code", -1)
            trigger_type = execution.get("trigger_type", "MANUAL")

            msg_parts = [
                f"<b>🕒 MiniCron 任务执行提醒</b>",
                f"",
                f"📌 <b>任务名称:</b> {html.escape(str(task_name))}",
                f"📄 <b>目标脚本:</b> <code>{html.escape(str(script_path))}</code>",
                f"📊 <b>执行结果:</b> <b>{status_emoji}</b>",
                f"⏱️ <b>执行耗时:</b> {duration:.2f}s",
                f"🔢 <b>退出代码:</b> <code>{exit_code}</code>",
                f"⚡ <b>触发方式:</b> {trigger_type}",
                f"📅 <b>完成时间:</b> <code>{now_str}</code>"
            ]

            # 提取脚本产生的实际输出内容 (无论是成功还是失败)
            log_path_rel = execution.get("log_path")
            script_output = ""
            if log_path_rel:
                log_file = settings.LOGS_DIR / log_path_rel
                if log_file.exists():
                    try:
                        raw_log = log_file.read_text(encoding="utf-8", errors="replace")
                        script_output = self._extract_clean_script_output(raw_log)
                    except Exception as e:
                        logger.warning(f"读取任务日志失败: {e}")

            if script_output:
                escaped_output = html.escape(script_output)
                if status == "SUCCESS":
                    msg_parts.append(f"\n📋 <b>脚本运行结果:</b>\n<pre>{escaped_output}</pre>")
                else:
                    msg_parts.append(f"\n⚠️ <b>异常日志输出摘要:</b>\n<pre>{escaped_output}</pre>")

            full_msg = "\n".join(msg_parts)

            bot_token = cfg.get("telegram_bot_token", "").strip()
            chat_id = cfg.get("telegram_chat_id", "").strip()
            proxy_url = cfg.get("proxy_url", "").strip()
            api_base_url = cfg.get("api_base_url", "").strip()

            await asyncio.to_thread(
                self._send_telegram_sync,
                bot_token,
                chat_id,
                full_msg,
                proxy_url,
                api_base_url
            )
        except Exception as e:
            logger.error(f"[Notifier] 发送 Telegram 任务通知异常: {e}")

notifier_service = NotifierService()
