import os
import json
import time
from collections import defaultdict
from itertools import zip_longest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.google_client import GoogleSheetClient
from shared import config

class StateBus:
    """
    统一状态大巴：接管所有针对本地存储与云端表（Google Sheet）的读写与流转校验。
    """
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.output_file = os.path.join(self.base_dir, 'generated_seo_data.json')
        self.client = GoogleSheetClient()

    def push_new_topics(self, new_topics: list):
        """
        [节点 1 提供] 将新产生的话题推入总线：
        自动完成去重比对、落盘并同步至 Google Sheet 网络总线。
        """
        if not new_topics:
            return

        # 1. 设置系统标准流转状态标签
        for t in new_topics:
            if '[外部指定]' in t.get('Source_Trend', ''):
                t['Status'] = config.STATUS_PRIORITY
            else:
                t['Status'] = config.STATUS_READY

        # 2. 读取云端状态进行去重对比 (因为 Github Actions 是无状态容器，不能依赖本地 json)
        existing_topics = set()
        print("[StateBus] ☁️ 正在从 Google Sheet 获取历史文章进行云端去重比对...")
        try:
            # 简化：获取所有文章的标题
            all_records = self.client._get_sheet("cms").get_all_records()
            for r in all_records:
                title = r.get("Title") or r.get("Topic") or ""
                if title:
                    existing_topics.add(title)
            print(f"[StateBus] 📊 获取到 {len(existing_topics)} 个云端历史话题。")
        except Exception as e:
            print(f"[StateBus] ⚠️ 获取云端历史记录失败，退化为不完全去重: {e}")
        
        # 3. 过滤重复记录
        added_count = 0
        added_topics = []
        for t in new_topics:
            topic = t.get('Topic')
            if topic and topic not in existing_topics:
                added_topics.append(t)
                existing_topics.add(topic)
                added_count += 1
            else:
                print(f"[StateBus] ⏭️ 话题已存在云端，跳过: {topic}")
        
        if added_count > 0:

            # 4. 同步挂载到云端 Google Sheet
            print(f"[StateBus] ☁️ 正在推送 {added_count} 条新生代待处理任务给云端控制台流转...")
            try:
                upload_list = []
                now_str = time.strftime("%Y-%m-%d %H:%M:%S")
                for t in added_topics:
                    record = {
                        "Topic": t['Topic'],
                        "大项分类": t['大项分类'],
                        "Status": t['Status'],
                        "Source_Trend": t.get('Source_Trend', ''),
                        "选题生成时间": t.get('created_at') or now_str
                    }
                    upload_list.append(record)
                
                success = self.client.batch_create_records(upload_list)
                if success:
                    print(f"[StateBus] ✅ 流量推送成功！{len(upload_list)} 条新指令已并入网络节点 (Google Sheet)。")
            except Exception as e:
                print(f"[StateBus] ❌ 网络层总线路由异常 (Google Sheet 同步失败): {e}")

    def pull_ready_jobs(self, max_total_limit: int):
        """
        [节点 2 拉取] 从状态总线获取准备好的写入任务
        包含基于公平优先级的分配组装（Priority 插队及普通请求 Round-Robin）。
        
        返回: 执行清单列表 List[dict]
        """
        print("[StateBus] ☁️ 正在向公共状态总线核对库存任务清单...")
        
        # 拉取高级指令槽
        priority_topics = self.client.fetch_records_by_status(config.STATUS_PRIORITY, limit=100, sort_by_time_col="选题生成时间", reverse_batch=False)
        # 拉取普通指令槽
        ready_topics = self.client.fetch_records_by_status(config.STATUS_READY, limit=500, sort_by_time_col="选题生成时间", reverse_batch=False)
        
        if not (priority_topics + ready_topics):
             print("[StateBus] ❌ 状态池空荡无存。未检视到处于 Priority/Ready 标记的任务指令。流程休眠。")
             return []

        print(f"[StateBus] 📋 核对完毕：捕获指引任务 {len(priority_topics)} 篇(特权)，以及普通队栈任务 {len(ready_topics)} 篇。")
        print(f"[StateBus] ⚙️ 业务网关配置准入流量：每次最大吞吐 {max_total_limit} 篇。")

        # 对平凡任务执行轮询(Round-Robin)防止某类大项分类导致线程阻塞挂起
        grouped_topics = defaultdict(list)
        for t in ready_topics:
            cat = t.get('大项分类') or t.get('category') or '未分类'
            t['大项分类'] = cat
            
            # 安全后备字典键名修复
            if 'Topic' not in t:
                t['Topic'] = t.get('topic', '')
                
            grouped_topics[cat].append(t)

        sorted_topics = []
        
        # 1. 先进先填: 特权流（无缝插队）
        for t in priority_topics:
            sorted_topics.append(t)
            
        # 2. 轮流挂载：普通流（防止分布倾斜）
        lists = list(grouped_topics.values())
        for items in zip_longest(*lists):
            for item in items:
                if item is not None:
                    sorted_topics.append(item)
                    
        # 截流限闸
        sorted_topics = sorted_topics[:max_total_limit]
        print(f"[StateBus] 🔄 管线封口排期结束。此次总管线分配 {len(sorted_topics)} 单下达指令至主算力。")
        
        return sorted_topics

    def mark_job_status(self, job_record_id: str, fields: dict):
        """
        为某个正在处理的任务更新节点进度状态和附属成果
        """
        if not job_record_id:
            # 安全防呆: 没有ID则重补
            self.client.create_record(fields)
            print("[StateBus] ⚠️ 警告：总线流浪记录。已在表尾重新构建状态记录。")
            return True
            
        success = self.client.update_record(job_record_id, fields)
        if success:
             print(f"[StateBus] 💾 远程状态节点握手完成 (ID: {job_record_id} 并已推向 {fields.get('Status')} 轨道)")
        return success

    def pull_pending_publish_jobs(self, limit: int, category: str = None):
        """
        [节点 3 拉取] 从云端总线拉取处于撰写完毕待投发状态的任务。
        依照 Priority 队列插入最前的原则。
        """
        print(f"[StateBus] ☁️ 正在向公共状态总线核接待发布(Pending)文章... (分类过滤: {category or '无'})")
        # 1. 优先拉取最高优先级队列 (Top_priority_pending 或等价状态)
        priority_records = self.client.fetch_records_by_status(
            status=config.STATUS_TOP_PRIORITY_PENDING, 
            category=category,
            limit=limit,
            sort_by_time_col="生成时间",
            reverse_batch=True
        )
        
        remaining_limit = limit - len(priority_records)
        standard_records = []
        if remaining_limit > 0:
            standard_records = self.client.fetch_records_by_status(
                status=config.STATUS_PENDING, 
                category=category,
                limit=remaining_limit,
                sort_by_time_col="生成时间",
                reverse_batch=True
            )
            
        pending_records = priority_records + standard_records
        print(f"[StateBus] 📋 发现分配总数 {len(pending_records)} 篇待流转网络文章 (特权: {len(priority_records)}, 常规: {len(standard_records)})")
        return pending_records
        
    def mark_as_published(self, record_id: str, article_data: dict, published_url: str):
        """
        更新文章发布完成状态，并沉淀内容到自己的 SEO 知识库
        """
        from datetime import datetime
        self.mark_job_status(record_id, {
            "Status": config.STATUS_PUBLISHED,
            "URL": published_url,
            "发布时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        # Asset Write-back (SEO Closed Loop)
        self._record_to_assets(article_data, published_url)
        return True

    def mark_as_ready_to_retry(self, record_id: str):
        self.mark_job_status(record_id, {"Status": config.STATUS_READY})
        return True

    def fetch_published_articles(self, limit: int) -> list:
        """
        [节点 4 使用] 从总线拉取已发布文章，作为社媒内容素材库
        """
        return self.client.fetch_records_by_status(
            status=config.STATUS_PUBLISHED,
            limit=limit
        )

    def send_notification(self, title, content):
        self.client.send_notification(title=title, content=content)

    def _record_to_assets(self, article, url):
        """
        将已发布的文章记录到本地资产库，用于 SEO 内链
        """
        import json
        from datetime import datetime
        ASSETS_FILE = os.path.join(self.base_dir, "published_assets.json")
        
        new_record = {
            "title": article.get("title"),
            "url": url,
            "keywords": article.get("keywords"),
            "category_id": article.get("category_id"),
            "summary": article.get("summary"),
            "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        try:
            data = []
            if os.path.exists(ASSETS_FILE):
                with open(ASSETS_FILE, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                    except:
                        data = []
            
            existing_idx = next((i for i, item in enumerate(data) if item.get("url") == url), -1)
            if existing_idx >= 0:
                data[existing_idx] = new_record
            else:
                data.append(new_record)
                
            with open(ASSETS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            print(f"[StateBus] 📚 [SEO] 已沉淀至内部网络资产词典库 (当前总计厚度 {len(data)} 篇)")
            
        except Exception as e:
            print(f"[StateBus] ⚠️ 内部资产库更新受阻: {e}")
