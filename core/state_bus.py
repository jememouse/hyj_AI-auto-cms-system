import os
import json
import time
from collections import defaultdict
from itertools import zip_longest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.d1_client import D1Client
from shared import config
import requests

class StateBus:
    """
    统一状态大巴：全新升级！接管所有针对 Cloudflare D1 数据库的读写与流转校验。
    完全兼容旧版的输入输出格式，对上下游无缝替换。
    """
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.client = D1Client()

    def push_new_topics(self, new_topics: list):
        """
        [节点 1 提供] 将新产生的话题推入 D1 总线：自动去重并入库
        """
        if not new_topics:
            return

        # 1. 查出现有 D1 中的所有 topic 用于去重
        existing_records = self.client.execute("SELECT topic FROM seo_articles") or []
        existing_topics = {r['topic'] for r in existing_records}
        
        added_count = 0
        queries = []
        
        for t in new_topics:
            topic = t.get('Topic')
            if topic and topic not in existing_topics:
                status = config.STATUS_PRIORITY if '[外部指定]' in t.get('Source_Trend', '') else config.STATUS_READY
                sql = """
                INSERT INTO seo_articles (source_trend, topic, category_name, status, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """
                params = [
                    t.get('Source_Trend', ''), 
                    topic, 
                    t.get('大项分类', '行业资讯'), 
                    status
                ]
                queries.append({"sql": sql, "params": params})
                existing_topics.add(topic)
                added_count += 1
            else:
                print(f"[StateBus] ⏭️ 话题已存在 D1 中，跳过去重: {topic}")
                
        if added_count > 0:
            print(f"[StateBus] ☁️ 正在批量推送 {added_count} 条新生代待处理任务给 D1 数据库...")
            batch_size = 100
            for i in range(0, len(queries), batch_size):
                self.client.execute_batch(queries[i:i + batch_size])
            print(f"[StateBus] ✅ 流量推送成功！{added_count} 条新指令已并入 D1 网络节点。")

    def pull_ready_jobs(self, max_total_limit: int, category: str = None):
        """
        [节点 2 拉取] 从状态总线获取准备好的写入任务
        包含基于公平优先级的分配组装（Priority 插队及普通请求 Round-Robin）。
        """
        print(f"[StateBus] ☁️ 正在向 D1 总线拉取待写文章清单... (分类过滤: {category or '无'})")
        
        cat_sql = " AND category_name = ?" if category else ""
        
        # 拉取高级指令槽
        params_pri = [config.STATUS_PRIORITY]
        if category: params_pri.append(category)
        priority_topics = self.client.execute(
            f"SELECT * FROM seo_articles WHERE status = ? {cat_sql} ORDER BY created_at ASC LIMIT 100", 
            params_pri
        ) or []
        
        # 拉取普通指令槽
        params_ready = [config.STATUS_READY]
        if category: params_ready.append(category)
        ready_topics = self.client.execute(
            f"SELECT * FROM seo_articles WHERE status = ? {cat_sql} ORDER BY created_at ASC LIMIT 500", 
            params_ready
        ) or []
        
        if not (priority_topics + ready_topics):
             print("[StateBus] ❌ 状态池空荡无存。未检视到处于 Priority/Ready 标记的任务指令。流程休眠。")
             return []

        # 将 D1 返回结果映射回老版的字典格式，保证代码兼容
        def _map_to_old_dict(r):
            return {
                "record_id": str(r["id"]),
                "Topic": r["topic"],
                "大项分类": r["category_name"],
                "Status": r["status"],
                "Source_Trend": r["source_trend"],
                "created_at": r["created_at"]
            }
            
        priority_topics = [_map_to_old_dict(r) for r in priority_topics]
        ready_topics = [_map_to_old_dict(r) for r in ready_topics]

        # 轮询防止分布倾斜
        grouped_topics = defaultdict(list)
        for t in ready_topics:
            cat = t.get('大项分类') or '未分类'
            grouped_topics[cat].append(t)

        sorted_topics = []
        for t in priority_topics:
            sorted_topics.append(t)
            
        lists = list(grouped_topics.values())
        for items in zip_longest(*lists):
            for item in items:
                if item is not None:
                    sorted_topics.append(item)
                    
        sorted_topics = sorted_topics[:max_total_limit]
        print(f"[StateBus] 🔄 管线封口排期结束。此次总管线分配 {len(sorted_topics)} 单下达指令至主算力。")
        return sorted_topics

    def mark_job_status(self, job_record_id: str, fields: dict):
        """
        为某个正在处理的任务更新节点进度状态和附属成果
        """
        if not job_record_id:
            return False
            
        # 字段映射字典（老版字典 Key -> D1 表字段）
        mapping = {
            "Title": "topic",             # 生成时覆盖原有标题
            "HTML_Content": "content_body",
            "Status": "status",
            "关键词": "keywords",
            "摘要": "summary",
            "Tags": "keywords",           # 降级合并到 keywords 中
            "URL": "publish_url",
            "发布时间": "published_at",
            "error_log": "error_log"
        }
        
        update_parts = []
        params = []
        for k, v in fields.items():
            db_key = mapping.get(k)
            if db_key:
                update_parts.append(f"{db_key} = ?")
                params.append(str(v) if v is not None else "")
                
        if not update_parts:
            return True
            
        params.append(job_record_id)
        sql = f"UPDATE seo_articles SET {', '.join(update_parts)} WHERE id = ?"
        
        success = self.client.execute(sql, params)
        if success is not None:
             print(f"[StateBus] 💾 D1 远程状态握手完成 (ID: {job_record_id} 并已推向 {fields.get('Status')} 轨道)")
             return True
        return False

    def pull_pending_publish_jobs(self, limit: int, category: str = None):
        """
        [节点 3 拉取] 从云端总线拉取处于撰写完毕待投发状态的任务。
        """
        print(f"[StateBus] ☁️ 正在向 D1 总线核接待发布(Pending)文章...")
        cat_sql = " AND category_name = ?" if category else ""
        
        params_pri = [config.STATUS_TOP_PRIORITY_PENDING]
        if category: params_pri.append(category)
        priority_records = self.client.execute(
            f"SELECT * FROM seo_articles WHERE status = ? {cat_sql} ORDER BY created_at DESC LIMIT ?", 
            params_pri + [limit]
        ) or []
        
        remaining_limit = limit - len(priority_records)
        standard_records = []
        if remaining_limit > 0:
            params_std = [config.STATUS_PENDING]
            if category: params_std.append(category)
            standard_records = self.client.execute(
                f"SELECT * FROM seo_articles WHERE status = ? {cat_sql} ORDER BY created_at DESC LIMIT ?", 
                params_std + [remaining_limit]
            ) or []
            
        records = priority_records + standard_records
        
        # 映射回老代码兼容格式
        def _map_to_old_dict(r):
            return {
                "record_id": str(r["id"]),
                "Topic": r["topic"],
                "大项分类": r["category_name"],
                "Status": r["status"],
                "Source_Trend": r["source_trend"],
                "Title": r["topic"], 
                "HTML_Content": r["content_body"],
                "摘要": r["summary"],
                "关键词": r["keywords"]
            }
        
        pending_records = [_map_to_old_dict(r) for r in records]
        print(f"[StateBus] 📋 发现分配总数 {len(pending_records)} 篇待投发网络文章。")
        return pending_records
        
    def mark_as_published(self, record_id: str, article_data: dict, published_url: str):
        """
        更新文章发布完成状态
        """
        from datetime import datetime
        self.mark_job_status(record_id, {
            "Status": config.STATUS_PUBLISHED,
            "URL": published_url,
            "发布时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        return True

    def mark_as_ready_to_retry(self, record_id: str):
        self.mark_job_status(record_id, {"Status": config.STATUS_READY})
        return True

    def fetch_published_articles(self, limit: int) -> list:
        records = self.client.execute(
            "SELECT * FROM seo_articles WHERE status = ? LIMIT ?", 
            [config.STATUS_PUBLISHED, limit]
        ) or []
        return records

    def send_notification(self, title, content):
        webhook_url = getattr(config, 'FEISHU_WEBHOOK_URL', None)
        if not webhook_url:
            return False
        try:
            payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": title},
                        "template": "blue"
                    },
                    "elements": [
                        {"tag": "div", "text": {"tag": "lark_md", "content": content}}
                    ]
                }
            }
            requests.post(webhook_url, json=payload, timeout=10)
            return True
        except:
            return False
