#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json

from langchain_core.runnables import RunnableLambda, RunnableSequence

from src.infra.mysql.tools import analyze_roi2_rows, compose_mysql_sql, load_inputs_from_env, query_mysql


def main() -> None:
    init = load_inputs_from_env()
    pipeline = RunnableSequence(
        RunnableLambda(lambda _: init),
        RunnableLambda(lambda x: compose_mysql_sql.invoke(x)),
        RunnableLambda(lambda x: query_mysql.invoke({"sql": x["sql"]})),
        RunnableLambda(lambda x: analyze_roi2_rows.invoke({"rows": x["rows"]})),
    )
    out = pipeline.invoke(None)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


