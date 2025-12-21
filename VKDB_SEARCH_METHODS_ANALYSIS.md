# VikingDB 检索方法对比分析

## 概述

本文档对比分析了 VikingDB 提供的三种检索方法，以及当前项目中的实际使用情况。

---

## 三种检索方法对比

### 1. 随机检索 (Random Search)
**接口路径**: `/api/vikingdb/data/search/random`

**特点**:
- ✅ **无需查询内容**：不需要提供 text、image、video 等查询参数
- ✅ **随机返回**：从数据集中随机返回指定数量的记录
- ✅ **支持过滤和后处理**：可以配合 filter 参数使用
- ✅ **适用场景**：数据采样、效果对比、数据过滤测试

**请求示例**:
```json
{
    "collection_name": "test_coll",
    "index_name": "idx_1",
    "limit": 2
}
```

**响应特点**:
- 返回结果包含 `score` 和 `ann_score`，但都是固定值（如 1.0）
- 主要用于数据获取，不涉及相似度计算

---

### 2. 标量检索 (Scalar Search)
**接口路径**: `/api/vikingdb/data/search/scalar`

**特点**:
- ✅ **基于标量字段**：必须指定一个 int64 或 float32 类型的字段
- ✅ **需要标量索引**：该字段必须建立了标量索引
- ✅ **排序检索**：按照标量值进行排序（asc/desc）
- ✅ **适用场景**：按价格、时间、评分等标量字段排序检索

**特有参数**:
- `field` (必填): 字段名，必须是 int64 或 float32 类型
- `order` (可选): "asc" 或 "desc"，默认 "desc"

**请求示例**:
```json
{
    "collection_name": "test_coll",
    "index_name": "idx_1",
    "limit": 2,
    "field": "f_price",
    "order": "desc"
}
```

**响应特点**:
- `score` 字段返回的是标量字段的实际值（如价格 999000）
- 不是相似度分数，而是排序依据的标量值

---

### 3. 多模态检索 (Multi-Modal Search)
**接口路径**: `/api/vikingdb/data/search/multi_modal`

**特点**:
- ✅ **多模态支持**：支持文本、图片、视频等多种输入
- ✅ **模态组合**：可以同时使用 text + image、text + video 等组合
- ✅ **向量相似度**：基于向量相似度计算返回结果
- ✅ **Instruction 支持**：支持 `need_instruction` 参数，自动优化查询语句
- ✅ **适用场景**：语义检索、图文检索、视频检索等

**特有参数**:
- `text` (至少选1): 检索的文本内容
- `image` (可选): 图片链接（tos:// 或 http/https）
- `video` (可选): 视频对象 `{"value": "tos://...", "fps": 2.0}`
- `need_instruction` (条件必填): 如果模型支持 instruction，则必填

**请求示例**:
```json
{
    "collection_name": "test_coll_with_vectorize",
    "index_name": "idx_1",
    "text": "向量是指在数学中具有一定大小和方向的量",
    "need_instruction": true,
    "output_fields": ["f_text"],
    "limit": 2
}
```

**响应特点**:
- `score` 和 `ann_score` 是相似度分数（如 9.899999618530273）
- 可能包含 `real_text_query`：实际生效的检索语句（当启用 instruction 时）
- 可能包含 `token_usage`：token 使用统计信息

---

## 当前项目使用情况

### 当前实现
**文件位置**: `src/infra/vkdb/client.py`

**使用的接口**: 
- ✅ **仅使用多模态检索** (`/api/vikingdb/data/search/multi_modal`)
- ❌ **未使用随机检索**
- ❌ **未使用标量检索**

### 项目中的检索实现

**核心代码** (`src/infra/vkdb/client.py`):
```python
MULTI_MODAL_PATH = "/api/vikingdb/data/search/multi_modal"
```

**请求构建** (`src/graphs/agent_graph/tools.py`):
```python
def _build_vkdb_request(settings: AppSettings, user_input: FrontendSearchInput):
    # 支持 text、image、video 参数
    # 支持 need_instruction
    # 支持 filter（用于 influencer 过滤）
    # 支持 output_fields
```

**当前支持的功能**:
1. ✅ 文本检索 (`text`)
2. ✅ 图片检索 (`image`)
3. ✅ 视频检索 (`video` + `video_fps`)
4. ✅ Instruction 优化 (`need_instruction`)
5. ✅ 字段过滤 (`filter` - 用于 influencer)
6. ✅ 输出字段选择 (`output_fields`)

---

## 三种方法的区别总结

| 特性 | 随机检索 | 标量检索 | 多模态检索 |
|------|---------|---------|-----------|
| **查询输入** | 无需查询 | 无需查询（仅排序） | text/image/video |
| **排序依据** | 随机 | 标量字段值 | 向量相似度 |
| **返回 score** | 固定值（1.0） | 标量字段值 | 相似度分数 |
| **适用场景** | 数据采样 | 价格/时间排序 | 语义检索 |
| **索引要求** | 无特殊要求 | 需要标量索引 | 需要向量索引 |
| **项目使用** | ❌ 未使用 | ❌ 未使用 | ✅ 已使用 |

---

## 潜在的使用场景建议

### 1. 随机检索的使用场景
- **数据采样**：从大量数据中随机抽取样本进行分析
- **A/B 测试**：对比不同检索方法的效果
- **数据验证**：验证数据集的完整性和质量

**实现建议**:
```python
# 可以添加随机检索方法
RANDOM_PATH = "/api/vikingdb/data/search/random"

def vkdb_random_search(settings: AppSettings, limit: int) -> Dict[str, Any]:
    req_body = {
        "collection_name": settings.vikingdb_collection_name,
        "index_name": settings.resolve_index_name(),
        "limit": limit
    }
    client = VikingDBDataClient(...)
    return client.post_json(RANDOM_PATH, req_body)
```

### 2. 标量检索的使用场景
- **价格排序**：按商品价格从高到低检索
- **时间排序**：按发布时间排序检索最新内容
- **评分排序**：按用户评分排序检索优质内容

**实现建议**:
```python
# 可以添加标量检索方法
SCALAR_PATH = "/api/vikingdb/data/search/scalar"

def vkdb_scalar_search(
    settings: AppSettings,
    field: str,
    order: str = "desc",
    limit: int = 10
) -> Dict[str, Any]:
    req_body = {
        "collection_name": settings.vikingdb_collection_name,
        "index_name": settings.resolve_index_name(),
        "limit": limit,
        "field": field,
        "order": order
    }
    client = VikingDBDataClient(...)
    return client.post_json(SCALAR_PATH, req_body)
```

---

## 总结

1. **当前项目**：仅实现了多模态检索，完全满足语义检索需求
2. **随机检索**：适合数据采样和测试场景，当前未使用
3. **标量检索**：适合按数值字段排序的场景，当前未使用
4. **建议**：根据业务需求，可以考虑添加随机检索和标量检索的支持，以扩展检索能力

---

## 相关文件

- 文档文件：
  - `search_random.md` - 随机检索文档
  - `searchbyscalar.md` - 标量检索文档
  - `searchbumultimodal.md` - 多模态检索文档

- 代码文件：
  - `src/infra/vkdb/client.py` - VikingDB 客户端实现
  - `src/graphs/agent_graph/tools.py` - 检索工具实现
  - `src/services/vkdb_mysql_service.py` - 服务层实现

