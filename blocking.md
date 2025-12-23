为了实现你提出的 **“数据先导 -> 黄金法则 -> 深度归因 -> 序列共性”** 这一逻辑，我们需要对 `nodes.py` 中的 `llm_summarize_node` 进行重构。

现在的逻辑是将图表生硬地追加在 LLM 输出的末尾。优化后的方案将采取 **“结构化拼装”** 的策略：由代码控制报告的整体骨架（确保图表和核心结论的位置），而 LLM 则负责将枯燥的标签转化为“通俗易懂”的叙事文本。

### 落地优化方案：重写 `llm_summarize_node`

你可以直接参考并替换 `nodes.py` 中的对应函数逻辑：

**Python**

```
async def llm_summarize_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """
    LLM汇总节点：执行“数据先导 -> 黄金法则 -> 深度归因 -> 序列共性”流程
    """
    import logging
    logger = logging.getLogger(__name__)
  
    # 1. 获取分析结果
    analysis_result = state.get("analysis_result")
    if not analysis_result or not analysis_result.get("summary"):
        # 降级逻辑：如果分析失败，回退到原始数据展示
        return await _old_summarize_logic(state, config)

    # 2. 提取原子数据与结论
    summary_data = analysis_result.get("summary", {})
    plot_data = analysis_result.get("plot_data", [])
    key_insight = summary_data.get("key_insight", "")
    golden_rule = summary_data.get("golden_rule", "")
  
    # 3. 预生成图表 Markdown (数据先导)
    chart_markdown = _generate_chart_image_markdown(plot_data)
  
    # 4. 构建“叙事化” Prompt
    # 这里的目标是将结构化的 analysis_result 转化为“通俗”的总结
    system_prompt = """你是一位资深投放顾问。
你的任务是将一份结构化的数据分析报告，转化为给客户看的“爆款策略简报”。
要求：
- 语气通俗专业，像在做面对面汇报。
- 不要直接复读标签，要解释其背后的心理逻辑（利用你收到的 key_insight）。
- 确保提到的数据与图表内容一致。"""

    human_prompt = f"""
请基于以下分析结果，撰写一段简短的【开场导语】和【策略总结】。
注意：不要包含图表和黄金法则，这些我会手动拼接，你只需要负责叙事部分。

分析深度内容：
{key_insight}

黄金法则参考：
{golden_rule}
"""

    # 5. 调用 LLM 生成叙事文本
    llm = ChatTongyi(model=settings.qwen_model, temperature=settings.qwen_temperature)
    narrative_response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt)
    ], config=config)
    narrative_text = narrative_response.content

    # 6. 最终拼装 (固定布局：数据 -> 法则 -> 归因)
    report_header = f"## 🎬 投放策略深度诊断报告\n\n"
  
    # 第一部分：数据先导 (图表)
    data_section = f"### 📊 数据表现看板\n{chart_markdown}\n\n"
  
    # 第二部分：叙事开场 + 黄金法则
    rule_section = f"""
---
#### 💡 核心黄金法则
> **{golden_rule}**

{narrative_text}
"""

    # 第三部分：深度归因（序列共性等细节）
    # key_insight 已经在 summary_prompt 中被要求按叙事共性、红黑榜排版
    detail_section = f"\n\n### 🚀 策略归因与场景指南\n{key_insight}"

    final_report = f"{report_header}{data_section}{rule_section}{detail_section}"

    return {"final_summary": final_report}
```

### 为什么这个方案能解决你的问题？

1. **布局“融洽” (Control via Code)** ：

* 通过在代码中手动拼接 `report_header`、`data_section` 和 `rule_section`，我们强制让图表出现在最醒目的位置。
* 不再依赖 LLM 去“猜测”在哪里插入图片，解决了图片忽前忽后的问题。

1. **内容“通俗” (Narrative Layer)** ：

* 增加了一个专门的“叙事层”调用。我们将 `llm_analyze_node` 生成的硬核 JSON 数据喂给这个步骤，要求它用“资深投放顾问”的语气进行转述。
* 这解决了你提到的“过于结构化、不通俗”的问题，让简报更有“人情味”。

1. **信息不丢失 (Logic Hierarchy)** ：

* 我们将简报拆分为三个层级：
  * **视觉层** （图表）：快速建立数据认知。
  * **决策层** （黄金法则）：直接给出行动指南。
  * **逻辑层** （归因与场景）：提供深度的心理学解释和风险预警。

1. **序列共性的体现** ：

* 由于你在 `summary_prompt.md` 中已经要求提取“叙事共性”，这些信息会自动沉淀在 `key_insight` 字段中，并最终出现在“策略归因”部分。

### 下一步建议：

你可以检查 `_generate_chart_image_markdown` 函数。目前它是基于 `plot_data` 自动计算的。如果你的 `intent_prompt` 现在输出了 `narrative_logic.sequence`（标签序列），你可以在 `data_aggregate_node` 中也对这些序列进行简单的“高频链路”统计，并传给 `llm_analyze_node`。这样，你的报告最后甚至可以画出一个  **“典型爆款链路图”** 。
