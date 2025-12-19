from __future__ import annotations

import json
from typing import Any, Dict

from langchain_core.tools import StructuredTool

from src.core.settings import AppSettings
from src.domain.state import FrontendSearchInput
from src.infra.vkdb.client import MULTI_MODAL_PATH, VikingDBDataClient, build_influencer_filter, parse_output_fields


def _build_vkdb_request(settings: AppSettings, user_input: FrontendSearchInput) -> Dict[str, Any]:
    influence = (user_input.influence or "").strip()
    text = (user_input.text or "").strip()
    image = (user_input.image or "").strip()
    video = (user_input.video or "").strip()

    if not text and influence:
        text = influence

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
    if image:
        req_body["image"] = image
    if video:
        vmap: Dict[str, Any] = {"value": video}
        if user_input.video_fps is not None:
            vmap["fps"] = float(user_input.video_fps)
        req_body["video"] = vmap

    if settings.vikingdb_enable_influence_filter and influence:
        req_body["filter"] = build_influencer_filter(influence)

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
    def _run(**kwargs: Any) -> str:
        user_input = FrontendSearchInput.model_validate(kwargs)
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


