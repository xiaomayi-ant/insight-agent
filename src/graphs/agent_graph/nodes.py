from __future__ import annotations

import json
import re
from datetime import datetime, date
from typing import Any, Dict, Optional, List as TypingList

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_community.chat_models import ChatTongyi
from pydantic import BaseModel, Field


class DateTimeJSONEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理datetime和date对象"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

from src.core.settings import AppSettings
from src.domain.state import FrontendSearchInput
from src.graphs.agent_graph.tools import make_vkdb_search_tool
from src.services.vkdb_mysql_service import vkdb_response_to_mysql_join
from src.services.intent_structurize_service import structurize_intents_batch
from src.utils.data_aggregator import generate_aggregation_csv


class DateTimeJSONEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理datetime和date对象"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def _generate_chart_image_markdown(plot_data: List[Dict[str, Any]]) -> str:
    """
    生成图表图片并返回 Markdown 格式字符串（使用 QuickChart 服务）
    
    Args:
        plot_data: LLM分析结果中的plot_data
    
    Returns:
        str: Markdown 格式的图片字符串，如果失败返回空字符串
    """
    if not plot_data:
        return ""
    
    try:
        import json
        import urllib.parse
        
        # 提取数据
        categories = [item.get("category", "Unknown") for item in plot_data]
        roi_values = [float(item.get("roi", 0.0)) for item in plot_data]
        ctr_values = [float(item.get("ctr", 0.0)) for item in plot_data]
        
        # 构建 QuickChart 的配置 JSON
        # 使用组合图表：柱状图显示 ROI，折线图显示 CTR
        chart_config = {
            "type": "bar",
            "data": {
                "labels": categories,
                "datasets": [
                    {
                        "label": "ROI",
                        "type": "bar",
                        "data": roi_values,
                        "backgroundColor": [
                            "rgba(255, 107, 107, 0.7)" if x > 20 else "rgba(78, 205, 196, 0.7)"
                            for x in roi_values
                        ],
                        "borderColor": [
                            "rgba(255, 107, 107, 1)" if x > 20 else "rgba(78, 205, 196, 1)"
                            for x in roi_values
                        ],
                        "borderWidth": 1,
                        "yAxisID": "y"
                    },
                    {
                        "label": "CTR",
                        "type": "line",
                        "data": ctr_values,
                        "backgroundColor": "rgba(255, 165, 0, 0.2)",
                        "borderColor": "rgba(255, 165, 0, 1)",
                        "borderWidth": 2,
                        "fill": False,
                        "pointRadius": 4,
                        "pointBackgroundColor": "rgba(255, 165, 0, 1)",
                        "yAxisID": "y1"
                    }
                ]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": "Strategy Effectiveness Analysis",
                        "font": {"size": 16, "weight": "bold"}
                    },
                    "legend": {
                        "display": True,
                        "position": "top"
                    }
                },
                "scales": {
                    "y": {
                        "type": "linear",
                        "display": True,
                        "position": "left",
                        "title": {
                            "display": True,
                            "text": "ROI"
                        }
                    },
                    "y1": {
                        "type": "linear",
                        "display": True,
                        "position": "right",
                        "title": {
                            "display": True,
                            "text": "CTR"
                        },
                        "grid": {
                            "drawOnChartArea": False
                        }
                    },
                    "x": {
                        "ticks": {
                            "maxRotation": 45,
                            "minRotation": 45
                        }
                    }
                }
            }
        }
        
        # 将配置转换为 JSON 字符串并压缩（去除空格）
        chart_config_json = json.dumps(chart_config, separators=(',', ':'))
        
        # 生成 QuickChart URL（指定使用 Chart.js v3）
        base_url = "https://quickchart.io/chart"
        chart_url = f"{base_url}?v=3&c={urllib.parse.quote(chart_config_json)}&w=800&h=400&format=png"
        
        # 返回 Markdown 格式
        return f"\n\n![Analysis Chart]({chart_url})"
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"⚠️ [图表生成] 生成图表失败: {e}")
        return ""


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
    
    # 根据配置选择检索方式
    search_method = getattr(settings, 'vikingdb_search_method', 'multi_modal')
    
    if search_method == "random":
        from src.graphs.agent_graph.tools import make_vkdb_random_search_tool
        tool = make_vkdb_random_search_tool(settings)
    else:
        from src.graphs.agent_graph.tools import make_vkdb_search_tool
        tool = make_vkdb_search_tool(settings)
    
    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 [节点执行] vkdb_search - 开始VikingDB搜索 (模式: {search_method})")
        
        # 直接访问字典
        intent = state.get("intent")
        if intent != "vkdb_search":
            logger.error(f"❌ [节点错误] vkdb_search - 无效意图: {intent}")
            return {"error": "Invalid intent for vkdb_search node"}
        
        query = state.get("vkdb_query") or ""
        influencer_hint = (state.get("vkdb_influencer") or "").strip()
        
        # 随机检索不需要query，只需要influencer（如果没有influencer，使用query作为fallback）
        if search_method == "random":
            if not influencer_hint and not query:
                logger.error("❌ [节点错误] vkdb_search - 随机检索需要influencer或query")
                return {"error": "Random search requires influencer or query"}
        else:
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
        
        # 根据检索方式构建不同的输入参数
        influence_value = influencer_hint or query  # 优先使用意图解析出的 influencer
        
        if search_method == "random":
            # 随机检索只需要influence，不需要text
            search_input = FrontendSearchInput(
                influence=influence_value,
                limit=vkdb_limit,
                output_fields=output_fields
            )
            logger.info(f"📋 [节点参数] vkdb_search - influencer: {influence_value}, limit: {vkdb_limit}, output_fields: {search_input.output_fields}")
        else:
            # 多模态检索需要text
            search_input = FrontendSearchInput(
                influence=influence_value,
                text=query,  # 多模态需要text
                limit=vkdb_limit,
                output_fields=output_fields
            )
            logger.info(f"📋 [节点参数] vkdb_search - influencer: {influence_value}, text: {query}, limit: {vkdb_limit}, output_fields: {search_input.output_fields}")
        
        # 调试：查看实际传递给工具的参数
        tool_params = search_input.model_dump(exclude_none=True)
        logger.info(f"🔍 [节点调试] vkdb_search - 工具参数: {tool_params}")
        if search_method != "random":
            logger.info(f"🔍 [节点调试] vkdb_search - text值: '{tool_params.get('text', 'NOT_FOUND')}', influence值: '{tool_params.get('influence', 'NOT_FOUND')}'")
        else:
            logger.info(f"🔍 [节点调试] vkdb_search - influence值: '{tool_params.get('influence', 'NOT_FOUND')}'")
        
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
            material_ids_count = len(mysql_result.get("vkdb", {}).get("material_ids", []))
            logger.info(f"✅ [节点结果] mysql_join - Join成功，提取了 {material_ids_count} 个materialId，MySQL返回 {row_count} 行数据")
            
            # 如果materialId有但MySQL返回0行，记录警告
            if material_ids_count > 0 and row_count == 0:
                material_ids = mysql_result.get("vkdb", {}).get("material_ids", [])[:5]  # 只显示前5个
                logger.warning(f"⚠️ [节点警告] mysql_join - 有 {material_ids_count} 个materialId但MySQL返回0行，可能原因：")
                logger.warning(f"   1. roi2MaterialVideoName字段不包含'{influencer}'")
                logger.warning(f"   2. 不满足liveShowCountForRoi2V2 > 0或liveWatchCountForRoi2V2 > 0条件")
                logger.warning(f"   3. materialId在MySQL中不存在")
                logger.warning(f"   示例materialId: {material_ids}")
            
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
    """LLM汇总节点：汇总VikingDB和MySQL的结果，整合分析洞察，生成图表"""
    
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
        
        # 检查是否有分析结果（新流程）
        analysis_result = state.get("analysis_result")
        has_analysis = analysis_result is not None and analysis_result.get("summary") is not None
        
        if has_analysis:
            # 新流程：整合分析洞察
            logger.info("📊 [节点] llm_summarize - 检测到分析结果，使用新流程")
            
            # 构建汇总提示（整合分析洞察）
            system_prompt = """你是一个数据分析助手。根据AI分析师的洞察和原始数据，为用户生成清晰、有用的总结。

重点关注：
1. AI分析师的深度洞察（key_insight）
2. 黄金法则（golden_rule）
3. 用户原始查询的答案

用自然语言回复，不要返回JSON。"""
            
            key_insight = analysis_result.get("summary", {}).get("key_insight", "")
            golden_rule = analysis_result.get("summary", {}).get("golden_rule", "")
            
            user_query = state.get("vkdb_query") or "查询"
            logger.info(f"📝 [节点输入] llm_summarize - 用户查询: {user_query}")
            
            # 记录完整的分析结果供诊断
            plot_data = analysis_result.get("plot_data", [])
            logger.info(f"📊 [数据详情] llm_summarize - 接收到的分析结果:")
            logger.info(f"   - key_insight 长度: {len(key_insight)} 字符")
            logger.info(f"   - key_insight 内容预览: {key_insight[:500]}...")
            logger.info(f"   - golden_rule: {golden_rule}")
            logger.info(f"   - plot_data 数量: {len(plot_data)}")
            for idx, item in enumerate(plot_data[:5], 1):  # 只显示前5个
                logger.info(f"   - plot_data[{idx}]: {item}")
            
            human_prompt = f"""用户查询：{user_query}

AI分析师洞察：
{key_insight}

黄金法则：
{golden_rule}

请基于以上洞察，生成一个清晰、有用的总结回复。"""
            
            logger.info(f"📊 [数据详情] llm_summarize - 完整 human_prompt 内容:\n{human_prompt}")
        else:
            # 旧流程：直接汇总原始数据
            logger.info("📊 [节点] llm_summarize - 使用旧流程（直接汇总原始数据）")
            
            system_prompt = """你是一个数据分析助手。根据VikingDB搜索结果和MySQL分析结果，为用户生成清晰、有用的总结。

重点关注：
1. VikingDB搜索到的内容
2. MySQL数据分析结果（如果有）
3. 用户原始查询的答案

用自然语言回复，不要返回JSON。"""
            
            vkdb_info = json.dumps(vkdb_response, ensure_ascii=False, indent=2, cls=DateTimeJSONEncoder)
            mysql_info = ""
            mysql_join_result = state.get("mysql_join_result")
            if mysql_join_result:
                mysql_info = f"\n\nMySQL分析结果：\n{json.dumps(mysql_join_result, ensure_ascii=False, indent=2, cls=DateTimeJSONEncoder)}"
            
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
        prompt_length = system_prompt_len + human_prompt_len
        estimated_tokens = prompt_length // 4  # 粗略估算：1 token ≈ 4 字符
        
        logger.info(f"📊 [节点诊断] llm_summarize - Prompt组成分析:")
        logger.info(f"   - System Prompt: {system_prompt_len:,} 字符")
        logger.info(f"   - Human Prompt: {human_prompt_len:,} 字符")
        logger.info(f"     * 用户查询部分: {len(user_query)} 字符")
        if not has_analysis:
            vkdb_info_len = len(vkdb_info) if 'vkdb_info' in locals() else 0
            mysql_info_len = len(mysql_info) if 'mysql_info' in locals() else 0
            logger.info(f"     * VikingDB结果: {vkdb_info_len:,} 字符 ({vkdb_info_len/prompt_length*100:.1f}% of prompt)" if prompt_length > 0 else "     * VikingDB结果: 0 字符")
            logger.info(f"     * MySQL结果: {mysql_info_len:,} 字符")
        else:
            logger.info(f"     * 使用AI分析洞察（新流程）")
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
            summary = "".join(summary_chunks)
            logger.info(f"✅ [节点结果] llm_summarize - 汇总完成，长度: {len(summary)} 字符")
            
            # 生成图表图片并追加到文本（如果有分析结果）
            if has_analysis:
                plot_data = analysis_result.get("plot_data", [])
                if plot_data:
                    chart_markdown = _generate_chart_image_markdown(plot_data)
                    if chart_markdown:
                        summary += chart_markdown
                        logger.info(f"📊 [节点结果] llm_summarize - 图表已追加到文本，包含 {len(plot_data)} 个类别")
            
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


