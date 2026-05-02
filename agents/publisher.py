import sys
import os
from typing import Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.agent import BaseAgent
from skills.publish_skill import WellCMSPublishSkill

class PublisherAgent(BaseAgent):
    """
    智能体: 发布员
    职责: 负责将生成好的内容发布到 CMS 系统
    """
    def __init__(self, username: str = None, password: str = None):
        super().__init__(
            name="Publisher",
            role="发布专员",
            description="负责文章上架、封面图上传、排版检查"
        )
        self.add_skill(WellCMSPublishSkill(username=username, password=password))

    def publish_article(self, article_data: Dict) -> str:
        """
        [High-Level Action] 发布一篇文章
        Returns: Published URL or Empty string
        """
        print(f"🤖 [{self.name}] 开始发布: {article_data.get('title')}")
        
        result = self.use_skill("wellcms_publish", article_data)
        
        if result and result.get("success"):
            url = result.get("url")
            print(f"✅ [{self.name}] 发布成功! URL: {url}")
            return url
        else:
            print(f"❌ [{self.name}] 发布失败")
            return ""

    def open_session(self) -> bool:
        """打开并登录会话以供连续发布使用"""
        print(f"🤖 [{self.name}] 正在打开复用会话并登录...")
        return self.skills["wellcms_publish"].open_session()
        
    def publish_in_session(self, article_data: Dict) -> str:
        """在当前已打开的会话中发布文章"""
        print(f"🤖 [{self.name}] 会话内开始发布: {article_data.get('title')}")
        result = self.skills["wellcms_publish"].publish_in_session(article_data)
        if result and result.get("success"):
            url = result.get("url")
            print(f"✅ [{self.name}] 发布成功! URL: {url}")
            return url
        else:
            print(f"❌ [{self.name}] 发布失败")
            return ""
            
    def close_session(self):
        """关闭当前的发布会话"""
        print(f"🤖 [{self.name}] 关闭会话")
        self.skills["wellcms_publish"].close_session()
