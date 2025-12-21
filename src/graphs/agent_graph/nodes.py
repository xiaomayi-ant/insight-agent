from __future__ import annotations

import json
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_community.chat_models import ChatTongyi
from pydantic import BaseModel

from src.core.settings import AppSettings
from src.domain.state import FrontendSearchInput
from src.graphs.vkdb_graph.tools import make_vkdb_search_tool
from src.services.vkdb_mysql_service import vkdb_response_to_mysql_join


def intent_analysis_node(settings: AppSettings):
    """意图分析节点：判断是简单聊天还是需要VikingDB搜索"""
    
    llm = ChatTongyi(model=settings.qwen_model, temperature=settings.qwen_temperature)
    
    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("🔍 [节点执行] intent_analysis - 开始意图分析")
        
        # 直接访问字典，MessagesState是TypedDict
        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None
        
        if not last_message:
            logger.error("❌ [节点错误] intent_analysis - 没有消息")
            return {"error": "No message provided"}
        
        user_input = last_message.content
        logger.info(f"📝 [节点输入] intent_analysis - 用户输入: {user_input[:50]}...")
        
        # 使用LLM判断意图，并尽量提取 influencer 名称
        system_prompt = """你是意图分析助手，必须返回 JSON。

规则：
- 如果用户在找视频/数据/影响者/搜索/查询/查找/分析，意图为 vkdb_search。
- 如果用户只是闲聊，意图为 simple_chat。

输出 JSON 结构（字段名固定，全部小写）：
{
  "intent": "vkdb_search" | "simple_chat",
  "query": "尽量提取的核心查询词，如：李诞的视频",    // vkdb_search 必填
  "influencer": "影响者姓名，如果能确定就填，比如：李诞；否则留空" // 可选
}

注意：
- 只输出 JSON，不要其它内容。
- 如果能确定 influencer 就填具体姓名，否则填空字符串。
"""
        
        analysis_prompt = f"用户输入：{user_input}\n\n请按照上述 JSON 结构返回。"
        
        try:
            # 使用结构化输出
            class IntentResult(BaseModel):
                intent: str
                query: Optional[str] = None
                influencer: Optional[str] = None
            
            structured_llm = llm.with_structured_output(IntentResult)
            result = structured_llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=analysis_prompt)
            ])
            
            if result.intent == "vkdb_search":
                # 优先使用解析出的 influencer，否则用 query，否则回退 user_input
                influencer = (result.influencer or "").strip()
                query = (result.query or influencer or user_input).strip()
                logger.info(f"✅ [节点结果] intent_analysis - 意图: vkdb_search, 查询: {query}, influencer: {influencer}")
                return {
                    "intent": "vkdb_search",
                    "vkdb_query": query,
                    "vkdb_influencer": influencer or None
                }
            else:
                logger.info(f"✅ [节点结果] intent_analysis - 意图: simple_chat")
                return {
                    "intent": "simple_chat"
                }
        except Exception as e:
            logger.warning(f"⚠️ [节点警告] intent_analysis - 结构化输出失败，使用fallback: {e}")
            # 如果结构化输出失败，使用简单规则作为fallback
            vkdb_keywords = ["搜索", "查找", "查询", "找", "查", "数据", "视频", "影响者", "分析"]
            if any(keyword in user_input for keyword in vkdb_keywords):
                logger.info(f"✅ [节点结果] intent_analysis - 意图: vkdb_search (fallback)")
                return {
                    "intent": "vkdb_search",
                    "vkdb_query": user_input
                }
            logger.info(f"✅ [节点结果] intent_analysis - 意图: simple_chat (fallback)")
            return {
                "intent": "simple_chat"
            }
    
    return _node


