"""
MiniCron 通用通知模块 (notify.py)
支持在各类自动化与签到脚本中直接调用 `from notify import send` 发送业务通知。
当脚本调用 send(title, content) 时，将内容规范格式化输出到标准输出，
MiniCron 会自动捕获并在任务执行完毕后将实际运行结果完整推送至 Telegram 等通知渠道。
"""
import json
from typing import Any

NOTIFY_START_MARKER = "__MINICRON_NOTIFY_START__"
NOTIFY_END_MARKER = "__MINICRON_NOTIFY_END__"

def send(title: Any = "", content: Any = "", *args, **kwargs) -> None:
    """
    通用通知发送函数 (支持直接向 MiniCron 传递自定义业务标题与正文)
    """
    title_str = str(title).strip() if title is not None else ""
    content_str = str(content).strip() if content is not None else ""
    
    # 构造结构化载荷，供 MiniCron 后台精准捕获自定义通知
    payload = {
        "title": title_str,
        "content": content_str
    }
    encoded = json.dumps(payload, ensure_ascii=False)
    print(f"\n{NOTIFY_START_MARKER}{encoded}{NOTIFY_END_MARKER}\n", flush=True)

if __name__ == "__main__":
    send("MiniCron 通知测试", "这是一条来自 notify.py 的本地测试消息")
