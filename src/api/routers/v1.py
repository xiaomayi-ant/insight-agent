from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from src.services.agent_service import agent_stream
from src.domain.chat import ChatRequest

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True}


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


