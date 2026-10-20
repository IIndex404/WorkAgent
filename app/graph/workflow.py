"""
LangGraph 工作流：WorkAgent
==============================
流程图（ReAct 循环 + 人工审批）：

   START
    │
    ▼
  ┌───────┐   有 tool_calls    ┌───────┐
  │ agent │ ─────────────────▶ │ tools │
  │ 模型思考│ ◀───────────────── │ 执行工具│
  └───────┘    执行完回模型     └───────┘
    │
    │ 没有 tool_calls
    ▼
    END

关键设计：
  1. tools 节点里对"需要审批的工具"调用 interrupt() 中断，
     流程暂停，等待外部人工审批后再恢复执行
  2. 审批通过才真正执行敏感操作（发通知）
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.config import APPROVAL_TOOLS
from app.core.llm import get_llm
from app.core.memory import get_checkpointer
from app.graph.state import AgentState
from app.tools.calculator import calculator
from app.tools.handbook import search_employee_handbook
from app.tools.notice import _do_send, send_official_notice
from app.tools.weather import get_weather

# 全部工具清单（模型能看到的"说明书"）
ALL_TOOLS = [
    search_employee_handbook,
    calculator,
    get_weather,
    send_official_notice,
]

# Agent 系统提示词：强制"操作必须调工具"，防止模型偷懒直接编造完成
AGENT_SYSTEM_PROMPT = """你是 WorkAgent，负责企业内部的制度咨询与事务协助。
规则：
1. 回答公司制度问题：调用 search_employee_handbook 查询后回答。
2. 数学计算：调用 calculator。
3. 天气查询：调用 get_weather。
4. 发送通知/提醒/公告等操作：【必须】调用 send_official_notice，
   禁止在回复中直接输出通知内容来假装已发送——只有工具执行成功才算完成。
5. 不需要工具时，直接友好回答。"""

# 工具名 -> 实际执行函数（dispatch 表）
_TOOL_IMPL = {
    "search_employee_handbook": search_employee_handbook.func,
    "calculator": calculator.func,
    "get_weather": get_weather.func,
    "send_official_notice": _do_send,
}


def agent_node(state: AgentState) -> dict:
    """模型节点：把当前对话给模型，让它决定"直接回答"还是"调工具" """
    llm = get_llm(temperature=0.2).bind_tools(ALL_TOOLS)
    # 每次调用都带上系统提示词（规则），防止模型"偷懒不调工具"
    response = llm.invoke([SystemMessage(content=AGENT_SYSTEM_PROMPT), *state["messages"]])
    return {"messages": [response]}


def tools_node(state: AgentState) -> dict:
    """工具执行节点：执行模型请求的工具，敏感工具先走人工审批"""
    last = state["messages"][-1]
    tool_messages = []

    for tool_call in last.tool_calls:
        name = tool_call["name"]
        args = tool_call["args"]

        # ---- 需要审批的工具：中断，等人拍板 ----
        if name in APPROVAL_TOOLS:
            # interrupt 让流程"卡住"，把审批请求抛给外部（API 层）
            # 返回值 = 外部恢复时传入的人工决定
            decision = interrupt(
                {
                    "type": "approval",
                    "tool": name,
                    "args": args,
                    "message": f"是否批准执行：{args}",
                }
            )
            if decision != "approve":
                tool_messages.append(
                    ToolMessage(content="操作已被人工拒绝，请告知用户。", tool_call_id=tool_call["id"])
                )
                continue
            # 审批通过：真正执行
            print("    ✅ 人工审批通过，执行敏感操作……")

        # ---- 普通工具：直接执行 ----
        try:
            result = _TOOL_IMPL[name](**args)
        except Exception as e:
            result = f"工具执行出错：{e}"

        tool_messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

    return {"messages": tool_messages}


def route_after_agent(state: AgentState) -> str:
    """看模型回复：有 tool_calls -> 去工具节点；没有 -> 回答完毕"""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "end"


def build_graph():
    """构建并编译流程图（带检查点：多轮记忆 + 中断恢复）"""
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent", route_after_agent, {"tools": "tools", "end": END}
    )
    builder.add_edge("tools", "agent")  # 工具执行完回到模型（循环）

    # 企业版：检查点存 PostgreSQL（懒加载，第一次用才连库）
    return builder.compile(checkpointer=get_checkpointer())


# 懒加载的全局图：第一次调用 get_app_graph() 才构建（避免启动时连数据库）
_app_graph = None


def get_app_graph():
    """获取编译好的图（懒加载单例）"""
    global _app_graph
    if _app_graph is None:
        _app_graph = build_graph()
    return _app_graph
