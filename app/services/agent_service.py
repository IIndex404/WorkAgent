"""
Agent 服务：编排 LangGraph 流程 + 处理审批 + 确定性兜底
======================================================
对外提供两个操作：
  1. run()：发起一次智能体问答
     - 正常完成 -> 返回回答
     - 停在审批处 -> 返回"等待审批"及审批信息
  2. approve()：人工审批后恢复流程

三层设计（生产级，面试讲点）：
  ① 模型自主路径：ReAct 循环，模型自己决定调工具 → interrupt 审批
  ② 强制重试路径：模型"假装完成"（没调工具就回复）→ 注入指令重试
  ③ 确定性兜底：重试后模型仍不调工具 → 代码直接解析参数、进入审批
      （高优先级操作不赌模型自觉——这是企业 Agent 的稳定性保障）
"""

import json
import re
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command

from app.core.memory import get_session_config
from app.db import SessionLocal
from app.graph.workflow import get_app_graph
from app.models import ApprovalRecord
from app.tools.notice import _do_send

# 强信号关键词：出现这些词，基本可以确定用户要发通知/公告
_STRONG_NOTICE_KEYWORDS = ["通知", "公告"]
# 弱信号关键词：单独出现**不算数**（"提醒我算个数"也会命中"提醒"），
# 必须同时出现明确的收件人（"给张三发…"）才认定为通知请求
_WEAK_NOTICE_KEYWORDS = ["提醒", "发送", "告知", "转告"]

# 收件人模式："给张三发…" / "向李四发送…" / "给王五转告…"
# ★ 收件人部分用**非贪婪** `{1,10}?`：
#   贪婪写法会把"给张三发一条通知"解析成收件人="张三发一条"（见下方 _parse_notice_args 的注释）
_RECIPIENT_RE = re.compile(r"(?:给|向)([^\s，。：:]{1,10}?)(?:发|发送|通知|转告|告知|提醒)")

# 确定性兜底用：thread_id -> {"employee": ..., "content": ...}
_PENDING_APPROVALS: dict[str, dict] = {}

# 强制重试时注入的指令
_FORCE_TOOL_MSG = (
    "用户要求发送通知，但你还没有调用 send_official_notice 工具！"
    "【必须】调用该工具执行，禁止直接回复通知内容。请立即调用工具。"
)


def _log_approval(thread_id: str, tool: str, args: dict, status: str,
                  decided_by: str | None = None) -> None:
    """审批记录入库（审计：谁批的、何时批的、结果）"""
    try:
        with SessionLocal() as db:
            record = ApprovalRecord(
                thread_id=thread_id,
                tool=tool,
                args_json=json.dumps(args, ensure_ascii=False),
                status=status,
                decided_by=decided_by,
                decided_at=datetime.utcnow() if status != "pending" else None,
            )
            db.add(record)
            db.commit()
    except Exception as e:
        print(f"  ⚠️ 审批记录写入失败: {e}")


def _looks_like_notice_request(message: str) -> bool:
    """用户消息是否明显在要求"发通知"类操作。

    ★ 这里修过一个真 bug（已实测复现并验证修复）：
      旧版只用一个宽松关键词表 ["通知","提醒","公告","发送","告知","转告"]，
      导致"提醒我一下，3500乘以12等于多少？"也被判成通知请求。
      接着模型不会去调通知工具 → 强制重试 2 次仍不调 → 走确定性兜底 →
      弹出一个荒谬的审批："是否批准给员工发送通知：3500乘以12等于多少？？"

      修法：信号分级
        - 强信号（通知/公告）：出现即认定
        - 弱信号（提醒/发送/告知/转告）：必须**同时**出现明确收件人（"给X发…"）

      为什么收窄判断是安全的：
        真正的通知请求即使这里没识别出来，模型自己调用工具后会命中
        tools_node 里的 interrupt，由"非通知类"正常路径返回审批，
        功能不受影响——三层保障只是"模型不听话时"的额外保险。
    """
    if any(kw in message for kw in _STRONG_NOTICE_KEYWORDS):
        return True
    if any(kw in message for kw in _WEAK_NOTICE_KEYWORDS):
        return _RECIPIENT_RE.search(message) is not None
    return False


def _parse_notice_args(message: str) -> tuple[str, str]:
    """从用户消息里解析出（员工名, 通知内容）。

    教学版用简单规则解析，生产版应该用结构化输出（with_structured_output）提取。

    ★ 这里修过一个真 bug：收件人正则原本是**贪婪**的 `{1,10}`，
      导致"给张三发一条通知：明天上午10点开周会"被解析成
      收件人 = "张三发一条"（贪婪地把"发一条"也吃进姓名里）。
      这个错误姓名会直接显示在审批卡片上、并被 `_do_send` 拿去发送——
      也就是**通知会发给一个不存在的收件人**。
      修法：改成非贪婪 `{1,10}?`，让它尽早匹配到后面的动词（发/发送/通知）。
    """
    # 员工名："给张三发通知" / "向李四发送…"（与 _looks_like_notice_request 共用同一个正则）
    m = _RECIPIENT_RE.search(message)
    employee = m.group(1) if m else "员工"
    # 内容："通知：XXX" / "通知XXX" / "：XXX"
    m2 = re.search(r"[：:，,]\s*(.+)$", message)
    if not m2:
        m2 = re.search(r"(?:通知|告知)([^\s]{1,50})$", message)
    content = m2.group(1).strip() if m2 else message
    return employee, content


