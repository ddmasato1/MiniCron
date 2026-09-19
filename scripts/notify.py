"""
MiniCron 通用通知桥接模块 (notify.py)
兼容青龙面板及各类签到脚本中的 `from notify import send` 调用。
当脚本调用 send(title, content) 时，将内容规范格式化输出到标准输出，
MiniCron 会自动捕获并在任务执行完毕后将实际运行结果完整推送至 Telegram 等通知渠道。
"""
from typing import Any

def send(title: Any = "", content: Any = "", *args, **kwargs) -> None:
    """
    通用通知发送函数 (兼容青龙面板 notify.send 规范)
    """
    title_str = str(title).strip() if title is not None else ""
    content_str = str(content).strip() if content is not None else ""
    
    parts = []
    if title_str:
        parts.append(f"【{title_str}】")
    if content_str:
        parts.append(content_str)
        
    output_text = "\n".join(parts)
    print(f"\n📢 通知输出:\n{output_text}\n", flush=True)

if __name__ == "__main__":
    send("MiniCron 通知测试", "这是一条来自 notify.py 的本地测试消息")
