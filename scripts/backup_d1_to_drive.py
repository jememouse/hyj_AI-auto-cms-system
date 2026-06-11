import sys
import os
import json
import csv
import io
import base64
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.d1_client import D1Client

def backup():
    print("\n" + "=" * 50)
    print("🚀 D1 -> Google Drive (GAS 极客通道) 冷数据备份程序")
    print("=" * 50 + "\n")

    gas_url = os.getenv("GOOGLE_APPS_SCRIPT_URL", "")
    if not gas_url:
        print("❌ 错误：请在 .env 或 Github Secrets 中配置 GOOGLE_APPS_SCRIPT_URL")
        return

    # 1. 查询 D1 中待归档数据
    d1 = D1Client()
    print(">>> Step 1: 扫描 D1 数据库待归档记录...")
    # 限制 5000 条，防止一次性 Payload 超过 Google Apps Script 限制 (50MB)
    records = d1.execute(
        "SELECT * FROM seo_articles WHERE status IN ('Published', 'failed') AND is_archived = 0 LIMIT 5000"
    )
    
    if not records:
        print("✅ D1 中没有需要备份归档的冗余数据。")
        return
        
    print(f"📊 发现 {len(records)} 条已完结数据需要备份。")

    # 2. 生成 CSV (带 BOM utf-8-sig)
    print("\n>>> Step 2: 在内存中生成 CSV 备份文件...")
    csv_buffer = io.StringIO()
    # 写入 BOM 使得 Excel 打开不会乱码
    csv_buffer.write('\ufeff')
    writer = csv.writer(csv_buffer)
    
    headers = [
        "Topic", "Status", "大项分类", "Source_Trend", "Title", "HTML_Content",
        "摘要", "关键词", "URL", "发布时间", "生成时间"
    ]
    writer.writerow(headers)
    
    for r in records:
        writer.writerow([
            r.get("topic", ""),
            "归档_" + str(r.get("status", "")),
            r.get("category_name", ""),
            r.get("source_trend", ""),
            r.get("topic", ""),
            r.get("content_body", ""),
            r.get("summary", ""),
            r.get("keywords", ""),
            r.get("publish_url", ""),
            r.get("published_at", ""),
            r.get("created_at", "")
        ])
        
    csv_data = csv_buffer.getvalue()
    csv_buffer.close()

    # 3. 通过 Base64 编码数据以确保 JSON 传输安全
    print("\n>>> Step 3: 通过 Google Apps Script 投递文件到云盘...")
    filename = f"cms_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    encoded_csv = base64.b64encode(csv_data.encode('utf-8')).decode('utf-8')
    
    payload = {
        "filename": filename,
        "csvData": encoded_csv
    }
    
    try:
        # 发送 POST 请求到你的私人 API 中转站
        # Google Apps Script 经常会返回 302 重定向，requests 默认会自动跟随
        res = requests.post(gas_url, json=payload, timeout=60)
        
        # 尝试解析返回结果
        try:
            result = res.json()
        except Exception:
            # 如果解析失败，说明有可能遇到了重定向或其他非预期的响应格式
            print(f"❌ 解析 GAS 响应失败。HTTP 状态码: {res.status_code}")
            print(f"响应内容: {res.text[:500]}")
            return
            
        if result.get("success"):
            print(f"✅ 文件无缝创建成功！占用你私人云盘配额。File ID: {result.get('fileId')}")
            
            # 4. 回写 D1
            print("\n>>> Step 4: 回写 D1 归档标记并释放热数据空间...")
            queries = []
            for r in records:
                queries.append({
                    "sql": "UPDATE seo_articles SET is_archived = 1 WHERE id = ?",
                    "params": [r['id']]
                })
                
            batch_size = 100
            for i in range(0, len(queries), batch_size):
                d1.execute_batch(queries[i:i+batch_size])
                
            print(f"🎉 成功将 {len(records)} 条数据标记为归档。")
            
            # 5. 删除老数据释放容量
            delete_sql = "DELETE FROM seo_articles WHERE is_archived = 1 AND created_at <= datetime('now', '-3 days')"
            d1.execute(delete_sql)
            print("✅ 3天前的历史数据已从 D1 中彻底清除，热库减负完成。")
        else:
            print(f"❌ 云函数(GAS)处理失败: {result.get('error')}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求异常: {e}")

if __name__ == "__main__":
    backup()
