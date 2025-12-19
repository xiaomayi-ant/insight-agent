#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os

from src.services.vkdb_mysql_service import VkdbMysqlJoinRequest, vkdb_to_mysql_join


def _env(key: str, default: str = "") -> str:
    v = os.getenv(key, default)
    return "" if v is None else str(v)


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def main() -> None:
    req = VkdbMysqlJoinRequest(
        env_file=_env("ENV_FILE", ".env"),
        influencer=_env("INFLUENCER", "李诞").strip(),
        vkdb_limit=_env_int("VKDB_LIMIT", 100),
        mysql_table=_env("MYSQL_TABLE", "mandasike_qianchuan_room_daily_dimension").strip(),
        mysql_max_in=_env_int("MYSQL_MAX_IN", 100),
        mysql_max_rows=_env_int("MYSQL_MAX_ROWS", 5000),
    )

    out = vkdb_to_mysql_join(req)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


