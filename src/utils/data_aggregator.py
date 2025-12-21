from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from src.services.intent_structurize_service import StructuredIntentResult

logger = logging.getLogger(__name__)


def merge_structured_intents_with_mysql(
    structured_intents: List[StructuredIntentResult],
    mysql_join_result: Dict[str, Any],
    min_count: int = 2
) -> pd.DataFrame:
    """
    将结构化意图数据与 MySQL 数据合并
    
    Args:
        structured_intents: 结构化意图结果列表
        mysql_join_result: MySQL Join 结果
        min_count: 最小频次阈值（用于过滤）
    
    Returns:
        pd.DataFrame: 合并后的数据框
    """
    # 1. 构建结构化意图 DataFrame
    intent_data = []
    for result in structured_intents:
        if not result.success:
            continue
        
        material_id = result.materialId
        structured = result.structured_intent
        
        # 提取关键字段
        narrative = structured.get("narrative_analysis", {})
        tactical = structured.get("tactical_breakdown", {})
        
        intent_data.append({
            "materialId": material_id,
            "script_archetype": narrative.get("script_archetype", "Unknown"),
            "narrative_chain": narrative.get("narrative_chain", ""),
            "pacing": narrative.get("pacing", "Unknown"),
            "opening_strategy": tactical.get("opening_strategy", "Unknown"),
            "core_selling_points": tactical.get("core_selling_points", []),
            "closing_trigger": tactical.get("closing_trigger", "Unknown"),
            "dominant_emotion": tactical.get("dominant_emotion", "Unknown"),
        })
    
    if not intent_data:
        logger.warning("⚠️ [聚合] 没有有效的结构化意图数据")
        return pd.DataFrame()
    
    df_intents = pd.DataFrame(intent_data)
    logger.info(f"📊 [聚合] 结构化意图数据: {len(df_intents)} 条")
    
    # 2. 构建 MySQL 数据 DataFrame
    mysql_data = mysql_join_result.get("mysql", {})
    mysql_rows = mysql_data.get("rows", [])
    
    if not mysql_rows:
        logger.warning("⚠️ [聚合] 没有 MySQL 数据")
        return pd.DataFrame()
    
    # 从 MySQL 行数据中提取需要的字段
    mysql_records = []
    for row in mysql_rows:
        mysql_records.append({
            "materialId": str(row.get("materialId", "")),
            "roi2": float(row.get("totalPrepayAndPayOrderRoi2", 0.0)) if row.get("totalPrepayAndPayOrderRoi2") else 0.0,
            "ctr": float(row.get("liveWatchCountForRoi2V2", 0)) / float(row.get("liveShowCountForRoi2V2", 1)) 
                   if row.get("liveShowCountForRoi2V2", 0) > 0 else 0.0,
            "cost": float(row.get("statCostForRoi2", 0.0)) if row.get("statCostForRoi2") else 0.0,
            "show_count": int(row.get("liveShowCountForRoi2V2", 0)) if row.get("liveShowCountForRoi2V2") else 0,
            "click_count": int(row.get("liveWatchCountForRoi2V2", 0)) if row.get("liveWatchCountForRoi2V2") else 0,
        })
    
    df_mysql = pd.DataFrame(mysql_records)
    logger.info(f"📊 [聚合] MySQL 数据: {len(df_mysql)} 条")
    
    # 3. 合并数据（基于 materialId）
    df_merged = pd.merge(df_intents, df_mysql, on="materialId", how="inner")
    
    if df_merged.empty:
        logger.warning("⚠️ [聚合] 合并后数据为空（materialId 不匹配）")
        return pd.DataFrame()
    
    logger.info(f"✅ [聚合] 合并后数据: {len(df_merged)} 条")
    return df_merged


def aggregate_by_dimension(
    df: pd.DataFrame,
    dimension: str,
    min_count: int = 2
) -> pd.DataFrame:
    """
    按指定维度聚合数据
    
    Args:
        df: 合并后的数据框
        dimension: 聚合维度（如 "opening_strategy", "script_archetype"）
        min_count: 最小频次阈值
    
    Returns:
        pd.DataFrame: 聚合统计结果
    """
    if df.empty or dimension not in df.columns:
        return pd.DataFrame()
    
    # 聚合统计
    agg_stats = df.groupby(dimension).agg({
        "materialId": "count",  # 频次
        "roi2": "mean",  # 平均 ROI
        "ctr": "mean",  # 平均 CTR
        "cost": "sum",  # 总消耗
        "show_count": "sum",  # 总曝光
        "click_count": "sum",  # 总点击
    }).reset_index()
    
    # 重命名列
    agg_stats.columns = ["tag", "count", "avg_roi", "avg_ctr", "total_cost", "total_show", "total_click"]
    
    # 过滤低频标签
    agg_stats = agg_stats[agg_stats["count"] >= min_count]
    
    # 按 count 降序排序
    agg_stats = agg_stats.sort_values("count", ascending=False)
    
    return agg_stats


def generate_aggregation_csv(
    structured_intents: List[StructuredIntentResult],
    mysql_join_result: Dict[str, Any],
    dimensions: Optional[List[str]] = None,
    min_count: int = 2
) -> str:
    """
    生成聚合统计的 CSV 字符串（用于喂给 LLM）
    
    Args:
        structured_intents: 结构化意图结果列表
        mysql_join_result: MySQL Join 结果
        dimensions: 聚合维度列表（默认：opening_strategy, script_archetype, closing_trigger）
        min_count: 最小频次阈值
    
    Returns:
        str: CSV 格式的统计表
    """
    if dimensions is None:
        dimensions = ["opening_strategy", "script_archetype", "closing_trigger"]
    
    # 合并数据
    df_merged = merge_structured_intents_with_mysql(
        structured_intents,
        mysql_join_result,
        min_count
    )
    
    if df_merged.empty:
        logger.warning("⚠️ [聚合CSV] 合并数据为空，返回空 CSV")
        return "tag,count,avg_roi,avg_ctr\n"
    
    # 对每个维度进行聚合
    all_stats = []
    for dimension in dimensions:
        if dimension not in df_merged.columns:
            logger.warning(f"⚠️ [聚合CSV] 维度 {dimension} 不存在，跳过")
            continue
        
        stats = aggregate_by_dimension(df_merged, dimension, min_count)
        if not stats.empty:
            # 添加维度标识
            stats["dimension"] = dimension
            all_stats.append(stats)
    
    if not all_stats:
        logger.warning("⚠️ [聚合CSV] 没有有效的聚合统计")
        return "tag,count,avg_roi,avg_ctr\n"
    
    # 合并所有维度的统计
    df_all = pd.concat(all_stats, ignore_index=True)
    
    # 重新排列列顺序
    df_all = df_all[["dimension", "tag", "count", "avg_roi", "avg_ctr"]]
    
    # 转换为 CSV
    csv_str = df_all.to_csv(index=False)
    
    logger.info(f"✅ [聚合CSV] 生成 CSV，共 {len(df_all)} 行")
    return csv_str

