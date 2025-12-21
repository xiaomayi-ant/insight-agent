from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(dotenv_path: str = ".env", override: bool = False) -> None:
    """
    Lightweight .env loader (no python-dotenv dependency).
    - Supports: KEY=VALUE
    - Supports: # comments
    - Supports: quoted VALUE (single/double quotes)
    """
    p = Path(dotenv_path)
    if not p.exists():
        return

    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()

        if k.startswith("export "):
            k = k[len("export ") :].strip()

        # Check if value is quoted before processing
        is_quoted = len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'"))
        
        # Remove inline comments (everything after #) only for non-quoted values
        # Quoted values may contain # as part of the value itself
        if not is_quoted and "#" in v:
            v = v.split("#", 1)[0].strip()
        
        # Remove quotes after handling comments
        if is_quoted:
            v = v[1:-1]

        if not override and k in os.environ:
            continue
        os.environ[k] = v


