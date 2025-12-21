#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MySQL连接测试脚本

用于测试MySQL数据库的连接性和基本查询功能。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.dotenv import load_dotenv
from src.infra.mysql.tools import compose_mysql_sql, query_mysql

# 加载项目根目录下的 .env 文件
env_file_path = project_root / ".env"
load_dotenv(str(env_file_path), override=False)

def test_mysql_connection() -> dict:
    """测试MySQL基本连接"""
    try:
        import pymysql
        
        host = os.getenv("MYSQL_HOST")
        port = int(os.getenv("MYSQL_PORT", "3306"))
        user = os.getenv("MYSQL_USER")
        password = os.getenv("MYSQL_PASSWORD")
        db = os.getenv("MYSQL_DB")
        charset = os.getenv("MYSQL_CHARSET", "utf8mb4")
        
        print("🔌 [测试] 尝试连接MySQL...")
        print(f"   Host: {host}")
        print(f"   Port: {port}")
        print(f"   User: {user}")
        print(f"   Database: {db}")
        print(f"   Charset: {charset}")
        
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            db=db,
            charset=charset,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
        
        try:
            with conn.cursor() as cur:
                # 测试简单查询
                cur.execute("SELECT VERSION() as version, DATABASE() as current_db")
                result = cur.fetchone()
                
                print("✅ [成功] MySQL连接成功!")
                print(f"   MySQL版本: {result.get('version')}")
                print(f"   当前数据库: {result.get('current_db')}")
                
                return {
                    "success": True,
                    "version": result.get("version"),
                    "database": result.get("current_db"),
                }
        finally:
            conn.close()
            
    except Exception as e:
        print(f"❌ [失败] MySQL连接失败: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def test_mysql_query(
    influencer: str = "李诞",
    material_ids: list[str] | None = None,
    table: str = "mandasike_qianchuan_room_daily_dimension",
    max_rows: int = 10,
) -> dict:
    """测试MySQL查询功能"""
    print("\n" + "=" * 60)
    print("🔍 [测试] MySQL查询功能")
    print("=" * 60)
    
    if material_ids is None:
        material_ids = []
    
    print(f"   影响者: {influencer}")
    print(f"   Material IDs: {material_ids if material_ids else '(空，仅使用LIKE查询)'}")
    print(f"   表名: {table}")
    print(f"   最大返回行数: {max_rows}")
    
    try:
        # 1. 生成SQL
        print("\n📝 [步骤1] 生成SQL查询...")
        sql_output = compose_mysql_sql.invoke({
            "influencer": influencer,
            "material_ids": material_ids,
            "table": table,
            "require_in": False,  # 如果没有material_ids，允许只使用LIKE查询
        })
        
        sql = sql_output["sql"]
        print("   生成的SQL:")
        print("   " + "\n   ".join(sql.split("\n")))
        
        # 2. 执行查询
        print("\n🔄 [步骤2] 执行MySQL查询...")
        query_output = query_mysql.invoke({
            "sql": sql,
            "max_rows": max_rows,
        })
        
        row_count = query_output["row_count"]
        rows = query_output["rows"]
        
        print(f"✅ [成功] 查询成功!")
        print(f"   返回行数: {row_count}")
        
        if row_count > 0:
            print(f"\n📊 [结果] 前{min(3, row_count)}条数据预览:")
            for i, row in enumerate(rows[:3], 1):
                print(f"\n   记录 {i}:")
                for key, value in row.items():
                    # 限制显示长度
                    display_value = str(value)
                    if len(display_value) > 100:
                        display_value = display_value[:100] + "..."
                    print(f"     {key}: {display_value}")
        
        return {
            "success": True,
            "sql": sql,
            "row_count": row_count,
            "sample_rows": rows[:3],  # 只返回前3条作为示例
        }
        
    except Exception as e:
        print(f"\n❌ [失败] MySQL查询失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
        }


def main():
    """主函数"""
    print("=" * 60)
    print("MySQL连接和查询测试")
    print("=" * 60)
    
    # 显示环境变量文件路径（已经在文件顶部加载）
    env_file_path = project_root / ".env"
    print(f"\n📁 环境变量文件: {env_file_path}")
    if env_file_path.exists():
        print("   ✅ 文件存在")
    else:
        print("   ⚠️  文件不存在，请确保项目根目录下有 .env 文件")
    
    # 检查必要的环境变量
    required_vars = ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DB"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"\n❌ [错误] 缺少必要的环境变量: {', '.join(missing_vars)}")
        print("\n请在.env文件中设置以下变量:")
        for var in required_vars:
            print(f"   {var}=...")
        sys.exit(1)
    
    # 测试1: 基本连接
    print("\n" + "=" * 60)
    print("测试1: MySQL基本连接")
    print("=" * 60)
    connection_result = test_mysql_connection()
    
    if not connection_result.get("success"):
        print("\n⚠️  连接失败，无法继续后续测试")
        sys.exit(1)
    
    # 测试2: 查询测试（需要从命令行参数或环境变量获取参数）
    print("\n" + "=" * 60)
    print("测试2: MySQL查询测试")
    print("=" * 60)
    
    # 从环境变量或命令行参数获取测试参数
    influencer = os.getenv("TEST_INFLUENCER", "李诞")
    table = os.getenv("MYSQL_TABLE", "mandasike_qianchuan_room_daily_dimension")
    max_rows = int(os.getenv("TEST_MAX_ROWS", "10"))
    
    # 可以从环境变量获取material_ids（逗号分隔）
    material_ids_str = os.getenv("TEST_MATERIAL_IDS", "")
    material_ids = [mid.strip() for mid in material_ids_str.split(",") if mid.strip()] if material_ids_str else []
    
    query_result = test_mysql_query(
        influencer=influencer,
        material_ids=material_ids if material_ids else None,
        table=table,
        max_rows=max_rows,
    )
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"连接测试: {'✅ 通过' if connection_result.get('success') else '❌ 失败'}")
    print(f"查询测试: {'✅ 通过' if query_result.get('success') else '❌ 失败'}")
    
    if query_result.get("success"):
        print(f"查询返回行数: {query_result.get('row_count', 0)}")
    
    print("\n💡 提示:")
    print("   可以通过环境变量自定义测试参数:")
    print("   - TEST_INFLUENCER: 影响者名称（默认: 李诞）")
    print("   - TEST_MATERIAL_IDS: Material IDs，逗号分隔（可选）")
    print("   - TEST_MAX_ROWS: 最大返回行数（默认: 10）")
    print("   - MYSQL_TABLE: 表名（默认: mandasike_qianchuan_room_daily_dimension）")


if __name__ == "__main__":
    main()
