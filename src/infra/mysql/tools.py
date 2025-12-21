from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymysql
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.core.dotenv import load_dotenv


def env(key: str, default: Optional[str] = None, required: bool = False) -> str:
    v = os.getenv(key, default)
    if required and (v is None or str(v).strip() == ""):
        raise RuntimeError(f"Missing required env: {key}")
    return "" if v is None else str(v)


def env_int(key: str, default: int) -> int:
    v = os.getenv(key)
    if v is None or v.strip() == "":
        return default
    return int(v)


INFLUENCER_ALLOWED = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9 \t\.\-_\(\)（）·]+$")
MATERIAL_ID_ALLOWED = re.compile(r"^[A-Za-z0-9_\-\.]+$")


def escape_sql_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "''")


def escape_like_pattern(s: str) -> str:
    s = s.replace("\\", "\\\\")
    s = s.replace("%", r"\%").replace("_", r"\_")
    return s


def parse_material_ids(raw: str, max_n: int) -> List[str]:
    ids: List[str] = []
    seen = set()
    for part in (raw or "").split(","):
        x = part.strip()
        if not x or x in seen:
            continue
        if not MATERIAL_ID_ALLOWED.match(x):
            raise ValueError(f"materialId contains illegal chars: {x}")
        seen.add(x)
        ids.append(x)
        if len(ids) >= max_n:
            break
    return ids


class ComposeSqlInput(BaseModel):
    influencer: str = Field(..., description="Influencer name, used in LIKE filter")
    material_ids: List[str] = Field(default_factory=list, description="materialId list used in IN (...)")
    table: str = Field(..., description="MySQL table name")
    require_in: bool = Field(default=True, description="If true and material_ids empty, force empty-result query (WHERE 1=0)")


@tool("compose_mysql_sql", args_schema=ComposeSqlInput)
def compose_mysql_sql(influencer: str, material_ids: List[str], table: str, require_in: bool = True) -> Dict[str, Any]:
    """Compose a MySQL query for ROI2 analysis.

    This tool builds a SELECT statement with:
    - `roi2MaterialVideoName` LIKE '%{influencer}%'
    - Optional `materialId IN (...)` filter (or forced empty result when `require_in=True`)
    """
    if not influencer:
        raise ValueError("influencer is empty")
    if not INFLUENCER_ALLOWED.match(influencer):
        raise ValueError(f"influencer contains illegal chars: {influencer}")

    like_kw = escape_like_pattern(influencer)
    like_expr = f"'%{like_kw}%' ESCAPE '\\\\'"

    material_id_count = len(material_ids)
    if material_id_count == 0 and require_in:
        in_clause = "1=0"
    else:
        if material_id_count == 0:
            in_clause = "1=1"
        else:
            quoted = [f"'{escape_sql_string(x)}'" for x in material_ids]
            in_clause = f"materialId in ({','.join(quoted)})"

    sql = f"""
select
  timeline,                                    -- 数据时间戳
  statCostForRoi2,                            -- 整体消耗
  roi2MaterialVideoName,                      -- 广告素材视频名称
  materialId,                                 -- 素材ID
  roi2MaterialUploadTime,                     -- 广告素材上传时间
  totalPrepayAndPayOrderRoi2,                  -- 整体ROI
  liveShowCountForRoi2V2,                     -- 整体曝光次数
  liveWatchCountForRoi2V2                    -- 整体点击次数
from {table}
where roi2MaterialVideoName like {like_expr}
  and {in_clause}
  and liveShowCountForRoi2V2 > 0
  and liveWatchCountForRoi2V2 > 0
""".strip()

    return {"sql": sql, "influencer": influencer, "material_id_count": material_id_count}


class QueryMySqlInput(BaseModel):
    sql: str = Field(..., description="SQL to execute")
    max_rows: int = Field(default=5000, description="Max rows to fetch")


def _mysql_connect_from_env() -> pymysql.connections.Connection:
    host = env("MYSQL_HOST", required=True)
    port = env_int("MYSQL_PORT", 3306)
    user = env("MYSQL_USER", required=True)
    password = env("MYSQL_PASSWORD", required=True)
    db = env("MYSQL_DB", required=True)
    charset = env("MYSQL_CHARSET", "utf8mb4")
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        db=db,
        charset=charset,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


@tool("query_mysql", args_schema=QueryMySqlInput)
def query_mysql(sql: str, max_rows: int = 5000) -> Dict[str, Any]:
    """Execute a SQL query against MySQL and return at most `max_rows` rows."""
    conn = _mysql_connect_from_env()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchmany(size=max_rows)
        return {"row_count": len(rows), "rows": rows}
    finally:
        conn.close()


class AnalyzeInput(BaseModel):
    rows: List[Dict[str, Any]] = Field(default_factory=list, description="Rows returned from MySQL query")


@tool("analyze_roi2_rows", args_schema=AnalyzeInput)
def analyze_roi2_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate ROI2 rows by `materialId` and return sorted per-material metrics."""
    total = len(rows)
    agg: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        mid = str(r.get("materialId") or "")
        if not mid:
            continue
        bucket = agg.setdefault(
            mid,
            {
                "materialId": mid,
                "roi2MaterialVideoName": r.get("roi2MaterialVideoName"),
                "timeline_count": 0,
                "sum_statCostForRoi2": 0.0,
                "sum_liveShowCountForRoi2V2": 0.0,
            },
        )
        bucket["timeline_count"] += 1

        sc = r.get("statCostForRoi2")
        lc = r.get("liveShowCountForRoi2V2")
        try:
            bucket["sum_statCostForRoi2"] += float(sc) if sc is not None else 0.0
        except Exception:
            pass
        try:
            bucket["sum_liveShowCountForRoi2V2"] += float(lc) if lc is not None else 0.0
        except Exception:
            pass

    by_material = sorted(
        agg.values(),
        key=lambda x: (x["sum_statCostForRoi2"], x["sum_liveShowCountForRoi2V2"]),
        reverse=True,
    )

    return {"total_rows": total, "unique_materials": len(agg), "by_material": by_material}


def load_inputs_from_env() -> Dict[str, Any]:
    dotenv = env("ENV_FILE", ".env")
    load_dotenv(dotenv, override=False)

    influencer = env("VIKINGDB_INFLUENCE", required=True).strip()
    raw_ids = env("MATERIAL_IDS", "").strip()
    max_in = env_int("MYSQL_MAX_IN", 100)
    material_ids = parse_material_ids(raw_ids, max_n=max_in)
    table = env("MYSQL_TABLE", "mandasike_qianchuan_room_daily_dimension")

    return {"influencer": influencer, "material_ids": material_ids, "table": table}


