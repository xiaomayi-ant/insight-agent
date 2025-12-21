# Insight Agent

基于 LangGraph 的智能 Agent 服务，通过意图分析自动判断执行路径。

## 架构

主要链路：前端 → `/v1/chat/stream` → `agent_graph` → 返回流式响应

### Agent Graph 工作流

1. **意图分析节点** (`intent_analysis_node`)：判断用户意图
   - 如果需要工具：路由到 `vkdb_search`
   - 如果只是聊天：路由到 `simple_chat`

2. **VikingDB 搜索节点** (`vkdb_search_node`)：搜索视频数据

3. **MySQL Join 节点** (`mysql_join_node`)：从 VikingDB 结果提取 material_id，Join MySQL 进行 ROI2 分析

4. **LLM 汇总节点** (`llm_summarize_node`)：汇总 VikingDB 和 MySQL 结果，生成最终回复

5. **简单聊天节点** (`simple_chat_node`)：直接使用 LLM 回复

## 安装

### 依赖安装

在项目根目录：

```bash
pip install -r requirements.txt
```

### 开发安装（推荐）

把本项目安装成 editable：

```bash
pip install -e .
```

如果使用 uv：

```bash
uv pip install -e .
```

## 配置

在项目根目录创建 `.env` 文件：

```bash
# DashScope (Qwen) 配置（必需）
DASHSCOPE_API_KEY=...
QWEN_MODEL=qwen-turbo
QWEN_TEMPERATURE=0.0

# VikingDB 配置（必需）
VIKINGDB_AK=...
VIKINGDB_SK=...
VIKINGDB_HOST=...
VIKINGDB_COLLECTION_NAME=...
VIKINGDB_REGION=cn-beijing
VIKINGDB_INDEX_NAME=
VIKINGDB_LIMIT=100
VIKINGDB_OUTPUT_FIELDS=video_id,landscape_video,influencer,video_duration,content_structure

# MySQL 配置（可选，如果使用 MySQL Join 功能）
MYSQL_HOST=...
MYSQL_PORT=3306
MYSQL_USER=...
MYSQL_PASSWORD=...
MYSQL_DB=...
MYSQL_TABLE=mandasike_qianchuan_room_daily_dimension

# CORS 配置（可选，默认允许 localhost:3000）
CORS_ORIGINS=http://localhost:3000
```

## 运行

### 启动服务

```bash
python3 main.py
```

服务将运行在 `http://localhost:8000`

### API 接口

- `GET /v1/health`：健康检查
- `POST /v1/chat/stream`：统一聊天流式 API（Agent Graph 模式）

### 示例

健康检查：

```bash
curl -s http://127.0.0.1:8000/v1/health
```

聊天请求（SSE 流式响应）：

```bash
curl -X POST http://127.0.0.1:8000/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "查找李诞的视频", "system_prompt": null}'
```

## 测试

运行测试：

```bash
python -m pytest -q
```