def vkdb_search_node(settings: AppSettings):
    """VikingDB搜索节点"""
    
    tool = make_vkdb_search_tool(settings)
    
    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("🔍 [节点执行] vkdb_search - 开始VikingDB搜索")
        
        # 直接访问字典
        intent = state.get("intent")
        if intent != "vkdb_search":
            logger.error(f"❌ [节点错误] vkdb_search - 无效意图: {intent}")
            return {"error": "Invalid intent for vkdb_search node"}
        
        query = state.get("vkdb_query") or ""
        influencer_hint = (state.get("vkdb_influencer") or "").strip()
        if not query:
            logger.error("❌ [节点错误] vkdb_search - 没有查询内容")
            return {"error": "No query provided"}
        
        logger.info(f"📝 [节点输入] vkdb_search - 查询: {query}")
        if influencer_hint:
            logger.info(f"📌 [节点输入] vkdb_search - 解析出的influencer: {influencer_hint}")
        
        # 从settings读取配置
        vkdb_limit = settings.vikingdb_default_limit
        # 解析输出字段（从环境变量或默认值）
        # Agent Graph 需要的字段：influencer, intent_analysis, landscape_video
        # 优先使用 VKDB_AGENT_OUTPUT_FIELDS，如果没有设置则使用默认必需字段
        if settings.vkdb_output_fields:
            from src.infra.vkdb.client import parse_output_fields
            output_fields = parse_output_fields(settings.vkdb_output_fields)
        else:
            # 默认使用Agent Graph必需的字段（这些字段是Agent Graph工作流必需的）
            # 注意：如果需要修改这些默认字段，请在 .env 中设置 VKDB_AGENT_OUTPUT_FIELDS
            output_fields = ["influencer", "intent_analysis", "landscape_video"]
        
        # 简化参数：只使用influencer
        # 注意：VikingDB要求text/image/video至少有一个，所以设置text=influence
        influence_value = influencer_hint or query  # 优先使用意图解析出的 influencer
        search_input = FrontendSearchInput(
            influence=influence_value,  # influencer名称
            text=query,  # 同时设置text（VikingDB API要求）
            limit=vkdb_limit,
            output_fields=output_fields
        )
        
        logger.info(f"📋 [节点参数] vkdb_search - influencer: {influence_value}, text: {query}, limit: {vkdb_limit}, output_fields: {search_input.output_fields}")
        
        # 调试：查看实际传递给工具的参数
        tool_params = search_input.model_dump(exclude_none=True)
        logger.info(f"🔍 [节点调试] vkdb_search - 工具参数: {tool_params}")
        logger.info(f"🔍 [节点调试] vkdb_search - text值: '{tool_params.get('text', 'NOT_FOUND')}', influence值: '{tool_params.get('influence', 'NOT_FOUND')}'")
        
        try:
            logger.info("🔄 [节点执行] vkdb_search - 调用VikingDB搜索工具...")
            # 调用搜索工具 - 确保text参数被传递
            tool_result = tool.invoke(tool_params)
            vkdb_response = json.loads(tool_result)
            
            result_count = len(vkdb_response.get("result", {}).get("data", []))
            logger.info(f"✅ [节点结果] vkdb_search - 搜索成功，返回 {result_count} 条结果")
            
            # 诊断：分析VikingDB返回数据的结构大小
            if result_count:
                data_list = vkdb_response.get("result", {}).get("data", [])
                # 计算总JSON大小
                total_json_size = len(json.dumps(vkdb_response, ensure_ascii=False))
                logger.info(f"📊 [诊断] vkdb_search - VikingDB响应总JSON大小: {total_json_size:,} 字符")
                
                # 分析第一条记录的字段大小
                if data_list and len(data_list) > 0:
                    first_item = data_list[0]
                    logger.info(f"📊 [诊断] vkdb_search - 第一条记录的字段:")
                    for key, value in first_item.get("fields", {}).items():
                        if isinstance(value, str):
                            field_size = len(value)
                            logger.info(f"   - {key}: {field_size:,} 字符")
                        elif isinstance(value, (dict, list)):
                            field_size = len(json.dumps(value, ensure_ascii=False))
                            logger.info(f"   - {key}: {field_size:,} 字符 (JSON)")
                        else:
                            logger.info(f"   - {key}: {len(str(value))} 字符")
                
                # 计算平均每条记录的大小
                avg_item_size = total_json_size / result_count if result_count > 0 else 0
                logger.info(f"📊 [诊断] vkdb_search - 平均每条记录大小: {avg_item_size:,.0f} 字符")
                
                # 仅日志打印前5条，便于核对字段（截断以避免日志过长）
                preview = data_list[:5]
                preview_str = json.dumps(preview, ensure_ascii=False)
                logger.info(f"📝 [节点结果] vkdb_search - 前5条结果预览（前500字符）: {preview_str[:2000]}...")
            if result_count == 0:
                # 无结果时直接返回提示，后续节点可跳过
                logger.warning("⚠️ [节点结果] vkdb_search - 未收录该达人，直接返回提示")
                return {
                    "vkdb_response": vkdb_response,
                    "final_summary": "当前未收录该达人",
                    "vkdb_influencer": influence_value,
                    "vkdb_no_result": True
                }
            return {
                "vkdb_response": vkdb_response,
                "vkdb_influencer": influence_value,
                "vkdb_no_result": False
            }
        except Exception as e:
            logger.error(f"❌ [节点错误] vkdb_search - 搜索失败: {e}")
            return {
                "error": f"VikingDB search failed: {e}",
                "vkdb_response": None
            }
    
    return _node


