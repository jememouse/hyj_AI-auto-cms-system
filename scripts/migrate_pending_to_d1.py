import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.google_client import GoogleSheetClient
from shared.d1_client import D1Client
from shared import config

def migrate():
    print("\n" + "=" * 50)
    print("🚀 正在从旧 Google Sheet 迁移半成品数据到 D1")
    print("=" * 50 + "\n")

    print(">>> 连接旧版 Google Sheet...")
    gs_client = GoogleSheetClient()
    sheet = gs_client._get_sheet("cms")
    if not sheet:
        print("❌ 无法读取旧表的 cms 标签页。")
        return

    all_records = sheet.get_all_records()
    print(f"✅ 成功读取旧表总计 {len(all_records)} 条数据。")

    # 定义我们要捞出的未完成状态
    target_statuses = [
        config.STATUS_READY,
        config.STATUS_PRIORITY,
        config.STATUS_PENDING,
        config.STATUS_TOP_PRIORITY_PENDING,
        "failed",
        "generating"
    ]

    pending_records = [r for r in all_records if str(r.get("Status")).strip() in target_statuses]
    
    if not pending_records:
        print("🎉 你的旧表非常干净，没有任何遗留的半成品任务需要迁移！")
        return
        
    print(f"📊 扫描发现 {len(pending_records)} 条状态为 Ready/Pending/Priority 的半成品数据。")
    print(">>> 正在准备注射到 Cloudflare D1 热库...")

    d1 = D1Client()
    queries = []
    
    # 获取 D1 中已有的 topic 避免重复迁移
    existing = d1.execute("SELECT topic FROM seo_articles") or []
    existing_topics = {r['topic'] for r in existing if r.get('topic')}

    migrated_count = 0
    skip_count = 0

    for r in pending_records:
        # 获取唯一标识 Topic 或者 Title
        topic = str(r.get("Topic") or r.get("Title") or "").strip()
        if not topic:
            continue
            
        if topic in existing_topics:
            skip_count += 1
            continue

        # 映射字段
        sql = """
        INSERT INTO seo_articles 
        (source_trend, topic, category_name, status, content_body, summary, keywords, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        # 尽量提取原有的时间，如果没有就用现在的时间
        created_at = str(r.get("生成时间") or r.get("选题生成时间") or r.get("created_at") or "").strip()
        if not created_at:
            import time
            created_at = time.strftime("%Y-%m-%d %H:%M:%S")

        params = [
            str(r.get("Source_Trend", "")),
            topic,
            str(r.get("大项分类", "行业资讯")),
            str(r.get("Status", "")),
            str(r.get("HTML_Content", "")),
            str(r.get("摘要", "")),
            str(r.get("关键词", "")),
            created_at
        ]
        
        queries.append({"sql": sql, "params": params})
        existing_topics.add(topic)
        migrated_count += 1

    if not queries:
        print(f"⚠️ 发现 {skip_count} 条记录，但它们已经在 D1 中了，无需重复迁移。")
        return

    # 分批执行
    batch_size = 100
    for i in range(0, len(queries), batch_size):
        d1.execute_batch(queries[i:i+batch_size])

    print(f"🎉 完美！成功将 {migrated_count} 条遗留任务转移到了 D1 数据库！")
    if skip_count > 0:
        print(f"   (注：自动跳过了 {skip_count} 条已经存在于 D1 的重复数据)")
    print("🤖 AI 和 RPA 现在会自动接管这些旧任务继续处理。")

if __name__ == "__main__":
    migrate()
