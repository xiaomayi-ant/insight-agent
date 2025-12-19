## LangGraph（vkdb_graph）MVP

最简工作流：

- **START**：接收前端输入 JSON
- **TOOL**：调用 VikingDB multi_modal search（`src/infra/vkdb/client.py`）
- **LLM**：Qwen（DashScope）做结构化汇总（Pydantic schema）
- **END**：返回结构化结果

### 依赖

在项目根目录：

```bash
pip install -r requirements.txt
```

### 开发安装（推荐：解决任意目录运行时的 import 问题）

把本项目安装成 editable（会把 `vkdb_mysql_join.py` 等模块安装到当前 venv 的 site-packages）：

```bash
pip install -e .
```

如果你使用 uv：

```bash
uv pip install -e .
```

### 环境变量（示例）

把这些写进项目根目录的 `.env`：

```bash
VIKINGDB_AK=...
VIKINGDB_SK=...
VIKINGDB_HOST=...
VIKINGDB_COLLECTION_NAME=...
# 可选
VIKINGDB_REGION=cn-beijing
VIKINGDB_INDEX_NAME=
VIKINGDB_LIMIT=10
VIKINGDB_OUTPUT_FIELDS=video_id,landscape_video,influencer,video_duration,content_structure

DASHSCOPE_API_KEY=...
QWEN_MODEL=qwen-turbo
```

### 运行（stdin JSON，模拟前端）

在项目根目录执行：

```bash
echo '{"influence":"李诞","limit":5}' | python3 -m src.graphs.vkdb_graph.runtime
```

stdout 会输出最终 state（包含 `vkdb_response` 和 `summary`）。

### 运行测试

推荐：

```bash
python -m pytest -q
```

如果你想直接运行单测文件（在任意目录都可以），需要先执行上面的 `pip install -e .`：

```bash
python /Users/masync/Desktop/py/Insight-agent/tests/test_vkdb_mysql_join.py
```

---

## FastAPI 微服务（后端对接前端）

安装依赖（在项目根目录）：

```bash
pip install -r requirements.txt
```

启动服务：

```bash
python3 main.py
```

接口：

- `GET /v1/health`
- `POST /v1/vkdb/search`：VikingDB 原始搜索结果（不走 LLM）
- `POST /v1/vkdb/summary`：VikingDB + Qwen 结构化总结
- `POST /v1/vkdb/mysql-join`：VikingDB → 抽 material_id → MySQL join → ROI2 分析

示例：

```bash
curl -s http://127.0.0.1:8000/v1/health
```
