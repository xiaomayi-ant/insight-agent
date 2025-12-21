from __future__ import annotations

import json
from typing import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage

from src.core.settings import load_settings
from src.graphs.agent_graph.graph import build_agent_graph
from src.graphs.agent_graph.state import AgentState


async def agent_stream(
    user_message: str,
    system_prompt: str | None = None
) -> AsyncIterator[str]:
    """
    Agent流式服务
    
    使用Agent Graph处理用户请求，通过astream_events捕获流式事件
    
    Args:
        user_message: 用户输入的自然语言消息
        system_prompt: 可选的系统提示词
    
    Yields:
        SSE格式的字符串（data: {...}\n\n）
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🚀 [服务启动] agent_stream - 收到请求: {user_message[:50]}...")
    
    settings = load_settings()
    graph = build_agent_graph(settings)
    
    # 构建初始消息
    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=user_message))
    
    # 初始状态（直接使用字典格式）
    initial_state = {
        "messages": messages,
        "intent": None,
        "vkdb_query": None,
        "vkdb_influencer": None,
        "vkdb_response": None,
        "vkdb_no_result": None,
        "mysql_join_result": None,
        "final_summary": None,
        "error": None,
    }
    
    try:
        # 发送状态消息
        status_payload = json.dumps(
            {"type": "status", "content": "正在分析您的请求..."},
            ensure_ascii=False
        )
        yield f"data: {status_payload}\n\n"
        
        # 使用astream_events获取流式事件
        logger.info("🔄 [服务执行] agent_stream - 开始执行Graph...")
        final_state = None
        streamed_token = False  # 标记是否已有流式token输出，避免重复
        token_count = 0  # 流式token计数器
        stream_started = False  # 标记流式是否已开始
        stream_end_logged = False  # 标记是否已输出结尾日志
        total_tokens_estimate = None  # 估算总token数（用于判断中间位置）
        accumulated_text = ""  # 记录已发送的文本内容，用于检测图表增量
        
        async for event in graph.astream_events(initial_state, version="v1"):
            event_type = event.get("event", "")
            event_name = event.get("name", "")
            
            # 记录所有重要事件（改为INFO级别以便调试）
            if event_type in ["on_chain_start", "on_tool_start", "on_chain_end"]:
                metadata = event.get("metadata", {})
                node_name = metadata.get("langgraph_node", "")
                logger.info(f"📡 [事件] {event_type} - {event_name}, node: {node_name}")
            
            # 处理LLM流式输出
            if event_type == "on_chat_model_stream":
                # 关键修复：过滤节点名称，只处理 llm_summarize 和 simple_chat 的流式输出
                metadata = event.get("metadata", {})
                node_name = metadata.get("langgraph_node", "")
                
                # 只处理汇总节点和简单聊天节点的流式输出，避免混入其他节点的思考过程
                if node_name in ["llm_summarize", "simple_chat"]:
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        streamed_token = True
                        accumulated_text += chunk.content  # 累积已发送的文本
                        payload = json.dumps(
                            {"type": "token", "content": chunk.content},
                            ensure_ascii=False
                        )
                        yield f"data: {payload}\n\n"
                        
                        token_count += 1
                        
                        # 流式开始：输出第1条日志
                        if not stream_started:
                            stream_started = True
                            logger.info(f"📤 [服务] agent_stream - 流式开始: {chunk.content[:30]}... (from {node_name})")
                        
                        # 中间位置：在token_count达到一定数量时输出2条（比如每100个token输出一次，总共输出2次）
                        elif token_count == 10:  # 第10个token时输出第1条中间日志
                            logger.info(f"📤 [服务] agent_stream - 流式传输中 [{token_count}]: {chunk.content[:30]}...")
                        elif token_count == 20:  # 第20个token时输出第2条中间日志
                            logger.info(f"📤 [服务] agent_stream - 流式传输中 [{token_count}]: {chunk.content[:30]}...")
            
            # 捕获节点结束事件，获取最终状态
            elif event_type == "on_chain_end":
                metadata = event.get("metadata", {})
                node_name = metadata.get("langgraph_node", "")
                
                # 方法1：检查是否是最后一个节点的结束（llm_summarize 或 simple_chat）
                if node_name in ["llm_summarize", "simple_chat"]:
                    # 获取节点输出
                    output = event.get("data", {}).get("output", {})
                    logger.info(f"🔍 [调试] agent_stream - 捕获到 {node_name} 节点结束，output 类型: {type(output)}, 是否为dict: {isinstance(output, dict)}")
                    if isinstance(output, dict):
                        final_state = output
                        logger.info(f"🔍 [调试] agent_stream - 设置 final_state，包含字段: {list(final_state.keys())}")
                        
                        # 结尾日志：输出3条（在节点结束时）
                        if stream_started and not stream_end_logged:
                            stream_end_logged = True
                            final_summary = output.get("final_summary", "")
                            summary_len = len(final_summary) if final_summary else 0
                            logger.info(f"📤 [服务] agent_stream - 流式结束 [总计 {token_count} tokens, 内容 {summary_len} 字符]")
                            logger.info(f"📋 [服务] agent_stream - 捕获节点最终状态 ({node_name})，包含字段: {list(final_state.keys())}")
                            logger.info(f"✅ [服务] agent_stream - 流式传输完成")
                    else:
                        logger.warning(f"⚠️ [调试] agent_stream - {node_name} 节点输出格式不正确，output: {output}")
                
                # 方法2：检查是否是整个 Graph 的结束（Root Run，没有 langgraph_node）
                elif not node_name:
                    # Graph 级别的结束事件
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict) and "final_summary" in output:
                        final_state = output
                        # 如果之前没有输出结尾日志，在这里输出
                        if stream_started and not stream_end_logged:
                            stream_end_logged = True
                            final_summary = output.get("final_summary", "")
                            summary_len = len(final_summary) if final_summary else 0
                            logger.info(f"📤 [服务] agent_stream - 流式结束 [总计 {token_count} tokens, 内容 {summary_len} 字符]")
                            logger.info(f"📋 [服务] agent_stream - 捕获Graph最终状态，包含字段: {list(final_state.keys())}")
                            logger.info(f"✅ [服务] agent_stream - 流式传输完成")
                        else:
                            logger.info(f"📋 [服务] agent_stream - 捕获Graph最终状态，包含字段: {list(final_state.keys())}")
            
            # 处理工具调用开始
            elif event_type == "on_tool_start":
                tool_name = event.get("name", "unknown")
                payload = json.dumps(
                    {"type": "status", "content": f"正在调用工具: {tool_name}..."},
                    ensure_ascii=False
                )
                yield f"data: {payload}\n\n"
            
            # 处理节点开始
            elif event_type == "on_chain_start":
                node_name = event.get("name", "")
                if "intent_analysis" in node_name.lower():
                    payload = json.dumps(
                        {"type": "status", "content": "正在分析意图..."},
                        ensure_ascii=False
                    )
                    yield f"data: {payload}\n\n"
                elif "vkdb_search" in node_name.lower():
                    payload = json.dumps(
                        {"type": "status", "content": "正在搜索VikingDB..."},
                        ensure_ascii=False
                    )
                    yield f"data: {payload}\n\n"
                elif "mysql_join" in node_name.lower():
                    payload = json.dumps(
                        {"type": "status", "content": "正在执行MySQL分析..."},
                        ensure_ascii=False
                    )
                    yield f"data: {payload}\n\n"
                elif "llm_summarize" in node_name.lower():
                    payload = json.dumps(
                        {"type": "status", "content": "正在生成总结..."},
                        ensure_ascii=False
                    )
                    yield f"data: {payload}\n\n"
                elif "simple_chat" in node_name.lower():
                    payload = json.dumps(
                        {"type": "status", "content": "正在思考..."},
                        ensure_ascii=False
                    )
                    yield f"data: {payload}\n\n"
        
        # Graph执行完成后，检查final_summary并流式输出（兜底逻辑）
        # 检查是否有图表增量需要补发
        logger.info(f"🔍 [调试] agent_stream - 循环结束，final_state: {final_state is not None}, streamed_token: {streamed_token}, accumulated_text长度: {len(accumulated_text)}")
        if final_state and streamed_token:
            final_summary = final_state.get("final_summary", "")
            logger.info(f"🔍 [调试] agent_stream - final_summary存在: {final_summary is not None}, 长度: {len(final_summary) if final_summary else 0}")
            if final_summary and len(final_summary) > len(accumulated_text):
                # 计算差值（即图表 Markdown 部分）
                chart_part = final_summary[len(accumulated_text):]
                if chart_part.strip():
                    logger.info(f"📊 [服务] agent_stream - 检测到图表增量，正在补发 (长度: {len(chart_part)} 字符)")
                    payload = json.dumps(
                        {"type": "token", "content": chart_part},
                        ensure_ascii=False
                    )
                    yield f"data: {payload}\n\n"
            elif final_summary:
                logger.info(f"🔍 [调试] agent_stream - final_summary长度 ({len(final_summary)}) 不大于 accumulated_text长度 ({len(accumulated_text)})，无需补发")
        elif not final_state:
            logger.warning(f"⚠️ [调试] agent_stream - final_state 为 None，无法检查图表增量")
        elif not streamed_token:
            logger.info(f"🔍 [调试] agent_stream - 没有流式token，跳过图表增量检查")
        
        # Graph执行完成后，检查final_summary并流式输出（兜底逻辑）
        # 只有在未产生过流式token时，才用final_summary兜底输出，避免重复
        if not streamed_token:
            final_summary = None
            
            # 方法1：从事件中捕获的最终状态获取
            if final_state:
                final_summary = final_state.get("final_summary")
                if final_summary:
                    logger.info(f"📤 [服务] agent_stream - 从事件状态输出final_summary兜底: {final_summary[:50]}...")
            
            # 方法2：如果事件中未找到，从完整Graph状态获取
            if not final_summary:
                logger.warning("⚠️ [服务] agent_stream - 未从事件中获取到final_summary，尝试从Graph状态获取")
                async for state in graph.astream(initial_state):
                    final_summary = state.get("final_summary")
                    if final_summary:
                        logger.info(f"📤 [服务] agent_stream - 从Graph状态获取final_summary: {final_summary[:50]}...")
                        break
            
            # 输出兜底内容
            if final_summary:
                for char in final_summary:
                    payload = json.dumps(
                        {"type": "token", "content": char},
                        ensure_ascii=False
                    )
                    yield f"data: {payload}\n\n"
            else:
                logger.warning("⚠️ [服务] agent_stream - 未找到final_summary，无法输出兜底内容")
        
        # 流结束信号
        yield "data: [DONE]\n\n"
    
    except Exception as e:
        import traceback
        error_msg = f"处理消息时出错: {str(e)}\n{traceback.format_exc()}"
        error_payload = json.dumps(
            {"type": "error", "content": error_msg},
            ensure_ascii=False
        )
        yield f"data: {error_payload}\n\n"
        yield "data: [DONE]\n\n"
