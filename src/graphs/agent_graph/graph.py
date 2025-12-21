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
    intent_structurize_node,
    data_aggregate_node,
    llm_analyze_node,
)

# 日志配置已在 src.api.main 中统一配置


def build_agent_graph(settings: AppSettings):
    """
    构建Agent Graph：意图分析 + 串行工具流程
    
    流程：
    1. START → intent_analysis (意图分析)
    2. intent_analysis → 条件路由：
       - vkdb_search → vkdb_search → intent_structurize → mysql_join → data_aggregate → llm_analyze → llm_summarize → END
       - simple_chat → simple_chat → END
    
    新流程（如果启用意图结构化）：
    vkdb_search → intent_structurize → mysql_join → data_aggregate → llm_analyze → llm_summarize
    
    降级流程（如果意图结构化失败或禁用）：
    vkdb_search → mysql_join → llm_summarize
    """
    
    g = StateGraph(AgentState)
    
    # 添加所有节点
    g.add_node("intent_analysis", intent_analysis_node(settings))
    g.add_node("vkdb_search", vkdb_search_node(settings))
    g.add_node("intent_structurize", intent_structurize_node(settings))
    g.add_node("mysql_join", mysql_join_node(settings))
    g.add_node("data_aggregate", data_aggregate_node(settings))
    g.add_node("llm_analyze", llm_analyze_node(settings))
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
            "mysql_join": "intent_structurize",  # 有结果先进入意图结构化
            "end": END,
        }
    )
    
    # 意图结构化后的路由：如果启用且成功，继续新流程；否则跳过到 mysql_join
    def route_after_structurize(state: Dict[str, Any]) -> str:
        import logging
        logger = logging.getLogger(__name__)
        
        if not settings.intent_structurize_enabled:
            logger.info("➡️ [路由决策] route_after_structurize - 意图结构化已禁用，跳过到 mysql_join")
            return "mysql_join"
        
        structured_intents = state.get("structured_intents")
        if not structured_intents or len(structured_intents) == 0:
            logger.warning("⚠️ [路由决策] route_after_structurize - 结构化失败，降级到旧流程")
            return "mysql_join"
        
        # 检查成功率
        success_count = sum(1 for item in structured_intents if item.get("success", False))
        success_rate = success_count / len(structured_intents) if structured_intents else 0
        
        if success_rate < 0.5:  # 成功率低于50%，降级
            logger.warning(f"⚠️ [路由决策] route_after_structurize - 成功率 {success_rate:.1%} 过低，降级到旧流程")
            return "mysql_join"
        
        logger.info(f"✅ [路由决策] route_after_structurize - 结构化成功 ({success_rate:.1%})，继续新流程")
        return "mysql_join"  # 继续到 mysql_join
    
    g.add_conditional_edges(
        "intent_structurize",
        route_after_structurize,
        {
            "mysql_join": "mysql_join",
        }
    )
    
    # MySQL Join 后的路由：如果有聚合数据，走新流程；否则直接汇总
    def route_after_mysql(state: Dict[str, Any]) -> str:
        import logging
        logger = logging.getLogger(__name__)
        
        structured_intents = state.get("structured_intents")
        if structured_intents and len(structured_intents) > 0:
            logger.info("➡️ [路由决策] route_after_mysql - 有结构化数据，进入数据聚合")
            return "data_aggregate"
        else:
            logger.info("➡️ [路由决策] route_after_mysql - 无结构化数据，直接汇总")
            return "llm_summarize"
    
    g.add_conditional_edges(
        "mysql_join",
        route_after_mysql,
        {
            "data_aggregate": "data_aggregate",
            "llm_summarize": "llm_summarize",
        }
    )
    
    # 数据聚合后进入 LLM 分析
    g.add_edge("data_aggregate", "llm_analyze")
    
    # LLM 分析后进入汇总
    g.add_edge("llm_analyze", "llm_summarize")
    
    # 汇总后结束
    g.add_edge("llm_summarize", END)  # 结束
    
    # 简单聊天直接结束
    g.add_edge("simple_chat", END)
    
    return g.compile()
