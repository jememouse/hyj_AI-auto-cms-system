import os
import sys
import json
import re
import time
import random
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workflow import BaseWorkflow
from agents.chief_editor import ChiefEditorAgent
from shared import config


class ArticleWorkflow(BaseWorkflow):
    """
    Step 2：文章生成工作流

    fetch_jobs  → StateBus.pull_ready_jobs()，含 Priority 插队 + Round-Robin 均衡
    process_job → ChiefEditorAgent.write_article()，GEO+SEO 深度撰写
    on_success  → StateBus.mark_job_status()，状态流转至 Pending/Top priority
    on_failure  → 保持 Ready 状态，等待下次重试（无需写回）
    """

    def __init__(self):
        super().__init__("ArticleWorkflow")
        self.editor = ChiefEditorAgent()

    def fetch_jobs(self) -> list:
        limit = config.STEP2_STRATEGY.get("max_generate_total", 120)
        category_filter = os.getenv("ARTICLE_CATEGORY")
        return self.bus.pull_ready_jobs(limit, category=category_filter)

    def process_job(self, job: dict):
        source_trend = job.get('Source_Trend', '')
        if source_trend:
            # 清洗内部标签，防止 LLM 在正文中产生 "[外部指定]"、"[百度]" 等标识词幻觉
            clean_trend = re.sub(r'\[.*?\]\s*', '', source_trend).strip()
            print(f"   🔥 [Newsjacking] 关联热点: {clean_trend} (原始匹配: {source_trend})")
            source_trend = clean_trend

        return self.editor.write_article(
            job['Topic'],
            job['大项分类'],
            source_trend=source_trend
        )

    def on_success(self, job: dict, article: dict):
        title = article.get('title', '').strip()
        content = article.get('html_content', '').strip()

        if not title or len(content) < 50:
            print(f"   ⚠️ [Error] 生成内容无效 (Title: {len(title)}, Content: {len(content)})")
            print(f"   🛑 跳过保存，保持 Ready 状态等待重试")
            return

        is_priority = (job.get('Status') == config.STATUS_PRIORITY)
        target_status = config.STATUS_TOP_PRIORITY_PENDING if is_priority else config.STATUS_PENDING

        final_tags = article.get('tags')
        if is_priority:
            priority_tag = "盒艺家包装"
            if not final_tags:
                final_tags = priority_tag
            elif isinstance(final_tags, list):
                if priority_tag not in final_tags:
                    final_tags.insert(0, priority_tag)
                final_tags = ", ".join(str(t) for t in final_tags)
            else:
                tags_list = [t.strip() for t in str(final_tags).split(',') if t.strip()]
                if priority_tag not in tags_list:
                    tags_list.insert(0, priority_tag)
                final_tags = ", ".join(tags_list)

        fields = {
            "Title": title,
            "HTML_Content": content,
            "Status": target_status,
            "关键词": article.get('keywords'),
            "摘要": article.get('summary'),
            "描述": article.get('description'),
            "Tags": final_tags,
            "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            # 重生成时清除旧发布信息
            "URL": "",
            "发布时间": "",
            "One_Line_Summary": article.get('one_line_summary', ''),
            "Schema_FAQ": json.dumps(article.get('schema_faq', []), ensure_ascii=False),
            "Key_Points": json.dumps(article.get('key_points', []), ensure_ascii=False)
        }

        self.bus.mark_job_status(job.get('record_id'), fields)

    def _wait(self):
        wait_min = config.STEP2_STRATEGY.get("wait_time_min", 2.0)
        wait_max = config.STEP2_STRATEGY.get("wait_time_max", 4.0)
        wait_time = random.uniform(wait_min, wait_max)
        print(f"   ⏳ 等待 {wait_time:.1f} 秒...")
        time.sleep(wait_time)
