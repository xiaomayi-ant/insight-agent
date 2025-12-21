from __future__ import annotations

import json
from typing import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.chat_models import ChatTongyi

from src.core.settings import load_settings


async def chat_stream(user_message: str, system_prompt: str | None = None) -> AsyncIterator[str]:
    """
    流式聊天服务
    
    直接使用ChatTongyi的流式API，绕过LangGraph节点以支持真正的流式输出
    
    Args:
        user_message: 用户输入的消息
        system_prompt: 可选的系统提示词
    
    Yields:
        SSE格式的字符串（data: {...}\n\n）
    """
    settings = load_settings()
    
    # 创建LLM实例
    llm = ChatTongyi(model=settings.qwen_model, temperature=settings.qwen_temperature)
    
    # 构建消息列表
    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=user_message))
    
    try:
        # 发送状态消息
        status_payload = json.dumps(
            {"type": "status", "content": "正在思考..."},
            ensure_ascii=False
        )
        yield f"data: {status_payload}\n\n"
        
        # 直接使用LLM的流式API
        chunk_count = 0
        async for chunk in llm.astream(messages):
            chunk_count += 1
            # chunk是AIMessageChunk类型
            if hasattr(chunk, "content") and chunk.content:
                content = chunk.content
                # 构造token类型的SSE数据
                payload = json.dumps(
                    {"type": "token", "content": content},
                    ensure_ascii=False
                )
                yield f"data: {payload}\n\n"
        
        # 调试信息（可选，可以在生产环境中移除）
        if chunk_count == 0:
            # 如果没有收到任何chunk，可能是流式不支持，尝试非流式调用
            print("警告: 没有收到流式chunk，尝试非流式调用")
            response = await llm.ainvoke(messages)
            if hasattr(response, "content") and response.content:
                # 将完整响应作为单个token发送
                payload = json.dumps(
                    {"type": "token", "content": response.content},
                    ensure_ascii=False
                )
                yield f"data: {payload}\n\n"
        
        # 流结束信号
        yield "data: [DONE]\n\n"
    
    except Exception as e:
        # 错误处理
        import traceback
        error_msg = f"处理消息时出错: {str(e)}\n{traceback.format_exc()}"
        error_payload = json.dumps(
            {"type": "error", "content": error_msg},
            ensure_ascii=False
        )
        yield f"data: {error_payload}\n\n"
        yield "data: [DONE]\n\n"
