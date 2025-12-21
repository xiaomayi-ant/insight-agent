from __future__ import annotations

from typing import Optional, Dict, Any

from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Agent状态：基于MessagesState，添加工具流程的中间状态"""
    
    # 意图分析结果
    intent: Optional[str] = None  # "simple_chat" | "vkdb_search"
    
    # VikingDB搜索相关（如果intent == "vkdb_search"）
    vkdb_query: Optional[str] = None  # 从用户输入提取的查询内容
    vkdb_influencer: Optional[str] = None  # 解析出的达人名（用于过滤）
    vkdb_response: Optional[Dict[str, Any]] = None  # VikingDB搜索结果
    vkdb_no_result: Optional[bool] = None  # 是否无结果
    
    # MySQL Join相关（自动执行，如果vkdb_response存在）
    mysql_join_result: Optional[Dict[str, Any]] = None  # MySQL Join分析结果
    
    # LLM汇总结果（最终输出）
    final_summary: Optional[str] = None
    
    # 错误处理
    error: Optional[str] = None