def mysql_join_node(settings: AppSettings):
    """MySQL Join节点：自动从VikingDB结果中提取material_id，然后Join MySQL"""
    
    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("🔍 [节点执行] mysql_join - 开始MySQL Join")
        
        # 直接访问字典
        vkdb_response = state.get("vkdb_response")
        if not vkdb_response:
            logger.error("❌ [节点错误] mysql_join - 没有VikingDB搜索结果")
            return {"error": "No vkdb_response for MySQL join"}
        if state.get("vkdb_no_result"):
            # 上游已判定无数据，跳过Join
            logger.warning("⚠️ [节点结果] mysql_join - 上游无结果，跳过Join")
            return {
                "mysql_join_result": None,
                "final_summary": state.get("final_summary"),
                "vkdb_influencer": state.get("vkdb_influencer"),
            }
        
        # 从VikingDB响应中提取影响者信息
        # 尝试从vkdb_response中提取influencer
        vkdb_result = vkdb_response.get("result", {}).get("data", [])
        influencer = state.get("vkdb_influencer") or state.get("vkdb_query") or "未知"
        
        # 如果VikingDB结果中有influencer字段，优先使用
        if vkdb_result and isinstance(vkdb_result, list) and len(vkdb_result) > 0:
            first_item = vkdb_result[0]
            if isinstance(first_item, dict) and "influencer" in first_item:
                influencer = first_item["influencer"] or influencer
        
        logger.info(f"📝 [节点输入] mysql_join - 影响者: {influencer}")
        
        # 从settings获取MySQL配置
        mysql_table = settings.mysql_table
        mysql_max_in = settings.mysql_max_in
        mysql_max_rows = settings.mysql_max_rows
        
        try:
            logger.info("🔄 [节点执行] mysql_join - 调用MySQL Join服务（使用已有VikingDB结果）...")
            # 直接使用state中的vkdb_response，避免重复搜索
            mysql_result = vkdb_response_to_mysql_join(
                vkdb_response=vkdb_response,
                influencer=influencer,
                mysql_max_in=mysql_max_in,
                mysql_table=mysql_table,
                mysql_max_rows=mysql_max_rows,
                require_in=True,
            )
            
            row_count = mysql_result.get("mysql", {}).get("row_count", 0)
            logger.info(f"✅ [节点结果] mysql_join - Join成功，MySQL返回 {row_count} 行数据")
            
            return {
                "mysql_join_result": mysql_result
            }
        except Exception as e:
            logger.error(f"❌ [节点错误] mysql_join - Join失败: {e}")
            return {
                "error": f"MySQL join failed: {e}",
                "mysql_join_result": None
            }
    
    return _node


