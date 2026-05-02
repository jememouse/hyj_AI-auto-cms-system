import sys
import os
from typing import Dict, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.skill import BaseSkill
from shared import config
from step3_publish.wellcms_rpa import WellCMSPublisher

class WellCMSPublishSkill(BaseSkill):
    """
    技能: 将文章发布到 WellCMS (Playwright RPA)
    """
    def __init__(self, username: str = None, password: str = None):
        super().__init__(
            name="wellcms_publish",
            description="自动登录 WellCMS 后台并发布文章，处理封面图和 SEO 字段"
        )
        self.publisher = WellCMSPublisher(username=username, password=password)

    def execute(self, input_data: Dict) -> Dict:
        """
        Input: Article Dict (title, content, keywords...)
        Output: {"success": bool, "url": str}
        """
        article = input_data
        
        # 复用 step3_publish/wellcms_rpa.py 中的核心逻辑
        # 因为 RPA 逻辑复杂且依赖 Playwright，我们直接 wrap 原有的 WellCMSPublisher 类
        
        try:
            success, url = self.publisher.publish(article)
            return {
                "success": success,
                "url": url
            }
        except Exception as e:
            print(f"❌ [Skill: Publish] 失败: {e}")
            return {"success": False, "url": ""}

    def open_session(self) -> bool:
        """打开可复用的会话"""
        return self.publisher.open_session()
        
    def publish_in_session(self, article: Dict) -> Dict:
        """在已有会话中发布"""
        try:
            success, url = self.publisher.publish_in_session(article)
            return {"success": success, "url": url}
        except Exception as e:
            print(f"❌ [Skill: Publish Session] 失败: {e}")
            return {"success": False, "url": ""}
            
    def close_session(self):
        """关闭复用会话"""
        self.publisher.close_session()
