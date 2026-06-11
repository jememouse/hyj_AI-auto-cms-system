'''
Author: jememouse jememouse@gmail.com
Date: 2026-05-11 16:05:13
LastEditors: jememouse jememouse@gmail.com
LastEditTime: 2026-05-11 16:05:17
FilePath: /hyj_AI-auto-cms-system/scripts/daily_report.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
'''
import sys
import os
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# 动态添加项目根目录到 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from shared.google_client import GoogleSheetClient
from shared.d1_client import D1Client
from shared import config

def generate_daily_report():
    print("📊 开始生成每日发布数据统计报告...")
    
    client = GoogleSheetClient()
    db = D1Client()
    
    counts = defaultdict(int)
    total_published = 0
    
    try:
        # 获取历史累计总发布
        res_total = db.execute("SELECT COUNT(*) as c FROM seo_articles WHERE status = 'Published'")
        if res_total:
            total_published = res_total[0].get('c', 0)
            
        # 获取按天统计的发布数据
        res_counts = db.execute("SELECT substr(published_at, 1, 10) as d, COUNT(*) as c FROM seo_articles WHERE status = 'Published' AND published_at IS NOT NULL GROUP BY substr(published_at, 1, 10)")
        if res_counts:
            for row in res_counts:
                d = row.get('d')
                if d:
                    counts[d] += row.get('c', 0)
    except Exception as e:
        print(f"⚠️ 读取 D1 数据库失败: {e}")
        return
        
    # 强制使用北京时间 (UTC+8) 避免服务器环境时区干扰
    tz_bj = timezone(timedelta(hours=8))
    now = datetime.now(tz_bj)
    
    # 获取今天和昨天的日期
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    
    today_count = counts.get(today_str, 0)
    yesterday_count = counts.get(yesterday_str, 0)
    
    # 按照自然日历生成最近 7 天的日期列表（倒序：从今天往前推 6 天）
    recent_7_days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    
    # 构建飞书消息内容
    lines = [
        f"📅 **每日发布数据统计 ({today_str})**",
        "",
        f"🌟 **今日发布**: {today_count} 篇",
        f"📈 **昨日发布**: {yesterday_count} 篇",
        f"🏆 **历史累计总发布**: {total_published} 篇",
        "",
        "**🗓️ 最近 7 天发布趋势:**"
    ]
    
    for d in recent_7_days:
        lines.append(f" - {d}: {counts.get(d, 0)} 篇")
        
    lines.append("")
    lines.append("🤖 *本条消息由 AI-Auto-CMS 自动化系统每日定时发送*")
    
    content = "\n".join(lines)
    print("--------------------------------------------------")
    print(content)
    print("--------------------------------------------------")
    
    # 发送飞书通知
    success = client.send_notification("每日发布数据统计", content)
    if success:
        print("✅ 飞书通知发送成功！")
    else:
        print("❌ 飞书通知发送失败！请检查 webhook 配置。")

if __name__ == "__main__":
    generate_daily_report()
