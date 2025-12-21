from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool

from src.core.settings import AppSettings
from src.domain.state import FrontendSearchInput
from src.infra.vkdb.client import MULTI_MODAL_PATH, RANDOM_PATH, VikingDBDataClient, build_influencer_filter, parse_output_fields


def _build_vkdb_request(settings: AppSettings, user_input: FrontendSearchInput) -> Dict[str, Any]:
    import logging
    logger = logging.getLogger(__name__)
    
    influence = (user_input.influence or "").strip()
    text = (user_input.text or "").strip()
    image = (user_input.image or "").strip()
    video = (user_input.video or "").strip()

    if not text and influence:
        text = influence
        logger.info(f"🔄 [VikingDB] text为空，使用influence作为text: {text}")

    limit = user_input.limit if user_input.limit is not None else settings.vikingdb_default_limit
    need_instruction = user_input.need_instruction if user_input.need_instruction is not None else settings.vikingdb_need_instruction
    output_fields = (
        user_input.output_fields
        if user_input.output_fields is not None
        else parse_output_fields(settings.vikingdb_default_output_fields)
    )

    req_body: Dict[str, Any] = {
        "collection_name": settings.vikingdb_collection_name,
        "index_name": settings.resolve_index_name(),
        "limit": int(limit),
        "output_fields": output_fields,
    }

    if text:
        req_body["text"] = text
        req_body["need_instruction"] = bool(need_instruction)
        logger.info(f"✅ [VikingDB] 添加text参数: {text[:50]}...")
    else:
        logger.warning(f"⚠️ [VikingDB] text参数为空，可能导致API错误")
    
    if image:
        req_body["image"] = image
        logger.info(f"✅ [VikingDB] 添加image参数")
    if video:
        vmap: Dict[str, Any] = {"value": video}
        if user_input.video_fps is not None:
            vmap["fps"] = float(user_input.video_fps)
        req_body["video"] = vmap
        logger.info(f"✅ [VikingDB] 添加video参数")

    if settings.vikingdb_enable_influence_filter and influence:
        req_body["filter"] = build_influencer_filter(influence)
        logger.info(f"✅ [VikingDB] 添加filter参数: influencer={influence}")

    logger.info(f"📋 [VikingDB] 最终请求体: text={'有' if text else '无'}, image={'有' if image else '无'}, video={'有' if video else '无'}, filter={'有' if req_body.get('filter') else '无'}")
    
    # 记录完整的请求参数用于诊断缓存问题
    import time
    request_id = f"{int(time.time() * 1000)}"  # 毫秒时间戳作为请求ID
    logger.info(f"🔍 [VikingDB诊断] 请求ID: {request_id}")
    logger.info(f"🔍 [VikingDB诊断] 完整请求参数: {json.dumps(req_body, ensure_ascii=False, sort_keys=True)}")
    
    return req_body


def vkdb_multi_modal_search(settings: AppSettings, user_input: FrontendSearchInput) -> Dict[str, Any]:
    req_body = _build_vkdb_request(settings, user_input)
    client = VikingDBDataClient(
        ak=settings.vikingdb_ak,
        sk=settings.vikingdb_sk,
        host=settings.vikingdb_host,
        region=settings.vikingdb_region,
        service=settings.vikingdb_service,
        timeout_s=settings.vikingdb_timeout_s,
    )
    return client.post_json(MULTI_MODAL_PATH, req_body)


def make_vkdb_search_tool(settings: AppSettings) -> StructuredTool:
    """
    StructuredTool 需要显式的参数签名，否则 **kwargs 会被过滤掉，
    导致 model_validate 收到默认空值（text/influence 变空）。
    """

    def _run(
        influence: str = "",
        text: str = "",
        image: str = "",
        video: str = "",
        video_fps: Optional[float] = None,
        limit: Optional[int] = None,
        need_instruction: Optional[bool] = None,
        output_fields: Optional[List[str]] = None,
    ) -> str:
        user_input = FrontendSearchInput(
            influence=influence,
            text=text,
            image=image,
            video=video,
            video_fps=video_fps,
            limit=limit,
            need_instruction=need_instruction,
            output_fields=output_fields,
        )
        resp = vkdb_multi_modal_search(settings, user_input)
        return json.dumps(resp, ensure_ascii=False)

    return StructuredTool.from_function(
        func=_run,
        name="vkdb_multi_modal_search",
        description=(
            "Search VikingDB via multi_modal endpoint. "
            "Input: influence/text/image/video/video_fps/limit/need_instruction/output_fields. "
            "Output: raw JSON string response."
        ),
    )


def _build_random_request(settings: AppSettings, user_input: FrontendSearchInput) -> Dict[str, Any]:
    """构建随机检索请求"""
    import logging
    logger = logging.getLogger(__name__)
    
    influence = (user_input.influence or "").strip()
    limit = user_input.limit if user_input.limit is not None else settings.vikingdb_default_limit
    output_fields = (
        user_input.output_fields
        if user_input.output_fields is not None
        else parse_output_fields(settings.vikingdb_default_output_fields)
    )
    
    req_body: Dict[str, Any] = {
        "collection_name": settings.vikingdb_collection_name,
        "index_name": settings.resolve_index_name(),
        "limit": int(limit),
        "output_fields": output_fields,
    }
    
    # 添加influencer过滤
    if settings.vikingdb_enable_influence_filter and influence:
        req_body["filter"] = build_influencer_filter(influence)
        logger.info(f"✅ [VikingDB随机检索] 添加filter参数: influencer={influence}")
    
    logger.info(f"📋 [VikingDB随机检索] 请求体: filter={'有' if req_body.get('filter') else '无'}, limit={limit}")
    logger.info(f"🔍 [VikingDB随机检索] 完整请求参数: {json.dumps(req_body, ensure_ascii=False, sort_keys=True)}")
    
    return req_body


def vkdb_random_search(settings: AppSettings, user_input: FrontendSearchInput) -> Dict[str, Any]:
    """执行随机检索"""
    req_body = _build_random_request(settings, user_input)
    client = VikingDBDataClient(
        ak=settings.vikingdb_ak,
        sk=settings.vikingdb_sk,
        host=settings.vikingdb_host,
        region=settings.vikingdb_region,
        service=settings.vikingdb_service,
        timeout_s=settings.vikingdb_timeout_s,
    )
    return client.post_json(RANDOM_PATH, req_body)


def make_vkdb_random_search_tool(settings: AppSettings) -> StructuredTool:
    """创建随机检索工具"""
    def _run(
        influence: str = "",
        limit: Optional[int] = None,
        output_fields: Optional[List[str]] = None,
    ) -> str:
        user_input = FrontendSearchInput(
            influence=influence,
            limit=limit,
            output_fields=output_fields,
        )
        resp = vkdb_random_search(settings, user_input)
        return json.dumps(resp, ensure_ascii=False)
    
    return StructuredTool.from_function(
        func=_run,
        name="vkdb_random_search",
        description=(
            "Search VikingDB via random endpoint. "
            "Input: influence/limit/output_fields. "
            "Output: raw JSON string response."
        ),
    )