def llm_summarize_node(settings: AppSettings):
    """LLM汇总节点：汇总VikingDB和MySQL的结果"""
    
    llm = ChatTongyi(model=settings.qwen_model, temperature=settings.qwen_temperature)
    
    async def _node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("🔍 [节点执行] llm_summarize - 开始LLM汇总")
        
        # 直接访问字典
        vkdb_response = state.get("vkdb_response")
        if not vkdb_response:
            logger.error("❌ [节点错误] llm_summarize - 没有VikingDB搜索结果")
            return {"error": "No vkdb_response for summarization"}
        # 如果上游已给出最终提示（如未收录达人），直接返回
        if state.get("final_summary"):
            summary = state.get("final_summary")
            logger.info(f"ℹ️ [节点结果] llm_summarize - 使用上游summary直接返回: {summary}")
            return {"final_summary": summary}
        
        # 构建汇总提示
        system_prompt = """你是一个数据分析助手。根据VikingDB搜索结果和MySQL分析结果，为用户生成清晰、有用的总结。

重点关注：
1. VikingDB搜索到的内容
2. MySQL数据分析结果（如果有）
3. 用户原始查询的答案

用自然语言回复，不要返回JSON。"""
        
        vkdb_info = json.dumps(vkdb_response, ensure_ascii=False, indent=2)
        mysql_info = ""
        mysql_join_result = state.get("mysql_join_result")
        if mysql_join_result:
            mysql_info = f"\n\nMySQL分析结果：\n{json.dumps(mysql_join_result, ensure_ascii=False, indent=2)}"
        
        user_query = state.get("vkdb_query") or "查询"
        logger.info(f"📝 [节点输入] llm_summarize - 用户查询: {user_query}")
        
        human_prompt = f"""用户查询：{user_query}

VikingDB搜索结果：
{vkdb_info}
{mysql_info}

请生成总结回复。"""
        
        # 诊断：详细分析prompt长度，定位TTFT延迟问题
        system_prompt_len = len(system_prompt)
        human_prompt_len = len(human_prompt)
        vkdb_info_len = len(vkdb_info)
        mysql_info_len = len(mysql_info)
        prompt_length = system_prompt_len + human_prompt_len
        estimated_tokens = prompt_length // 4  # 粗略估算：1 token ≈ 4 字符
        
        logger.info(f"📊 [节点诊断] llm_summarize - Prompt组成分析:")
        logger.info(f"   - System Prompt: {system_prompt_len:,} 字符")
        logger.info(f"   - Human Prompt: {human_prompt_len:,} 字符")
        logger.info(f"     * 用户查询部分: {len(user_query)} 字符")
        logger.info(f"     * VikingDB结果: {vkdb_info_len:,} 字符 ({vkdb_info_len/prompt_length*100:.1f}% of prompt)")
        logger.info(f"     * MySQL结果: {mysql_info_len:,} 字符")
        logger.info(f"   - Prompt总长度: {prompt_length:,} 字符")
        logger.info(f"   - 估算Token数: ~{estimated_tokens:,} tokens")
        
        # 如果prompt很大，给出警告
        if estimated_tokens > 100000:
            logger.warning(f"⚠️ [节点诊断] llm_summarize - Prompt非常大 (~{estimated_tokens:,} tokens)，可能导致TTFT延迟")
        elif estimated_tokens > 50000:
            logger.warning(f"⚠️ [节点诊断] llm_summarize - Prompt较大 (~{estimated_tokens:,} tokens)，可能影响TTFT")
        
        try:
            import time
            prefill_start_time = time.time()
            logger.info("🔄 [节点执行] llm_summarize - 开始调用LLM API（即将进入Prefill阶段）...")
            logger.info(f"⏱️ [时间诊断] llm_summarize - API调用开始时间: {prefill_start_time:.3f}")
            summary_chunks: list[str] = []
            # 关键修复：传递 config 给 astream，让流式事件能被 astream_events 捕获
            async_iterator = llm.astream([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt)
            ], config=config)
            
            # 记录第一个chunk到达的时间
            first_chunk_time = None
            async for chunk in async_iterator:
                if first_chunk_time is None:
                    first_chunk_time = time.time()
                    ttft = first_chunk_time - prefill_start_time
                    logger.info(f"⏱️ [时间诊断] llm_summarize - 第一个Token到达时间: {first_chunk_time:.3f}")
                    logger.info(f"⏱️ [时间诊断] llm_summarize - TTFT (Time To First Token): {ttft:.2f} 秒")
                if hasattr(chunk, "content") and chunk.content:
                    summary_chunks.append(chunk.content)
            # 消费流并累积内容，事件层会直接把chunk推给前端
            async for chunk in async_iterator:
                if hasattr(chunk, "content") and chunk.content:
                    summary_chunks.append(chunk.content)
            summary = "".join(summary_chunks)
            logger.info(f"✅ [节点结果] llm_summarize - 汇总完成，长度: {len(summary)} 字符")
            return {
                "final_summary": summary
            }
        except Exception as e:
            logger.error(f"❌ [节点错误] llm_summarize - 汇总失败: {e}")
            return {
                "error": f"LLM summarization failed: {e}",
                "final_summary": None
            }
    
    return _node


def simple_chat_node(settings: AppSettings):
    """简单聊天节点：直接LLM回复"""
    
    llm = ChatTongyi(model=settings.qwen_model, temperature=settings.qwen_temperature)
    
    def _node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("🔍 [节点执行] simple_chat - 开始简单聊天")
        
        # 直接访问字典
        messages = state.get("messages", [])
        
        if not messages:
            logger.error("❌ [节点错误] simple_chat - 没有消息")
            return {"error": "No messages provided"}
        
        user_input = messages[-1].content if messages else ""
        logger.info(f"📝 [节点输入] simple_chat - 用户输入: {user_input[:50]}...")
        
        try:
            logger.info("🔄 [节点执行] simple_chat - 调用LLM生成回复...")
            # 传递 config 给 invoke，确保事件能被捕获（虽然当前是 invoke，但为统一性加上）
            response = llm.invoke(messages, config=config)
            content = response.content if hasattr(response, 'content') else str(response)
            
            logger.info(f"✅ [节点结果] simple_chat - 回复生成完成，长度: {len(content)} 字符")
            
            return {
                "final_summary": content
            }
        except Exception as e:
            logger.error(f"❌ [节点错误] simple_chat - 聊天失败: {e}")
            return {
                "error": f"Simple chat failed: {e}",
                "final_summary": None
            }
    
    return _node
