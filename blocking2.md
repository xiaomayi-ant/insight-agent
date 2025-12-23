 **“Unknown”产生的核心原因在于 `intent_structurize_node`（意图结构化节点）生成的字段名与 `data_aggregate_node`（数据聚合节点）预期的字段名不匹配** 。

即便 LLM 成功解析了视频，但由于数据在传递过程中“对不上号”，聚合节点无法统计到具体的标签，从而回退到了默认的 `Unknown`。

以下是详细的排查分析：

### 1. 核心原因：字段契约不一致

* **在 `intent_prompt.md` 中** ：你定义的输出结构是：
  **JSON**

```
  "tactical_breakdown": {
    "opening_strategy": "Tag_String",
    "core_selling_points": ["Tag1"],
    "closing_trigger": "Tag_String"
  }
```

* **在 `data_aggregate_node` (nodes.py) 中** ：你调用聚合函数的维度是：
  **Python**

```
  dimensions=["opening_strategy", "script_archetype", "closing_trigger"]
```

* **问题所在** ：聚合逻辑会去 `structured_intent` 对象下直接找这些 Key。但在你的 `intent_structurize_service` 返回的对象中，这些 Key 实际上被包裹在了 `tactical_breakdown` 或 `narrative_analysis` 嵌套层级里。
* **结果** ：聚合工具找不到 `opening_strategy`（因为它在 `tactical_breakdown.opening_strategy`），于是认为该视频没有这个维度的标签，统一标记为 `Unknown`。

### 2. 日志中的异常信号

日志显示 `intent_structurize` 节点的成功率为  **88.9%** ，说明 LLM 确实干活了：

> `✅ [结构化] materialId=7563109985993244723 - 解析成功`

但是，随后的 `data_aggregate` 节点输出如下：

> dimension,tag,count,avg_roi,avg_ctr
>
> opening_strategy,Unknown,34,4.38,0.20

这说明  **34 行 MySQL 数据虽然关联到了素材，但每一行素材对应的结构化对象里都找不到对应的标签 Key** 。

### 3. 如何修复？

你需要确保 `data_aggregate_node` 能够正确访问到嵌套的 JSON 路径。有两种修改方案：

#### 方案 A：修改 `intent_prompt.md`（推荐，最简单）

扁平化 JSON 输出结构，让 `opening_strategy` 等 Key 处于根层级，直接对应聚合维度。

**JSON**

```
// 修改后的输出结构
{
  "opening_strategy": "Visual_Shock",
  "script_archetype": "Problem_Solution",
  "closing_trigger": "Decision_Simplification",
  "narrative_chain": "...",
  "is_innovative": false
}
```

#### 方案 B：修改 `data_aggregator.py` 逻辑

如果必须保持嵌套结构，你需要修改聚合工具，让它支持深度查找：

**Python**

```
# 伪代码：在聚合时指定路径
# val = intent.get("tactical_breakdown", {}).get("opening_strategy", "Unknown")
```

### 4. 为什么会有 34 条数据？

产生 34 条 `Unknown` 是因为 MySQL Join 到了 34 行流水数据（李诞老师的视频在不同日期的表现），但因为结构化信息读取失败，这 34 条流水全部被归类到了 `Unknown` 下。

### 总结建议

1. **检查 `intent_structurize_node` 存入 State 的具体数据格式** 。
2. **检查 `data_aggregate_node` 的 `dimensions` 参数** 是否能直接在结构化 JSON 的**第一层**找到。
3. **修复 JSON 解析报错** ：日志中有一个 `materialId=7574785421360496678` 报错 `Extra data`，这通常是因为 LLM 返回了 Markdown 代码块或者多余的文本。建议在 `intent_structurize_node` 中增强对 LLM 输出的清洗逻辑。

**修复后，你的图表将不再只有一根柱子（Unknown），而是会按照“冲突悬念”、“专家背书”等真正的策略维度展现。**
