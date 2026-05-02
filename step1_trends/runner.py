# step1_trends/runner.py
"""
节点1 执行器: 热词搜索 + 标题生成 + 上传飞书
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from . import fetch_trends
from . import generate_topics
from shared.d1_client import D1Client
from shared import config
import json


def run():
    """执行节点1完整流程"""
    print("\n" + "=" * 50)
    print("🔍 节点1: 热词搜索 + 标题生成")
    print("=" * 50 + "\n")
    
    # Step 1: 抓取热点
    print(">>> Step 1: 抓取热点...")
    fetch_trends.main()
    
    # Step 2: 生成标题
    print("\n>>> Step 2: 生成 SEO 标题...")
    generator = generate_topics.SEOGenerator()
    generator.generate()
    
    # Step 3: 上传飞书
    print("\n>>> Step 3: 上传到飞书...")
    output_file = os.path.join(config.PROJECT_ROOT, "generated_seo_data.json")
    
    if not os.path.exists(output_file):
        print("❌ 找不到生成的数据文件")
        return
    
    with open(output_file, 'r', encoding='utf-8') as f:
        records = json.load(f)
    
    if not records:
        print("⚠️ 没有生成任何标题")
        return
    
    client = D1Client()
    
    # 转换为 D1 批量插入格式
    queries = []
    for item in records:
        sql = """
        INSERT INTO seo_articles (source_trend, topic, category_name, status, created_at) 
        VALUES (?, ?, ?, ?, ?)
        """
        params = [
            item.get("Source_Trend", ""),
            item.get("Topic", ""),
            item.get("大项分类", "行业资讯"),
            config.STATUS_READY,
            item.get("created_at", "")
        ]
        queries.append({"sql": sql, "params": params})
        
    # 分批上传 (D1 一次 HTTP 可以处理上百条，这里设个100为一批)
    batch_size = 100
    for i in range(0, len(queries), batch_size):
        batch = queries[i:i + batch_size]
        client.execute_batch(batch)
    
    print(f"\n✅ 节点1完成！共上传 {len(queries)} 条标题到 D1 数据库 (Status=Ready)")


if __name__ == "__main__":
    run()
