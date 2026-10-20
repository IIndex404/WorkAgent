"""
通知工具（需要人工审批）
========================
这个工具执行"有影响"的操作：向员工发送官方通知。
Agent 一旦决定调用它，流程会在执行前中断，等人工审批。

注意：真正的"发送"动作在审批通过后才执行（见 graph/workflow.py）。
"""

from langchain_core.tools import tool

# 审批通过后真正执行的动作
def _do_send(employee: str, content: str) -> str:
    """真实项目里这里调用消息系统 API 发送通知"""
    print(f"    📤 [已执行] 向 {employee} 发送通知：{content}")
    return f"通知已发送给{employee}"


@tool
def send_official_notice(employee: str, content: str) -> str:
    """向指定员工发送一条官方通知。
    当用户要求发送通知、提醒、公告、会议提醒、处罚告知等内容时，【必须】调用本工具执行，
    禁止直接在回复里输出通知内容来假装完成——通知只有通过本工具发送才算真正发出。
    参数 employee 是员工姓名，content 是通知正文。
    注意：这是有影响力的操作，执行前需要人工审批！"""
    # 这个函数本身不会真正发送——真正的发送在审批通过后执行
    # 这里只返回"准备发送的内容"，让流程中断等待审批
    return f"待审批的通知：给{employee}发送『{content}』"
