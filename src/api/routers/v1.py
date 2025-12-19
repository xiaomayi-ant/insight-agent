from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.services.vkdb_graph_service import vkdb_search_raw, vkdb_summary
from src.services.vkdb_mysql_service import VkdbMysqlJoinRequest, vkdb_to_mysql_join

from src.domain.state import FrontendSearchInput, VkdbSummary

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.post("/vkdb/search", response_model=dict)
def post_vkdb_search(payload: FrontendSearchInput) -> dict:
    try:
        return vkdb_search_raw(payload.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vkdb/summary", response_model=VkdbSummary)
def post_vkdb_summary(payload: FrontendSearchInput) -> VkdbSummary:
    try:
        summary_dict = vkdb_summary(payload.model_dump())
        return VkdbSummary.model_validate(summary_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vkdb/mysql-join", response_model=dict)
def post_vkdb_mysql_join(payload: VkdbMysqlJoinRequest) -> dict:
    try:
        return vkdb_to_mysql_join(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


