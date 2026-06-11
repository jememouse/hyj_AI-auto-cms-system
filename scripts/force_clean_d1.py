import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.d1_client import D1Client

def clean_old_records(days=7):
    print(f"🧹 开始强制清理 D1 中超过 {days} 天的历史数据以释放空间...")
    db = D1Client()
    
    # 直接删除老的已发布和已失败记录
    sql = f"DELETE FROM seo_articles WHERE status IN ('Published', 'failed') AND created_at <= datetime('now', '-{days} days')"
    payload = {"sql": sql, "params": []}
    
    try:
        res = requests.post(db.url, headers=db.headers, json=payload)
        res.raise_for_status()
        data = res.json()
        if data.get("success"):
            meta = data['result'][0].get('meta', {})
            changes = meta.get('changes', 0)
            size_after = meta.get('size_after', 0)
            size_mb = size_after / 1024 / 1024
            print(f"✅ 清理成功！共删除了 {changes} 条历史数据。")
            print(f"📉 当前数据库容量: {size_mb:.2f} MB (上限 500 MB)")
        else:
            print("❌ 清理失败:", data.get('errors'))
    except Exception as e:
        print(f"❌ 请求出错: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="删除多少天前的数据")
    args = parser.parse_args()
    
    clean_old_records(args.days)
