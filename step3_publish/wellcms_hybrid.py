import sys
import os
import time
import logging
import requests
from typing import Dict, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright
from shared import config
from step3_publish.wellcms_rpa import WellCMSPublisher

logger = logging.getLogger(__name__)

class WellCMSHybridPublisher(WellCMSPublisher):
    """
    WellCMS 混合驱动发布器 (Hybrid Engine)
    - 阶段 1: Playwright 自动处理复杂的加密登录
    - 阶段 2: 提取 Cookie 移交 requests API 瞬间发文
    """
    
    def __init__(self, username: str = None, password: str = None):
        super().__init__(username, password)
        self.api_session = requests.Session()
        self.api_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        })
        self.cookies_extracted = False

    def _login(self) -> bool:
        """覆写登录：登录成功后立刻提取 Cookie 并接管"""
        # 复用父类稳定的 Playwright 登录
        success = super()._login()
        if not success:
            return False
            
        logger.info("✅ [Hybrid] Playwright 物理登录成功，开始提取底层 Cookie 凭证...")
        # 提取 Cookie
        cookies = self.page.context.cookies()
        for cookie in cookies:
            self.api_session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])
        
        self.cookies_extracted = True
        logger.info("✅ [Hybrid] Cookie 提取成功！即将关闭浏览器引擎，移交 API 纯净接管。")
        
        # 卸磨杀驴，直接关掉浏览器释放服务器内存
        self._close_browser()
        return True

    def _publish_article(self, article: Dict) -> Tuple[bool, str]:
        """完全绕过页面的 API 极速发贴"""
        if not self.cookies_extracted:
            if not self._login():
                return False, ""

        logger.info("🚀 [Hybrid] 开始构建极速 API 报文...")
        
        category_mapping = {
            "专业知识": "1",
            "行业资讯": "2",
            "产品介绍": "3"
        }
        category_id = category_mapping.get(article.get('category_id'), "2")
        submit_url = f"{self.admin_url}?0=content&1=create&fid={category_id}"
        
        # 预先拉取发布页面，提取可能存在的安全校验码 (FORM_HASH 等)
        try:
            from bs4 import BeautifulSoup
            page_resp = self.api_session.get(submit_url)
            soup = BeautifulSoup(page_resp.text, 'html.parser')
            hidden_inputs = soup.find_all("input", type="hidden")
        except Exception as e:
            logger.warning(f"⚠️ 提取表单隐藏字段失败: {e}")
            hidden_inputs = []
        
        # 组装原版表单
        payload = {
            "subject": article.get("title", "未命名标题"),
            "fid": category_id,
            "brief": article.get("summary", ""),
            "keyword": article.get("keywords", ""),
            "tags": article.get("tags", article.get("keywords", "")),
            "description": article.get("description", ""),
            "message": article.get("html_content", ""),
            "closed": "1"
        }
        
        for hidden_input in hidden_inputs:
            name = hidden_input.get("name")
            value = hidden_input.get("value", "")
            if name and name not in payload:
                payload[name] = value

        logger.info(f"📤 [Hybrid] 正在向服务器轰炸发送文章 (标题: {payload['subject'][:15]}...)")
        
        try:
            # 使用 requests 发起纯正的 HTTP POST (耗时不到 0.5s)
            resp = self.api_session.post(submit_url, data=payload, allow_redirects=False, timeout=10)
            
            # WellCMS 发布成功后通常返回 302 跳转
            if resp.status_code in [301, 302]:
                redirect_url = resp.headers.get("Location", "")
                logger.info(f"✅ [Hybrid] 秒发成功！收到系统重定向: {redirect_url}")
                if redirect_url.startswith("http"):
                    return True, redirect_url
                else:
                    base_url = self.admin_url.split("/admin")[0]
                    return True, f"{base_url}/{redirect_url}"
            elif resp.status_code == 200:
                try:
                    resp_json = resp.json()
                    if resp_json.get("code") == 0 or resp_json.get("message") == "ok":
                        logger.info("✅ [Hybrid] AJAX 响应秒发成功！")
                        return True, "Published_via_API"
                    else:
                        logger.warning(f"⚠️ 服务器驳回发贴: {resp.text}")
                except:
                    logger.warning(f"⚠️ 无法解析 200 响应内容: {resp.text[:200]}")
                return False, ""
            else:
                logger.error(f"❌ 接口报错，状态码: {resp.status_code}")
                return False, ""
                
        except Exception as e:
            logger.error(f"❌ API 发送异常: {e}")
            return False, ""

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    publisher = WellCMSHybridPublisher()
    publisher._init_browser()
    success, url = publisher._publish_article({
        "title": "Hybrid API 极速发贴测试",
        "category_id": "2",
        "summary": "这是混合引擎的测试文章。",
        "html_content": "<p>测试成功！不仅绕过了登录加密，还能绕开前端编辑器！</p>",
        "keywords": "测试, API"
    })
    print(f"最终结果: Success={success}, URL={url}")
