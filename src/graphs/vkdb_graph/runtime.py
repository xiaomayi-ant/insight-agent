from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

from src.core.settings import load_settings
from src.domain.state import FrontendSearchInput, GraphState
from src.graphs.vkdb_graph.graph import build_graph


def _read_stdin_json() -> Optional[Dict[str, Any]]:
    if sys.stdin.isatty():
        return None
    raw = sys.stdin.read()
    if raw is None or raw.strip() == "":
        return None
    return json.loads(raw)


def run_once(frontend_payload: Dict[str, Any]) -> Dict[str, Any]:
    settings = load_settings()
    graph = build_graph(settings)

    user_input = FrontendSearchInput.model_validate(frontend_payload)
    state = GraphState(input=user_input).model_dump()
    out = graph.invoke(state)
    return out


def main() -> int:
    payload = _read_stdin_json()
    if payload is None:
        print(
            "Missing input. Provide frontend JSON via stdin.\n"
            'Example:\n  echo \'{"influence":"李诞","limit":5}\' | python3 -m src.graphs.vkdb_graph.runtime',
            file=sys.stderr,
        )
        return 2

    out = run_once(payload)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if out.get("error"):
        print(f"[ERROR] {out['error']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