def intent_structurize_node(settings: AppSettings):
    """意图结构化节点：将段落型 intent_analysis 转为结构化 JSON"""
    
    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("🔍 [节点执行] intent_structurize - 开始意图结构化")
        
        # 检查是否启用
        if not settings.intent_structurize_enabled:
            logger.info("ℹ️ [节点] intent_structurize - 功能已禁用，跳过")
            return {}
        
        # 直接访问字典
        vkdb_response = state.get("vkdb_response")
        if not vkdb_response:
            logger.error("❌ [节点错误] intent_structurize - 没有VikingDB搜索结果")
            return {"error": "No vkdb_response for intent structurization"}
        
        if state.get("vkdb_no_result"):
            logger.warning("⚠️ [节点] intent_structurize - 上游无结果，跳过")
            return {}
        
        try:
            logger.info("🔄 [节点执行] intent_structurize - 开始批量结构化处理...")
            results = structurize_intents_batch(
                vkdb_response=vkdb_response,
                settings=settings,
                concurrency=settings.intent_structurize_concurrency,
                timeout=settings.intent_structurize_timeout
            )
            
            # 转换为字典列表（便于存储到 state）
            structured_list = []
            for result in results:
                structured_list.append({
                    "materialId": result.materialId,
                    "structured_intent": result.structured_intent,
                    "success": result.success,
                    "error": result.error
                })
            
            success_count = sum(1 for r in results if r.success)
            logger.info(f"✅ [节点结果] intent_structurize - 完成，成功: {success_count}/{len(results)}")
            
            return {
                "structured_intents": structured_list
            }
        except Exception as e:
            logger.error(f"❌ [节点错误] intent_structurize - 结构化失败: {e}")
            return {
                "error": f"Intent structurization failed: {e}",
                "structured_intents": []
            }
    
    return _node


