from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from src.core.settings import AppSettings


class ChatState(Dict[str, Any]):
    """聊天图的状态，使用字典格式以兼容LangGraph"""

    messages: List[BaseMessage]
    error: str | None = None


def _chat_node(settings: AppSettings):
    """聊天节点：使用LLM生成回复"""
    from langchain_community.chat_models import ChatTongyi  # pylint: disable=import-outside-toplevel

    llm = ChatTongyi(model=settings.qwen_model, temperature=settings.qwen_temperature)

    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        messages = state.get("messages", [])
        if not messages:
            return {"error": "No messages provided"}

        try:
            # 调用LLM生成回复
            response = llm.invoke(messages)
            # 将回复添加到消息列表
            return {"messages": messages + [response]}
        except Exception as e:
            return {"error": f"LLM invocation failed: {e}"}

    return _node


def build_chat_graph(settings: AppSettings):
    """
    构建通用聊天图
    
    流程：
    1. START -> chat_node (LLM生成回复)
    2. chat_node -> END
    """
    g = StateGraph(dict)
    g.add_node("chat", _chat_node(settings))
    g.add_edge(START, "chat")
    g.add_edge("chat", END)
    return g.compile()


def create_chat_messages(user_message: str, system_prompt: str | None = None) -> List[BaseMessage]:
    """
    创建聊天消息列表
    
    Args:
        user_message: 用户输入的消息
        system_prompt: 可选的系统提示词
    
    Returns:
        消息列表
    """
    messages: List[BaseMessage] = []
    
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    
    messages.append(HumanMessage(content=user_message))
    
    return messages