def _interrupt_info(snapshot) -> tuple[str, dict]:
    """从中断快照里取出（工具名, 参数）——用于审批审计记录"""
    tasks = getattr(snapshot, "tasks", [])
    if tasks and tasks[0].interrupts:
        value = tasks[0].interrupts[0].value or {}
        return value.get("tool", "unknown"), value.get("args", {})
    return "unknown", {}


def _approval_response(session_id: str, snapshot) -> dict:
    """把中断信息整理成响应"""
    interrupt_value = None
    tasks = snapshot.tasks
    if tasks:
        interrupt_value = tasks[0].interrupts[0].value if tasks[0].interrupts else None
    return {
        "status": "awaiting_approval",
        "session_id": session_id,
        "approval": interrupt_value,
    }


def run(message: str, session_id: str) -> dict:
    """发起智能体问答"""
    config = get_session_config(session_id)
    graph = get_app_graph()  # 懒加载图（第一次用才连数据库）

    # ---- 通知类请求：模型自主 → 强制重试 → 确定性兜底 ----
    if _looks_like_notice_request(message):
        # ① 模型自主路径：ReAct，模型自己调用工具
        result = graph.invoke(
            {"messages": [HumanMessage(content=message)]}, config=config
        )
        snapshot = graph.get_state(config)
        if snapshot.next:
            # ★ 记录"待审批"审计（模型自主调工具的中断路径之前漏了）
            tool, args = _interrupt_info(snapshot)
            _log_approval(session_id, tool, args, "pending")
            return _approval_response(session_id, snapshot)

        # ② 强制重试：模型没调工具就回复（假装完成）→ 注入指令
        for _ in range(2):
            last_msg = result["messages"][-1]
            if isinstance(last_msg, AIMessage) and not last_msg.tool_calls:
                print("  ⚠️ 模型未调用工具，注入强制指令重试……")
                result = graph.invoke(
                    {"messages": [SystemMessage(content=_FORCE_TOOL_MSG)]}, config=config
                )
                snapshot = graph.get_state(config)
                if snapshot.next:
                    tool, args = _interrupt_info(snapshot)
                    _log_approval(session_id, tool, args, "pending")
                    return _approval_response(session_id, snapshot)
            else:
                break

        # ③ 确定性兜底：模型始终不调工具 → 代码直接解析参数进入审批
        print("  ⚠️ 模型始终不调工具，走确定性审批兜底（不赌模型自觉）……")
        employee, content = _parse_notice_args(message)
        args = {"employee": employee, "content": content}
        _PENDING_APPROVALS[session_id] = args
        _log_approval(session_id, "send_official_notice", args, "pending")
        return {
            "status": "awaiting_approval",
            "session_id": session_id,
            "approval": {
                "type": "approval",
                "tool": "send_official_notice",
                "args": args,
                "message": f"是否批准给{employee}发送通知：{content}？",
            },
        }

    # ---- 非通知类：正常走 Agent（ReAct 循环） ----
    result = graph.invoke(
        {"messages": [HumanMessage(content=message)]}, config=config
    )
    snapshot = graph.get_state(config)
    if snapshot.next:  # 停在审批（其他敏感工具）
        return _approval_response(session_id, snapshot)

    # 正常完成：取模型最终回答
    reply = ""
    for msg in result["messages"]:
        if isinstance(msg, HumanMessage):
            continue
        reply = msg.content  # 取最后一条非用户消息
    return {"status": "done", "reply": reply, "session_id": session_id}


def approve(thread_id: str, decision: bool, decided_by: str = "admin") -> dict:
    """人工审批：优先处理确定性兜底的待审批项，否则恢复图流程"""
    # ---- 确定性兜底路径：直接执行，不依赖图 ----
    pending = _PENDING_APPROVALS.pop(thread_id, None)
    if pending:
        if decision:
            result = _do_send(pending["employee"], pending["content"])
            _log_approval(thread_id, "send_official_notice", pending, "approved", decided_by)
            return {"status": "done", "reply": result, "session_id": thread_id}
        _log_approval(thread_id, "send_official_notice", pending, "rejected", decided_by)
        return {"status": "done", "reply": "操作已被人工拒绝，未发送。", "session_id": thread_id}

    # ---- 正常图路径：Command(resume=...) 恢复中断 ----
    config = get_session_config(thread_id)
    resume_value = "approve" if decision else "reject"
    graph = get_app_graph()
    # ★ 恢复前先读中断信息，用于审计记录（谁批的、哪个工具、结果）
    tool, args = _interrupt_info(graph.get_state(config))
    result = graph.invoke(Command(resume=resume_value), config=config)
    _log_approval(thread_id, tool, args, "approved" if decision else "rejected", decided_by)

    reply = ""
    for msg in result["messages"]:
        if isinstance(msg, HumanMessage):
            continue
        reply = msg.content
    return {"status": "done", "reply": reply, "session_id": thread_id}
