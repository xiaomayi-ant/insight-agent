from __future__ import annotations

from typing import Any, Dict

from src.core.settings import load_settings
from src.domain.state import FrontendSearchInput
from src.graphs.vkdb_graph.runtime import run_once
from src.graphs.vkdb_graph.tools import vkdb_multi_modal_search


def vkdb_search_raw(frontend_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Raw VikingDB search (no LLM).
    """
    settings = load_settings()
    user_input = FrontendSearchInput.model_validate(frontend_payload)
    return vkdb_multi_modal_search(settings, user_input)


def vkdb_summary(frontend_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph MVP: vkdb search -> qwen structured summary.
    Returns the summary object as dict.
    """
    out = run_once(frontend_payload)
    summary = out.get("summary")
    if not summary:
        err = out.get("error") or "missing summary"
        raise RuntimeError(err)
    if not isinstance(summary, dict):
        raise RuntimeError("invalid summary type")
    return summary


