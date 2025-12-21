from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """聊天请求模型"""
    
    message: str = Field(..., description="用户输入的消息")
    system_prompt: str | None = Field(None, description="可选的系统提示词")


class ChatMessage(BaseModel):
    """聊天消息模型（用于前端）"""
    
    role: str = Field(..., description="消息角色: user 或 assistant")
    content: str = Field(..., description="消息内容")
