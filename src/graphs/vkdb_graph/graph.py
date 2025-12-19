from __future__ import annotations

import json
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from src.core.settings import AppSettings
from src.domain.state import FrontendSearchInput, GraphState, VkdbSummary
from src.graphs.vkdb_graph.tools import make_vkdb_search_tool


def _vkdb_search_node(settings: AppSettings):
    tool = make_vkdb_search_tool(settings)

    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        s = GraphState.model_validate(state)
        tool_out = tool.invoke(s.input.model_dump())
        try:
            vkdb_response = json.loads(tool_out)
        except Exception as e:
            return {"error": f"vkdb tool returned non-json: {e}", "vkdb_response": None}
        return {"vkdb_response": vkdb_response}

    return _node


def _llm_summarize_node(settings: AppSettings):
    from langchain_community.chat_models import ChatTongyi  # pylint: disable=import-outside-toplevel

    llm = ChatTongyi(model=settings.qwen_model, temperature=settings.qwen_temperature)

    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        s = GraphState.model_validate(state)
        if s.error:
            return {}
        if not s.vkdb_response:
            return {"error": "missing vkdb_response"}

        query = FrontendSearchInput.model_validate(s.input.model_dump())

        system = SystemMessage(
            content=(
                "You are a data analyst. Summarize the VikingDB search result.\n"
                "Return ONLY a JSON object that matches the required schema.\n"
                "Do NOT output markdown. Do NOT wrap in code fences."
            )
        )
        human = HumanMessage(
            content=(
                "Required JSON schema (Pydantic):\n"
                f"{json.dumps(VkdbSummary.model_json_schema(), ensure_ascii=False)}\n\n"
                "User query:\n"
                f"{query.model_dump_json(ensure_ascii=False)}\n\n"
                "VikingDB response JSON:\n"
                f"{json.dumps(s.vkdb_response, ensure_ascii=False)}"
            )
        )

        try:
            structured_llm = llm.with_structured_output(VkdbSummary)
            summary_obj = structured_llm.invoke([system, human])
            summary = summary_obj.model_copy(update={"query": query})
            return {"summary": summary.model_dump()}
        except Exception:
            resp_msg = llm.invoke([system, human])
            raw = getattr(resp_msg, "content", "") or ""
            try:
                data = json.loads(raw)
                summary = VkdbSummary.model_validate({**data, "query": query.model_dump()})
                return {"summary": summary.model_dump()}
            except Exception as e:
                return {"error": f"failed to parse llm summary json: {e}"}

    return _node


def build_graph(settings: AppSettings):
    g = StateGraph(dict)
    g.add_node("vkdb_search", _vkdb_search_node(settings))
    g.add_node("llm_summarize", _llm_summarize_node(settings))

    g.add_edge(START, "vkdb_search")
    g.add_edge("vkdb_search", "llm_summarize")
    g.add_edge("llm_summarize", END)
    return g.compile()


