from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from src.services.vkdb_graph_service import vkdb_search_raw, vkdb_summary
from src.services.vkdb_mysql_service import VkdbMysqlJoinRequest, vkdb_to_mysql_join
from src.services.agent_service import agent_stream

from src.domain.state import FrontendSearchInput, VkdbSummary
from src.domain.chat import ChatRequest

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


@router.post("/chat/stream")
async def post_chat_stream(payload: ChatRequest) -> StreamingResponse:
    """
    统一聊天流式API（Agent Graph模式）
    
    所有前端请求都通过这个端点，由Agent Graph的意图分析节点自动判断和执行：
    - 如果需要工具：走固定串行流程（VikingDB → MySQL → LLM汇总）
    - 如果不需要工具：直接LLM回复
    
    接收用户消息（纯文本），返回SSE格式的流式响应
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # 配置日志级别为INFO，确保能看到节点执行日志
    logging.basicConfig(level=logging.INFO)
    
    try:
        logger.info(f"📨 [API] 收到聊天请求: message={payload.message[:50]}...")
        return StreamingResponse(
            agent_stream(payload.message, payload.system_prompt),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用Nginx缓冲
            },
        )
    except Exception as e:
        logger.error(f"❌ [API错误] 聊天流式API错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


