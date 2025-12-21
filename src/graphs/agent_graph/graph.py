from __future__ import annotations

from typing import Dict, Any

from langgraph.graph import StateGraph, START, END

from src.core.settings import AppSettings
from src.graphs.agent_graph.state import AgentState
from src.graphs.agent_graph.nodes import (
    intent_analysis_node,
    vkdb_search_node,
    mysql_join_node,
    llm_summarize_node,
    simple_chat_node,
)

# 配置日志
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def build_agent_graph(settings: AppSettings):
    """
    构建Agent Graph：意图分析 + 串行工具流程
    
    流程：
    1. START → intent_analysis (意图分析)
    2. intent_analysis → 条件路由：
       - vkdb_search → vkdb_search → mysql_join → llm_summarize → END
       - simple_chat → simple_chat → END
    """
    
    g = StateGraph(AgentState)
    
    # 添加所有节点
    g.add_node("intent_analysis", intent_analysis_node(settings))
    g.add_node("vkdb_search", vkdb_search_node(settings))
    g.add_node("mysql_join", mysql_join_node(settings))
    g.add_node("llm_summarize", llm_summarize_node(settings))
    g.add_node("simple_chat", simple_chat_node(settings))
    
    # 设置入口
    g.add_edge(START, "intent_analysis")
    
    # 意图分析后的路由
    def route_after_intent(state: Dict[str, Any]) -> str:
        """根据意图分析结果路由"""
        import logging
        logger = logging.getLogger(__name__)
        
        # 直接访问字典
        intent = state.get("intent")
        logger.info(f"🔀 [路由决策] route_after_intent - 意图: {intent}")
        
        if intent == "vkdb_search":
            logger.info("➡️ [路由决策] route_after_intent - 路由到: vkdb_search")
            return "vkdb_search"
        elif intent == "simple_chat":
            logger.info("➡️ [路由决策] route_after_intent - 路由到: simple_chat")
            return "simple_chat"
        else:
            logger.warning(f"⚠️ [路由决策] route_after_intent - 未知意图，默认路由到: simple_chat")
            return "simple_chat"  # 默认走简单聊天
    
    g.add_conditional_edges(
        "intent_analysis",
        route_after_intent,
        {
            "vkdb_search": "vkdb_search",
            "simple_chat": "simple_chat"
        }
    )
    
    # VikingDB搜索后的路由：有结果则继续，无结果直接END
    def route_after_vkdb(state: Dict[str, Any]) -> str:
        import logging
        logger = logging.getLogger(__name__)
        if state.get("vkdb_no_result"):
            logger.info("➡️ [路由决策] route_after_vkdb - 无结果，直接结束")
            return "end"
        logger.info("➡️ [路由决策] route_after_vkdb - 有结果，进入mysql_join")
        return "mysql_join"
    
    g.add_conditional_edges(
        "vkdb_search",
        route_after_vkdb,
        {
            "mysql_join": "mysql_join",
            "end": END,
        }
    )
    g.add_edge("mysql_join", "llm_summarize")  # 有结果才会到达此处
    g.add_edge("llm_summarize", END)  # 结束
    
    # 简单聊天直接结束
    g.add_edge("simple_chat", END)
    
    return g.compile()