def data_aggregate_node(settings: AppSettings):
    """数据聚合节点：合并结构化意图数据与 MySQL 数据，生成统计表"""
    
    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("🔍 [节点执行] data_aggregate - 开始数据聚合")
        
        # 直接访问字典
        structured_intents = state.get("structured_intents")
        mysql_join_result = state.get("mysql_join_result")
        
        if not structured_intents:
            logger.warning("⚠️ [节点] data_aggregate - 没有结构化意图数据，跳过")
            return {}
        
        if not mysql_join_result:
            logger.warning("⚠️ [节点] data_aggregate - 没有MySQL Join结果，跳过")
            return {}
        
        try:
            logger.info("🔄 [节点执行] data_aggregate - 开始聚合统计...")
            
            # 转换 structured_intents 为 StructuredIntentResult 对象
            from src.services.intent_structurize_service import StructuredIntentResult
            intent_results = [
                StructuredIntentResult(
                    materialId=item["materialId"],
                    structured_intent=item["structured_intent"],
                    success=item.get("success", True),
                    error=item.get("error")
                )
                for item in structured_intents
            ]
            
            # 生成 CSV
            csv_str = generate_aggregation_csv(
                structured_intents=intent_results,
                mysql_join_result=mysql_join_result,
                dimensions=["opening_strategy", "script_archetype", "closing_trigger"],
                min_count=settings.data_aggregate_min_count
            )
            
            logger.info(f"✅ [节点结果] data_aggregate - 生成 CSV，长度: {len(csv_str)} 字符")
            logger.info(f"📊 [数据详情] data_aggregate - CSV 内容预览（前1000字符）:\n{csv_str[:1000]}")
            if len(csv_str) > 1000:
                logger.info(f"📊 [数据详情] data_aggregate - CSV 完整内容:\n{csv_str}")
            
            return {
                "aggregated_stats": csv_str
            }
        except Exception as e:
            logger.error(f"❌ [节点错误] data_aggregate - 聚合失败: {e}")
            return {
                "error": f"Data aggregation failed: {e}",
                "aggregated_stats": None
            }
    
    return _node


