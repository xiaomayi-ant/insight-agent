from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.chat_models import ChatTongyi
from pydantic import BaseModel, Field, ValidationError, field_validator

from src.core.settings import AppSettings
from src.infra.vkdb.join import extract_join_info_from_vkdb_item

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _require_non_empty(value: str, field_name: str) -> str:
    v = (value or "").strip()
    if not v:
        raise ValueError(f"{field_name} must be non-empty")
    if v.lower() == "unknown":
        raise ValueError(f"{field_name} must not be 'Unknown'")
    return v


def _require_tag(value: str, field_name: str) -> str:
    v = _require_non_empty(value, field_name)
    if not _TAG_RE.match(v):
        raise ValueError(f"{field_name} must match pattern {_TAG_RE.pattern}, got: {v!r}")
    return v


class StructuredIntentResult(BaseModel):
    """结构化意图解析结果"""
    materialId: str
    structured_intent: Dict[str, Any]
    success: bool
    error: Optional[str] = None


def load_intent_prompt() -> str:
    """加载意图结构化 Prompt 模板"""
    prompt_path = Path(__file__).parent.parent / "graphs" / "agent_graph" / "prompts" / "intent_prompt.md"
    try:
        return prompt_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to load intent_prompt.md: {e}")
        raise


def parse_single_intent_analysis(
    material_id: str,
    intent_analysis: str,
    llm: ChatTongyi,
    prompt_template: str,
    timeout: int = 20
) -> StructuredIntentResult:
    """
    解析单个视频的意图分析文本
    
    Args:
        material_id: 素材ID（用于日志和结果绑定）
        intent_analysis: 段落型意图分析文本
        llm: LLM实例
        prompt_template: Prompt模板
        timeout: 超时时间（秒）
    
    Returns:
        StructuredIntentResult
    """
    if not intent_analysis or not intent_analysis.strip():
        return StructuredIntentResult(
            materialId=material_id,
            structured_intent={},
            success=False,
            error="Empty intent_analysis"
        )
    
    try:
        # 使用更严格的结构化输出：避免“空dict也算成功”导致聚合全是Unknown
        class NarrativeAnalysis(BaseModel):
            script_archetype: str = Field(..., description="Narrative archetype, PascalCase or known enum")
            narrative_chain: str = Field(..., description="3-5 nodes chain: Node -> Node -> Node")
            pacing: str = Field(..., description="Fast|Moderate|Slow")

            @field_validator("script_archetype")
            @classmethod
            def _v_script_archetype(cls, v: str) -> str:
                return _require_tag(v, "script_archetype")

            @field_validator("narrative_chain")
            @classmethod
            def _v_narrative_chain(cls, v: str) -> str:
                vv = _require_non_empty(v, "narrative_chain")
                if "->" not in vv:
                    raise ValueError("narrative_chain must contain '->'")
                return vv

            @field_validator("pacing")
            @classmethod
            def _v_pacing(cls, v: str) -> str:
                vv = _require_non_empty(v, "pacing")
                allowed = {"Fast", "Moderate", "Slow"}
                if vv not in allowed:
                    raise ValueError(f"pacing must be one of {sorted(allowed)}")
                return vv

        class TacticalBreakdown(BaseModel):
            opening_strategy: str = Field(..., description="Opening strategy tag, Snake_Case")
            core_selling_points: List[str] = Field(..., description="1-5 core hooks tags")
            closing_trigger: str = Field(..., description="Closing trigger tag, Snake_Case")
            dominant_emotion: str = Field(..., description="Excitement|Anxiety|Curiosity|Humor|Trust")

            @field_validator("opening_strategy")
            @classmethod
            def _v_opening_strategy(cls, v: str) -> str:
                return _require_tag(v, "opening_strategy")

            @field_validator("closing_trigger")
            @classmethod
            def _v_closing_trigger(cls, v: str) -> str:
                return _require_tag(v, "closing_trigger")

            @field_validator("core_selling_points")
            @classmethod
            def _v_core_selling_points(cls, v: List[str]) -> List[str]:
                if not v or len(v) == 0:
                    raise ValueError("core_selling_points must contain at least 1 item")
                cleaned: List[str] = []
                for item in v[:5]:
                    cleaned.append(_require_tag(item, "core_selling_points[]"))
                return cleaned

            @field_validator("dominant_emotion")
            @classmethod
            def _v_dominant_emotion(cls, v: str) -> str:
                vv = _require_non_empty(v, "dominant_emotion")
                allowed = {"Excitement", "Anxiety", "Curiosity", "Humor", "Trust"}
                if vv not in allowed:
                    raise ValueError(f"dominant_emotion must be one of {sorted(allowed)}")
                return vv

        class InnovationCheck(BaseModel):
            is_innovative: bool = Field(..., description="Whether there is a novel tactic")
            unique_tactic_desc: str = Field("", description="One-line description; empty if none")

        class IntentAnalysisOutput(BaseModel):
            narrative_analysis: NarrativeAnalysis
            tactical_breakdown: TacticalBreakdown
            innovation_check: InnovationCheck
        
        structured_llm = llm.with_structured_output(IntentAnalysisOutput)
        
        # 调用 LLM（带超时控制）
        start_time = time.time()
        try:
            response = structured_llm.invoke([
                SystemMessage(content=prompt_template),
                HumanMessage(content=intent_analysis)
            ])
        except Exception as structured_error:
            # Fallback: ask for raw JSON and validate with pydantic (handles "Extra data"/code fences).
            logger.warning(f"⚠️ [结构化] materialId={material_id} - 结构化输出失败，尝试fallback: {structured_error}")
            fallback_prompt = prompt_template + """

重要提示（必须遵守）：
- 只输出 JSON 对象（不要Markdown，不要代码块，不要解释）。
- 字段必须齐全且非空，不得输出 Unknown。
"""
            raw = llm.invoke([
                SystemMessage(content=fallback_prompt),
                HumanMessage(content=intent_analysis)
            ])
            content = (raw.content if hasattr(raw, "content") else str(raw)).strip()
            content = content.replace("```json", "").replace("```", "").strip()
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise structured_error
            parsed = json.loads(content[start:end + 1])
            response = IntentAnalysisOutput.model_validate(parsed)
        elapsed = time.time() - start_time
        
        if elapsed > timeout:
            logger.warning(f"⚠️ [结构化] materialId={material_id} - 处理时间 {elapsed:.2f}s 超过超时阈值 {timeout}s")
        
        structured_dict = response.model_dump()
        
        logger.info(f"✅ [结构化] materialId={material_id} - 解析成功，耗时 {elapsed:.2f}s")
        return StructuredIntentResult(
            materialId=material_id,
            structured_intent=structured_dict,
            success=True
        )
    
    except (ValidationError, json.JSONDecodeError, Exception) as e:
        logger.error(f"❌ [结构化] materialId={material_id} - 解析失败: {e}")
        return StructuredIntentResult(
            materialId=material_id,
            structured_intent={},
            success=False,
            error=str(e)
        )


