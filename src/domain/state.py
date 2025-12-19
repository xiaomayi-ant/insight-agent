from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FrontendSearchInput(BaseModel):
    """
    Frontend request input (LangChain/LangGraph friendly).
    - influence: used for scalar filter; if text is empty, we fallback to text=influence.
    """

    influence: str = ""
    text: str = ""
    image: str = ""
    video: str = ""
    video_fps: Optional[float] = None

    limit: Optional[int] = None
    need_instruction: Optional[bool] = None
    output_fields: Optional[List[str]] = None


class VkdbSummaryItem(BaseModel):
    rank: int
    video_id: Optional[str] = None
    influencer: Optional[str] = None
    score: Optional[float] = None
    ann_score: Optional[float] = None
    landscape_video: Optional[str] = None
    fields_preview: Dict[str, Any] = Field(default_factory=dict)


class VkdbSummary(BaseModel):
    query: FrontendSearchInput
    returned: int
    items: List[VkdbSummaryItem]
    notes: str = ""


class GraphState(BaseModel):
    """
    LangGraph state (single source of truth).
    """

    input: FrontendSearchInput
    vkdb_response: Optional[Dict[str, Any]] = None
    summary: Optional[VkdbSummary] = None
    error: Optional[str] = None


