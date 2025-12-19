from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field

from src.core.dotenv import load_dotenv
from src.infra.mysql.tools import analyze_roi2_rows, compose_mysql_sql, query_mysql
from src.infra.vkdb.client import MULTI_MODAL_PATH, VikingDBDataClient, build_influencer_filter, parse_output_fields
from src.infra.vkdb.join import extract_join_info_from_vkdb_item


class VkdbMysqlJoinRequest(BaseModel):
    """
    Request for: VikingDB -> extract material_id -> MySQL join -> ROI2 analysis.

    Defaults are aligned with the existing `run_vkdb_to_mysql.py` script.
    """

    env_file: str = Field(default=".env", description="dotenv path to load")

    influencer: str = Field(default="李诞", description="Influencer name")
    vkdb_limit: int = Field(default=100, ge=1, le=1000, description="VikingDB search limit")

    mysql_table: str = Field(
        default="mandasike_qianchuan_room_daily_dimension",
        description="MySQL table name (recommended to keep fixed on server side)",
    )
    mysql_max_in: int = Field(default=100, ge=1, le=500, description="Max extracted material_ids to use in SQL IN")
    mysql_max_rows: int = Field(default=5000, ge=1, le=50000, description="Max rows to fetch from MySQL")

    require_in: bool = Field(default=True, description="If true and material_ids empty, force empty-result query")


def _env(key: str, default: str = "", required: bool = False) -> str:
    v = os.getenv(key, default)
    if required and (v is None or str(v).strip() == ""):
        raise RuntimeError(f"Missing required env: {key}")
    return "" if v is None else str(v)


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _build_vkdb_request(influencer: str, limit: int) -> Dict[str, Any]:
    collection = _env("VIKINGDB_COLLECTION_NAME", required=True)
    index = _env("VIKINGDB_INDEX_NAME", "").strip() or collection

    output_fields_env = _env(
        "VIKINGDB_OUTPUT_FIELDS",
        "video_id,landscape_video,influencer,video_duration,content_structure",
    )
    output_fields = parse_output_fields(output_fields_env)

    req: Dict[str, Any] = {
        "collection_name": collection,
        "index_name": index,
        "limit": int(limit),
        "output_fields": output_fields,
    }

    text = _env("VIKINGDB_TEXT", "").strip() or influencer
    if text:
        req["text"] = text
        req["need_instruction"] = _env("VIKINGDB_NEED_INSTRUCTION", "true").strip().lower() in {"1", "true", "yes", "y"}

    enable_filter = _env("VIKINGDB_ENABLE_INFLUENCE_FILTER", "true").strip().lower() in {"1", "true", "yes", "y"}
    if enable_filter and influencer:
        req["filter"] = build_influencer_filter(influencer)

    return req


def _vkdb_search(influencer: str, limit: int) -> Dict[str, Any]:
    client = VikingDBDataClient(
        ak=_env("VIKINGDB_AK", required=True),
        sk=_env("VIKINGDB_SK", required=True),
        host=_env("VIKINGDB_HOST", required=True),
        region=_env("VIKINGDB_REGION", "cn-beijing"),
        service=_env("VIKINGDB_SERVICE", "vikingdb"),
        timeout_s=_env_int("VIKINGDB_TIMEOUT_S", 60),
    )
    req = _build_vkdb_request(influencer=influencer, limit=limit)
    return client.post_json(MULTI_MODAL_PATH, req)


def _extract_material_ids_and_tos(vkdb_resp: Dict[str, Any], max_n: int) -> Tuple[List[str], List[str]]:
    result = vkdb_resp.get("result") or {}
    data = result.get("data") or []
    if not isinstance(data, list):
        return ([], [])

    material_ids: List[str] = []
    tos_urls: List[str] = []
    seen_ids = set()

    for item in data:
        if not isinstance(item, dict):
            continue
        join_info = extract_join_info_from_vkdb_item(item)
        if join_info.tos_url:
            tos_urls.append(join_info.tos_url)

        mid = join_info.material_id
        if not mid:
            continue
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        material_ids.append(mid)
        if len(material_ids) >= max_n:
            break

    return (material_ids, tos_urls)


def vkdb_to_mysql_join(req: VkdbMysqlJoinRequest) -> Dict[str, Any]:
    load_dotenv(req.env_file, override=False)

    influencer = (req.influencer or "").strip()
    if not influencer:
        raise RuntimeError("influencer is required")

    vkdb_resp = _vkdb_search(influencer=influencer, limit=req.vkdb_limit)
    returned = len(((vkdb_resp.get("result") or {}).get("data") or [])) if isinstance(vkdb_resp, dict) else 0

    material_ids, tos_urls = _extract_material_ids_and_tos(vkdb_resp, max_n=req.mysql_max_in)
    if not material_ids:
        raise RuntimeError("No material_ids extracted from vkdb landscape_video. Check output_fields and URL format.")

    sql_out = compose_mysql_sql.invoke(
        {
            "influencer": influencer,
            "material_ids": material_ids,
            "table": req.mysql_table,
            "require_in": req.require_in,
        }
    )
    sql = sql_out["sql"]

    mysql_out = query_mysql.invoke({"sql": sql, "max_rows": req.mysql_max_rows})
    analysis = analyze_roi2_rows.invoke({"rows": mysql_out["rows"]})

    return {
        "influencer": influencer,
        "vkdb": {
            "returned": returned,
            "tos_urls": tos_urls,
            "material_ids": material_ids,
        },
        "mysql": {
            "table": req.mysql_table,
            "row_count": mysql_out["row_count"],
        },
        "analysis": analysis,
    }