def extract_videos_from_vkdb_response(vkdb_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从 VikingDB 响应中提取视频数据
    
    Returns:
        List[{"materialId": str, "intent_analysis": str}]
    """
    result = vkdb_response.get("result", {})
    data = result.get("data", [])
    
    videos = []
    for item in data:
        if not isinstance(item, dict):
            continue
        
        fields = item.get("fields", {})
        intent_analysis = fields.get("intent_analysis", "")
        
        # 提取 materialId
        join_info = extract_join_info_from_vkdb_item(item)
        material_id = join_info.material_id
        
        if not material_id:
            logger.warning(f"⚠️ [提取] 跳过无 materialId 的记录")
            continue
        
        if not intent_analysis or not intent_analysis.strip():
            logger.warning(f"⚠️ [提取] materialId={material_id} - 无 intent_analysis，跳过")
            continue
        
        videos.append({
            "materialId": material_id,
            "intent_analysis": intent_analysis
        })
    
    return videos


def structurize_intents_batch(
    vkdb_response: Dict[str, Any],
    settings: AppSettings,
    concurrency: Optional[int] = None,
    timeout: Optional[int] = None
) -> List[StructuredIntentResult]:
    """
    批量并发解析意图分析
    
    Args:
        vkdb_response: VikingDB 搜索结果
        settings: 应用配置
        concurrency: 并发数（默认使用配置值）
        timeout: 单条超时时间（默认使用配置值）
    
    Returns:
        List[StructuredIntentResult]
    """
    concurrency = concurrency or settings.intent_structurize_concurrency
    timeout = timeout or settings.intent_structurize_timeout
    
    # 提取视频数据
    videos = extract_videos_from_vkdb_response(vkdb_response)
    total_count = len(videos)
    
    if total_count == 0:
        logger.warning("⚠️ [批量结构化] 没有可解析的视频数据")
        return []
    
    logger.info(f"🚀 [批量结构化] 开始处理 {total_count} 条数据，并发数: {concurrency}, 超时: {timeout}s")
    
    # 加载 Prompt 模板
    prompt_template = load_intent_prompt()
    
    # 初始化 LLM
    llm = ChatTongyi(
        model=settings.qwen_model,
        temperature=settings.qwen_temperature
    )
    
    # 并发处理
    results: List[StructuredIntentResult] = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # 提交所有任务
        future_to_video = {
            executor.submit(
                parse_single_intent_analysis,
                video["materialId"],
                video["intent_analysis"],
                llm,
                prompt_template,
                timeout
            ): video["materialId"]
            for video in videos
        }
        
        # 收集结果
        completed = 0
        for future in as_completed(future_to_video):
            material_id = future_to_video[future]
            try:
                result = future.result(timeout=timeout + 5)  # 额外5秒缓冲
                results.append(result)
                completed += 1
                
                if completed % 10 == 0:
                    logger.info(f"📊 [批量结构化] 进度: {completed}/{total_count}")
            
            except FutureTimeoutError:
                logger.error(f"❌ [批量结构化] materialId={material_id} - 任务超时")
                results.append(StructuredIntentResult(
                    materialId=material_id,
                    structured_intent={},
                    success=False,
                    error="Task timeout"
                ))
            except Exception as e:
                logger.error(f"❌ [批量结构化] materialId={material_id} - 任务异常: {e}")
                results.append(StructuredIntentResult(
                    materialId=material_id,
                    structured_intent={},
                    success=False,
                    error=str(e)
                ))
    
    elapsed = time.time() - start_time
    success_count = sum(1 for r in results if r.success)
    success_rate = (success_count / total_count * 100) if total_count > 0 else 0
    
    logger.info(f"✅ [批量结构化] 完成！总耗时: {elapsed:.2f}s, 成功: {success_count}/{total_count} ({success_rate:.1f}%)")
    
    # 性能检查
    if elapsed > 30:
        logger.warning(f"⚠️ [批量结构化] 总耗时 {elapsed:.2f}s 超过30秒目标")
    
    return results

