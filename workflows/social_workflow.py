import os
import sys
import time
import random
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workflow import BaseWorkflow
from agents.social_manager import SocialManagerAgent
from shared import config
from shared.google_client import GoogleSheetClient


class SocialWorkflow(BaseWorkflow):
    """
    Step 4：社媒矩阵分发工作流（Fan-out 模式）

    fetch_jobs → StateBus.fetch_published_articles()，拉取已发布文章作为素材库
    run()      → 按平台维度 fan-out：遍历 SOCIAL_PLATFORMS，按配额生成社媒文案
    process_job → SocialManagerAgent.create_social_post()，改写为平台风格文案
    on_success  → 写入对应平台 Google Sheet（Draft 状态）

    注意：Step 4 写入目标是各平台独立 Sheet，不走主流水线状态机，
         故平台写入仍使用 GoogleSheetClient，由 Workflow 层持有。
    """

    def __init__(self):
        super().__init__("SocialWorkflow")
        self.agent = SocialManagerAgent()
        self.client = GoogleSheetClient()
        self.base_time = datetime.now()
        self._current_platform = None

    def fetch_jobs(self) -> list:
        print("🔍 [System] 正在加载素材库 (Published Articles)...")
        records = self.bus.fetch_published_articles(limit=300)
        print(f"📚 素材库就绪: {len(records)} 篇")
        return records

    def process_job(self, job: dict):
        """job 为已发布文章，改写为当前平台的社媒文案"""
        article_content = job.get("HTML_Content", "")
        if not article_content or len(article_content) < 100:
            return None
            
        import re
        clean_content = re.sub(r'<[^>]+>', '', article_content)
        
        return self.agent.create_social_post(
            job.get("Title", "无标题"),
            clean_content,
            self._current_platform
        )

    def on_success(self, job: dict, post_data: dict):
        if not post_data.get('title') or not post_data.get('content'):
            print(f"   ⚠️ [Error] 生成内容无效，跳过保存")
            return
        new_record = {
            "Title": post_data['title'],
            "Content": post_data['content'],
            "Keywords": post_data['keywords'],
            "Source": post_data['source_title'],
            "Status": "Draft",
            "Cover": post_data.get('cover_url', ''),
            "生成时间": self.base_time.strftime("%Y-%m-%d %H:%M:%S")
        }
        p_sheet = config.SOCIAL_PLATFORMS[self._current_platform]['sheet_name']
        self.client.create_record(new_record, table_id=p_sheet)
        print(f"   💾 [System] 已保存至 {p_sheet}")

    def run(self):
        """覆写 run()：Step 4 是 fan-out 模式，外层按平台迭代，内层按素材配额消费"""
        print(f"\n{'=' * 50}")
        print(f"🤖 启动 Workflow: {self.name}")
        print(f"{'=' * 50}\n")

        source_records = self.fetch_jobs()
        if not source_records:
            print("❌ 素材库为空，无法生成社交内容。")
            return

        run_mode = os.getenv("SOCIAL_RUN_MODE", "accumulate")
        today_str = self.base_time.strftime("%Y-%m-%d")

        for p_key, p_conf in config.SOCIAL_PLATFORMS.items():
            p_name = p_conf['name']
            p_target = p_conf['daily_target']
            p_sheet = p_conf['sheet_name']

            print(f"\n🌊 [Platform] 开始处理平台: {p_name} (目标: {p_target}/天)")

            sheet_obj = self.client._get_sheet(p_sheet)
            if not sheet_obj:
                print(f"   ❌ 无法获取工作表 {p_sheet}，跳过")
                continue

            today_count = sum(
                1 for r in sheet_obj.get_all_records()
                if today_str in str(r.get('生成时间', ''))
            )

            if run_mode == "batch":
                remaining_quota = p_target
                print(f"   🚀 [Batch Mode] 增量模式: 忽略今日已发 ({today_count})，目标: {remaining_quota}")
            else:
                remaining_quota = p_target - today_count
                print(f"   📊 [Accumulate Mode] 水位补齐: {today_count}/{p_target} (需补: {remaining_quota})")

            if remaining_quota <= 0:
                print(f"   ✅ 今日配额已满，跳过。")
                continue

            self._current_platform = p_key
            
            # 使用加权随机抽取，优先最新发布的文章
            pool_source = list(source_records)
            weights = [max(1, len(pool_source) - i) for i in range(len(pool_source))]
            
            pool = []
            if pool_source:
                # 按照权重抽取足够数量（有放回，去重）
                sampled_raw = random.choices(pool_source, weights=weights, k=len(pool_source)*3)
                seen = set()
                for item in sampled_raw:
                    item_id = item.get("id") or item.get("record_id") or str(item)
                    if item_id not in seen:
                        seen.add(item_id)
                        pool.append(item)
            
            success_count = 0

            for record in pool:
                if success_count >= remaining_quota:
                    break
                try:
                    result = self.process_job(record)
                    if result:
                        self.on_success(record, result)
                        success_count += 1
                        time.sleep(2)
                except Exception as e:
                    print(f"   ⚠️ 处理异常: {e}")

            print(f"   🎉 {p_name} 完成，本次生成: {success_count} 篇")
