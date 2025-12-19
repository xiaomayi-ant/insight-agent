from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlsplit


def extract_landscape_video_value(landscape_video: Any) -> str:
    """
    VikingDB `landscape_video` may be:
    - "tos://bucket/key.mp4"
    - {"value": "tos://bucket/key.mp4", ...}
    """
    if landscape_video is None:
        return ""
    if isinstance(landscape_video, str):
        return landscape_video.strip()
    if isinstance(landscape_video, dict):
        v = landscape_video.get("value")
        return str(v).strip() if v is not None else ""
    return ""


def extract_material_id_from_landscape_video(landscape_video_url: str) -> Optional[str]:
    """
    Join key rule:
    - take substring between last "/" and ".mp4"
    - must be digits, otherwise None
    """
    raw = (landscape_video_url or "").strip()
    if not raw:
        return None

    try:
        parsed = urlsplit(raw)
        path = parsed.path or ""
        filename = (path.rsplit("/", 1)[-1] if path else raw.rsplit("/", 1)[-1]).strip()
    except Exception:
        filename = raw.rsplit("/", 1)[-1].strip()

    if not filename:
        return None

    lower = filename.lower()
    idx = lower.rfind(".mp4")
    if idx <= 0:
        return None

    material_id = filename[:idx]
    if not material_id.isdigit():
        return None
    return material_id


@dataclass(frozen=True)
class JoinExtractResult:
    tos_url: str
    material_id: Optional[str]


def extract_join_info_from_vkdb_item(item: dict[str, Any]) -> JoinExtractResult:
    fields = item.get("fields") or {}
    tos_url = extract_landscape_video_value(fields.get("landscape_video"))
    material_id = extract_material_id_from_landscape_video(tos_url)
    return JoinExtractResult(tos_url=tos_url, material_id=material_id)


