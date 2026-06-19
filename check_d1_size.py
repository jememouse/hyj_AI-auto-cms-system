import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared.d1_client import D1Client

account_id = os.getenv("CF_ACCOUNT_ID", "").strip()
database_id = os.getenv("CF_D1_DATABASE_ID", "").strip()
api_token = os.getenv("CF_API_TOKEN", "").strip()

print("="*40)
print("📦 D1 空间与容量明细报告")
print("="*40)

# 1. 查物理文件大小
if account_id and database_id and api_token:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json().get('result', {})
        file_size_bytes = data.get('file_size', 0)
        mb = file_size_bytes / (1024 * 1024)
        print(f"💽 数据库物理总占用: {mb:.2f} MB / 500.00 MB (Cloudflare 硬性上限)")
        print(f"🟢 健康度: {'极佳' if mb < 100 else '良好' if mb < 300 else '警告'}")
    else:
        print("❌ 无法获取物理大小:", resp.text)
else:
    print("❌ 缺少 Cloudflare API 凭据，无法读取物理大小。")

# 2. 查各状态分布
d1 = D1Client()
try:
    print("\n📊 核心表 (seo_articles) 数据分布:")
    res = d1.execute("SELECT status, is_archived, COUNT(*) as cnt FROM seo_articles GROUP BY status, is_archived ORDER BY cnt DESC")
    total = 0
    for row in res:
        status = row.get("status", "Unknown")
        archived = " (已归档)" if row.get("is_archived") == 1 else " (热数据)"
        cnt = row.get("cnt", 0)
        total += cnt
        print(f"  - 状态: [{status}]{archived:<10} -> {cnt} 条")
    print("-" * 40)
    print(f"总计留存数据: {total} 条")
except Exception as e:
    print("查询表数据失败:", e)