def llm_analyze_node(settings: AppSettings):
    """LLM 分析节点：对聚合统计表进行语义归纳和洞察生成"""
    
    llm = ChatTongyi(model=settings.qwen_model, temperature=settings.qwen_temperature)
    
    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        import logging
        from pathlib import Path
        logger = logging.getLogger(__name__)
        logger.info("🔍 [节点执行] llm_analyze - 开始LLM分析")
        
        # 直接访问字典
        aggregated_stats = state.get("aggregated_stats")
        if not aggregated_stats:
            logger.warning("⚠️ [节点] llm_analyze - 没有聚合统计数据，跳过")
            return {}
        
        try:
            # 加载 summary_prompt 模板
            prompt_path = Path(__file__).parent / "prompts" / "summary_prompt.md"
            prompt_template = prompt_path.read_text(encoding="utf-8")
            
            # 替换 CSV 占位符
            full_prompt = prompt_template.replace("{csv_context}", aggregated_stats)
            
            # 使用结构化输出
            class PlotDataItem(BaseModel):
                category: str
                count: int
                roi: float
                ctr: float
            
            class SummaryItem(BaseModel):
                key_insight: str = Field(description="深度分析文本，可以使用Markdown格式")
                golden_rule: str = Field(description="一句话总结高ROI公式")
            
            class AnalysisOutput(BaseModel):
                summary: SummaryItem
                plot_data: TypingList[PlotDataItem]
            
            structured_llm = llm.with_structured_output(AnalysisOutput)
            
            logger.info("🔄 [节点执行] llm_analyze - 调用LLM进行语义归纳...")
            try:
                response = structured_llm.invoke([
                    SystemMessage(content=full_prompt),
                    HumanMessage(content=aggregated_stats)
                ])
            except Exception as parse_error:
                # 如果结构化输出失败，记录详细错误并尝试fallback
                error_msg = str(parse_error)
                logger.warning(f"⚠️ [节点] llm_analyze - 结构化输出失败: {error_msg[:200]}...")
                
                # 尝试使用普通LLM调用，然后手动解析JSON
                logger.info("🔄 [节点] llm_analyze - 尝试fallback方案（普通LLM调用+手动解析）")
                fallback_llm = ChatTongyi(model=settings.qwen_model, temperature=settings.qwen_temperature)
                
                # 改进prompt，明确要求JSON格式
                fallback_prompt = full_prompt + """

重要提示：
- 必须返回有效的JSON格式
- key_insight字段中的换行符必须使用\\n转义（不是实际的换行）
- 不要使用Markdown代码块包裹JSON
- 直接返回JSON对象，不要其他文字说明
"""
                
                fallback_response = fallback_llm.invoke([
                    SystemMessage(content=fallback_prompt),
                    HumanMessage(content=aggregated_stats)
                ])
                
                # 尝试从响应中提取JSON（支持多种格式）
                content = fallback_response.content.strip()
                
                # 移除可能的markdown代码块标记
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                # 尝试提取JSON对象
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    try:
                        json_str = json_match.group()
                        # 替换未转义的换行符
                        json_str = json_str.replace('\n', '\\n').replace('\r', '\\r')
                        parsed_json = json.loads(json_str)
                        
                        # 验证结构
                        if 'summary' not in parsed_json or 'plot_data' not in parsed_json:
                            raise ValueError("JSON结构不完整")
                        
                        # 构造响应对象
                        class MockResponse:
                            def __init__(self, data):
                                summary_data = data.get('summary', {})
                                self.summary = type('obj', (object,), {
                                    'key_insight': summary_data.get('key_insight', ''),
                                    'golden_rule': summary_data.get('golden_rule', '')
                                })()
                                self.plot_data = [
                                    type('obj', (object,), {
                                        'category': item.get('category', ''),
                                        'count': item.get('count', 0),
                                        'roi': item.get('roi', 0.0),
                                        'ctr': item.get('ctr', 0.0)
                                    })()
                                    for item in data.get('plot_data', [])
                                ]
                        
                        response = MockResponse(parsed_json)
                        logger.info("✅ [节点] llm_analyze - Fallback方案成功解析JSON")
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.error(f"❌ [节点] llm_analyze - Fallback JSON解析失败: {e}")
                        logger.error(f"📝 [节点] llm_analyze - 响应内容预览: {content[:500]}")
                        raise parse_error
                else:
                    logger.error(f"❌ [节点] llm_analyze - 无法从响应中提取JSON")
                    logger.error(f"📝 [节点] llm_analyze - 响应内容: {content[:500]}")
                    raise parse_error
            
            # 转换为字典
            analysis_result = {
                "summary": {
                    "key_insight": response.summary.key_insight,
                    "golden_rule": response.summary.golden_rule
                },
                "plot_data": [
                    {
                        "category": item.category,
                        "count": item.count,
                        "roi": item.roi,
                        "ctr": item.ctr
                    }
                    for item in response.plot_data
                ]
            }
            
            logger.info(f"✅ [节点结果] llm_analyze - 分析完成，生成 {len(response.plot_data)} 个类别")
            logger.info(f"📊 [数据详情] llm_analyze - key_insight 内容:\n{response.summary.key_insight}")
            logger.info(f"📊 [数据详情] llm_analyze - golden_rule: {response.summary.golden_rule}")
            logger.info(f"📊 [数据详情] llm_analyze - plot_data ({len(response.plot_data)} 项):")
            for idx, item in enumerate(response.plot_data, 1):
                logger.info(f"   [{idx}] category={item.category}, count={item.count}, roi={item.roi:.3f}, ctr={item.ctr:.3f}")
            
            return {
                "analysis_result": analysis_result
            }
        except Exception as e:
            logger.error(f"❌ [节点错误] llm_analyze - LLM分析失败: {e}")
            return {
                "error": f"LLM analysis failed: {e}",
                "analysis_result": None
            }
    
    return _node
