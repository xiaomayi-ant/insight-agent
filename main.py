from __future__ import annotations

"""
Root entrypoint.

Rule: the project root keeps only this `main.py`; all other implementation lives in packages.
"""

import uvicorn


def main() -> None:
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()


