"""
Agent 状态定义
==============
State 是节点间共享的"白板"。
messages 用 Annotated + add_messages：节点往里面加内容时是"追加"而不是"覆盖"。
"""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """智能体共享状态"""
    messages: Annotated[list, add_messages]   # 对话历史（自动追加合并）
