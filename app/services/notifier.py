import html
import json
import logging
import asyncio
import re
from datetime import datetime
from typing import Optional, Tuple, List, Dict
import requests
from app.models.db import get_db
from app.core.config import settings

logger = logging.getLogger("minicron.notifier")

NOTIFY_START_MARKER = "__MINICRON_NOTIFY_START__"
NOTIFY_END_MARKER = "__MINICRON_NOTIFY_END__"

DEFAULT_NOTIFY_SETTINGS = {
    "telegram_enabled": False,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "proxy_url": "",
    "api_base_url": "https://api.telegram.org",
    "notify_policy": "CUSTOM_ONLY",  # CUSTOM_ONLY (仅脚本通知+失败兜底), ONLY_FAILURE (仅失败), ALWAYS (全部), OFF (关闭)
    
    # 系统安全通知配置
    "security_notify_enabled": True,
    "security_chat_id": "",
    "notify_on_login_success": False,
    "notify_on_login_failure": True,
    "notify_on_password_change": True,
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
    def _extract_custom_notifications(raw_log: str) -> List[Dict[str, str]]:
        """
        从脚本运行日志中提取所有结构化自定义通知（支持 notify.send 协议）
        标记格式：__MINICRON_NOTIFY_START__{"title": "...", "content": "..."}__MINICRON_NOTIFY_END__
        """
        if not raw_log or NOTIFY_START_MARKER not in raw_log:
            return []

        pattern = re.compile(
            re.escape(NOTIFY_START_MARKER) + r"(.*?)" + re.escape(NOTIFY_END_MARKER),
            re.DOTALL
        )
        notifications = []
        for match in pattern.finditer(raw_log):
            content_str = match.group(1).strip()
            try:
                data = json.loads(content_str)
                if isinstance(data, dict) and (data.get("title") or data.get("content")):
                    notifications.append({
                        "title": str(data.get("title", "")).strip(),
                        "content": str(data.get("content", "")).strip()
                    })
            except Exception as e:
                logger.warning(f"解析自定义通知 JSON 标记失败: {e}")
        return notifications

    @staticmethod
    def _extract_clean_script_output(raw_log: str, max_chars: int = 2800, max_lines: int = 35) -> str:
        """
        清洗并提取脚本产生的实际输出内容：
        1. 剥离自定义通知标记 __MINICRON_NOTIFY_START__ ... __MINICRON_NOTIFY_END__
        2. 剥离 MiniCron 内部运行头尾标识与环境变量注入提示
        3. 过滤 ANSI 终端颜色代码
        4. 截断超长内容以适应 Telegram 4096 字符限制
        """
        if not raw_log or not raw_log.strip():
            return ""

        # 先剥离自定义通知结构化标记
        cleaned = re.sub(
            re.escape(NOTIFY_START_MARKER) + r".*?" + re.escape(NOTIFY_END_MARKER),
            "",
            raw_log,
            flags=re.DOTALL
        )

        # 过滤 ANSI 转义字符
        ansi_regex = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        cleaned_text = ansi_regex.sub('', cleaned)

        lines = cleaned_text.splitlines()
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            # 过滤 MiniCron 系统的包裹标记
            if (
                stripped.startswith("=== [MiniCron]")
                or stripped.startswith("=== 脚本:")
                or stripped.startswith("=== 已注入环境变量:")
            ):
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
        """即时测试 Telegram 代理与通知连通性（支持测试任务通道或安全告警通道）"""
        cfg = await self.get_settings()
        if test_cfg:
            for k, v in test_cfg.items():
                if v is not None and (v != "" or k in ["proxy_url", "api_base_url"]):
                    cfg[k] = v

        bot_token = cfg.get("telegram_bot_token", "").strip()
        proxy_url = cfg.get("proxy_url", "").strip()
        api_base_url = cfg.get("api_base_url", "").strip() or "https://api.telegram.org"
        test_type = test_cfg.get("test_type", "task") if test_cfg else "task"

        if test_type == "security":
            chat_id = (cfg.get("security_chat_id", "") or cfg.get("telegram_chat_id", "")).strip()
            channel_name = "系统安全告警通道"
        else:
            chat_id = cfg.get("telegram_chat_id", "").strip()
            channel_name = "定时任务通知通道"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        proxy_display = proxy_url if proxy_url else "直连（未配置代理）"

        msg = (
            f"<b>🕒 MiniCron 通知测试</b>\n\n"
            f"🎉 恭喜！Telegram 通知已成功连通！\n"
            f"🎯 <b>测试目标:</b> <code>{channel_name}</code>\n"
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

    async def notify_security_event(self, event_type: str, details: dict) -> None:
        """
        触发系统安全关键事件告警（登录成功/失败、修改密码）
        """
        try:
            cfg = await self.get_settings()
            if not cfg.get("telegram_enabled") or not cfg.get("security_notify_enabled", True):
                return

            # 校验细分事件开关
            if event_type == "LOGIN_SUCCESS" and not cfg.get("notify_on_login_success", False):
                return
            if event_type == "LOGIN_FAILURE" and not cfg.get("notify_on_login_failure", True):
                return
            if event_type == "PASSWORD_CHANGE" and not cfg.get("notify_on_password_change", True):
                return

            bot_token = cfg.get("telegram_bot_token", "").strip()
            # 优先使用安全专属 Chat ID，未配置则回退到主 Chat ID
            chat_id = (cfg.get("security_chat_id", "") or cfg.get("telegram_chat_id", "")).strip()
            if not bot_token or not chat_id:
                return

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            username = html.escape(str(details.get("username", "admin")))
            client_ip = html.escape(str(details.get("ip", "未知 IP")))

            if event_type == "LOGIN_SUCCESS":
                msg = (
                    f"🛡️ <b>MiniCron 安全提醒</b>\n\n"
                    f"• <b>事件</b>: 🔑 管理员登录成功\n"
                    f"• <b>账号</b>: <code>{username}</code>\n"
                    f"• <b>IP 地址</b>: <code>{client_ip}</code>\n"
                    f"• <b>时间</b>: <code>{now_str}</code>"
                )
            elif event_type == "LOGIN_FAILURE":
                msg = (
                    f"🛡️ <b>MiniCron 安全告警</b>\n\n"
                    f"• <b>事件</b>: ⚠️ 管理员登录失败 (密码错误)\n"
                    f"• <b>账号</b>: <code>{username}</code>\n"
                    f"• <b>IP 地址</b>: <code>{client_ip}</code>\n"
                    f"• <b>时间</b>: <code>{now_str}</code>\n"
                    f"• <b>提示</b>: 若非本人操作，请警惕暴力破解风险！"
                )
            elif event_type == "PASSWORD_CHANGE":
                msg = (
                    f"🛡️ <b>MiniCron 安全提醒</b>\n\n"
                    f"• <b>事件</b>: 🔐 管理员密码已修改\n"
                    f"• <b>账号</b>: <code>{username}</code>\n"
                    f"• <b>IP 地址</b>: <code>{client_ip}</code>\n"
                    f"• <b>时间</b>: <code>{now_str}</code>\n"
                    f"• <b>提示</b>: 管理员密码已更新并持久化生效。"
                )
            else:
                return

            proxy_url = cfg.get("proxy_url", "").strip()
            api_base_url = cfg.get("api_base_url", "").strip()

            await asyncio.to_thread(
                self._send_telegram_sync,
                bot_token,
                chat_id,
                msg,
                proxy_url,
                api_base_url
            )
        except Exception as e:
            logger.error(f"[Notifier] 发送系统安全通知异常: {e}")

    async def notify_task_result(self, task: dict, execution: dict) -> None:
        """
        任务执行完毕后触发结果通知：
        1. 优先提取脚本通过 notify.send() 发送的自定义通知（纯净业务模式）；
        2. 若未自定义通知且任务失败，则发送精简故障告警卡片；
        3. 若 policy 为 ALWAYS，且未自定义通知且任务成功，发送精简完成提醒。
        """
        try:
            cfg = await self.get_settings()
            if not cfg.get("telegram_enabled"):
                return

            policy = cfg.get("notify_policy", "CUSTOM_ONLY")
            if policy == "OFF":
                return

            bot_token = cfg.get("telegram_bot_token", "").strip()
            chat_id = cfg.get("telegram_chat_id", "").strip()
            if not bot_token or not chat_id:
                return

            proxy_url = cfg.get("proxy_url", "").strip()
            api_base_url = cfg.get("api_base_url", "").strip()

            status = execution.get("status", "FAILED")
            task_name = task.get("name", "未命名任务")
            script_path = task.get("script_path", "")
            duration = execution.get("duration_seconds", 0.0)
            exit_code = execution.get("exit_code", -1)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 读取任务运行日志
            raw_log = ""
            log_path_rel = execution.get("log_path")
            if log_path_rel:
                log_file = settings.LOGS_DIR / log_path_rel
                if log_file.exists():
                    try:
                        raw_log = log_file.read_text(encoding="utf-8", errors="replace")
                    except Exception as e:
                        logger.warning(f"读取任务日志失败: {e}")

            # 1. 尝试提取脚本主动发出的自定义通知
            custom_notifs = self._extract_custom_notifications(raw_log)

            if custom_notifs:
                # 策略控制：如果配置为 ONLY_FAILURE 且任务成功，则跳过
                if policy == "ONLY_FAILURE" and status == "SUCCESS":
                    return

                # 发送纯粹直观的自定义通知
                for notif in custom_notifs:
                    title = notif.get("title", "").strip()
                    content = notif.get("content", "").strip()
                    
                    parts = []
                    if title:
                        parts.append(f"<b>{html.escape(title)}</b>")
                    if content:
                        parts.append(html.escape(content))
                    
                    # 尾部附带任务名与时间戳小字
                    parts.append(f"<i>🕒 {now_str} · {html.escape(str(task_name))}</i>")
                    
                    msg = "\n\n".join(parts)
                    await asyncio.to_thread(
                        self._send_telegram_sync,
                        bot_token,
                        chat_id,
                        msg,
                        proxy_url,
                        api_base_url
                    )
                return

            # 2. 脚本未主动发送通知时的系统处理
            if status != "SUCCESS":
                # 任务失败/超时：只要不是 OFF，均发送精简故障告警 (CUSTOM_ONLY, ONLY_FAILURE, ALWAYS 均告警)
                clean_output = self._extract_clean_script_output(raw_log)
                msg_parts = [
                    f"⚠️ <b>任务执行失败告警</b>\n",
                    f"📌 <b>任务名称:</b> {html.escape(str(task_name))}",
                    f"📄 <b>目标脚本:</b> <code>{html.escape(str(script_path))}</code>",
                    f"⏱️ <b>执行耗时:</b> {duration:.2f}s (退出代码: <code>{exit_code}</code>)",
                    f"📅 <b>失败时间:</b> <code>{now_str}</code>"
                ]
                if clean_output:
                    msg_parts.append(f"\n❌ <b>异常输出摘要:</b>\n<pre>{html.escape(clean_output)}</pre>")

                full_msg = "\n".join(msg_parts)
                await asyncio.to_thread(
                    self._send_telegram_sync,
                    bot_token,
                    chat_id,
                    full_msg,
                    proxy_url,
                    api_base_url
                )
            elif policy == "ALWAYS":
                # 任务成功且策略为 ALWAYS：发送精炼完成卡片
                clean_output = self._extract_clean_script_output(raw_log)
                msg_parts = [
                    f"✅ <b>任务执行完成</b>\n",
                    f"📌 <b>任务名称:</b> {html.escape(str(task_name))}",
                    f"📄 <b>目标脚本:</b> <code>{html.escape(str(script_path))}</code>",
                    f"⏱️ <b>执行耗时:</b> {duration:.2f}s",
                    f"📅 <b>完成时间:</b> <code>{now_str}</code>"
                ]
                if clean_output:
                    msg_parts.append(f"\n📋 <b>运行输出:</b>\n<pre>{html.escape(clean_output)}</pre>")

                full_msg = "\n".join(msg_parts)
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

