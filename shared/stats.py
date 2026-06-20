# shared/stats.py
"""
数据统计汇总模块
"""
import json
import os
from datetime import datetime
from typing import Dict

# 统计文件路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATS_FILE = os.path.join(BASE_DIR, ".cache", "stats.json")


def _load_stats() -> Dict:
    """加载统计数据"""
    if not os.path.exists(STATS_FILE):
        return {"daily": {}, "total": {"generated": 0, "published": 0, "failed": 0}}
    try:
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"daily": {}, "total": {"generated": 0, "published": 0, "failed": 0}}


def _save_stats(stats: Dict):
    """保存统计数据"""
    os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def record_generated(count: int = 1):
    """记录文章生成数"""
    stats = _load_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    
    if today not in stats["daily"]:
        stats["daily"][today] = {"generated": 0, "published": 0, "failed": 0}
    
    stats["daily"][today]["generated"] += count
    stats["total"]["generated"] += count
    _save_stats(stats)


def record_published(count: int = 1):
    """记录文章发布数"""
    stats = _load_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    
    if today not in stats["daily"]:
        stats["daily"][today] = {"generated": 0, "published": 0, "failed": 0}
    
    stats["daily"][today]["published"] += count
    stats["total"]["published"] += count
    _save_stats(stats)


def record_failed(count: int = 1):
    """记录失败数"""
    stats = _load_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    
    if today not in stats["daily"]:
        stats["daily"][today] = {"generated": 0, "published": 0, "failed": 0}
    
    stats["daily"][today]["failed"] += count
    stats["total"]["failed"] += count
    _save_stats(stats)


def get_summary() -> str:
    """获取统计摘要"""
    stats = _load_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    daily = stats["daily"].get(today, {"generated": 0, "published": 0, "failed": 0})
    total = stats["total"]
    
    # === 新增：从 D1 获取真实发布数量，解决并发统计丢失/多环境缓存隔离问题 ===
    try:
        from core.state_bus import StateBus
        bus = StateBus()
        today_prefix = today + "%"
        
        res_today = bus.client.execute(
            "SELECT count(*) as cnt FROM seo_articles WHERE status = 'Published' AND published_at LIKE ?", 
            [today_prefix]
        )
        if res_today:
            daily['published'] = res_today[0].get('cnt', daily['published'])
            
        res_total = bus.client.execute(
            "SELECT count(*) as cnt FROM seo_articles WHERE status = 'Published'"
        )
        if res_total:
            total['published'] = res_total[0].get('cnt', total['published'])
        res_total_gen = bus.client.execute(
            "SELECT count(*) as cnt FROM seo_articles WHERE status IN ('Pending', 'Top priority', 'Published')"
        )
        if res_total_gen:
            total['generated'] = res_total_gen[0].get('cnt', total['generated'])
            
        res_today_gen = bus.client.execute(
            "SELECT count(*) as cnt FROM seo_articles WHERE substr(datetime(created_at, '+8 hours'), 1, 10) = ?", 
            [today]
        )
        if res_today_gen:
            daily['generated'] = res_today_gen[0].get('cnt', daily['generated'])
            
    except Exception as e:
        print(f"⚠️ [Stats] 无法从 D1 获取实时发布数据: {e}")
        
    generated_base = max(total['generated'], 1)
    success_rate = min(total['published'] / generated_base * 100, 100.0)
    
    return f"""📊 **数据统计**
**今日 ({today})**
- 新增话题: {daily['generated']} 篇
- 成功发布: {daily['published']} 篇
- 任务失败: {daily['failed']} 篇

**累计**
- 累计生成: {total['generated']} 篇
- 累计发布: {total['published']} 篇
- 发布进度: {success_rate:.1f}%"""


def print_summary():
    """打印统计摘要"""
    print(get_summary())
