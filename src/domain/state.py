from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


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


