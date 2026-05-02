import sys
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 在导入任何自建模块之前，强制将旧表的 ID 环境变量指向新备份表的 ID
backup_id = os.getenv("GOOGLE_SHEET_BACKUP_ID", "")
if backup_id:
    os.environ["GOOGLE_SHEET_ID"] = backup_id

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.google_client import GoogleSheetClient
from shared.d1_client import D1Client

def backup():
    print("\n" + "=" * 50)
    print("📦 D1 -> Google Sheet 冷数据备份归档程序")
    print("=" * 50 + "\n")

    if not backup_id:
        print("❌ 错误：请在 .env 中配置 GOOGLE_SHEET_BACKUP_ID")
        return

    d1 = D1Client()
    
    # 1. 查询 D1 中已经发布且尚未归档的老数据
    print(">>> Step 1: 扫描 D1 数据库待归档记录...")
    # 这里我们备份状态为 'Published' 或 'failed'，并且 is_archived = 0 的数据
    records = d1.execute(
        "SELECT * FROM seo_articles WHERE status IN ('Published', 'failed') AND is_archived = 0 LIMIT 1000"
    )
    
    if not records:
        print("✅ D1 中没有需要备份归档的冗余数据。")
        return
        
    print(f"📊 发现 {len(records)} 条已完结数据需要备份。")
    
    # 2. 转换为 Google Sheet 需要的格式 (兼容老版格式)
    print("\n>>> Step 2: 连接 Backup Google Sheet 并推送数据...")
    sheet_client = GoogleSheetClient()
    upload_list = []
    
    for r in records:
        upload_list.append({
            "Topic": r.get("topic", ""),
            "Status": "归档_" + r.get("status", ""),
            "大项分类": r.get("category_name", ""),
            "Source_Trend": r.get("source_trend", ""),
            "Title": r.get("topic", ""),
            "HTML_Content": r.get("content_body", ""),
            "摘要": r.get("summary", ""),
            "关键词": r.get("keywords", ""),
            "URL": r.get("publish_url", ""),
            "发布时间": r.get("published_at", ""),
            "生成时间": r.get("created_at", "")
        })
        
        
    # 执行批量推送前，检查行数是否需要滚动
    try:
        sheet = sheet_client._get_sheet("cms_backup")
        if sheet:
            filled_rows = len(sheet.col_values(1))
            if filled_rows >= 10000:
                new_title = f"cms_backup_{datetime.now().strftime('%Y%m%d_%H%M')}"
                sheet.update_title(new_title)
                print(f"🔄 检测到备份表已满 10000 行，已自动将原标签页重命名归档为: {new_title}")
                # 原表被改名后，接下来的 batch_create_records 会自动帮你建一个全新的 cms_backup 标签页
    except Exception as e:
        print(f"⚠️ 检查表格行数时发生异常: {e}")

    # 执行批量推送
    success = sheet_client.batch_create_records(upload_list, table_id="cms_backup")
    
    if success:
        # 3. 备份成功后，更新 D1 中的归档标记或直接删除以释放空间
        print("\n>>> Step 3: 回写 D1 归档标记并释放热数据空间...")
        
        # 方案 A: 标记归档 (保留在 D1 中) -> UPDATE seo_articles SET is_archived = 1
        # 方案 B: 直接清理 (节省 D1 空间) -> DELETE FROM seo_articles
        # 我们采用方案 A，如果你需要省空间，可以改写成 DELETE。
        
        queries = []
        for r in records:
            queries.append({
                "sql": "UPDATE seo_articles SET is_archived = 1 WHERE id = ?",
                "params": [r['id']]
            })
            
        # 批量执行归档更新
        batch_size = 100
        for i in range(0, len(queries), batch_size):
            d1.execute_batch(queries[i:i+batch_size])
            
        print(f"🎉 归档大功告成！成功将 {len(records)} 条数据从 D1 热库转移至 Google Sheet 冷库。")
        
        # 4. 清理超过 3 天的已归档数据
        print("\n>>> Step 4: 清理 D1 中超过 3 天的已归档数据...")
        delete_sql = "DELETE FROM seo_articles WHERE is_archived = 1 AND created_at <= datetime('now', '-3 days')"
        # 使用 execute 而非 execute_batch 因为这是单条指令
        d1.execute(delete_sql)
        print("✅ 3天前的历史数据已从 D1 中彻底清除，释放空间。")
    else:
        print("❌ 备份到 Google Sheet 失败，已中断流程，D1 数据将保留等待下次重试。")

if __name__ == "__main__":
    backup()
