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

    # 初始化 CMS 数据库 (seo_articles)
    d1_cms = D1Client(db_id=os.getenv("CF_D1_DATABASE_ID", ""))
    
    # 初始化 词库 数据库 (keywords_repo)
    d1_pkg = D1Client(db_id=os.getenv("CF_D1_PACKAGING_DB_ID", "2ef1ee52-ad2a-48c8-9c60-a20c3260cc70"))
    
    # ==========================================
    # 任务 1: 归档 CMS 文章数据库
    # ==========================================
    print(">>> [Task 1] 扫描 CMS 数据库待归档记录...")
    # 限制 5000 条，防止一次性 Payload 超过 Google Apps Script 限制 (50MB)
    records = d1_cms.execute(
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
    filename = f"cms_backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_共{len(records)}条.csv"
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
                d1_cms.execute_batch(queries[i:i+batch_size])
                
            print(f"🎉 成功将 {len(records)} 条数据标记为归档。")
            
            # 5. 删除老数据释放容量
            delete_sql = "DELETE FROM seo_articles WHERE is_archived = 1 AND created_at <= datetime('now', '-3 days')"
            d1_cms.execute(delete_sql)
            print("✅ 3天前的历史数据已从 CMS D1 中彻底清除，热库减负完成。")
        else:
            print(f"❌ 云函数(GAS)处理 CMS 失败: {result.get('error')}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求异常: {e}")

    # ==========================================
    # 任务 2: 归档 词库 数据库 (keywords_repo)
    # ==========================================
    print("\n" + "-" * 50)
    print(">>> [Task 2] 扫描 词库 数据库待归档记录...")
    # 假设 keywords_repo 表已有 is_archived 字段
    kws_records = d1_pkg.execute(
        "SELECT * FROM keywords_repo WHERE status = 'Used' AND (is_archived = 0 OR is_archived IS NULL) LIMIT 10000"
    )
    
    if not kws_records:
        print("✅ 词库中没有需要备份归档的冗余数据。")
    else:
        print(f"📊 发现 {len(kws_records)} 条已消耗词汇需要备份。")
        
        csv_buffer_pkg = io.StringIO()
        csv_buffer_pkg.write('\ufeff')
        writer_pkg = csv.writer(csv_buffer_pkg)
        
        headers_pkg = ["ID", "Keyword", "Intent", "Fetch_Date", "Status", "Used_At"]
        writer_pkg.writerow(headers_pkg)
        
        for r in kws_records:
            writer_pkg.writerow([
                r.get("id", ""),
                r.get("keyword", ""),
                r.get("intent", ""),
                r.get("fetch_date", ""),
                r.get("status", ""),
                r.get("used_at", "")
            ])
            
        csv_data_pkg = csv_buffer_pkg.getvalue()
        csv_buffer_pkg.close()
        
        filename_pkg = f"keywords_backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_共{len(kws_records)}条.csv"
        encoded_csv_pkg = base64.b64encode(csv_data_pkg.encode('utf-8')).decode('utf-8')
        
        payload_pkg = {
            "filename": filename_pkg,
            "csvData": encoded_csv_pkg
        }
        
        try:
            res_pkg = requests.post(gas_url, json=payload_pkg, timeout=60)
            try:
                result_pkg = res_pkg.json()
            except Exception:
                print(f"❌ 解析 GAS 响应失败。HTTP 状态码: {res_pkg.status_code}")
                result_pkg = {}
                
            if result_pkg.get("success"):
                print(f"✅ 词库文件无缝创建成功！File ID: {result_pkg.get('fileId')}")
                
                # 回写词库的 is_archived 标记
                queries_pkg = []
                for r in kws_records:
                    queries_pkg.append({
                        "sql": "UPDATE keywords_repo SET is_archived = 1 WHERE id = ?",
                        "params": [r['id']]
                    })
                    
                for i in range(0, len(queries_pkg), 100):
                    d1_pkg.execute_batch(queries_pkg[i:i+100])
                    
                print(f"🎉 成功将 {len(kws_records)} 条词库数据标记为归档。")
                
            else:
                print(f"❌ 云函数(GAS)处理词库失败: {result_pkg.get('error')}")
        except requests.exceptions.RequestException as e:
            print(f"❌ 词库网络请求异常: {e}")
            
    # 执行方案B：清理超过180天且已归档的老旧词条，避免无限膨胀
    print("\n>>> 执行词库安全清理策略 (180天)")
    delete_pkg_sql = "DELETE FROM keywords_repo WHERE is_archived = 1 AND used_at <= datetime('now', '-180 days')"
    d1_pkg.execute(delete_pkg_sql)
    print("✅ 180天前已归档的历史词条已被彻底清除，空间释放完毕。")

if __name__ == "__main__":
    backup()
